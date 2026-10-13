# Could the same 50,000 drops produce a better Universal build?

**Yes.** Replayed the exact deterministic `random.Random(20261011)` stream
with the production `random_item()` generator and fixture. The stream matches
the previous greedy run, including weapon drop #20304 (Divine Lv109,
Attack Speed 27.72, CDT -46.94) and backpack drop #47048.

The complete benchmark was run on GitHub Actions:
[success / source logs](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38207762735),
[complete JSON and Markdown artifact](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38207762735/artifacts/11727594427).
Implementation:
[`tools/offline_universal_benchmark.py`](../tools/offline_universal_benchmark.py).

## Method

- **Same pool:** exactly 50,000 seeded Immortal/Divine EXP generated items,
  same initial six pieces, with fixed Wings/Cloak.
- **Greedy reference:** actual production `run_strategy`, all 50,000
  sequential EQUIP/SELL decisions evaluated by `BuildScorer(Universal)`.
- **Offline alternative:** exact mixed-integer linear solver (SciPy/HiGHS)
  chooses one item from each of six slots without respecting drop order or
  the irreversible SELL limitation. Only items with two exceptional rolls
  from CDT, Ranged Defense, Melee Defense, Triple and Mega are considered.
  Their defensive roles must have >=50% CDT or >=90% side defense.
  Exactly 2 CDT, 1 Ranged, 1 Melee, 4 Triple, 4 Mega. Require >=90 total
  Triple, >=37 total Mega, at least 3 Attack Speed, 2 Crit Damage and
  1 Crit Chance items. Maximize a **documented linear proxy** for normal
  roll quality, rarity, level, Triple and Mega.
- **Scoring:** both full resulting loadouts are then scored by the *actual*
  production Universal and PVE scoring implementations. The offline result
  is **not claimed globally optimal under the nonlinear Universal score**.

## Found attainable improvement

| Metric | Greedy final | Offline result |
|---|---:|---:|
| Universal production score | **2837.077** | **2883.623** (+46.546) |
| PVE production score | 1353.564 | 1349.641 (−3.923, ~0.29%) |
| CDT rolls | −46.94 / −52.99 | **−64.56 / −63.84** |
| Ranged Defense | 94.99 | **99.52** |
| Melee Defense | 97.28 | 93.33 |
| Triple total (effective cap 100) | 104.74 | 103.26 |
| Mega total | 35.47 | **37.19** |
| Items with Attack Speed | 4 | **5** |
| Items with Crit Damage | 3 | 3 |
| Items with Crit Chance | 2 | 2 |

### Exact six items selected (zero-based drop numbers)

| Slot | Drop # | Rarity | Level | Normal rolls | Exceptional rolls |
|---|---:|---|---:|---|---|
| Weapon | 46035 | Divine | 16 | Ranged Damage 0.40, AS 38.52, Companion Damage 27.05 | Triple 29.89, Ranged Defense 99.52 |
| Helmet | 43276 | Divine | 32 | Double Hit 16.90, Crit Chance 10.68, AS 32.60 | Triple 25.21, Mega 9.88 |
| Backpack | 7730 | Immortal | 111 | Damage 13.17, AS 30.83, Crit Chance 9.56 | Mega 8.76, CDT −64.56 |
| Gloves | 9966 | Divine | 65 | Crit Damage 95.40, Ranged Damage 14.47, Companion Cooldown −3.24 | Triple 20.55, Mega 8.80 |
| Necklace | 20910 | Immortal | 31 | Double Hit 32.43, AS 38.29, Crit Damage 66.68 | Triple 27.61, Mega 9.75 |
| Ring | 7686 | Divine | 97 | Crit Damage 39.38, AS 38.46, Block 0.19 | Melee Defense 93.33, CDT −63.84 |

### Demonstrated multi-item synergy

Comparing each of four changed slots against the *final* greedy build:

| Replaced slots | Universal score delta |
|---|---:|
| Weapon only | −200.921 |
| Backpack only | −119.664 |
| Gloves only | −254.009 |
| Ring only | −143.892 |
| Weapon + Backpack | +5.870 |
| Gloves + Ring | +34.774 |
| **All four** | **+46.546** |

Every individual change is negative even though the full four-slot swap
is positive. Three target drops (#7730, #9966, #7686) appeared **before**
the items occupying their slots in the final greedy build (#47048, #26295,
#32946); the alternative Weapon #46035 appeared later than greedy Weapon
#20304. This demonstrates why irreversibly selling early drops prevents
future synergy.

## What is mathematically achievable in this 50k pool?

Under exactly 12 exceptional slots, two CDT rolls >=50, one ranged and one
melee defense roll >=90, the only target allocations are:

- **4 Triple + 4 Mega:** require Triple >=90 and Mega >=40.
  The solver *proved infeasible*. The **exact maximum Mega is 39.79%**
  with Triple >=90 and the stated defensive constraints.
- **3 Triple + 5 Mega:** require Triple >=90 and Mega >=40.
  Also *proved infeasible*. The **exact maximum Triple is 89.89%**
  with Mega >=40 and the stated defenses.

Both maxima are rigorously optimal for these exact **linear constraints**;
they are **not** proofs of the strongest possible nonlinear-scored build.
For the impossibility, remember each Mega roll is capped at 10%, each
Triple at 30%: four Mega would need four perfect 10% rolls to reach 40,
or three Triple would need three perfect 30% rolls to reach 90.

## Interpretation

The precise goal is not attainable in the generated pool with the stated
exceptional-role allocation, but **a better-than-greedy Universal score and
a build closer to the target were both attainable**. The discrepancy is not
only from score weighting: it is a demonstrated consequence of greedy
irrevocable decisions. This is a synthetic RNG stress test, not real drop
probabilities. No production strategy was changed by this benchmark.
