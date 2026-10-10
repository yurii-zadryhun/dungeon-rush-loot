from __future__ import annotations

import json
import unittest

from src.affix_rules import has_exp_marker, unparsed_affix_lines, validate_affixes
from src.android_bridge import evaluate_spans_json, validate_equipment_json
from src.config import EXCEPTIONAL_SKILLS, MAX_STATS, MIN_STATS, RARITY_TIERS
from src.domain import Box, EquipmentSlot, OcrLine, ParsedStat
from src.equipment import EquipmentCodec, EquipmentStateError
from src.equipment_import import EquipmentScreenshotParser
from src.parsing import LootItemParser


NORMAL = (
    ("health", 5.0),
    ("damage", 6.0),
    ("critical chance", 8.0),
    ("attack speed", 15.0),
    ("lifesteal", 4.0),
)
EXCEPTIONAL = ("mega crit chance", 8.0)


def skills(*rows: tuple[str, float]) -> dict[str, float]:
    return dict(rows)


def make_slot(slot: EquipmentSlot, rarity: str, count: int, exp: bool) -> dict:
    source = [EXCEPTIONAL, *NORMAL] if exp else list(NORMAL)
    chosen = source[:count]
    title = f"{rarity.title()} {'[EXP] ' if exp else ''}{slot.value.title()}"
    data = {
        "title": title,
        "rarity": rarity.title(),
        "level": 9,
        "stats": skills(*chosen),
    }
    if slot is EquipmentSlot.WINGS:
        data["primary"] = {"attack": 1000, "health": 5000}
        data["title"] = f"{'[EXP] ' if exp else ''}Eternal"
    if slot is EquipmentSlot.CAPE:
        data["intrinsic_stats"] = {"damage": 80, "health": 80}
        data["title"] = f"{'[EXP] ' if exp else ''}Divine Cloak"
    return data


def loadout(rarity: str, count: int, exp: bool) -> dict:
    return {slot.value: make_slot(slot, rarity, count, exp) for slot in EquipmentSlot}


def ocr_line(text: str, y: int) -> OcrLine:
    return OcrLine(text, 0.98, Box(100, y, 650, y + 28))


def ocr_spans(texts: list[str]) -> str:
    return json.dumps([
        {
            "text": text,
            "score": 0.98,
            "box": {"left": 100, "top": i * 38, "right": 650, "bottom": i * 38 + 28},
        }
        for i, text in enumerate(texts)
    ])


