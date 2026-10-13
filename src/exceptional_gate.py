"""Shared Universal candidate policy, independent of desktop/Android OCR.

Hard reject below 90% of combined *useful* exceptional per-roll caps.
This intentionally prefers long-term exceptional quality to any temporary
normal-stat, rarity, or level upgrade; PVE/PVP modes are unaffected.
"""
from __future__ import annotations

from typing import Iterable

from .config import EXCEPTIONAL_SKILLS, SKILLS
from .domain import ParsedStat

USEFUL_EXCEPTIONAL = frozenset({
    "critical damage taken", "ranged defense", "melee defense",
    "triple hit chance", "mega crit chance",
})
MIN_PROMISING_CAP_FRACTION = 0.90


def useful_exceptional_fraction(stats: Iterable[ParsedStat]) -> float:
    return sum(
        abs(stat.value) / SKILLS[stat.name].cap
        for stat in stats
        if stat.name in USEFUL_EXCEPTIONAL
    )


def weak_exceptional_candidate(stats: Iterable[ParsedStat]) -> bool:
    rolls = tuple(stats)
    exceptional = [s for s in rolls if s.name in EXCEPTIONAL_SKILLS]
    return bool(exceptional) and useful_exceptional_fraction(exceptional) < MIN_PROMISING_CAP_FRACTION
