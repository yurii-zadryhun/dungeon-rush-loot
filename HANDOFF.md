# Chat handoff / project context

This file exists so a fresh ChatGPT chat can resume the work without reconstructing the history.

## Working agreement

- Personal project. Prefer simple, clean architecture over process overhead.
- Desktop/general work normally goes directly to `master`.
- Android is intentionally being developed on the live branch `android-live`.
- Keep **shared game/domain logic in Python**. Platform differences belong behind adapters.
- Keep desktop working: PC = ADB + PaddleOCR; Android = native screenshot/OCR/touch adapters + the same Python domain.
- Prefer fail-closed behavior for automation/OCR: if uncertain, CHECK/do nothing rather than guess and tap.
- Code style: clean architecture/SRP, intent-revealing names, short cohesive classes/methods.
- Do not sit polling GitHub Actions. After pushing, check CI at most once; if still running, report `CI pending` and return. There is no webhook/callback available here and repeated polling has caused several stalled turns.

## Repository / branch state

Repository: `yurii-zadryhun/dungeon-rush-loot`

Android branch: `android-live`

At handoff, branch head is around the application-diagnostics work. Shared Python CI is green, but the latest Android APK workflow is failing at Kotlin compilation because of bad `weight` imports/usages:

- `AppUi.kt:14:43 Cannot access 'val RowColumnParentData?.weight: Float': it is internal in file.`
- `LogsUi.kt:40:43 Cannot access 'val RowColumnParentData?.weight: Float': it is internal in file.`

Fix this first, then build Android once. Do not wait synchronously for workflow completion.

## High-level architecture

One Python decision domain, two platform shells:

```text
                         shared Python
                   parser / equipment / scorer
                     strategies / decisions
                        /             \
                       /               \
Desktop                                       Android
ADB screenshot                               Accessibility screenshot
PaddleOCR                                    ML Kit OCR
ADB gestures                                 Accessibility gestures
JSON equipment                               Android local storage
Rich/console                                 Compose UI
JSONL decision logs                          JSONL session logs + UI
```

Important shared modules include:

- `src/domain.py`
- `src/config.py`
- `src/text.py`
- `src/parsing.py`
- `src/equipment.py`
- `src/scoring.py`
- `src/strategies.py`
- `src/core.py`
- `src/events.py`
- `src/ui_geometry.py`
- `src/equipment_import.py`
- `src/game_catalog.py`
- `src/android_bridge.py`

Android embeds the same Python code through Chaquopy. Do not duplicate scorer/parser rules in Kotlin.

Android runtime adapter boundary already exists for screen capture, OCR, touch and foreground app detection. The screenshot interface was deliberately designed so MediaProjection can be added later without changing shared logic/controller/UI.

## Equipment/build model

Tracked slots are now **8**:

1. weapon
2. helmet
3. backpack
4. gloves
5. necklace
6. ring
7. wings
8. cape

Build scoring must aggregate all eight because Wings/Cape contribute stats.

### Standard gear

The first six slots use the existing rarity/level primary-stat model and 4–5 rolled affixes.

Do **not** infer the slot from English semantics like “helmet”, “backpack”, etc. The game has misleading names:

- `Celestial Lyre` -> backpack
- `Infernal Tome` -> backpack
- `Radiant Shield` -> backpack
- `Blessed Tiara` -> helmet
- `Undying Mask` -> helmet
- `Eternal Cape` -> helmet
- `Celestial Lightning` -> weapon

The current solution uses a catalog extracted from the supplied game APK/Unity serialized assets. `src/game_catalog.py` contains the name -> slot mapping (hundreds of EquipmentData definitions). Keep catalog-based classification as the authority.

### Wings

Example current Wings screenshot:

- rarity: Divine
- title: Eternal
- level: 100
- absolute primary Damage: 2.25M
- absolute primary Health: 7.50M
- five rolled affixes

Wings are structurally identified by both absolute Damage + Health primaries plus a known Wings name. They have their own progression constants in the extracted game data; level can be inferred from primary values when OCR misses the level.

### Cape / Cloak

Example current cape:

