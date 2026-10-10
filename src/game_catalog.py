from __future__ import annotations

from dataclasses import dataclass
import difflib
import re
from typing import Iterable, Sequence

from .domain import EquipmentSlot
from .text import LEVEL_RE, PERCENT_RE, normalize_text

# Extracted from com.lavalabs.dungeonrush v55 Unity serialized assets supplied by
# the user. 406 EquipmentData objects collapse to 365 distinct display names.
# There are no cross-slot name collisions in this build.
_STANDARD_ITEM_SLOTS = {'arcane backpack': 'backpack', 'arcane bow': 'weapon', 'arcane dagger': 'weapon', 'arcane gloves': 'gloves', 'arcane helmet': 'helmet', 'arcane necklace': 'necklace', 'arcane ring': 'ring', 'archer cape': 'helmet', 'archer gloves': 'gloves', 'archer hat': 'helmet', 'archer mittens': 'gloves', 'archer necklace': 'necklace', 'archer quiver': 'backpack', 'archer ring': 'ring', 'arrow bundle': 'backpack', 'arrow necklace': 'necklace', 'battle axe': 'weapon', 'bed roll': 'backpack', 'birch ring': 'ring', 'blessed tiara': 'helmet', 'blizzard greatsword': 'weapon', 'blood gloves': 'gloves', 'bow': 'weapon', 'celestial gloves': 'gloves', 'celestial helmet': 'helmet', 'celestial lightning': 'weapon', 'celestial lyre': 'backpack', 'celestial necklace': 'necklace', 'celestial ring': 'ring', 'chill cape': 'helmet', 'chill gloves': 'gloves', 'chill necklace': 'necklace', 'chill ring': 'ring', 'crimson backpack': 'backpack', 'crimson gauntlets': 'gloves', 'crimson gloves': 'gloves', 'crude dagger': 'weapon', 'crystal gloves': 'gloves', 'crystal necklace': 'necklace', 'crystal ring': 'ring', 'cultist helmet': 'helmet', 'cultistweapon': 'weapon', 'cursed necklace': 'necklace', 'cursed ring': 'ring', 'dark ring': 'ring', 'divine gloves': 'gloves', 'divine mace': 'weapon', 'dragonweapon': 'weapon', 'dread dagger': 'weapon', 'dread gloves': 'gloves', 'dread helm': 'helmet', 'dread necklace': 'necklace', 'druid hat': 'helmet', 'druidic cape': 'helmet', 'druidic crossbow': 'weapon', 'druidic gloves': 'gloves', 'druidic necklace': 'necklace', 'druidic ring': 'ring', 'druidic sword': 'weapon', 'elven helmet': 'helmet', 'eternal cape': 'helmet', 'eternal crossbow': 'weapon', 'exceptional gloves': 'gloves', 'exceptional helmet': 'helmet', 'exceptional weapon': 'weapon', 'farm gloves': 'gloves', 'feather necklace': 'necklace', 'flame staff': 'weapon', 'frost bow': 'weapon', 'frost gloves': 'gloves', 'frost greataxe': 'weapon', 'frost helmet': 'helmet', 'frost necklace': 'necklace', 'frost ring': 'ring', 'frost shield': 'backpack', 'glacial tiara': 'helmet', 'glimmer axe': 'weapon', 'great axe': 'weapon', 'green necklace': 'necklace', 'green ring': 'ring', 'hand wraps': 'gloves', 'hawk necklace': 'necklace', 'heavy gauntlets': 'gloves', 'heavy gloves': 'gloves', 'hide backpack': 'backpack', 'hide bracers': 'gloves', 'hide gloves': 'gloves', 'holy gloves': 'gloves', 'holy greatsword': 'weapon', 'holy necklace': 'necklace', 'holy ring': 'ring', 'ice dagger': 'weapon', 'ice gloves': 'gloves', 'ice helmet': 'helmet', 'ice javelin': 'weapon', 'ice necklace': 'necklace', 'ice ring': 'ring', 'ice shield': 'backpack', 'ice staff': 'weapon', 'infernal cape': 'helmet', 'infernal greatsword': 'weapon', 'infernal tome': 'backpack', 'iron gauntlets': 'gloves', 'iron gloves': 'gloves', 'iron necklace': 'necklace', 'iron ring': 'ring', 'iron sword': 'weapon', 'javelin': 'weapon', 'kite shield': 'backpack', 'knight crossbow': 'weapon', 'knight gloves': 'gloves', 'knight helmet': 'helmet', 'knight javelin': 'weapon', 'knight necklace': 'necklace', 'knight ring': 'ring', 'knight shield': 'backpack', 'knight sword': 'weapon', 'leather cape': 'helmet', 'leather gloves': 'gloves', 'longbow': 'weapon', 'mace': 'weapon', 'mage gloves': 'gloves', 'mage hat': 'helmet', 'marksman hat': 'helmet', 'melee-1': 'weapon', 'melee-2': 'weapon', 'mystic gloves': 'gloves', 'mystic kunai': 'weapon', 'mystic necklace': 'necklace', 'mystic ring': 'ring', 'mystic shield': 'backpack', 'mystic sword': 'weapon', 'oak ring': 'ring', 'orange gloves': 'gloves', 'orange mittens': 'gloves', 'peasant cap': 'helmet', 'peasant cape': 'helmet', 'peasant hat': 'helmet', 'pitchfork': 'weapon', 'primitive bow': 'weapon', 'primitive necklace': 'necklace', 'quiver': 'backpack', 'radiant gloves': 'gloves', 'radiant shield': 'backpack', 'radiant staff': 'weapon', 'range-1': 'weapon', 'range-2': 'weapon', 'rider gloves': 'gloves', 'round helmet': 'helmet', 'round shield': 'backpack', 'royal cape': 'helmet', 'royal necklace': 'necklace', 'royal ring': 'ring', 'royal sword': 'weapon', 'rune necklace': 'necklace', 'sacred book': 'backpack', 'sacred gloves': 'gloves', 'sacred necklace': 'necklace', 'sacred ring': 'ring', 'sacred spear': 'weapon', 'sacred sword': 'weapon', 'scarlet necklace': 'necklace', 'scarlet ring': 'ring', 'scifi_tier_01_back_item_01': 'backpack', 'scifi_tier_01_back_item_02': 'backpack', 'scifi_tier_01_glove_01': 'gloves', 'scifi_tier_01_glove_02': 'gloves', 'scifi_tier_01_hat_01': 'helmet', 'scifi_tier_01_hat_02': 'helmet', 'scifi_tier_01_necklace_01': 'necklace', 'scifi_tier_01_necklace_02': 'necklace', 'scifi_tier_01_ring_01': 'ring', 'scifi_tier_01_ring_02': 'ring', 'scifi_tier_02_back_item_01': 'backpack', 'scifi_tier_02_back_item_02': 'backpack', 'scifi_tier_02_glove_01': 'gloves', 'scifi_tier_02_glove_02': 'gloves', 'scifi_tier_02_hat_01': 'helmet', 'scifi_tier_02_hat_02': 'helmet', 'scifi_tier_02_melee_weapon 1': 'weapon', 'scifi_tier_02_melee_weapon 2': 'weapon', 'scifi_tier_02_necklace_01': 'necklace', 'scifi_tier_02_necklace_02': 'necklace', 'scifi_tier_02_range_weapon 1': 'weapon', 'scifi_tier_02_range_weapon 2': 'weapon', 'scifi_tier_02_ring_01': 'ring', 'scifi_tier_02_ring_02': 'ring', 'scifi_tier_03_back_item_01': 'backpack', 'scifi_tier_03_back_item_02': 'backpack', 'scifi_tier_03_glove_01': 'gloves', 'scifi_tier_03_glove_02': 'gloves', 'scifi_tier_03_hat_01': 'helmet', 'scifi_tier_03_hat_02': 'helmet', 'scifi_tier_03_melee_weapon 1': 'weapon', 'scifi_tier_03_melee_weapon 2': 'weapon', 'scifi_tier_03_necklace_01': 'necklace', 'scifi_tier_03_necklace_02': 'necklace', 'scifi_tier_03_range_weapon 1': 'weapon', 'scifi_tier_03_range_weapon 2': 'weapon', 'scifi_tier_03_ring_01': 'ring', 'scifi_tier_03_ring_02': 'ring', 'scifi_tier_04_back_item_01': 'backpack', 'scifi_tier_04_back_item_02': 'backpack', 'scifi_tier_04_glove_01': 'gloves', 'scifi_tier_04_glove_02': 'gloves', 'scifi_tier_04_hat_01': 'helmet', 'scifi_tier_04_hat_02': 'helmet', 'scifi_tier_04_melee_weapon 1': 'weapon', 'scifi_tier_04_melee_weapon 2': 'weapon', 'scifi_tier_04_necklace_01': 'necklace', 'scifi_tier_04_necklace_02': 'necklace', 'scifi_tier_04_range_weapon 1': 'weapon', 'scifi_tier_04_range_weapon 2': 'weapon', 'scifi_tier_04_ring_01': 'ring', 'scifi_tier_04_ring_02': 'ring', 'scifi_tier_05_back_item_01': 'backpack', 'scifi_tier_05_back_item_02': 'backpack', 'scifi_tier_05_glove_01': 'gloves', 'scifi_tier_05_glove_02': 'gloves', 'scifi_tier_05_hat_01': 'helmet', 'scifi_tier_05_hat_02': 'helmet', 'scifi_tier_05_melee_weapon 1': 'weapon', 'scifi_tier_05_melee_weapon 2': 'weapon', 'scifi_tier_05_necklace_01': 'necklace', 'scifi_tier_05_necklace_02': 'necklace', 'scifi_tier_05_range_weapon 1': 'weapon', 'scifi_tier_05_range_weapon 2': 'weapon', 'scifi_tier_05_ring_01': 'ring', 'scifi_tier_05_ring_02': 'ring', 'scifi_tier_06_back_item_01': 'backpack', 'scifi_tier_06_back_item_02': 'backpack', 'scifi_tier_06_glove_01': 'gloves', 'scifi_tier_06_glove_02': 'gloves', 'scifi_tier_06_hat_01': 'helmet', 'scifi_tier_06_hat_02': 'helmet', 'scifi_tier_06_melee_weapon 1': 'weapon', 'scifi_tier_06_melee_weapon 2': 'weapon', 'scifi_tier_06_necklace_01': 'necklace', 'scifi_tier_06_necklace_02': 'necklace', 'scifi_tier_06_range_weapon 1': 'weapon', 'scifi_tier_06_range_weapon 2': 'weapon', 'scifi_tier_06_ring_01': 'ring', 'scifi_tier_06_ring_02': 'ring', 'scifi_tier_07_back_item_01': 'backpack', 'scifi_tier_07_back_item_02': 'backpack', 'scifi_tier_07_glove_01': 'gloves', 'scifi_tier_07_glove_02': 'gloves', 'scifi_tier_07_hat_01': 'helmet', 'scifi_tier_07_hat_02': 'helmet', 'scifi_tier_07_melee_weapon 1': 'weapon', 'scifi_tier_07_melee_weapon 2': 'weapon', 'scifi_tier_07_necklace_01': 'necklace', 'scifi_tier_07_necklace_02': 'necklace', 'scifi_tier_07_range_weapon 1': 'weapon', 'scifi_tier_07_range_weapon 2': 'weapon', 'scifi_tier_07_ring_01': 'ring', 'scifi_tier_07_ring_02': 'ring', 'scifi_tier_08_back_item_01': 'backpack', 'scifi_tier_08_back_item_02': 'backpack', 'scifi_tier_08_glove_01': 'gloves', 'scifi_tier_08_glove_02': 'gloves', 'scifi_tier_08_hat_01': 'helmet', 'scifi_tier_08_hat_02': 'helmet', 'scifi_tier_08_melee_weapon 1': 'weapon', 'scifi_tier_08_melee_weapon 2': 'weapon', 'scifi_tier_08_necklace_01': 'necklace', 'scifi_tier_08_necklace_02': 'necklace', 'scifi_tier_08_range_weapon 1': 'weapon', 'scifi_tier_08_range_weapon 2': 'weapon', 'scifi_tier_08_ring_01': 'ring', 'scifi_tier_08_ring_02': 'ring', 'scifi_tier_09_back_item_01': 'backpack', 'scifi_tier_09_back_item_02': 'backpack', 'scifi_tier_09_glove_01': 'gloves', 'scifi_tier_09_glove_02': 'gloves', 'scifi_tier_09_hat_01': 'helmet', 'scifi_tier_09_hat_02': 'helmet', 'scifi_tier_09_melee_weapon 1': 'weapon', 'scifi_tier_09_melee_weapon 2': 'weapon', 'scifi_tier_09_necklace_01': 'necklace', 'scifi_tier_09_necklace_02': 'necklace', 'scifi_tier_09_range_weapon 1': 'weapon', 'scifi_tier_09_range_weapon 2': 'weapon', 'scifi_tier_09_ring_01': 'ring', 'scifi_tier_09_ring_02': 'ring', 'scifi_tier_10_back_item_01': 'backpack', 'scifi_tier_10_back_item_02': 'backpack', 'scifi_tier_10_glove_01': 'gloves', 'scifi_tier_10_glove_02': 'gloves', 'scifi_tier_10_hat_01': 'helmet', 'scifi_tier_10_hat_02': 'helmet', 'scifi_tier_10_melee_weapon 1': 'weapon', 'scifi_tier_10_melee_weapon 2': 'weapon', 'scifi_tier_10_necklace_01': 'necklace', 'scifi_tier_10_necklace_02': 'necklace', 'scifi_tier_10_range_weapon 1': 'weapon', 'scifi_tier_10_range_weapon 2': 'weapon', 'scifi_tier_10_ring_01': 'ring', 'scifi_tier_10_ring_02': 'ring', 'sickle': 'weapon', 'simple helmet': 'helmet', 'sling': 'weapon', 'solar greataxe': 'weapon', 'solar helmet': 'helmet', 'solar necklace': 'necklace', 'solar ring': 'ring', 'soldier bow': 'weapon', 'soldier daggers': 'weapon', 'soldier helmet': 'helmet', 'soldier sword': 'weapon', 'sorcerer cape': 'helmet', 'squire crossbow': 'weapon', 'squire helmet': 'helmet', 'squire javelin': 'weapon', 'squire necklace': 'necklace', 'squire ring': 'ring', 'squire sword': 'weapon', 'steel gloves': 'gloves', 'steel ring': 'ring', 'straw hat': 'helmet', 'templar gloves': 'gloves', 'templar helmet': 'helmet', 'templar necklace': 'necklace', 'templar ring': 'ring', 'templar shield': 'backpack', 'thief ring': 'ring', 'throwing stick': 'weapon', 'tooth necklace': 'necklace', 'travel pack': 'backpack', 'twin dagger': 'weapon', 'tyrant gloves': 'gloves', 'tyrant helmet': 'helmet', 'tyrant staff': 'weapon', 'undying bow': 'weapon', 'undying mask': 'helmet', 'undying necklace': 'necklace', 'undying ring': 'ring', 'vagabond gloves': 'gloves', 'verdant gloves': 'gloves', 'verdant helmet': 'helmet', 'viking bow': 'weapon', 'viking cape': 'helmet', 'viking hat': 'helmet', 'viking helmet': 'helmet', 'viking horns': 'helmet', 'viking ring': 'ring', 'viking spear': 'weapon', 'void javelin': 'weapon', 'void ring': 'ring', 'void scythe': 'weapon', 'wild axe': 'weapon', 'wild gloves': 'gloves', 'wild necklace': 'necklace', 'wild quiver': 'backpack', 'wild ring': 'ring', 'wild staff': 'weapon', 'winter gloves': 'gloves', 'wizard hat': 'helmet', 'wizard staff': 'weapon', 'wood axe': 'weapon', 'wooden necklace': 'necklace', 'wooden ring': 'ring', 'wooden sword': 'weapon', 'zombie gloves': 'gloves', 'zombie helmet': 'helmet'}

