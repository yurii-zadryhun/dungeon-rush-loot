from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

from .domain import Action, Comparison, EquipmentSlot, OcrSpan, ParsedItem
from .equipment import EquipmentLoadout


@runtime_checkable
class ScreenCapturePort(Protocol):
    def screenshot(self) -> Any: ...


@runtime_checkable
class ForegroundPort(Protocol):
    def foreground_package(self) -> str | None: ...


@runtime_checkable
class OcrPort(Protocol):
    def recognize(self, image: Any) -> Sequence[OcrSpan]: ...


@runtime_checkable
class TouchPort(Protocol):
    def touch(self, action: Action, screen_size: tuple[int, int]): ...


@runtime_checkable
class EquipmentRepositoryPort(Protocol):
    def snapshot(self) -> EquipmentLoadout: ...

    def replace(self, slot: EquipmentSlot, item: ParsedItem) -> None: ...


@runtime_checkable
class DecisionLogPort(Protocol):
    def append(self, comparison: Comparison, *, source: str) -> None: ...
