from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Protocol

from .domain import BuildMetrics, ScoreComponent, ScoringStrategy

SCORE_LOG_SCALE = 160.0
BASE_CRITICAL_MULTIPLIER = 1.05
HARD_CAPS: dict[str, float] = {
    "triple hit chance": 100.0,
    "double hit chance": 100.0,
    "mega crit chance": 100.0,
    "critical chance": 100.0,
    "critical damage taken": 100.0,
    "block chance": 100.0,
}


@dataclass(frozen=True)
class CombatStrategyScore:
    total: float
    components: tuple[ScoreComponent, ...]
    effective_stats: Mapping[str, float]


@dataclass(frozen=True)
class CritThreat:
    mega_crit_chance: float
    critical_chance: float
    critical_damage: float


@dataclass(frozen=True)
class StrategyProfile:
    name: ScoringStrategy
    enemy_cdt: float
    incoming_crit: CritThreat
    ranged_threat_share: float
    offense_weight: float
    defense_weight: float
    sustain_weight: float
    utility_weight: float
    lifesteal_soft_target: float
    movement_utility: float
    knockback_utility: float
    thorns_utility: float
    companion_damage_utility: float
    companion_cooldown_utility: float


class BuildScoringStrategy(Protocol):
    name: ScoringStrategy

    def score(self, metrics: BuildMetrics) -> CombatStrategyScore: ...


