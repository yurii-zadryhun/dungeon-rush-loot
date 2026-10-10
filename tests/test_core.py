from __future__ import annotations

import io
import random
import re
import unittest

from rich.console import Console

from src.cli import build_parser, _validate
from src.domain import (
    Action,
    AnalysisArtifacts,
    Box,
    Comparison,
    ComparisonStatus,
    ModeOutcome,
    OcrLine,
    ParsedItem,
    ParsedStat,
    WatchState,
)
from src.parsing import LootItemParser
from src.presentation import ComparisonFormatter, ConsolePresenter
from src.scoring import ItemComparer, PrimaryPowerScorer
from src.touch import HumanGestureGenerator, LootButtonLayout
from src.watcher import LootWatcher


def item(title: str, tier: int, level: int, stats=()) -> ParsedItem:
    return ParsedItem(title, title.split()[0], tier, level, tuple(stats), (), 1.0, "[Melee]" in title or "[Meele]" in title)


class PrimaryPowerScorerTest(unittest.TestCase):
    def test_reference_endpoints(self):
        scorer = PrimaryPowerScorer()
        self.assertAlmostEqual(scorer.score(item("Immortal Gloves", 8, 1)), -15.0, places=6)
        self.assertAlmostEqual(scorer.score(item("Divine Gloves", 9, 130)), 20.0, places=6)

    def test_immortal_65_66_are_still_negative(self):
        scorer = PrimaryPowerScorer()
        self.assertAlmostEqual(scorer.score(item("Immortal Gloves", 8, 65)), -4.4966, places=3)
        self.assertAlmostEqual(scorer.score(item("Immortal Gloves", 8, 66)), -4.3772, places=3)


class MeleeRegressionTest(unittest.TestCase):
    def test_meele_typo_is_rejected(self):
        parser = LootItemParser()
        parsed = parser.parse([OcrLine("Divine Hammer [Meele]", 0.99, Box(0, 0, 200, 20))])
        self.assertTrue(parsed.melee)

    def test_malformed_melee_without_loadout_fails_closed(self):
        comparer = ItemComparer()
        equipped = item("Divine Ring", 9, 100)
        candidate = item("Divine Hammer [Meele]", 9, 100)
        comparison = comparer.compare(equipped, candidate)
        self.assertEqual(comparison.status, ComparisonStatus.CHECK_OCR)
        self.assertEqual(comparison.action, Action.CHECK)
        self.assertEqual(str(ComparisonFormatter.summary(comparison, False)), "🟡 CHECK OCR")


class GestureTest(unittest.TestCase):
    def test_random_gesture_stays_inside_button(self):
        generator = HumanGestureGenerator(random.Random(42))
        rect = LootButtonLayout().target(Action.EQUIP)
        gesture = generator.generate(rect, (709, 1536))
        left, top, right, bottom = rect.pixels((709, 1536))
        for x, y in (gesture.start, gesture.end):
            self.assertTrue(left <= x <= right)
            self.assertTrue(top <= y <= bottom)
        self.assertTrue(55 <= gesture.duration_ms <= 125)


class ParserRegressionTest(unittest.TestCase):
    def test_multiline_critical_damage_taken(self):
        parser = LootItemParser()
        lines = [
            OcrLine("Divine [EXP] Holy Ring", 0.99, Box(0, 0, 300, 30)),
            OcrLine("Lvl103", 0.99, Box(0, 30, 80, 60)),
            OcrLine("+30.15% Attack Speed", 0.99, Box(0, 60, 300, 90)),
            OcrLine("+50.60% Critical Damage", 0.99, Box(0, 90, 300, 120)),
            OcrLine("+8.50% Damage", 0.99, Box(0, 120, 300, 150)),
            OcrLine("-51.11% Critical Damage", 0.99, Box(0, 150, 300, 180)),
            OcrLine("Taken", 0.99, Box(0, 180, 100, 210)),
        ]
        parsed = parser.parse(lines)
        self.assertEqual(parsed.tier, 9)
        self.assertEqual(parsed.level, 103)
        self.assertEqual(len(parsed.stats), 4)
        self.assertTrue(any(stat.name == "critical damage taken" and abs(stat.value + 51.11) < 0.01 for stat in parsed.stats))

    def test_immortal_rarity_parses(self):
        parser = LootItemParser()
        parsed = parser.parse([
            OcrLine("Immortal [EXP] Blood Gloves", 0.99, Box(0, 0, 300, 30)),
            OcrLine("Lvl65", 0.99, Box(0, 30, 80, 60)),
        ])
        self.assertEqual(parsed.tier, 8)
        self.assertEqual(parsed.rarity, "Immortal")


