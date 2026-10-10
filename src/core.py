from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .domain import Comparison, OcrLine, OcrSpan
from .parsing import LootCardSplitter, LootItemParser, OcrLineAssembler
from .scoring import ItemComparer


@dataclass(frozen=True)
class DecisionResult:
    comparison: Comparison
    popup_lines: tuple[OcrLine, ...]
    equipped_lines: tuple[OcrLine, ...]
    candidate_lines: tuple[OcrLine, ...]


class LootDecisionEngine:
    """Platform-independent OCR-result -> loot-decision pipeline."""

    def __init__(self, comparer: ItemComparer) -> None:
        self.comparer = comparer
        self.lines = OcrLineAssembler()
        self.splitter = LootCardSplitter()
        self.parser = LootItemParser()

    def decide_spans(self, spans: Sequence[OcrSpan]) -> DecisionResult:
        return self.decide_lines(self.lines.assemble(spans))

    def decide_lines(self, lines: Sequence[OcrLine]) -> DecisionResult:
        popup_lines = tuple(lines)
        equipped_lines, candidate_lines = self.splitter.split(popup_lines)
        equipped = self.parser.parse(equipped_lines)
        candidate = self.parser.parse(candidate_lines)
        comparison = self.comparer.compare(equipped, candidate)
        return DecisionResult(
            comparison=comparison,
            popup_lines=popup_lines,
            equipped_lines=tuple(equipped_lines),
            candidate_lines=tuple(candidate_lines),
        )
