#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-cpu.txt
python -m unittest discover -s tests -v
python -m compileall -q src

echo
echo "Ready. Copy equipment.example.json to equipment.json, fill the current eight slots, then run ./loot_watcher.sh."
