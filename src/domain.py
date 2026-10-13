from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class Action(str, Enum):
    EQUIP = "equip"
    SELL = "sell"
    CONFIRM_SELL = "confirm_sell"
    CHECK = "check"


class ComparisonStatus(str, Enum):
    OK = "ok"
    CHECK_OCR = "check_ocr"


class EquipmentSlot(str, Enum):
    WEAPON = "weapon"
    HELMET = "helmet"
    BACKPACK = "backpack"
    GLOVES = "gloves"
    NECKLACE = "necklace"
    RING = "ring"


class ScoringStrategy(str, Enum):
    UNIVERSAL = "universal"
    PVE = "pve"
    PVP = "pvp"


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
class BuildMetrics:
    base_attack: float
    base_health: float
    attack_progression: float
    health_progression: float
    stats: Mapping[str, float]
    # Values retained separately for the six replaceable [EXP] items.
    # Universal needs individual exceptional quality, not summed totals.
    equipment_rolls: Mapping[str, tuple[float, ...]] | None = None
    # Same-item normal affixes let us reward AS + Crit Damage together.
    item_affixes: Mapping[EquipmentSlot, Mapping[str, float]] | None = None


@dataclass(frozen=True)
class BuildStat:
    name: str
    raw: float
    effective: float

    @property
    def capped(self) -> bool:
        return self.effective + 1e-9 < self.raw


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    score: float


@dataclass(frozen=True)
class BuildScore:
    total: float
    combat: float
    flexibility: float
    base_attack: float
    base_health: float
    stats: tuple[BuildStat, ...]
    components: tuple[ScoreComponent, ...] = ()

    def stat(self, name: str) -> BuildStat | None:
        return next((stat for stat in self.stats if stat.name == name), None)


@dataclass(frozen=True)
class Comparison:
    status: ComparisonStatus
    action: Action
    candidate: ParsedItem | None
    equipped: ParsedItem | None
    candidate_score: BuildScore | None
    equipped_score: BuildScore | None
    message: str
    equipment_slot: EquipmentSlot | None = None
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
