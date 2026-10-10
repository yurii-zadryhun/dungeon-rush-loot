#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-info}"
SERIAL="${2:-}"
[[ "$MODE" == "info" || "$MODE" == "auto" ]] || { echo "Usage: $0 [info|auto] [ADB_SERIAL]" >&2; exit 2; }

select_device() {
  if [[ -n "$SERIAL" ]]; then return; fi
  mapfile -t tcp < <(adb devices | awk '$2 == "device" && $1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+$/ {print $1}')
  if (( ${#tcp[@]} == 1 )); then SERIAL="${tcp[0]}"; return; fi
  mapfile -t all < <(adb devices | awk '$2 == "device" {print $1}')
  if (( ${#all[@]} == 1 )); then SERIAL="${all[0]}"; return; fi
  echo "Could not uniquely select an ADB device. Pass it explicitly." >&2
  adb devices >&2
  exit 1
}

termux_user() {
  local uid android_user app_id app_number
  uid="$(adb -s "$SERIAL" shell cmd package list packages -U com.termux 2>/dev/null | tr -d '\r' | sed -n 's/.*uid:\([0-9][0-9]*\).*/\1/p' | head -n1)"
  [[ "$uid" =~ ^[0-9]+$ ]] || return 1
  android_user=$(( uid / 100000 )); app_id=$(( uid % 100000 )); app_number=$(( app_id - 10000 ))
  (( app_number >= 0 )) || return 1
  printf 'u%s_a%s\n' "$android_user" "$app_number"
}

select_device
PY="python3"; [[ -x .venv/bin/python ]] && PY=.venv/bin/python
ARGS=(--adb "$SERIAL" --mode "$MODE" --device "${PADDLE_DEVICE:-gpu:0}")

if [[ "$MODE" == "info" && "${PHONE_NOTIFY:-1}" == "1" ]]; then
  KEY="${PHONE_SSH_KEY:-$HOME/.ssh/id_ed25519_termux}"
  PORT="${PHONE_FORWARD_PORT:-8022}"
  if [[ -f "$KEY" ]]; then
    USER="$(termux_user || true)"; USER="${USER:-termux}"
    if adb -s "$SERIAL" forward "tcp:$PORT" tcp:8022 >/dev/null 2>&1; then
      ARGS+=(--phone-ssh "$USER@127.0.0.1" --phone-ssh-port "$PORT" --phone-ssh-key "$KEY" --phone-ssh-trust-transport --phone-toast --phone-push)
    fi
  fi
fi

#echo "Dungeon Rush loot watcher ($MODE)"
exec "$PY" -m src "${ARGS[@]}" \
#  --verbose
