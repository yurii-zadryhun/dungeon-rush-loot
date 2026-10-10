from __future__ import annotations

import json
import unittest

from src.android_bridge import app_config_json, equipment_from_imports_json
from src.domain import Box, EquipmentSlot, OcrLine
from src.equipment import EquipmentCodec
from src.equipment_import import EquipmentScreenshotParser
from src.game_catalog import match_standard_item
from src.text import fuzzy_skill_name
from src.scoring import BuildMetricsAggregator


def line(text: str, y: float) -> OcrLine:
    return OcrLine(text, 0.99, Box(0, y, 600, y + 30))


class EquipmentScreenshotParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = EquipmentScreenshotParser()

    def test_ocr_levenshtein_recovers_item_name_glyph_confusions(self):
        match = match_standard_item(["[EXP] +11 Dread Neck1ace"], primary_kind="health")
        self.assertIsNotNone(match)
        self.assertEqual(match.slot, EquipmentSlot.NECKLACE)

    def test_ocr_levenshtein_recovers_affix_glyph_confusions(self):
        name, confidence = fuzzy_skill_name("Attack 5peed")
        self.assertEqual(name, "attack speed")
        self.assertGreater(confidence, 0.9)
    def test_apk_catalog_handles_names_which_do_not_describe_the_slot(self):
        fixtures = {
            "Celestial Lyre": EquipmentSlot.BACKPACK,
            "Infernal Tome": EquipmentSlot.BACKPACK,
            "Radiant Shield": EquipmentSlot.BACKPACK,
            "Blessed Tiara": EquipmentSlot.HELMET,
            "Undying Mask": EquipmentSlot.HELMET,
            "Eternal Cape": EquipmentSlot.HELMET,
            "Celestial Lightning": EquipmentSlot.WEAPON,
        }
        for title, slot in fixtures.items():
            with self.subTest(title=title):
                match = match_standard_item([title])
                self.assertIsNotNone(match)
                self.assertEqual(match.slot, slot)

    def test_current_standard_screens_are_catalog_classified(self):
        fixtures = {
            EquipmentSlot.HELMET: [
                "Divine", "[EXP] +11 Celestial Helmet", "Health 7.25M",
                "+18.92% Lifesteal", "+1.98% Ranged Damage", "+10.82% Critical Chance",
                "+67.63% Melee Defense", "+6.54% Mega Crit Chance", "Lvl 87",
            ],
            EquipmentSlot.GLOVES: [
                "Immortal", "[EXP] +11 Crimson Gloves", "Damage 379.24K",
                "+4.50% Lifesteal", "+7.32% Ranged Damage", "+19.30% Melee Damage",
                "-51.74% Critical Damage Taken", "+24.12% Triple Hit Chance", "Lvl124",
            ],
            EquipmentSlot.BACKPACK: [
                "Immortal", "(EXP] •11 Crimson", "Backpack", "Health 1.72M",
                "+8.04% Critical Chance", "+78.01% Critical Damage", "+9.11% Attack Speed",
                "+54.09% Ranged Defense", "-39.40% Critical Damage Taken", "Lvl106",
            ],
            EquipmentSlot.NECKLACE: [
                "Immortal", "EXP] 11 Dread Necklace", "Health 521.56K",
                "+11.32% Lifesteal", "-3.66% Companion Cooldown", "+46.04% Critical Damage",
                "+24.44% Triple Hit Chance", "-44.78% Critical Damage Taken", "Lvl12",
            ],
            EquipmentSlot.RING: [
                "Immortal", "(EXP] •11 Void Ring", "Damage 164.42K",
                "+3.64% Health Regen", "-5.72% Companion Cooldown", "+8.74% Critical Chance",
                "+23.09% Triple Hit Chance", "+9.07% Mega Crit Chance", "Lvl16",
            ],
            EquipmentSlot.WEAPON: [
                "Divine", "[EXP] +11 Eternal Crossbow", "[Range]", "Damage 709.35K",
                "+87.06% Critical Damage", "+8.21% Health", "-4.98% Companion Cooldown",
                "+9.40% Mega Crit Chance", "Lvl30",
            ],
        }
        for slot, texts in fixtures.items():
            with self.subTest(slot=slot):
                result = self.parser.parse_lines([line(text, i * 35) for i, text in enumerate(texts)])
                self.assertEqual(result.slot, slot)
                self.assertIsNotNone(result.item)
                self.assertEqual(result.issues, ())

    def test_dedicated_level_crop_can_recover_digits_without_lvl_glyphs(self):
        texts = [
            "Divine", "[EXP] +11 Celestial Helmet", "Health 7.25M",
            "+18.92% Lifesteal", "+1.98% Ranged Damage", "+10.82% Critical Chance",
            "+67.63% Melee Defense", "+6.54% Mega Crit Chance",
        ]
        result = self.parser.parse_lines(
            [line(text, i * 35) for i, text in enumerate(texts)],
            [line("87", 0)],
        )
        self.assertEqual(result.slot, EquipmentSlot.HELMET)
        self.assertEqual(result.item.level, 87)
        self.assertEqual(result.issues, ())

    def test_wings_infer_level_from_apk_primary_progression_when_ocr_misses_it(self):
        texts = [
            "Divine", "Eternal", "Damage 2.25M", "Health 7.50M",
            "+13.13% Ranged Damage", "+79.10% Critical Damage", "+13.19% Damage",
            "+11.06% Critical Chance", "+30.50% Attack Speed",
        ]
        result = self.parser.parse_lines([line(text, i * 35) for i, text in enumerate(texts)])
        self.assertEqual(result.slot, EquipmentSlot.WINGS)
        self.assertEqual(result.item.level, 100)
        self.assertEqual(result.item.primary_attack, 2_250_000)
        self.assertEqual(result.item.primary_health, 7_500_000)
        self.assertEqual(len(result.item.stats), 5)
        self.assertEqual(result.issues, ())

    def test_cape_recovers_missing_fixed_damage_line_without_stealing_an_affix(self):
        # Matches the first bad Android import: ML Kit saw Health and the rolled
        # affixes but skipped the fixed +80% Damage line.
        texts = [
            "Divine Cloak", "[Mythic]", "Lvl 31", "+80.0% Health",
            "+33.25% Critical Damage", "+8.89% Critical Chance",
        ]
        result = self.parser.parse_lines([line(text, i * 35) for i, text in enumerate(texts)])
        self.assertEqual(result.slot, EquipmentSlot.CAPE)
        self.assertEqual(result.item.rarity, "Mythic")
        self.assertEqual(
            {stat.name: stat.value for stat in result.item.intrinsic_stats},
            {"damage": 80.0, "health": 80.0},
        )
        self.assertEqual(
            {stat.name for stat in result.item.stats},
            {"critical damage", "critical chance"},
        )
        self.assertEqual(result.issues, ())

    def test_cape_handles_rarity_merged_into_title_line(self):
        texts = [
            "Divine Cloak [Mythic]", "Lvl 31", "+80.0% Damage", "+80.0% Health",
            "+33.25% Critical Damage", "+8.89% Critical Chance",
        ]
        result = self.parser.parse_lines([line(text, i * 35) for i, text in enumerate(texts)])
        self.assertEqual(result.slot, EquipmentSlot.CAPE)
        self.assertEqual(result.item.rarity, "Mythic")
        self.assertEqual(result.item.title, "Divine Cloak")
        self.assertEqual(result.issues, ())

    def test_wings_handles_rarity_merged_into_title_line(self):
        texts = [
            "Divine Eternal", "Damage 2.25M", "Health 7.50M", "Lvl 100",
            "+13.13% Ranged Damage", "+79.10% Critical Damage", "+13.19% Damage",
            "+11.06% Critical Chance", "+30.50% Attack Speed",
        ]
        result = self.parser.parse_lines([line(text, i * 35) for i, text in enumerate(texts)])
        self.assertEqual(result.slot, EquipmentSlot.WINGS)
        self.assertEqual(result.item.rarity, "Divine")
        self.assertEqual(result.item.title, "Eternal")
        self.assertEqual(result.issues, ())

    def test_wings_and_cape_change_whole_build_metrics(self):
        rows = []
        for slot in EquipmentSlot:
            if slot is EquipmentSlot.WINGS:
                item = {
                    "title": "Eternal", "rarity": "Divine", "level": 100,
                    "primary": {"attack": 2250000, "health": 7500000},
                    "stats": {
                        "ranged damage": 13.13, "critical damage": 79.10, "damage": 13.19,
                        "critical chance": 11.06, "attack speed": 30.50,
                    },
                }
            elif slot is EquipmentSlot.CAPE:
                item = {
                    "title": "Divine Cloak", "rarity": "Mythic", "level": 31,
                    "intrinsic_stats": {"damage": 80, "health": 80},
                    "stats": {"critical damage": 33.25, "critical chance": 8.89},
                }
            else:
                item = {
                    "title": slot.value, "rarity": "Divine", "level": 100,
                    "stats": {"damage": 1, "health": 1, "critical chance": 1, "attack speed": 1},
                }
            rows.append({"slot": slot.value, "item": item})

        raw = equipment_from_imports_json(json.dumps(rows))
        loadout = EquipmentCodec.loads_json(raw)
        metrics = BuildMetricsAggregator().aggregate(loadout)
        self.assertGreaterEqual(metrics.base_attack, 2_250_000)
        self.assertGreaterEqual(metrics.base_health, 7_500_000)
        self.assertGreaterEqual(metrics.stats["damage"], 80)
        self.assertGreaterEqual(metrics.stats["health"], 80)

    def test_android_config_exposes_static_import_and_level_crops(self):
        config = json.loads(app_config_json())
        self.assertEqual(len(config["slots"]), 8)
        self.assertIn("wings", config["slots"])
        self.assertIn("cape", config["slots"])

        crop = config["equipment_import_crop"]
        level_crop = config["equipment_import_level_crop"]
        for rect in (crop, level_crop):
            self.assertLess(rect["top"], rect["bottom"])
            self.assertLess(rect["left"], rect["right"])
        self.assertLessEqual(crop["bottom"], 0.705)


if __name__ == "__main__":
    unittest.main()
