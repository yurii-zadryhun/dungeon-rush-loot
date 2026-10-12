# Android live build

Every push to `android-live` runs the **Android APK** workflow.

A successful build publishes both an Actions artifact named `DungeonRushLoot-android-live` and a rolling prerelease named `android-live-latest`. The APK is `DungeonRushLoot.apk` and is accompanied by a SHA-256 file.

## Android OCR: PaddleOCR PP-OCRv6 Small

ML Kit has been removed from Android's code and Gradle dependencies.
The official upstream [PaddleOCR Android SDK](https://github.com/PaddlePaddle/PaddleOCR/tree/dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf/deploy/ppocr-android/ppocr-sdk) is pinned to one commit (Apache-2.0);
the ONNX detection/recognition models run entirely on-device and are included in the APK.

Before a local build (also executed automatically in GitHub Actions):

```bash
bash scripts/prepare-android-ocr.sh
gradle :androidApp:assembleRelease
```

The script retrieves the upstream SDK source and official PP-OCRv6 Small ONNX weights
into ignored `ppocrSdk/src/`. This is a build-time step only, not a runtime download.
The platform implementation is `PaddleOcrAdapter`; the existing `OcrAdapter`,
shared Python parser, two-frame verification, strict validation, and fail-closed
Auto behavior are preserved. On failed model initialization or inference, Auto
logs an error and never taps. Real-device accuracy and latency must be verified
separately.

## First run

1. Install the APK.
2. Open **Equipment** and configure all eight slots (six normal items + wings + cape), or use Import equipment from screenshots and select the 8 current-item screenshots.
3. Open **Auto** and choose Universal, PvE or PvP.
4. Open Accessibility settings from the app and enable Dungeon Rush Loot.
5. Tap **START AUTO**.
6. Open Dungeon Rush.

Auto remains disabled until the shared Python equipment validator accepts all eight slots. The service only captures or taps while `com.lavalabs.dungeonrush` is foreground.

Successful Equip actions are visually verified before the slot is persisted. If confirmation fails, the decision is logged but the equipment state is not changed.

## OCR and capture

The first Android adapter uses Accessibility screenshots plus on-device PP-OCRv6 Small via the official PaddleOCR Android ONNX Runtime SDK. The scorer and parser remain Python through Chaquopy.

`ScreenCaptureAdapter` is deliberately independent of Accessibility so MediaProjection or another capture source can be added later.

## Logs

The **Logs** tab is a file browser. **Application log** appears first, followed by individual session JSONL files. Tap a file to open its dedicated detail screen; use Back to return to the list.

- Application log: one persistent JSONL in app-private storage, updated on process/activity startup and on importer, Accessibility and Auto runtime diagnostics. The detail page shows recent events and expandable raw JSON. This file is *not* mixed into session logs.
- Session logs: each START AUTO creates one JSONL; STOP AUTO closes that session. Old files remain listed. Detail shows color-coded decisions, OCR CHECK messages, scores and expandable comparisons.
- All log append operations flush/fsync immediately. Detail screens paginate the newest records in batches of 50.
- **Export** is on each file's detail page, not in the file browser. It saves a raw JSONL snapshot directly into the user's **Downloads** directory using Android MediaStore, with no location/name picker and no storage permission on minSdk 30. A failed export cleans up the incomplete destination.

## Live OCR level recovery

Full-popup PaddleOCR OCR reads the right-hand affixes well but can entirely miss
the `Lvl` labels drawn over the two item icons. When both passes cannot
recover a level, Android performs a **targeted icon-label OCR fallback**:
two small regions anchored on the recognized item-title rows are read in
normal and high-contrast mode. The resulting text is sent through the same
strict Python parser and rarity/affix validation.

No missing level is inferred from the equipped item, UI tier, rarity, or
previous screenshot. An unreadable label, conflicting level, or unknown
title still yields **CHECK OCR** and no automated tap.

The temporary one-shot screenshot/ZIP diagnostic has been removed from the
application. Only existing JSONL session and application logs remain.

## Alt accounts, rarity and exceptional rolls

The **rarity defines an exact number of ordinary rolled affixes**:

| Rarity | Ordinary affixes | Exceptional affixes without [EXP] | With [EXP] |
|---|---:|---:|---:|
| Common / Uncommon / Rare / Epic | 1 | 0 | 1–2 additional |
| Legendary / Mythic / Artifact / Ancient | 2 | 0 | 1–2 additional |
| Immortal / Divine | 3 | 0 | 1–2 additional |

The total is therefore **1–5 rolled affixes** depending on rarity and marker.
[EXP] means there must be either one or two exceptional rolls, in addition to
all normal rolls for that rarity. It is not a substitute for a normal affix.
Without [EXP], exceptional rolls are forbidden.

The item-name catalog includes **Ultimate**, but its ordinary-affix count has
not been provided or confirmed. Ultimate remains visible as a rarity, yet
configuration/import/Auto **fails closed** rather than guessing a valid count.

The user's real Divine Eternal Wings screenshot contains **five normal rolled
affixes without [EXP]**; this is a known Wings-specific exception to Divine's
three-normal rule. Cape's fixed Damage/Health intrinsic percentages are excluded
from the rolled-affix count. The other documented Cape affixes obey its rarity.

All rules are centralized in Python (`src/affix_rules.py`) and used for
persisted equipment, screenshot import, and live comparison. Android receives
the same rarity-to-normal-count mapping, EXP range and verified Wings exception
via `app_config_json()`, and uses those values for editor input/count checks.
The editor does not infer [EXP] from the skills selected.

**Important OCR limitation:** With [EXP], one *or* two exceptional affixes are
valid. If OCR entirely loses the second exceptional line, a valid-looking
one-exceptional item cannot be disproved from rarity alone. Visible malformed
affix rows yield CHECK, and missing ordinary affixes always fail count checking.
Do not claim that cardinality alone detects an invisible second exceptional.

Older builds stripped [EXP] from saved standard-item titles. Re-import the
equipment screenshots after updating so the true marker is retained.

## Live OCR parsing

Android Auto attempts PP-OCRv6 Small at 2.0× and retries at 3.0× when the Python decision is CHECK. The shared Python loot parser understands separate rarity headers, wrapped item titles, lvl labels interspersed with affixes, OCR-confusable textual skill names and bounded percentage separator errors. Numeric digits are **never** Levenshtein-matched. Unknown/ambiguous titles, missing affixes, impossible rolls, signs and conflicting levels lead to CHECK/no tap. Source OCR text and parser outcomes are periodically recorded under `auto_ocr.observation` in the Application log.

## Equipment screenshot import

The current importer uses one intentionally static relative crop for the supplied 709x1536 current-item modal. Gallery decoding and PaddleOCR OCR stay in the Android layer; slot inference and item parsing are shared Python logic. A later popup detector or MediaProjection capture adapter can replace the current Android source without changing the scorer.


### Native OpenCV failures and APK verification

The app uses `com.quickbirdstudios:opencv:4.5.3.0` instead of upstream's
`4.5.3` artifact, which its publisher warns can fail at runtime on Android.
An OpenCV load failure preserves its original `UnsatisfiedLinkError` (including
`dlopen` details) in exported app logs instead of obscuring it behind a
boolean initialization result. Auto fails closed and never taps on OCR failure.

CI verifies that the APK contains arm64 OpenCV/ONNX native libraries and both
PP-OCRv6 model files; publishing also verifies that the rolling Release APK's
SHA-256 matches the signed APK produced by that Actions run. These checks do
not replace smoke-testing OCR on a physical Android 16 device.


### OCR columns, level reliability and automation retry (Oct 2026)

Live Android OCR first scans the left badge column (`x=0.155..0.345`) for
exactly two rarity headings at any vertical position. Each heading anchors an
icon-only level crop at `x=0.17..0.335` and `y=heading+0.035..0.095 * height`.
The right text column (`x=0.345..0.875`) is OCR'd independently. If the two
rarity anchors cannot be established, the adapter uses a full-popup pass rather
than guessing card placement. Normal-affix counts are verified in shared Python
from each item's parsed rarity, not duplicated in Android. Level regex tolerates
short non-digit corruption following `Lv` but never manufactures missing digits.

A rejected Android touch never marks a candidate as handled. Unconfirmed Equip
state updates likewise remain retryable; successful actions deduplicate by
verification key for 5 seconds using monotonic elapsed time. A CHECK result
continues to retry (with log throttling). There is deliberately no Android
image-hash gate skipping CHECK frames, so a visual fingerprint cannot permanently
lock Auto out of the same popup.
