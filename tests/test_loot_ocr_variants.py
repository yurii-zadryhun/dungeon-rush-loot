from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from src.android_bridge import evaluate_spans_json
from src.domain import Box, EquipmentSlot, OcrLine, OcrSpan
from src.parsing import LootCardSplitter, LootItemParser, OcrLineAssembler


@dataclass(frozen=True)
class Card:
    rarity: str
    title: str
    level: int
    stats: tuple[tuple[str, float], ...]

    @property
    def exp(self) -> bool:
        from src.config import EXCEPTIONAL_SKILLS
        return any(name in EXCEPTIONAL_SKILLS for name, _ in self.stats)

    @property
    def payload(self) -> dict:
        marker = "[EXP] " if self.exp else ""
        return {
            "title": f"{self.rarity} {marker}{self.title}",
            "rarity": self.rarity,
            "level": self.level,
            "stats": dict(self.stats),
        }


CARDS = {
    EquipmentSlot.WEAPON: (
        Card("Divine", "Eternal Crossbow", 30, (
            ("critical damage", 87.06), ("health", 8.21),
            ("companion cooldown", -4.98), ("mega crit chance", 9.40),
        )),
        Card("Immortal", "Druidic Crossbow", 12, (
            ("critical damage", 61.21), ("critical chance", 5.02),
            ("health", 3.79), ("knockback", 4.05),
        )),
    ),
    EquipmentSlot.HELMET: (
        Card("Divine", "Celestial Helmet", 87, (
            ("lifesteal", 18.92), ("ranged damage", 1.98),
            ("critical chance", 10.82), ("melee defense", 67.63),
            ("mega crit chance", 6.54),
        )),
        Card("Immortal", "Infernal Cape", 12, (
            ("critical damage", 81.21), ("critical chance", 5.02),
            ("health", 3.79), ("knockback", 4.05),
        )),
    ),
    EquipmentSlot.BACKPACK: (
        Card("Immortal", "Crimson Backpack", 106, (
            ("critical chance", 8.04), ("critical damage", 78.01),
            ("attack speed", 9.11), ("ranged defense", 54.09),
            ("critical damage taken", -39.40),
        )),
        Card("Divine", "Celestial Lyre", 87, (
            ("lifesteal", 11.32), ("ranged damage", 7.32),
            ("attack speed", 25.10), ("mega crit chance", 9.07),
        )),
    ),
    EquipmentSlot.GLOVES: (
        Card("Immortal", "Crimson Gloves", 124, (
            ("lifesteal", 4.50), ("ranged damage", 7.32),
            ("melee damage", 19.30), ("critical damage taken", -51.74),
            ("triple hit chance", 24.12),
        )),
        Card("Divine", "Sacred Gloves", 63, (
            ("critical damage", 67.20), ("critical chance", 8.20),
            ("damage", 11.10), ("mega crit chance", 8.00),
        )),
    ),
    EquipmentSlot.NECKLACE: (
        Card("Immortal", "Dread Necklace", 12, (
            ("lifesteal", 11.32), ("companion cooldown", -3.66),
            ("critical damage", 46.04), ("triple hit chance", 24.44),
            ("critical damage taken", -44.78),
        )),
        Card("Divine", "Sacred Necklace", 44, (
            ("attack speed", 30.22), ("critical chance", 9.33),
            ("critical damage", 85.42), ("triple hit chance", 20.00),
        )),
    ),
    EquipmentSlot.RING: (
        Card("Immortal", "Void Ring", 16, (
            ("health regen", 3.64), ("companion cooldown", -5.72),
            ("critical chance", 8.74), ("triple hit chance", 23.09),
            ("mega crit chance", 9.07),
        )),
        Card("Divine", "Celestial Ring", 44, (
            ("attack speed", 30.10), ("critical chance", 10.20),
            ("critical damage", 78.21), ("triple hit chance", 20.00),
        )),
    ),
}


def equipment(slot: EquipmentSlot, equipped: Card) -> str:
    base = {
        name.value: {
            "title": name.value,
            "rarity": "Divine",
            "level": 100,
            "stats": {
                "damage": 5, "health": 5,
                "attack speed": 10,
            },
        }
        for name in EquipmentSlot
        if name not in {EquipmentSlot.CAPE, EquipmentSlot.WINGS}
    }
    base[slot.value] = equipped.payload
    base["wings"] = {
        "title": "Eternal", "rarity": "Divine", "level": 100,
        "primary": {"attack": 2250000, "health": 7500000},
        "stats": {
            "ranged damage": 13.13, "critical damage": 79.10,
            "damage": 13.19, "critical chance": 11.06,
            "attack speed": 30.50,
        },
    }
    base["cape"] = {
        "title": "Divine Cloak", "rarity": "Mythic", "level": 31,
        "intrinsic_stats": {"damage": 80, "health": 80},
        "stats": {"critical damage": 33.25, "critical chance": 8.89},
    }
    return json.dumps(base)


