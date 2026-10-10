from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .config import MAX_ITEM_LEVEL, MAX_STATS, MIN_STATS, RARITY_TIERS, SKILLS
from .domain import EquipmentSlot, ParsedItem, ParsedStat
from .text import canonical_name


class EquipmentStateError(RuntimeError):
    pass


def beneficial_value(name: str, value: float) -> float:
    return abs(value) if canonical_name(name) == "critical damage taken" else max(0.0, value)


def item_identity(item: ParsedItem) -> tuple[int | None, int | None, tuple[tuple[str, float], ...]]:
    stats = tuple(
        sorted(
            (canonical_name(stat.name), round(beneficial_value(stat.name, stat.value), 2))
            for stat in item.stats
        )
    )
    return item.tier, item.level, stats


class EquipmentLoadout:
    def __init__(self, items: Mapping[EquipmentSlot, ParsedItem]) -> None:
        missing = set(EquipmentSlot) - set(items)
        extra = set(items) - set(EquipmentSlot)
        if missing or extra:
            raise EquipmentStateError(
                "Equipment must contain exactly six tracked slots; "
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
                "The OCR-equipped item is not present in equipment.json. "
                "Update the initial equipment state before running the watcher."
            )
        if len(matches) > 1:
            raise EquipmentStateError(
                "The OCR-equipped item matches more than one configured slot; "
                "make the manual equipment state unambiguous."
            )
        return matches[0]

    def with_replacement(self, slot: EquipmentSlot, item: ParsedItem) -> "EquipmentLoadout":
        items = dict(self._items)
        items[slot] = item
        return EquipmentLoadout(items)

    def without_affixes(self, slot: EquipmentSlot) -> "EquipmentLoadout":
        stripped = replace(self._items[slot], stats=())
        return self.with_replacement(slot, stripped)


class JsonEquipmentRepository:
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
                "Copy equipment.example.json, fill the six current items, and retry."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EquipmentStateError(f"Could not read equipment state from {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise EquipmentStateError("equipment.json must contain a JSON object keyed by equipment slot.")
        items: dict[EquipmentSlot, ParsedItem] = {}
        for raw_slot, raw_item in payload.items():
            try:
                slot = EquipmentSlot(raw_slot)
            except ValueError as exc:
                raise EquipmentStateError(f"Unknown equipment slot: {raw_slot!r}") from exc
            items[slot] = JsonEquipmentRepository._parse_item(slot, raw_item)
        return EquipmentLoadout(items)

    @staticmethod
    def _parse_item(slot: EquipmentSlot, raw_item) -> ParsedItem:
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
        if not MIN_STATS <= len(raw_stats) <= MAX_STATS:
            raise EquipmentStateError(
                f"Slot {slot.value!r} requires {MIN_STATS}-{MAX_STATS} stats; got {len(raw_stats)}."
            )
        stats = tuple(JsonEquipmentRepository._parse_stat(slot, name, value) for name, value in raw_stats.items())
        return ParsedItem(
            title=str(raw_item.get("title") or f"{rarity.title()} {slot.value.title()}"),
            rarity=rarity.title(),
            tier=RARITY_TIERS[rarity],
            level=level,
            stats=stats,
            raw_lines=(),
            average_ocr_confidence=1.0,
            melee=False,
        )

    @staticmethod
    def _parse_stat(slot: EquipmentSlot, raw_name: str, raw_value) -> ParsedStat:
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

    def _persist(self, loadout: EquipmentLoadout) -> None:
        payload = {
            slot.value: self._serialize_item(item)
            for slot, item in sorted(loadout.items.items(), key=lambda pair: pair[0].value)
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _serialize_item(item: ParsedItem) -> dict:
        return {
            "title": item.title,
            "rarity": item.rarity,
            "level": item.level,
            "stats": {canonical_name(stat.name): stat.value for stat in item.stats},
        }
