from __future__ import annotations

import json
import unittest

from src.android_bridge import app_config_json, evaluate_spans_json, replace_equipment_json, validate_equipment_json
from src.domain import EquipmentSlot


def _equipment() -> dict:
    stats = {
        "attack speed": 10,
        "critical chance": 5,
        "damage": 5,
    }
    payload = {
        slot.value: {
            "title": f"Divine {slot.value}",
            "rarity": "Divine",
            "level": 100,
            "stats": dict(stats),
        }
        for slot in EquipmentSlot
        if slot not in {EquipmentSlot.WINGS, EquipmentSlot.CAPE}
    }
    payload["wings"] = {
        "title": "Eternal",
        "rarity": "Divine",
        "level": 100,
        "primary": {"attack": 2250000, "health": 7500000},
        "stats": {
            "ranged damage": 13.13,
            "critical damage": 79.10,
            "damage": 13.19,
            "critical chance": 11.06,
            "attack speed": 30.50,
        },
    }
    payload["cape"] = {
        "title": "Divine Cloak",
        "rarity": "Mythic",
        "level": 31,
        "intrinsic_stats": {"damage": 80, "health": 80},
        "stats": {
            "critical damage": 33.25,
            "critical chance": 8.89,
        },
    }
    payload["helmet"] = {
        "title": "Divine [EXP] Celestial Helmet",
        "rarity": "Divine",
        "level": 87,
        "stats": {
            "lifesteal": 18.92,
            "ranged damage": 1.98,
            "critical chance": 10.82,
            "melee defense": 67.63,
            "mega crit chance": 6.54,
        },
    }
    return payload


def _span(text: str, top: int, bottom: int) -> dict:
    return {
        "text": text,
        "score": 0.99,
        "box": {"left": 100, "top": top, "right": 800, "bottom": bottom},
    }


