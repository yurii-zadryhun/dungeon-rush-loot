from __future__ import annotations

import re
from statistics import median
from typing import Sequence

from .config import MAX_ITEM_LEVEL, RARITY_TIERS, SKILLS
from .domain import Box, OcrLine, OcrSpan, ParsedItem, ParsedStat
from .game_catalog import match_standard_item
from .text import LEVEL_RE, PERCENT_RE, fuzzy_skill_name, is_melee_title, looks_like_title, normalize_text, parse_rarity


# Recognition can lose the percent glyph or render it as l/I/°.
# The numeric digits remain strict, and missing percent is accepted only with
# an explicit +/- sign, an unambiguous known skill, and an in-range value.
STAT_NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<number>[+-]?\s*\d{1,3}[.,]\d{1,2})"
    r"\s*(?P<suffix>%(?:\s*%)*|[lI]\s*%+|[lI]\.|[°º]|[lIoO](?=\s))?(?=\s|$|[A-Za-z])",
    re.I,
)
# Lv0124 and LvU 106 were observed on the Android device. Only the
# zero-prefixed 3-digit form is accepted; ordinary Lv0 is not a level.
LEVEL_MARKER_RE = re.compile(
    # ML Kit's "LU1O6" and "LU 106" are narrow observed variants of Lvl 106.
    # Repair O ONLY inside the explicit level token, never in affix numbers.
    r"\b(?:lvl|lvi|lvu|lu|lv0(?=1[0-2]\d\b)|lv)\s*[-:.]?\s*(?P<level>\d{1,3}|\dO\d)\b",
    re.I,
)
# Observed ML Kit live OCR: "LvI 124 •7.32 Ranged Damage".
# A bullet is recovered as a positive separator ONLY when an explicit level
# marker occurs on the same row, followed by an intact decimal stat value.
LEVEL_ROW_BULLET_SIGN_RE = re.compile(
    r"^[•·]\s*(?=\d{1,3}[.,]\d{1,2}(?:\s|%|$))"
)
NEGATIVE_ONLY_SKILLS = frozenset({"critical damage taken", "companion cooldown"})


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
            index for index in range(len(useful))
            if self._title_at(useful, index) is not None
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
        if not LootCardSplitter._title_fragment(stripped):
            return False
        match = match_standard_item([stripped])
        if match is None:
            return False
        # "Backpack" or "Gloves" alone are NOT identifying item titles.
        return match.exact or match.confidence >= 0.94

    @classmethod
    def _title_at(cls, lines: Sequence[OcrLine], index: int) -> str | None:
        text = normalize_text(lines[index].text)
        if index > 0:
            previous = normalize_text(lines[index - 1].text)
            if (
                cls._title_fragment(previous)
                and cls._title_fragment(text)
                and not cls._is_item_title(previous)
                and not cls._is_item_title(text)
                and match_standard_item([previous + " " + text]) is not None
            ):
                # This row completes a two-line title already discovered at
                # index-1; it is not the title of a second loot card.
                return None

        if cls._is_item_title(text):
            return text

        # Wrapped [EXP] item names are common on 709px screens, e.g.
        # "[EXP] +11 Crimson" / "Backpack". Both fragments must reconstruct a
        # known catalog name. Unknown, partial titles remain CHECK/no action.
        if index + 1 >= len(lines) or not cls._title_fragment(text):
            return None
        following = normalize_text(lines[index + 1].text)
        if not cls._title_fragment(following) or cls._is_item_title(following):
            # E.g. "Taken" from a wrapped Critical Damage Taken affix
            # followed by a complete "Immortal [EXP] Scarlet Necklace".
            return None
        combined = f"{text} {following}"
        return combined if match_standard_item([combined]) is not None else None

    @staticmethod
    def _title_fragment(value: str) -> bool:
        text = normalize_text(value)
        if not text or text.lower() in RARITY_TIERS:
            return False
        if text.lower() in {"equipped", "equip", "sell"}:
            return False
        if LEVEL_RE.search(text) or PERCENT_RE.search(text) or STAT_NUMBER_RE.search(text):
            return False
        if re.match(r"^\s*(?:damage|health)\s+\d", text, re.I):
            return False
        if re.fullmatch(r"\[\s*(?:range|ranged|melee|meele)\s*\]", text, re.I):
            return False
        return True

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
        # A game HUD "Lvl 123" sometimes remains visible to the right of the
        # loot popup. Ignore only standalone level spans clearly outside the
        # stat-text boundary, not contradictory levels inside the card.
        stat_rights = [
            line.box.right for line in lines
            if STAT_NUMBER_RE.search(self._strip_level_marker(normalize_text(line.text)))
            and ("%" in line.text or "+" in line.text or "-" in line.text)
        ]
        right_boundary = max(stat_rights) if stat_rights else None
        levels: set[int] = set()
        for line in lines:
            text = normalize_text(line.text)
            matches = list(LEVEL_MARKER_RE.finditer(text))
            if not matches:
                continue
            remainder = self._strip_level_marker(text).strip(" ()")
            if (
                not remainder and right_boundary is not None
                and line.box.left > right_boundary + 20
            ):
                continue
            for match in matches:
                number = match.group("level").upper().replace("O", "0")
                level = self._normalize_ocr_level(int(number))
                if level is not None:
                    levels.add(level)
        return next(iter(levels)) if len(levels) == 1 else None

    @staticmethod
    def _normalize_ocr_level(level: int) -> int | None:
        if 1 <= level <= MAX_ITEM_LEVEL:
            return level

        if 131 <= level <= 199:
            return level - 100

        return None

    @staticmethod
    def _title(lines: Sequence[OcrLine]) -> str:
        for index in range(len(lines)):
            title = LootCardSplitter._title_at(lines, index)
            if title is None:
                continue
            if index > 0:
                rarity = normalize_text(lines[index - 1].text)
                if rarity.lower() in RARITY_TIERS:
                    return f"{rarity} {title}"
            return title
        return ""

    def _stats(
        self, lines: Sequence[OcrLine], *, allow_cape_primaries: bool = False,
    ) -> list[ParsedStat]:
        """Parse stat rows without inferring or changing numeric digits."""
        parsed: list[ParsedStat] = []
        index = 0
        while index < len(lines):
            stat, consumed = self._parse_stat(lines, index, allow_cape_primaries)
            if stat is not None:
                parsed.append(stat)
            index += consumed
        # Do not erase duplicated/contradictory OCR rolls before validation.
        # On 2-affix gear that could turn an invalid 3-row card into OK.
        return parsed

    def _parse_stat(
        self, lines: Sequence[OcrLine], index: int, allow_cape_primaries: bool,
    ) -> tuple[ParsedStat | None, int]:
        line = lines[index]
        # Numbers can appear after "Lvl 87" on the same physical OCR line.
        observed = normalize_text(line.text)
        clean = self._strip_level_marker(observed)
        if LEVEL_MARKER_RE.search(observed):
            # Do not guess numbers: preserve the intact two-decimal value.
            # The known positive-only skill and cap are checked below.
            clean = LEVEL_ROW_BULLET_SIGN_RE.sub("+", clean, count=1)
        match = STAT_NUMBER_RE.search(clean)
        if match is None:
            return None, 1

        numeric = match.group("number")
        suffix = (match.group("suffix") or "").strip()
        value = float(numeric.replace(" ", "").replace(",", "."))
        remainder = self._clean_label(clean[match.end():])
        # Only a real percent or a close visual glyph variant counts as a
        # recognized separator. Wholly missing separators require a sign.
        repaired_separator = not suffix.startswith("%")
        if repaired_separator and not numeric.lstrip().startswith(("+", "-")):
            return None, 1

        candidates: list[tuple[str, int]] = [(remainder, 1)]
        candidates.extend(self._continuations(lines, index, remainder))

        ranked: list[tuple[float, int, str, str]] = []
        for label, consumed in candidates:
            name, ratio = fuzzy_skill_name(label)
            if name is None:
                continue
            # Never infer a missing percent from a poor/ambiguous name match.
            if repaired_separator and ratio < 0.93:
                continue
            if not self._valid_stat_value(name, value, allow_cape_primaries):
                continue
            ranked.append((ratio, consumed, name, label))

        if not ranked:
            return None, 1
        ratio, consumed, name, raw_label = max(
            ranked, key=lambda entry: (entry[0], -entry[1])
        )
        if repaired_separator:
            # We recovered the separator, NOT the number. Keep original text
            # and signal reduced certainty relative to an intact percent glyph.
            confidence = min(line.score, ratio, 0.93)
        else:
            confidence = min(line.score, ratio)
        return ParsedStat(name, value, line.text, confidence), consumed

    @staticmethod
    def _strip_level_marker(text: str) -> str:
        return LEVEL_MARKER_RE.sub(" ", text).strip()

    def _continuations(
        self, lines: Sequence[OcrLine], index: int, remainder: str,
    ) -> list[tuple[str, int]]:
        # ML Kit sometimes places the level between a percentage and its
        # textual label. Inspect at most two following physical rows.
        additions: list[tuple[str, int]] = []
        parts = [remainder] if remainder else []
        for lookahead in (1, 2):
            next_index = index + lookahead
            if next_index >= len(lines):
                break
            text = normalize_text(lines[next_index].text)
            if LEVEL_MARKER_RE.fullmatch(text):
                continue
            if STAT_NUMBER_RE.search(text) or PERCENT_RE.search(text):
                break
            if looks_like_title(text) or text.lower() in RARITY_TIERS:
                break
            if re.match(r"^\s*(?:damage|health)\s+\d", text, re.I):
                break
            if text.lower() in {"sell", "equip", "equipped"}:
                break
            cleaned = self._clean_label(text)
            if not cleaned:
                break
            parts.append(cleaned)
            additions.append((" ".join(parts), lookahead + 1))
        return additions

    @staticmethod
    def _valid_stat_value(
        name: str, value: float, allow_cape_primaries: bool,
    ) -> bool:
        # Intrinsic Cape Damage/Health are NOT rolled affixes. A later
        # progression check must match their exact expected values.
        if allow_cape_primaries and name in {"damage", "health"} and 0 < value <= 500:
            return True
        rule = SKILLS.get(name)
        if rule is None or not 0.01 <= abs(value) <= rule.cap + 0.05:
            return False
        return (value < 0) if name in NEGATIVE_ONLY_SKILLS else (value > 0)

    @staticmethod
    def _clean_label(raw: str) -> str:
        text = LEVEL_MARKER_RE.sub(" ", normalize_text(raw))
        # Rare ML Kit lines contain the game's adjacent x4 reward badge
        # appended to an otherwise complete affix: "Attack Speed BSX4".
        # Strip ONLY a trailing, visually identified badge, never free-form
        # unrecognized words or digits inside an affix name.
        text = re.sub(r"\s+B[S]?X4\s*$", "", text, flags=re.I)
        return re.sub(r"\s+", " ", text).strip(" :-·•")
    
    @staticmethod
    def _dedupe(stats: list[ParsedStat]) -> list[ParsedStat]:
        seen: set[tuple[str, float]] = set()
        result: list[ParsedStat] = []
        for stat in stats:
            key = stat.name, round(stat.value, 2)
            if key not in seen:
                seen.add(key); result.append(stat)
        return result
