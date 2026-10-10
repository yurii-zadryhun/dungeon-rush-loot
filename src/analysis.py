from __future__ import annotations

from PIL import Image

from .domain import AnalysisArtifacts
from .ocr import PaddleOcrEngine
from .parsing import LootCardSplitter, LootItemParser, OcrLineAssembler
from .scoring import ItemComparer
from .vision import fixed_ocr_crop, preprocess_popup


class LootAnalyzer:
    def __init__(self, engine: PaddleOcrEngine, comparer: ItemComparer, scale: float = 2.0, show_ocr: bool = False) -> None:
        self.engine = engine
        self.comparer = comparer
        self.scale = scale
        self.show_ocr = show_ocr
        self.lines = OcrLineAssembler()
        self.splitter = LootCardSplitter()
        self.parser = LootItemParser()

    def analyze(self, image: Image.Image) -> AnalysisArtifacts:
        popup_box, popup_lines = self._ocr_popup(image.convert("RGB"))
        equipped_lines, candidate_lines = self.splitter.split(popup_lines)
        comparison = self.comparer.compare(self.parser.parse(equipped_lines), self.parser.parse(candidate_lines))
        return AnalysisArtifacts(comparison, popup_box, tuple(popup_lines), tuple(equipped_lines), tuple(candidate_lines))

    def _ocr_popup(self, image: Image.Image):
        popup_box = fixed_ocr_crop(image.width, image.height)
        spans = self.engine.recognize(preprocess_popup(image.crop(popup_box), self.scale))
        lines = self.lines.assemble(spans)
        if self.show_ocr:
            self._print_ocr(lines)
        return popup_box, lines

    @staticmethod
    def _print_ocr(lines) -> None:
        print("\nOCR lines:")
        for line in lines:
            print(f"  y={line.box.center_y:7.1f} conf={line.score:5.1%}  {line.text}")
