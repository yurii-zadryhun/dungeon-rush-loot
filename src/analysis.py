from __future__ import annotations

from PIL import Image

from .core import LootDecisionEngine
from .domain import AnalysisArtifacts
from .ocr import PaddleOcrEngine
from .scoring import ItemComparer
from .vision import fixed_ocr_crop, preprocess_popup


class LootAnalyzer:
    """Desktop adapter composition: screenshot crop + Paddle OCR around the shared decision engine."""

    def __init__(self, engine: PaddleOcrEngine, comparer: ItemComparer, scale: float = 2.0, show_ocr: bool = False) -> None:
        self.engine = engine
        self.decision_engine = LootDecisionEngine(comparer)
        self.scale = scale
        self.show_ocr = show_ocr

    def analyze(self, image: Image.Image) -> AnalysisArtifacts:
        popup_box, spans = self._ocr_popup(image.convert("RGB"))
        result = self.decision_engine.decide_spans(spans)
        if self.show_ocr:
            self._print_ocr(result.popup_lines)
        return AnalysisArtifacts(
            result.comparison,
            popup_box,
            result.popup_lines,
            result.equipped_lines,
            result.candidate_lines,
        )

    def _ocr_popup(self, image: Image.Image):
        popup_box = fixed_ocr_crop(image.width, image.height)
        spans = self.engine.recognize(preprocess_popup(image.crop(popup_box), self.scale))
        return popup_box, spans

    @staticmethod
    def _print_ocr(lines) -> None:
        print("\nOCR lines:")
        for line in lines:
            print(f"  y={line.box.center_y:7.1f} conf={line.score:5.1%}  {line.text}")