class ConsolePresenterTest(unittest.TestCase):
    def setUp(self):
        self.buffer = io.StringIO()
        self.console = Console(file=self.buffer, force_terminal=False, width=120)
        self.presenter = ConsolePresenter(console=self.console)

    def test_warning_includes_timestamp(self):
        self.presenter.warning("test warning message")
        output = self.buffer.getvalue()
        self.assertRegex(output, r"\[\d{2}:\d{2}:\d{2}\] test warning message")

    def test_foreground_includes_timestamp(self):
        self.presenter.foreground(True)
        self.assertRegex(self.buffer.getvalue(), r"\[\d{2}:\d{2}:\d{2}\] OCR resumed")

        self.buffer.truncate(0)
        self.buffer.seek(0)
        self.presenter.foreground(False)
        self.assertRegex(self.buffer.getvalue(), r"\[\d{2}:\d{2}:\d{2}\] OCR paused")

    def test_result_check_ocr_includes_timestamp(self):
        comp = Comparison(ComparisonStatus.CHECK_OCR, Action.CHECK, None, None, None, None, "unclear text")
        self.presenter.result(comp)
        output = self.buffer.getvalue()
        self.assertRegex(output, r"\[\d{2}:\d{2}:\d{2}\] 🟡 CHECK OCR · unclear text")

    def test_unverified_melee_does_not_log_a_sell(self):
        comparer = ItemComparer()
        equipped = item("Divine Ring", 9, 100)
        candidate = item("Divine Hammer [Meele]", 9, 100)
        comp = comparer.compare(equipped, candidate)
        self.presenter.result(comp)
        output = self.buffer.getvalue()
        self.assertRegex(output, r"\[\d{2}:\d{2}:\d{2}\] 🟡 CHECK OCR")


