#!/usr/bin/env bash
#
# Start the JaiSadguru backend (FastAPI + Uvicorn).
#
# cd's to backend/ itself, because `vendor` must resolve as a sibling of `app` no matter
# where the script is called from.
#
#   ./run.sh                 # http://localhost:8000
#   ./run.sh --reload        # extra arguments are forwarded to uvicorn
#   PORT=9000 ./run.sh
#
# Environment: HOST, PORT, LOG_LEVEL, plus every knob in .env.example.
#
set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

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