RARITY_WORDS = (
    "common", "uncommon", "rare", "epic", "legendary", "mythic",
    "artifact", "ancient", "immortal", "divine", "ultimate",
)

WING_NAMES = (
    "Fledgling", "Hawk", "Dove", "Blaze", "Wyrmling", "Onyx",
    "Green Dragon", "Fiend", "Celestial", "Eternal",
)

CAPE_DEFINITIONS = {
    "peasant cloak": (5.0, 0.02, 1),
    "leather cloak": (5.0, 0.02, 1),
    "orange cloak": (10.0, 0.02, 1),
    "green cloak": (10.0, 0.02, 1),
    "knight cloak": (15.0, 0.02, 1),
    "royal cloak": (15.0, 0.02, 1),
    "druid cloak": (20.0, 0.02, 2),
    "frozen cloak": (20.0, 0.02, 2),
    "vampire cloak": (30.0, 0.02, 2),
    "fiend cloak": (30.0, 0.02, 2),
    "holy cloak": (50.0, 0.02, 2),
    "divine cloak": (50.0, 0.02, 2),
}

WING_DAMAGE_BASE = 9.0
WING_HEALTH_BASE = 30.0
WING_LEVEL_SCALER = 0.014999999664723873
WING_TIER_SCALER = 3.1622776985168457


