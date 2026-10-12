#!/usr/bin/env python3
"""Exact MILP feasibility + attainable offline alternative for seeded EXP drops.

This is a LOOK-AHEAD REFERENCE, not a replacement for the live EQUIP/SELL
algorithm. The offline selector can retain any of the 50k drops, irrespective
of chronological order, while the live watcher immediately sells rejected gear.

The full-target feasibility/maxima are proven for the enumerated 4T+4M and
3T+5M allocations, with 2 CDT, 1 ranged defense and 1 melee defense. The
balanced candidate maximizes a stated *linear proxy* subject to constraints;
it is NOT claimed to globally maximize the nonlinear Universal score.

Usage:
  python -m tools.offline_universal_benchmark --output dist/offline-universal-50k
"""
from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

from src.config import EXCEPTIONAL_SKILLS, SKILLS
from src.domain import EquipmentSlot, ParsedItem, ScoringStrategy
from src.equipment import EquipmentCodec, EquipmentLoadout
from src.scoring import BuildScorer
from src.strategies import strategy_for
from tools.simulate_strategy_loot import (
    DEFAULT_EQUIPMENT, STANDARD_SLOTS, random_item, run_strategy,
)
import random

SEED = 20261011
ITERATIONS = 50_000
CDT = "critical damage taken"
RANGED = "ranged defense"
MELEE = "melee defense"
TRIPLE = "triple hit chance"
MEGA = "mega crit chance"
ROLES = (CDT, RANGED, MELEE, TRIPLE, MEGA)
PRIORITY_NORMALS = (
    "attack speed", "critical damage", "critical chance", "damage",
    "ranged damage", "lifesteal", "block chance", "health",
)
NORMAL_WEIGHTS = (15.0, 15.0, 10.0, 5.0, 5.0, 2.0, 2.0, 2.0)


@dataclass(frozen=True)
class IndexedDrop:
    number: int  # zero-based generator index
    slot: EquipmentSlot
    item: ParsedItem
    values: dict[str, float]  # positive magnitudes


class OfflinePool:
    def __init__(self, drops: list[tuple[EquipmentSlot, ParsedItem]]) -> None:
        # To realize all twelve desired exceptional roles, every chosen item
        # must have exactly two exceptional affixes of the five desired types.
        # These per-roll quality floors match the user's requested near-caps.
        self.items = []
        for index, (slot, item) in enumerate(drops):
            values = {s.name: abs(s.value) for s in item.stats}
            actual_roles = set(values) & EXCEPTIONAL_SKILLS
            if len(actual_roles) != 2 or not actual_roles.issubset(ROLES):
                continue
            if values.get(CDT, 100.0) < 50.0:
                continue
            if values.get(RANGED, 100.0) < 90.0:
                continue
            if values.get(MELEE, 100.0) < 90.0:
                continue
            self.items.append(IndexedDrop(index, slot, item, values))

        n = len(self.items)
        self.rows = (
            tuple(slot.value for slot in STANDARD_SLOTS)
            + ROLES
            + ("triple_total", "mega_total", "as_count", "cd_count", "cc_count")
        )
        matrix = np.zeros((len(self.rows), n), dtype=np.float64)
        merit = np.zeros(n, dtype=np.float64)
        for j, drop in enumerate(self.items):
            values = drop.values
            matrix[STANDARD_SLOTS.index(drop.slot), j] = 1
            for k, role in enumerate(ROLES):
                matrix[6 + k, j] = float(role in values)
            matrix[11, j] = values.get(TRIPLE, 0.0)
            matrix[12, j] = values.get(MEGA, 0.0)
            for k, name in enumerate(("attack speed", "critical damage", "critical chance")):
                matrix[13 + k, j] = float(name in values)
            merit[j] = sum(
                NORMAL_WEIGHTS[k] * values.get(name, 0.0) / SKILLS[name].cap
                for k, name in enumerate(PRIORITY_NORMALS)
            ) + 0.03 * (drop.item.level - 1) + 0.5 * (drop.item.rarity == "Divine")
        self.matrix = csr_matrix(matrix)
        self.normal_merit = merit
        self.triple_values = matrix[11]
        self.mega_values = matrix[12]

    def choose(
        self, *,
        triples: int, megas: int, min_triple: float,
        min_mega: float, minimum_normals: tuple[int, int, int] = (0, 0, 0),
        objective: str = "balanced",
    ) -> tuple[IndexedDrop, ...] | None:
        if triples + megas != 8:
            raise ValueError("Exactly eight offensive exceptional rolls are available")
        exact = [1.0] * 6 + [2.0, 1.0, 1.0, float(triples), float(megas)]
        lower = exact + [min_triple, min_mega, *minimum_normals]
        upper = exact + [np.inf] * 5
        if objective == "balanced":
            values = self.normal_merit + 0.2 * self.triple_values + 0.6 * self.mega_values
        elif objective == "mega":
            values = self.mega_values
        elif objective == "triple":
            values = self.triple_values
        else:
            raise ValueError(f"Unknown objective {objective}")
        result = milp(
            c=-values,
            integrality=np.ones(len(self.items), dtype=np.int32),
            bounds=Bounds(np.zeros(len(self.items)), np.ones(len(self.items))),
            constraints=LinearConstraint(self.matrix, lower, upper),
            options={"mip_rel_gap": 0.0, "time_limit": 60.0},
        )
        if result.status == 2:  # proved infeasible by HiGHS
            return None
        if result.status != 0 or result.x is None:
            raise RuntimeError(
                f"MILP did not prove optimality/infeasibility: status={result.status}"
            )
        chosen = tuple(
            self.items[j] for j in np.flatnonzero(result.x > 0.5)
        )
        if len(chosen) != 6 or len({d.slot for d in chosen}) != 6:
            raise AssertionError("MILP returned an invalid six-slot combination")
        return tuple(sorted(chosen, key=lambda d: STANDARD_SLOTS.index(d.slot)))


