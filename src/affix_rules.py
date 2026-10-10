from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Sequence

from .config import (
    EXCEPTIONAL_SKILLS,
    MAX_EXCEPTIONAL_AFFIXES,
    MIN_EXCEPTIONAL_AFFIXES,
    RARITY_NORMAL_AFFIX_COUNT,
    SKILLS,
)
from .domain import EquipmentSlot, ParsedStat
from .text import canonical_name, normalize_text, parse_rarity

# Recognition variants observed in device OCR, not arbitrary partial strings.
EXP_MARKER_RE = re.compile(r"(?<![a-z0-9])(?:[\\[(]\\s*)?exp\\s*[\\])]", re.I)


def has_exp_marker(title: str) -> bool:
    return bool(EXP_MARKER_RE.search(normalize_text(title)))


@dataclass(frozen=True)
class AffixRequirement:
    normal: int
    exceptional_min: int
    exceptional_max: int

    @property
    def minimum(self) -> int:
        return self.normal + self.exceptional_min

    @property
    def maximum(self) -> int:
        return self.normal + self.exceptional_max


def affix_requirement(
    rarity: str,
    title: str,
    *,
    slot: EquipmentSlot | None = None,
) -> AffixRequirement:
    key = rarity.strip().lower()
    normal = RARITY_NORMAL_AFFIX_COUNT.get(key)
    if normal is None:
        raise ValueError(f"No verified affix-count rule for rarity {rarity!r}.")

    # The real Divine Eternal Wings screenshot has five NORMAL rolls and no
    # EXP marker. Wings use a separately observed item-specific mechanic.
    # Don't reinterpret a valid Wings screen as a failed Divine 3-roll item.
    if slot is EquipmentSlot.WINGS and key == "divine" and not has_exp_marker(title):
        return AffixRequirement(normal=5, exceptional_min=0, exceptional_max=0)

    if has_exp_marker(title):
        return AffixRequirement(
            normal=normal,
            exceptional_min=MIN_EXCEPTIONAL_AFFIXES,
            exceptional_max=MAX_EXCEPTIONAL_AFFIXES,
        )
    return AffixRequirement(normal=normal, exceptional_min=0, exceptional_max=0)


def validate_affixes(
    title: str,
    stats: Sequence[ParsedStat],
    *,
    rarity: str | None = None,
    slot: EquipmentSlot | None = None,
) -> str | None:
    """Validate the COMPLETE affix inventory, never just a broad 1-5 range.

    Normal affixes depend on rarity; [EXP] adds one/two exceptional affixes.
    Unknown rarity rules (including Ultimate) fail closed until verified.
    """
    if rarity is None:
        rarity, _ = parse_rarity(title)
    if not rarity:
        return "Missing rarity for exact affix validation."
    try:
        expectation = affix_requirement(rarity, title, slot=slot)
    except ValueError as exc:
        return str(exc)

    normal = exceptional = 0
    seen: set[str] = set()
    for stat in stats:
        name = canonical_name(stat.name)
        if name in seen:
            return f"Duplicate affix: {name}."
        seen.add(name)
        rule = SKILLS.get(name)
        if rule is None or not math.isfinite(stat.value):
            return f"Unknown or invalid affix: {name}."
        if abs(stat.value) < 0.01 or abs(stat.value) > rule.cap + 0.05:
            return f"Out-of-range affix: {name}={stat.value}."
        negative = name in {"critical damage taken", "companion cooldown"}
        if (negative and stat.value >= 0) or (not negative and stat.value <= 0):
            return f"Invalid sign for affix: {name}={stat.value}."
        if name in EXCEPTIONAL_SKILLS:
            exceptional += 1
        else:
            normal += 1

    if normal != expectation.normal:
        return (
            f"{rarity.title()} requires exactly {expectation.normal} normal affixes; "
            f"parsed {normal}."
        )
    if not expectation.exceptional_min <= exceptional <= expectation.exceptional_max:
        return (
            f"{rarity.title()}{' [EXP]' if has_exp_marker(title) else ''} "
            f"requires {expectation.exceptional_min}-{expectation.exceptional_max} "
            f"exceptional affixes; parsed {exceptional}."
        )
    return None


# Even when the expected number of affixes survives, an unreadable other affix
# must never silently become a valid 2-affix item.
_AFFIX_CANDIDATE_RE = re.compile(r"^\s*(?:[+\-]\s*\S+|\d{1,3}[.,]\S+\s+[a-z])", re.I)
_LEVEL_RE = re.compile(r"\b(?:lvl|lv|lvi)\s*[-:.]?\s*\d{1,3}\b", re.I)


def unparsed_affix_lines(raw_lines: Sequence[str], stats: Sequence[ParsedStat]) -> tuple[str, ...]:
    recognized = {normalize_text(stat.raw_text) for stat in stats}
    bad = []
    for raw in raw_lines:
        text = normalize_text(raw)
        without_level = _LEVEL_RE.sub(" ", text).strip()
        if _AFFIX_CANDIDATE_RE.match(without_level) and text not in recognized:
            bad.append(text)
    return tuple(bad)
