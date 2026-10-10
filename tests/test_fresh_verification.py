from __future__ import annotations

import json
import unittest
from dataclasses import replace

from src.android_bridge import evaluate_spans_json
from src.domain import (
    Action, Comparison, ComparisonStatus, EquipmentSlot,
    ParsedItem, ParsedStat,
)
from src.verification import verification_key


def stat(name: str, value: float, raw: str = "", confidence: float = 0.95) -> ParsedStat:
    return ParsedStat(name, value, raw, confidence)


def item(
    title: str, rarity: str, tier: int, level: int, affixes: tuple[ParsedStat, ...],
) -> ParsedItem:
    return ParsedItem(
        title=title, rarity=rarity, tier=tier, level=level,
        stats=affixes, raw_lines=(), average_ocr_confidence=0.90,
    )


EQUIPPED = item(
    "Divine [EXP] Celestial Helmet", "Divine", 9, 87,
    (
        stat("lifesteal", 18.92, "+18.92% Lifesteal"),
        stat("ranged damage", 1.98, "+1.98% Ranged Damage"),
        stat("critical chance", 10.82, "+10.82% Critical Chance"),
        stat("melee defense", 67.63, "+67.63% Melee Defense"),
        stat("mega crit chance", 6.54, "+6.54% Mega Crit Chance"),
    ),
)
CANDIDATE = item(
    "Immortal [EXP] Infernal Cape", "Immortal", 8, 12,
    (
        stat("critical damage", 81.21, "+81.21% Critical Damage"),
        stat("critical chance", 5.02, "+5.02% Critical Chance"),
        stat("health", 3.79, "+3.79% Health"),
        stat("knockback", 4.05, "+4.05% Knockback"),
    ),
)


def comparison(
    equipped: ParsedItem = EQUIPPED,
    candidate: ParsedItem = CANDIDATE,
    slot: EquipmentSlot = EquipmentSlot.HELMET,
    action: Action = Action.SELL,
    status: ComparisonStatus = ComparisonStatus.OK,
) -> Comparison:
    return Comparison(status, action, candidate, equipped, None, None, "", slot)


class FreshVerificationIdentityTest(unittest.TestCase):
    def test_ignores_raw_ocr_text_confidence_and_affix_row_order(self):
        initial = verification_key(comparison())
        self.assertIsNotNone(initial)
        noisy_equipped = replace(
            EQUIPPED, title="Divine [EXP] +11 Celestial Helmet",
            average_ocr_confidence=0.51,
            stats=tuple(reversed([
                replace(s, raw_text=f"Lvl87 {s.value:+.2f}%% {s.name.upper()}",
                        confidence=0.57)
                for s in EQUIPPED.stats
            ])),
        )
        noisy_candidate = replace(
            CANDIDATE, title="Immortal [EXP] +11 Infernal Cape",
            average_ocr_confidence=0.55,
            stats=tuple(reversed([
                replace(s, raw_text=f"{s.value:+.2f}% {s.name}",
                        confidence=0.45)
                for s in CANDIDATE.stats
            ])),
        )
        self.assertEqual(initial, verification_key(comparison(noisy_equipped, noisy_candidate)))

    def test_any_real_item_change_produces_a_different_key(self):
        initial = verification_key(comparison())
        modifications = {
            "candidate level": comparison(candidate=replace(CANDIDATE, level=13)),
            "candidate rarity": comparison(candidate=replace(CANDIDATE, rarity="Divine", tier=9)),
            "candidate item": comparison(candidate=replace(
                CANDIDATE, title="Immortal [EXP] Dread Helm",
            )),
            "candidate affix": comparison(candidate=replace(
                CANDIDATE,
                stats=(replace(CANDIDATE.stats[0], value=81.22), *CANDIDATE.stats[1:]),
            )),
            "equipped affix": comparison(equipped=replace(
                EQUIPPED,
                stats=(*EQUIPPED.stats[:-1], replace(EQUIPPED.stats[-1], value=6.55)),
            )),
            "equipped level": comparison(equipped=replace(EQUIPPED, level=88)),
            "exp marker": comparison(candidate=replace(
                CANDIDATE, title="Immortal Infernal Cape",
            )),
        }
        for cause, updated in modifications.items():
            with self.subTest(cause=cause):
                self.assertIsNotNone(verification_key(updated))
                self.assertNotEqual(verification_key(updated), initial)

    def test_missing_title_cross_slot_and_failed_ocr_never_produce_key(self):
        scenarios = [
            comparison(candidate=replace(CANDIDATE, title="unreadable")),
            comparison(candidate=replace(CANDIDATE, title="Immortal [EXP] Void Ring")),
            comparison(status=ComparisonStatus.CHECK_OCR),
            comparison(equipped=replace(EQUIPPED, level=None)),
            comparison(candidate=replace(CANDIDATE, rarity=None)),
        ]
        for modified in scenarios:
            with self.subTest(item=modified):
                self.assertIsNone(verification_key(modified))

    def test_json_bridge_emits_semantic_key_when_live_card_passes(self):
        # Integration: two ML Kit OCR passes with different glyph rendering,
        # confidence, y offsets and stat order MUST agree on the same item.
        from tests.test_android_bridge import _equipment

        def spans(typo: bool, reversed_affixes: bool) -> str:
            helmet = [
                "+18.92% Lifesteal", "+1.98% Ranged Damage", "+10.82% Critical Chance",
                "+67.63% Melee Defense", "+6.54% Mega Crit Chance",
            ]
            candidate = [
                "+81.21% Critical Damage", "+5.02% Critical Chance",
                "+3.79% Health", "+4.05% Knockback",
            ]
            if reversed_affixes:
                helmet.reverse()
                candidate.reverse()
            if typo:
                candidate[0] = candidate[0].replace("%", "%%")
            rows = (
                ["Equipped", "Divine", "[EXP] Celestial Helmet", "Lvl87"]
                + helmet
                + ["Immortal", "[EXP] Infernal Cape", "Lvl12"]
                + candidate
            )
            return json.dumps([
                {
                    "text": row,
                    "score": 0.93 if typo else 0.99,
                    "box": {
                        "left": 100, "right": 690,
                        "top": i * 40 + (2 if typo else 0),
                        "bottom": i * 40 + 31 + (2 if typo else 0),
                    },
                }
                for i, row in enumerate(rows)
            ])

        raw_equipment = json.dumps(_equipment())
        first = json.loads(evaluate_spans_json(spans(False, False), raw_equipment, "pvp"))
        verified = json.loads(evaluate_spans_json(spans(True, True), raw_equipment, "pvp"))
        self.assertEqual(first["status"], "ok", first["message"])
        self.assertEqual(verified["status"], "ok", verified["message"])
        self.assertEqual(first["action"], verified["action"])
        self.assertEqual(first["verification_key"], verified["verification_key"])
        self.assertTrue(first["verification_key"])

    def test_invalid_bridge_result_does_not_return_verified_key(self):
        from tests.test_android_bridge import _equipment

        invalid = json.loads(evaluate_spans_json("[]", json.dumps(_equipment()), "pvp"))
        self.assertEqual(invalid["status"], "check_ocr")
        self.assertIsNone(invalid["verification_key"])


if __name__ == "__main__":
    unittest.main()
