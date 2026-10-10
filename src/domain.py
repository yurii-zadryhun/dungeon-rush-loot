from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    EQUIP = "equip"
    SELL = "sell"
    CONFIRM_SELL = "confirm_sell"
    CHECK = "check"


class ComparisonStatus(str, Enum):
    OK = "ok"
    CHECK_OCR = "check_ocr"


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0

    def shifted_scaled(self, offset_x: float, offset_y: float, scale: float) -> "Box":
        return Box(
            offset_x + self.left / scale,
            offset_y + self.top / scale,
            offset_x + self.right / scale,
            offset_y + self.bottom / scale,
        )


@dataclass(frozen=True)
class OcrSpan:
    text: str
    score: float
    box: Box


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    box: Box
    spans: tuple[OcrSpan, ...] = ()


@dataclass(frozen=True)
class ParsedStat:
    name: str
    value: float
    raw_text: str
    confidence: float


@dataclass(frozen=True)
class ParsedItem:
    title: str
    rarity: str | None
    tier: int | None
    level: int | None
    stats: tuple[ParsedStat, ...]
    raw_lines: tuple[str, ...]
    average_ocr_confidence: float
    melee: bool = False


@dataclass(frozen=True)
class ScoreContribution:
    name: str
    value: float
    contribution: float


@dataclass(frozen=True)
class ItemScore:
    total: float
    affixes: float
    base_power: float
    details: tuple[ScoreContribution, ...]
    unknown: tuple[str, ...] = ()


@dataclass(frozen=True)
class Comparison:
    status: ComparisonStatus
    action: Action
    candidate: ParsedItem | None
    equipped: ParsedItem | None
    candidate_score: ItemScore | None
    equipped_score: ItemScore | None
    message: str
    rejection_reason: str | None = None

    @property
    def candidate_wins(self) -> bool:
        return self.action is Action.EQUIP

    @property
    def rejected(self) -> bool:
        return self.rejection_reason is not None


@dataclass(frozen=True)
class AnalysisArtifacts:
    comparison: Comparison
    popup_box: tuple[int, int, int, int]
    popup_lines: tuple[OcrLine, ...]
    equipped_lines: tuple[OcrLine, ...]
    candidate_lines: tuple[OcrLine, ...]


@dataclass(frozen=True)
class ModeOutcome:
    consume_candidate: bool
    touched: bool = False
    message: str | None = None


@dataclass
class WatchState:
    last_success_region: tuple[int, int, int, int] | None = None
    last_success_signature: bytes | None = None
    last_success_signature_at: float = 0.0
    last_candidate_hash: str | None = None
    last_candidate_hash_at: float = 0.0
    last_error_key: str | None = None
    last_error_at: float = 0.0
    foreground: bool | None = None

    def reset_visual_gate(self) -> None:
        self.last_success_region = None
        self.last_success_signature = None
        self.last_success_signature_at = 0.0

    def reset_candidate_hash(self) -> None:
        self.last_candidate_hash = None
        self.last_candidate_hash_at = 0.0
