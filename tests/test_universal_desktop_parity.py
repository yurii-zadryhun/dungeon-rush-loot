"""Desktop Universal regression contracts shared with Android's strategy.

The six desktop slots intentionally keep their current equipment.json schema.
Do not replace the old desktop stack with the Android capture/automation code.
"""
from __future__ import annotations

import unittest

from src.config import SKILLS
from src.domain import BuildMetrics, EquipmentSlot, ParsedItem, ParsedStat, ScoringStrategy
from src.equipment import EquipmentLoadout
from src.scoring import BuildMetricsAggregator, BuildScorer
from src.strategies import UniversalScoringStrategy, strategy_for


def stats(*pairs: tuple[str, float]) -> tuple[ParsedStat, ...]:
    return tuple(ParsedStat(name, value, "", 1.0) for name, value in pairs)


def metrics(rolls: dict[str, tuple[float, ...]]) -> BuildMetrics:
    return BuildMetrics(
        base_attack=1.0,
        base_health=1.0,
        attack_progression=1.0,
        health_progression=1.0,
        stats={name: sum(values) for name, values in rolls.items()},
        equipment_rolls=rolls,
    )


def component(rolls: dict[str, tuple[float, ...]], part: str) -> float:
    score = strategy_for(ScoringStrategy.UNIVERSAL).score(metrics(rolls))
    return next(c.score for c in score.components if c.name == part)


class UniversalDesktopParityTests(unittest.TestCase):
    def test_universal_is_pve_plus_explicit_roles_not_pve_pvp_average(self):
        profile = strategy_for(ScoringStrategy.UNIVERSAL)
        self.assertIsInstance(profile, UniversalScoringStrategy)
        self.assertEqual(profile.TRIPLE_ROLLS, 4)
        self.assertEqual(profile.MEGA_ROLLS, 4)
        target = metrics({
            "critical damage taken": (56.0, 54.0),
            "ranged defense": (98.0,),
            "melee defense": (97.0,),
            "triple hit chance": (28.0, 25.0, 24.0, 21.0),
            "mega crit chance": (9.8, 9.5, 9.4, 9.2),
        })
        score = profile.score(target)
        self.assertEqual(
            {c.name for c in score.components},
            {"pve", "target_defense", "target_triple", "target_mega", "normal_priorities"},
        )
        self.assertNotAlmostEqual(score.total, strategy_for(ScoringStrategy.PVE).score(target).total)

    def test_fourth_good_mega_significantly_beats_max_lifesteal(self):
        profile = strategy_for(ScoringStrategy.UNIVERSAL)
        base = {
            "critical damage taken": (55.0, 56.0),
            "ranged defense": (96.0,),
            "melee defense": (96.0,),
            "triple hit chance": (27.0, 25.0, 24.0, 22.0),
            "mega crit chance": (9.5, 9.5, 9.5),
        }
        with_mega = profile.score(metrics({
            **base, "mega crit chance": (*base["mega crit chance"], 9.5)
        })).total
        with_lifesteal = profile.score(metrics({
            **base, "lifesteal": (SKILLS["lifesteal"].cap,),
        })).total
        self.assertGreater(with_mega, with_lifesteal + 30.0)

    def test_cannot_satisfy_four_role_target_with_five_weak_megas(self):
        four = {"mega crit chance": (8.0, 8.0, 8.0, 8.0)}
        five = {"mega crit chance": (8.0, 8.0, 8.0, 8.0, 8.0)}
        self.assertEqual(component(four, "target_mega"), component(five, "target_mega"))
        self.assertEqual(
            component({"triple hit chance": (25.0, 24.0, 23.0, 22.0)}, "target_triple"),
            component({"triple hit chance": (25.0, 24.0, 23.0, 22.0, 20.0)}, "target_triple"),
        )

    def test_two_strong_cdt_and_one_strong_side_defense_win(self):
        self.assertGreater(
            component({"critical damage taken": (50.0, 50.0)}, "target_defense"),
            component({"critical damage taken": (66.0, 34.0)}, "target_defense") + 15,
        )
        self.assertGreater(
            component({"ranged defense": (95.0,), "melee defense": (95.0,)}, "target_defense"),
            component({"ranged defense": (47.5, 47.5), "melee defense": (47.5, 47.5)}, "target_defense") + 60,
        )

    def test_normal_priorities_and_same_item_pairing(self):
        def priority(name: str) -> float:
            return component({name: (SKILLS[name].cap,)}, "normal_priorities")
        self.assertAlmostEqual(priority("attack speed"), priority("critical damage"))
        self.assertGreater(priority("critical damage"), priority("critical chance"))
        self.assertGreater(priority("critical chance"), priority("ranged damage"))
        self.assertGreater(priority("ranged damage"), priority("lifesteal"))
        self.assertEqual(priority("companion damage"), 0.0)

        profile = strategy_for(ScoringStrategy.UNIVERSAL)
        rolls = {"attack speed": (36.0,), "critical damage": (90.0,)}
        paired = metrics(rolls)
        from dataclasses import replace
        on_one_item = replace(paired, item_affixes={
            EquipmentSlot.GLOVES: {"attack speed": 36.0, "critical damage": 90.0},
        })
        on_two_items = replace(paired, item_affixes={
            EquipmentSlot.GLOVES: {"attack speed": 36.0},
            EquipmentSlot.RING: {"critical damage": 90.0},
        })
        self.assertGreater(profile.score(on_one_item).total, profile.score(on_two_items).total + 9)

    def test_desktop_aggregator_provides_item_specific_rolls(self):
        items = {
            slot: ParsedItem("Divine Ring", "Divine", 9, 90, stats(
                ("health", 4.0), ("attack speed", 35.0), ("critical damage", 80.0),
                ("mega crit chance", 9.0),
            ), (), 1.0)
            for slot in EquipmentSlot
        }
        loadout = EquipmentLoadout(items)
        aggregated = BuildMetricsAggregator().aggregate(loadout)
        self.assertEqual(len(aggregated.equipment_rolls["mega crit chance"]), 6)
        self.assertEqual(len(aggregated.item_affixes), 6)
        # Equipment rolls track six replaceable slots; raw build totals
        # include all eight pieces, including the two fixed special slots.
        self.assertEqual(aggregated.stats["mega crit chance"], 72.0)
        self.assertAlmostEqual(
            BuildScorer(strategy_for(ScoringStrategy.PVE)).score(loadout).combat,
            strategy_for(ScoringStrategy.PVE).score(aggregated).total,
        )

    def test_pve_and_pvp_math_untouched(self):
        sample = metrics({
            "critical damage": (80.0,),
            "critical chance": (10.0,),
            "mega crit chance": (9.5,),
            "lifesteal": (15.0,),
        })
        self.assertLess(
            strategy_for(ScoringStrategy.PVP).score(sample).total,
            strategy_for(ScoringStrategy.PVE).score(sample).total,
        )


if __name__ == "__main__":
    unittest.main()
