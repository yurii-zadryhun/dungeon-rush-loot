from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from .config import MAX_ITEM_LEVEL, RARITY_TIERS
from .domain import EquipmentSlot, OcrLine, OcrSpan, ParsedItem, ParsedStat
from .parsing import LootItemParser, OcrLineAssembler
from .text import LEVEL_RE, PERCENT_RE, canonical_name, is_melee_title, normalize_text

ABSOLUTE_PRIMARY_RE = re.compile(
    r"^\s*(damage|health)\s+([0-9]+(?:[.,][0-9]+)?)\s*([kmbtq]?)\b",
    re.I,
)
BRACKET_RARITY_RE = re.compile(
    r"^\s*\[(common|uncommon|rare|epic|legendary|mythic|artifact|ancient|immortal|divine|ultimate)\]\s*$",
    re.I,
)
RARITY_WORD_RE = re.compile(
    r"\b(common|uncommon|rare|epic|legendary|mythic|artifact|ancient|immortal|divine|ultimate)\b",
    re.I,
)

STANDARD_SLOT_PATTERNS: tuple[tuple[EquipmentSlot, re.Pattern[str]], ...] = (
    (EquipmentSlot.HELMET, re.compile(r"\b(?:helmet|hood)\b", re.I)),
    (EquipmentSlot.BACKPACK, re.compile(r"\b(?:backpack|armor|armour|chest)\b", re.I)),
    (EquipmentSlot.GLOVES, re.compile(r"\bgloves?\b", re.I)),
    (EquipmentSlot.NECKLACE, re.compile(r"\bnecklace\b", re.I)),
    (EquipmentSlot.RING, re.compile(r"\bring\b", re.I)),
    (
        EquipmentSlot.WEAPON,
        re.compile(r"\[(?:range|ranged|melee)\]|\b(?:crossbow|bow|mace|sword|staff|wand)\b", re.I),
    ),
)

IGNORED_IMPORT_LINES = {"x", "lock", "reroll", "reroll substats"}


@dataclass(frozen=True)
class EquipmentImportResult:
    slot: EquipmentSlot | None
    slot_confidence: float
    item: ParsedItem | None
    issues: tuple[str, ...]
    lines: tuple[OcrLine, ...]


