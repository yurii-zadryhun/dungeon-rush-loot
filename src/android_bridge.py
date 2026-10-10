from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .config import RARITY_TIERS, SKILLS, TARGET_PACKAGE
from .core import LootDecisionEngine
from .domain import Action, Box, Comparison, ComparisonStatus, EquipmentSlot, OcrSpan, ParsedItem, ParsedStat, ScoringStrategy
from .equipment import EquipmentCodec, EquipmentStateError, InMemoryEquipmentRepository
from .events import comparison_event
from .scoring import BuildScorer, ItemComparer
from .strategies import strategy_for
from .text import canonical_name
from .ui_geometry import LOOT_UI


def app_config_json() -> str:
    payload = {
        "schema": 1,
        "target_package": TARGET_PACKAGE,
        "crop": LOOT_UI.crop.to_dict(),
        "targets": {
            action.value: rect.to_dict()
            for action, rect in LOOT_UI.targets.items()
        },
        "rarities": [
            {"name": rarity.title(), "tier": tier}
            for rarity, tier in sorted(RARITY_TIERS.items(), key=lambda pair: pair[1])
        ],
        "skills": [
            {
                "name": name,
                "per_item_cap": rule.cap,
                "category": rule.category,
            }
            for name, rule in sorted(SKILLS.items())
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def validate_equipment_json(equipment_json: str) -> str:
    try:
        loadout = EquipmentCodec.loads_json(equipment_json)
        return json.dumps(
            {
                "valid": True,
                "normalized": EquipmentCodec.to_payload(loadout),
                "error": None,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except EquipmentStateError as exc:
        return json.dumps(
            {"valid": False, "normalized": None, "error": str(exc)},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def evaluate_spans_json(spans_json: str, equipment_json: str, strategy_name: str) -> str:
    strategy = ScoringStrategy(strategy_name)
    try:
        loadout = EquipmentCodec.loads_json(equipment_json)
        repository = InMemoryEquipmentRepository(loadout)
        comparer = ItemComparer(repository, BuildScorer(strategy_for(strategy)))
        result = LootDecisionEngine(comparer).decide_spans(_parse_spans(spans_json))
        event = comparison_event(
            result.comparison,
            source="android",
            strategy=strategy.value,
            ocr_lines=result.popup_lines,
        )
        _enrich_android_event(event, result.comparison)
        return json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        comparison = Comparison(
            status=ComparisonStatus.CHECK_OCR,
            action=Action.CHECK,
            candidate=None,
            equipped=None,
            candidate_score=None,
            equipped_score=None,
            message=f"{type(exc).__name__}: {exc}",
        )
        event = comparison_event(comparison, source="android", strategy=strategy.value)
        _enrich_android_event(event, comparison)
        return json.dumps(event, ensure_ascii=False, separators=(",", ":"))


def replace_equipment_json(equipment_json: str, slot_name: str, candidate_json: str) -> str:
    loadout = EquipmentCodec.loads_json(equipment_json)
    slot = EquipmentSlot(slot_name)
    candidate = _item_from_event(json.loads(candidate_json))
    updated = loadout.with_replacement(slot, candidate)
    return EquipmentCodec.dumps_json(updated)


def _parse_spans(raw: str) -> list[OcrSpan]:
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("OCR payload must be a list of spans.")
    spans = []
    for row in payload:
        box = row["box"]
        spans.append(
            OcrSpan(
                text=str(row["text"]),
                score=float(row.get("score", 1.0)),
                box=Box(
                    float(box["left"]),
                    float(box["top"]),
                    float(box["right"]),
                    float(box["bottom"]),
                ),
            )
        )
    return spans


def _item_from_event(payload: dict[str, Any]) -> ParsedItem:
    rarity = payload.get("rarity")
    tier = payload.get("tier")
    level = payload.get("level")
    stats = tuple(
        ParsedStat(
            name=canonical_name(str(stat["name"])),
            value=float(stat["value"]),
            raw_text=str(stat.get("raw_text", "")),
            confidence=float(stat.get("confidence", 1.0)),
        )
        for stat in payload.get("stats", [])
    )
    return ParsedItem(
        title=str(payload.get("title", "")),
        rarity=str(rarity) if rarity is not None else None,
        tier=int(tier) if tier is not None else None,
        level=int(level) if level is not None else None,
        stats=stats,
        raw_lines=(),
        average_ocr_confidence=float(payload.get("average_ocr_confidence", 1.0)),
        melee=bool(payload.get("melee", False)),
    )


def _enrich_android_event(event: dict[str, Any], comparison: Comparison) -> None:
    target = LOOT_UI.targets.get(comparison.action)
    event["touch_target"] = target.to_dict() if target else None
    event["needs_sell_confirmation"] = bool(
        comparison.action is Action.SELL
        and comparison.equipped is not None
        and comparison.candidate is not None
        and comparison.equipped.tier == 8
        and comparison.candidate.tier == 9
    )
    event["confirm_sell_target"] = LOOT_UI.target(Action.CONFIRM_SELL).to_dict()
