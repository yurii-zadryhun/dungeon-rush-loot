from __future__ import annotations

from PIL import Image

from .core import DecisionResult, LootDecisionEngine
from .domain import Action, AnalysisArtifacts, Box, Comparison, ComparisonStatus, OcrPass, OcrSpan
from .ocr import PaddleOcrEngine
from .parsing import LootCardTitleCountError
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
        popup_box, spans, raw = self._ocr_popup(image.convert("RGB"))
        lines = tuple(self.decision_engine.lines.assemble(spans))
        try:
            result = self.decision_engine.decide_lines(lines)
        except LootCardTitleCountError:
            raise
        except ValueError as exc:
            comparison = Comparison(ComparisonStatus.CHECK_OCR, Action.CHECK, None, None, None, None, str(exc))
            result = DecisionResult(comparison, lines, (), ())
        left, top, _, _ = popup_box
        diagnostic = OcrPass(
            "popup", Box(*popup_box), self.scale,
            tuple(OcrSpan(span.text, span.score, span.box.shifted_scaled(left, top, self.scale)) for span in raw),
        )
        if self.show_ocr:
            self._print_ocr(result.popup_lines)
        return AnalysisArtifacts(
            result.comparison,
            popup_box,
            result.popup_lines,
            result.equipped_lines,
            result.candidate_lines,
            (diagnostic,),
        )

    def _ocr_popup(self, image: Image.Image):
        popup_box = fixed_ocr_crop(image.width, image.height)
        spans, raw = self.engine.recognize_with_diagnostics(preprocess_popup(image.crop(popup_box), self.scale))
        return popup_box, spans, raw

    @staticmethod
    def _print_ocr(lines) -> None:
        print("\nOCR lines:")
        for line in lines:
            print(f"  y={line.box.center_y:7.1f} conf={line.score:5.1%}  {line.text}")
