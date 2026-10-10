from __future__ import annotations

import math
from statistics import mean

from .config import (
    BASE_SCORE_MAX,
    BASE_SCORE_MAX_LEVEL,
    BASE_SCORE_MAX_TIER,
    BASE_SCORE_MIN,
    BASE_SCORE_MIN_LEVEL,
    BASE_SCORE_MIN_TIER,
    LEVEL_SCALER,
    MAX_ITEM_LEVEL,
    MAX_STATS,
    MIN_STATS,
    SKILLS,
    TIER_SCALER,
)
from .domain import (
    Action,
    BuildMetrics,
    BuildScore,
    BuildStat,
    Comparison,
    ComparisonStatus,
    EquipmentSlot,
    ParsedItem,
    ScoreComponent,
)
from .equipment import EquipmentLoadout, EquipmentRepository, EquipmentStateError, beneficial_value
from .affix_rules import unparsed_affix_lines, validate_affixes
from .game_catalog import match_standard_item
from .strategies import BuildScoringStrategy
from .text import canonical_name

FLEXIBILITY_WEIGHT = 0.12
FLEXIBILITY_LOOKAHEAD_SLOTS = 2

PRIMARY_BASE = {
    EquipmentSlot.WEAPON: 7.0,
    EquipmentSlot.GLOVES: 6.0,
    EquipmentSlot.RING: 6.0,
    EquipmentSlot.HELMET: 45.0,
    EquipmentSlot.BACKPACK: 30.0,
    EquipmentSlot.NECKLACE: 20.0,
}
ATTACK_SLOTS = frozenset({EquipmentSlot.WEAPON, EquipmentSlot.GLOVES, EquipmentSlot.RING})
HEALTH_SLOTS = frozenset({EquipmentSlot.HELMET, EquipmentSlot.BACKPACK, EquipmentSlot.NECKLACE})
REFERENCE_PRIMARY_POWER = (TIER_SCALER**BASE_SCORE_MIN_TIER) * (1.0 + LEVEL_SCALER * BASE_SCORE_MIN_LEVEL)
REFERENCE_BASE_ATTACK = sum(PRIMARY_BASE[slot] for slot in ATTACK_SLOTS) * REFERENCE_PRIMARY_POWER
REFERENCE_BASE_HEALTH = sum(PRIMARY_BASE[slot] for slot in HEALTH_SLOTS) * REFERENCE_PRIMARY_POWER


class PrimaryPowerScorer:
    def score(self, item: ParsedItem) -> float:
        if item.tier is None or item.level is None:
            raise ValueError("Rarity/tier and level are required for base-power scoring.")
        return self._normalize(self._power(item.tier, item.level))

    @staticmethod
    def _power(tier: int, level: int) -> float:
        return (TIER_SCALER**tier) * (1.0 + LEVEL_SCALER * level)

    def _normalize(self, power: float) -> float:
        minimum = self._power(BASE_SCORE_MIN_TIER, BASE_SCORE_MIN_LEVEL)
        maximum = self._power(BASE_SCORE_MAX_TIER, BASE_SCORE_MAX_LEVEL)
        position = math.log(power / minimum) / math.log(maximum / minimum)
        return BASE_SCORE_MIN + position * (BASE_SCORE_MAX - BASE_SCORE_MIN)


class PrimaryStatCalculator:
    def value(self, slot: EquipmentSlot, item: ParsedItem) -> float:
        if slot not in PRIMARY_BASE:
            raise ValueError(f"{slot.value} does not use the standard slot primary formula.")
        if item.tier is None or item.level is None:
            raise ValueError("Rarity/tier and level are required for primary-stat scoring.")
        return PRIMARY_BASE[slot] * (TIER_SCALER**item.tier) * (1.0 + LEVEL_SCALER * item.level)


class BuildMetricsAggregator:
    def __init__(self, primary: PrimaryStatCalculator | None = None) -> None:
        self.primary = primary or PrimaryStatCalculator()

    def aggregate(self, loadout: EquipmentLoadout) -> BuildMetrics:
        stats: dict[str, float] = {}
        base_attack = 0.0
        base_health = 0.0
        for slot, item in loadout:
            if slot in ATTACK_SLOTS:
                base_attack += self.primary.value(slot, item)
            elif slot in HEALTH_SLOTS:
                base_health += self.primary.value(slot, item)
            elif slot is EquipmentSlot.WINGS:
                base_attack += item.primary_attack or 0.0
                base_health += item.primary_health or 0.0

            for stat in (*item.intrinsic_stats, *item.stats):
                name = canonical_name(stat.name)
                stats[name] = stats.get(name, 0.0) + beneficial_value(name, stat.value)
        return BuildMetrics(
            base_attack=base_attack,
            base_health=base_health,
            attack_progression=base_attack / REFERENCE_BASE_ATTACK,
            health_progression=base_health / REFERENCE_BASE_HEALTH,
            stats=stats,
        )


