from __future__ import annotations

import re
from statistics import median
from typing import Sequence

from .config import MAX_ITEM_LEVEL, RARITY_TIERS
from .domain import Box, OcrLine, OcrSpan, ParsedItem, ParsedStat
from .game_catalog import match_standard_item
from .text import LEVEL_RE, PERCENT_RE, fuzzy_skill_name, is_melee_title, looks_like_title, normalize_text, parse_rarity


class OcrLineAssembler:
    def assemble(self, spans: Sequence[OcrSpan]) -> list[OcrLine]:
        rows = self._group_rows(spans)
        return sorted((self._line(row) for row in rows), key=lambda line: (line.box.center_y, line.box.left))

    def _group_rows(self, spans: Sequence[OcrSpan]) -> list[list[OcrSpan]]:
        if not spans:
            return []
        heights = [span.box.height for span in spans if span.box.height > 0]
        tolerance = max(6.0, (median(heights) if heights else 20.0) * 0.48)
        rows: list[list[OcrSpan]] = []
        for span in sorted(spans, key=lambda item: (item.box.center_y, item.box.left)):
            self._append_to_best_row(rows, span, tolerance)
        return rows

    @staticmethod
    def _append_to_best_row(rows: list[list[OcrSpan]], span: OcrSpan, tolerance: float) -> None:
        candidates = [(abs(span.box.center_y - sum(x.box.center_y for x in row) / len(row)), row) for row in rows]
        valid = [(distance, row) for distance, row in candidates if distance <= tolerance]
        if not valid:
            rows.append([span])
            return
        min(valid, key=lambda pair: pair[0])[1].append(span)

    @staticmethod
    def _line(row: list[OcrSpan]) -> OcrLine:
        row = sorted(row, key=lambda span: span.box.left)
        text = " ".join(normalize_text(item.text) for item in row if item.text.strip()).strip()
        total_width = sum(max(item.box.width, 1.0) for item in row)
        score = sum(item.score * max(item.box.width, 1.0) for item in row) / total_width
        box = Box(min(x.box.left for x in row), min(x.box.top for x in row), max(x.box.right for x in row), max(x.box.bottom for x in row))
        return OcrLine(text, score, box, tuple(row))


class LootCardSplitter:
    """Split the two visible loot cards without discarding separate rarity rows.

    Positions and readable item titles, not gaps between percentage values,
    delimit cards. A missing or ambiguous title must be CHECK, never a tap.
    """

    def split(self, lines: Sequence[OcrLine]) -> tuple[list[OcrLine], list[OcrLine]]:
        useful = [
            line for line in lines
            if not re.fullmatch(r"\s*(?:sell|equip|equipped)\s*", line.text, re.I)
        ]
        titles = [
            index for index, line in enumerate(useful)
            if self._is_item_title(line.text)
        ]
        if len(titles) != 2:
            raise ValueError(
                f"Expected exactly two identifiable loot-card titles, got {len(titles)}."
            )

        first_title, second_title = titles
        first_start = self._card_start(useful, first_title)
        second_start = self._card_start(useful, second_title)
        if first_start >= second_start or first_title >= second_start:
            raise ValueError("Loot-card title/rarity boundaries overlap.")

        return useful[first_start:second_start], useful[second_start:]

    @staticmethod
    def _is_item_title(text: str) -> bool:
        stripped = normalize_text(text)
        if re.fullmatch(r"\[\s*(?:range|ranged|melee|meele)\s*\]", stripped, re.I):
            return False
        if looks_like_title(stripped):
            return True
        # Desktop/Paddle may see plain item titles without an EXP marker.
        # Accept only names confidently classified by the extracted APK catalog.
        return match_standard_item([stripped]) is not None

    @staticmethod
    def _card_start(lines: Sequence[OcrLine], title_index: int) -> int:
        if title_index == 0:
            return 0
        previous = normalize_text(lines[title_index - 1].text).lower()
        return title_index - 1 if previous in RARITY_TIERS else title_index


