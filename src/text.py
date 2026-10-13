from __future__ import annotations

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
    ranked = sorted(
        ((ocr_text_similarity(value, skill), skill) for skill in SKILLS),
        reverse=True,
    )
    if not ranked:
        return None, 0.0

    best_ratio, best = ranked[0]
    second_ratio = ranked[1][0] if len(ranked) > 1 else 0.0
    threshold = 0.78 if len(value) <= 6 else 0.72
    if best_ratio < threshold or best_ratio - second_ratio < 0.05:
        return None, best_ratio
    return best, best_ratio


_OCR_CONFUSABLE_SUBSTITUTIONS = {
    ("0", "o"),
    ("1", "l"),
    ("1", "i"),
    ("2", "z"),
    ("5", "s"),
    ("6", "g"),
    ("8", "b"),
}


def ocr_text_similarity(observed: str, expected: str) -> float:
    """OCR-aware Levenshtein similarity for textual labels only.

    Numeric stat values deliberately never pass through this function.
    Common glyph confusions inside names get a reduced substitution cost.
    """
    left = canonical_name(observed)
    right = canonical_name(expected)
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    distance = _weighted_levenshtein(left, right)
    return max(0.0, 1.0 - distance / max(len(left), len(right)))


def _weighted_levenshtein(left: str, right: str) -> float:
    previous = [float(index) for index in range(len(right) + 1)]
    for left_index, left_char in enumerate(left, start=1):
        current = [float(left_index)]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[right_index - 1] + 1.0,
                    previous[right_index] + 1.0,
                    previous[right_index - 1] + _ocr_substitution_cost(left_char, right_char),
                )
            )
        previous = current
    return previous[-1]


def _ocr_substitution_cost(observed: str, expected: str) -> float:
    if observed == expected:
        return 0.0
    pair = (observed.lower(), expected.lower())
    reverse = (pair[1], pair[0])
    if pair in _OCR_CONFUSABLE_SUBSTITUTIONS or reverse in _OCR_CONFUSABLE_SUBSTITUTIONS:
        return 0.25
    return 1.0


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
