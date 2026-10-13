from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from .adb import AdbDevice
from .analysis import LootAnalyzer
from .config import TARGET_PACKAGE
from .domain import Action, AnalysisArtifacts, ComparisonStatus, ModeOutcome
from .equipment import JsonEquipmentRepository
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
        equipment: JsonEquipmentRepository,
        scale: float,
        visual_change_threshold: float,
        rng: random.Random | None = None,
    ) -> None:
        self.device = device
        self.analyzer = analyzer
        self.touch = touch
        self.presenter = presenter
        self.equipment = equipment
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

        comparison = verified.artifacts.comparison
        self.click(comparison.action, verified.image.size)

        if (
            comparison.action is Action.SELL
            and comparison.equipped is not None
            and comparison.candidate is not None
            and comparison.equipped.tier == 8
            and comparison.candidate.tier == 9
        ):
            time.sleep(0.5)
            self.click(Action.CONFIRM_SELL, verified.image.size)

        if comparison.action is Action.EQUIP:
            if not self._post_touch_changed(verified):
                return ModeOutcome(
                    consume_candidate=True,
                    touched=True,
                    message=(
                        "Equip touch sent, but popup change was not visually confirmed; "
                        "equipment.json was not updated. Inspect the game/state before continuing."
                    ),
                )
            if comparison.equipment_slot is None or comparison.candidate is None:
                return ModeOutcome(
                    consume_candidate=True,
                    touched=True,
                    message="Equip touch sent, but comparison did not carry a resolvable equipment slot.",
                )
            self.equipment.replace(comparison.equipment_slot, comparison.candidate)
            return ModeOutcome(
                consume_candidate=True,
                touched=True,
                message=f"Equipment state updated: {comparison.equipment_slot.value}.",
            )

        return ModeOutcome(consume_candidate=True, touched=True)

    def click(self, action: Action, size: tuple[int, int]) -> None:
        gesture = self.touch.touch(action, size)
        if self.presenter.verbose:
            self.presenter.warning(
                f"touch {action.value.upper()} {gesture.start}->{gesture.end} · {gesture.duration_ms}ms"
            )

    def _fresh_verification(self, context: DecisionContext) -> DecisionContext | None:
        if self.device.foreground_package() != TARGET_PACKAGE:
            return None
        image = self.device.screenshot()
        if image.size != context.image.size:
            return None
        # The candidate card contains all item rarity/level/affix pixels.
        # When its actual pixels remain stable, rerunning a slow neural OCR
        # cannot improve verification. If pixels changed or the visual test
        # is uncertain, fall back to a full new OCR + semantic comparison.
        region = source_region_for_lines(
            context.artifacts.candidate_lines,
            context.artifacts.popup_box,
            self.scale,
            image.size,
        )
        before = visual_signature(context.image, region)
        after = visual_signature(image, region)
        if visual_difference(before, after) <= 0.005:
            return DecisionContext(image, context.artifacts, context.candidate_hash)
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

    def _post_touch_changed(self, context: DecisionContext) -> bool:
        region = source_region_for_lines(
            context.artifacts.candidate_lines,
            context.artifacts.popup_box,
            self.scale,
            context.image.size,
        )
        before_signature = visual_signature(context.image, region)
        for _ in range(3):
            time.sleep(self.rng.uniform(0.12, 0.22))
            if self.device.foreground_package() != TARGET_PACKAGE:
                return False
            try:
                after = self.device.screenshot()
            except Exception:
                continue
            after_signature = visual_signature(after, region)
            if visual_difference(before_signature, after_signature) >= self.visual_change_threshold:
                return True
        return False