@dataclass(frozen=True)
class CatalogMatch:
    name: str
    slot: EquipmentSlot
    confidence: float
    exact: bool


def normalize_item_name(value: str) -> str:
    value = normalize_text(value).lower()
    value = re.sub(r"(?:\\[|\\()\\s*(?:range|ranged|melee)\\s*(?:\\]|\\))", " ", value, flags=re.I)
    value = re.sub(
        r"^.*?\\bexp\\b[\\]\\)]?[\\s:+•·-]*(?:\\+?\\s*)?\\d{1,2}\\s*",
        "",
        value,
        count=1,
        flags=re.I,
    )
    value = re.sub(r"^\\s*[+•·]\\s*\\d{1,2}\\s+", "", value)
    return re.sub(r"[^a-z0-9_-]+", " ", value).strip()


def title_candidates(texts: Sequence[str]) -> list[str]:
    fragments: list[list[str]] = []
    for raw in texts:
        text = normalize_text(raw).strip()
        lowered = text.lower()
        if not text or PERCENT_RE.search(text) or LEVEL_RE.search(text):
            continue
        if re.match(r"^\\s*(?:damage|health)\\s+\\d", text, re.I):
            continue
        if lowered in {"x", "lock", "reroll", "reroll substats"}:
            continue

        normalized = normalize_item_name(text)
        variants: list[str] = []
        if normalized:
            variants.append(normalized)
        for rarity in RARITY_WORDS:
            prefix = rarity + " "
            if normalized.startswith(prefix) and len(normalized) > len(prefix):
                variants.append(normalized[len(prefix):].strip())
        if normalized in RARITY_WORDS:
            variants = []
        fragments.append(list(dict.fromkeys(variants)))

    candidates: list[str] = []
    for index, variants in enumerate(fragments):
        candidates.extend(variants)
        for length in (2, 3):
            if index + length > len(fragments):
                continue
            windows = fragments[index:index + length]
            if any(not window for window in windows):
                continue
            # The OCR review use-case only needs the first cleaned variant from
            # each physical line for joined titles such as "Crimson" + "Backpack".
            joined = " ".join(window[0] for window in windows).strip()
            if joined:
                candidates.append(joined)
    return list(dict.fromkeys(candidates))


