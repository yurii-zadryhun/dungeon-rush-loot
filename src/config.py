from __future__ import annotations

from dataclasses import dataclass
from typing import Final

TARGET_PACKAGE: Final = "com.lavalabs.dungeonrush"
MAX_ITEM_LEVEL: Final = 130
MIN_STATS: Final = 1
MAX_STATS: Final = 5
OCR_CROP_TOP: Final = 0.40
OCR_CROP_BOTTOM: Final = 0.82
OCR_CROP_LEFT: Final = 0.125
OCR_CROP_RIGHT: Final = 0.875
DEFAULT_VISUAL_CHANGE_THRESHOLD: Final = 0.010
DEFAULT_BACKGROUND_CHECK_INTERVAL: Final = 0.50
DEFAULT_RETRY_INTERVAL: Final = 0.25
DEFAULT_HASH_TTL: Final = 10.0
DEFAULT_VISUAL_SIGNATURE_TTL: Final = 10.0
DEFAULT_CANDIDATE_HASH_TTL: Final = 10.0

TIER_SCALER: Final = 3.1622776985168457
LEVEL_SCALER: Final = 0.014999999664723873
BASE_SCORE_MIN: Final = -15.0
BASE_SCORE_MAX: Final = 20.0
BASE_SCORE_MIN_TIER: Final = 8  # Immortal
BASE_SCORE_MIN_LEVEL: Final = 1
BASE_SCORE_MAX_TIER: Final = 9  # Divine
BASE_SCORE_MAX_LEVEL: Final = 130

EXCEPTIONAL_SKILLS: Final = {
    "mega crit chance",
    "triple hit chance",
    "melee defense",
    "ranged defense",
    "critical damage taken",
    "thorns",
    "movement speed",
    "knockback",
}

CATEGORY_WEIGHTS: Final[dict[str, float]] = {
    "excellent": 180.0,
    "great": 100.0,
    "good": 55.0,
    "ok": 12.0,
    "bad": 2.0,
}


@dataclass(frozen=True)
class SkillRule:
    cap: float
    category: str


SKILLS: Final[dict[str, SkillRule]] = {
    "mega crit chance": SkillRule(10.0, "excellent"),
    "triple hit chance": SkillRule(30.0, "excellent"),
    "ranged defense": SkillRule(100.0, "excellent"),
    "critical damage taken": SkillRule(66.0, "excellent"),
    "melee defense": SkillRule(100.0, "great"),
    "attack speed": SkillRule(40.0, "great"),
    "critical chance": SkillRule(12.0, "great"),
    "critical damage": SkillRule(100.0, "great"),
    "damage": SkillRule(15.0, "good"),
    "ranged damage": SkillRule(15.0, "good"),
    "lifesteal": SkillRule(20.0, "good"),
    "block chance": SkillRule(5.0, "ok"),
    "double hit chance": SkillRule(40.0, "ok"),
    "health": SkillRule(15.0, "ok"),
    "thorns": SkillRule(15.0, "bad"),
    "movement speed": SkillRule(20.0, "bad"),
    "knockback": SkillRule(15.0, "bad"),
    "health regen": SkillRule(6.0, "bad"),
    "melee damage": SkillRule(50.0, "bad"),
    "companion damage": SkillRule(30.0, "bad"),
    "companion cooldown": SkillRule(7.0, "bad"),
}

ALIASES: Final[dict[str, str]] = {
    "mega crit": "mega crit chance",
    "triple hit": "triple hit chance",
    "double hit": "double hit chance",
    "crit chance": "critical chance",
    "crit damage": "critical damage",
    "crit damage taken": "critical damage taken",
    "melee defence": "melee defense",
    "ranged defence": "ranged defense",
    "regen": "health regen",
}

RARITY_TIERS: Final[dict[str, int]] = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
    "mythic": 5,
    "artifact": 6,
    "ancient": 7,
    "immortal": 8,
    "divine": 9,
    "ultimate": 10,
}


# Exact rarity-specific NORMAL affix counts, observed/confirmed by user.
# Ultimate has no confirmed rule; do not guess from its tier number.
RARITY_NORMAL_AFFIX_COUNT: Final[dict[str, int]] = {
    **{rarity: 1 for rarity in ("common", "uncommon", "rare", "epic")},
    **{rarity: 2 for rarity in ("legendary", "mythic", "artifact", "ancient")},
    **{rarity: 3 for rarity in ("immortal", "divine")},
}
MIN_EXCEPTIONAL_AFFIXES: Final = 1
MAX_EXCEPTIONAL_AFFIXES: Final = 2

TITLE_HINTS: Final = (
    "ring", "necklace", "shield", "crossbow", "mace", "bow", "sword", "staff",
    "wand", "helmet", "hood", "armor", "armour", "chest", "boots", "gloves",
    "cape", "wings",
)
