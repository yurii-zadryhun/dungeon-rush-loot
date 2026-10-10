from __future__ import annotations

import hashlib
import json

from .affix_rules import has_exp_marker
from .domain import Comparison, ComparisonStatus, ParsedItem
from .game_catalog import match_standard_item
from .text import canonical_name


def _identity(item: ParsedItem, expected_slot: str) -> dict | None:
    """Stable, complete item identity, independent of OCR presentation noise.

    A catalog miss or cross-slot item must never become an automation key.
    Numeric values stay exact at the displayed game's two-decimal precision:
    no fuzzy matching or tolerance that could hide a real loot change.
    """
    match = match_standard_item([item.title])
    if match is None or match.slot.value != expected_slot:
        return None
    if not item.rarity or item.level is None or item.tier is None:
        return None
    return {
        "name": match.name.lower(),
        "slot": expected_slot,
        "rarity": item.rarity.lower(),
        "tier": item.tier,
        "level": item.level,
        "exp": has_exp_marker(item.title),
        "melee": item.melee,
        "stats": sorted(
            (canonical_name(stat.name), round(stat.value, 2))
            for stat in item.stats
        ),
    }


def verification_key(comparison: Comparison) -> str | None:
    """Only validated comparisons can be verified for an automated tap."""
    if (
        comparison.status is not ComparisonStatus.OK
        or comparison.candidate is None
        or comparison.equipped is None
        or comparison.equipment_slot is None
    ):
        return None
    slot = comparison.equipment_slot.value
    equipped = _identity(comparison.equipped, slot)
    candidate = _identity(comparison.candidate, slot)
    if equipped is None or candidate is None:
        return None
    encoded = json.dumps(
        {"equipped": equipped, "candidate": candidate},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