def match_standard_item(
    texts: Sequence[str],
    primary_kind: str | None = None,
) -> CatalogMatch | None:
    allowed = _allowed_slots(primary_kind)
    catalog = [
        (name, EquipmentSlot(slot))
        for name, slot in _STANDARD_ITEM_SLOTS.items()
        if EquipmentSlot(slot) in allowed
    ]
    return _best_catalog_match(title_candidates(texts), catalog, threshold=0.82, margin=0.07)


def match_wing_name(texts: Sequence[str]) -> tuple[str, float] | None:
    catalog = [(normalize_item_name(name), name) for name in WING_NAMES]
    return _best_name_match(title_candidates(texts), catalog, threshold=0.82, margin=0.10)


def match_cape_name(texts: Sequence[str]) -> tuple[str, float] | None:
    catalog = [(name, _display_name(name)) for name in CAPE_DEFINITIONS]
    return _best_name_match(title_candidates(texts), catalog, threshold=0.82, margin=0.08)


def infer_wing_level(rarity_tier: int, damage: float | None, health: float | None) -> int | None:
    if damage is None and health is None:
        return None
    best_level = None
    best_error = float("inf")
    for level in range(1, 101):
        tier_factor = WING_TIER_SCALER ** (rarity_tier + 1)
        scale = 1.0 + WING_LEVEL_SCALER * level
        predicted_damage = WING_DAMAGE_BASE * tier_factor * scale
        predicted_health = WING_HEALTH_BASE * tier_factor * scale
        errors = []
        if damage is not None:
            errors.append(abs(predicted_damage - damage) / max(predicted_damage, damage, 1.0))
        if health is not None:
            errors.append(abs(predicted_health - health) / max(predicted_health, health, 1.0))
        error = max(errors)
        if error < best_error:
            best_error = error
            best_level = level
    # UI values are abbreviated to K/M with two decimals. 1% leaves generous
    # room for display rounding while still making the integer level unique.
    return best_level if best_error <= 0.01 else None


