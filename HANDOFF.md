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

Latest **verified production APK source commit**: `fade8fef74e47edef9e3af0feb71aef29efb5321`. Android workflow `38082125026` and Python CI workflow `38082125040` succeeded, and `android-live-latest` release's target_commitish matches exactly. All 92 shared Python tests passed on 3.11 and 3.12; Android JVM tests, Gradle build, signature and publication succeeded. Subsequent documentation-only commits may advance the branch SHA; verify source SHA of the APK separately.

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

The first six slots use the rarity/level primary-stat model and exact rarity-specific rolled-affix composition (see current TODO).

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

## Current immediate TODO — new live session OCR failures fixed (2026-10-10)

User reported session `session-20261010-194809-529.jsonl` with five CHECK OCR events at 19:48–19:49; compared real `ocr_lines` (text, confidence and screen boxes) to `android-live`.

**Distinct causes and fixes:**

1. Equipped Gloves Lv124 could parse as null (displayed `Lv0`) or erroneously 123. ML Kit recognized `LvI 124 +7.32% Ranged Damage` or `Lv0124 +7.32% ...`, while a **separate, unrelated HUD label** `Lvl 123` sat far to the right of the equipment popup. `LootItemParser._level` now accepts the narrowly observed `Lv0124` spelling and ignores standalone levels outside the affix-text horizontal boundary. Two conflicting *in-card* levels still yield CHECK. `LogsUi.kt` shows `Level unreadable`, not `Lv0`, when a level really is missing.
2. Candidate Ancient Winter Gloves sometimes had `Lvi 51 +8.54% Attack Speed BSX4` or `Bx4`. The trailing game's `x4` badge was accidentally included as part of the stat label. `_clean_label` removes **only** this explicitly recognized trailing badge, not arbitrary letters/numbers.
3. `-44.78% Critical Damage` + separate `Taken` appeared in equipped Dread Necklace; `-39.40% Critical Damage` + `Taken` in Crimson Backpack. Title splitter wrongly glued `Taken` to the following full candidate title, discarding the essential affix suffix from the equipped card. Now complete catalog titles are accepted on their own, and wrapped-title logic does not steal the preceding text. The stat continuation correctly restores `critical damage taken`.
4. `(LvU 106) -5.26% Companion Cooldown` is another narrowly recognized level OCR spelling, tested in the Backpack case.
5. The 19:49:53 event had *zero OCR spans* and appropriately yielded CHECK/no tap; no action warranted without actual loot text.

**Regression coverage:** `tests/test_android_bridge.py` adds four comprehensive cases replaying the logged Gloves (both level spellings, both badge spellings and right-side HUD level), Necklace, Backpack and true in-card level conflicts. They go through the full Android JSON bridge, validate the parsed affixes/levels/slot and require a verified decision where appropriate.

**Verified:** **92 Python tests** pass on both 3.11 and 3.12, run `38082125040`. Android workflow `38082125026` green: shared Python, JVM tests, signed APK, signature, publish. Rolling release `android-live-latest` targets exactly `fade8fef74e47edef9e3af0feb71aef29efb5321`, file size 53,859,985 bytes.

APK: https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/download/android-live-latest/DungeonRushLoot.apk

**Next:** Install and retest live on device. Fail-closed if new OCR patterns arise; export Application log raw `auto_ocr.observation` and relevant session logs. Future tier/level scoring calibration and `dungeon-rush-simulator` reference remain deferred. Ultimate is not currently available.

---

## Previous milestone — uploaded log audit completed (2026-10-10)

The user provided actual exported files:
- `session-20261010-190130-547.jsonl`: 5 records: session start and four SELL/GLOVES decisions, all cancelled by old "loot changed during fresh verification".
- `dungeon-rush-app-log.jsonl (3)`: 151 events, including 9 Auto OCR observations and 2 historical import-validation failures.

### Findings

1. **Previously fixed:** the import at 18:57:54 had 7/8 success; **only** Ring failed due to `+9.07%% Mega Crit Chance`. The shared parser now handles repeated percent glyphs; regression test with exact real Void Ring OCR exists.
2. **Previously fixed:** four unsuccessful SELL/GLOVES fresh verifications at 19:01 had equal semantic candidates and equipped items but changing OCR `raw_text` and `confidence`, confirming that old `DecisionEvent.candidateKey` was unstable. This is already fixed by `src/verification.py` and the Kotlin consumer of `verification_key`.
3. **Additional observed OCR case, fixed in this audit:** at 19:01:55 the live parser returned CHECK because ML Kit recognized `LvI 124 •7.32 Ranged Damage`; a bullet replaced + and the % was absent. In `src/parsing.py`, `LEVEL_ROW_BULLET_SIGN_RE` now recovers ONLY leading `•`/`·` from an OCR row that also contains a valid explicit level marker and intact 1–2 decimal digits. The normal stat's permitted sign and upper cap still apply. It does not infer arbitrary signs or repair numbers. `tests/test_android_bridge.py` exercises a full Gloves Auto two-card OCR-to-decision flow with the actual recorded data, plus malformed/negative cases.
4. Also fixed APK workflow trigger: test-only commits under `tests/**` now trigger a new Android build. Previously a source-only build was green but release skipped because the branch advanced to a test-only commit before publication.