def apply_choice(
    initial: EquipmentLoadout, selected: tuple[IndexedDrop, ...],
) -> EquipmentLoadout:
    result = initial
    for drop in selected:
        result = result.with_replacement(drop.slot, drop.item)
    return result


def totals(chosen: tuple[IndexedDrop, ...]) -> dict[str, float]:
    stats: dict[str, float] = {}
    for drop in chosen:
        for name, value in drop.values.items():
            stats[name] = stats.get(name, 0.0) + value
    return {name: round(value, 2) for name, value in stats.items()}


def serialize_choice(chosen: tuple[IndexedDrop, ...]) -> list[dict]:
    return [
        {
            "drop_index_0_based": drop.number,
            "slot": drop.slot.value,
            **EquipmentCodec.serialize_item(drop.item),
        }
        for drop in chosen
    ]


def benchmark(iterations: int = ITERATIONS, seed: int = SEED) -> dict:
    if iterations != ITERATIONS or seed != SEED:
        raise ValueError("Published benchmark is defined for the exact seed and 50k pool")
    rng = random.Random(seed)
    drops = [random_item(rng) for _ in range(iterations)]
    initial = EquipmentCodec.loads_json(DEFAULT_EQUIPMENT.read_text(encoding="utf-8"))

    pool = OfflinePool(drops)
    if len(pool.items) != 1674:
        raise AssertionError("Unexpected eligible pool: generator/config has changed")

    # Strong target: all defense rolls meet >=50/90/90, Triple >=90 and
    # Mega >=40. Examine the only two possible 12-slot allocations.
    ideal_4_4 = pool.choose(triples=4, megas=4, min_triple=90, min_mega=40)
    ideal_3_5 = pool.choose(triples=3, megas=5, min_triple=90, min_mega=40)
    if ideal_4_4 is not None or ideal_3_5 is not None:
        raise AssertionError("Previously impossible all-target solution became feasible")

    # These are exact maxima subject to the stated role/quality constraints.
    mega_max = pool.choose(
        triples=4, megas=4, min_triple=90, min_mega=0, objective="mega",
    )
    triple_max = pool.choose(
        triples=3, megas=5, min_triple=0, min_mega=40, objective="triple",
    )
    assert mega_max is not None and triple_max is not None

    # Human-centered balanced benchmark: at least 3 AS / 2 CD / 1 CC pieces,
    # target-covered defenses and Triple >= 90 / Mega >= 37.
    balanced = pool.choose(
        triples=4, megas=4, min_triple=90, min_mega=37,
        minimum_normals=(3, 2, 1), objective="balanced",
    )
    assert balanced is not None

    # Live greedy decision sequence, with the EXACT SAME original drop pool.
    online = run_strategy(drops, initial, ScoringStrategy.UNIVERSAL, iterations)
    offline_loadout = apply_choice(initial, balanced)
    scorer = BuildScorer(strategy_for(ScoringStrategy.UNIVERSAL))
    pve = BuildScorer(strategy_for(ScoringStrategy.PVE))
    online_score = scorer.score(online.final).total
    offline_score = scorer.score(offline_loadout).total
    online_pve = pve.score(online.final).total
    offline_pve = pve.score(offline_loadout).total
    if offline_score <= online_score:
        raise AssertionError("Claimed offline improvement did not reproduce")

    changed = tuple(
        slot for slot in STANDARD_SLOTS
        if EquipmentCodec.serialize_item(online.final.item(slot))
        != EquipmentCodec.serialize_item(offline_loadout.item(slot))
    )
    swap_deltas = {}
    for size in range(1, len(changed) + 1):
        for subset in itertools.combinations(changed, size):
            trial = online.final
            for slot in subset:
                trial = trial.with_replacement(slot, offline_loadout.item(slot))
            swap_deltas["+".join(slot.value for slot in subset)] = round(
                scorer.score(trial).total - online_score, 3
            )

    return {
        "seed": seed,
        "iterations": iterations,
        "eligible_target_candidates": len(pool.items),
        "constraint_definition": {
            "fixed_roles": "2 CDT >=50 each, 1 ranged >=90, 1 melee >=90",
            "offense_options": ["4 Triple + 4 Mega", "3 Triple + 5 Mega"],
            "balanced_minimum": "Triple >=90; Mega >=37; 3 AS, 2 CD, 1 CC",
            "optimization": "exact 0.0-gap MILP for stated linear objective",
            "important_limit": "NOT globally optimal for nonlinear Universal score",
        },
        "strict_full_target_feasible": False,
        "max_mega_with_four_rolls_and_triple_90": round(
            totals(mega_max)[MEGA], 2,
        ),
        "max_triple_with_three_rolls_and_mega_40": round(
            totals(triple_max)[TRIPLE], 2,
        ),
        "online_greedy": {
            "equips": online.equipped,
            "universal_score": round(online_score, 3),
            "pve_score": round(online_pve, 3),
            "equipment": EquipmentCodec.to_payload(online.final),
        },
        "offline_balanced": {
            "universal_score": round(offline_score, 3),
            "pve_score": round(offline_pve, 3),
            "selected_drops": serialize_choice(balanced),
            "total_stats_six_slots": totals(balanced),
            "equipment": EquipmentCodec.to_payload(offline_loadout),
        },
        "universal_improvement": round(offline_score - online_score, 3),
        "pve_difference": round(offline_pve - online_pve, 3),
        "changes": [slot.value for slot in changed],
        "swap_delta_vs_greedy": swap_deltas,
    }


