"""One small OCR crop to quickly discard weak-Exceptional candidates.

Fast path: OCR candidate footer; parse stats; sum useful exceptional rolls as
fractions of their per-affix caps. Under 90% => SELL. Otherwise normal shared
full comparison. No color, rarity, hash or second-item checks in this probe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image

from .config import EXCEPTIONAL_SKILLS
from .exceptional_gate import MIN_PROMISING_CAP_FRACTION, useful_exceptional_fraction
from .domain import OcrLine, OcrSpan, ParsedStat
from .parsing import LootItemParser, OcrLineAssembler
from .ui_geometry import LOOT_EXCEPTIONAL_CROP
from .vision import preprocess_popup

if TYPE_CHECKING:
    from .ocr import PaddleOcrEngine


@dataclass(frozen=True)
class FastSellEvidence:
    stats: tuple[ParsedStat, ...]
    cap_fraction: float
    ocr_lines: tuple[OcrLine, ...]
    crop: tuple[int, int, int, int]


class FastExceptionalSellProbe:
    def __init__(self, engine: PaddleOcrEngine, scale: float = 2.0) -> None:
        self.engine = engine
        self.scale = scale
        self.parser = LootItemParser()
        self.assembler = OcrLineAssembler()

    def probe(self, image: Image.Image) -> FastSellEvidence | None:
        crop = LOOT_EXCEPTIONAL_CROP.pixels(image.size)
        spans = self.engine.recognize(
            preprocess_popup(image.crop(crop), self.scale)
        )
        left, top, _, _ = crop
        lines = tuple(self.assembler.assemble([
            OcrSpan(span.text, span.score,
                    span.box.shifted_scaled(left, top, self.scale))
            for span in spans
        ]))
        # No OCR text/stat => nothing to decide in the shortcut.
        stats = tuple(self.parser._stats(lines))
        if not stats:
            return None
        exceptional = tuple(
            stat for stat in stats if stat.name in EXCEPTIONAL_SKILLS
        )
        ratio = useful_exceptional_fraction(exceptional)
        if ratio >= MIN_PROMISING_CAP_FRACTION:
            return None
        return FastSellEvidence(exceptional, ratio, lines, crop)
