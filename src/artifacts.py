from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageDraw

from .domain import AnalysisArtifacts
from .presentation import ComparisonFormatter
from .text import LEVEL_RE, parse_rarity


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
            self._annotate_rarity_level(image, artifacts)

    def rarity_level_image_path(self, artifacts: AnalysisArtifacts) -> Path | None:
        if self.annotate_enabled and artifacts.rarity_level_passes:
            return self.output_dir / "rarity-level-annotated.jpg"
        return None

    def _annotate_rarity_level(self, source: Image.Image, artifacts: AnalysisArtifacts) -> None:
        path = self.rarity_level_image_path(artifacts)
        if path is None:
            return
        image = source.convert("RGB").copy()
        draw = ImageDraw.Draw(image)
        draw.text((16, 16), "Rarity / level OCR: cyan=rarity, yellow=level, gray=other raw text", fill="white")
        for index, diagnostic in enumerate(artifacts.rarity_level_passes, start=1):
            crop = diagnostic.crop
            draw.rectangle((crop.left, crop.top, crop.right, crop.bottom), outline=(0, 210, 255), width=2)
            draw.text((crop.left, max(0, crop.top - 16)),
                      f"{index}: {diagnostic.kind} {diagnostic.scale:g}x ({len(diagnostic.lines)} raw lines)", fill="white")
            for line in diagnostic.lines:
                color = (0, 210, 255) if parse_rarity(line.text)[0] else (
                    (255, 200, 0) if LEVEL_RE.search(line.text) else (180, 180, 180)
                )
                box = line.box
                draw.rectangle((box.left, box.top, box.right, box.bottom), outline=color, width=2)
                label = f"{line.text} ({line.score:.1%})"
                width = draw.textbbox((0, 0), label)[2]
                draw.text((max(0, min(box.right + 4, image.width - width)), box.top), label, fill=color)
        image.save(path, quality=95)

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
