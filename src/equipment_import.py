from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Sequence

from .config import MAX_ITEM_LEVEL, RARITY_TIERS, SKILLS
from .affix_rules import has_exp_marker, unparsed_affix_lines, validate_affixes
from .domain import EquipmentSlot, OcrLine, OcrSpan, ParsedItem, ParsedStat
from .game_catalog import (
    CatalogMatch,
    cape_affix_count,
    cape_intrinsic_value,
    expected_wing_primaries,
    infer_cape_level,
    infer_wing_level,
    match_cape_name,
    match_standard_item,
    match_wing_name,
)
from .parsing import LootItemParser, OcrLineAssembler
from .text import LEVEL_RE, PERCENT_RE, canonical_name, fuzzy_skill_name, is_melee_title, normalize_text

ABSOLUTE_PRIMARY_RE = re.compile(
    r"^\s*(damage|health)\s+([0-9]+(?:[.,][0-9]+)?)\s*([kmbtq]?)\b",
    re.I,
)
BRACKET_RARITY_RE = re.compile(
    r"\[(common|uncommon|rare|epic|legendary|mythic|artifact|ancient|immortal|divine|ultimate)\]",
    re.I,
)
RARITY_WORD_RE = re.compile(
    r"\b(common|uncommon|rare|epic|legendary|mythic|artifact|ancient|immortal|divine|ultimate)\b",
    re.I,
)

# Import-only: the screenshot is known to contain percentage affixes.
# Require an intact signed decimal and a known stat label; never repair digits.
IMPERFECT_PERCENT_RE = re.compile(
    r"^\s*([+-]\s*\d{1,3}[.,]\d{1,2})\s*(?:[lI](?:[.,])?)?\s*%?\s+(.+?)\s*$",
    re.I,
)


@dataclass(frozen=True)
class EquipmentImportResult:
    slot: EquipmentSlot | None
    slot_confidence: float
    item: ParsedItem | None
    issues: tuple[str, ...]
    lines: tuple[OcrLine, ...]