class RarityAndExpTest(unittest.TestCase):
    def test_full_game_rarity_catalog_supported(self):
        self.assertEqual(
            list(RARITY_TIERS),
            ["common", "uncommon", "rare", "epic", "legendary",
             "mythic", "artifact", "ancient", "immortal", "divine", "ultimate"],
        )
        self.assertEqual((MIN_STATS, MAX_STATS), (2, 5))

    def test_2_to_5_affixes_across_all_rarities_and_eight_slots(self):
        for rarity in RARITY_TIERS:
            for count in range(2, 6):
                for exp in (False, True):
                    with self.subTest(rarity=rarity, count=count, exp=exp):
                        normalized = EquipmentCodec.loads_json(json.dumps(loadout(rarity, count, exp)))
                        self.assertEqual(len(normalized.items), 8)
                        for _, item in normalized:
                            self.assertEqual(item.rarity.lower(), rarity)
                            self.assertEqual(len(item.stats), count)
                            self.assertEqual(has_exp_marker(item.title), exp)
                        self.assertTrue(json.loads(validate_equipment_json(
                            json.dumps(loadout(rarity, count, exp))
                        ))["valid"])

    def test_exp_requires_exceptional_and_plain_forbids_exceptional(self):
        for rarity in RARITY_TIERS:
            for slot in EquipmentSlot:
                for exp, rows in [
                    (True, NORMAL[:2]),
                    (False, (EXCEPTIONAL, NORMAL[0])),
                ]:
                    with self.subTest(rarity=rarity, slot=slot, exp=exp):
                        item = make_slot(slot, rarity, 2, exp)
                        item["stats"] = skills(*rows)
                        payload = loadout(rarity, 2, False)
                        payload[slot.value] = item
                        validation = json.loads(validate_equipment_json(json.dumps(payload)))
                        self.assertFalse(validation["valid"])
                        self.assertIn("exceptional", validation["error"].lower())

    def test_1_or_6_affixes_rejected_even_on_lower_rarity(self):
        for count in (1, 6):
            payload = loadout("uncommon", 2, False)
            stats = skills(*NORMAL)
            if count == 1:
                stats = {"health": 5}
            else:
                stats["health regen"] = 3
            payload["ring"]["stats"] = stats
            check = json.loads(validate_equipment_json(json.dumps(payload)))
            self.assertFalse(check["valid"])
            self.assertIn("affixes", check["error"])

    def test_all_exceptional_skills_are_classified_as_exceptional(self):
        for name in EXCEPTIONAL_SKILLS:
            stats = (
                ParsedStat(name, -10.0 if name == "critical damage taken" else 5.0, "", 1.0),
                ParsedStat("health", 5.0, "", 1.0),
            )
            self.assertIsNone(validate_affixes("[EXP] Sacred Gloves", stats))
            self.assertIn("exceptional", validate_affixes("Sacred Gloves", stats).lower())

    def test_exp_marker_ocr_variants_and_false_positives(self):
        for text in ("[EXP] Helmet", "[exp] Helmet", "(EXP] •11 Helmet", "EXP] 11 Helmet"):
            self.assertTrue(has_exp_marker(text), text)
        for text in ("EXPECTED Helmet", "EXPLOSIVE", "[ex]", "Helmet", "super_exp_item"):
            self.assertFalse(has_exp_marker(text), text)

    def test_low_rarity_import_preserves_exp_flag_and_value(self):
        fixtures = [
            (
                ["Rare", "[EXP] +2 Iron Ring", "Damage 10.0K", "Lvl 9",
                 "+8.00% Mega Crit Chance", "+5.00% Health"],
                True,
            ),
            (
                ["Uncommon", "Iron Ring", "Damage 10.0K", "Lvl 9",
                 "+6.00% Damage", "+5.00% Health"],
                False,
            ),
        ]
        for lines, exp in fixtures:
            with self.subTest(exp=exp):
                result = EquipmentScreenshotParser().parse_lines(
                    [ocr_line(text, i * 35) for i, text in enumerate(lines)]
                )
                self.assertEqual(result.slot, EquipmentSlot.RING)
                self.assertEqual(result.issues, ())
                self.assertIsNotNone(result.item)
                self.assertEqual(len(result.item.stats), 2)
                self.assertEqual(has_exp_marker(result.item.title), exp)

    def test_live_popup_low_rarity_with_two_regular_affixes_is_actionable(self):
        payload = loadout("rare", 2, False)
        payload["ring"] = {
            "title": "Rare Iron Ring", "rarity": "Rare", "level": 9,
            "stats": {"health": 5.0, "damage": 6.0},
        }
        texts = [
            "Rare", "Iron Ring", "Lvl 9", "+5.00% Health", "+6.00% Damage",
            "Uncommon", "Void Ring", "Lvl 12", "+4.50% Health", "+6.10% Damage",
        ]
        result = json.loads(evaluate_spans_json(ocr_spans(texts), json.dumps(payload), "pvp"))
        self.assertEqual(result["status"], "ok", result["message"])
        self.assertEqual(result["slot"], "ring")
        self.assertEqual(result["equipped"]["rarity"], "Rare")
        self.assertEqual(result["candidate"]["rarity"], "Uncommon")

    def test_live_popup_low_rarity_exp_with_two_affixes_is_actionable(self):
        payload = loadout("rare", 2, False)
        payload["ring"] = {
            "title": "Rare [EXP] Iron Ring", "rarity": "Rare", "level": 9,
            "stats": {"mega crit chance": 8.0, "health": 5.0},
        }
        texts = [
            "Rare", "[EXP] Iron Ring", "Lvl 9",
            "+8.00% Mega Crit Chance", "+5.00% Health",
            "Uncommon", "[EXP] Void Ring", "Lvl 12",
            "+8.20% Mega Crit Chance", "+6.10% Damage",
        ]
        result = json.loads(evaluate_spans_json(ocr_spans(texts), json.dumps(payload), "pvp"))
        self.assertEqual(result["status"], "ok", result["message"])
        self.assertEqual(result["slot"], "ring")
        self.assertEqual(len(result["candidate"]["stats"]), 2)

    def test_unparsed_third_stat_cannot_disappear_at_two_stat_minimum(self):
        payload = loadout("rare", 2, False)
        payload["ring"] = {
            "title": "Rare Iron Ring", "rarity": "Rare", "level": 9,
            "stats": {"health": 5.0, "damage": 6.0},
        }
        prefixes = [
            "+1O.82% Critical Chance",  # letter O inside number
            "+70.82% Critical Chance",  # invalid cap
            "-8.20% Health",            # invalid sign
            "+10.A2% Critical Chance",  # malformed decimal
        ]
        for malformed in prefixes:
            with self.subTest(malformed=malformed):
                texts = [
                    "Rare", "Iron Ring", "Lvl 9",
                    "+5.00% Health", "+6.00% Damage",
                    "Rare", "Void Ring", "Lvl 12",
                    "+4.50% Health", "+6.10% Damage", malformed,
                ]
                event = json.loads(evaluate_spans_json(
                    ocr_spans(texts), json.dumps(payload), "pvp",
                ))
                self.assertEqual(event["status"], "check_ocr", event)
                self.assertEqual(event["action"], "check")

    def test_duplicate_stat_lines_cannot_be_deduplicated_to_valid_item(self):
        stats = [
            ocr_line("+5.00% Health", 0),
            ocr_line("+6.00% Damage", 40),
            ocr_line("+5.00% Health", 80),
        ]
        parsed = LootItemParser()._stats(stats)
        self.assertEqual(len(parsed), 3)
        self.assertIn("Duplicate", validate_affixes("Iron Ring", parsed))

    def test_import_rejects_exp_without_exceptional_and_plain_with_exceptional(self):
        for title, affixes in [
            ("[EXP] Iron Ring", ["+6.00% Damage", "+5.00% Health"]),
            ("Iron Ring", ["+8.00% Mega Crit Chance", "+5.00% Health"]),
        ]:
            with self.subTest(title=title):
                result = EquipmentScreenshotParser().parse_lines(
                    [ocr_line(x, i * 35) for i, x in enumerate([
                        "Rare", title, "Damage 10K", "Lvl 9", *affixes,
                    ])]
                )
                self.assertTrue(result.issues)
                self.assertTrue(any("exceptional" in issue.lower() for issue in result.issues))
