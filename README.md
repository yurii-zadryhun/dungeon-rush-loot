# Dungeon Rush Loot Watcher

Live ADB-only loot comparer with two execution strategies:

- `info`: compare + console + optional Termux toast/push; never touches the game.
- `auto`: compare, re-check the same candidate on a fresh frame, re-check foreground, then issue a randomized short touchscreen swipe inside Sell/Equip.

## Run

```bash
./loot_watcher.sh info
./loot_watcher.sh auto
./loot_watcher.sh auto 192.168.28.176:32783
```

The wrapper auto-selects a unique ADB device. `info` mode auto-configures the existing Termux SSH/ADB-forward path when the key exists. `auto` mode does not depend on Termux.

## Behavior

- OCR is paused while `com.lavalabs.dungeonrush` is not foreground.
- Returning to the game resets only the visual gate; the semantic candidate hash stays intact so the same item is not emitted/clicked twice.
- Visual signatures and candidate hashes have a time-to-live (TTL, defaulting to 5.0s) so the watcher retries if an error occurs or a candidate remains unhandled instead of staying idle forever.
- There is no fixed 2-second foreground polling delay. ADB screenshot/foreground calls naturally pace the loop. Background checks default to 0.5s and OCR-error retries to 0.25s.
- Auto mode is fail-closed: no action on CHECK OCR, missing rarity/level, incomplete affixes, changed candidate, changed decision, or lost foreground.
- After a touch, the candidate is consumed even if visual confirmation fails, preventing accidental double-clicks.

## Base-power scoring

Uses the game formula extracted in `dungeon-rush-simulator`:

```text
power = tier_scaler^tier × (1 + level_scaler × level)
tier_scaler  = 3.1622776985168457
level_scaler = 0.014999999664723873
```

The slot-specific base stat cancels out. `power` is log-normalized so `Immortal Lv1 = -15` and `Divine Lv130 = +20`. Examples: `Immortal 65 ≈ -4.50`, `Immortal 66 ≈ -4.38`, `Divine 88 ≈ +16.21`.

## Tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q dungeon_rush_loot
bash -n loot_watcher.sh
```
