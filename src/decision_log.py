from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .domain import Comparison
from .events import comparison_event


class JsonlDecisionLog:
    """Append-only structured log shared by desktop tooling and Android UI semantics."""

    def __init__(self, path: Path, strategy: str | None = None) -> None:
        self.path = path
        self.strategy = strategy
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def start_session(
        cls,
        output_dir: Path,
        strategy: str | None = None,
        *,
        started_at: datetime | None = None,
    ) -> "JsonlDecisionLog":
        """Reserve a unique timestamped file for each desktop watcher run.

        Timestamp is local time at start, not at each decision. Exclusive
        creation avoids appending a later session to another session's log,
        even when two runs start within the same second.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = (started_at or datetime.now().astimezone()).strftime("%Y%m%d-%H%M%S")
        suffix = 1
        while True:
            name = f"decisions-{stamp}" + (f"-{suffix}" if suffix > 1 else "") + ".jsonl"
            path = output_dir / name
            try:
                with path.open("x", encoding="utf-8"):
                    pass
            except FileExistsError:
                suffix += 1
                continue
            return cls(path, strategy)

    def append(self, comparison: Comparison, *, source: str = "desktop", ocr_lines=(),
               rarity_level_passes=(), rarity_level_annotated_image: Path | None = None) -> None:
        event = comparison_event(
            comparison,
            source=source,
            strategy=self.strategy,
            ocr_lines=ocr_lines,
        )
        event["rarity_level_passes"] = [
            {
                "kind": diagnostic.kind,
                "crop": asdict(diagnostic.crop),
                "scale": diagnostic.scale,
                "coordinate_space": "screenshot_pixels",
                "ocr_lines": [asdict(line) for line in diagnostic.lines],
            }
            for diagnostic in rarity_level_passes
        ]
        event["rarity_level_annotated_image"] = (
            str(rarity_level_annotated_image) if rarity_level_annotated_image is not None else None
        )
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
