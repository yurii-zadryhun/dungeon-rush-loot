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
    """Offense-oriented target build, rather than 50/50 PvE-PvP averaging.

    Exactly twelve exceptional slots are available on six [EXP] pieces.
    The desired allocation is 2 CDT, 1 ranged and 1 melee defense, then
    3-4 triple and 4-5 mega rolls. Goals saturate: another defense roll
    beyond the target has no special value, and never replaces a missing
    offensive role simply because raw defense keeps growing.

    Normal-roll weights are evaluated for EACH interchangeable item, not for
    combined totals (which otherwise conceal a missing stat on one item).
    All bonuses are continuous, allowing greedy single-item replacements.
    """

    name = ScoringStrategy.UNIVERSAL
    # Explicit quality targets; points are on the same scale as the combat
    # log-score. These are preferences, not verified game-mechanic formulas.
    CDT_PER_ROLL = 50.0
    SIDE_DEFENSE_PER_ROLL = 95.0
    TRIPLE_TOTAL = 95.0
    MEGA_TOTAL = 40.0
    NORMAL_WEIGHTS = {
        "attack speed": 22.0,
        "critical damage": 22.0,
        "critical chance": 14.0,
        "damage": 6.0,
        "ranged damage": 6.0,
        "lifesteal": 2.0,
        "block chance": 2.0,
        "health": 2.0,
    }

    def __init__(self, pve: BuildScoringStrategy) -> None:
        self.pve = pve

    @staticmethod
    def _rolls(metrics: BuildMetrics, name: str) -> tuple[float, ...]:
        if metrics.equipment_rolls is None:
            return (max(0.0, metrics.stats.get(name, 0.0)),)
        return tuple(sorted(metrics.equipment_rolls.get(name, ()), reverse=True))

    @staticmethod
    def _saturation(value: float, target: float) -> float:
        return min(max(value / target, 0.0), 1.0)

    def score(self, metrics: BuildMetrics) -> CombatStrategyScore:
        from dataclasses import replace
        from .config import SKILLS

        # PVE is the foundation, but defense beyond the requested coverage
        # is not a reason to hoard more defensive rolls.
        combat_stats = dict(metrics.stats)
        for name in ("ranged defense", "melee defense"):
            combat_stats[name] = min(combat_stats.get(name, 0.0), 100.0)
        pve = self.pve.score(replace(metrics, stats=combat_stats))

        cdt = self._rolls(metrics, "critical damage taken")
        ranged = self._rolls(metrics, "ranged defense")
        melee = self._rolls(metrics, "melee defense")
        triple = self._rolls(metrics, "triple hit chance")
        mega = self._rolls(metrics, "mega crit chance")

        # Desired defensive distribution: two separate -50% CDT rolls and
        # ONE strong roll for each damage type. Extra defense saturates.
        # Favor near-cap rolls rather than accumulating weak fragments. The
        # convex finish bonus makes 50 vs 47 CDT and 95 vs 87 defense matter.
        def coverage(value: float, target: float) -> float:
            ratio = self._saturation(value, target)
            return 125.0 * ratio + 110.0 * ratio ** 14

        defense = sum(coverage(v, self.CDT_PER_ROLL) for v in cdt[:2])
        defense += coverage(ranged[0], self.SIDE_DEFENSE_PER_ROLL) if ranged else 0.0
        defense += coverage(melee[0], self.SIDE_DEFENSE_PER_ROLL) if melee else 0.0

        # A third or fourth strong Triple roll reaches ~90-100; 4-5 Mega
        # rolls reach ~40-50. Reward both total and individually good rolls.
        triple_ratio = self._saturation(sum(triple), self.TRIPLE_TOTAL)
        triple_bonus = 240.0 * triple_ratio
        triple_bonus += 25.0 * sum(self._saturation(v, 26.0) for v in triple[:4])
        mega_ratio = self._saturation(sum(mega), self.MEGA_TOTAL)
        mega_bonus = 240.0 * mega_ratio + 120.0 * mega_ratio ** 12
        mega_bonus += 52.0 * sum(self._saturation(v, 9.5) for v in mega[:4])

        # Rank every normal affix separately; an attack-speed+crit-damage
        # pair in six slots earns six times the reward of the same pair in
        # one slot. No reward for junk beyond its effect on genuine PvE DPS.
        normal = sum(
            weight * sum(
                self._saturation(v, SKILLS[name].cap) ** 1.5
                for v in self._rolls(metrics, name)
            )
            for name, weight in self.NORMAL_WEIGHTS.items()
        )
        # Same-piece AS + Crit Damage is preferred over distributing them
        # across different items at identical aggregate totals. Crit Chance
        # is the softer, third normal affix of choice on each piece.
        paired_normals = 0.0
        for affixes in (metrics.item_affixes or {}).values():
            attack = self._saturation(affixes.get("attack speed", 0.0), 36.0)
            crit_damage = self._saturation(affixes.get("critical damage", 0.0), 90.0)
            crit_chance = self._saturation(affixes.get("critical chance", 0.0), 10.0)
            paired_normals += 10.0 * attack * crit_damage
            paired_normals += 4.0 * attack * crit_damage * crit_chance
        normal += paired_normals

        components = (
            ScoreComponent("pve", pve.total),
            ScoreComponent("target_defense", defense),
            ScoreComponent("target_triple", triple_bonus),
            ScoreComponent("target_mega", mega_bonus),
            ScoreComponent("normal_priorities", normal),
        )
        return CombatStrategyScore(
            total=sum(component.score for component in components),
            components=components,
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
    return UniversalScoringStrategy(pve)
