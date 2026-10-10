from __future__ import annotations

import argparse
from pathlib import Path

from .adb import AdbDevice
from .analysis import LootAnalyzer
from .artifacts import ArtifactWriter
from .config import (
    DEFAULT_BACKGROUND_CHECK_INTERVAL,
    DEFAULT_CANDIDATE_HASH_TTL,
    DEFAULT_RETRY_INTERVAL,
    DEFAULT_VISUAL_CHANGE_THRESHOLD,
    DEFAULT_VISUAL_SIGNATURE_TTL,
)
from .domain import ScoringStrategy
from .equipment import EquipmentStateError, JsonEquipmentRepository
from .modes import AutoClickMode, InfoMode
from .notification import PhoneNotifier
from .ocr import PaddleOcrEngine
from .presentation import ConsolePresenter
from .scoring import BuildScorer, ItemComparer
from .strategies import strategy_for
from .touch import RandomizedAdbTouchController
from .watcher import LootWatcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live Dungeon Rush loot watcher/advisor.")
    parser.add_argument("--adb", required=True, metavar="SERIAL", help="ADB device serial.")
    parser.add_argument(
        "--mode",
        choices=("info", "auto"),
        default="info",
        help="info = report only; auto = verify and click Sell/Equip.",
    )
    parser.add_argument(
        "--strategy",
        choices=tuple(strategy.value for strategy in ScoringStrategy),
        default=ScoringStrategy.UNIVERSAL.value,
        help="Build scoring strategy. Default: universal.",
    )
    parser.add_argument(
        "--equipment",
        type=Path,
        default=Path("equipment.json"),
        help="Manual current loadout. Auto mode persists successful equips back to this file.",
    )
    parser.add_argument("--device", default="gpu:0", help="Paddle device. Default: gpu:0")
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--min-confidence", type=float, default=0.20)
    parser.add_argument("--visual-change-threshold", type=float, default=DEFAULT_VISUAL_CHANGE_THRESHOLD)
    parser.add_argument("--background-check-interval", type=float, default=DEFAULT_BACKGROUND_CHECK_INTERVAL)
    parser.add_argument("--retry-interval", type=float, default=DEFAULT_RETRY_INTERVAL)
    parser.add_argument("--hash-ttl", type=float, default=None, help="TTL in seconds for both visual signature and candidate hash.")
    parser.add_argument(
        "--visual-signature-ttl",
        type=float,
        default=DEFAULT_VISUAL_SIGNATURE_TTL,
        help=f"TTL in seconds for visual signature cache (default: {DEFAULT_VISUAL_SIGNATURE_TTL:g}s).",
    )
    parser.add_argument(
        "--candidate-hash-ttl",
        type=float,
        default=DEFAULT_CANDIDATE_HASH_TTL,
        help=f"TTL in seconds for candidate hash deduplication (default: {DEFAULT_CANDIDATE_HASH_TTL:g}s).",
    )
    parser.add_argument("--adb-executable", default="adb")
    parser.add_argument("--adb-timeout", type=float, default=15.0)
    parser.add_argument("--show-ocr", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--allow-partial", action="store_true", help="Debug only; auto mode refuses this option.")
    parser.add_argument("--output-dir", type=Path, default=Path("loot_runtime"))
    parser.add_argument("--no-annotate", action="store_true")
    parser.add_argument("--phone-ssh")
    parser.add_argument("--phone-ssh-port", type=int)
    parser.add_argument("--phone-ssh-key", type=Path)
    parser.add_argument("--phone-ssh-trust-transport", action="store_true")
    parser.add_argument("--phone-toast", action="store_true")
    parser.add_argument("--phone-push", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    _validate(args)
    presenter = ConsolePresenter(args.verbose)
    equipment = _load_equipment(args.equipment)
    strategy = strategy_for(ScoringStrategy(args.strategy))
    comparer = ItemComparer(equipment, BuildScorer(strategy), allow_partial=args.allow_partial)
    device = AdbDevice(args.adb, args.adb_executable, args.adb_timeout)

    presenter.debug(f"Scoring: {args.strategy} · equipment: {args.equipment}")
    presenter.debug("Loading OCR models...")
    engine = PaddleOcrEngine(args.device, args.min_confidence, quiet=not args.verbose)
    analyzer = LootAnalyzer(engine, comparer, args.scale, args.show_ocr)
    mode = _build_mode(args, device, analyzer, presenter, equipment)
    visual_signature_ttl = args.hash_ttl if args.hash_ttl is not None else args.visual_signature_ttl
    candidate_hash_ttl = args.hash_ttl if args.hash_ttl is not None else args.candidate_hash_ttl
    watcher = LootWatcher(
        device,
        analyzer,
        mode,
        presenter,
        ArtifactWriter(args.output_dir, not args.no_annotate),
        scale=args.scale,
        visual_change_threshold=args.visual_change_threshold,
        background_check_interval=args.background_check_interval,
        retry_interval=args.retry_interval,
        visual_signature_ttl=visual_signature_ttl,
        candidate_hash_ttl=candidate_hash_ttl,
    )
    return watcher.run()


def _load_equipment(path: Path) -> JsonEquipmentRepository:
    try:
        return JsonEquipmentRepository(path)
    except EquipmentStateError as exc:
        raise SystemExit(str(exc)) from exc


def _build_mode(args, device, analyzer, presenter, equipment):
    if args.mode == "auto":
        return AutoClickMode(
            device,
            analyzer,
            RandomizedAdbTouchController(device),
            presenter,
            equipment,
            args.scale,
            args.visual_change_threshold,
        )
    return InfoMode(_build_notifier(args))


def _build_notifier(args) -> PhoneNotifier | None:
    if not args.phone_ssh or not (args.phone_toast or args.phone_push):
        return None
    return PhoneNotifier(
        args.phone_ssh,
        ssh_port=args.phone_ssh_port,
        identity_file=args.phone_ssh_key,
        trust_transport=args.phone_ssh_trust_transport,
        toast=args.phone_toast,
        push=args.phone_push,
    )


def _validate(args) -> None:
    if args.mode == "auto" and args.allow_partial:
        raise SystemExit("--allow-partial is intentionally forbidden in auto mode.")
    if args.scale < 1.0 or args.scale > 4.0:
        raise SystemExit("--scale must be between 1 and 4.")
    if args.background_check_interval <= 0 or args.retry_interval <= 0 or args.adb_timeout <= 0:
        raise SystemExit("Intervals/timeouts must be > 0.")
    if args.hash_ttl is not None and args.hash_ttl <= 0:
        raise SystemExit("--hash-ttl must be > 0.")
    if args.visual_signature_ttl <= 0 or args.candidate_hash_ttl <= 0:
        raise SystemExit("TTL values must be > 0.")
    if not 0 <= args.visual_change_threshold <= 1:
        raise SystemExit("--visual-change-threshold must be between 0 and 1.")