def markdown_report(data: dict) -> str:
    online, offline = data["online_greedy"], data["offline_balanced"]
    selected = data["offline_balanced"]["selected_drops"]
    lines = [
        "# Offline target feasibility for the SAME 50,000 EXP drops",
        "",
        f"Seed {data['seed']}; eligible near-target candidates {data['eligible_target_candidates']}.",
        "",
        "## Main finding",
        "",
        "| | Greedy Auto | Offline six-item selection |",
        "|---|---:|---:|",
        f"| Universal score | {online['universal_score']} | {offline['universal_score']} |",
        f"| PVE score | {online['pve_score']} | {offline['pve_score']} |",
        "",
        f"**Universal gain: {data['universal_improvement']:+.3f}.**",
        "",
        "## Strict feasibility certificates",
        "",
        "- BOTH patterns (4 Triple + 4 Mega and 3 Triple + 5 Mega) are infeasible",
        "  at Triple >=90 and Mega >=40 while keeping >=50/90/90 defense rolls.",
        f"- Exact max Mega with 4 Mega and >=90 Triple: **{data['max_mega_with_four_rolls_and_triple_90']}%**.",
        f"- Exact max Triple with 3 Triple and >=40 Mega: **{data['max_triple_with_three_rolls_and_mega_40']}%**.",
        "",
        "## Better attainable six-piece build",
        "",
        "| Slot | Drop # (zero-based) | Rarity | Level | Normal | Exceptional |",
        "|---|---:|---|---:|---|---|",
    ]
    for drop in selected:
        normals = ", ".join(
            f"{k} {v:+g}" for k,v in drop["stats"].items()
            if k not in EXCEPTIONAL_SKILLS
        )
        exceptional = ", ".join(
            f"{k} {v:+g}" for k,v in drop["stats"].items()
            if k in EXCEPTIONAL_SKILLS
        )
        lines.append(
            f"| {drop['slot']} | {drop['drop_index_0_based']} | "
            f"{drop['rarity']} | {drop['level']} | {normals} | {exceptional} |"
        )
    lines.extend(["", "## Why greedy misses this build", ""])
    for combo, delta in data["swap_delta_vs_greedy"].items():
        lines.append(f"- {combo}: {delta:+.3f} Universal score")
    lines.extend([
        "",
        "The offline benchmark can retain every observed drop and replace",
        "multiple equipment slots together. The live watcher cannot: it must",
        "immediately EQUIP or SELL each candidate. The chosen six pieces",
        "maximize an explicit **linear proxy** subject to target constraints,",
        "not the true nonlinear Universal score. Infeasibility and extrema",
        "above, in contrast, are exact MILP results for the stated pool.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("dist/offline-universal-50k"),
    )
    args = parser.parse_args()
    result = benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8",
    )
    report = markdown_report(result)
    args.output.with_suffix(".md").write_text(report + "\n", encoding="utf-8")
    print(report, flush=True)


if __name__ == "__main__":
    main()
