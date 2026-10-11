# EXP loot simulation — 50,000 drops per strategy (2026-10-11)

Production code: `android-live` at `2d6311917e1d090514b49d8d004aa56fec34a83f`.
[Successful GitHub Actions run](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38173221073) |
[Full JSON and Markdown artifact](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38173221073/artifacts/11714453330).

Seed `20261011`, **same identical 50,000 synthetic drops** offered to each strategy, starting from the eight pieces in `tests/fixtures/strategy_start_equipment.json`. Original Eternal Wings and Divine Cloak are fixed. Every candidate is Immortal or Divine (50/50, not actual drop odds), level 1–130 uniform, slot uniform across six, with **3 unique normal and 1–2 unique exceptional affixes** drawn uniformly within game-configured caps. No melee weapon candidate is generated (the actual Auto strategy hard-rejects melee). An item equips only if the exact production build scorer, including replacement flexibility, improves by >0.01; cached scorer is differential-tested against `ItemComparer`.

## Decisions

| Strategy | EQUIP | SELL | Final own objective score |
|---|---:|---:|---:|
| PVP | 41 | 49,959 | 1707.77 |
| PVE | 34 | 49,966 | 1402.71 |
| Universal | 34 | 49,966 | 1455.39 |

## Cross-evaluation (scores are only comparable **within a column**)

| Built by | PVP score | PVE score | Universal score |
|---|---:|---:|---:|
| PVP | **1707.77** | 1186.59 | 1405.48 |
| PVE | 1505.59 | **1402.71** | 1445.92 |
| Universal | 1680.06 | 1292.70 | **1455.39** |

## PVP — final six slots

| Slot | Item | Normal affixes | Exceptional affixes |
|---|---|---|---|
| Weapon | Divine 127 | Health +12.03; Block +3.25; Lifesteal +16.79 | Melee Defense +63.96; CDT −55.30 |
| Helmet | Divine 118 | Companion Cooldown −2.75; Double Hit +24.69; Ranged Damage +12.30 | Ranged Defense +97.20; Triple Hit +27.12 |
| Backpack | Divine 116 | Melee Damage +2.53; Companion Cooldown −5.45; Attack Speed +38.22 | Ranged Defense +95.86; Triple Hit +24.59 |
| Gloves | Divine 98 | Lifesteal +17.71; Attack Speed +35.49; Companion Cooldown −2.60 | Triple Hit +25.29; Melee Defense +30.16 |
| Necklace | Divine 118 | Attack Speed +37.77; Block +3.91; Health +2.64 | Melee Defense +97.12; CDT −48.09 |
| Ring | Divine 123 | Ranged Damage +12.98; Critical Damage +55.36; Attack Speed +32.94 | Ranged Defense +88.16; Melee Defense +87.40 |

Full-build totals (including Wings/Cloak): **Attack Speed 174.92%, Triple Hit 77.00%, Ranged Defense 281.22%, Melee Defense 278.64%, Critical Damage Taken −103.39% (effective cap −100%)**, Lifesteal 34.50%, Block 7.16%, Ranged Damage 38.41%, Critical Damage 167.71%, Critical Chance 19.95%.

## PVE — final six slots

| Slot | Item | Normal affixes | Exceptional affixes |
|---|---|---|---|
| Weapon | Divine 109 | Attack Speed +27.72; Block +0.62; Critical Damage +83.91 | CDT −46.94; Triple Hit +28.73 |
| Helmet | Divine 124 | Attack Speed +30.22; Critical Chance +9.54; Critical Damage +97.63 | Triple Hit +27.06; Movement Speed +18.54 |
| Backpack | Immortal 111 | Damage +13.17; Attack Speed +30.83; Critical Chance +9.56 | Mega Crit +8.76; CDT −64.56 |
| Gloves | Divine 65 | Critical Damage +95.40; Ranged Damage +14.47; Companion Cooldown −3.24 | Triple Hit +20.55; Mega Crit +8.80 |
| Necklace | Immortal 31 | Double Hit +32.43; Attack Speed +38.29; Critical Damage +66.68 | Triple Hit +27.61; Mega Crit +9.75 |
| Ring | Divine 108 | Critical Damage +96.60; Health Regen +0.84; Attack Speed +38.70 | Melee Defense +30.62; Mega Crit +7.07 |

Full-build totals: **Attack Speed 196.26%, Triple Hit 103.95% (effective cap 100%), Mega Crit 34.38%, Critical Damage 552.57%, Critical Chance 39.05%, CDT −111.50% (cap −100%)**, Melee Defense 30.62%, Damage 106.36%, Ranged Damage 27.60%.

## Universal — final six slots

| Slot | Item | Normal affixes | Exceptional affixes |
|---|---|---|---|
| Weapon | Divine 121 | Health Regen +0.83; Attack Speed +23.07; Critical Chance +10.65 | Ranged Defense +60.79; Triple Hit +25.56 |
| Helmet | Divine 124 | Attack Speed +30.22; Critical Chance +9.54; Critical Damage +97.63 | Triple Hit +27.06; Movement Speed +18.54 |
| Backpack | Divine 104 | Ranged Damage +11.60; Health +5.10; Attack Speed +31.47 | Triple Hit +20.81; CDT −61.55 |
| Gloves | Divine 94 | Companion Damage +24.46; Block +4.01; Critical Damage +80.26 | Ranged Defense +86.37; Triple Hit +25.42 |
| Necklace | Divine 118 | Attack Speed +37.77; Block +3.91; Health +2.64 | Melee Defense +97.12; CDT −48.09 |
| Ring | Divine 123 | Ranged Damage +12.98; Critical Damage +55.36; Attack Speed +32.94 | Ranged Defense +88.16; Melee Defense +87.40 |

Full-build totals: **Attack Speed 185.97%, Triple Hit 98.85%, Ranged Defense 235.32%, Melee Defense 184.52%, CDT −109.64% (cap −100%), Critical Damage 345.60%, Critical Chance 40.14%**, Ranged Damage 37.71%, Health 87.74%.

## What this demonstrates — and does not

The current PVP objective rewards broad EHP and already capped CDT (and assumes opponents have 100% CDT). PVE chooses strong multi-hit and critical offense, even leaving two slots Immortal at 50,000 samples. Universal interpolates. This is **one reproducible, synthetic trajectory** and a test of strategy decision behavior, not a claim that these are globally optimal or statistically representative game drops. Rarity and level distribution were deliberately chosen for stress testing; in-game probabilities must be substituted before forecasting achievable gear.
