from __future__ import annotations

import math
import re
from typing import Sequence

from .config import EXCEPTIONAL_SKILLS, MAX_STATS, MIN_STATS, SKILLS
from .domain import ParsedStat
from .text import canonical_name, normalize_text

# Recognize the UI marker as well as observed OCR variants, such as (EXP]
# and EXP] 11. No guessed marker is inferred from the affixes themselves.
EXP_MARKER_RE = re.compile(r"(?<![a-z0-9])(?:[\[(]\s*)?exp\s*[\])]", re.I)


def has_exp_marker(title: str) -> bool:
    return bool(EXP_MARKER_RE.search(normalize_text(title)))


def validate_affixes(
    title: str,
    stats: Sequence[ParsedStat],
    *,
    minimum: int = MIN_STATS,
    maximum: int = MAX_STATS,
) -> str | None:
    """Central validation used by live OCR, imports, and persisted equipment.

    '[EXP]' means at least one exceptional roll is present; ordinary gear may
    not carry exceptional rolls. Never use this rule to synthesize an EXP tag.
    """
    if not minimum <= len(stats) <= maximum:
        return f"Expected {minimum}-{maximum} affixes; parsed {len(stats)}."

    seen: set[str] = set()
    exceptional = 0
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
        exceptional += name in EXCEPTIONAL_SKILLS

    marked = has_exp_marker(title)
    if marked and exceptional == 0:
        return "[EXP] item must have at least one exceptional affix."
    if not marked and exceptional:
        return "Non-[EXP] item cannot have exceptional affixes."
    return None


# Even when two correctly read affixes survive, an unreadable third affix
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
