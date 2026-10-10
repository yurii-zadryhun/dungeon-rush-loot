# Architecture

The project has one Python decision domain and two platform shells.

```text
                         shared Python
                     +--------------------+
 OCR observations --->| LootDecisionEngine |---> Comparison / DecisionEvent
 equipment state ---->| parser + scorer     |
 strategy ----------->| PvE/PvP/Universal  |
                     +--------------------+
                         ^            ^
                         |            |
                  desktop adapters   Android adapters
```

## Shared Python

`domain.py`, `config.py`, `text.py`, `parsing.py`, `equipment.py`, `equipment_import.py`, `scoring.py`, `strategies.py`, `core.py`, `events.py` and `ui_geometry.py` are platform-neutral. `android_bridge.py` is only a JSON serialization boundary around that same domain.

`LootDecisionEngine` consumes OCR spans, assembles lines, splits the two cards, parses both items and delegates to `ItemComparer`. Android does not reimplement scoring in Kotlin.

## Platform ports

The important boundaries are screen capture, foreground detection, OCR, touch execution, equipment persistence, structured decision logging and presentation.

Desktop uses ADB + PaddleOCR + JSON files + Rich. Android uses Accessibility screenshots, bundled ML Kit OCR, Accessibility gestures, app-private equipment storage and Compose.

`AndroidLootController` depends on interfaces from `runtime/Ports.kt`, not concrete screenshot/OCR/touch implementations. A later MediaProjection implementation can replace `AccessibilityScreenshotAdapter` by implementing `ScreenCaptureAdapter`; no scorer/parser/UI changes are required.

## Android flow

```text
Accessibility screenshot
  -> shared relative crop
  -> ML Kit word spans
  -> PythonDecisionBridge
  -> shared LootDecisionEngine
  -> structured DecisionEvent
  -> fresh screenshot/OCR verification
  -> Accessibility Sell/Equip gesture
  -> on Equip: visual-change verification
  -> persist updated equipment
```

The controller stops screenshots and gestures whenever Dungeon Rush is not foreground.

## Structured logs

The Python domain owns the decision event schema: action/status, slot, both parsed items, build scores, score components, effective/capped aggregate stats and OCR lines. Desktop appends JSONL under `loot_runtime/decisions.jsonl`; Android rotates one JSONL file per Auto session, fsyncs each event immediately, and renders persisted sessions as colored expandable cards with 50-entry incremental loading.

## Signing

`android-live` is an internal personal-testing channel. Its APK uses a stable development signing key committed to this public repository so CI builds can update each other without manual secret setup.

The key is intentionally not a production identity. If the app is ever distributed publicly, use a private release key stored in GitHub/environment secrets and a production application ID.

## Special slots

The build has eight slots. The six normal loot slots retain the extracted tier/level primary formula. Wings contribute their displayed absolute Damage and Health primaries plus rolled affixes. Cape keeps its level-dependent Damage/Health values as intrinsic stats, separate from rolled affixes. The shared equipment codec and scorer preserve that distinction on desktop and Android.
