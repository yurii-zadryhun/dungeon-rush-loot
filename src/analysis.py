from __future__ import annotations

from PIL import Image

from .core import DecisionResult, LootDecisionEngine
from .domain import Action, AnalysisArtifacts, Box, Comparison, ComparisonStatus, OcrPass, OcrSpan
from .ocr import PaddleOcrEngine
from .parsing import LootCardTitleCountError
from .scoring import ItemComparer
from .vision import fixed_ocr_crop, preprocess_popup
from .ui_geometry import LOOT_BADGE_CROP, LOOT_TEXT_CROP


class LootAnalyzer:
    """Desktop adapter composition: screenshot crop + Paddle OCR around the shared decision engine."""

    def __init__(self, engine: PaddleOcrEngine, comparer: ItemComparer, scale: float = 2.0, show_ocr: bool = False) -> None:
        self.engine = engine
        self.decision_engine = LootDecisionEngine(comparer)
        self.scale = scale
        self.show_ocr = show_ocr

    def analyze(self, image: Image.Image) -> AnalysisArtifacts:
        popup_box, spans, diagnostics = self._ocr_popup(image.convert("RGB"))
        lines = tuple(self.decision_engine.lines.assemble(spans))
        try:
            result = self.decision_engine.decide_lines(lines)
        except LootCardTitleCountError:
            raise
        except ValueError as exc:
            comparison = Comparison(ComparisonStatus.CHECK_OCR, Action.CHECK, None, None, None, None, str(exc))
            result = DecisionResult(comparison, lines, (), ())

        if self.show_ocr:
            self._print_ocr(result.popup_lines)
        return AnalysisArtifacts(
            result.comparison,
            popup_box,
            result.popup_lines,
            result.equipped_lines,
            result.candidate_lines,
            diagnostics,
        )

    def _ocr_popup(self, image: Image.Image):
        popup_box = fixed_ocr_crop(image.width, image.height)
        popup_left, popup_top, _, _ = popup_box
        combined: list[OcrSpan] = []
        passes: list[OcrPass] = []
        for kind, crop in (("badge", LOOT_BADGE_CROP), ("affixes", LOOT_TEXT_CROP)):
            region = crop.pixels(image.size)
            accepted, raw = self.engine.recognize_with_diagnostics(
                preprocess_popup(image.crop(region), self.scale)
            )
            # The shared assembler expects popup-local, scaled coordinates.
            # The diagnostics instead retain original screenshot pixels.
            dx = (region[0] - popup_left) * self.scale
            dy = (region[1] - popup_top) * self.scale
            combined.extend(
                OcrSpan(span.text, span.score, Box(
                    span.box.left + dx, span.box.top + dy,
                    span.box.right + dx, span.box.bottom + dy,
                ))
                for span in accepted
            )
            passes.append(OcrPass(
                kind, Box(*region), self.scale,
                tuple(OcrSpan(s.text, s.score, s.box.shifted_scaled(
                    region[0], region[1], self.scale,
                )) for s in raw),
            ))
        return popup_box, combined, tuple(passes)

    @staticmethod
    def _print_ocr(lines) -> None:
        print("\nOCR lines:")
        for line in lines:
            print(f"  y={line.box.center_y:7.1f} conf={line.score:5.1%}  {line.text}")
