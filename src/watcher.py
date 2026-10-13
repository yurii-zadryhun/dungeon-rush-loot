from __future__ import annotations

import time

from .adb import AdbDevice
from .analysis import LootAnalyzer
from .artifacts import ArtifactWriter
from .config import DEFAULT_CANDIDATE_HASH_TTL, DEFAULT_VISUAL_SIGNATURE_TTL, TARGET_PACKAGE
from .domain import Action, Comparison, ComparisonStatus, ScoringStrategy, WatchState
from .modes import DecisionContext, DecisionMode
from .parsing import LootCardTitleCountError
from .fast_sell import FastExceptionalSellProbe
from .modes import AutoClickMode
from .presentation import ConsolePresenter
from .vision import semantic_candidate_hash, source_region_for_lines, visual_difference, visual_signature


class LootWatcher:
    def __init__(
        self,
        device: AdbDevice,
        analyzer: LootAnalyzer,
        mode: DecisionMode,
        presenter: ConsolePresenter,
        artifacts: ArtifactWriter,
        *,
        scale: float,
        visual_change_threshold: float,
        background_check_interval: float,
        retry_interval: float,
        visual_signature_ttl: float = DEFAULT_VISUAL_SIGNATURE_TTL,
        candidate_hash_ttl: float = DEFAULT_CANDIDATE_HASH_TTL,
        decision_log=None,
    ) -> None:
        self.device = device
        self.analyzer = analyzer
        self.mode = mode
        self.presenter = presenter
        self.artifacts = artifacts
        self.scale = scale
        self.visual_change_threshold = visual_change_threshold
        self.background_check_interval = background_check_interval
        self.retry_interval = retry_interval
        self.visual_signature_ttl = visual_signature_ttl
        self.candidate_hash_ttl = candidate_hash_ttl
        self.decision_log = decision_log
        self.state = WatchState()
        # The same full Python comparer remains authoritative for any
        # promising/uncertain item. This optional cheap SELL gate is auto-only.
        strategy = getattr(self.analyzer.decision_engine.comparer, "scorer", None)
        self.quick_probe = (
            FastExceptionalSellProbe(self.analyzer.engine, scale=self.scale)
            if isinstance(mode, AutoClickMode)
            and strategy is not None
            and strategy.strategy.name is ScoringStrategy.UNIVERSAL
            else None
        )

    def run(self) -> int:
        self.presenter.debug("Ready. No fixed foreground polling delay; ADB I/O sets the pace. Ctrl+C to stop.")

        try:
            while True:
                self._cycle()
        except KeyboardInterrupt:
            self.presenter.debug("Stopped.")
            return 0

    def _cycle(self) -> None:
        if not self._ensure_foreground():
            time.sleep(self.background_check_interval)
            return
        try:
            self._process_frame(self.device.screenshot())
        except LootCardTitleCountError:
            self.state.reset_visual_gate()
            time.sleep(self.retry_interval)
        except Exception as exc:
            self.state.reset_visual_gate()
            self._report_error(exc)
            time.sleep(self.retry_interval)

    def _ensure_foreground(self) -> bool:
        active = self.device.foreground_package() == TARGET_PACKAGE
        if active != self.state.foreground:
            self.state.foreground = active
            self.state.reset_visual_gate()
            self.presenter.foreground(active)
        return active

    def _process_frame(self, image) -> None:
        if self._unchanged(image):
            return
        if self.quick_probe is not None:
            try:
                evidence = self.quick_probe.probe(image)
            except Exception as exc:
                # Any uncertain fast probe must fall back to the proven full
                # OCR/parser path, never authorize SELL based on partial data.
                if self.presenter.verbose:
                    self.presenter.warning(f"Fast OCR unavailable; full OCR fallback: {exc}")
                evidence = None
            if evidence is not None and self.mode.quick_sell(image, evidence.crop):
                names = ", ".join(f"{s.name} {abs(s.value):.2f}%" for s in evidence.stats)
                comparison = Comparison(
                    status=ComparisonStatus.OK,
                    action=Action.SELL,
                    candidate=None, equipped=None,
                    candidate_score=None, equipped_score=None,
                    message=(f"Fast Exceptional SELL: {names}; "
                             f"cap coverage {evidence.cap_fraction:.0%} < 90%."),
                    rejection_reason="fast_exceptional",
                )
                self.presenter.result(comparison)
                if self.decision_log is not None:
                    self.decision_log.append(
                        comparison, source="desktop", ocr_lines=evidence.ocr_lines,
                    )
                self.state.last_success_region = evidence.crop
                self.state.last_success_signature = visual_signature(image, evidence.crop)
                self.state.last_success_signature_at = time.monotonic()
                self.state.last_error_key = None
                return
        artifacts = self.analyzer.analyze(image)
        comparison = artifacts.comparison
        if comparison.status is not ComparisonStatus.OK or comparison.candidate is None:
            self.state.reset_visual_gate()
            self._report_check(image, artifacts)
            time.sleep(self.retry_interval)
            return
        candidate_hash = semantic_candidate_hash(comparison.candidate)
        if self._is_candidate_same(candidate_hash):
            self._commit_visual_gate(image, artifacts)
            return
        self.presenter.result(comparison)
        self._save_diagnostics(image, artifacts)
        outcome = self.mode.handle(DecisionContext(image, artifacts, candidate_hash))
        if outcome.message and self.presenter.verbose:
            self.presenter.warning(outcome.message)
        if outcome.consume_candidate:
            self.state.last_candidate_hash = candidate_hash
            self.state.last_candidate_hash_at = time.monotonic()
            self._commit_visual_gate(image, artifacts)
        else:
            self.state.reset_visual_gate()

    def _unchanged(self, image) -> bool:
        if self.state.last_success_region is None or self.state.last_success_signature is None:
            return False
        if self.visual_signature_ttl > 0 and (time.monotonic() - self.state.last_success_signature_at) >= self.visual_signature_ttl:
            self.state.reset_visual_gate()
            return False
        current = visual_signature(image, self.state.last_success_region)
        return visual_difference(self.state.last_success_signature, current) < self.visual_change_threshold

    def _is_candidate_same(self, candidate_hash: str) -> bool:
        if self.state.last_candidate_hash is None or self.state.last_candidate_hash != candidate_hash:
            return False
        if self.candidate_hash_ttl <= 0:
            return True
        return (time.monotonic() - self.state.last_candidate_hash_at) < self.candidate_hash_ttl

    def _commit_visual_gate(self, image, artifacts) -> None:
        region = source_region_for_lines(artifacts.candidate_lines, artifacts.popup_box, self.scale, image.size)
        self.state.last_success_region = region
        self.state.last_success_signature = visual_signature(image, region)
        self.state.last_success_signature_at = time.monotonic()
        self.state.last_error_key = None

    def _save_diagnostics(self, image, artifacts) -> None:
        self.artifacts.save(image, artifacts, self.scale)
        if self.decision_log is not None:
            self.decision_log.append(
                artifacts.comparison, source="desktop", ocr_lines=artifacts.popup_lines,
                rarity_level_passes=artifacts.rarity_level_passes,
                rarity_level_annotated_image=self.artifacts.rarity_level_image_path(artifacts),
            )

    def _report_check(self, image, artifacts) -> None:
        comparison = artifacts.comparison
        key = comparison.message
        now = time.monotonic()
        if key != self.state.last_error_key or now - self.state.last_error_at >= 10.0:
            self.presenter.result(comparison)
            self._save_diagnostics(image, artifacts)
            self.mode.handle_check(comparison)
            self.state.last_error_key, self.state.last_error_at = key, now

    def _report_error(self, exc: Exception) -> None:
        key, now = f"{type(exc).__name__}: {exc}", time.monotonic()
        if self.presenter.verbose and (key != self.state.last_error_key or now - self.state.last_error_at >= 10.0):
            self.presenter.warning(f"RETRY · {exc}")
            self.state.last_error_key, self.state.last_error_at = key, now
