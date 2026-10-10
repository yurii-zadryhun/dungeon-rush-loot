from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageDraw

from .domain import AnalysisArtifacts
from .presentation import ComparisonFormatter


class ArtifactWriter:
    def __init__(self, output_dir: Path, annotate: bool = True) -> None:
        self.output_dir = output_dir
        self.annotate_enabled = annotate
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, image: Image.Image, artifacts: AnalysisArtifacts, scale: float) -> None:
        image.save(self.output_dir / "captured.png", format="PNG")
        (self.output_dir / "comparison.json").write_text(json.dumps(asdict(artifacts.comparison), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        if self.annotate_enabled:
            self._annotate(image, artifacts, scale)

    def _annotate(self, source: Image.Image, artifacts: AnalysisArtifacts, scale: float) -> None:
        image = source.convert("RGB").copy()
        draw = ImageDraw.Draw(image)
        left, top, _, _ = artifacts.popup_box
        for line in artifacts.popup_lines:
            box = line.box.shifted_scaled(left, top, scale)
            draw.rectangle((box.left, box.top, box.right, box.bottom), outline=(255, 200, 0), width=1)
        draw.rectangle(artifacts.popup_box, outline=(0, 210, 255), width=3)
        draw.text((16, 16), str(ComparisonFormatter.summary(artifacts.comparison, verbose=True)), fill=(255, 255, 255))
        image.save(self.output_dir / "annotated.jpg", quality=95)
