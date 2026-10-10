from __future__ import annotations

import hashlib
import json

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .config import OCR_CROP_BOTTOM, OCR_CROP_TOP, OCR_CROP_LEFT, OCR_CROP_RIGHT
from .domain import OcrLine, ParsedItem
from .text import canonical_name, normalize_text


def fixed_ocr_crop(width: int, height: int) -> tuple[int, int, int, int]:
    return int(width * OCR_CROP_LEFT), int(height * OCR_CROP_TOP), int(width * OCR_CROP_RIGHT), int(height * OCR_CROP_BOTTOM)


def preprocess_popup(image: Image.Image, scale: float) -> Image.Image:
    if scale != 1.0:
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    return image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=125, threshold=2))


def clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    left, top = max(0, min(width - 1, left)), max(0, min(height - 1, top))
    return left, top, max(left + 1, min(width, right)), max(top + 1, min(height, bottom))


def source_region_for_lines(
    lines: tuple[OcrLine, ...], popup_box: tuple[int, int, int, int], scale: float, image_size: tuple[int, int]
) -> tuple[int, int, int, int]:
    if not lines:
        return popup_box
    popup_left, popup_top, _, _ = popup_box
    mapped = [line.box.shifted_scaled(popup_left, popup_top, scale) for line in lines]
    box = (int(min(x.left for x in mapped)) - 28, int(min(x.top for x in mapped)) - 22, int(max(x.right for x in mapped)) + 28, int(max(x.bottom for x in mapped)) + 22)
    return clamp_box(box, image_size[0], image_size[1])


def visual_signature(image: Image.Image, region: tuple[int, int, int, int]) -> bytes:
    roi = ImageOps.autocontrast(image.crop(region).convert("L")).filter(ImageFilter.GaussianBlur(radius=0.6))
    return roi.resize((96, 64), Image.Resampling.BILINEAR).tobytes()


def visual_difference(previous: bytes, current: bytes) -> float:
    if len(previous) != len(current) or not previous:
        return 1.0
    return sum(abs(a - b) for a, b in zip(previous, current)) / (255.0 * len(previous))


def semantic_candidate_hash(item: ParsedItem) -> str:
    payload = {
        "title": normalize_text(item.title).lower(),
        "rarity": item.rarity,
        "level": item.level,
        "stats": [(canonical_name(stat.name), round(stat.value, 2)) for stat in item.stats],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()
