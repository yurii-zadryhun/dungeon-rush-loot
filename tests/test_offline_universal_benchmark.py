"""Exact seeded-drop and MILP certificates; optional SciPy in normal CI."""
from __future__ import annotations

import importlib.util
import random
import unittest


@unittest.skipUnless(importlib.util.find_spec("scipy"), "SciPy optional in normal CI")
class OfflineUniversalBenchmarkTest(unittest.TestCase):
    def test_seed_identifies_same_real_drops_as_previous_50k_report(self):
        from tools.simulate_strategy_loot import random_item
        rng = random.Random(20261011)
        found = {}
        for index in range(50_000):
            slot, item = random_item(rng)
            if index in (0, 20304, 43276, 46035, 7730, 7686):
                found[index] = (slot.value, item)
        self.assertEqual(found[0][0], "gloves")
        self.assertEqual(found[0][1].level, 127)
        self.assertEqual(found[20304][0], "weapon")
        self.assertEqual(found[20304][1].level, 109)
        self.assertEqual(
            next(s.value for s in found[20304][1].stats if s.name == "critical damage taken"),
            -46.94,
        )
        self.assertEqual(found[43276][0], "helmet")
        self.assertEqual(found[46035][0], "weapon")
        self.assertEqual(found[7730][0], "backpack")
        self.assertEqual(found[7686][0], "ring")

    def test_exact_milp_certificate_and_balanced_six_item_selection(self):
        from tools.offline_universal_benchmark import OfflinePool, totals
        from tools.simulate_strategy_loot import random_item
        rng = random.Random(20261011)
        pool = OfflinePool([random_item(rng) for _ in range(50_000)])
        self.assertEqual(len(pool.items), 1674)
        for triple_count, mega_count in ((4, 4), (3, 5)):
            with self.subTest(alloc=(triple_count, mega_count)):
                self.assertIsNone(pool.choose(
                    triples=triple_count, megas=mega_count,
                    min_triple=90, min_mega=40,
                ))
        four = pool.choose(triples=4, megas=4, min_triple=90, min_mega=37,
                           minimum_normals=(3, 2, 1))
        self.assertIsNotNone(four)
        self.assertEqual(
            [d.number for d in four],
            [46035, 43276, 7730, 9966, 20910, 7686],
        )
        self.assertGreaterEqual(totals(four)["mega crit chance"], 37)
        self.assertGreaterEqual(totals(four)["triple hit chance"], 90)
        best_mega = pool.choose(triples=4, megas=4, min_triple=90,
                                min_mega=0, objective="mega")
        self.assertAlmostEqual(totals(best_mega)["mega crit chance"], 39.79)

    def test_swap_interactions_are_nonlinear(self):
        # This is a true production score comparison with the reproducible
        # greedy items; the complete 50k online comparison runs in the workflow.
        from src.domain import EquipmentSlot, ScoringStrategy
        from src.equipment import EquipmentCodec
        from src.scoring import BuildScorer
        from src.strategies import strategy_for
        from tools.offline_universal_benchmark import OfflinePool, apply_choice
        from tools.simulate_strategy_loot import DEFAULT_EQUIPMENT, random_item
        rng = random.Random(20261011)
        drops = [random_item(rng) for _ in range(50_000)]
        alt = OfflinePool(drops).choose(
            triples=4, megas=4, min_triple=90, min_mega=37,
            minimum_normals=(3, 2, 1),
        )
        baseline = EquipmentCodec.loads_json(DEFAULT_EQUIPMENT.read_text())
        completed = apply_choice(baseline, alt)
        scorer = BuildScorer(strategy_for(ScoringStrategy.UNIVERSAL))
        self.assertEqual(set(completed.items), set(baseline.items))
        self.assertEqual(
            completed.item(EquipmentSlot.WINGS),
            baseline.item(EquipmentSlot.WINGS),
        )
        self.assertEqual(
            completed.item(EquipmentSlot.CAPE),
            baseline.item(EquipmentSlot.CAPE),
        )
        self.assertEqual(round(scorer.score(completed).total, 2), 2883.62)


if __name__ == "__main__":
    unittest.main()
