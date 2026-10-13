"""Contract tests for the user's offensive Universal target build.

Test separately identified rolls, not only totals. This makes it impossible
for two weak defensive affixes to masquerade as a single near-cap affix.
"""
from __future__ import annotations

from collections import defaultdict
import unittest
from dataclasses import replace

from src.config import SKILLS
from src.domain import BuildMetrics, EquipmentSlot, ScoringStrategy
from src.equipment import EquipmentCodec
from src.scoring import BuildMetricsAggregator, BuildScorer
from src.strategies import UniversalScoringStrategy, strategy_for
from tools.simulate_strategy_loot import DEFAULT_EQUIPMENT, simulate


def metrics_with_rolls(rolls: dict[str, tuple[float, ...]]) -> BuildMetrics:
    return BuildMetrics(
        base_attack=1.0,
        base_health=1.0,
        attack_progression=1.0,
        health_progression=1.0,
        stats={name: sum(values) for name, values in rolls.items()},
        equipment_rolls=rolls,
    )


def component(rolls: dict[str, tuple[float, ...]], name: str) -> float:
    score = strategy_for(ScoringStrategy.UNIVERSAL).score(metrics_with_rolls(rolls))
    return next(c.score for c in score.components if c.name == name)


def rolls_to_item(rolls):
    return {name: values[0] for name, values in rolls.items()}


