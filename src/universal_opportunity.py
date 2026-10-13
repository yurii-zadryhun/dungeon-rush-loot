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


    @staticmethod
    def _valuable_rolls(loadout: EquipmentLoadout, name: str, count: int) -> tuple[float, ...]:
        values = sorted((
            beneficial_value(name, stat.value)
            for slot, item in loadout
            if slot in REPLACEABLE
            for stat in item.stats
            if canonical_name(stat.name) == name
        ), reverse=True)
        return tuple(values[:count])

    def _protect_obtained_roles(
        self, current: EquipmentLoadout, prospective: EquipmentLoadout,
    ) -> bool:
        # Counterfactuals can be optimistic, but an explicitly hard-to-replace
        # offensive roll already in hand must not be thrown out just to
        # chase another role. Future upgrades may be uncertain/rare.
        for name in ("mega crit chance", "triple hit chance"):
            old = self._valuable_rolls(current, name, 4)
            new = self._valuable_rolls(prospective, name, 4)
            if len(new) < len(old):
                return False
            if sum(new) + 0.25 < sum(old):
                return False
        # Preserve achieved two-CDT and single near-cap side defenses. When
        # a role is still incomplete, the policy may reorganize those rolls.
        for name, count, threshold in (
            ("critical damage taken", 2, 50.0),
            ("ranged defense", 1, 90.0),
            ("melee defense", 1, 90.0),
        ):
            old = self._valuable_rolls(current, name, count)
            new = self._valuable_rolls(prospective, name, count)
            if len(old) == count and min(old) >= threshold:
                if len(new) < count or min(new) < threshold:
                    return False
        return True

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
        if not self._protect_obtained_roles(loadout, alternative):
            return None
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
