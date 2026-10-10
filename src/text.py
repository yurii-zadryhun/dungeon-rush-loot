from __future__ import annotations

import difflib
import re

from .config import ALIASES, RARITY_TIERS, SKILLS, TITLE_HINTS

PERCENT_RE = re.compile(r"([+\-]?\s*\d{1,3}(?:[.,]\d{1,2})?)\s*%")
LEVEL_RE = re.compile(r"\b(?:lvl|lv|lvi)\s*[-:.]?\s*(\d{1,3})\b", re.I)
MELEE_RE = re.compile(r"\[\s*(?:melee|meele)\s*\]", re.I)


def normalize_text(text: str) -> str:
    return (
        str(text)
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("＋", "+")
        .replace("％", "%")
        .replace("|", "I")
        .strip()
    )


def canonical_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    return ALIASES.get(normalized, normalized)


def fuzzy_skill_name(raw: str) -> tuple[str | None, float]:
    normalized = _fix_common_ocr_errors(canonical_name(raw))
    if normalized in SKILLS:
        return normalized, 1.0
    return _closest_skill(normalized)


def _fix_common_ocr_errors(value: str) -> str:
    return (
        value.replace("defenee", "defense")
        .replace("defence", "defense")
        .replace("criticai", "critical")
        .replace("lifesteai", "lifesteal")
        .replace("cooidown", "cooldown")
    )


def _closest_skill(value: str) -> tuple[str | None, float]:
    best = max(SKILLS, key=lambda skill: difflib.SequenceMatcher(None, value, skill).ratio())
    ratio = difflib.SequenceMatcher(None, value, best).ratio()
    return (best, ratio) if ratio >= 0.72 else (None, ratio)


def looks_like_title(text: str) -> bool:
    lowered = normalize_text(text).lower()
    if PERCENT_RE.search(lowered):
        return False
    if "[exp" in lowered or MELEE_RE.search(lowered) or "[range" in lowered:
        return True
    return any(rarity in lowered for rarity in RARITY_TIERS) and any(hint in lowered for hint in TITLE_HINTS)


def parse_rarity(title: str) -> tuple[str | None, int | None]:
    lowered = normalize_text(title).lower()
    for rarity, tier in sorted(RARITY_TIERS.items(), key=lambda pair: -len(pair[0])):
        if re.search(rf"\b{re.escape(rarity)}\b", lowered):
            return rarity.title(), tier
    return None, None


def is_melee_title(title: str) -> bool:
    return bool(MELEE_RE.search(title))
