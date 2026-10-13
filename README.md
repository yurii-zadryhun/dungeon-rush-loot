# Dungeon Rush Loot Watcher

Live ADB loot comparer with build-aware scoring and two execution modes:

- `info`: compare + console + optional Termux notification; never touches the game.
- `auto`: re-check the same candidate on a fresh frame, re-check foreground, then issue a randomized Sell/Equip gesture.

The comparer scores the **whole eight-slot loadout** rather than treating the two visible items as isolated objects.

## Initial equipment state

Create your local state once:

```bash
cp equipment.example.json equipment.json
```

Fill all eight build slots: weapon, helmet, backpack, gloves, necklace, ring, wings, cape. Rolled affixes follow **exact rarity-based counts**, not a loose 1–5 range: Common/Uncommon/Rare/Epic have 1 normal affix; Legendary/Mythic/Artifact/Ancient have 2; Immortal/Divine have 3. **[EXP] adds 1–2 exceptional affixes** on top, and unmarked items have zero exceptional affixes. The Android editor, screenshot importer, persisted equipment validator and Auto comparator share this rule. `Ultimate` is recognized as a rarity but has **no verified affix count**, so automation fails closed instead of inventing one. The observed Divine Eternal Wings are a distinct exception with five ordinary rolled affixes and separate absolute Damage/Health primaries. Cape Damage/Health intrinsic percentages are not rolled affixes. Re-import old app equipment screenshots after updating: older builds stripped the [EXP] marker.

`equipment.json` is intentionally gitignored. In `auto` mode, a visually confirmed Equip replaces that slot in memory **and atomically persists the new item back to the same file**. Every later drop is therefore scored against the updated build.

If the OCR-equipped item does not match exactly one configured slot, the watcher fails closed with CHECK instead of guessing.

## Run

Universal is the default:

```bash
./loot_watcher.sh info
./loot_watcher.sh auto
./loot_watcher.sh auto 192.168.28.176:32783
```

Select a strategy with an environment variable or a third argument:

```bash
LOOT_STRATEGY=pve ./loot_watcher.sh auto
LOOT_STRATEGY=pvp ./loot_watcher.sh auto
./loot_watcher.sh auto 192.168.28.176:32783 universal
```

Direct CLI also supports `--strategy universal|pve|pvp` and `--equipment PATH`.

## Scoring model

The implementation follows mechanics already reproduced in `dungeon-rush-simulator`. It uses closed-form expectations where the game mechanics are known instead of adding Monte-Carlo noise to deterministic comparisons.

### Tier / level primary stats

Tier and level are no longer an arbitrary independent bonus. They feed the actual primary Attack/Health totals before combat utility is evaluated:

```text
primary = slot_base × tier_scaler^tier × (1 + level_scaler × level)

tier_scaler  = 3.1622776985168457
level_scaler = 0.014999999664723873
```

Tracked ranged-build slot bases are the extracted game values:

```text
Attack: weapon 7 + gloves 6 + ring 6
Health: helmet 45 + backpack 30 + necklace 20
```

The resulting loadout primary Attack/Health are normalized to an all-Immortal-Lv1 reference only to keep score magnitudes readable; relative combat power is unchanged.

### Hit count

The simulator checks Triple first, then Double only if Triple fails:

```text
E[hits] = 1 + 2T + (1 - T)D
```

Therefore Double automatically loses marginal value as Triple approaches 100%, and gives no additional hit-count value at 100% Triple.

### Crit / Mega Crit

Mega Crit is checked before normal Crit:

```text
P(mega) = M
P(crit) = (1 - M)C
```

Normal Crit Chance therefore loses marginal value as Mega Crit rises. Critical Damage Taken (CDT) reduces only the bonus part of the critical multiplier and is capped at 100%. Mega Crit then doubles the CDT-reduced multiplier.

That last ordering matters in PvP: against an opponent at 100% CDT, ordinary Crit Chance/Crit Damage add no outgoing damage, while Mega Crit still matters.

### Offense / defense