class EquipmentScreenshotParser:
    """Shared parser for static current-equipment screenshots.

    Android is responsible only for image selection/cropping/OCR. Slot
    classification, title cleanup, special-item semantics and validation stay in
    Python so the same importer can later be driven by Paddle or another capture
    adapter on desktop.
    """

    def __init__(self) -> None:
        self.assembler = OcrLineAssembler()
        self.item_parser = LootItemParser()

    def parse_spans(
        self,
        spans: Sequence[OcrSpan],
        level_spans: Sequence[OcrSpan] = (),
    ) -> EquipmentImportResult:
        return self.parse_lines(
            self.assembler.assemble(spans),
            self.assembler.assemble(level_spans),
        )

    def parse_lines(
        self,
        lines: Sequence[OcrLine],
        level_lines: Sequence[OcrLine] = (),
    ) -> EquipmentImportResult:
        lines = tuple(line for line in lines if normalize_text(line.text).strip())
        texts = [normalize_text(line.text).strip() for line in lines]
        level_texts = [normalize_text(line.text).strip() for line in level_lines]

        primary = self._absolute_primaries(texts)
        primary_kind = next(iter(primary)) if len(primary) == 1 else None
        bracket_rarity = any(BRACKET_RARITY_RE.search(text) for text in texts)

        cape_match = match_cape_name(texts)
        wing_match = match_wing_name(texts)
        standard_match = match_standard_item(texts, primary_kind)

        slot: EquipmentSlot | None
        slot_confidence: float
        title: str
        if bracket_rarity and cape_match is not None:
            slot = EquipmentSlot.CAPE
            title, slot_confidence = cape_match
        elif {"damage", "health"}.issubset(primary) and wing_match is not None:
            slot = EquipmentSlot.WINGS
            title, slot_confidence = wing_match
        elif standard_match is not None:
            slot = standard_match.slot
            slot_confidence = standard_match.confidence
            title = standard_match.name
        else:
            slot = None
            slot_confidence = 0.0
            title = ""

        issues: list[str] = []
        if slot is None:
            issues.append("Could not identify equipment slot safely from the game catalog.")

        rarity = self._rarity(texts, slot)
        tier = RARITY_TIERS[rarity.lower()] if rarity else None
        if rarity is None:
            issues.append("Could not parse rarity.")

        level = self._level(texts, level_texts)
        recovered_lines = self._recover_equipment_percents(lines, slot, title, level)
        parsed_stats = tuple(self.item_parser._stats(
            recovered_lines, allow_cape_primaries=slot is EquipmentSlot.CAPE,
        ))

        intrinsic: tuple[ParsedStat, ...] = ()
        affixes = parsed_stats
        primary_attack = None
        primary_health = None

        if slot is EquipmentSlot.WINGS:
            primary_attack = primary.get("damage")
            primary_health = primary.get("health")

            if level is None and tier is not None:
                level = infer_wing_level(tier, primary_attack, primary_health)

            if level is not None and tier is not None:
                expected_attack, expected_health = expected_wing_primaries(tier, level)
                if primary_attack is None and primary_health is not None:
                    primary_attack = expected_attack
                if primary_health is None and primary_attack is not None:
                    primary_health = expected_health

            if primary_attack is None or primary_health is None:
                issues.append("Wings require both absolute Damage and Health primary values.")
            # Wing affix count is validated alongside every other slot.

        elif slot is EquipmentSlot.CAPE:
            observed_intrinsic = self._first_cape_intrinsic_value(parsed_stats)
            if level is None and title:
                level = infer_cape_level(title, observed_intrinsic)
            intrinsic, affixes = self._split_cape_stats(parsed_stats, title, level)
            intrinsic_names = {canonical_name(stat.name) for stat in intrinsic}
            if intrinsic_names != {"damage", "health"}:
                issues.append("Cape primary Damage/Health lines were not parsed safely.")

            # Low-rarity Cape variants may have only two rolled affixes.

        elif slot is not None:
            pass  # All slots share the 2-5 affix bounds below.

        # Retain exceptional marker in normalized persisted title. Older
        # importer versions stripped it when canonicalizing catalog names.
        if slot not in {None, EquipmentSlot.WINGS, EquipmentSlot.CAPE} and has_exp_marker(" ".join(texts)):
            title = "[EXP] " + title

        if slot is not None:
            affix_error = validate_affixes(title, affixes)
            if affix_error:
                issues.append(affix_error)
            invalid_lines = unparsed_affix_lines(
                [line.text for line in recovered_lines], parsed_stats,
            )
            if invalid_lines:
                issues.append(f"Unparsed affix lines: {invalid_lines[:3]}.")

        if level is None:
            issues.append("Could not parse level.")
        if not title:
            issues.append("Could not parse item title.")

        item = None
        if rarity is not None and level is not None and title:
            confidences = [line.score for line in (*lines, *level_lines) if line.text.strip()]
            item = ParsedItem(
                title=title,
                rarity=rarity.title(),
                tier=tier,
                level=level,
                stats=affixes,
                raw_lines=tuple(texts),
                average_ocr_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
                melee=is_melee_title(" ".join(texts)),
                primary_attack=primary_attack,
                primary_health=primary_health,
                intrinsic_stats=intrinsic,
            )

        return EquipmentImportResult(
            slot=slot,
            slot_confidence=slot_confidence,
            item=item,
            issues=tuple(dict.fromkeys(issues)),
            lines=lines,
        )

    @staticmethod
    def _recover_equipment_percents(
        lines: Sequence[OcrLine],
        slot: EquipmentSlot | None,
        title: str,
        level: int | None,
    ) -> tuple[OcrLine, ...]:
        if slot is None:
            return tuple(lines)

        cape_primary = None
        if slot is EquipmentSlot.CAPE and title and level is not None:
            try:
                cape_primary = cape_intrinsic_value(title, level)
            except (KeyError, ValueError):
                pass

        recovered = []
        for line in lines:
            text = normalize_text(line.text)
            if PERCENT_RE.search(text):
                recovered.append(line)
                continue

            match = IMPERFECT_PERCENT_RE.fullmatch(text)
            if match is None:
                recovered.append(line)
                continue

            numeric, raw_label = match.groups()
            skill, confidence = fuzzy_skill_name(raw_label)
            if skill is None or confidence < 0.94:
                recovered.append(line)
                continue

            value = float(numeric.replace(" ", "").replace(",", "."))
            if slot is EquipmentSlot.CAPE and skill in {"damage", "health"}:
                valid = cape_primary is not None and abs(value - cape_primary) <= 0.35
            else:
                valid = abs(value) <= SKILLS[skill].cap + 0.01

            if valid:
                # Only the separator was recovered. The observed numeric value
                # remains untouched, and the original OCR line remains logged.
                recovered.append(replace(line, text=f"{numeric}% {raw_label}"))
            else:
                recovered.append(line)

        return tuple(recovered)

    @staticmethod
    def _rarity(texts: Sequence[str], slot: EquipmentSlot | None) -> str | None:
        if slot is EquipmentSlot.CAPE:
            for text in texts:
                match = BRACKET_RARITY_RE.search(text)
                if match:
                    return match.group(1)
        for text in texts:
            match = RARITY_WORD_RE.search(text)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _level(texts: Sequence[str], level_texts: Sequence[str]) -> int | None:
        for text in (*texts, *level_texts):
            search_text = text[:text.find("%")] if "%" in text else text
            match = LEVEL_RE.search(search_text)
            if not match:
                continue
            normalized = EquipmentScreenshotParser._normalize_level(int(match.group(1)))
            if normalized is not None:
                return normalized

        # The dedicated level crop contains only the item icon/footer. ML Kit
        # occasionally recognizes the outlined "Lvl" poorly but still reads the
        # digits. In that tightly scoped crop a single valid integer is safe.
        values: set[int] = set()
        for text in level_texts:
            for raw in re.findall(r"\d{1,3}", text):
                normalized = EquipmentScreenshotParser._normalize_level(int(raw))
                if normalized is not None:
                    values.add(normalized)
        return next(iter(values)) if len(values) == 1 else None

    @staticmethod
    def _normalize_level(value: int) -> int | None:
        if 1 <= value <= MAX_ITEM_LEVEL:
            return value
        if 131 <= value <= 199:
            corrected = value - 100
            return corrected if 1 <= corrected <= MAX_ITEM_LEVEL else None
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
    def _first_cape_intrinsic_value(stats: Sequence[ParsedStat]) -> float | None:
        for stat in stats:
            if canonical_name(stat.name) in {"damage", "health"}:
                return abs(stat.value)
        return None

    @staticmethod
    def _split_cape_stats(
        stats: tuple[ParsedStat, ...],
        title: str,
        level: int | None,
    ) -> tuple[tuple[ParsedStat, ...], tuple[ParsedStat, ...]]:
        if not title or level is None:
            return (), stats

        try:
            expected = cape_intrinsic_value(title, level)
        except (KeyError, ValueError):
            return (), stats

        intrinsic_by_name: dict[str, ParsedStat] = {}
        affixes: list[ParsedStat] = []
        tolerance = max(0.35, expected * 0.012)

        for stat in stats:
            name = canonical_name(stat.name)
            if (
                name in {"damage", "health"}
                and name not in intrinsic_by_name
                and abs(abs(stat.value) - expected) <= tolerance
            ):
                intrinsic_by_name[name] = stat
            else:
                affixes.append(stat)

        # APK data confirms every cape in v55 has identical Damage/Health base
        # and scaler. If OCR catches only one of the two fixed primary lines,
        # reconstruct the sibling rather than treating the next rolled affix as
        # primary.
        for name in ("damage", "health"):
            if name not in intrinsic_by_name and intrinsic_by_name:
                intrinsic_by_name[name] = ParsedStat(
                    name=name,
                    value=expected,
                    raw_text=f"{expected:+.2f}% {name} [inferred from cape progression]",
                    confidence=min(stat.confidence for stat in intrinsic_by_name.values()),
                )

        intrinsic = tuple(
            intrinsic_by_name[name]
            for name in ("damage", "health")
            if name in intrinsic_by_name
        )
        return intrinsic, tuple(affixes)
