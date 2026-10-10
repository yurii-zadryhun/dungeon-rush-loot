from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Protocol

from .config import MAX_ITEM_LEVEL, MAX_STATS, MIN_STATS, RARITY_TIERS, SKILLS
from .affix_rules import has_exp_marker, validate_affixes
from .domain import EquipmentSlot, ParsedItem, ParsedStat
from .text import canonical_name
from .game_catalog import match_standard_item


class EquipmentStateError(RuntimeError):
    pass


STANDARD_SLOTS = frozenset({
    EquipmentSlot.WEAPON,
    EquipmentSlot.HELMET,
    EquipmentSlot.BACKPACK,
    EquipmentSlot.GLOVES,
    EquipmentSlot.NECKLACE,
    EquipmentSlot.RING,
})


def affix_bounds(slot: EquipmentSlot) -> tuple[int, int]:
    return MIN_STATS, MAX_STATS


def beneficial_value(name: str, value: float) -> float:
    # Both are beneficial reductions displayed as negative percentages.
    return abs(value) if canonical_name(name) in {
        "critical damage taken", "companion cooldown"
    } else max(0.0, value)


def item_identity(item: ParsedItem) -> tuple:
    stats = tuple(
        sorted(
            (canonical_name(stat.name), round(beneficial_value(stat.name, stat.value), 2))
            for stat in item.stats
        )
    )
    intrinsic = tuple(
        sorted(
            (canonical_name(stat.name), round(beneficial_value(stat.name, stat.value), 2))
            for stat in item.intrinsic_stats
        )
    )
    return (
        item.tier,
        item.level,
        has_exp_marker(item.title),
        stats,
        intrinsic,
        round(item.primary_attack or 0.0, 2),
        round(item.primary_health or 0.0, 2),
    )


class EquipmentLoadout:
    def __init__(self, items: Mapping[EquipmentSlot, ParsedItem]) -> None:
        missing = set(EquipmentSlot) - set(items)
        extra = set(items) - set(EquipmentSlot)
        if missing or extra:
            raise EquipmentStateError(
                "Equipment must contain exactly eight tracked slots; "
                f"missing={sorted(slot.value for slot in missing)}, "
                f"extra={sorted(str(slot) for slot in extra)}."
            )
        self._items = dict(items)

    @property
    def items(self) -> Mapping[EquipmentSlot, ParsedItem]:
        return MappingProxyType(self._items)

    def __iter__(self):
        return iter(self._items.items())

    def item(self, slot: EquipmentSlot) -> ParsedItem:
        return self._items[slot]

    def slot_of(self, item: ParsedItem) -> EquipmentSlot:
        identity = item_identity(item)
        matches = [slot for slot, equipped in self._items.items() if item_identity(equipped) == identity]
        if not matches:
            raise EquipmentStateError(
                "The OCR-equipped item is not present in configured equipment. "
                "Update the initial equipment state before running the watcher."
            )
        if len(matches) > 1:
            # Low-rarity gear with 2 common affixes often has identical numeric
            # identities in several slots. The known APK item-name catalog
            # supplies the slot, but only if its numeric identity also matches.
            catalog_match = match_standard_item([item.title])
            if catalog_match is not None and catalog_match.slot in matches:
                return catalog_match.slot
            raise EquipmentStateError(
                "The OCR-equipped item matches more than one configured slot "
                "and the catalog could not disambiguate it."
            )
        return matches[0]

    def with_replacement(self, slot: EquipmentSlot, item: ParsedItem) -> "EquipmentLoadout":
        items = dict(self._items)
        items[slot] = item
        return EquipmentLoadout(items)

    def without_affixes(self, slot: EquipmentSlot) -> "EquipmentLoadout":
        stripped = replace(self._items[slot], stats=())
        return self.with_replacement(slot, stripped)


class EquipmentRepository(Protocol):
    def snapshot(self) -> EquipmentLoadout: ...

    def replace(self, slot: EquipmentSlot, item: ParsedItem) -> None: ...