### Verified

- Python CI: **88 tests passed**, Python 3.11 and 3.12, GitHub run `38080621075`.
- Android workflow: **success**, run `38080621076`, including shared Python tests, Android JVM tests, Gradle signed APK, signature verification and prerelease publish.
- Verified rolling release `android-live-latest` SHA is **`68a82c66fc3cc8ac36d95b4aa476c9d1dfc74c6a`**, exactly matching the successful Android source SHA; release `DungeonRushLoot.apk` is 53,859,981 bytes.
- APK link: https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/download/android-live-latest/DungeonRushLoot.apk
- **Real-device behavior for this new OCR variant is not yet retested.** It should now parse the logged `•7.32` safely, but the next device run is the empirical validation.

### Follow-up

Test the same alt/primary game popup. If Auto still returns CHECK or cancels, export Application log JSONL so `auto_ocr.observation` and `auto_verification.fresh_check_rejected` show the actual next cause. Do NOT revisit rarity/level scoring, `dungeon-rush-simulator` integration, or Ultimate placeholder in this bugfix.

---

## Previous milestone — OCR percent + fresh verification fixed (2026-10-10)

### Device reports and root causes

1. Import of the actual Immortal [EXP] Void Ring failed because ML Kit rendered `+9.07%% Mega Crit Chance`. In the shared parser's `STAT_NUMBER_RE` only one literal `%` was permitted, so a doubled glyph made the entire stat unreadable and caused an unparsed-affix issue.
2. Auto logged repeated `SELL · GLOVES` with `Auto cancelled: loot changed during fresh verification`, despite the visible popup not changing and repeated displayed scores. The Android `DecisionEvent.candidateKey` included JSON-serialized `stats` arrays with `raw_text` and `confidence`, so harmless differences between OCR frames changed the supposedly stable identity key.

### Implemented and verified

- `src/parsing.py`: recognizes repeated `%` separators, including `%%`, `%%%` and `% %` without changing numeric digits or caps. `tests/test_equipment_import.py` reproduces the exact ring import + malformed numeric negatives.
- `src/verification.py`: deterministic semantic SHA-256 key for the **complete pair** of equipped/candidate items with normalized catalog names/slot, rarity, tier, level, [EXP], melee flag and sorted canonical affix name+two-decimal value pairs. Ignores raw OCR strings, confidence, span geometry, and affix order. Cannot produce a key on CHECK or unrecognized/wrong-slot titles.
- `src/android_bridge.py` emits `verification_key`. `Models.kt` uses **only that validated key**, instead of reserializing OCR `stats` metadata. Null/missing key always means no tap.
- `runtime/FreshVerification.kt` differentiates OCR-inconclusive, action/slot changes and semantic item-identity mismatches. `AndroidLootController.kt` still requires two independent OK passes with same semantic key and action and logs structured `auto_verification.fresh_check_rejected` diagnostics instead of a misleading generic 'loot changed'.
- `tests/test_fresh_verification.py` includes end-to-end two-pass OCR with differing confidence, line order and percent glyph, plus checks that actual item/roll/level/rarity/EXP changes are not treated equal. Android JVM `FreshVerificationTest.kt` tests stable key usage and fail-closed behavior.
- GitHub Python CI **success**, run `38079699127`, **87 tests**, both Python 3.11 and 3.12.
- GitHub Android workflow **success**, run `38079699155`, source commit `a4d9821cd8f7b426150a70f04a2dcb3c42814357`. All 87 shared Python tests, Android `testReleaseUnitTest`, signed release APK build, signature verification, artifact upload, and rolling prerelease publication passed. Verified `android-live-latest` points at that exact SHA and has `DungeonRushLoot.apk` (53,859,985 bytes).
- Direct APK: https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/download/android-live-latest/DungeonRushLoot.apk

### Next user/device steps

- Install the new APK; retry importing the same eight screenshots, especially Void Ring with duplicated percent.
- Re-test Auto SELL in-game with an unchanged Gloves popup. It should proceed after two semantically identical OK decisions (assuming target and other safety checks succeed).
- If another verification rejects, export the **Application log** JSONL and locate category `auto_verification`, event `fresh_check_rejected`: it now includes first/fresh status, action, slot, semantic keys and fresh OCR error message. This will distinguish actual mismatch from unreadable second pass.
- No claim has yet been made that the APK is tested on-device for these two fixes.

