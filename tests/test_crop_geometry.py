"""Prevent cross-platform popup crop drift.

The Android OCR adapter receives the same relative rectangle used by desktop
PaddleOCR; the x4 badge and HUD level seen in live logs were actually *inside*
the old OCR rectangle, so simply restoring these constants cannot remove them.
"""
from __future__ import annotations

import json
import unittest

from src.android_bridge import app_config_json
from src.config import (
    OCR_CROP_LEFT, OCR_CROP_RIGHT, OCR_CROP_TOP, OCR_CROP_BOTTOM,
)
from src.ui_geometry import LOOT_UI
from src.vision import fixed_ocr_crop


class CropGeometryTests(unittest.TestCase):
    def test_live_android_and_desktop_share_original_popup_crop(self):
        reference = {
            "left": 0.125, "top": 0.40,
            "right": 0.875, "bottom": 0.82,
        }
        self.assertEqual(
            (OCR_CROP_LEFT, OCR_CROP_TOP, OCR_CROP_RIGHT, OCR_CROP_BOTTOM),
            (0.125, 0.40, 0.875, 0.82),
        )
        self.assertEqual(LOOT_UI.crop.to_dict(), reference)
        self.assertEqual(json.loads(app_config_json())["crop"], reference)
        self.assertEqual(fixed_ocr_crop(1080, 2340), (135, 936, 945, 1918))

    def test_ocr_log_hud_artifacts_fall_inside_original_crop(self):
        # Real recorded bounding boxes from the 19:48 session:
        # The excluded pixels are x < 135 or x >= 945, but the
        # game's unrelated HUD elements are closer to the popup.
        left, _, right, _ = fixed_ocr_crop(1080, 2340)
        for start, end in ((837, 891), (873, 933)):
            self.assertGreaterEqual(start, left)
            self.assertLess(end, right)

    def test_invalid_rectangles_are_not_accepted_as_crop(self):
        crop = LOOT_UI.crop
        self.assertTrue(0.0 <= crop.left < crop.right <= 1.0)
        self.assertTrue(0.0 <= crop.top < crop.bottom <= 1.0)


if __name__ == "__main__":
    unittest.main()