class EquipmentCodec:
    @staticmethod
    def loads_json(raw: str) -> EquipmentLoadout:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EquipmentStateError(f"Invalid equipment JSON: {exc}") from exc
        return EquipmentCodec.from_payload(payload)

    @staticmethod
    def dumps_json(loadout: EquipmentLoadout, *, indent: int | None = None) -> str:
        return json.dumps(
            EquipmentCodec.to_payload(loadout),
            ensure_ascii=False,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
        )

    @staticmethod
    def from_payload(payload) -> EquipmentLoadout:
        if not isinstance(payload, dict):
            raise EquipmentStateError("Equipment state must be a JSON object keyed by equipment slot.")
        items: dict[EquipmentSlot, ParsedItem] = {}
        for raw_slot, raw_item in payload.items():
            try:
                slot = EquipmentSlot(raw_slot)
            except ValueError as exc:
                raise EquipmentStateError(f"Unknown equipment slot: {raw_slot!r}") from exc
            items[slot] = EquipmentCodec.parse_item(slot, raw_item)
        return EquipmentLoadout(items)

    @staticmethod
    def to_payload(loadout: EquipmentLoadout) -> dict:
        return {
            slot.value: EquipmentCodec.serialize_item(item)
            for slot, item in sorted(loadout.items.items(), key=lambda pair: pair[0].value)
        }

    @staticmethod
    def parse_item(slot: EquipmentSlot, raw_item) -> ParsedItem:
        if not isinstance(raw_item, dict):
            raise EquipmentStateError(f"Slot {slot.value!r} must contain a JSON object.")
        rarity = str(raw_item.get("rarity", "")).strip().lower()
        if rarity not in RARITY_TIERS:
            raise EquipmentStateError(f"Slot {slot.value!r} has unknown rarity: {raw_item.get('rarity')!r}")
        try:
            level = int(raw_item["level"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EquipmentStateError(f"Slot {slot.value!r} requires an integer level.") from exc
        if not 1 <= level <= MAX_ITEM_LEVEL:
            raise EquipmentStateError(
                f"Slot {slot.value!r} level must be between 1 and {MAX_ITEM_LEVEL}; got {level}."
            )

        raw_stats = raw_item.get("stats")
        if not isinstance(raw_stats, dict):
            raise EquipmentStateError(f"Slot {slot.value!r} requires a stats object.")
        minimum, maximum = affix_bounds(slot)
        if not minimum <= len(raw_stats) <= maximum:
            expected = str(minimum) if minimum == maximum else f"{minimum}-{maximum}"
            raise EquipmentStateError(
                f"Slot {slot.value!r} requires {expected} affixes; got {len(raw_stats)}."
            )
        stats = tuple(EquipmentCodec.parse_stat(slot, name, value) for name, value in raw_stats.items())
        title = str(raw_item.get("title") or f"{rarity.title()} {slot.value.title()}")
        # A missing title in a new payload cannot safely claim [EXP] status;
        # older imports that dropped this tag must be re-imported.
        affix_error = validate_affixes(title, stats, minimum=minimum, maximum=maximum)
        if affix_error:
            raise EquipmentStateError(f"Slot {slot.value!r}: {affix_error}")

        intrinsic_raw = raw_item.get("intrinsic_stats", {})
        if not isinstance(intrinsic_raw, dict):
            raise EquipmentStateError(f"Slot {slot.value!r} intrinsic_stats must be an object.")
        intrinsic_stats = tuple(
            EquipmentCodec.parse_stat(slot, name, value)
            for name, value in intrinsic_raw.items()
        )

        primary = raw_item.get("primary", {})
        if not isinstance(primary, dict):
            raise EquipmentStateError(f"Slot {slot.value!r} primary must be an object.")
        primary_attack = EquipmentCodec._optional_number(primary.get("attack"), slot, "primary.attack")
        primary_health = EquipmentCodec._optional_number(primary.get("health"), slot, "primary.health")

        if slot is EquipmentSlot.WINGS and (not primary_attack or not primary_health):
            raise EquipmentStateError("Wings require positive primary.attack and primary.health values.")
        if slot is EquipmentSlot.CAPE:
            intrinsic_names = {canonical_name(stat.name) for stat in intrinsic_stats}
            if not {"damage", "health"}.issubset(intrinsic_names):
                raise EquipmentStateError("Cape requires intrinsic Damage and Health values.")

        return ParsedItem(
            title=title,
            rarity=rarity.title(),
            tier=RARITY_TIERS[rarity],
            level=level,
            stats=stats,
            raw_lines=(),
            average_ocr_confidence=1.0,
            melee=False,
            primary_attack=primary_attack,
            primary_health=primary_health,
            intrinsic_stats=intrinsic_stats,
        )

    @staticmethod
    def parse_stat(slot: EquipmentSlot, raw_name: str, raw_value) -> ParsedStat:
        name = canonical_name(str(raw_name))
        if name not in SKILLS:
            raise EquipmentStateError(f"Slot {slot.value!r} has unknown stat: {raw_name!r}")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise EquipmentStateError(
                f"Slot {slot.value!r} stat {raw_name!r} must be numeric."
            ) from exc
        return ParsedStat(name, value, f"{value:+.2f}% {name}", 1.0)

    @staticmethod
    def _optional_number(raw_value, slot: EquipmentSlot, field: str) -> float | None:
        if raw_value is None:
            return None
        try:
            return float(raw_value)
        except (TypeError, ValueError) as exc:
            raise EquipmentStateError(f"Slot {slot.value!r} {field} must be numeric.") from exc

    @staticmethod
    def serialize_item(item: ParsedItem) -> dict:
        payload = {
            "title": item.title,
            "rarity": item.rarity,
            "level": item.level,
            "stats": {canonical_name(stat.name): stat.value for stat in item.stats},
        }
        if item.primary_attack is not None or item.primary_health is not None:
            payload["primary"] = {
                "attack": item.primary_attack,
                "health": item.primary_health,
            }
        if item.intrinsic_stats:
            payload["intrinsic_stats"] = {
                canonical_name(stat.name): stat.value for stat in item.intrinsic_stats
            }
        return payload


class InMemoryEquipmentRepository:
    def __init__(self, loadout: EquipmentLoadout) -> None:
        self._loadout = loadout

    def snapshot(self) -> EquipmentLoadout:
        return self._loadout

    def replace(self, slot: EquipmentSlot, item: ParsedItem) -> None:
        self._loadout = self._loadout.with_replacement(slot, item)


class JsonEquipmentRepository:
    """Desktop file adapter. The build/scoring domain depends only on EquipmentRepository."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._loadout = self._load(path)

    def snapshot(self) -> EquipmentLoadout:
        return self._loadout

    def replace(self, slot: EquipmentSlot, item: ParsedItem) -> None:
        updated = self._loadout.with_replacement(slot, item)
        self._persist(updated)
        self._loadout = updated

    @staticmethod
    def _load(path: Path) -> EquipmentLoadout:
        if not path.exists():
            raise EquipmentStateError(
                f"Equipment state file does not exist: {path}. "
                "Copy equipment.example.json, fill the eight current items, and retry."
            )
        try:
            return EquipmentCodec.loads_json(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise EquipmentStateError(f"Could not read equipment state from {path}: {exc}") from exc

    def _persist(self, loadout: EquipmentLoadout) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(EquipmentCodec.dumps_json(loadout, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