For the ranged build, offense uses the simulator relationships for:

- primary Attack;
- `Damage + Ranged Damage`;
- Attack Speed;
- expected Triple/Double hit count;
- expected Mega/Crit multiplier.

Defense uses primary Health, Health%, Block, own CDT and both defense types. Melee/Ranged defense use the real formula:

```text
damage_after_defense = damage / (1 + defense / 100)
```

For a mixed threat, the scorer averages the post-defense damage fractions and inverts them into effective survivability. This gives defense natural diminishing returns and favors a balanced universal profile over extreme overinvestment into only one defense type.

Lifesteal and Health Regen use soft saturation: useful amounts are rewarded, but the heuristic does not encourage stacking them without bound. Movement, Knockback, Thorns and companion affixes are intentionally small strategy-specific utilities because their exact matchup value is less certain.

All major multiplicative combat factors are combined in log-space, so percentage improvements compose cleanly and diminishing returns emerge from the actual formulas rather than from per-item category weights.

## Strategies

### PvE

PvE is offense-led. Triple/Double, Mega/Crit/Crit Damage, Attack Speed, Damage/Ranged Damage and primary Attack are valued through expected damage. Health, defense, own CDT and sustain still matter, but at lower weights.

The PvE incoming-crit reference profile used only to value defensive affixes is isolated in `src/strategies.py` and is an explicit tuning assumption, not a claimed hidden game constant.

### PvP

PvP models outgoing damage against an end-game opponent with **100% CDT**. Consequently:

- normal Crit Chance and Crit Damage have zero direct outgoing-damage value;
- Mega Crit remains useful because it doubles the CDT-reduced multiplier;
- Triple is premium, while Double fades out as Triple approaches 100%;
- Attack Speed, Damage/Ranged Damage and primary Attack remain direct offense;
- own CDT, Block, Health and both defenses receive much more weight;
- Lifesteal is useful but softly saturated rather than treated as an unlimited linear stat.

The reference enemy crit profile used to value **our own CDT** is explicit in `src/strategies.py`. It is deliberately easy to tune when we collect better PvP evidence.

### Universal

Universal blends PvE and PvP scores 50/50 and applies a small balance penalty. A build that is excellent in one mode but poor in the other is therefore less attractive than a similarly strong balanced build.

## Build-level caps and replacement flexibility

Hard mechanic caps are applied to the **aggregated build**, not to each item independently:

- Triple Hit: 100%
- Double Hit: 100%
- Mega Crit: 100%
- Crit Chance: 100%
- Block: 100%
- CDT: 100%

Overflow never becomes immediate combat power.

However, overcap can still have **option value**. Suppose the other items have `CDT 45 + CDT 45`, and the compared slot changes from `CDT 10` to `CDT 65`. The new 55 points above the current 100% build cap are not counted as combat strength, but they can make one of the old CDT items easier to replace later.

To model that without pretending overflow is current power, the scorer performs a small one-step look-ahead over the other seven slots. For each other item it removes that item's **entire affix package while preserving its tier/level primary stat**, measures the build-score loss, then gives a small flexibility advantage when one or two other slots have become cheap to replace.

That means an old `CDT 45` item with excellent Triple/Attack Speed is still expensive to give up; only its redundant part becomes replaceable. The look-ahead therefore evaluates the whole item, not only the capped stat.

## Runtime behavior

- OCR pauses while `com.lavalabs.dungeonrush` is not foreground.
- Auto mode is fail-closed on OCR/rarity/level/stat errors, equipment-state mismatch, changed candidate/decision, or lost foreground.
- Visual and semantic dedupe have TTLs, so transient failures retry instead of wedging forever.
- There is no fixed foreground poll delay; ADB I/O sets the pace.
- The current Divine-sell confirmation click remains in auto mode for the known `Immortal equipped -> Divine candidate -> SELL` case.

