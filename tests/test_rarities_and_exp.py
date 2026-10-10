from __future__ import annotations

import json
import unittest

from src.affix_rules import (
    affix_requirement, has_exp_marker, validate_affixes, unparsed_affix_lines,
)
from src.android_bridge import app_config_json, evaluate_spans_json, validate_equipment_json
from src.config import (
    EXCEPTIONAL_SKILLS, MAX_EXCEPTIONAL_AFFIXES, MAX_STATS,
    MIN_EXCEPTIONAL_AFFIXES, MIN_STATS, RARITY_NORMAL_AFFIX_COUNT,
    RARITY_TIERS,
)
from src.domain import Box, EquipmentSlot, OcrLine, ParsedStat
from src.equipment import EquipmentCodec
from src.equipment_import import EquipmentScreenshotParser
from src.parsing import LootItemParser

NORMAL = (
    ("health", 5.0),
    ("damage", 6.0),
    ("critical chance", 8.0),
    ("attack speed", 15.0),
    ("lifesteal", 4.0),
)
EXCEPTIONAL = (
    ("mega crit chance", 8.0),
    ("triple hit chance", 22.0),
)


def make_item(slot: EquipmentSlot, rarity: str, exp_count: int = 0) -> dict:
    normal = RARITY_NORMAL_AFFIX_COUNT[rarity]
    if slot is EquipmentSlot.WINGS and rarity == "divine" and exp_count == 0:
        normal = 5  # Observed Divine Eternal Wings have five normal affixes.
    data = {
        "title": f"{rarity.title()} {'[EXP] ' if exp_count else ''}{slot.value.title()}",
        "rarity": rarity.title(),
        "level": 9,
        "stats": dict((*NORMAL[:normal], *EXCEPTIONAL[:exp_count])),
    }
    if slot is EquipmentSlot.WINGS:
        data["title"] = f"{'[EXP] ' if exp_count else ''}Eternal"
        data["primary"] = {"attack": 1000, "health": 5000}
    elif slot is EquipmentSlot.CAPE:
        data["title"] = f"{'[EXP] ' if exp_count else ''}Divine Cloak"
        data["intrinsic_stats"] = {"damage": 80, "health": 80}
    elif slot is EquipmentSlot.RING:
        data["title"] = f"{rarity.title()} {'[EXP] ' if exp_count else ''}Iron Ring"
    return data


def loadout(rarity: str, exp_count: int = 0) -> dict:
    return {slot.value: make_item(slot, rarity, exp_count) for slot in EquipmentSlot}


def ocr_line(text: str, y: int) -> OcrLine:
    return OcrLine(text, 0.98, Box(100, y, 650, y + 28))


def spans(texts: list[str]) -> str:
    return json.dumps([
        {
            "text": text,
            "score": 0.98,
            "box": {"left": 100, "top": i * 38, "right": 650, "bottom": i * 38 + 28},
        } for i, text in enumerate(texts)
    ])


def popup(rarity: str, current_exp: int = 0, dropped_exp: int = 0) -> tuple[dict, list[str]]:
    gear = loadout(rarity, current_exp)
    gear["ring"] = make_item(EquipmentSlot.RING, rarity, current_exp)
    other = make_item(EquipmentSlot.RING, rarity, dropped_exp)
    other["title"] = f"{rarity.title()} {'[EXP] ' if dropped_exp else ''}Void Ring"
    other["level"] = 12

    def lines(item: dict) -> list[str]:
        return [
            item["rarity"],
            item["title"].replace(item["rarity"], "", 1).strip(),
            f"Lvl {item['level']}",
            *(f"{value:+.2f}% {name.title()}" for name, value in item["stats"].items()),
        ]

    return gear, lines(gear["ring"]) + lines(other)


