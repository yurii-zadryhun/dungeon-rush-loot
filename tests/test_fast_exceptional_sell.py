"""Live-size fast Exceptional filtering: no false SELL on unreadable/color-clipped rolls."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from PIL import Image, ImageDraw

from src.config import TARGET_PACKAGE
from src.domain import Box, OcrSpan
from src.fast_sell import (
    FastExceptionalSellProbe, MIN_PROMISING_CAP_FRACTION, orange_rows,
)
from src.modes import AutoClickMode
from src.ui_geometry import LOOT_EXCEPTIONAL_CROP


W, H = 945, 2048
ORANGE = (255, 173, 34)


def screen(bands=(1631,), hidden=False):
    image = Image.new("RGB", (W, H), (39, 39, 39))
    d = ImageDraw.Draw(image)
    for y in bands:
        d.rectangle((355, y, 785, y + 19), fill=ORANGE)
    if hidden:
        d.rectangle((355, 1490, 785, 1509), fill=ORANGE)
    return image


class FakeOcr:
    def __init__(self, stats=("+8.35% Thorns",), rarities=("Divine", "Immortal"),
                 positions=(1631, 1659)):
        self.stats = stats
        self.rarities = rarities
        self.positions = positions
        self.calls = []

    def recognize(self, crop):
        self.calls.append(crop.size)
        # The cropped region is scaled 2x. Badge width: 0.19 * 945 * 2,
        # exceptional width: 0.53 * 945 * 2.
        if crop.width < 500:
            y0 = int(0.40 * H)
            return [
                OcrSpan(text, 0.99, Box(20, (y - y0)*2, 275, (y + 23 - y0)*2))
                for text, y in zip(self.rarities, (951, 1390))
            ]
        y0 = int(.748*H)
        return [
            OcrSpan(text, 0.99, Box(45, (y-y0)*2, 900, (y+19-y0)*2))
            for text, y in zip(self.stats, self.positions)
        ]


class FastExceptionalTests(unittest.TestCase):
    def test_live_screenshot_geometry_is_exact_candidate_footer(self):
        region = LOOT_EXCEPTIONAL_CROP.pixels((W, H))
        self.assertEqual(region, (326, 1531, 826, 1679))
        self.assertEqual(orange_rows(screen(), region), ((1631, 1651),))

    def test_weak_thorns_is_sold_from_tiny_crop_and_two_rarities(self):
        model = FakeOcr()
        evidence = FastExceptionalSellProbe(model).probe(screen())
        self.assertIsNotNone(evidence)
        self.assertAlmostEqual(evidence.cap_fraction, 0.0)
        self.assertEqual(evidence.rarity_equipped, "divine")
        self.assertEqual(evidence.rarity_candidate, "immortal")
        self.assertEqual([x.name for x in evidence.stats], ["thorns"])
        self.assertEqual(len(model.calls), 2)

    def test_two_middling_good_rolls_meeting_cap_ratio_require_full_analysis(self):
        model = FakeOcr(
            ("+15.00% Triple Hit Chance", "+5.00% Mega Crit Chance"),
            positions=(1575, 1631),
        )
        self.assertIsNone(
            FastExceptionalSellProbe(model).probe(screen((1575, 1631)))
        )
        # No badge OCR needed: the useful exceptional threshold already passed.
        self.assertEqual(len(model.calls), 1)

    def test_good_single_exceptional_and_exact_boundary_do_not_fast_sell(self):
        for value in (27.0, 29.8):
            model = FakeOcr((f"+{value:.2f}% Triple Hit Chance",))
            with self.subTest(value=value):
                self.assertIsNone(FastExceptionalSellProbe(model).probe(screen()))
                self.assertEqual(len(model.calls), 1)
        self.assertEqual(MIN_PROMISING_CAP_FRACTION, 0.90)

    def test_triple_below_threshold_can_fast_sell(self):
        model = FakeOcr(("+12.00% Triple Hit Chance",))
        evidence = FastExceptionalSellProbe(model).probe(screen())
        self.assertIsNotNone(evidence)
        self.assertAlmostEqual(evidence.cap_fraction, 0.4)

    def test_ambiguous_and_missing_orange_lines_always_fall_back(self):
        cases = (
            (FakeOcr(stats=()), screen()),
            (FakeOcr(stats=("Taken",)), screen()),
            (FakeOcr(stats=("+70% Ranged Defense",)), screen()),
            (FakeOcr(), screen(hidden=True)),
            (FakeOcr(), screen((1533,))),
            (FakeOcr(), screen((1663,))),
            (FakeOcr(), screen((1631, 1659))),
        )
        for model, image in cases:
            with self.subTest(label=(model.stats, image.getpixel((360,1492)))):
                self.assertIsNone(FastExceptionalSellProbe(model).probe(image))

    def test_divine_over_immortal_falls_back_for_sell_confirmation(self):
        ocr = FakeOcr(rarities=("Immortal", "Divine"))
        self.assertIsNone(FastExceptionalSellProbe(ocr).probe(screen()))

    def test_badge_reading_error_must_not_authorize_quick_sell(self):
        for rarities in ((), ("Divine",), ("Divine", "Immortal", "Divine"),
                         ("Divine", "Bogus")):
            with self.subTest(rarities=rarities):
                self.assertIsNone(
                    FastExceptionalSellProbe(FakeOcr(rarities=rarities)).probe(screen())
                )

    def test_fast_touch_requires_foreground_and_unchanged_candidate_pixels(self):
        first = screen()
        device = Mock()
        device.foreground_package.return_value = TARGET_PACKAGE
        device.screenshot.return_value = first.copy()
        touch = Mock()
        mode = AutoClickMode(device, Mock(), touch, Mock(verbose=False), Mock(),
                             2.0, 0.01)
        region = LOOT_EXCEPTIONAL_CROP.pixels(first.size)
        self.assertTrue(mode.quick_sell(first, region))
        touch.touch.assert_called_once()
        device.foreground_package.return_value = "other.app"
        self.assertFalse(mode.quick_sell(first, region))
        device.foreground_package.return_value = TARGET_PACKAGE
        changed = screen((1590,))
        device.screenshot.return_value = changed
        self.assertFalse(mode.quick_sell(first, region))


if __name__ == "__main__":
    unittest.main()