class AndroidBridgeTest(unittest.TestCase):
    def test_config_exposes_shared_geometry_and_catalog(self):
        config = json.loads(app_config_json())
        self.assertEqual(config["target_package"], "com.lavalabs.dungeonrush")
        self.assertEqual(config["schema"], 4)
        self.assertEqual(config["affix_bounds"], {"min": 1, "max": 5})
        self.assertIn("sell", config["targets"])
        self.assertIn("equip", config["targets"])
        self.assertTrue(any(
            skill["name"] == "critical damage taken" and skill["exceptional"]
            for skill in config["skills"]
        ))
        self.assertTrue(any(
            skill["name"] == "attack speed" and not skill["exceptional"]
            for skill in config["skills"]
        ))

    def test_equipment_validation_and_replace_are_platform_neutral(self):
        raw = json.dumps(_equipment())
        validation = json.loads(validate_equipment_json(raw))
        self.assertTrue(validation["valid"])

        candidate = {
            "title": "Divine [EXP] New Helmet",
            "rarity": "Divine",
            "tier": 9,
            "level": 120,
            "stats": [
                {"name": "triple hit chance", "value": 25, "raw_text": "", "confidence": 1},
                {"name": "attack speed", "value": 35, "raw_text": "", "confidence": 1},
                {"name": "critical chance", "value": 10, "raw_text": "", "confidence": 1},
                {"name": "damage", "value": 14, "raw_text": "", "confidence": 1},
            ],
        }
        updated = json.loads(replace_equipment_json(raw, "helmet", json.dumps(candidate)))
        self.assertEqual(updated["helmet"]["level"], 120)
        self.assertEqual(updated["helmet"]["stats"]["triple hit chance"], 25)

    def test_real_loot_screen_with_separate_rarity_headings(self):
        # Actual in-game structure: rarity is ABOVE the [EXP] name, not on it.
        # "Infernal Cape" is a HELMET according to the Unity game catalog.
        texts = [
            "Equipped",
            "Divine",
            "[EXP] Celestial Helmet",
            "Health 3.28M",
            "Lvl 87",
            "+18.92% Lifesteal",
            "+1.98% Ranged Damage",
            "+10.82% Critical Chance",
            "+67.63% Melee Defense",
            "+6.54% Mega Crit Chance",
            "Immortal",
            "[EXP] Infernal Cape",
            "Health 531.00K",
            "Lvl 12",
            "+81.21% Critical Damage",
            "+5.02% Critical Chance",
            "+3.79% Health",
            "+4.05% Knockback",
            "Sell", "Equip",
        ]
        spans = [_span(text, index * 38, index * 38 + 30) for index, text in enumerate(texts)]
        result = json.loads(evaluate_spans_json(json.dumps(spans), json.dumps(_equipment()), "universal"))
        self.assertEqual(result["status"], "ok", result["message"])
        self.assertEqual(result["slot"], "helmet")
        self.assertEqual(result["equipped"]["rarity"], "Divine")
        self.assertEqual(result["candidate"]["rarity"], "Immortal")
        self.assertEqual(result["equipped"]["level"], 87)
        self.assertEqual(result["candidate"]["level"], 12)
        self.assertEqual(len(result["equipped"]["stats"]), 5)
        self.assertEqual(len(result["candidate"]["stats"]), 4)
        self.assertEqual(result["action"], "sell")

    def test_plain_catalog_titles_without_exp_still_work_on_desktop(self):
        # Legendary has exactly 2 ordinary rolls; neither title is [EXP].
        payload = _equipment()
        payload["helmet"] = {
            "title": "Legendary Celestial Helmet",
            "rarity": "Legendary", "level": 87,
            "stats": {"health": 8.21, "lifesteal": 11.0},
        }
        texts = [
            "Legendary", "Celestial Helmet", "Lvl 87",
            "+8.21% Health", "+11.00% Lifesteal",
            "Legendary", "Infernal Cape", "Lvl 12",
            "+4.21% Health", "+7.02% Critical Chance",
        ]
        spans = [_span(t, i * 38, i * 38 + 30) for i, t in enumerate(texts)]
        result = json.loads(evaluate_spans_json(json.dumps(spans), json.dumps(payload), "universal"))
        self.assertEqual(result["status"], "ok", result["message"])
        self.assertEqual(result["equipped"]["rarity"], "Legendary")
        self.assertEqual(result["candidate"]["rarity"], "Legendary")
        self.assertEqual(result["slot"], "helmet")

    def test_standalone_range_marker_is_not_an_item_title(self):
        from src.domain import Box, OcrLine
        from src.parsing import LootCardSplitter, LootItemParser

        texts = [
            "Divine", "[EXP] Eternal Crossbow", "[Range]",
            "Damage 709.35K", "Lvl 30",
            "+87.06% Critical Damage", "+8.21% Health",
            "-4.98% Companion Cooldown", "+9.40% Mega Crit Chance",
            "Immortal", "[EXP] Infernal Cape", "Lvl 12",
            "+81.21% Critical Damage", "+5.02% Critical Chance",
            "+3.79% Health", "+4.05% Knockback",
        ]
        lines = [
            OcrLine(text, 0.99, Box(0, i * 35, 600, i * 35 + 30))
            for i, text in enumerate(texts)
        ]
        equipped_lines, candidate_lines = LootCardSplitter().split(lines)
        equipped = LootItemParser().parse(equipped_lines)
        self.assertEqual(equipped.rarity, "Divine")
        self.assertEqual(equipped.level, 30)
        self.assertEqual(len(equipped.stats), 4)
        self.assertEqual(len(candidate_lines), 7)

    def test_standalone_melee_marker_is_respected(self):
        from src.domain import Box, OcrLine
        from src.parsing import LootItemParser

        texts = [
            "Immortal [EXP] Infernal Greatsword",
            "[Melee]", "Lvl 12", "+81.21% Critical Damage",
            "+5.02% Critical Chance", "+3.79% Health", "+4.05% Knockback",
        ]
        lines = [
            OcrLine(text, 0.99, Box(0, i * 35, 600, i * 35 + 30))
            for i, text in enumerate(texts)
        ]
        self.assertTrue(LootItemParser().parse(lines).melee)

    def test_missing_rarity_header_fails_closed(self):
        texts = [
            "[EXP] Celestial Helmet",
            "Lvl 87", "+18.92% Lifesteal", "+1.98% Ranged Damage",
            "+10.82% Critical Chance", "+67.63% Melee Defense", "+6.54% Mega Crit Chance",
            "Immortal", "[EXP] Infernal Cape", "Lvl 12",
            "+81.21% Critical Damage", "+5.02% Critical Chance",
            "+3.79% Health", "+4.05% Knockback",
        ]
        spans = [_span(t, i * 38, i * 38 + 30) for i, t in enumerate(texts)]
        result = json.loads(evaluate_spans_json(json.dumps(spans), json.dumps(_equipment()), "universal"))
        self.assertEqual(result["status"], "check_ocr")
        self.assertEqual(result["action"], "check")

    def test_real_auto_gloves_bullet_after_level_is_verified_safely(self):
        # Real 2026-10-10 application log: a single pass rendered
        # "LvI 124 •7.32 Ranged Damage". Previous parser lost that stat,
        # changing the 5-affix equipped identity and causing CHECK.
        equipment = _equipment()
        equipment["gloves"] = {
            "title": "Immortal [EXP] Crimson Gloves",
            "rarity": "Immortal", "level": 124,
            "stats": {
                "lifesteal": 4.50, "ranged damage": 7.32,
                "melee damage": 19.30, "critical damage taken": -51.74,
                "triple hit chance": 24.12,
            },
        }

        def observe(level_stat: str):
            rows = [
                "Equipped", "Immortal EXP] Crimson Gloves",
                "Damage 171.60K", "+4.50% Lifesteal",
                level_stat, "+19.30% Melee Damage",
                "-51.74% Critical Damage", "Taken",
                "+24.12% Triple Hit Chance",
                "Ancient [EXP] Winter Gloves", "Damage 33.49K",
                "Lvl 51", "+4.38% Critical Chance",
                "+8.54% Attack Speed", "+56.83% Ranged Defense",
            ]
            spans = [_span(t, i * 38, i * 38 + 30) for i, t in enumerate(rows)]
            return json.loads(evaluate_spans_json(
                json.dumps(spans), json.dumps(equipment), "pvp",
            ))

        clean = observe("LvI 124 +7.32% Ranged Damage")
        self.assertEqual(clean["status"], "ok", clean["message"])
        self.assertEqual(clean["slot"], "gloves")
        self.assertTrue(clean["verification_key"])
        for variant in ("LvI 124 •7.32 Ranged Damage", "LvI 124 ·7.32 Ranged Damage"):
            with self.subTest(variant=variant):
                noisy = observe(variant)
                self.assertEqual(noisy["status"], "ok", noisy["message"])
                self.assertEqual(noisy["verification_key"], clean["verification_key"])
                self.assertEqual(noisy["action"], clean["action"])
                self.assertIn(
                    {"name": "ranged damage", "value": 7.32},
                    [{"name": a["name"], "value": a["value"]}
                     for a in noisy["equipped"]["stats"]],
                )

        # Do not guess a leading sign in unrelated OCR rows.
        for variant in (
            "•7.32 Ranged Damage",
            "LvI 124 •70.32 Ranged Damage",  # exceeds the per-item cap
            "LvI 124 •7.A2 Ranged Damage",  # damaged numeric digits
            "LvI 124 •7.32 Critical Damage Taken",  # must be negative
        ):
            with self.subTest(rejected_variant=variant):
                noisy = observe(variant)
                self.assertEqual(noisy["status"], "check_ocr")
                self.assertEqual(noisy["action"], "check")

    def test_actual_session_gloves_hud_level_and_x4_noise(self):
        # Device JSONL 2026-10-10 19:48:32/19:48:57. The game HUD level at
        # far right is NOT the equipped item level. "Lv0124" is ML Kit for
        # "Lvl 124"; Bx4/BSX4 is an unrelated reward badge.
        equipment = _equipment()
        equipment["gloves"] = {
            "title": "Immortal [EXP] Crimson Gloves", "rarity": "Immortal",
            "level": 124,
            "stats": {
                "lifesteal": 4.50, "ranged damage": 7.32,
                "melee damage": 19.30, "critical damage taken": -51.74,
                "triple hit chance": 24.12,
            },
        }
        for level_text, badge in (
            ("LvI 124", "Bx4"),
            ("Lv0124", "BSX4"),
        ):
            with self.subTest(level_text=level_text, badge=badge):
                rows = [
                    ("Equipped", 220, 355),
                    ("Immortal EXP] Crimson Gloves", 300, 755),
                    ("Damage 171.60K", 425, 660),
                    ("+4.50% Lifesteal", 425, 640),
                    (f"{level_text} +7.32% Ranged Damage", 275, 742),
                    ("Lvl 123", 870, 934),  # background/HUD at far right
                    ("+19.30% Melee Damage", 425, 735),
                    ("-51.74% Critical Damage", 425, 752),
                    ("Taken", 425, 500),
                    ("+24.12% Triple Hit Chance", 425, 773),
                    ("Ancient EXP] Winter Gloves", 285, 739),
                    ("Damage 33.49K", 425, 652),
                    ("+4.38% Critical Chance", 425, 734),
                    (f"Lvi 51 +8.54% Attack Speed {badge}", 298, 900),
                    ("+56.83% Ranged Defense", 425, 764),
                ]
                spans = [
                    {
                        "text": text, "score": 0.86,
                        "box": {
                            "left": left, "top": i * 38,
                            "right": right, "bottom": i * 38 + 27,
                        },
                    }
                    for i, (text, left, right) in enumerate(rows)
                ]
                event = json.loads(evaluate_spans_json(
                    json.dumps(spans), json.dumps(equipment), "pvp",
                ))
                self.assertEqual(event["status"], "ok", event["message"])
                self.assertEqual(event["slot"], "gloves")
                self.assertEqual(event["equipped"]["level"], 124)
                self.assertEqual(event["candidate"]["level"], 51)
                self.assertIn(
                    {"name": "attack speed", "value": 8.54},
                    [{"name": s["name"], "value": s["value"]}
                     for s in event["candidate"]["stats"]],
                )
                self.assertTrue(event["verification_key"])

    def test_actual_session_wrapped_taken_is_not_a_title_prefix(self):
        equipment = _equipment()
        equipment["necklace"] = {
            "title": "Immortal [EXP] Dread Necklace", "rarity": "Immortal",
            "level": 12,
            "stats": {
                "lifesteal": 11.32, "companion cooldown": -3.66,
                "critical damage": 46.04, "triple hit chance": 24.44,
                "critical damage taken": -44.78,
            },
        }
        rows = [
            "quipped", "Immortal EXP] Dread Necklace", "Health 236.00K",
            "+11.32l Lifesteal", "Lv 12 -3.66% Companion Cooldown",
            "+46.04% Critical Damage", "+24.44% Triple Hit Chance",
            "-44.78% Critical Damage", "Taken",
            "Immortal [EXP] Scarlet Necklace", "Health 257.00K",
            "+65.17% Critical Damage", "LvI 19 +1.78% Ranged Damage",
            "+7.21% Critical Chance", "+7.19% Knockback",
        ]
        event = json.loads(evaluate_spans_json(
            json.dumps([_span(t, i * 38, i * 38 + 27)
                        for i, t in enumerate(rows)]),
            json.dumps(equipment), "pvp",
        ))
        self.assertEqual(event["status"], "ok", event["message"])
        self.assertEqual(event["slot"], "necklace")
        self.assertEqual(event["equipped"]["level"], 12)
        self.assertEqual(event["candidate"]["level"], 19)
        self.assertEqual(
            [s["value"] for s in event["equipped"]["stats"]
             if s["name"] == "critical damage taken"], [-44.78],
        )
        self.assertTrue(event["verification_key"])

    def test_actual_session_backpack_level_marker_lvu(self):
        equipment = _equipment()
        equipment["backpack"] = {
            "title": "Immortal [EXP] Crimson Backpack", "rarity": "Immortal",
            "level": 106,
            "stats": {
                "critical chance": 8.04, "critical damage": 78.01,
                "attack speed": 9.11, "ranged defense": 54.09,
                "critical damage taken": -39.40,
            },
        }
        rows = [
            "quipped", "Immortal [EXP] Crimson Backpack",
            "Health 777.00K", "+8.04% Critical Chance",
            "Lvl 106 +78.01% Critical Damage", "+9.11% Attack Speed",
            "+54.09% Ranged Defense", "-39.40% Critical Damage",
            "Taken", "Immortal [EXP] Infernal Tome",
            "Health 777.00K", "+3.40% Critical Chance",
            "(LvU 106) -5.26% Companion Cooldown",
            "+15.54% Lifesteal", "8.56% Ranged Defense",
        ]
        event = json.loads(evaluate_spans_json(
            json.dumps([_span(t, i * 38, i * 38 + 27)
                        for i, t in enumerate(rows)]),
            json.dumps(equipment), "pvp",
        ))
        self.assertEqual(event["status"], "ok", event["message"])
        self.assertEqual(event["slot"], "backpack")
        self.assertEqual(event["equipped"]["level"], 106)
        self.assertEqual(event["candidate"]["level"], 106)
        self.assertEqual(
            [s["value"] for s in event["equipped"]["stats"]
             if s["name"] == "critical damage taken"], [-39.40],
        )

    def test_off_card_level_filter_does_not_hide_real_in_card_conflicts(self):
        equipment = _equipment()
        equipment["gloves"] = {
            "title": "Immortal [EXP] Crimson Gloves", "rarity": "Immortal",
            "level": 124,
            "stats": {
                "lifesteal": 4.50, "ranged damage": 7.32,
                "melee damage": 19.30, "critical damage taken": -51.74,
                "triple hit chance": 24.12,
            },
        }
        rows = [
            "Immortal [EXP] Crimson Gloves",
            "Lvl 124 +4.50% Lifesteal", "Lvl 123 +7.32% Ranged Damage",
            "+19.30% Melee Damage", "-51.74% Critical Damage",
            "Taken", "+24.12% Triple Hit Chance",
            "Ancient [EXP] Winter Gloves", "Lvl 51",
            "+4.38% Critical Chance", "+8.54% Attack Speed",
            "+56.83% Ranged Defense",
        ]
        result = json.loads(evaluate_spans_json(
            json.dumps([_span(t, i * 38, i * 38 + 27)
                        for i, t in enumerate(rows)]),
            json.dumps(equipment), "pvp",
        ))
        self.assertEqual(result["status"], "check_ocr")
        self.assertEqual(result["action"], "check")

    def test_different_candidate_slot_must_not_be_tapped(self):
        texts = [
            "Divine", "[EXP] Celestial Helmet", "Lvl 87",
            "+18.92% Lifesteal", "+1.98% Ranged Damage", "+10.82% Critical Chance",
            "+67.63% Melee Defense", "+6.54% Mega Crit Chance",
            "Immortal", "[EXP] Void Ring", "Lvl 16",
            "+3.64% Health Regen", "-5.72% Companion Cooldown",
            "+8.74% Critical Chance", "+23.09% Triple Hit Chance", "+9.07% Mega Crit Chance",
        ]
        spans = [_span(t, i * 38, i * 38 + 30) for i, t in enumerate(texts)]
        result = json.loads(evaluate_spans_json(json.dumps(spans), json.dumps(_equipment()), "universal"))
        self.assertEqual(result["status"], "check_ocr")
        self.assertIn("slot", result["message"].lower())

    def test_incomplete_affixes_never_trigger_sell(self):
        texts = [
            "Divine", "[EXP] Celestial Helmet", "Lvl 87",
            "+18.92% Lifesteal", "+1.98% Ranged Damage", "+10.82% Critical Chance",
            "+67.63% Melee Defense", "+6.54% Mega Crit Chance",
            "Immortal", "[EXP] Infernal Cape", "Lvl 12",
            "+81.21% Critical Damage", "+5.02% Critical Chance", "+3.79% Health",
        ]
        spans = [_span(t, i * 38, i * 38 + 30) for i, t in enumerate(texts)]
        result = json.loads(evaluate_spans_json(json.dumps(spans), json.dumps(_equipment()), "universal"))
        self.assertEqual(result["status"], "check_ocr")
        self.assertEqual(result["action"], "check")

    def test_impossible_roll_never_triggers_sell(self):
        texts = [
            "Divine", "[EXP] Celestial Helmet", "Lvl 87",
            "+18.92% Lifesteal", "+1.98% Ranged Damage", "+10.82% Critical Chance",
            "+67.63% Melee Defense", "+6.54% Mega Crit Chance",
            "Immortal", "[EXP] Infernal Cape", "Lvl 12",
            "+81.21% Critical Damage", "+50.02% Critical Chance",
            "+3.79% Health", "+4.05% Knockback",
        ]
        spans = [_span(t, i * 38, i * 38 + 30) for i, t in enumerate(texts)]
        result = json.loads(evaluate_spans_json(json.dumps(spans), json.dumps(_equipment()), "universal"))
        self.assertEqual(result["status"], "check_ocr")
        self.assertIn("unparsed", result["message"].lower())

    def test_missing_title_fails_closed_without_percentage_gap_guess(self):
        texts = [
            "Divine", "+18.92% Lifesteal", "+1.98% Ranged Damage",
            "+10.82% Critical Chance", "+67.63% Melee Defense", "+6.54% Mega Crit Chance",
            "Immortal", "[EXP] Infernal Cape", "Lvl 12",
            "+81.21% Critical Damage", "+5.02% Critical Chance",
            "+3.79% Health", "+4.05% Knockback",
        ]
        spans = [_span(t, i * 38, i * 38 + 30) for i, t in enumerate(texts)]
        result = json.loads(evaluate_spans_json(json.dumps(spans), json.dumps(_equipment()), "universal"))
        self.assertEqual(result["status"], "check_ocr")
        self.assertEqual(result["action"], "check")

    def test_mlkit_style_spans_flow_through_shared_parser_and_scorer(self):
        spans = [
            _span("Divine [EXP] Celestial Helmet", 0, 40),
            _span("Health 3.28M", 55, 90),
            _span("+18.92% Lifesteal", 100, 135),
            _span("Lvl87 +1.98% Ranged Damage", 145, 180),
            _span("+10.82% Critical Chance", 190, 225),
            _span("+67.63% Melee Defense", 235, 270),
            _span("+6.54% Mega Crit Chance", 280, 315),
            _span("Immortal [EXP] Dread Helm", 360, 400),
            _span("Health 679.50K", 415, 450),
            _span("+12.57% Damage", 460, 495),
            _span("Lv34 +2.64% Health Regen", 505, 540),
            _span("+8.16% Health", 550, 585),
            _span("+6.60% Mega Crit Chance", 595, 630),
        ]
        event = json.loads(
            evaluate_spans_json(
                json.dumps(spans),
                json.dumps(_equipment()),
                "universal",
            )
        )
        self.assertEqual(event["status"], "ok")
        self.assertEqual(event["slot"], "helmet")
        self.assertIn(event["action"], {"sell", "equip"})
        self.assertEqual(event["equipped"]["level"], 87)
        self.assertEqual(event["candidate"]["level"], 34)
        self.assertIsNotNone(event["touch_target"])


if __name__ == "__main__":
    unittest.main()