- title: Divine Cloak
- rarity marker: `[Mythic]`
- level: 31
- fixed/intrinsic `+80% Damage`
- fixed/intrinsic `+80% Health`
- rolled affixes: `+33.25% Critical Damage`, `+8.89% Critical Chance`

Important: Cape Damage/Health are **not rolled affixes**. They are intrinsic cape stats which scale with cape level. They belong in build aggregation, but must remain separate from `stats` (rolled affixes).

Game data for cape/wings also exists in `dungeon-rush-simulator` and was used to derive progression/affix behavior.

## Scoring

Three strategies exist:

- `universal`
- `pve`
- `pvp`

Scoring is build-aware, not item-isolated. It evaluates replacing the slot in the entire loadout, including caps/overcaps and interactions.

Important design requirement: do not treat a candidate’s stat as mostly worthless merely because the current total is capped. A higher roll may enable replacing a weaker stat source in another slot later. Existing flexibility/look-ahead scoring was introduced for this reason.

PvP direction discussed:
- very high value: Critical Damage Taken, defenses, Triple Hit, Attack Speed
- Double Hit loses marginal value as Triple Hit grows
- useful but not blindly stacked Lifesteal
- crit-oriented offensive stats lose value if opponents commonly have CDT around -100%

PvE direction discussed:
- Triple Hit, Attack Speed
- Mega Crit, with Crit Chance declining in value as Mega Crit coverage grows
- Crit Damage
- Double Hit declines as Triple Hit grows

Universal balances both.

## OCR / textual fuzzy matching

Numeric data must stay strict. Do not fuzzy-match numbers.

Good:
- regex/range/known progression recovery for `Lvl`, percentages, K/M values
- known special correction such as OCR `Lv134` -> real `Lv34` only when the impossible range proves the leading `1` is OCR noise
- Wings/Cape progression-based recovery where the game formula makes it safe

Bad:
- Levenshtein/fuzzy matching numeric values

Text labels **should** use OCR-aware fuzzy matching.

`src/text.py` has/was being changed to use weighted Levenshtein for names such as:

- `Attack 5peed` -> `Attack Speed`
- `Dread Neck1ace` -> `Dread Necklace`

OCR-confusable substitutions (e.g. 0/o, 1/l, 1/i, 5/s) have reduced edit cost. Item-name matching also uses confidence threshold + margin to the second-best candidate. If ambiguous, fail closed.

## Android equipment screenshot import

User wants to select the 8 current-equipment screenshots in any order and have the app identify all slots automatically.

For the current device/screenshots, the item modal is effectively the same size/static position. We intentionally use static crops for now. Later, when the product is considered ready, replace this with robust popup/layout detection for multiple devices/resolutions.

Critical constraint: aggregate build stats are visible behind/below the item popup. OCR must stay inside the foreground item modal so those background stats cannot be mistaken for affixes.

Current import stack:

- Android selects images
- `EquipmentScreenshotImporter.kt`
- fixed main crop
- ML Kit line OCR with upscaling / multiple passes
- separate tight high-scale level crop because outlined `Lvl` text is difficult
- shared Python `EquipmentScreenshotParser`
- APK-derived item catalog for standard-slot detection
- structural/canonical detection for Wings/Cape
- review dialog before saving

The import is **still the main broken area**. User’s latest real test still produced failures:
- Wings: slot detected, but level not parsed
- Helmet: slot detected, but level not parsed
- Weapon: level not parsed and only 3 affixes parsed
- Cape: slot/title/level parsed, but one fixed Damage/Health line was missed, producing “Cape primary Damage/Health lines were not parsed safely.”

Screenshots/results from the conversation showed that ML Kit gets most text but occasionally drops outlined level text and individual rows. Do not assume parser logic alone is the issue; capture raw OCR diagnostics from every pass.

Recent importer work added:
- APK catalog instead of keyword slot guessing
- line-level ML Kit OCR
- upscaled 2.5x/3.5x main passes merged by physical row
- dedicated 3.5x/5x level OCR passes
- Wings level inference from primary progression
- Cape intrinsic recovery based on known cape progression
- OCR-aware Levenshtein for item/affix names

The next useful debugging input must be an exported application diagnostics log, not another screenshot of the review dialog.

## Logging design

There are two intentionally separate log concepts.