class EquipmentScreenshotParser:
    def __init__(self) -> None:
        self.assembler = OcrLineAssembler()
        self.item_parser = LootItemParser()

    def parse_spans(self, spans: Sequence[OcrSpan]) -> EquipmentImportResult:
        return self.parse_lines(self.assembler.assemble(spans))

    def parse_lines(self, lines: Sequence[OcrLine]) -> EquipmentImportResult:
        lines = tuple(line for line in lines if normalize_text(line.text).strip())
        texts = [normalize_text(line.text).strip() for line in lines]
        primary = self._absolute_primaries(texts)
        slot, confidence, slot_reason = self._slot(texts, primary)
        issues: list[str] = []
        if slot is None:
            issues.append("Could not identify equipment slot safely.")

        rarity = self._rarity(texts, slot)
        if rarity is None:
            issues.append("Could not parse rarity.")
            tier = None
        else:
            tier = RARITY_TIERS[rarity.lower()]

        level = self._level(texts)
        if level is None:
            issues.append("Could not parse level.")

        title = self._title(texts, slot)
        if not title:
            issues.append("Could not parse item title.")

        parsed_stats = tuple(self.item_parser._stats(lines))
        intrinsic: tuple[ParsedStat, ...] = ()
        affixes = parsed_stats
        primary_attack = None
        primary_health = None

        if slot is EquipmentSlot.WINGS:
            primary_attack = primary.get("damage")
            primary_health = primary.get("health")
            if not primary_attack or not primary_health:
                issues.append("Wings require both absolute Damage and Health primary values.")
            if len(affixes) != 5:
                issues.append(f"Wings expected 5 affixes; parsed {len(affixes)}.")
        elif slot is EquipmentSlot.CAPE:
            intrinsic, affixes = self._split_cape_stats(parsed_stats)
            intrinsic_names = {canonical_name(stat.name) for stat in intrinsic}
            if intrinsic_names != {"damage", "health"}:
                issues.append("Cape primary Damage/Health lines were not parsed safely.")
            if not 2 <= len(affixes) <= 5:
                issues.append(f"Cape expected at least 2 affixes; parsed {len(affixes)}.")
        elif slot is not None and not 4 <= len(affixes) <= 5:
            issues.append(f"Standard equipment expected 4-5 affixes; parsed {len(affixes)}.")

        item = None
        if rarity is not None and level is not None and title:
            confidences = [line.score for line in lines]
            item = ParsedItem(
                title=title,
                rarity=rarity.title(),
                tier=tier,
                level=level,
                stats=affixes,
                raw_lines=tuple(texts),
                average_ocr_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
                melee=is_melee_title(title),
                primary_attack=primary_attack,
                primary_health=primary_health,
                intrinsic_stats=intrinsic,
            )

        if slot_reason and confidence < 0.9:
            issues.append(f"slot: {slot_reason}")

        return EquipmentImportResult(slot, confidence, item, tuple(issues), lines)

    @staticmethod
    def _slot(texts: Sequence[str], primary: dict[str, float]) -> tuple[EquipmentSlot | None, float, str]:
        combined = " ".join(texts)
        bracket_rarity = any(BRACKET_RARITY_RE.fullmatch(text) for text in texts)
        cape_name = bool(re.search(r"\b(?:cloak|cape)\b", combined, re.I))
        if bracket_rarity and cape_name:
            return EquipmentSlot.CAPE, 1.0, "bracketed rarity + cloak/cape title"

        standard_matches = [slot for slot, pattern in STANDARD_SLOT_PATTERNS if pattern.search(combined)]
        has_both_primaries = {"damage", "health"}.issubset(primary)
        noisy_wings_title = bool(re.search(r"\[exp\]|\+\d+|\[(?:range|ranged|melee)\]", combined, re.I))
        if has_both_primaries and not standard_matches and not noisy_wings_title:
            return EquipmentSlot.WINGS, 0.99, "both absolute Damage + Health primaries and clean title"

        unique = set(standard_matches)
        if len(unique) == 1:
            return next(iter(unique)), 0.99, "slot keyword in title"
        if len(unique) > 1:
            return None, 0.0, "multiple standard slot signatures"
        return None, 0.0, "no unique slot signature"

    @staticmethod
    def _rarity(texts: Sequence[str], slot: EquipmentSlot | None) -> str | None:
        if slot is EquipmentSlot.CAPE:
            for text in texts:
                match = BRACKET_RARITY_RE.fullmatch(text)
                if match:
                    return match.group(1)
        for text in texts:
            match = RARITY_WORD_RE.search(text)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _level(texts: Sequence[str]) -> int | None:
        for text in texts:
            search_text = text[:text.find("%")] if "%" in text else text
            match = LEVEL_RE.search(search_text)
            if not match:
                continue
            value = int(match.group(1))
            if 1 <= value <= MAX_ITEM_LEVEL:
                return value
            if 131 <= value <= 199:
                corrected = value - 100
                if 1 <= corrected <= MAX_ITEM_LEVEL:
                    return corrected
        return None

    @staticmethod
    def _absolute_primaries(texts: Sequence[str]) -> dict[str, float]:
        result: dict[str, float] = {}
        for text in texts:
            if "%" in text:
                continue
            match = ABSOLUTE_PRIMARY_RE.search(text)
            if not match:
                continue
            result[match.group(1).lower()] = EquipmentScreenshotParser._magnitude(
                match.group(2), match.group(3)
            )
        return result

    @staticmethod
    def _magnitude(number: str, suffix: str) -> float:
        value = float(number.replace(",", "."))
        multipliers = {
            "": 1.0,
            "k": 1_000.0,
            "m": 1_000_000.0,
            "b": 1_000_000_000.0,
            "t": 1_000_000_000_000.0,
            "q": 1_000_000_000_000_000.0,
        }
        return value * multipliers[suffix.lower()]

    @staticmethod
    def _title(texts: Sequence[str], slot: EquipmentSlot | None) -> str:
        if slot is EquipmentSlot.CAPE:
            return next((text for text in texts if re.search(r"\b(?:cloak|cape)\b", text, re.I)), "")

        if slot is EquipmentSlot.WINGS:
            candidates = []
            for text in texts:
                lower = text.lower().strip()
                if lower in IGNORED_IMPORT_LINES:
                    continue
                if RARITY_WORD_RE.fullmatch(text) or BRACKET_RARITY_RE.fullmatch(text):
                    continue
                if LEVEL_RE.search(text.replace(" ", "")) or PERCENT_RE.search(text):
                    continue
                if ABSOLUTE_PRIMARY_RE.search(text):
                    continue
                candidates.append(text)
            return candidates[-1] if candidates else ""

        if slot is not None:
            for text in texts:
                for candidate_slot, pattern in STANDARD_SLOT_PATTERNS:
                    if candidate_slot is slot and pattern.search(text):
                        return text
        return ""

    @staticmethod
    def _split_cape_stats(
        stats: tuple[ParsedStat, ...],
    ) -> tuple[tuple[ParsedStat, ...], tuple[ParsedStat, ...]]:
        if len(stats) >= 2:
            first_two = stats[:2]
            if {canonical_name(stat.name) for stat in first_two} == {"damage", "health"}:
                return first_two, stats[2:]
        return (), stats