def affix_line(name: str, value: float, separator: str = "%") -> str:
    return f"{value:+.2f}{separator} {name.title()}"


def render_card(
    card: Card,
    *,
    title_style: str = "separate",
    level_style: str = "between",
    separator: str = "%",
    level_format: str = "Lvl {level}",
    affix_override: dict[int, str] | None = None,
) -> list[str]:
    marker = "[EXP] " if card.exp and title_style != "plain" else ""
    title = marker + card.title
    if title_style == "inline":
        rows = [f"{card.rarity} {title}"]
    elif title_style == "wrapped":
        first, last = card.title.rsplit(" ", 1)
        rows = [card.rarity, marker + first, last]
    elif title_style == "plain":
        rows = [card.rarity, card.title]
    elif title_style == "exp_plus":
        rows = [card.rarity, (f"[EXP] +11 {card.title}" if card.exp else card.title)]
    else:
        rows = [card.rarity, title]
    rows.append("Health 3.28M" if card.title in {
        "Celestial Helmet", "Infernal Cape", "Crimson Backpack",
        "Celestial Lyre", "Dread Necklace", "Sacred Necklace",
    } else "Damage 709.35K")

    affixes = [
        (affix_override or {}).get(i, affix_line(name, value, separator))
        for i, (name, value) in enumerate(card.stats)
    ]
    level = level_format.format(level=card.level)
    if level_style == "first":
        rows.append(level)
        rows.extend(affixes)
    elif level_style == "last":
        rows.extend(affixes)
        rows.append(level)
    elif level_style == "prefix":
        affixes[0] = f"{level} {affixes[0]}"
        rows.extend(affixes)
    elif level_style == "inside_label":
        parts = affixes[1].split(" ", 1)
        affixes[1] = f"{parts[0]} {level} {parts[1]}"
        rows.extend(affixes)
    elif level_style == "suffix":
        affixes[1] = f"{affixes[1]} {level}"
        rows.extend(affixes)
    else:
        rows.extend(affixes[:2] + [level] + affixes[2:])
    return rows


def popup_rows(equipped: Card, candidate: Card, **kwargs) -> list[str]:
    return (
        ["Equipped"]
        + render_card(equipped, **kwargs)
        + render_card(candidate, **kwargs)
        + ["Sell", "Equip"]
    )


def as_lines(rows: list[str]) -> list[OcrLine]:
    return [
        OcrLine(text, 0.97, Box(100, index * 40, 700, index * 40 + 27))
        for index, text in enumerate(rows)
    ]


def as_spans(rows: list[str]) -> str:
    return json.dumps([
        {
            "text": text, "score": 0.97,
            "box": {"left": 100, "top": i * 40, "right": 700, "bottom": i * 40 + 27},
        }
        for i, text in enumerate(rows)
    ])


