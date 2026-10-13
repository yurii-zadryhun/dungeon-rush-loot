from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from src.analysis import LootAnalyzer
from src.artifacts import ArtifactWriter
from src.decision_log import JsonlDecisionLog
from src.domain import Action, Comparison, ComparisonStatus, ModeOutcome, ParsedItem
from src.ocr import PaddleOcrEngine
from src.parsing import LootCardSplitter, LootCardTitleCountError
from src.scoring import ItemComparer
from src.vision import fixed_ocr_crop
from src.watcher import LootWatcher


def engine_with_rows(rows):
    engine = PaddleOcrEngine.__new__(PaddleOcrEngine)
    engine.min_confidence = 0.2
    def predict(image):
        # Badges and affix text are recognized independently in Desktop.
        # Retain original Y positions and model the distinct region contents.
        left_region = image.width < 500
        indexed = [
            (index, text, score) for index, (text, score) in enumerate(rows)
            if text.lower().startswith(("lvl", "lv?")) == left_region
        ]
        return [{
            "rec_texts": [text for _, text, _ in indexed],
            "rec_scores": [score for _, _, score in indexed],
            "rec_boxes": [[20, i * 40 + 20, 120, i * 40 + 40]
                          for i, _, _ in indexed],
        }]
    engine._predict = Mock(side_effect=predict)
    return engine


class DesktopOcrDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (709, 1536), "black")
        self.engine = engine_with_rows([
            ("Divine Celestial Helmet", 0.99), ("Lv?", 0.12), ("Lvl87", 0.98),
            ("Immortal Dread Helm", 0.99), ("Lvl4", 0.98),
        ])
        self.analyzer = LootAnalyzer(self.engine, ItemComparer(), scale=2.0)

    def test_raw_diagnostics_keep_rejected_text_without_changing_recognition(self):
        accepted, raw = self.engine.recognize_with_diagnostics(self.image)
        self.assertEqual([s.text for s in accepted],
                         ["Divine Celestial Helmet", "Lvl87", "Immortal Dread Helm", "Lvl4"])
        self.assertEqual([s.text for s in raw],
                         ["Divine Celestial Helmet", "Lv?", "Lvl87", "Immortal Dread Helm", "Lvl4"])
        self.assertEqual(self.engine.recognize(self.image), accepted)

    def test_analyzer_maps_raw_boxes_to_screenshot_coordinates(self):
        artifacts = self.analyzer.analyze(self.image)
        badge, affixes = artifacts.rarity_level_passes
        left, top, right, bottom = fixed_ocr_crop(*self.image.size)
        self.assertEqual(badge.kind, "badge")
        self.assertEqual(affixes.kind, "affixes")
        self.assertGreater(badge.crop.left, left)
        self.assertEqual(badge.crop.bottom, bottom)
        self.assertEqual(badge.scale, 2.0)
        self.assertAlmostEqual(badge.lines[0].box.left, badge.crop.left + 10)
        self.assertAlmostEqual(badge.lines[0].box.top, top + 30)
        self.assertEqual(badge.lines[0].score, 0.12)
        self.assertNotIn("Lv?", [line.text for line in artifacts.popup_lines])
        self.assertEqual(self.engine._predict.call_count, 2)

    def test_annotation_is_saved_without_modifying_source(self):
        artifacts = self.analyzer.analyze(self.image)
        with tempfile.TemporaryDirectory() as directory:
            writer = ArtifactWriter(Path(directory))
            writer.save(self.image, artifacts, 2.0)
            path = Path(directory) / "rarity-level-annotated.jpg"
            self.assertTrue(path.is_file())
            with Image.open(path) as annotated:
                self.assertEqual(annotated.size, self.image.size)
                self.assertIsNotNone(annotated.getbbox())
            self.assertIsNone(self.image.getbbox())

    def test_no_annotate_disables_both_images(self):
        artifacts = self.analyzer.analyze(self.image)
        with tempfile.TemporaryDirectory() as directory:
            ArtifactWriter(Path(directory), annotate=False).save(self.image, artifacts, 2.0)
            self.assertFalse((Path(directory) / "annotated.jpg").exists())
            self.assertFalse((Path(directory) / "rarity-level-annotated.jpg").exists())

    def test_title_count_raises_custom_exception(self):
        with self.assertRaisesRegex(LootCardTitleCountError, "got 0"):
            LootCardSplitter().split([])

    def test_analyzer_propagates_title_count_exception(self):
        self.engine._predict.side_effect = lambda _: []
        with self.assertRaises(LootCardTitleCountError):
            self.analyzer.analyze(self.image)

    def test_empty_pass_is_silently_ignored(self):
        self.engine._predict.return_value = []
        presenter, mode, writer, decision_log = Mock(), Mock(), Mock(), Mock()
        watcher = LootWatcher(
            Mock(), self.analyzer, mode, presenter, writer,
            scale=2.0, visual_change_threshold=0.01,
            background_check_interval=0.5, retry_interval=0.25,
            decision_log=decision_log,
        )
        with patch.object(watcher, "_ensure_foreground", return_value=True), patch("src.watcher.time.sleep") as sleep:
            watcher.device.screenshot.return_value = self.image
            watcher._cycle()
        self.assertEqual(presenter.mock_calls, [])
        self.assertEqual(mode.mock_calls, [])
        self.assertEqual(writer.mock_calls, [])
        self.assertEqual(decision_log.mock_calls, [])
        sleep.assert_called_once_with(0.25)

    def test_check_keeps_ocr_lines_and_image_with_existing_throttling(self):
        self._verify_watcher_diagnostics()

    def test_ok_keeps_raw_diagnostics(self):
        item = ParsedItem("Divine Ring", "Divine", 9, 87, (), (), 1.0)
        comparison = Comparison(ComparisonStatus.OK, Action.SELL, item, item, None, None, "ok")
        self.analyzer.decision_engine.comparer = Mock()
        self.analyzer.decision_engine.comparer.compare.return_value = comparison
        self._verify_watcher_diagnostics(ok=True)

    def _verify_watcher_diagnostics(self, *, empty=False, ok=False):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            mode = Mock()
            mode.handle.return_value = ModeOutcome(consume_candidate=True)
            writer = ArtifactWriter(output)
            watcher = LootWatcher(
                None, self.analyzer, mode, Mock(), writer,
                scale=2.0, visual_change_threshold=0.01,
                background_check_interval=0.5, retry_interval=0.25,
                decision_log=JsonlDecisionLog(output / "decisions.jsonl"),
            )
            with patch("src.watcher.time.sleep"):
                watcher._process_frame(self.image)
                watcher._process_frame(self.image)
            events = (output / "decisions.jsonl").read_text().splitlines()
            self.assertEqual(len(events), 1)
            event = json.loads(events[0])
            self.assertEqual(event["status"], "ok" if ok else "check_ocr")
            diagnostic = event["rarity_level_passes"][0]
            self.assertEqual(diagnostic["coordinate_space"], "screenshot_pixels")
            self.assertEqual([line["text"] for line in diagnostic["ocr_lines"]],
                             [] if empty else ["Lv?", "Lvl87", "Lvl4"])
            self.assertEqual(len(event["ocr_lines"]), 0 if empty else 4)
            self.assertEqual(event["rarity_level_annotated_image"],
                             str(output / "rarity-level-annotated.jpg"))
            self.assertTrue(Path(event["rarity_level_annotated_image"]).exists())
            if not ok:
                mode.handle.assert_not_called()
                mode.handle_check.assert_called_once()


if __name__ == "__main__":
    unittest.main()