### 1. Loot/session logs

These contain only an Auto loot session and remain one JSONL file per session.

- Start Auto -> create new session file
- append each event immediately and fsync; never buffer until Stop
- Stop Auto -> close session
- old session files remain selectable
- active session is automatically selected in the viewer
- UI loads 50 newest entries and loads 50 more while scrolling

Do not put unrelated app/import errors in these files.

### 2. Global application diagnostics log

This was the latest requested feature and implementation is partially/mostly committed on `android-live`.

Purpose: one persistent application-level JSONL containing diagnostics unrelated to a loot session, especially equipment screenshot import debugging.

Expected categories/events include:
- app lifecycle/startup
- Accessibility service lifecycle/errors
- controller/runtime failures which are application-level
- equipment import started/completed/failed
- validation failures
- per-screenshot result
- raw OCR data for each OCR pass (main/level, scale, recognized text/boxes/confidence)
- exceptions + stack traces

Requirements from user:
- separate from session logs
- persistent across app launches
- write immediately
- on Logs page: dedicate **one row** to “Application log”
- put an export/download action at the end of that row
- export the raw log file so the user can attach it in the next chat

Recent commits added files/wiring around:
- `ApplicationLogStore.kt`
- application log port
- import diagnostics
- per-pass OCR diagnostics
- accessibility lifecycle logging
- controller failure mirroring
- export row on Logs screen
- app/process startup logging

Verify the current implementation after fixing Android compilation. In particular, confirm exported JSONL contains enough OCR-pass detail to reproduce why each screenshot failed.

## Android home-screen UX request

On the Auto/home screen there are two status cards:

- Accessibility service
- Equipment

User explicitly requested inline actions **inside these cards, at the end of the row/card**:

- Accessibility card -> button/action opens Android Accessibility settings
- Equipment card -> button/action switches directly to the Equipment tab/screen

Recent commit `feat: add inline home status actions` attempted this. Current Android compilation failure is in the UI around `weight`, so verify these cards after fixing imports/layout.

Do not keep a redundant full-width “Open Accessibility settings” button if the inline card action already covers it cleanly.

## Android Auto lifecycle

Auto mode is explicitly Start/Stop.

AccessibilityService may remain enabled/connected after Stop, but automation should do nothing while Auto is disabled.

A process restart must not silently resume auto-tapping. User must explicitly Start again.

## Current immediate TODO

1. **Fix Android Kotlin compilation** (`weight` issue in `AppUi.kt` and `LogsUi.kt`).
2. Build once; check workflow once only.
3. Verify the global application log feature end-to-end:
   - app startup lines
   - import validation lines
   - every ML Kit import pass
   - raw recognized lines/boxes/confidences
   - exception stack traces
   - raw file export from the single Logs-page row
4. Verify home status-card actions:
   - Accessibility -> settings
   - Equipment -> Equipment tab
5. Install/test new APK against the same 8 screenshots.
6. User should export and attach `dungeon-rush-app-log.jsonl`.
7. Use that log to fix the remaining importer problems empirically instead of guessing from review screenshots.
8. Once screenshot import is reliable, return to Auto live testing and tune ML Kit/parsing only where logs show actual failures.

## Useful game/reverse-engineering context

A separate simulator repo exists: `yurii-zadryhun/dungeon-rush-simulator`.

The user supplied current game files/XAPK/APK plus Cpp2IL output. Unity serialized assets proved more useful than Cpp2IL for item-name/slot catalogs.

Relevant extracted facts:
- ordinary equipment definitions expose item/display names and slots
- Cape and Wings have distinct data/progression
- item naming cannot safely infer slot semantically
- current game package: `com.lavalabs.dungeonrush`

## Safety behavior for automation

Before any Auto tap:
- game must be foreground
- fresh screenshot/OCR must still describe the same candidate
- action must be unchanged
- uncertainty -> CHECK/no tap

After Equip, update persisted equipment only after visual evidence that the UI changed.

There is an older known weak point around sell-confirmation handling: the current implementation historically used a rarity-based “Sell then Confirm” assumption rather than robustly detecting the confirmation modal. Do not expand this while debugging import unless needed, but it remains a future hardening item.