class ExactRarityAffixRulesTest(unittest.TestCase):
    def test_expected_rarity_table_and_global_bounds(self):
        self.assertEqual((MIN_STATS, MAX_STATS), (1, 5))
        self.assertEqual((MIN_EXCEPTIONAL_AFFIXES, MAX_EXCEPTIONAL_AFFIXES), (1, 2))
        self.assertEqual(
            RARITY_NORMAL_AFFIX_COUNT,
            {
                "common": 1, "uncommon": 1, "rare": 1, "epic": 1,
                "legendary": 2, "mythic": 2, "artifact": 2, "ancient": 2,
                "immortal": 3, "divine": 3,
            },
        )
        self.assertIn("ultimate", RARITY_TIERS)
        self.assertNotIn("ultimate", RARITY_NORMAL_AFFIX_COUNT)

    def test_valid_complete_items_all_rarities_slots_and_exp_levels(self):
        for rarity, ordinary in RARITY_NORMAL_AFFIX_COUNT.items():
            for exp_count in (0, 1, 2):
                for slot in EquipmentSlot:
                    with self.subTest(rarity=rarity, exp=exp_count, slot=slot.value):
                        item = make_item(slot, rarity, exp_count)
                        requirement = affix_requirement(
                            rarity, item["title"], slot=slot,
                        )
                        self.assertEqual(len(item["stats"]), requirement.normal + exp_count)
                        self.assertEqual(requirement.exceptional_min <= exp_count <=
                                         requirement.exceptional_max, True)
                        state = loadout(rarity, exp_count)
                        parsed = EquipmentCodec.loads_json(json.dumps(state))
                        self.assertEqual(len(parsed.items), 8)
                        self.assertTrue(json.loads(validate_equipment_json(json.dumps(state)))["valid"])

    def test_every_off_by_one_normal_count_fails_for_all_rarities(self):
        for rarity, count in RARITY_NORMAL_AFFIX_COUNT.items():
            for exp in (0, 1, 2):
                for delta in (-1, 1):
                    with self.subTest(rarity=rarity, exp=exp, delta=delta):
                        item = make_item(EquipmentSlot.RING, rarity, exp)
                        actual = count + delta
                        if actual < 0:
                            continue
                        item["stats"] = dict((*NORMAL[:actual], *EXCEPTIONAL[:exp]))
                        check = validate_equipment_json(json.dumps({
                            **loadout(rarity, exp), "ring": item,
                        }))
                        result = json.loads(check)
                        self.assertFalse(result["valid"])
                        if not 1 <= actual + exp <= 5:
                            self.assertIn("between 1 and 5", result["error"])
                        else:
                            self.assertIn("normal affixes", result["error"])

    def test_exceptional_count_zero_one_two_three_and_marker(self):
        for rarity, normal_count in RARITY_NORMAL_AFFIX_COUNT.items():
            ordinary = NORMAL[:normal_count]
            for marked in (False, True):
                for exceptional_count in range(4):
                    names = ("mega crit chance", "triple hit chance", "melee defense")
                    exceptional = tuple((n, 5.0) for n in names[:exceptional_count])
                    stats = tuple(ParsedStat(n, v, "", 1.0) for n, v in (*ordinary, *exceptional))
                    title = f"{rarity.title()} {'[EXP] ' if marked else ''}Iron Ring"
                    result = validate_affixes(title, stats, rarity=rarity)
                    expected_ok = (1 <= exceptional_count <= 2) if marked else exceptional_count == 0
                    with self.subTest(rarity=rarity, marked=marked, exceptional=exceptional_count):
                        self.assertEqual(result is None, expected_ok, result)

    def test_all_exceptional_skills_are_classified_correctly(self):
        for exceptional_name in EXCEPTIONAL_SKILLS:
            stat = ParsedStat(
                exceptional_name,
                -10.0 if exceptional_name == "critical damage taken" else 5.0,
                "",
                1.0,
            )
            normal = ParsedStat("health", 5.0, "", 1.0)
            self.assertIsNone(validate_affixes(
                "Common [EXP] Iron Ring", (normal, stat), rarity="common",
            ))
            self.assertIn("exceptional", validate_affixes(
                "Common Iron Ring", (normal, stat), rarity="common",
            ))

    def test_ultimate_fails_closed_until_rule_is_confirmed(self):
        for exp in (0, 1, 2):
            raw = loadout("divine", exp)
            raw["ring"]["rarity"] = "Ultimate"
            raw["ring"]["title"] = f"Ultimate {'[EXP] ' if exp else ''}Iron Ring"
            result = json.loads(validate_equipment_json(json.dumps(raw)))
            self.assertFalse(result["valid"])
            self.assertIn("No verified affix-count rule", result["error"])

    def test_previous_real_divine_wings_with_five_normal_affixes_still_pass(self):
        item = make_item(EquipmentSlot.WINGS, "divine", 0)
        self.assertEqual(len(item["stats"]), 5)
        parsed = EquipmentCodec.parse_item(EquipmentSlot.WINGS, item)
        self.assertEqual(len(parsed.stats), 5)

        item["stats"].pop("lifesteal")
        with self.assertRaisesRegex(Exception, "normal affixes"):
            EquipmentCodec.parse_item(EquipmentSlot.WINGS, item)

    def test_exp_marker_recognition_with_real_ocr_variations(self):
        for title in (
            "[EXP] Helmet", "[exp] Helmet", "(EXP] •11 Helmet", "EXP] 11 Helmet",
            "Immortal EXP Infernal Tome", "Immortal [EXP Infernal Tome",
            "Immortal EXP] Infernal Tome", "Immortal (EXP Infernal Tome",
            "Immortal [EXP] Infernal Tome",
        ):
            self.assertTrue(has_exp_marker(title), title)
        for title in (
            "EXPECTED Helmet", "EXPLOSIVE", "[ex]", "Helmet", "super_exp_item",
            "Immortal Infernal Tome", "Immortal EXPI Infernal Tome",
            "Immortal EXPN Infernal Tome",
        ):
            self.assertFalse(has_exp_marker(title), title)

    def test_infernal_tome_exp_marker_survives_broken_brackets(self):
        # Live 20:50 session: candidate has a highlighted exceptional Ranged
        # Defense, and the visible item title contains [EXP]. OCR sometimes
        # loses a bracket in the fresh pass, which previously caused
        # "requires 0-0 exceptional affixes; parsed 1".
        stats = tuple(
            ParsedStat(name, value, "", 0.84)
            for name, value in (
                ("critical chance", 3.40),
                ("companion cooldown", -5.26),
                ("lifesteal", 15.54),
                ("ranged defense", 78.56),
            )
        )
        for title in (
            "Immortal [EXP] Infernal Tome",
            "Immortal EXP] Infernal Tome",
            "Immortal [EXP Infernal Tome",
            "Immortal EXP Infernal Tome",
        ):
            with self.subTest(title=title):
                self.assertIsNone(validate_affixes(title, stats, rarity="immortal"))
        self.assertIn(
            "0-0 exceptional",
            validate_affixes("Immortal Infernal Tome", stats, rarity="immortal"),
        )

    def test_low_rarity_one_affix_import_and_exp_with_two_or_three(self):
        fixtures = [
            (["Common", "Iron Ring", "Damage 10K", "Lvl 9", "+5.00% Health"], 1, False),
            (["Rare", "[EXP] +2 Iron Ring", "Damage 10K", "Lvl 9",
              "+5.00% Health", "+8.00% Mega Crit Chance"], 2, True),
            (["Epic", "[EXP] Iron Ring", "Damage 10K", "Lvl 9",
              "+5.00% Health", "+8.00% Mega Crit Chance", "+20.00% Triple Hit Chance"], 3, True),
            (["Legendary", "Iron Ring", "Damage 10K", "Lvl 9",
              "+5.00% Health", "+6.00% Damage"], 2, False),
        ]
        for words, expected_count, exp in fixtures:
            with self.subTest(rarity=words[0], count=expected_count, exp=exp):
                parsed = EquipmentScreenshotParser().parse_lines(
                    [ocr_line(text, index * 35) for index, text in enumerate(words)]
                )
                self.assertEqual(parsed.slot, EquipmentSlot.RING)
                self.assertEqual(parsed.issues, ())
                self.assertEqual(len(parsed.item.stats), expected_count)
                self.assertEqual(has_exp_marker(parsed.item.title), exp)

    def test_rarity_count_detects_missing_affix_even_when_remaining_rows_valid(self):
        for rarity in RARITY_NORMAL_AFFIX_COUNT:
            for exp_count in (0, 1, 2):
                item = make_item(EquipmentSlot.RING, rarity, exp_count)
                raw = list(item["stats"].items())
                for missing_index in range(len(raw)):
                    with self.subTest(rarity=rarity, exp=exp_count, dropped=missing_index):
                        truncated = tuple(
                            ParsedStat(n, v, "", 1.0)
                            for index, (n, v) in enumerate(raw) if index != missing_index
                        )
                        result = validate_affixes(
                            item["title"], truncated, rarity=rarity,
                            slot=EquipmentSlot.RING,
                        )
                        removed_is_exceptional = raw[missing_index][0] in EXCEPTIONAL_SKILLS
                        if exp_count == 2 and removed_is_exceptional:
                            # Without a visible unreadable line, losing one of
                            # two exceptional rolls looks identical to a valid
                            # one-exceptional [EXP] item. OCR alone cannot
                            # distinguish these; don't claim otherwise.
                            self.assertIsNone(result)
                        else:
                            self.assertIsNotNone(result)

    def test_live_auto_one_affix_common_and_three_plus_two_divine(self):
        for rarity, first, second in (
            ("common", 0, 0), ("rare", 0, 2),
            ("legendary", 1, 2), ("immortal", 2, 0),
            ("divine", 2, 2),
        ):
            with self.subTest(rarity=rarity, exp=(first, second)):
                gear, lines = popup(rarity, first, second)
                result = json.loads(evaluate_spans_json(
                    spans(lines), json.dumps(gear), "pvp",
                ))
                self.assertEqual(result["status"], "ok", result["message"])
                self.assertEqual(result["slot"], "ring")
                self.assertEqual(len(result["equipped"]["stats"]),
                                 RARITY_NORMAL_AFFIX_COUNT[rarity] + first)
                self.assertEqual(len(result["candidate"]["stats"]),
                                 RARITY_NORMAL_AFFIX_COUNT[rarity] + second)

    def test_live_auto_dropped_last_line_produces_check_not_sell(self):
        for rarity, first, second in (
            ("common", 0, 0), ("legendary", 1, 1),
            ("immortal", 1, 1), ("divine", 0, 1),
        ):
            gear, lines = popup(rarity, first, second)
            full = json.loads(evaluate_spans_json(spans(lines), json.dumps(gear), "pvp"))
            self.assertEqual(full["status"], "ok", full)
            broken = lines[:-1]
            result = json.loads(evaluate_spans_json(spans(broken), json.dumps(gear), "pvp"))
            self.assertEqual(result["status"], "check_ocr")
            self.assertEqual(result["action"], "check")

    def test_missing_one_of_two_exceptional_rolls_requires_visible_evidence(self):
        # There are TWO permitted EXP sizes; if the entire last OCR row
        # vanishes, rarity+EXP alone does not tell us which size it had.
        gear, texts = popup("divine", 1, 2)
        complete = json.loads(evaluate_spans_json(spans(texts), json.dumps(gear), "pvp"))
        self.assertEqual(complete["status"], "ok", complete)
        missing = texts[:-1]
        ambiguous = json.loads(evaluate_spans_json(spans(missing), json.dumps(gear), "pvp"))
        self.assertEqual(ambiguous["status"], "ok", ambiguous)

        # But any damaged OCR stat that is still visible in the raw spans
        # must produce CHECK rather than being discarded.
        damaged = missing + ["+2O.00% Triple Hit Chance"]
        checked = json.loads(evaluate_spans_json(spans(damaged), json.dumps(gear), "pvp"))
        self.assertEqual(checked["status"], "check_ocr", checked)
        self.assertEqual(checked["action"], "check")

    def test_parser_rejects_corrupted_extra_affixes_and_duplicates(self):
        stats = [
            ocr_line("+5.00% Health", 0),
            ocr_line("+6.00% Damage", 40),
            ocr_line("+5.00% Health", 80),
        ]
        parsed = LootItemParser()._stats(stats)
        self.assertEqual(len(parsed), 3)
        self.assertIn("Duplicate", validate_affixes(
            "Legendary Iron Ring", parsed, rarity="legendary",
        ))
        bad = unparsed_affix_lines(
            ["+5.00% Health", "+6.00% Damage", "+1O.82% Critical Chance"],
            parsed[:2],
        )
        self.assertEqual(bad, ("+1O.82% Critical Chance",))

    def test_exp_validation_for_special_cape_and_wings(self):
        cape = make_item(EquipmentSlot.CAPE, "mythic", 1)
        parsed_cape = EquipmentCodec.parse_item(EquipmentSlot.CAPE, cape)
        self.assertEqual(len(parsed_cape.stats), 3)
        wings = make_item(EquipmentSlot.WINGS, "divine", 2)
        parsed_wings = EquipmentCodec.parse_item(EquipmentSlot.WINGS, wings)
        self.assertEqual(len(parsed_wings.stats), 5)

    def test_android_config_exposes_exact_same_rules_as_python(self):
        config = json.loads(app_config_json())
        self.assertEqual(config["schema"], 4)
        self.assertEqual(config["affix_bounds"], {"min": 1, "max": 5})
        self.assertEqual(config["rarity_normal_affixes"], RARITY_NORMAL_AFFIX_COUNT)
        self.assertEqual(config["exp_exceptional_bounds"], {"min": 1, "max": 2})
        self.assertEqual(config["divine_wings_normal_affixes"], 5)


if __name__ == "__main__":
    unittest.main()