class CombatMath:
    @staticmethod
    def effective_stats(stats: Mapping[str, float]) -> dict[str, float]:
        effective = dict(stats)
        for name, cap in HARD_CAPS.items():
            if name in effective:
                effective[name] = min(max(effective[name], 0.0), cap)
        return effective

    @staticmethod
    def expected_hits(stats: Mapping[str, float]) -> float:
        triple = CombatMath._chance(stats.get("triple hit chance", 0.0))
        double = CombatMath._chance(stats.get("double hit chance", 0.0))
        return 1.0 + 2.0 * triple + (1.0 - triple) * double

    @staticmethod
    def expected_critical_multiplier(stats: Mapping[str, float], defender_cdt: float) -> float:
        mega = CombatMath._chance(stats.get("mega crit chance", 0.0))
        critical = CombatMath._chance(stats.get("critical chance", 0.0))
        critical_multiplier = BASE_CRITICAL_MULTIPLIER + max(0.0, stats.get("critical damage", 0.0)) / 100.0
        cdt = CombatMath._chance(defender_cdt)
        effective_critical = 1.0 + (critical_multiplier - 1.0) * (1.0 - cdt)
        mega_probability = mega
        critical_probability = (1.0 - mega) * critical
        normal_probability = (1.0 - mega) * (1.0 - critical)
        return (
            mega_probability * 2.0 * effective_critical
            + critical_probability * effective_critical
            + normal_probability
        )

    @staticmethod
    def offense_factor(metrics: BuildMetrics, stats: Mapping[str, float], enemy_cdt: float) -> float:
        attack_speed = 1.0 + max(0.0, stats.get("attack speed", 0.0)) / 100.0
        damage = max(0.0, stats.get("damage", 0.0)) + max(0.0, stats.get("ranged damage", 0.0))
        attack_power = metrics.attack_progression * (1.0 + damage / 100.0)
        return (
            attack_power
            * attack_speed
            * CombatMath.expected_hits(stats)
            * CombatMath.expected_critical_multiplier(stats, enemy_cdt)
        )

    @staticmethod
    def defense_factor(
        metrics: BuildMetrics,
        stats: Mapping[str, float],
        threat: CritThreat,
        ranged_threat_share: float,
    ) -> float:
        health = metrics.health_progression * (1.0 + max(0.0, stats.get("health", 0.0)) / 100.0)
        block = min(CombatMath._chance(stats.get("block chance", 0.0)), 0.999)
        block_ehp = 1.0 / (1.0 - block)
        ranged_defense = 1.0 + max(0.0, stats.get("ranged defense", 0.0)) / 100.0
        melee_defense = 1.0 + max(0.0, stats.get("melee defense", 0.0)) / 100.0
        ranged_share = min(max(ranged_threat_share, 0.0), 1.0)
        mixed_damage_fraction = (
            ranged_share / ranged_defense
            + (1.0 - ranged_share) / melee_defense
        )
        mixed_defense = 1.0 / mixed_damage_fraction
        incoming_without_cdt = CombatMath._incoming_crit_factor(0.0, threat)
        incoming_with_cdt = CombatMath._incoming_crit_factor(
            stats.get("critical damage taken", 0.0), threat
        )
        cdt_ehp = incoming_without_cdt / incoming_with_cdt
        return health * block_ehp * mixed_defense * cdt_ehp

    @staticmethod
    def sustain_factor(stats: Mapping[str, float], lifesteal_target: float) -> float:
        lifesteal = CombatMath._soft_saturation(stats.get("lifesteal", 0.0), lifesteal_target)
        regeneration = CombatMath._soft_saturation(stats.get("health regen", 0.0), 10.0)
        return 1.0 + lifesteal / 100.0 + 0.5 * regeneration / 100.0

    @staticmethod
    def utility_factor(stats: Mapping[str, float], profile: StrategyProfile) -> float:
        utility = (
            max(0.0, stats.get("movement speed", 0.0)) * profile.movement_utility
            + max(0.0, stats.get("knockback", 0.0)) * profile.knockback_utility
            + max(0.0, stats.get("thorns", 0.0)) * profile.thorns_utility
            + max(0.0, stats.get("companion damage", 0.0)) * profile.companion_damage_utility
            + max(0.0, stats.get("companion cooldown", 0.0)) * profile.companion_cooldown_utility
        )
        return 1.0 + utility / 100.0

    @staticmethod
    def _incoming_crit_factor(cdt: float, threat: CritThreat) -> float:
        stats = {
            "mega crit chance": threat.mega_crit_chance,
            "critical chance": threat.critical_chance,
            "critical damage": threat.critical_damage,
        }
        return CombatMath.expected_critical_multiplier(stats, cdt)

    @staticmethod
    def _chance(value: float) -> float:
        return min(max(value, 0.0), 100.0) / 100.0

    @staticmethod
    def _soft_saturation(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        return target * (1.0 - math.exp(-max(value, 0.0) / target))


class ProfileScoringStrategy:
    def __init__(self, profile: StrategyProfile) -> None:
        self.profile = profile
        self.name = profile.name

    def score(self, metrics: BuildMetrics) -> CombatStrategyScore:
        effective = CombatMath.effective_stats(metrics.stats)
        factors = (
            (
                "offense",
                self.profile.offense_weight,
                CombatMath.offense_factor(metrics, effective, self.profile.enemy_cdt),
            ),
            (
                "defense",
                self.profile.defense_weight,
                CombatMath.defense_factor(
                    metrics,
                    effective,
                    self.profile.incoming_crit,
                    self.profile.ranged_threat_share,
                ),
            ),
            (
                "sustain",
                self.profile.sustain_weight,
                CombatMath.sustain_factor(effective, self.profile.lifesteal_soft_target),
            ),
            ("utility", self.profile.utility_weight, CombatMath.utility_factor(effective, self.profile)),
        )
        components = tuple(
            ScoreComponent(name, SCORE_LOG_SCALE * weight * math.log(max(factor, 1e-9)))
            for name, weight, factor in factors
        )
        return CombatStrategyScore(
            total=sum(component.score for component in components),
            components=components,
            effective_stats=effective,
        )


class UniversalScoringStrategy:
    name = ScoringStrategy.UNIVERSAL
    BALANCE_PENALTY = 0.08

    def __init__(self, pve: BuildScoringStrategy, pvp: BuildScoringStrategy) -> None:
        self.pve = pve
        self.pvp = pvp

    def score(self, metrics: BuildMetrics) -> CombatStrategyScore:
        pve = self.pve.score(metrics)
        pvp = self.pvp.score(metrics)
        average = 0.5 * (pve.total + pvp.total)
        balance_penalty = self.BALANCE_PENALTY * abs(pve.total - pvp.total)
        return CombatStrategyScore(
            total=average - balance_penalty,
            components=(
                ScoreComponent("pve", 0.5 * pve.total),
                ScoreComponent("pvp", 0.5 * pvp.total),
                ScoreComponent("balance", -balance_penalty),
            ),
            effective_stats=pve.effective_stats,
        )


PVE_PROFILE = StrategyProfile(
    name=ScoringStrategy.PVE,
    enemy_cdt=0.0,
    incoming_crit=CritThreat(mega_crit_chance=5.0, critical_chance=20.0, critical_damage=100.0),
    ranged_threat_share=0.5,
    offense_weight=1.0,
    defense_weight=0.25,
    sustain_weight=0.15,
    utility_weight=0.05,
    lifesteal_soft_target=25.0,
    movement_utility=0.10,
    knockback_utility=0.05,
    thorns_utility=0.02,
    companion_damage_utility=0.05,
    companion_cooldown_utility=0.05,
)

PVP_PROFILE = StrategyProfile(
    name=ScoringStrategy.PVP,
    enemy_cdt=100.0,
    incoming_crit=CritThreat(mega_crit_chance=25.0, critical_chance=40.0, critical_damage=300.0),
    ranged_threat_share=0.5,
    offense_weight=0.80,
    defense_weight=1.0,
    sustain_weight=0.35,
    utility_weight=0.10,
    lifesteal_soft_target=35.0,
    movement_utility=0.20,
    knockback_utility=0.15,
    thorns_utility=0.10,
    companion_damage_utility=0.03,
    companion_cooldown_utility=0.03,
)


def strategy_for(name: ScoringStrategy) -> BuildScoringStrategy:
    pve = ProfileScoringStrategy(PVE_PROFILE)
    pvp = ProfileScoringStrategy(PVP_PROFILE)
    if name is ScoringStrategy.PVE:
        return pve
    if name is ScoringStrategy.PVP:
        return pvp
    return UniversalScoringStrategy(pve, pvp)