class LootOcrVariantTest(unittest.TestCase):
    def assert_cards(self, rows: list[str], equipped: Card, candidate: Card):
        left, right = LootCardSplitter().split(as_lines(rows))
        for observed, expected in (
            (LootItemParser().parse(left), equipped),
            (LootItemParser().parse(right), candidate),
        ):
            self.assertEqual(observed.rarity, expected.rarity)
            self.assertIn(expected.title.lower(), observed.title.lower())
            self.assertEqual(observed.level, expected.level)
            self.assertEqual(len(observed.stats), len(expected.stats))
            self.assertEqual(
                {stat.name: round(stat.value, 2) for stat in observed.stats},
                dict(expected.stats),
            )

    def test_all_six_slots_with_separated_and_inline_rarity(self):
        for slot, (equipped, candidate) in CARDS.items():
            for title_style in ("separate", "inline", "plain", "exp_plus", "wrapped"):
                with self.subTest(slot=slot.value, style=title_style):
                    rows = popup_rows(equipped, candidate, title_style=title_style)
                    self.assert_cards(rows, equipped, candidate)

    def test_level_in_six_different_positions(self):
        for slot, (equipped, candidate) in CARDS.items():
            for level_style in ("first", "last", "between", "prefix", "inside_label", "suffix"):
                with self.subTest(slot=slot.value, level_style=level_style):
                    self.assert_cards(
                        popup_rows(equipped, candidate, level_style=level_style),
                        equipped, candidate,
                    )

    def test_multiple_level_label_variants(self):
        for slot, (equipped, candidate) in CARDS.items():
            for format_ in ("Lvl {level}", "Lvl{level}", "Lv {level}", "LVL: {level}", "Lvi {level}"):
                with self.subTest(slot=slot.value, format=format_):
                    self.assert_cards(
                        popup_rows(equipped, candidate, level_format=format_),
                        equipped, candidate,
                    )

    def test_percent_variations_per_every_affix_and_slot(self):
        for slot, (equipped, candidate) in CARDS.items():
            for separator in ("%", " %", "l%", "I%", "l.", "°", "º", "o", "O", ""):
                with self.subTest(slot=slot.value, separator=separator):
                    self.assert_cards(
                        popup_rows(equipped, candidate, separator=separator),
                        equipped, candidate,
                    )

    def test_label_ocr_confusions_and_comma_decimals(self):
        for slot, (equipped, candidate) in CARDS.items():
            substitutions = {
                "Attack Speed": "Attack 5peed",
                "Critical Damage": "CriticaI Damage",
                "Critical Chance": "Critical Chanee",
                "Lifesteal": "Lifesteai",
                "Melee Defense": "Meele Defense",
                "Companion Cooldown": "Companion Cooidown",
            }
            for name, typo in substitutions.items():
                for item_index, card in enumerate((equipped, candidate)):
                    matching = [i for i, (skill, _) in enumerate(card.stats) if skill.title() == name]
                    if not matching:
                        continue
                    affix_index = matching[0]
                    value = card.stats[affix_index][1]
                    typo_value = f"{value:+.2f}".replace(".", ",")
                    altered = affix_line(name, value).replace(f"{value:+.2f}% {name}", f"{typo_value}% {typo}")
                    left = render_card(equipped, affix_override={affix_index: altered} if item_index == 0 else None)
                    right = render_card(candidate, affix_override={affix_index: altered} if item_index == 1 else None)
                    with self.subTest(slot=slot.value, typo=typo, index=item_index):
                        self.assert_cards(["Equipped"] + left + right, equipped, candidate)

    def test_split_stat_text_and_percent_between_lines(self):
        # Label continuation: the value is recognized, but ML Kit places its
        # descriptive label on the next line, sometimes after a level label.
        left, right = CARDS[EquipmentSlot.HELMET]
        rows = render_card(left, level_style="first")
        index = next(i for i, s in enumerate(rows) if "Ranged Damage" in s)
        rows[index] = "+1.98%"
        rows.insert(index + 1, "Ranged Damage")
        self.assert_cards(["Equipped"] + rows + render_card(right), left, right)

        rows = render_card(left, level_style="last")
        index = next(i for i, s in enumerate(rows) if "Ranged Damage" in s)
        rows[index] = "+1.98%"
        rows.insert(index + 1, "Lvl 87")
        rows.insert(index + 2, "Ranged Damage")
        # Duplicate valid level markers do not introduce contradictory values.
        self.assert_cards(["Equipped"] + rows + render_card(right), left, right)

    def test_element_level_jitter_assembles_into_a_stat_row(self):
        assembler = OcrLineAssembler()
        spans = [
            OcrSpan("Lvl87", 0.98, Box(5, 100, 75, 127)),
            OcrSpan("+1.98%", 0.94, Box(90, 102, 160, 126)),
            OcrSpan("Ranged", 0.95, Box(170, 98, 240, 128)),
            OcrSpan("Damage", 0.92, Box(250, 103, 330, 125)),
        ]
        lines = assembler.assemble(spans)
        self.assertEqual(len(lines), 1)
        item = LootItemParser().parse([OcrLine("Divine [EXP] Celestial Helmet", .99, Box(0, 0, 500, 30)), *lines])
        self.assertEqual(item.level, 87)
        self.assertEqual(item.stats[0].name, "ranged damage")
        self.assertEqual(item.stats[0].value, 1.98)

    def test_android_bridge_scores_each_slot_from_variant_popup(self):
        for slot, (equipped, candidate) in CARDS.items():
            for style in ("between", "inside_label"):
                with self.subTest(slot=slot.value, level=style):
                    result = json.loads(evaluate_spans_json(
                        as_spans(popup_rows(equipped, candidate, level_style=style)),
                        equipment(slot, equipped),
                        "pvp",
                    ))
                    self.assertEqual(result["status"], "ok", result["message"])
                    self.assertEqual(result["slot"], slot.value)
                    self.assertEqual(result["equipped"]["level"], equipped.level)
                    self.assertEqual(result["candidate"]["level"], candidate.level)
                    self.assertIn(result["action"], {"sell", "equip"})

    def test_bad_numbers_or_missing_required_fields_fail_closed(self):
        equipped, candidate = CARDS[EquipmentSlot.HELMET]
        fixtures = {
            "unreadable digits": "+1O.82% Critical Chance",
            "out of bounds": "+70.82% Critical Chance",
            "wrong sign": "-10.82% Critical Chance",
            "no leading sign or percent": "10.82 Critical Chance",
            "unknown label": "+10.82% Chocolate Croissant",
            "incomplete decimal": "+10.A2% Critical Chance",
        }
        for label, corrupted in fixtures.items():
            eq_lines = render_card(equipped, affix_override={2: corrupted})
            result = json.loads(evaluate_spans_json(
                as_spans(["Equipped"] + eq_lines + render_card(candidate)),
                equipment(EquipmentSlot.HELMET, equipped),
                "pvp",
            ))
            with self.subTest(case=label):
                self.assertEqual(result["status"], "check_ocr", result)
                self.assertEqual(result["action"], "check")

    def test_conflicting_level_or_missing_title_fails_closed(self):
        equipped, candidate = CARDS[EquipmentSlot.HELMET]
        rows = render_card(equipped) + ["Lvl 44"] + render_card(candidate)
        event = json.loads(evaluate_spans_json(
            as_spans(rows), equipment(EquipmentSlot.HELMET, equipped), "pvp",
        ))
        self.assertEqual(event["status"], "check_ocr")
        self.assertEqual(event["action"], "check")

        rows = render_card(equipped)
        rows[1] = "Random nonsense without equipment name"
        event = json.loads(evaluate_spans_json(
            as_spans(rows + render_card(candidate)),
            equipment(EquipmentSlot.HELMET, equipped), "pvp",
        ))
        self.assertEqual(event["status"], "check_ocr")

    def test_duplicate_or_incomplete_affix_never_taps(self):
        equipped, candidate = CARDS[EquipmentSlot.HELMET]
        rows = render_card(equipped)
        duplicate = rows.copy()
        affix_index = next(i for i, s in enumerate(duplicate) if "Mega Crit Chance" in s)
        duplicate[affix_index] = "+10.82% Critical Chance"
        for label, current in (("duplicate", duplicate), ("missing", rows[:-1])):
            result = json.loads(evaluate_spans_json(
                as_spans(current + render_card(candidate)),
                equipment(EquipmentSlot.HELMET, equipped), "universal",
            ))
            with self.subTest(kind=label):
                self.assertEqual(result["action"], "check")
                self.assertEqual(result["status"], "check_ocr")


    def test_generic_corrupted_level_prefix_with_intact_digits(self):
        equipped, candidate = CARDS[EquipmentSlot.HELMET]
        for variant in (
            "Lvl/{level}", "LvI/{level}", "Lv?{level}",
            "Lv ..{level}", "LU|{level}", "Lv••{level}",
            "Lv1 {level}", "Lv1/{level}", "Lv1-{level}",
        ):
            with self.subTest(variant=variant):
                self.assert_cards(
                    popup_rows(equipped, candidate, level_format=variant),
                    equipped, candidate,
                )

    def test_corrupted_numeric_level_is_never_reconstructed(self):
        equipped, candidate = CARDS[EquipmentSlot.HELMET]
        for invalid in ("06", "Lvl", "LvXXXX9", "Lvl 999", "Lv??1234", "Lv5 24", "Lv1123", "Lv1 1234", "Lvl 12.34%", "Lvl 154"):
            rows = render_card(equipped)
            rows = [invalid if row == f"Lvl {equipped.level}" else row for row in rows]
            result = json.loads(evaluate_spans_json(
                as_spans(rows + render_card(candidate)),
                equipment(EquipmentSlot.HELMET, equipped), "pvp",
            ))
            with self.subTest(invalid=invalid):
                self.assertEqual(result["status"], "check_ocr", result)
                self.assertEqual(result["action"], "check")

if __name__ == "__main__":
    unittest.main()