def expected_wing_primaries(rarity_tier: int, level: int) -> tuple[float, float]:
    tier_factor = WING_TIER_SCALER ** (rarity_tier + 1)
    scale = 1.0 + WING_LEVEL_SCALER * level
    return WING_DAMAGE_BASE * tier_factor * scale, WING_HEALTH_BASE * tier_factor * scale


def infer_cape_level(name: str, intrinsic_value: float | None) -> int | None:
    definition = CAPE_DEFINITIONS.get(normalize_item_name(name))
    if definition is None or intrinsic_value is None:
        return None
    base, scaler, _ = definition
    best = min(
        range(1, 101),
        key=lambda level: abs(cape_intrinsic_value(name, level) - intrinsic_value),
    )
    return best if abs(cape_intrinsic_value(name, best) - intrinsic_value) <= 0.25 else None


def cape_intrinsic_value(name: str, level: int) -> float:
    definition = CAPE_DEFINITIONS[normalize_item_name(name)]
    base, scaler, _ = definition
    return base * (1.0 + scaler * (level - 1))


def cape_affix_count(name: str) -> int | None:
    definition = CAPE_DEFINITIONS.get(normalize_item_name(name))
    return definition[2] if definition else None


def _allowed_slots(primary_kind: str | None) -> frozenset[EquipmentSlot]:
    if primary_kind == "damage":
        return frozenset({EquipmentSlot.WEAPON, EquipmentSlot.GLOVES, EquipmentSlot.RING})
    if primary_kind == "health":
        return frozenset({EquipmentSlot.HELMET, EquipmentSlot.BACKPACK, EquipmentSlot.NECKLACE})
    return frozenset({
        EquipmentSlot.WEAPON,
        EquipmentSlot.HELMET,
        EquipmentSlot.BACKPACK,
        EquipmentSlot.GLOVES,
        EquipmentSlot.NECKLACE,
        EquipmentSlot.RING,
    })


