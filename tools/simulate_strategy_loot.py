#!/usr/bin/env python3
"""Greedy EXP-only loot stress test using the production build-aware scorer.

Synthetic, not a drop-rate forecast: rarity is sampled 50/50 Immortal/Divine;
slot and level (1..130) uniform; non-zero affix percentages uniform to their
configured caps. Each sample has exactly 3 normal and 1 or 2 distinct
exceptional affixes. Wings and cape are unchanged.

Run:
    python -m tools.simulate_strategy_loot --iterations 50000 --seed 20261011
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.affix_rules import validate_affixes
from src.config import EXCEPTIONAL_SKILLS, MAX_ITEM_LEVEL, RARITY_TIERS, SKILLS
from src.domain import EquipmentSlot, ParsedItem, ParsedStat, ScoringStrategy
from src.equipment import EquipmentCodec, EquipmentLoadout
from src.scoring import BuildScorer
from src.strategies import strategy_for

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EQUIPMENT = ROOT / "tests" / "fixtures" / "strategy_start_equipment.json"
STANDARD_SLOTS = (
    EquipmentSlot.WEAPON, EquipmentSlot.HELMET, EquipmentSlot.BACKPACK,
    EquipmentSlot.GLOVES, EquipmentSlot.NECKLACE, EquipmentSlot.RING,
)
NAMES = {
    EquipmentSlot.WEAPON: "Tyrant Staff",  # ranged-only; melee is rejected in Auto
    EquipmentSlot.HELMET: "Celestial Helmet",
    EquipmentSlot.BACKPACK: "Crimson Backpack",
    EquipmentSlot.GLOVES: "Crimson Gloves",
    EquipmentSlot.NECKLACE: "Dread Necklace",
    EquipmentSlot.RING: "Void Ring",
}
NORMAL = tuple(sorted(set(SKILLS) - set(EXCEPTIONAL_SKILLS)))
EXCEPTIONAL = tuple(sorted(EXCEPTIONAL_SKILLS))
NEGATIVE_STATS = frozenset({"critical damage taken", "companion cooldown"})
PROFILES = (
    ScoringStrategy.PVP, ScoringStrategy.PVE, ScoringStrategy.UNIVERSAL,
)


def random_item(rng: random.Random) -> tuple[EquipmentSlot, ParsedItem]:
    slot = rng.choice(STANDARD_SLOTS)
    rarity = rng.choice(("Immortal", "Divine"))
    level = rng.randint(1, MAX_ITEM_LEVEL)
    names = (*rng.sample(NORMAL, 3), *rng.sample(EXCEPTIONAL, rng.randint(1, 2)))
    stats = []
    for name in names:
        cap = int(round(SKILLS[name].cap * 100))
        value = rng.randint(1, cap) / 100
        if name in NEGATIVE_STATS:
            value = -value
        stats.append(ParsedStat(name, value, f"{value:+.2f}% {name}", 1.0))
    result = ParsedItem(
        title=f"{rarity} [EXP] +11 {NAMES[slot]}",
        rarity=rarity,
        tier=RARITY_TIERS[rarity.lower()],
        level=level,
        stats=tuple(stats),
        raw_lines=(),
        average_ocr_confidence=1.0,
        melee=False,
    )
    return slot, result


@dataclass
class SimulationResult:
    strategy: str
    iterations: int
    equipped: int
    sold: int
    by_slot: dict[str, int]
    final: EquipmentLoadout
    score_total: float
    score_combat: float
    score_flexibility_by_slot: dict[str, float]


def run_strategy(
    drops: Iterable[tuple[EquipmentSlot, ParsedItem]],
    start: EquipmentLoadout,
    strategy: ScoringStrategy,
    iterations: int,
) -> SimulationResult:
    scorer = BuildScorer(strategy_for(strategy))
    loadout = start
    equipped = 0
    rejected = 0
    by_slot: Counter[str] = Counter()
    baseline_cache: dict[EquipmentSlot, float] = {}

    # This is exactly the same > 0.01 build-score comparison as ItemComparer:
    # current and candidate are scored with protected_slot=slot, including
    # the replacement flexibility term. Only deterministic, validated items
    # are passed to this hot path (unit-tested against ItemComparer).
    for slot, candidate in drops:
        if validate_affixes(candidate.title, candidate.stats, rarity=candidate.rarity, slot=slot):
            raise ValueError(f"Generator created invalid affixes: {candidate}")
        if slot not in baseline_cache:
            baseline_cache[slot] = scorer.score(loadout, protected_slot=slot).total
        next_loadout = loadout.with_replacement(slot, candidate)
        candidate_score = scorer.score(next_loadout, protected_slot=slot).total
        if candidate_score > baseline_cache[slot] + 0.01:
            loadout = next_loadout
            equipped += 1
            by_slot[slot.value] += 1
            # Changing any item changes each protected-slot build score.
            baseline_cache.clear()
        else:
            rejected += 1

    score = scorer.score(loadout)
    return SimulationResult(
        strategy=strategy.value,
        iterations=iterations,
        equipped=equipped,
        sold=rejected,
        by_slot={slot.value: by_slot[slot.value] for slot in STANDARD_SLOTS},
        final=loadout,
        score_total=score.total,
        score_combat=score.combat,
        score_flexibility_by_slot={
            slot.value: scorer.score(loadout, protected_slot=slot).flexibility
            for slot in STANDARD_SLOTS
        },
    )


def simulate(iterations: int = 50_000, seed: int = 20261011,
             fixture: Path = DEFAULT_EQUIPMENT) -> dict:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    start = EquipmentCodec.loads_json(fixture.read_text(encoding="utf-8"))
    rng = random.Random(seed)
    # Reuse EXACTLY the same 50,000 generated drops for each strategy.
    drops = tuple(random_item(rng) for _ in range(iterations))
    generated = {
        "rarities": dict(Counter(item.rarity for _, item in drops)),
        "exceptional_counts": dict(sorted(Counter(
            sum(stat.name in EXCEPTIONAL_SKILLS for stat in item.stats)
            for _, item in drops
        ).items())),
        "slots": {slot.value: sum(s is slot for s, _ in drops) for slot in STANDARD_SLOTS},
    }
    outcomes = [
        run_strategy(drops, start, strategy, iterations) for strategy in PROFILES
    ]
    cross_scores = {
        outcome.strategy: {
            strategy.value: round(BuildScorer(strategy_for(strategy)).score(outcome.final).total, 3)
            for strategy in PROFILES
        }
        for outcome in outcomes
    }
    results = {}
    for outcome in outcomes:
        metrics = BuildScorer(strategy_for(ScoringStrategy.PVP)).aggregator.aggregate(outcome.final)
        results[outcome.strategy] = {
            "equips": outcome.equipped,
            "sells": outcome.sold,
            "equips_by_slot": outcome.by_slot,
            "own_objective_score": round(outcome.score_total, 3),
            "objective_combat": round(outcome.score_combat, 3),
            "replacement_flexibility_by_slot": {
                key: round(value, 3)
                for key, value in outcome.score_flexibility_by_slot.items()
            },
            "primary_attack": round(metrics.base_attack, 4),
            "primary_health": round(metrics.base_health, 4),
            "total_stats": {
                name: round(value, 2)
                for name, value in sorted(metrics.stats.items())
            },
            "final_equipment": EquipmentCodec.to_payload(outcome.final),
        }
    return {
        "seed": seed,
        "iterations_per_strategy": iterations,
        "random_model": {
            "rarity": "Immortal/Divine each 50%",
            "level": "uniform integer 1..130",
            "slot": "uniform over six standard slots; Wings and Cape fixed",
            "rolls": "3 unique normal + 1 or 2 unique exceptional",
            "values": "uniform discrete hundredths (0.01..configured cap)",
            "auto_melee": "no melee weapons; only ranged Tyrant Staff",
            "decision_rule": "production build scorer with protected slot; EQUIP iff delta > 0.01",
        },
        "generated": generated,
        "cross_profile_scores": cross_scores,
        "results": results,
    }


def markdown_report(data: dict) -> str:
    n = data["iterations_per_strategy"]
    lines = [
        f"# Dungeon Rush EXP equipment simulation — {n:,} drops / profile",
        "",
        f"Seed: \`{data['seed']}\` • all profiles saw the identical {n:,} items.",
        "",
        "**Synthetic model:** 50/50 Immortal/Divine, uniform levels 1–130,"
        " uniform rolls within caps, exactly 3 normal and 1–2 exceptional affixes."
        " Only six standard slots rotate; original Eternal Wings and Divine Cloak are fixed.",
        "",
        "## Decisions",
        "",
        "| Profile | EQUIP | SELL | Own score |",
        "|---|---:|---:|---:|",
    ]
    for profile, result in data["results"].items():
        lines.append(f"| {profile} | {result['equips']} | {result['sells']} | {result['own_objective_score']:.1f} |")
    lines.extend([
        "",
        "## Cross-evaluation (same scorer applied to each resulting build)",
        "",
        "| Built by | PVP score | PVE score | Universal score |",
        "|---|---:|---:|---:|",
    ])
    for profile, row in data["cross_profile_scores"].items():
        lines.append(f"| {profile} | {row['pvp']:.2f} | {row['pve']:.2f} | {row['universal']:.2f} |")
    for profile, result in data["results"].items():
        lines.extend([
            "",
            f"## {profile.upper()} final six-slot equipment",
            "",
            "| Slot | Rarity | Level | Normal affixes | Exceptional affixes |",
            "|---|---|---:|---|---|",
        ])
        for slot in STANDARD_SLOTS:
            item = result["final_equipment"][slot.value]
            normal = ", ".join(f"{k} {v:+g}%" for k, v in item["stats"].items()
                               if k not in EXCEPTIONAL_SKILLS)
            exceptional = ", ".join(f"{k} {v:+g}%" for k, v in item["stats"].items()
                                    if k in EXCEPTIONAL_SKILLS)
            lines.append(
                f"| {slot.value} | {item['rarity']} | {item['level']} | {normal} | {exceptional} |"
            )
        lines.extend([
            "",
            "**Final total stats:** " + "; ".join(
                f"{k}: {v:g}%" for k, v in result["total_stats"].items()
            ),
            "",
        ])
    lines.extend([
        "## Interpretation limits",
        "",
        "- This probes the **current deterministic strategy**, not real game drop odds.",
        "- The current PVP opponent profile assumes 100% enemy Critical Damage Taken reduction.",
        "- Scores across different strategies are not directly comparable; cross-score each build in the same column.",
        "- A single seeded 50,000-drop experiment measures one trajectory, not statistical confidence.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=20261011)
    parser.add_argument("--equipment", type=Path, default=DEFAULT_EQUIPMENT)
    parser.add_argument("--output", type=Path, default=Path("dist/strategy-simulation"))
    args = parser.parse_args()
    data = simulate(args.iterations, args.seed, args.equipment)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown_report(data) + "\n", encoding="utf-8")
    print(markdown_report(data), flush=True)
    print(f"\nSaved: {args.output.with_suffix('.json')} / {args.output.with_suffix('.md')}", flush=True)


if __name__ == "__main__":
    main()
