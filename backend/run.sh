#!/usr/bin/env bash
#
# Start the JaiSadguru backend (FastAPI + Uvicorn).
#
#   ./run.sh                 # http://localhost:8000
#   ./run.sh --reload        # extra arguments are forwarded to uvicorn
#   PORT=9000 ./run.sh
#
# Environment: HOST, PORT, LOG_LEVEL, plus every knob in .env.example.
#
# Do NOT source this file (`. run.sh`) — it calls exec and would replace your shell.
#
# Resolve our own directory from BASH_SOURCE rather than $0: when a file is *sourced*, $0 is
# the invoking shell's name, so `dirname "$0"` silently resolves to the wrong place.
# (This preamble is deliberately duplicated in each script so every one stays runnable on
# its own — a script that needs its neighbour first is worse than ten repeated lines.)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  echo "error: this script must be run, not sourced." >&2
  echo >&2
  echo "  correct:   ${SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" >&2
  echo "  incorrect: source backend/run.sh   /   . backend/run.sh" >&2
  echo >&2
  echo "  Sourcing changes where relative paths resolve, because \$0 becomes your" >&2
  echo "  shell's name instead of this script's path." >&2
  return 1 2>/dev/null || exit 1
fi

# Strict mode is enabled only *after* the guard. Enabling it earlier would leak
# `set -euo pipefail` into an interactive shell that sources this file, and the `return 1`
# above would then make that shell exit rather than simply report the mistake.
set -euo pipefail

cd -- "$SCRIPT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Must run from backend/ so that `vendor` resolves as a sibling of `app`.
if [ ! -f app/main.py ]; then
  echo "error: app/main.py not found under $SCRIPT_DIR" >&2
  echo "       Run this script from a full checkout of the project." >&2
  exit 1
fi

# Prefer the project virtualenv, so a stray global uvicorn cannot be picked up by accident.
UVICORN="uvicorn"
PYTHON="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
fi
if [ -x ".venv/bin/uvicorn" ]; then
  UVICORN=".venv/bin/uvicorn"
fi

if [ ! -x "$UVICORN" ] && ! command -v "$UVICORN" >/dev/null 2>&1; then
  cat >&2 <<'MSG'
error: uvicorn was not found.

Set up the environment first, from the project root:

  ./setup.sh

or manually, from backend/:

  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt

MSG
  exit 1
fi

if ! "$PYTHON" -c "import fastapi" >/dev/null 2>&1; then
  echo "error: FastAPI is not importable with $PYTHON." >&2
  echo "       Install the backend dependencies:" >&2
  echo "         $PYTHON -m pip install -r requirements.txt" >&2
  exit 1
fi

# torch is deliberately not required to start: the API boots without it and reports the
# problem through /api/health. But every forecast would fail, so say so now rather than
# letting it surface as a confusing click later.
if ! "$PYTHON" -c "import torch" >/dev/null 2>&1; then
  cat >&2 <<'MSG'
warning: torch is not installed — the API will start but every forecast will fail,
         and /api/health will report "degraded".

  CPU-only machines (avoids a multi-gigabyte CUDA download):
    .venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu

MSG
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  echo "note: no backend/.env found — running on defaults (.env.example documents every knob)"
fi

echo "JaiSadguru API → http://localhost:${PORT}   (docs: http://localhost:${PORT}/docs)"

exec "$UVICORN" app.main:app --host "$HOST" --port "$PORT" "$@"
