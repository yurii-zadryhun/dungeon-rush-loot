"""Avoid expensive duplicate neural OCR on visually identical fresh item cards."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from PIL import Image, ImageDraw

from src.domain import (
    Action, AnalysisArtifacts, Box, Comparison, ComparisonStatus, OcrLine,
    ParsedItem,
)
from src.modes import AutoClickMode, DecisionContext
from src.vision import semantic_candidate_hash


class FreshCardVerificationTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (709, 1536), "black")
        d = ImageDraw.Draw(self.image)
        d.rectangle((200, 1050, 585, 1200), fill="white")
        d.text((215, 1100), "Mega Crit 9.82%", fill="black")
        self.item = ParsedItem("Immortal [EXP] Crimson Gloves", "Immortal", 8, 115, (), (), 1.0)
        self.compare = Comparison(ComparisonStatus.OK, Action.SELL, self.item,
                                  self.item, None, None, "decision")
        self.artifacts = AnalysisArtifacts(
            self.compare, (88, 614, 620, 1259), (),
            (OcrLine("Immortal [EXP] Crimson Gloves", 0.98,
                     Box(100, 50, 470, 86)),),
            (OcrLine("Mega Crit 9.82%", 0.98, Box(120, 900, 495, 1150)),),
        )
        self.device = Mock()
        self.analyzer = Mock()
        self.mode = AutoClickMode(self.device, self.analyzer, Mock(), Mock(),
                                  Mock(), 2.0, 0.01)
        self.hash = semantic_candidate_hash(self.item)
        self.ctx = DecisionContext(self.image, self.artifacts, self.hash)

    def test_same_candidate_pixels_skip_second_ocr(self):
        self.device.screenshot.return_value = self.image.copy()
        verified = self.mode._fresh_verification(self.ctx)
        self.assertIsNotNone(verified)
        self.assertEqual(verified.candidate_hash, self.hash)
        self.analyzer.analyze.assert_not_called()

    def test_changed_pixels_require_semantic_ocr_confirmation(self):
        changed = self.image.copy()
        ImageDraw.Draw(changed).rectangle((270, 1140, 510, 1190), fill="black")
        self.device.screenshot.return_value = changed
        self.analyzer.analyze.return_value = self.artifacts
        verified = self.mode._fresh_verification(self.ctx)
        self.assertIsNotNone(verified)
        self.analyzer.analyze.assert_called_once_with(changed)


if __name__ == "__main__":
    unittest.main()
