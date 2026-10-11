# Universal target strategy — calibration and 50k experiments

Implemented on `android-live`, using the current production `BuildScorer`/
`ItemComparer` and the same **50,000 generated Immortal/Divine [EXP] drops**
(seed `20261011`) as the initial PVP/PVE/Universal comparison. The initial
eight-item state comes from `tests/fixtures/strategy_start_equipment.json`;
Wings and Cloak remain unchanged. The generator uses uniformly selected
rarities (50/50), levels (1..130), slots, valid affix names and rolls within
caps. **Not** a model of the game's actual drop distribution.

## Desired exceptional allocation

There are six replaceable [EXP] slots with a maximum of two exceptional rolls
on each: **12 total available**. Desired: two separate CDT rolls of at least
50%, one near-cap (~95%) ranged defense, one near-cap melee defense, three or
four Triple rolls with 90–100% sum, and four or five Mega Crit rolls with
40–50% sum. Therefore **4 Triple + 5 Mega requires 13 slots and is
impossible** when including the four defensive rolls. Valid best-case
patterns include 4 Triple + 4 Mega or 3 Triple + 5 Mega.

Normal roll priorities on *each item*: Attack Speed and Crit Damage (paired
bonus), then Crit Chance, then Damage/Ranged Damage, then Lifesteal/Block/Health.
Other normal skills have no target-specific bonus but may still offer a small
advantage via the PVE combat math. The PVP and PVE scoring implementations
remain unchanged.

## Approach

`BuildMetricsAggregator` now preserves individual roll values and same-item
co-occurrence across the six changing pieces, rather than only aggregate
totals. The Universal objective uses PVE combat as its base plus independent
**saturating** goals for exactly the required defensive coverage and
Triple/Mega target rolls. Additional defense beyond the targets has no bonus.
It also rewards good normal rolls across the six pieces, especially paired
Attack Speed + Crit Damage.

Before full runs, contract tests verify that two 50% CDT rolls beat a 66%+34%
split, one 95% ranged/melee defense beats two weak rolls with the same sum,
post-target redundant defense saturates, Normal priorities rank correctly,
and a same-item AS+CD pair beats the same totals split across pieces.
Production comparer equivalence, seeded reproducibility and affix-validity
tests also pass.

## Same-seed 50k experiments

| Experiment | CDT rolls | Ranged / Melee Defense | Triple | Mega | Normal AS/CD/CC count | Note |
|---|---|---|---|---|---|---|
| Initial soft target bonus | 46.94 / 62.25 | 89.81 / 86.70 | 93.79 (4) | 37.95 (4) | 5 / 3 / 2 | Correct role categories, values just below goals |
| Emphasize normal pair quality | 46.94 / 52.93 | 94.05 / 86.70 | 54.67 (2) | 35.62 (4) | 4 / 5 / 4 | Too much weight on normals, wasted exceptional slots |
| **Selected: favor required exceptional roles** | **46.94 / 52.99** | **94.99 / 97.28** | **104.74 (4)** (effective 100) | **35.47 (4)** | **4 / 3 / 2** | All 12 exceptional slots assigned to requested roles; closest defensively |
| Sharper near-cap roll weighting | 53.49 / 58.20 | 95.86 / 95.50 | 75.39 (3) | 42.02 (5) | 4 / 3 / 0 | Reached Mega, but lost too much Triple and normal offense |
| Balance all deficits with smooth penalties | 46.94 / 63.19 | 91.28 / 98.40 | 81.55 (3) | 37.73 (4) | 5 / 3 / 1 | Greedy replacement again favored a local optimum |

Selected result: [50k report + raw JSON](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38175700564/artifacts/11716146127).

**Do not interpret the objective score change across scoring revisions as an
improvement.** Cross-evaluate using an identical scorer and inspect the actual
equipped items, especially target-role counts and normal-affix quality. The
last two variants were reverted because they improved some goals at the
expense of others.

## Important limitation / follow-up

This is an **online, single-item greedy EQUIP/SELL** system. It may become
trapped in a combination that could be improved only by replacing several
items together, but it cannot retain and later equip already sold drops.
Consequently **the user-specified perfect target is not guaranteed after
50k generated items**, even when individual near-perfect drops occurred.

Before any further weight tuning, benchmark (a) more than one random seed
and (b) an offline constrained-optimum or bounded-beam reference that keeps
candidate pools per slot. That separates **lack of attainable drops** from
**bad greedy decisions**. An online improvement would then need carefully
designed, reversible decisions or a stash, not just a different weight number.

No changes made to PVP/PVE, tier/level scaling, Wings/Cloak or Ultimate.
