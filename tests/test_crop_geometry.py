"""Prevent cross-platform popup crop drift.

The Android OCR adapter receives the same relative rectangle used by desktop
PaddleOCR. The source screenshot demonstrates that x4 and the game's Lvl 123
are OUTSIDE this crop. An OCR log bounding box inside that crop is not proof
that the actual HUD pixels appeared inside the captured bitmap: investigate
the original AccessibilityService screenshot and ML Kit input before guessing.
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

    def test_crop_excludes_background_hud_in_reference_screenshot(self):
        # Verified against the user's 709x1536 screenshot: the modal occupies
        # about x=84..625. The background HUD 'Lvl 123' starts beyond x=640
        # and the x4 badge outside the modal starts beyond x=624.
        left, _, right, _ = fixed_ocr_crop(709, 1536)
        self.assertEqual((left, right), (88, 620))
        self.assertGreaterEqual(left, 84)
        self.assertLess(right, 624)
        self.assertLess(right, 640)

    def test_invalid_rectangles_are_not_accepted_as_crop(self):
        crop = LOOT_UI.crop
        self.assertTrue(0.0 <= crop.left < crop.right <= 1.0)
        self.assertTrue(0.0 <= crop.top < crop.bottom <= 1.0)


if __name__ == "__main__":
    unittest.main()