### Future only — do not implement without explicit request

- Revisit rarity/tier/level/primary stat score weights for all newly supported lower rarities. Earlier linear calibration assumed Immortal Lv1 approximately -20 points to Divine Lv130 approximately +15; now its extrapolation needs separate analysis. **Do not modify scoring in this bugfix.**
- For combat and item mechanics use the existing `yurii-zadryhun/dungeon-rush-simulator` repository as a reference when genuinely needed, not proactively for these two fixes.
- `Ultimate` is a prerelease placeholder (not currently obtainable in the game); keep it fail-closed/unconfigured. No need to ask the user for a currently unknowable count.

---

## Previous milestone — rarity-exact model (2026-10-10)

### Confirmed user rules

- Common, Uncommon, Rare, Epic: **exactly 1 NORMAL** rolled affix.
- Legendary, Mythic, Artifact, Ancient: **exactly 2 NORMAL** rolled affixes.
- Immortal, Divine: **exactly 3 NORMAL** rolled affixes.
- If the title contains [EXP], add **1 or 2 EXCEPTIONAL** rolled affixes; otherwise exactly 0 exceptional. Normal count does **not** decrease for EXP. Total is 1–5.
- `Ultimate` exists in the catalog but user did NOT provide its affix count: fail closed, do not infer from tier.
- Observed **Divine Eternal Wings without EXP has 5 normal affixes** and absolute Damage/Health primaries. This is a verified slot-specific exception. Cape's fixed primary Damage/Health percentages are not rolled affixes.
- Semantic limitation: loss of an entire second exceptional OCR line makes a 2-exceptional item observationally identical to a valid 1-exceptional item. Visible damaged lines and missing normal affixes are detectable; don't pretend rarity determines 1 vs 2.

### Implemented

- `src/config.py` owns `RARITY_NORMAL_AFFIX_COUNT`, exceptional count range (1–2), `MIN_STATS=1`, `MAX_STATS=5`.
- `src/affix_rules.py` has centralized `affix_requirement(rarity, title, slot)` and `validate_affixes(title, stats, rarity=, slot=)`. Checks exact ordinary count, 0 vs 1–2 exceptional, duplicate/unknown names, range and sign; unknown Ultimate fails closed.
- `src/equipment.py` enforces model during persisted JSON validation. `src/equipment_import.py` enforces model during each screenshot import. `src/scoring.py` validates both equipped/candidate live OCR items before Sell/Equip, checking raw suspicious stat lines first.
- Android `app_config_json()` schema **4** includes `rarity_normal_affixes`, `exp_exceptional_bounds`, `divine_wings_normal_affixes`, and absolute `affix_bounds` 1–5. `Models.kt` parses these fields; `EquipmentUi.kt` editor uses dynamic count bounds for selected rarity/title, shows expected ordinary/exceptional split, and blocks Ultimate when no rule exists.
- The broader Logs browser/detail and one-click Downloads exports remain, as do 2.5×/3.5× OCR and `auto_ocr.observation` logging.
- `tests/test_rarities_and_exp.py` rewritten with complete all-rarity×all-slot×EXP matrix, off-by-one counts, missing affixes, OCR, Ultimate, Wings/Cape, Android schema and live low rarity scenarios. Existing regression tests and source fixtures updated for exact counts. Crucially, test for 2→1 lost exceptional acknowledges unavoidable ambiguity.

### Verified CI and next action

- **Python CI success** on `806bdd1f`, GitHub Actions run `38078441935`: **79 tests**, both Python 3.11 and 3.12. Some earlier CI runs failed for a regex escaping bug and tests that incorrectly assumed second exceptional loss was always detectable; both addressed.
- **Android APK verified successful:** run `38078660399` on source SHA `706b7b3657bc8f23b3800b3d6dacf059dc6f4c7d` completed successfully. Shared Python tests, Gradle assembleRelease, apksigner verification, artifact upload and rolling prerelease publication all succeeded. Verified `android-live-latest` release `target_commitish` equals that exact source SHA and includes `DungeonRushLoot.apk` (53,843,601 bytes).
- Direct APK: https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/download/android-live-latest/DungeonRushLoot.apk
- **Device validation pending:** install new APK, **re-import existing equipment** so the actual [EXP] markers are retained, test a 1-affix Common/Rare, 2-affix Legendary/Mythic, 3-affix Immortal/Divine and EXP1/EXP2 item, plus Logs→Application log→Export. If any CHECK, attach the new `auto_ocr.observation` application JSONL. No device-success claims yet.
- `Ultimate` count remains unverified; request that specific rule from the user before enabling automation for it.

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
