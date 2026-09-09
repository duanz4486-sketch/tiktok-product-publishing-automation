#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8002}"

"$PYTHON_BIN" -m pip install -r requirements.txt
"$PYTHON_BIN" scripts/check_setup.py
exec "$PYTHON_BIN" web_app.py --host "$HOST" --port "$PORT"