Desktop diagnostics (both `info` and `auto`) are saved under `loot_runtime/`
or `--output-dir`. Alongside `captured.png`, `comparison.json` and `annotated.jpg`,
`rarity-level-annotated.jpg` shows raw OCR text and confidence in screenshot
coordinates: cyan highlights rarity, yellow level, and gray other/unparsed text.
Desktop uses its existing full-popup OCR pass for these diagnostics, without
adding recognition passes or changing confidence filtering. Low-confidence
results remain diagnostic-only and never influence decisions.

`decisions.jsonl` includes accepted `ocr_lines` and `rarity_level_passes` with
the crop, scale and all raw OCR lines (including rejected and empty results).
`rarity_level_annotated_image` points to the latest image, not a historical
snapshot. Images are overwritten to keep storage bounded; copy them before
continuing to preserve an observation. CHECK results also save diagnostics,
including unreadable/missing titles, using the existing 10-second retry-log
throttle. `--no-annotate` disables both annotated images, but not OCR logs.

## Setup / tests

```bash
./setup.sh
python -m unittest discover -s tests -v
python -m compileall -q src
bash -n loot_watcher.sh setup.sh
```

GitHub Actions runs the unit suite, compile check, critical Ruff checks and shell syntax on Python 3.11 and 3.12.


## Android screenshot equipment import

The Android app can import the current build from 8 screenshots. The first implementation intentionally uses a fixed crop matching the current 709x1536 current-item modal, so aggregate build stats visible behind the modal are excluded from OCR. Normal slots are inferred from title signatures; cape requires a cloak/cape title plus bracketed rarity; wings require both absolute Damage and Health primary lines. A review dialog allows slot override before all eight items are persisted.


## Android OCR

The Android app now uses local **PP-OCRv6 Small ONNX** (official PaddleOCR
Android SDK), not Google ML Kit. Run `bash scripts/prepare-android-ocr.sh`
before local Android builds; CI does it automatically. Models are included in
the APK, not downloaded on first launch. See [docs/android.md](docs/android.md).


## Universal scoring in Desktop

The Desktop default `--strategy universal` now uses the **same goal-based
Universal objective** as the `android-live` branch, rather than the legacy
50% PvE/50% PvP blend. On six replaceable [EXP] items, it targets exactly
2 Critical Damage Taken rolls (each 50%+), 1 Ranged Defense (~95%+),
1 Melee Defense (~95%+), 4 Triple Hit rolls (~90–100% total), and
4 Mega Crit rolls (four near-10% rolls, 40% maximum). Normal-affix
preferences, on *each item*: Attack Speed and Crit Damage as a pair,
Crit Chance, Damage/Ranged Damage, then Lifesteal/Block/Health.

The six-slot Desktop `equipment.json` format is **unchanged** and the
existing desktop OCR/ADB tools continue to work. The Android branch
has additional Wings/Cape and platform adapters, so absolute build scores
are not directly comparable between the two environments. Neither
guarantees the exact endgame build: immediate irreversible EQUIP/SELL
decisions are a greedy online policy, not a hindsight optimizer.

To verify locally: `python -m unittest discover -s tests -v`.

## Single decision engine (Desktop + Android)

`master` is now the sole active development branch. Desktop screenshot
capture/Paddle OCR and Android capture/Paddle OCR supply observations to the
**same Python** `LootDecisionEngine → ItemComparer → BuildScorer`. Android's
Chaquopy source directory `androidApp/src/main/python/src` is a symlink to
the repository's `src/`, not a fork or duplicate of the scorer. Tests replay
actual captured 2026-10-13 item comparisons through both entry points and
verify identical actions, component deltas and values.

Desktop prints `Δ points (candidate − equipped)` broken into PvE,
target Defense/Triple/Mega, Normal skills and Flexibility. **`Σ` denotes
a total percentage for that stat in the build, not scoring points.**
A full item swap may correctly lose to a weak +4% Mega Crit if it sacrifices
a vital −50% CDT and a +24% Triple roll, even though standalone Mega Crit
is far more valuable than Companion Damage.

Rolling Android builds now come from `master`:
`https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/tag/master-latest`.
