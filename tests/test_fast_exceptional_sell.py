"""Straight-through fast SELL and optional one-crop Confirm OCR."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PIL import Image

from src.domain import Action, Box, OcrSpan
from src.fast_sell import FastExceptionalSellProbe, MIN_PROMISING_CAP_FRACTION
from src.modes import AutoClickMode
from src.ui_geometry import LOOT_EXCEPTIONAL_CROP, LOOT_CONFIRM_TEXT_CROP

WIDTH, HEIGHT = 709, 1536


class FakeOcr:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def recognize(self, image):
        self.calls.append(image.size)
        return [
            OcrSpan(text, 0.99, Box(20, i*65 + 10, 580, i*65 + 52))
            for i, text in enumerate(self.rows)
        ]


class FastExceptionalTests(unittest.TestCase):
    def setUp(self):
        self.frame = Image.new("RGB", (WIDTH, HEIGHT), (25, 25, 25))

    def test_candidate_footer_is_single_crop_without_badge_or_color_passes(self):
        ocr = FakeOcr((
            "+34.83% Melee Damage",
            "+3.67% Block Chance",
            "+8.35% Thorns",
        ))
        result = FastExceptionalSellProbe(ocr).probe(self.frame)
        self.assertIsNotNone(result)
        self.assertEqual(result.cap_fraction, 0)
        self.assertEqual(len(ocr.calls), 1)
        x1,y1,x2,y2 = LOOT_EXCEPTIONAL_CROP.pixels(self.frame.size)
        self.assertEqual(ocr.calls[0], ((x2-x1)*2,(y2-y1)*2))

    def test_low_mega_and_single_cdt_50_both_fast_sell(self):
        for row in ("+4.10% Mega Crit Chance", "-50.00% Critical Damage Taken"):
            with self.subTest(row=row):
                ocr=FakeOcr((row,))
                evidence=FastExceptionalSellProbe(ocr).probe(self.frame)
                self.assertIsNotNone(evidence)
                self.assertLess(evidence.cap_fraction, 0.90)
        self.assertEqual(MIN_PROMISING_CAP_FRACTION, 0.90)

    def test_two_medium_rolls_or_valuable_one_take_full_path(self):
        for rows in (
            ("+15.00% Triple Hit Chance","+5.00% Mega Crit Chance"),
            ("+27.00% Triple Hit Chance",),
            ("-60.00% Critical Damage Taken",),
        ):
            with self.subTest(rows=rows):
                ocr=FakeOcr(rows)
                self.assertIsNone(FastExceptionalSellProbe(ocr).probe(self.frame))
                self.assertEqual(len(ocr.calls),1)

    def test_wrap_long_cdt_into_two_lines(self):
        ocr=FakeOcr(("-50.00% Critical Damage", "Taken"))
        evidence=FastExceptionalSellProbe(ocr).probe(self.frame)
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.stats[0].name,"critical damage taken")

    def test_empty_ocr_falls_back_to_full_path(self):
        self.assertIsNone(FastExceptionalSellProbe(FakeOcr(())).probe(self.frame))

    def mode(self, confirm_text):
        device=Mock()
        device.screenshot.return_value=self.frame
        model=FakeOcr((confirm_text,) if confirm_text else ())
        analyzer=Mock(engine=model)
        touch=Mock()
        mode=AutoClickMode(device,analyzer,touch,Mock(verbose=False),Mock(),2.0,0.01)
        return mode,touch,model

    @patch("src.modes.time.sleep")
    def test_fast_sell_confirm_detected_once_then_tapped(self, _sleep):
        mode,touch,model=self.mode("Confirm")
        self.assertTrue(mode.quick_sell(self.frame))
        self.assertEqual([c.args[0] for c in touch.touch.call_args_list],
                         [Action.SELL,Action.CONFIRM_SELL])
        self.assertEqual(len(model.calls),1)
        x1,y1,x2,y2=LOOT_CONFIRM_TEXT_CROP.pixels(self.frame.size)
        self.assertEqual(model.calls[0],((x2-x1)*2,(y2-y1)*2))

    @patch("src.modes.time.sleep")
    def test_no_confirm_dialog_means_no_second_touch(self, _sleep):
        for text in ("", "Cancel", "Sell"):
            with self.subTest(text=text):
                mode,touch,model=self.mode(text)
                self.assertTrue(mode.quick_sell(self.frame))
                self.assertEqual([c.args[0] for c in touch.touch.call_args_list],
                                 [Action.SELL])
                self.assertEqual(len(model.calls),1)

    @patch("src.modes.time.sleep")
    def test_normalized_confirm_match(self, _sleep):
        mode,touch,_=self.mode(" Con firm! ")
        mode.quick_sell(self.frame)
        self.assertEqual(touch.touch.call_count,2)


if __name__=="__main__":
    unittest.main()
