from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from .adb import AdbDevice
from .analysis import LootAnalyzer
from .config import TARGET_PACKAGE
from .domain import AnalysisArtifacts, ComparisonStatus, ModeOutcome, Action
from .notification import PhoneNotifier
from .presentation import ConsolePresenter
from .touch import RandomizedAdbTouchController
from .vision import semantic_candidate_hash, source_region_for_lines, visual_difference, visual_signature


@dataclass(frozen=True)
class DecisionContext:
    image: Image.Image
    artifacts: AnalysisArtifacts
    candidate_hash: str


class DecisionMode(Protocol):
    def handle(self, context: DecisionContext) -> ModeOutcome: ...
    def handle_check(self, comparison) -> None: ...


class InfoMode:
    def __init__(self, notifier: PhoneNotifier | None = None) -> None:
        self.notifier = notifier

    def handle(self, context: DecisionContext) -> ModeOutcome:
        if self.notifier is not None:
            self.notifier.send(context.artifacts.comparison)
        return ModeOutcome(consume_candidate=True)

    def handle_check(self, comparison) -> None:
        if self.notifier is not None:
            self.notifier.send(comparison)


class AutoClickMode:
    def __init__(
        self,
        device: AdbDevice,
        analyzer: LootAnalyzer,
        touch: RandomizedAdbTouchController,
        presenter: ConsolePresenter,
        scale: float,
        visual_change_threshold: float,
        rng: random.Random | None = None,
    ) -> None:
        self.device = device
        self.analyzer = analyzer
        self.touch = touch
        self.presenter = presenter
        self.scale = scale
        self.visual_change_threshold = visual_change_threshold
        self.rng = rng or random.SystemRandom()

    def handle_check(self, comparison) -> None:
        return None

    def handle(self, context: DecisionContext) -> ModeOutcome:
        verified = self._fresh_verification(context)
        if verified is None:
            return ModeOutcome(consume_candidate=False, message="Auto-click cancelled: state changed before touch.")
        if self.device.foreground_package() != TARGET_PACKAGE:
            return ModeOutcome(consume_candidate=False, message="Auto-click cancelled: Dungeon Rush lost foreground.")
        self.click(verified.artifacts.comparison.action, verified.image.size)
        if(
            verified.artifacts.comparison.action is Action.SELL
            and verified.artifacts.comparison.equipped.tier == 8
            and verified.artifacts.comparison.candidate.tier == 9
        ) :
            time.sleep(0.5)
            self.click(Action.CONFIRM_SELL, verified.image.size)
#         gesture = self.touch.touch(context.artifacts.comparison.action, context.image.size)
#         self._post_touch_check(verified)
        return ModeOutcome(consume_candidate=True, touched=True)

    def click(self, action: Action, size: tuple[int, int]) -> None:
        gesture = self.touch.touch(action, size)
        if self.presenter.verbose:
            self.presenter.warning(f"touch {action.upper()} {gesture.start}->{gesture.end} · {gesture.duration_ms}ms")

    def _fresh_verification(self, context: DecisionContext) -> DecisionContext | None:
        if self.device.foreground_package() != TARGET_PACKAGE:
            return None
        image = self.device.screenshot()
        try:
            artifacts = self.analyzer.analyze(image)
        except Exception:
            return None
        comparison = artifacts.comparison
        if comparison.status is not ComparisonStatus.OK or comparison.candidate is None:
            return None
        candidate_hash = semantic_candidate_hash(comparison.candidate)
        if candidate_hash != context.candidate_hash or comparison.action is not context.artifacts.comparison.action:
            return None
        return DecisionContext(image, artifacts, candidate_hash)

    def _post_touch_check(self, context: DecisionContext) -> None:
        time.sleep(self.rng.uniform(0.16, 0.32))
        try:
            after = self.device.screenshot()
        except Exception:
            return
        region = source_region_for_lines(context.artifacts.candidate_lines, context.artifacts.popup_box, self.scale, context.image.size)
        before_sig, after_sig = visual_signature(context.image, region), visual_signature(after, region)
        if visual_difference(before_sig, after_sig) < self.visual_change_threshold:
            self.presenter.warning("Touch sent, but popup change was not visually confirmed; candidate is consumed to avoid double-clicking.")