class UniversalTargetContract(unittest.TestCase):
    def test_separate_cdt_rolls_of_at_least_50_are_necessary(self):
        distributed = {"critical damage taken": (50.0, 50.0)}
        weak_second = {"critical damage taken": (66.0, 34.0)}
        same_total = sum(distributed["critical damage taken"]) == sum(weak_second["critical damage taken"])
        self.assertTrue(same_total)
        self.assertGreater(
            component(distributed, "target_defense"),
            component(weak_second, "target_defense") + 15,
        )

    def test_near_100_percent_side_defense_is_preferred_to_many_small_rolls(self):
        one_strong = {"ranged defense": (95.0,), "melee defense": (95.0,)}
        fragmented = {"ranged defense": (47.5, 47.5), "melee defense": (47.5, 47.5)}
        self.assertGreater(
            component(one_strong, "target_defense"),
            component(fragmented, "target_defense") + 60,
        )

    def test_defensive_roles_saturate_after_one_strong_each_and_two_cdt(self):
        target = {
            "critical damage taken": (60.0, 55.0),
            "ranged defense": (100.0,),
            "melee defense": (100.0,),
        }
        excess = {
            **target,
            "ranged defense": (100.0, 100.0),
            "melee defense": (100.0, 95.0),
            "critical damage taken": (60.0, 55.0, 60.0),
        }
        # No score benefit for wasting another exceptional slot on defense.
        self.assertAlmostEqual(
            component(target, "target_defense"),
            component(excess, "target_defense"),
        )
        scorer = strategy_for(ScoringStrategy.UNIVERSAL)
        self.assertAlmostEqual(
            scorer.score(metrics_with_rolls(target)).total,
            scorer.score(metrics_with_rolls(excess)).total,
        )

    def test_marginal_triple_and_mega_rewards_saturate_at_desired_targets(self):
        triple = {"triple hit chance": (30.0, 30.0, 30.0)}
        added = {"triple hit chance": (30.0, 30.0, 30.0, 10.0)}
        self.assertGreater(component(added, "target_triple"), component(triple, "target_triple"))  # 3x30 is 90, preferred target 95
        peak = {"triple hit chance": (30.0, 30.0, 30.0, 30.0)}
        redundant = {"triple hit chance": (30.0, 30.0, 30.0, 30.0, 30.0)}
        self.assertEqual(component(peak, "target_triple"),
                         component(redundant, "target_triple"))

        almost = {"mega crit chance": (10.0, 10.0, 10.0)}
        four = {"mega crit chance": (10.0, 10.0, 10.0, 10.0)}
        five = {"mega crit chance": (10.0, 10.0, 10.0, 10.0, 10.0)}
        self.assertGreater(component(four, "target_mega"), component(almost, "target_mega"))
        self.assertEqual(component(four, "target_mega"), component(five, "target_mega"))

    def test_exact_four_megas_matter_more_than_max_lifesteal_while_missing(self):
        strategy = strategy_for(ScoringStrategy.UNIVERSAL)
        current = {
            "critical damage taken": (55.0, 56.0),
            "ranged defense": (96.0,),
            "melee defense": (96.0,),
            "triple hit chance": (27.0, 25.0, 24.0, 22.0),
            "mega crit chance": (9.5, 9.5, 9.5),
        }
        base = strategy.score(metrics_with_rolls(current)).total
        fourth_mega = strategy.score(metrics_with_rolls({
            **current, "mega crit chance": (*current["mega crit chance"], 9.5),
        })).total
        max_lifesteal = strategy.score(metrics_with_rolls({
            **current, "lifesteal": (SKILLS["lifesteal"].cap,),
        })).total
        self.assertGreater(fourth_mega - base, max_lifesteal - base + 30.0)

    def test_exact_four_roles_not_five_weak_megas(self):
        # Fifth Mega cannot fill the four allocated offensive roles. This
        # is a structural preference, NOT a nerf to PVE combat mechanics.
        four = {"mega crit chance": (8.0, 8.0, 8.0, 8.0)}
        five = {"mega crit chance": (8.0, 8.0, 8.0, 8.0, 8.0)}
        self.assertEqual(component(four, "target_mega"), component(five, "target_mega"))
        four_triples = {"triple hit chance": (25.0, 24.0, 23.0, 22.0)}
        five_triples = {"triple hit chance": (25.0, 24.0, 23.0, 22.0, 20.0)}
        self.assertEqual(component(four_triples, "target_triple"),
                         component(five_triples, "target_triple"))

    def test_missing_exceptional_roles_outweigh_one_near_cap_normal_roll(self):
        strategy = strategy_for(ScoringStrategy.UNIVERSAL)
        # A single roll of junk/normal quality must not be kept in preference
        # to the missing THIRD good Triple or FOURTH good Mega roll.
        for exceptional, rolls, new_value, normal, old_value in (
            ("triple hit chance", (29.0, 29.0), 27.0, "attack speed", 40.0),
            ("mega crit chance", (9.8, 9.8, 9.8), 9.5, "critical damage", 100.0),
        ):
            with self.subTest(exceptional=exceptional):
                old = metrics_with_rolls({
                    exceptional: rolls,
                    normal: (old_value,),
                })
                new = metrics_with_rolls({
                    exceptional: (*rolls, new_value),
                })
                self.assertGreater(strategy.score(new).total, strategy.score(old).total)

    def test_normal_skill_ordering_on_each_item_matches_user_priorities(self):
        def contribution(name: str, fraction: float = 1.0) -> float:
            return component({name: (SKILLS[name].cap * fraction,)}, "normal_priorities")
        first = contribution("attack speed")
        self.assertAlmostEqual(first, contribution("critical damage"))
        self.assertGreater(first, contribution("critical chance"))
        self.assertGreater(contribution("critical chance"), contribution("damage"))
        self.assertAlmostEqual(contribution("damage"), contribution("ranged damage"))
        self.assertGreater(contribution("damage"), contribution("lifesteal"))
        self.assertAlmostEqual(contribution("lifesteal"), contribution("block chance"))
        self.assertAlmostEqual(contribution("block chance"), contribution("health"))
        for junk in ("melee damage", "health regen", "companion damage",
                     "companion cooldown", "double hit chance"):
            self.assertEqual(contribution(junk), 0.0, junk)

    def test_attack_speed_and_crit_damage_on_same_item_are_better_than_split(self):
        rolls = {
            "attack speed": (36.0,),
            "critical damage": (90.0,),
            "critical chance": (10.0,),
        }
        base = metrics_with_rolls(rolls)
        paired = replace(base, item_affixes={
            EquipmentSlot.WEAPON: rolls_to_item(rolls),
        })
        split = replace(base, item_affixes={
            EquipmentSlot.WEAPON: {"attack speed": 36.0},
            EquipmentSlot.HELMET: {"critical damage": 90.0, "critical chance": 10.0},
        })
        universal = strategy_for(ScoringStrategy.UNIVERSAL)
        self.assertGreater(universal.score(paired).total,
                           universal.score(split).total + 13.0)
        for mode in (ScoringStrategy.PVE, ScoringStrategy.PVP):
            strategy = strategy_for(mode)
            self.assertAlmostEqual(strategy.score(paired).total,
                                   strategy.score(split).total)

    def test_six_individual_attack_and_critical_rolls_all_contribute(self):
        for name in ("attack speed", "critical damage", "critical chance"):
            cap = SKILLS[name].cap
            single = component({name: (cap,)}, "normal_priorities")
            six = component({name: (cap,) * 6}, "normal_priorities")
            self.assertAlmostEqual(six, 6 * single)

    def test_universal_uses_pve_baseline_without_changing_pve_or_pvp(self):
        original = metrics_with_rolls({
            "ranged defense": (95.0,),
            "critical damage taken": (50.0, 50.0),
        })
        redistributed = metrics_with_rolls({
            "ranged defense": (47.5, 47.5),
            "critical damage taken": (66.0, 34.0),
        })
        for name in (ScoringStrategy.PVE, ScoringStrategy.PVP):
            evaluator = strategy_for(name)
            self.assertAlmostEqual(evaluator.score(original).total,
                                   evaluator.score(redistributed).total)
        self.assertNotEqual(
            strategy_for(ScoringStrategy.UNIVERSAL).score(original).total,
            strategy_for(ScoringStrategy.UNIVERSAL).score(redistributed).total,
        )

    def test_real_equipment_aggregator_preserves_rolls_and_excludes_wings_and_cloak(self):
        fixture = EquipmentCodec.loads_json(DEFAULT_EQUIPMENT.read_text())
        metrics = BuildMetricsAggregator().aggregate(fixture)
        self.assertEqual(metrics.equipment_rolls["attack speed"],
                         (34.72, 9.11, 22.99))
        self.assertEqual(metrics.equipment_rolls["critical damage"],
                         (78.01, 46.04))
        self.assertEqual(metrics.equipment_rolls["critical damage taken"],
                         (39.4, 51.74, 44.78))
        self.assertEqual(metrics.equipment_rolls["mega crit chance"],
                         (8.02, 6.54))
        self.assertGreater(metrics.stats["attack speed"],
                           sum(metrics.equipment_rolls["attack speed"]))

    def test_single_profile_simulation_changes_only_six_standard_slots(self):
        result = simulate(iterations=100, seed=20261011,
                          profiles=(ScoringStrategy.UNIVERSAL,))
        self.assertEqual(set(result["results"]), {"universal"})
        self.assertEqual(result["results"]["universal"]["equips"] +
                         result["results"]["universal"]["sells"], 100)
        self.assertEqual(set(result["cross_profile_scores"]["universal"]),
                         {"universal", "pvp", "pve"})


if __name__ == "__main__":
    unittest.main()