class WatchStateAndTtlTest(unittest.TestCase):
    def test_watch_state_reset_methods(self):
        state = WatchState(
            last_success_region=(0, 0, 100, 100),
            last_success_signature=b"test",
            last_success_signature_at=123.45,
            last_candidate_hash="abc",
            last_candidate_hash_at=678.90,
        )
        state.reset_visual_gate()
        self.assertIsNone(state.last_success_region)
        self.assertIsNone(state.last_success_signature)
        self.assertEqual(state.last_success_signature_at, 0.0)

        state.reset_candidate_hash()
        self.assertIsNone(state.last_candidate_hash)
        self.assertEqual(state.last_candidate_hash_at, 0.0)

    def test_is_candidate_same_with_ttl(self):
        watcher = LootWatcher(
            device=None,
            analyzer=None,
            mode=None,
            presenter=ConsolePresenter(console=Console(file=io.StringIO())),
            artifacts=None,
            scale=2.0,
            visual_change_threshold=0.01,
            background_check_interval=0.5,
            retry_interval=0.25,
            visual_signature_ttl=5.0,
            candidate_hash_ttl=5.0,
        )
        self.assertFalse(watcher._is_candidate_same("hash1"))

        watcher.state.last_candidate_hash = "hash1"
        watcher.state.last_candidate_hash_at = 100.0

        import time
        orig_monotonic = time.monotonic
        try:
            time.monotonic = lambda: 102.0
            self.assertTrue(watcher._is_candidate_same("hash1"))
            self.assertFalse(watcher._is_candidate_same("hash2"))

            time.monotonic = lambda: 106.0
            self.assertFalse(watcher._is_candidate_same("hash1"))
        finally:
            time.monotonic = orig_monotonic

    def test_unchanged_with_ttl(self):
        from PIL import Image
        from src.vision import visual_signature

        img = Image.new("RGB", (200, 200), color=(100, 100, 100))
        region = (10, 10, 50, 50)
        sig = visual_signature(img, region)

        watcher = LootWatcher(
            device=None,
            analyzer=None,
            mode=None,
            presenter=ConsolePresenter(console=Console(file=io.StringIO())),
            artifacts=None,
            scale=2.0,
            visual_change_threshold=0.01,
            background_check_interval=0.5,
            retry_interval=0.25,
            visual_signature_ttl=5.0,
            candidate_hash_ttl=5.0,
        )
        watcher.state.last_success_region = region
        watcher.state.last_success_signature = sig
        watcher.state.last_success_signature_at = 100.0

        import time
        orig_monotonic = time.monotonic
        try:
            time.monotonic = lambda: 102.0
            self.assertTrue(watcher._unchanged(img))

            time.monotonic = lambda: 106.0
            self.assertFalse(watcher._unchanged(img))
            self.assertIsNone(watcher.state.last_success_signature)
        finally:
            time.monotonic = orig_monotonic

    def test_process_frame_unconsumed_resets_visual_gate(self):
        from PIL import Image

        img = Image.new("RGB", (200, 200), color=(100, 100, 100))
        test_item = item("Divine Ring", 9, 100)
        comp = Comparison(ComparisonStatus.OK, Action.SELL, test_item, test_item, None, None, "ok")
        mock_artifacts = AnalysisArtifacts(
            comparison=comp,
            popup_box=(0, 0, 100, 100),
            popup_lines=(),
            equipped_lines=(),
            candidate_lines=(),
        )

        class MockAnalyzer:
            def analyze(self, image):
                return mock_artifacts

        class MockMode:
            def __init__(self, consume):
                self.consume = consume
                self.handled = 0

            def handle(self, context):
                self.handled += 1
                return ModeOutcome(consume_candidate=self.consume)

            def handle_check(self, comparison):
                pass

        class MockArtifactWriter:
            def save(self, image, artifacts, scale):
                pass

        mode_fail = MockMode(consume=False)
        watcher = LootWatcher(
            device=None,
            analyzer=MockAnalyzer(),
            mode=mode_fail,
            presenter=ConsolePresenter(console=Console(file=io.StringIO())),
            artifacts=MockArtifactWriter(),
            scale=2.0,
            visual_change_threshold=0.01,
            background_check_interval=0.5,
            retry_interval=0.25,
        )

        watcher._process_frame(img)
        self.assertEqual(mode_fail.handled, 1)
        self.assertIsNone(watcher.state.last_candidate_hash)
        self.assertIsNone(watcher.state.last_success_signature)

        mode_success = MockMode(consume=True)
        watcher.mode = mode_success
        watcher._process_frame(img)
        self.assertEqual(mode_success.handled, 1)
        self.assertIsNotNone(watcher.state.last_candidate_hash)
        self.assertIsNotNone(watcher.state.last_success_signature)

    def test_cli_ttl_args(self):
        parser = build_parser()
        args = parser.parse_args(["--adb", "serial1", "--hash-ttl", "7.5"])
        _validate(args)
        self.assertEqual(args.hash_ttl, 7.5)

        args = parser.parse_args(["--adb", "serial1", "--visual-signature-ttl", "3.0", "--candidate-hash-ttl", "6.0"])
        _validate(args)
        self.assertEqual(args.visual_signature_ttl, 3.0)
        self.assertEqual(args.candidate_hash_ttl, 6.0)

        with self.assertRaises(SystemExit):
            bad_args = parser.parse_args(["--adb", "serial1", "--hash-ttl", "0"])
            _validate(bad_args)


if __name__ == "__main__":
    unittest.main()
