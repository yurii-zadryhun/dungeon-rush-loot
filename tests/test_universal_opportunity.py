"""Bounded optimistic Universal policy safety and true comparer/simulator parity."""
from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from src.domain import EquipmentSlot, ParsedStat, ScoringStrategy
from src.equipment import EquipmentCodec
from src.scoring import BuildScorer
from src.strategies import strategy_for
from src.universal_opportunity import UniversalOpportunityPolicy

FIXTURE = Path(__file__).parent / "fixtures" / "strategy_start_equipment.json"


class UniversalOpportunityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loadout = EquipmentCodec.loads_json(FIXTURE.read_text(encoding="utf-8"))
        cls.scorer = BuildScorer(strategy_for(ScoringStrategy.UNIVERSAL))
        cls.policy = UniversalOpportunityPolicy()

    @staticmethod
    def item_with(old, rolls):
        return replace(old, stats=tuple(
            ParsedStat(name, value, f"{value:+.2f}% {name}", 1.0)
            for name, value in rolls
        ))

    def test_weak_mega_does_not_sacrifice_existing_cdt_and_triple(self):
        slot = EquipmentSlot.GLOVES
        item = self.loadout.item(slot)
        candidate = self.item_with(item, (
            ("critical damage", 55.98), ("block chance", 3.71),
            ("companion damage", 17.53),
            ("mega crit chance", 4.10), ("thorns", 1.89),
        ))
        self.assertIsNone(self.policy.assess(
            self.loadout, slot, candidate, self.scorer, 2069.4, 1836.8
        ))
        self.assertLess(self.policy.quality(candidate)[0], self.policy.quality(item)[0])

    def test_cannot_override_genuine_improvement_or_huge_loss(self):
        slot = EquipmentSlot.HELMET
        old = self.loadout.item(slot)
        candidate = self.item_with(old, (("mega crit chance", 9.8),
                                         ("triple hit chance", 29.0)))
        self.assertIsNone(self.policy.assess(
            self.loadout, slot, candidate, self.scorer, 100.0, 120.0,
        ))
        self.assertIsNone(self.policy.assess(
            self.loadout, slot, candidate, self.scorer, 100.0, 0.0,
        ))

    def test_one_conflicting_slot_can_justify_temporary_loss(self):
        slot = EquipmentSlot.HELMET
        old = self.loadout.item(slot)
        candidate = self.item_with(old, (
            ("attack speed", 36.0), ("critical damage", 88.0),
            ("critical chance", 11.0),
            ("mega crit chance", 9.8), ("triple hit chance", 29.0),
        ))

        class FakeAggregation:
            @staticmethod
            def aggregate(loadout):
                upgraded = loadout.item(slot).stats == candidate.stats
                gloves_removed = not loadout.item(EquipmentSlot.GLOVES).stats
                return upgraded, gloves_removed

        class FakeStrategy:
            @staticmethod
            def score(metrics):
                upgraded, gloves_removed = metrics
                return SimpleNamespace(total=(150.0 if gloves_removed and upgraded
                                              else 100.0 if not upgraded else 80.0))

        scorer = SimpleNamespace(aggregator=FakeAggregation(), strategy=FakeStrategy())
        opp = self.policy.assess(
            self.loadout, slot, candidate, scorer, 100.0, 80.0,
        )
        self.assertIsNotNone(opp)
        self.assertEqual(opp.conflict_slot, EquipmentSlot.GLOVES)
        self.assertEqual(opp.immediate_delta, -20.0)
        self.assertGreater(opp.future_delta, 15.0)


if __name__ == "__main__":
    unittest.main()