def _best_catalog_match(
    candidates: Sequence[str],
    catalog: Sequence[tuple[str, EquipmentSlot]],
    *,
    threshold: float,
    margin: float,
) -> CatalogMatch | None:
    exact = [
        (candidate, name, slot)
        for candidate in candidates
        for name, slot in catalog
        if candidate == name
    ]
    if exact:
        _, name, slot = exact[0]
        return CatalogMatch(_display_name(name), slot, 1.0, True)

    best_by_slot: dict[EquipmentSlot, tuple[float, str]] = {}
    for candidate in candidates:
        for name, slot in catalog:
            score = _similarity(candidate, name)
            current = best_by_slot.get(slot)
            if current is None or score > current[0]:
                best_by_slot[slot] = (score, name)
    if not best_by_slot:
        return None

    ranked = sorted(
        ((score, name, slot) for slot, (score, name) in best_by_slot.items()),
        reverse=True,
    )
    best_score, best_name, best_slot = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score < threshold or best_score - second_score < margin:
        return None
    return CatalogMatch(_display_name(best_name), best_slot, best_score, False)


def _best_name_match(
    candidates: Sequence[str],
    catalog: Sequence[tuple[str, str]],
    *,
    threshold: float,
    margin: float,
) -> tuple[str, float] | None:
    scored: list[tuple[float, str]] = []
    for candidate in candidates:
        for normalized, display in catalog:
            scored.append((_similarity(candidate, normalized), display))
    if not scored:
        return None
    scored.sort(reverse=True)
    best_score, best_name = scored[0]
    second_score = next(
        (score for score, name in scored[1:] if name != best_name),
        0.0,
    )
    if best_score < threshold or best_score - second_score < margin:
        return None
    return best_name, best_score


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if len(right) >= 5 and right in left:
        return max(0.94, len(right) / max(len(left), 1))
    if len(left) >= 5 and left in right:
        return max(0.90, len(left) / max(len(right), 1))
    return difflib.SequenceMatcher(None, left, right).ratio()


def _display_name(normalized: str) -> str:
    return " ".join(
        token if token.startswith("scifi_") else token.capitalize()
        for token in normalized.split()
    )
