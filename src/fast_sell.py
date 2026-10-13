"""Desktop fast-path for obviously unhelpful Exceptional loot.

Only returns a SELL recommendation after *color-verified* orange rows, OCR
recognition of every colored row, exact exceptional affix validation and a
second lightweight rarity check. Everything ambiguous takes the full OCR and
shared ItemComparer path. No candidate stats are guessed or silently dropped.

The ratio threshold is explicitly a gameplay preference, not a combat formula:
sum(value / per-affix-cap) >= 0.90 means send to full build comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from .config import EXCEPTIONAL_SKILLS, RARITY_TIERS
from .exceptional_gate import MIN_PROMISING_CAP_FRACTION, useful_exceptional_fraction
from .domain import OcrLine, OcrSpan, ParsedStat
from .parsing import LootItemParser, OcrLineAssembler
from .ui_geometry import LOOT_BADGE_CROP, LOOT_EXCEPTIONAL_CROP
from .vision import preprocess_popup

if TYPE_CHECKING:
    from .ocr import PaddleOcrEngine

# Upper guard checks that no colored roll was cut by the fixed bottom crop.
TOP_GUARD_START = 0.715
BOTTOM_GUARD_END = 0.835


@dataclass(frozen=True)
class FastSellEvidence:
    stats: tuple[ParsedStat, ...]
    cap_fraction: float
    rarity_equipped: str
    rarity_candidate: str
    ocr_lines: tuple[OcrLine, ...]
    crop: tuple[int, int, int, int]


def orange_rows(image: Image.Image, region: tuple[int, int, int, int]) -> tuple[tuple[int, int], ...]:
    """Detect visible orange letter rows in screenshot coordinates.

    Group contiguous color-positive scanlines into text rows. Background/white
    normal rolls should never be counted. This is intentionally conservative:
    failure to segment just skips the quick path.
    """
    left, top, right, bottom = region
    pixels = np.asarray(image.crop(region).convert("RGB"), dtype=np.int16)
    if pixels.size == 0:
        return ()
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    orange = (
        (red > 145) & (green > 70) & (blue < 175)
        & (red > green * 1.12) & (green > blue * 1.10)
    )
    counts = orange.sum(axis=1)
    threshold = max(7, (right - left) // 90)
    indices = np.flatnonzero(counts >= threshold)
    if len(indices) == 0:
        return ()
    groups = []
    first = last = int(indices[0])
    for current in map(int, indices[1:]):
        if current - last > 6:
            if last - first >= 7:
                groups.append((top + first, top + last + 1))
            first = current
        last = current
    if last - first >= 7:
        groups.append((top + first, top + last + 1))
    return tuple(groups)


def _has_orange_text_pixels(
    image: Image.Image, region: tuple[int, int, int, int],
) -> bool:
    """Guard bands must detect even a *partial* truncated colored line."""
    pixels = np.asarray(image.crop(region).convert("RGB"), dtype=np.int16)
    if pixels.size == 0:
        return False
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    orange = (
        (red > 145) & (green > 70) & (blue < 175)
        & (red > green * 1.12) & (green > blue * 1.10)
    )
    return bool(np.any(orange.sum(axis=1) >= max(7, (region[2] - region[0]) // 90)))


class FastExceptionalSellProbe:
    def __init__(self, engine: PaddleOcrEngine, scale: float = 2.0) -> None:
        self.engine = engine
        self.scale = scale
        self.parser = LootItemParser()
        self.assembler = OcrLineAssembler()

    def _ocr(self, image: Image.Image, crop: tuple[int, int, int, int]) -> tuple[OcrLine, ...]:
        spans = self.engine.recognize(preprocess_popup(image.crop(crop), self.scale))
        left, top, _, _ = crop
        screen_spans = [
            OcrSpan(span.text, span.score,
                    span.box.shifted_scaled(left, top, self.scale))
            for span in spans
        ]
        return tuple(self.assembler.assemble(screen_spans))

    def probe(self, image: Image.Image) -> FastSellEvidence | None:
        width, height = image.size
        if width < 300 or height < 650:
            return None
        candidate_region = LOOT_EXCEPTIONAL_CROP.pixels(image.size)
        bands = orange_rows(image, candidate_region)
        if not 1 <= len(bands) <= 3:
            return None
        # An orange row crossing the crop edges means an affix may be hidden.
        if bands[0][0] <= candidate_region[1] + 6 or bands[-1][1] >= candidate_region[3] - 6:
            return None
        # If another orange affix exists above or below the crop, we cannot
        # prove that all exceptional rolls were inspected.
        guard_top = (candidate_region[0], int(TOP_GUARD_START * height),
                     candidate_region[2], candidate_region[1])
        guard_bottom = (candidate_region[0], candidate_region[3],
                        candidate_region[2], int(BOTTOM_GUARD_END * height))
        if _has_orange_text_pixels(image, guard_top) or _has_orange_text_pixels(image, guard_bottom):
            return None

        lines = self._ocr(image, candidate_region)
        colored_lines: list[OcrLine] = []
        matched_bands: set[int] = set()
        for line in lines:
            matched = [
                index for index, (top, bottom) in enumerate(bands)
                if min(line.box.bottom, bottom + 7) - max(line.box.top, top - 7) >= 5
            ]
            # A single tall OCR box spanning two distinct orange rows does
            # not prove that two Exceptional affixes were fully recognized.
            if len(matched) > 1:
                return None
            if matched:
                if matched[0] in matched_bands:
                    return None
                colored_lines.append(line)
                matched_bands.add(matched[0])
        if len(matched_bands) != len(bands) or len(colored_lines) != len(bands):
            return None
        parsed: list[ParsedStat] = []
        cursor = 0
        while cursor < len(colored_lines):
            stat, consumed = self.parser._parse_stat(colored_lines, cursor, False)
            if stat is None or stat.name not in EXCEPTIONAL_SKILLS or stat.confidence < 0.75:
                return None
            parsed.append(stat)
            cursor += consumed
        if not 1 <= len(parsed) <= 2 or len({s.name for s in parsed}) != len(parsed):
            return None

        fraction = useful_exceptional_fraction(parsed)
        if fraction >= MIN_PROMISING_CAP_FRACTION:
            return None

        # Divine candidate over Immortal equipped needs an extra confirmation
        # popup. Without seeing both rarities the fast path must NOT tap.
        badge_lines = self._ocr(image, LOOT_BADGE_CROP.pixels(image.size))
        rarities = [
            line.text.strip().lower() for line in badge_lines
            if line.text.strip().lower() in RARITY_TIERS
        ]
        if len(rarities) != 2 or rarities[0] not in RARITY_TIERS or rarities[1] not in RARITY_TIERS:
            return None
        if RARITY_TIERS[rarities[1]] > RARITY_TIERS[rarities[0]]:
            return None
        return FastSellEvidence(
            stats=tuple(parsed), cap_fraction=fraction,
            rarity_equipped=rarities[0], rarity_candidate=rarities[1],
            ocr_lines=lines + badge_lines,
            crop=candidate_region,
        )
