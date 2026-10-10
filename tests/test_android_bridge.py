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
        "health": 5,
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
        self.assertIn("sell", config["targets"])
        self.assertIn("equip", config["targets"])
        self.assertTrue(any(skill["name"] == "critical damage taken" for skill in config["skills"]))

    def test_equipment_validation_and_replace_are_platform_neutral(self):
        raw = json.dumps(_equipment())
        validation = json.loads(validate_equipment_json(raw))
        self.assertTrue(validation["valid"])

        candidate = {
            "title": "Divine New Helmet",
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
