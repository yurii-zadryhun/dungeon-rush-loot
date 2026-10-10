from __future__ import annotations

import json
from pathlib import Path

from .domain import Comparison
from .events import comparison_event


class JsonlDecisionLog:
    """Append-only structured log shared by desktop tooling and Android UI semantics."""

    def __init__(self, path: Path, strategy: str | None = None) -> None:
        self.path = path
        self.strategy = strategy
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, comparison: Comparison, *, source: str = "desktop", ocr_lines=()) -> None:
        event = comparison_event(
            comparison,
            source=source,
            strategy=self.strategy,
            ocr_lines=ocr_lines,
        )
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
