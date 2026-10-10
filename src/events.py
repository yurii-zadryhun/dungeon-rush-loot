from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Sequence

from .domain import BuildScore, Comparison, OcrLine, ParsedItem


def _score_payload(score: BuildScore | None) -> dict[str, Any] | None:
    if score is None:
        return None
    return {
        "total": score.total,
        "combat": score.combat,
        "flexibility": score.flexibility,
        "base_attack": score.base_attack,
        "base_health": score.base_health,
        "stats": [asdict(stat) for stat in score.stats],
        "components": [asdict(component) for component in score.components],
    }


def item_payload(item: ParsedItem | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "title": item.title,
        "rarity": item.rarity,
        "tier": item.tier,
        "level": item.level,
        "stats": [asdict(stat) for stat in item.stats],
        "intrinsic_stats": [asdict(stat) for stat in item.intrinsic_stats],
        "primary_attack": item.primary_attack,
        "primary_health": item.primary_health,
        "average_ocr_confidence": item.average_ocr_confidence,
        "melee": item.melee,
    }


def comparison_event(
    comparison: Comparison,
    *,
    source: str,
    strategy: str | None = None,
    ocr_lines: Sequence[OcrLine] = (),
) -> dict[str, Any]:
    return {
        "schema": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "strategy": strategy,
        "status": comparison.status.value,
        "action": comparison.action.value,
        "slot": comparison.equipment_slot.value if comparison.equipment_slot else None,
        "message": comparison.message,
        "rejection_reason": comparison.rejection_reason,
        "equipped": item_payload(comparison.equipped),
        "candidate": item_payload(comparison.candidate),
        "equipped_score": _score_payload(comparison.equipped_score),
        "candidate_score": _score_payload(comparison.candidate_score),
        "ocr_lines": [
            {
                "text": line.text,
                "score": line.score,
                "box": asdict(line.box),
            }
            for line in ocr_lines
        ],
    }
