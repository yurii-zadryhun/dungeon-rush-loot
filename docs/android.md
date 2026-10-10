# Android live build

Every push to `android-live` runs the **Android APK** workflow.

A successful build publishes both an Actions artifact named `DungeonRushLoot-android-live` and a rolling prerelease named `android-live-latest`. The APK is `DungeonRushLoot.apk` and is accompanied by a SHA-256 file.

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

The first Android adapter uses Accessibility screenshots plus the bundled ML Kit Latin text-recognition model. The scorer and parser remain Python through Chaquopy.

`ScreenCaptureAdapter` is deliberately independent of Accessibility so MediaProjection or another capture source can be added later.

## Logs

Each START AUTO creates a new app-private JSONL session file and each STOP AUTO closes that session. Every event is appended and fsynced immediately. The Logs tab keeps old session files, auto-selects the active session, and loads entries newest-first in batches of 50 as the user scrolls. Entries are color-coded and expandable into equipped/candidate stats, before/after build scores, overcap reductions and runtime action details.

## Equipment screenshot import

The current importer uses one intentionally static relative crop for the supplied 709x1536 current-item modal. Gallery decoding and ML Kit OCR stay in the Android layer; slot inference and item parsing are shared Python logic. A later popup detector or MediaProjection capture adapter can replace the current Android source without changing the scorer.