class BuildScorer:
    def __init__(
        self,
        strategy: BuildScoringStrategy,
        aggregator: BuildMetricsAggregator | None = None,
        flexibility_weight: float = FLEXIBILITY_WEIGHT,
    ) -> None:
        self.strategy = strategy
        self.aggregator = aggregator or BuildMetricsAggregator()
        self.flexibility_weight = flexibility_weight

    def score(self, loadout: EquipmentLoadout, protected_slot: EquipmentSlot | None = None) -> BuildScore:
        metrics = self.aggregator.aggregate(loadout)
        combat = self.strategy.score(metrics)
        flexibility = self._flexibility(loadout, protected_slot, combat.total)
        build_stats = tuple(
            BuildStat(name, raw, combat.effective_stats.get(name, raw))
            for name, raw in sorted(metrics.stats.items())
        )
        components = combat.components + (ScoreComponent("flexibility", flexibility),)
        return BuildScore(
            total=combat.total + flexibility,
            combat=combat.total,
            flexibility=flexibility,
            base_attack=metrics.base_attack,
            base_health=metrics.base_health,
            stats=build_stats,
            components=components,
        )

    def _flexibility(
        self,
        loadout: EquipmentLoadout,
        protected_slot: EquipmentSlot | None,
        full_combat_score: float,
    ) -> float:
        if protected_slot is None or self.flexibility_weight <= 0:
            return 0.0

        marginal_losses = []
        for slot, _ in loadout:
            if slot is protected_slot:
                continue
            stripped_metrics = self.aggregator.aggregate(loadout.without_affixes(slot))
            stripped_score = self.strategy.score(stripped_metrics).total
            marginal_losses.append(max(0.0, full_combat_score - stripped_score))

        if not marginal_losses:
            return 0.0
        count = min(FLEXIBILITY_LOOKAHEAD_SLOTS, len(marginal_losses))
        easiest_slots = sorted(marginal_losses)[:count]
        return -self.flexibility_weight * mean(easiest_slots)


class ItemComparer:
    def __init__(
        self,
        equipment: EquipmentRepository | None = None,
        scorer: BuildScorer | None = None,
        allow_partial: bool = False,
    ) -> None:
        self.equipment = equipment
        self.scorer = scorer
        self.allow_partial = allow_partial

    def compare(self, equipped: ParsedItem, candidate: ParsedItem) -> Comparison:
        # Do not bypass OCR and slot validation for hard-rejected melee drops.
        # Even SELL is an irreversible action and must be based on real cards.
        validation_error = self._validation_error(equipped, candidate)
        if validation_error:
            return self._check(equipped, candidate, validation_error)
        if self.equipment is None or self.scorer is None:
            return self._check(equipped, candidate, "Build-aware scoring requires an equipment state and strategy.")
        return self._build_comparison(equipped, candidate)

    def _build_comparison(self, equipped: ParsedItem, candidate: ParsedItem) -> Comparison:
        loadout = self.equipment.snapshot()
        try:
            slot = loadout.slot_of(equipped)
        except EquipmentStateError as exc:
            return self._check(equipped, candidate, str(exc))

        equipped_match = match_standard_item([equipped.title])
        candidate_match = match_standard_item([candidate.title])
        if equipped_match is None or equipped_match.slot is not slot:
            return self._check(equipped, candidate, "Equipped title does not match its catalog slot.")
        if candidate_match is None or candidate_match.slot is not slot:
            return self._check(equipped, candidate, "Candidate item is not in the equipped slot (game catalog).")

        if candidate.melee:
            return self._melee_rejection(equipped, candidate, slot)

        current_score = self.scorer.score(loadout, protected_slot=slot)
        candidate_score = self.scorer.score(loadout.with_replacement(slot, candidate), protected_slot=slot)
        action = Action.EQUIP if candidate_score.total > current_score.total + 0.01 else Action.SELL
        return Comparison(
            status=ComparisonStatus.OK,
            action=action,
            candidate=candidate,
            equipped=equipped,
            candidate_score=candidate_score,
            equipped_score=current_score,
            message=f"{self.scorer.strategy.name.value.upper()} build-aware scoring with caps, interactions and replacement flexibility.",
            equipment_slot=slot,
        )

    def _validation_error(self, equipped: ParsedItem, candidate: ParsedItem) -> str | None:
        for label, item in (("equipped", equipped), ("candidate", candidate)):
            if item.tier is None or item.level is None or not 1 <= item.level <= MAX_ITEM_LEVEL:
                return f"Could not parse valid {label} rarity/level."
            if not item.title:
                return f"Missing {label} item title."
            # Report visible-but-unparsed OCR lines before the count check;
            # e.g. an impossible 50% Crit Chance should not be silently lost.
            missing = unparsed_affix_lines(item.raw_lines, item.stats)
            if missing:
                return f"Unparsed {label} affix lines: {missing[:3]}."
            if not self.allow_partial:
                problem = validate_affixes(item.title, item.stats, rarity=item.rarity)
                if problem:
                    return f"{label}: {problem}"
        return None

    @staticmethod
    def _melee_rejection(
        equipped: ParsedItem, candidate: ParsedItem, slot: EquipmentSlot,
    ) -> Comparison:
        return Comparison(
            status=ComparisonStatus.OK,
            action=Action.SELL,
            candidate=candidate,
            equipped=equipped,
            candidate_score=None,
            equipped_score=None,
            message="Melee candidate hard-rejected after full OCR and slot validation.",
            equipment_slot=slot,
            rejection_reason="melee",
        )

    @staticmethod
    def _check(equipped: ParsedItem, candidate: ParsedItem, message: str) -> Comparison:
        return Comparison(ComparisonStatus.CHECK_OCR, Action.CHECK, candidate, equipped, None, None, message)
