from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from .adb import AdbDevice
from .domain import Action
from .ui_geometry import LOOT_UI, RelativeRect


@dataclass(frozen=True)
class Gesture:
    start: tuple[int, int]
    end: tuple[int, int]
    duration_ms: int
    pre_delay_seconds: float


class LootButtonLayout:
    def target(self, action: Action) -> RelativeRect:
        return LOOT_UI.target(action)


class HumanGestureGenerator:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.SystemRandom()

    def generate(self, rect: RelativeRect, size: tuple[int, int]) -> Gesture:
        bounds = rect.pixels(size)
        start = self._point(bounds)
        end = self._nearby_point(start, bounds)
        return Gesture(start, end, self.rng.randint(55, 125), self.rng.uniform(0.08, 0.22))

    def _point(self, bounds: tuple[int, int, int, int]) -> tuple[int, int]:
        left, top, right, bottom = bounds
        return self.rng.randint(left, right), self.rng.randint(top, bottom)

    def _nearby_point(self, start: tuple[int, int], bounds: tuple[int, int, int, int]) -> tuple[int, int]:
        angle, distance = self.rng.uniform(0, math.tau), self.rng.uniform(1.0, 9.0)
        raw = round(start[0] + math.cos(angle) * distance), round(start[1] + math.sin(angle) * distance)
        left, top, right, bottom = bounds
        return min(right, max(left, raw[0])), min(bottom, max(top, raw[1]))


class RandomizedAdbTouchController:
    """Desktop touch adapter implemented with ADB."""

    def __init__(self, device: AdbDevice, layout: LootButtonLayout | None = None, gestures: HumanGestureGenerator | None = None) -> None:
        self.device = device
        self.layout = layout or LootButtonLayout()
        self.gestures = gestures or HumanGestureGenerator()

    def touch(self, action: Action, screen_size: tuple[int, int]) -> Gesture:
        gesture = self.gestures.generate(self.layout.target(action), screen_size)
        time.sleep(gesture.pre_delay_seconds)
        self.device.swipe(gesture.start, gesture.end, gesture.duration_ms)
        time.sleep(gesture.pre_delay_seconds)
        return gesture
