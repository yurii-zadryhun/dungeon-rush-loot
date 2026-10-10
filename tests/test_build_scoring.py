from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.domain import BuildMetrics, EquipmentSlot, ParsedItem, ParsedStat, ScoringStrategy
from src.equipment import EquipmentLoadout, JsonEquipmentRepository
from src.scoring import BuildMetricsAggregator, BuildScorer, ItemComparer
from src.strategies import strategy_for


def stat(name: str, value: float) -> ParsedStat:
    return ParsedStat(name, value, f"{value:+.2f}% {name}", 1.0)


def item(level: int = 100, tier: int = 9, stats=()) -> ParsedItem:
    rarity = "Divine" if tier == 9 else "Immortal"
    return ParsedItem(rarity, rarity, tier, level, tuple(stats), (), 1.0)


def loadout(overrides=None, *, default_tier: int = 9, default_level: int = 100) -> EquipmentLoadout:
    overrides = overrides or {}
    items = {
        slot: overrides.get(
            slot,
            item(level=default_level + index, tier=default_tier, stats=(stat("health", 1 + index),)),
        )
        for index, slot in enumerate(EquipmentSlot)
    }
    return EquipmentLoadout(items)


def metrics(stats=None) -> BuildMetrics:
    return BuildMetrics(
        base_attack=1.0,
        base_health=1.0,
        attack_progression=1.0,
        health_progression=1.0,
        stats=stats or {},
    )


class StrategyMechanicsTest(unittest.TestCase):
    def test_build_caps_real_probability_stats(self):
        scorer = BuildScorer(strategy_for(ScoringStrategy.UNIVERSAL), flexibility_weight=0)
        gear = loadout({
            EquipmentSlot.WEAPON: item(stats=(stat("triple hit chance", 70), stat("critical damage taken", -65))),
            EquipmentSlot.HELMET: item(stats=(stat("triple hit chance", 60), stat("critical damage taken", -55))),
        })
        score = scorer.score(gear)
        self.assertEqual(score.stat("triple hit chance").raw, 130)
        self.assertEqual(score.stat("triple hit chance").effective, 100)
        self.assertEqual(score.stat("critical damage taken").raw, 120)
        self.assertEqual(score.stat("critical damage taken").effective, 100)

    def test_double_hit_loses_marginal_value_as_triple_rises(self):
        strategy = strategy_for(ScoringStrategy.PVE)
        low_triple = strategy.score(metrics({"double hit chance": 40})).total - strategy.score(metrics()).total
        high_triple = (
            strategy.score(metrics({"triple hit chance": 90, "double hit chance": 40})).total
            - strategy.score(metrics({"triple hit chance": 90})).total
        )
        self.assertGreater(low_triple, high_triple * 5)

    def test_crit_chance_loses_marginal_value_as_mega_rises(self):
        strategy = strategy_for(ScoringStrategy.PVE)
        no_mega = (
            strategy.score(metrics({"critical chance": 20, "critical damage": 200})).total
            - strategy.score(metrics({"critical damage": 200})).total
        )
        high_mega = (
            strategy.score(metrics({"mega crit chance": 80, "critical chance": 20, "critical damage": 200})).total
            - strategy.score(metrics({"mega crit chance": 80, "critical damage": 200})).total
        )
        self.assertGreater(no_mega, high_mega * 4)

    def test_pvp_capped_enemy_cdt_nullifies_normal_crit_build(self):
        strategy = strategy_for(ScoringStrategy.PVP)
        baseline = strategy.score(metrics()).total
        crit_stack = strategy.score(metrics({"critical chance": 100, "critical damage": 500})).total
        mega = strategy.score(metrics({"mega crit chance": 50})).total
        self.assertAlmostEqual(baseline, crit_stack, places=9)
        self.assertGreater(mega, baseline)

    def test_tier_and_level_feed_real_primary_attack_and_health(self):
        aggregator = BuildMetricsAggregator()
        baseline = EquipmentLoadout({
            slot: item(level=1, tier=8, stats=(stat("health", 1 + index),))
            for index, slot in enumerate(EquipmentSlot)
        })
        baseline_metrics = aggregator.aggregate(baseline)
        self.assertAlmostEqual(baseline_metrics.attack_progression, 1.0, places=9)
        self.assertAlmostEqual(baseline_metrics.health_progression, 1.0, places=9)

        upgraded_weapon = baseline.with_replacement(
            EquipmentSlot.WEAPON,
            item(level=1, tier=9, stats=baseline.item(EquipmentSlot.WEAPON).stats),
        )
        upgraded_metrics = aggregator.aggregate(upgraded_weapon)
        self.assertGreater(upgraded_metrics.attack_progression, 1.0)
        self.assertAlmostEqual(upgraded_metrics.health_progression, 1.0, places=9)


