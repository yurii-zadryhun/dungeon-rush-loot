from __future__ import annotations

import math

from .config import (
    BASE_SCORE_MAX,
    BASE_SCORE_MAX_LEVEL,
    BASE_SCORE_MAX_TIER,
    BASE_SCORE_MIN,
    BASE_SCORE_MIN_LEVEL,
    BASE_SCORE_MIN_TIER,
    CATEGORY_WEIGHTS,
    LEVEL_SCALER,
    MAX_STATS,
    MIN_STATS,
    SKILLS,
    TIER_SCALER,
)
from .domain import Action, Comparison, ComparisonStatus, ItemScore, ParsedItem, ScoreContribution
from .text import canonical_name


class PrimaryPowerScorer:
    def score(self, item: ParsedItem) -> float:
        if item.tier is None or item.level is None:
            raise ValueError("Rarity/tier and level are required for base-power scoring.")
        return self._normalize(self._power(item.tier, item.level))

    @staticmethod
    def _power(tier: int, level: int) -> float:
        return (TIER_SCALER ** tier) * (1.0 + LEVEL_SCALER * level)

    def _normalize(self, power: float) -> float:
        minimum = self._power(BASE_SCORE_MIN_TIER, BASE_SCORE_MIN_LEVEL)
        maximum = self._power(BASE_SCORE_MAX_TIER, BASE_SCORE_MAX_LEVEL)
        position = math.log(power / minimum) / math.log(maximum / minimum)
        return BASE_SCORE_MIN + position * (BASE_SCORE_MAX - BASE_SCORE_MIN)


class AffixScorer:
    def score(self, item: ParsedItem) -> tuple[float, tuple[ScoreContribution, ...], tuple[str, ...]]:
        contributions, unknown = [], []
        for stat in item.stats:
            contribution = self._contribution(stat.name, stat.value)
            if contribution is None:
                unknown.append(stat.raw_text)
            else:
                contributions.append(contribution)
        contributions.sort(key=lambda item: item.contribution, reverse=True)
        return sum(item.contribution for item in contributions), tuple(contributions), tuple(unknown)

    @staticmethod
    def _contribution(name: str, raw_value: float) -> ScoreContribution | None:
        canonical = canonical_name(name)
        rule = SKILLS.get(canonical)
        if rule is None or not math.isfinite(raw_value):
            return None
        value = abs(raw_value) if canonical == "critical damage taken" else max(0.0, raw_value)
        normalized = min(1.0, value / rule.cap)
        return ScoreContribution(canonical, value, normalized * CATEGORY_WEIGHTS[rule.category])


class ItemScorer:
    def __init__(self, affixes: AffixScorer | None = None, base_power: PrimaryPowerScorer | None = None) -> None:
        self.affixes = affixes or AffixScorer()
        self.base_power = base_power or PrimaryPowerScorer()

    def score(self, item: ParsedItem) -> ItemScore:
        affix_score, details, unknown = self.affixes.score(item)
        base_score = self.base_power.score(item)
        return ItemScore(affix_score + base_score, affix_score, base_score, details, unknown)


class ItemComparer:
    def __init__(self, scorer: ItemScorer | None = None, allow_partial: bool = False) -> None:
        self.scorer = scorer or ItemScorer()
        self.allow_partial = allow_partial

    def compare(self, equipped: ParsedItem, candidate: ParsedItem) -> Comparison:
        if candidate.melee:
            return self._melee_rejection(equipped, candidate)
        validation_error = self._validation_error(equipped, candidate)
        if validation_error:
            return self._check(equipped, candidate, validation_error)
        return self._scored_comparison(equipped, candidate)

    def _validation_error(self, equipped: ParsedItem, candidate: ParsedItem) -> str | None:
        if equipped.tier is None or candidate.tier is None or equipped.level is None or candidate.level is None:
            return "Could not parse rarity/level required for base-power scoring."
        if not self.allow_partial and (not self._valid_stat_count(equipped) or not self._valid_stat_count(candidate)):
            return f"Expected 4-5 stats; candidate={len(candidate.stats)}, equipped={len(equipped.stats)}."
        return None

    def _scored_comparison(self, equipped: ParsedItem, candidate: ParsedItem) -> Comparison:
        equipped_score, candidate_score = self.scorer.score(equipped), self.scorer.score(candidate)
        unknown = equipped_score.unknown + candidate_score.unknown
        if unknown and not self.allow_partial:
            return self._check(equipped, candidate, "Unknown OCR stats: " + ", ".join(unknown))
        action = Action.EQUIP if candidate_score.total > equipped_score.total + 0.01 else Action.SELL
        return Comparison(ComparisonStatus.OK, action, candidate, equipped, candidate_score, equipped_score, "Affix + calibrated base-power scoring.")

    @staticmethod
    def _valid_stat_count(item: ParsedItem) -> bool:
        return MIN_STATS <= len(item.stats) <= MAX_STATS

    @staticmethod
    def _melee_rejection(equipped: ParsedItem, candidate: ParsedItem) -> Comparison:
        return Comparison(ComparisonStatus.OK, Action.SELL, candidate, equipped, None, None, "Melee candidate hard-rejected.", "melee")

    @staticmethod
    def _check(equipped: ParsedItem, candidate: ParsedItem, message: str) -> Comparison:
        return Comparison(ComparisonStatus.CHECK_OCR, Action.CHECK, candidate, equipped, None, None, message)
