"""Per-watcher-run decision JSONL files must never overwrite older sessions."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.decision_log import JsonlDecisionLog
from src.domain import Action, Comparison, ComparisonStatus


class DecisionLogSessionTests(unittest.TestCase):
    def test_timestamped_log_per_run_and_collision_safe_rotation(self):
        started = datetime(2026, 10, 13, 11, 31, 34, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as work:
            base = Path(work)
            first = JsonlDecisionLog.start_session(base, "universal", started_at=started)
            self.assertEqual(first.path.name, "decisions-20261013-113134.jsonl")
            check = Comparison(
                ComparisonStatus.CHECK_OCR, Action.CHECK, None, None, None, None,
                "Unparsed candidate affix lines",
            )
            first.append(check)
            text = first.path.read_text(encoding="utf-8")
            self.assertIn("check_ocr", text)
            second = JsonlDecisionLog.start_session(base, "universal", started_at=started)
            self.assertEqual(second.path.name, "decisions-20261013-113134-2.jsonl")
            self.assertEqual(first.path.read_text(encoding="utf-8"), text)
            self.assertEqual(second.path.read_text(encoding="utf-8"), "")
            tomorrow = JsonlDecisionLog.start_session(
                base, "universal", started_at=datetime(2026, 10, 14, 8, 5, 2),
            )
            self.assertEqual(tomorrow.path.name, "decisions-20261014-080502.jsonl")
            second.append(check)
            self.assertEqual(first.path.read_text(encoding="utf-8"), text)
            self.assertEqual(len(list(base.glob("decisions-*.jsonl"))), 3)

    def test_real_start_timestamp_is_read_once(self):
        with tempfile.TemporaryDirectory() as work:
            start = datetime(2026, 10, 13, 11, 47, 5)
            with patch("src.decision_log.datetime") as clock:
                clock.now.return_value.astimezone.return_value = start
                session = JsonlDecisionLog.start_session(Path(work))
            self.assertEqual(session.path.name, "decisions-20261013-114705.jsonl")


if __name__ == "__main__":
    unittest.main()
