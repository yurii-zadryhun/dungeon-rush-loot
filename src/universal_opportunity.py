"""Bounded one-other-slot counterfactual for irreversible Universal decisions.

Keep strong, hard-to-replace exceptional combinations even when their present
contribution is obscured by another item. This is an optimistic one-step
planning proxy, not clairvoyance or a guarantee of finding the future drop.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .domain import EquipmentSlot, ParsedItem
from .equipment import EquipmentLoadout, beneficial_value
from .text import canonical_name

if TYPE_CHECKING:
    from .scoring import BuildScorer

REPLACEABLE = frozenset({
    EquipmentSlot.WEAPON, EquipmentSlot.HELMET,
    EquipmentSlot.BACKPACK, EquipmentSlot.GLOVES,
    EquipmentSlot.NECKLACE, EquipmentSlot.RING,
})
ROLE_TARGETS = {
    "critical damage taken": 50.0,
    "ranged defense": 95.0,
    "melee defense": 95.0,
    "triple hit chance": 25.0,
    "mega crit chance": 9.5,
}


@dataclass(frozen=True)
class Opportunity:
    conflict_slot: EquipmentSlot
    immediate_delta: float
    future_delta: float
    rare_quality_delta: float


class UniversalOpportunityPolicy:
    MAX_TEMPORARY_LOSS = 85.0
    MIN_QUALITY_GAIN = 15.0
    MIN_FUTURE_GAIN = 15.0
    MIN_STRONG_ROLL = 0.85

    @staticmethod
    def quality(item: ParsedItem) -> tuple[float, float]:
        ratios = [
            min(1.0, beneficial_value(stat.name, stat.value) / ROLE_TARGETS[canonical_name(stat.name)])
            for stat in item.stats
            if canonical_name(stat.name) in ROLE_TARGETS
        ]
        # A high-quality roll is harder to replace than a weak filler.
        return 90.0 * sum(ratio * ratio for ratio in ratios), max(ratios, default=0.0)

    def assess(
        self,
        loadout: EquipmentLoadout,
        slot: EquipmentSlot,
        candidate: ParsedItem,
        scorer: BuildScorer,
        current_total: float,
        candidate_total: float,
    ) -> Opportunity | None:
        if slot not in REPLACEABLE:
            return None
        delta = candidate_total - current_total
        if delta >= -0.01 or delta < -self.MAX_TEMPORARY_LOSS:
            return None
        old_quality, _ = self.quality(loadout.item(slot))
        new_quality, strongest = self.quality(candidate)
        gain = new_quality - old_quality
        if strongest < self.MIN_STRONG_ROLL or gain < self.MIN_QUALITY_GAIN:
            return None

        alternative = loadout.with_replacement(slot, candidate)
        best: Opportunity | None = None
        for other in sorted(REPLACEABLE - {slot}, key=lambda item: item.value):
            # Compare exactly the same hypothetical removal on both sides.
            # This identifies a blocking slot without inventing a drop.
            before = scorer.aggregator.aggregate(loadout.without_affixes(other))
            after = scorer.aggregator.aggregate(alternative.without_affixes(other))
            future_delta = scorer.strategy.score(after).total - scorer.strategy.score(before).total
            if future_delta < self.MIN_FUTURE_GAIN:
                continue
            if future_delta * 0.8 + 15.0 < -delta:
                continue
            if best is None or future_delta > best.future_delta:
                best = Opportunity(other, delta, future_delta, gain)
        return best
