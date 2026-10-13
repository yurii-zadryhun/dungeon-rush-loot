"""Actual 2026-10-13 loot decisions through BOTH platform entry points.

No separate Android scorer, coefficient map or Kotlin decision rules exist:
Android hands OCR lines to src.android_bridge.evaluate_spans_json(), which
instantiates the same LootDecisionEngine/ItemComparer/BuildScorer as Desktop.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from src.android_bridge import evaluate_spans_json
from src.core import LootDecisionEngine
from src.domain import Box, OcrSpan, ScoringStrategy
from src.equipment import EquipmentCodec, InMemoryEquipmentRepository
from src.events import comparison_event, score_delta_payload
from src.scoring import BuildMetricsAggregator, BuildScorer, ItemComparer
from src.strategies import strategy_for


FIXTURE = Path(__file__).parent / "fixtures" / "field_universal_equipment_20261013.json"


def spans_from_rows(rows):
    return [
        {
            "text": text,
            "score": 0.99,
            "box": {"left": 112 if text.startswith(("Immortal", "Divine", "Lvl"))
                    else 490, "top": top, "right": 1400, "bottom": bottom},
        }
        for text, top, bottom in rows
    ]


# OCR text and vertical coordinates from the user's 2026-10-13 desktop
# decisions.jsonl, not a synthetic item generator.
GLOVES = [
    ("Immortal [EXP] Crimson Gloves", 247, 366),
    ("Damage 171.60K", 385, 494),
    ("+4.50% Lifesteal", 498, 577),
    ("Lvl 124 +7.32% Ranged Damage", 590, 687),
    ("+19.30% Melee Damage", 689, 779),
    ("-51.74% Critical Damage", 785, 877),
    ("Taken", 886, 965),
    ("+24.12% Triple Hit Chance", 983, 1066),
    ("Immortal [EXP] Tyrant Gloves", 1200, 1317),
    ("Damage 140.10K", 1340, 1437),
    ("+55.98% Critical Damage", 1446, 1537),
    ("Lvl 89 +3.71% Block Chance", 1539, 1623),
    ("+17.53% Companion Damage", 1641, 1734),
    ("+4.10% Mega Crit Chance", 1741, 1824),
    ("+1.89% Thorns", 1838, 1915),
]

HELMET = [
    ("Divine [EXP] Celestial Helmet", 440, 566),
    ("Health 3.28M", 587, 676),
    ("+18.92% Lifesteal", 695, 770),
    ("Lvl 87 +1.98% Ranged Damage", 780, 883),
    ("+10.82% Critical Chance", 888, 964),
    ("+67.63% Melee Defense", 984, 1062),
    ("+6.54% Mega Crit Chance", 1079, 1165),
    ("Immortal [EXP] Undying Mask", 1292, 1423),
    ("Health 1.17M", 1443, 1525),
    ("+16.78% Lifesteal", 1549, 1622),
    ("Lvl 107 +9.17% Double Hit Chance", 1636, 1721),
    ("+11.05% Ranged Damage", 1739, 1829),
    ("+8.26% Mega Crit Chance", 1838, 1921),
]


# Raw recognized strings and y-coordinates from the user's stuck
# 2026-10-13 11:31 Desktop session, including the actual OCR 'O'.
NECKLACE_FRACTIONAL_O = [
    ("Immortal [EXP] Dread Necklace", 345, 466),
    ("Health 236.00K", 488, 581),
    ("+11.32% Lifesteal", 596, 674),
    ("Lvl 12 -3.66% Companion Cooldown", 685, 779),
    ("+46.04% Critical Damage", 786, 877),
    ("+24.44% Triple Hit Chance", 887, 968),
    ("-44.78% Critical Damage", 980, 1070),
    ("Taken", 1079, 1161),
    ("Immortal [EXP] Undying Necklace", 1293, 1421),
    ("Health 209.00K", 1440, 1526),
    ("+5.64% Critical Chance", 1548, 1624),
    ("Lvl 3 +2.95% Health Regen", 1636, 1731),
    ("+15.O2% Double Hit Chance", 1742, 1816),
    ("+4.58% Mega Crit Chance", 1838, 1920),
]


class SharedDesktopAndroidDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_text(encoding="utf-8")
        cls.loadout = EquipmentCodec.loads_json(cls.raw)

    def decisions(self, rows):
        raw = spans_from_rows(rows)
        json_payload = json.dumps(raw)
        platform_event = json.loads(evaluate_spans_json(
            json_payload, self.raw, "universal",
        ))
        spans = [
            OcrSpan(text=d["text"], score=d["score"], box=Box(**d["box"]))
            for d in raw
        ]
        repo = InMemoryEquipmentRepository(self.loadout)
        scorer = BuildScorer(strategy_for(ScoringStrategy.UNIVERSAL))
        desktop = LootDecisionEngine(ItemComparer(repo, scorer)).decide_spans(spans)
        desktop_event = comparison_event(
            desktop.comparison, source="desktop", strategy="universal",
            ocr_lines=desktop.popup_lines,
        )
        for field in ("status", "action", "slot", "message", "equipped_score",
                      "candidate_score", "score_delta", "equipped", "candidate"):
            self.assertEqual(desktop_event[field], platform_event[field], field)
        self.assertEqual(
            score_delta_payload(desktop.comparison), platform_event["score_delta"]
        )
        return desktop_event

    def test_real_gloves_mega_gain_does_not_cover_lost_cdt_and_triple(self):
        event = self.decisions(GLOVES)
        self.assertEqual(event["status"], "ok", event["message"])
        self.assertEqual(event["action"], "sell")
        self.assertEqual(event["slot"], "gloves")
        self.assertAlmostEqual(event["equipped_score"]["total"], 2069.4001465, places=3)
        self.assertAlmostEqual(event["candidate_score"]["total"], 1836.7736745, places=3)
        parts = event["score_delta"]["components"]
        self.assertAlmostEqual(parts["target_defense"], -165, places=3)
        self.assertAlmostEqual(parts["target_triple"], -87.7347368, places=3)
        self.assertGreater(parts["target_mega"], 37)
        self.assertGreater(parts["normal_priorities"], 0)
        self.assertAlmostEqual(
            event["score_delta"]["total"], sum(parts.values()), places=7
        )

    def test_real_helmet_mega_upgrade_and_missing_melee_are_balanced(self):
        event = self.decisions(HELMET)
        self.assertEqual(event["status"], "ok", event["message"])
        self.assertEqual(event["slot"], "helmet")
        self.assertEqual(event["action"], "sell")
        self.assertGreater(event["score_delta"]["components"]["target_mega"], 15)
        self.assertAlmostEqual(
            event["score_delta"]["components"]["target_defense"], 0, places=6,
        )
        self.assertAlmostEqual(event["score_delta"]["total"], -0.08, delta=0.5)

    def test_stuck_necklace_20261013_fractional_O_is_validated_identically(self):
        event = self.decisions(NECKLACE_FRACTIONAL_O)
        self.assertEqual(event["status"], "ok", event["message"])
        self.assertEqual(event["slot"], "necklace")
        self.assertEqual(event["action"], "sell")
        candidate = event["candidate"]
        self.assertEqual(candidate["level"], 3)
        double_hit = next(stat for stat in candidate["stats"] if stat["name"] == "double hit chance")
        self.assertAlmostEqual(double_hit["value"], 15.02)
        self.assertEqual(double_hit["raw_text"], "+15.O2% Double Hit Chance")
        self.assertLessEqual(double_hit["confidence"], 0.90)

    def test_real_midgame_mega_and_triple_marginals_dwarf_companion_damage(self):
        base = BuildMetricsAggregator().aggregate(self.loadout)
        universal = strategy_for(ScoringStrategy.UNIVERSAL)
        base_score = universal.score(base).total

        def gain(name, value):
            all_stats = dict(base.stats)
            all_stats[name] = all_stats.get(name, 0.0) + value
            rolls = dict(base.equipment_rolls or {})
            rolls[name] = (*rolls.get(name, ()), value)
            updated = replace(base, stats=all_stats, equipment_rolls=rolls)
            return universal.score(updated).total - base_score

        # Marginal scoring probes, not claims of a legal complete five-affix
        # replacement. Actual legal replacements are tested above.
        companion = gain("companion damage", 17.53)
        mega = gain("mega crit chance", 4.10)
        triple = gain("triple hit chance", 12.0)
        lifesteal = gain("lifesteal", 4.50)
        self.assertGreater(mega, 30)
        self.assertGreater(triple, 30)
        self.assertGreater(mega, companion * 15)
        self.assertGreater(triple, companion * 15)
        self.assertGreater(mega, lifesteal * 10)

    def test_android_packages_same_master_python_sources(self):
        repository_root = Path(__file__).resolve().parents[1]
        packaged = repository_root / "androidApp/src/main/python/src"
        shared = repository_root / "src"
        self.assertTrue(packaged.is_symlink(), "Android Python must be linked, never copied")
        self.assertEqual(packaged.resolve(), shared.resolve())


if __name__ == "__main__":
    unittest.main()