class LootItemParser:
    def parse(self, lines: Sequence[OcrLine]) -> ParsedItem:
        title = self._title(lines)
        rarity, tier = parse_rarity(title)
        stats = tuple(self._stats(lines))
        confidences = [line.score for line in lines if line.text.strip()]
        return ParsedItem(
            title=title,
            rarity=rarity,
            tier=tier,
            level=self._level(lines),
            stats=stats,
            raw_lines=tuple(line.text for line in lines),
            average_ocr_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
            melee=any(is_melee_title(line.text) for line in lines),
        )

    def _level(self, lines: Sequence[OcrLine]) -> int | None:
        for line in lines:
            text = normalize_text(line.text)
            search_text = text[:text.find("%")] if "%" in text else text

            match = LEVEL_RE.search(search_text)
            if not match:
                continue

            level = self._normalize_ocr_level(int(match.group(1)))
            if level is not None:
                return level

        return None

    @staticmethod
    def _normalize_ocr_level(level: int) -> int | None:
        if 1 <= level <= MAX_ITEM_LEVEL:
            return level

        if 131 <= level <= 199:
            return level - 100

        return None

    @staticmethod
    def _title(lines: Sequence[OcrLine]) -> str:
        for index, line in enumerate(lines):
            text = normalize_text(line.text)
            if LootCardSplitter._is_item_title(text):
                # Game UI often prints rarity and item title in different rows:
                # "Divine" followed by "[EXP] Celestial Helmet".
                if index > 0:
                    rarity = normalize_text(lines[index - 1].text)
                    if rarity.lower() in RARITY_TIERS:
                        return f"{rarity} {text}"
                return text
        return ""

    def _stats(self, lines: Sequence[OcrLine]) -> list[ParsedStat]:
        parsed: list[ParsedStat] = []
        index = 0
        while index < len(lines):
            result, consumed_next = self._parse_stat(lines, index)
            if result is not None:
                parsed.append(result)
            index += 2 if consumed_next else 1
        return self._dedupe(parsed)

    def _parse_stat(self, lines: Sequence[OcrLine], index: int) -> tuple[ParsedStat | None, bool]:
        line = lines[index]
        source = self._percent_source(line)
        if source is None:
            return None, False
        value, remainder, source_score, raw_percent = source
        candidates = [remainder] + self._continuations(lines, index, remainder)
        chosen_name, chosen_ratio, chosen_raw = self._best_name(candidates)
        if chosen_name is None:
            return None, False
        stat = ParsedStat(chosen_name, value, f"{raw_percent} {chosen_raw}".strip(), min(source_score, chosen_ratio))
        return stat, len(candidates) > 1 and chosen_raw == candidates[1]

    def _percent_source(self, line: OcrLine) -> tuple[float, str, float, str] | None:
        sources = [(normalize_text(span.text), span.score) for span in line.spans if PERCENT_RE.search(normalize_text(span.text))]
        sources.append((normalize_text(line.text), line.score))
        for text, score in sources:
            match = PERCENT_RE.search(text)
            if match is None:
                continue
            remainder = self._clean_label(text[match.end():])
            if remainder:
                return float(match.group(1).replace(" ", "").replace(",", ".")), remainder, score, match.group(0)
        return None

    def _continuations(self, lines: Sequence[OcrLine], index: int, remainder: str) -> list[str]:
        if index + 1 >= len(lines) or PERCENT_RE.search(lines[index + 1].text):
            return []
        next_text = self._clean_label(lines[index + 1].text)
        return [f"{remainder} {next_text}".strip()] if next_text and not looks_like_title(next_text) else []

    @staticmethod
    def _best_name(candidates: list[str]) -> tuple[str | None, float, str]:
        scored = []
        for raw in candidates:
            name, ratio = fuzzy_skill_name(raw)
            scored.append((name, ratio, raw))
        return max(scored, key=lambda row: (row[1], len(row[2]))) if scored else (None, 0.0, "")

    @staticmethod
    def _clean_label(raw: str) -> str:
        text = normalize_text(raw).strip(" :-·•")
        text = re.sub(r"\s+\b(?:lvl|lv|lvi)\s*[-:.]?\s*\d{1,3}\b.*$", "", text, flags=re.I)
        text = re.sub(r"\s+\bx\d+\b.*$", "", text, flags=re.I)
        if re.fullmatch(r"(?:lvl|lv|lvi)\s*[-:.]?\s*\d{1,3}|x\d+", text, re.I):
            return ""
        return text.strip(" :-·•")

    @staticmethod
    def _dedupe(stats: list[ParsedStat]) -> list[ParsedStat]:
        seen: set[tuple[str, float]] = set()
        result: list[ParsedStat] = []
        for stat in stats:
            key = stat.name, round(stat.value, 2)
            if key not in seen:
                seen.add(key); result.append(stat)
        return result