class ReplacementFlexibilityTest(unittest.TestCase):
    def test_concentrated_cdt_can_free_another_slot_without_counting_overcap_as_power(self):
        strategy = strategy_for(ScoringStrategy.PVP)
        scorer = BuildScorer(strategy, flexibility_weight=0.12)
        protected = EquipmentSlot.RING
        gear = loadout({
            EquipmentSlot.WEAPON: item(stats=(stat("critical damage taken", -45),)),
            EquipmentSlot.HELMET: item(stats=(stat("critical damage taken", -45),)),
            protected: item(stats=(stat("critical damage taken", -10),)),
        })
        concentrated = gear.with_replacement(protected, item(stats=(stat("critical damage taken", -65),)))

        current = scorer.score(gear, protected_slot=protected)
        candidate = scorer.score(concentrated, protected_slot=protected)

        self.assertAlmostEqual(current.combat, candidate.combat, places=9)
        self.assertGreater(candidate.flexibility, current.flexibility)
        self.assertGreater(candidate.total, current.total)

    def test_other_affixes_keep_a_redundant_cdt_item_expensive_to_replace(self):
        strategy = strategy_for(ScoringStrategy.PVP)
        scorer = BuildScorer(strategy, flexibility_weight=0.12)
        protected = EquipmentSlot.RING
        plain = loadout({
            EquipmentSlot.WEAPON: item(stats=(stat("critical damage taken", -45),)),
            EquipmentSlot.HELMET: item(stats=(stat("critical damage taken", -45),)),
            protected: item(stats=(stat("critical damage taken", -65),)),
        })
        valuable = plain.with_replacement(
            EquipmentSlot.WEAPON,
            item(stats=(stat("critical damage taken", -45), stat("triple hit chance", 30), stat("attack speed", 40))),
        )
        self.assertLess(
            scorer.score(valuable, protected).flexibility,
            scorer.score(plain, protected).flexibility,
        )


class EquipmentRepositoryTest(unittest.TestCase):
    def test_successful_replacement_updates_runtime_and_json_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "equipment.json"
            payload = self._payload()
            path.write_text(json.dumps(payload), encoding="utf-8")
            repository = JsonEquipmentRepository(path)
            old = repository.snapshot().item(EquipmentSlot.RING)
            candidate = item(
                level=old.level,
                stats=(
                    stat("triple hit chance", 30),
                    stat("attack speed", 40),
                    stat("critical chance", 12),
                    stat("damage", 15),
                ),
            )
            repository.replace(EquipmentSlot.RING, candidate)

            self.assertEqual(repository.snapshot().slot_of(candidate), EquipmentSlot.RING)
            reloaded = JsonEquipmentRepository(path)
            self.assertEqual(reloaded.snapshot().slot_of(candidate), EquipmentSlot.RING)

    def test_comparer_scores_the_whole_build_not_the_item_in_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "equipment.json"
            path.write_text(json.dumps(self._payload()), encoding="utf-8")
            repository = JsonEquipmentRepository(path)
            equipped = repository.snapshot().item(EquipmentSlot.RING)
            candidate = item(
                level=equipped.level,
                stats=(
                    stat("triple hit chance", 30),
                    stat("attack speed", 40),
                    stat("critical chance", 12),
                    stat("damage", 15),
                ),
            )
            # Comparisons now require real catalog-backed titles: the UI
            # must prove that equipped and candidate belong to the same slot.
            from dataclasses import replace
            equipped = replace(equipped, title="Divine Iron Ring")
            candidate = replace(candidate, title="Divine [EXP] Void Ring")
            comparer = ItemComparer(repository, BuildScorer(strategy_for(ScoringStrategy.UNIVERSAL)))
            comparison = comparer.compare(equipped, candidate)
            self.assertEqual(comparison.equipment_slot, EquipmentSlot.RING)
            self.assertTrue(comparison.candidate_wins)

    @staticmethod
    def _payload() -> dict:
        payload = {}
        for index, slot in enumerate(EquipmentSlot):
            if slot is EquipmentSlot.WINGS:
                payload[slot.value] = {
                    "title": "Eternal",
                    "rarity": "Divine",
                    "level": 100,
                    "primary": {"attack": 2_250_000, "health": 7_500_000},
                    "stats": {
                        "ranged damage": 13.13,
                        "critical damage": 79.10,
                        "damage": 13.19,
                        "critical chance": 11.06,
                        "attack speed": 30.50,
                    },
                }
            elif slot is EquipmentSlot.CAPE:
                payload[slot.value] = {
                    "title": "Divine Cloak",
                    "rarity": "Mythic",
                    "level": 31,
                    "intrinsic_stats": {"damage": 80, "health": 80},
                    "stats": {
                        "critical damage": 33.25,
                        "critical chance": 8.89,
                    },
                }
            else:
                payload[slot.value] = {
                    "title": f"Divine {slot.value}",
                    "rarity": "Divine",
                    "level": 100 + index,
                    "stats": {
                        "health": 1 + index,
                        "damage": 2 + index,
                        "block chance": 1,
                        "health regen": 1,
                    },
                }
        return payload


if __name__ == "__main__":
    unittest.main()
