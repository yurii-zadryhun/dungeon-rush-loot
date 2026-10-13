from __future__ import annotations

import random
import unittest
from collections import Counter

from src.affix_rules import affix_requirement, validate_affixes
from src.config import EXCEPTIONAL_SKILLS, SKILLS
from src.domain import Action, ScoringStrategy
from src.equipment import EquipmentCodec, InMemoryEquipmentRepository
from src.scoring import BuildScorer, ItemComparer
from src.strategies import strategy_for
from tools.simulate_strategy_loot import (
    DEFAULT_EQUIPMENT, PROFILES, STANDARD_SLOTS, random_item, run_strategy, simulate,
)


class RandomExpDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = EquipmentCodec.loads_json(DEFAULT_EQUIPMENT.read_text(encoding="utf-8"))

    def test_actual_starting_eight_slots_have_expected_exp_and_fixed_special_equipment(self):
        self.assertEqual(len(self.initial.items), 8)
        self.assertEqual(self.initial.item(STANDARD_SLOTS[0]).level, 94)
        self.assertEqual(self.initial.items[next(k for k in self.initial.items if k.value == "helmet")].level, 87)
        for slot, item in self.initial:
            self.assertIsNone(validate_affixes(item.title, item.stats, rarity=item.rarity, slot=slot),
                              (slot, item))
        self.assertEqual(self.initial.items[next(k for k in self.initial.items if k.value == "wings")].level, 100)
        self.assertEqual(self.initial.items[next(k for k in self.initial.items if k.value == "cape")].level, 31)

    def test_many_generated_items_follow_verified_affix_constraints(self):
        rng = random.Random(377)
        seen = Counter()
        for _ in range(2000):
            slot, item = random_item(rng)
            seen[slot] += 1
            self.assertIn(item.rarity, ("Immortal", "Divine"))
            self.assertIn("[EXP]", item.title)
            self.assertTrue(1 <= item.level <= 130)
            rule = affix_requirement(item.rarity, item.title, slot=slot)
            normals = sum(s.name not in EXCEPTIONAL_SKILLS for s in item.stats)
            exceptional = len(item.stats) - normals
            self.assertEqual(normals, 3)
            self.assertEqual(normals, rule.normal)
            self.assertIn(exceptional, (1, 2))
            self.assertEqual(len({s.name for s in item.stats}), len(item.stats))
            for stat in item.stats:
                self.assertGreaterEqual(abs(stat.value), .01)
                self.assertLessEqual(abs(stat.value), SKILLS[stat.name].cap)
                if stat.name in ("critical damage taken", "companion cooldown"):
                    self.assertLess(stat.value, 0)
                else:
                    self.assertGreater(stat.value, 0)
            self.assertIsNone(validate_affixes(item.title, item.stats, rarity=item.rarity, slot=slot))
        self.assertEqual(set(seen), set(STANDARD_SLOTS))

    def test_seeded_random_item_stream_is_repeatable(self):
        a, b = random.Random(123), random.Random(123)
        self.assertEqual([random_item(a) for _ in range(100)],
                         [random_item(b) for _ in range(100)])
        c = random.Random(124)
        self.assertNotEqual(random_item(a), random_item(c))

    def test_cached_hot_path_matches_production_item_comparer(self):
        # Important: Monte Carlo uses a cached current score for speed, but
        # MUST select the same sequence of items as the real ItemComparer.
        drops = tuple(random_item(random.Random(i)) for i in range(180))
        for profile in PROFILES:
            with self.subTest(strategy=profile.value):
                expected = InMemoryEquipmentRepository(self.initial)
                comparer = ItemComparer(expected, BuildScorer(strategy_for(profile)))
                accepted = Counter()
                for slot, candidate in drops:
                    equipped = expected.snapshot().item(slot)
                    comparison = comparer.compare(equipped, candidate)
                    self.assertIn(comparison.action, (Action.EQUIP, Action.SELL), comparison.message)
                    if comparison.action is Action.EQUIP:
                        expected.replace(slot, candidate)
                        accepted[slot.value] += 1
                fast = run_strategy(drops, self.initial, profile, len(drops))
                self.assertEqual(fast.equipped, sum(accepted.values()))
                self.assertEqual(fast.by_slot, {
                    slot.value: accepted[slot.value] for slot in STANDARD_SLOTS
                })
                self.assertEqual(EquipmentCodec.to_payload(fast.final),
                                 EquipmentCodec.to_payload(expected.snapshot()))

    def test_small_end_to_end_seed_is_reproducible_across_all_three_strategies(self):
        first = simulate(iterations=75, seed=567)
        second = simulate(iterations=75, seed=567)
        self.assertEqual(first, second)
        self.assertEqual(set(first["results"]), {p.value for p in PROFILES})
        for name, result in first["results"].items():
            self.assertEqual(result["equips"] + result["sells"], 75)
            self.assertEqual(set(result["final_equipment"]),
                             {slot.value for slot, _ in self.initial})
            self.assertEqual(result["final_equipment"]["wings"],
                             EquipmentCodec.to_payload(self.initial)["wings"])
            self.assertEqual(result["final_equipment"]["cape"],
                             EquipmentCodec.to_payload(self.initial)["cape"])
            self.assertEqual(set(first["cross_profile_scores"][name]),
                             {profile.value for profile in PROFILES})

    def test_bad_iteration_count_is_rejected(self):
        with self.assertRaises(ValueError):
            simulate(iterations=0)


if __name__ == "__main__":
    unittest.main()
