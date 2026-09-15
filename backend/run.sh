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

# Locate the interpreter built by ./setup.sh. Resolving it explicitly — rather than trusting
# PATH and activation — means this behaves identically whether or not you remembered to
# `conda activate` first, which is the most common way to end up running the wrong Python.
CONDA_ENV_NAME="${CONDA_ENV_NAME:-jaisadguru}"

PYTHON=""
ENV_LABEL=""

# `conda env list` prints the name first and the prefix last, with an optional `*` marking
# the active env.
if command -v conda >/dev/null 2>&1; then
  PREFIX="$(conda env list 2>/dev/null | awk -v n="$CONDA_ENV_NAME" '$1 == n { print $NF; exit }')"
  if [ -n "$PREFIX" ] && [ -x "$PREFIX/bin/python" ]; then
    PYTHON="$PREFIX/bin/python"
    ENV_LABEL="conda env '$CONDA_ENV_NAME'"
  fi
fi

if [ -z "$PYTHON" ] && [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
  ENV_LABEL="backend/.venv"
fi

if [ -z "$PYTHON" ] && command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
  ENV_LABEL="system python3"
fi

if [ -z "$PYTHON" ]; then
  cat >&2 <<'MSG'
error: no Python interpreter was found.

Set up the backend environment first, from the project root:

  ./setup.sh

MSG
  exit 1
fi

if ! "$PYTHON" -c "import fastapi" >/dev/null 2>&1; then
  echo "error: FastAPI is not importable with $PYTHON" >&2
  echo "       ($ENV_LABEL)" >&2
  echo "       Build the backend environment from the project root:" >&2
  echo "         ./setup.sh" >&2
  exit 1
fi

# torch is deliberately not required to start: the API boots without it and reports the
# problem through /api/health. But every forecast would fail, so say so now rather than
# letting it surface as a confusing click later.
if ! "$PYTHON" -c "import torch" >/dev/null 2>&1; then
  # Plain echo rather than a heredoc so that $PYTHON interpolates — quoting the heredoc
  # delimiter would have printed the variable name literally.
  echo "warning: torch is not installed — the API will start but every forecast will fail," >&2
  echo "         and /api/health will report \"degraded\"." >&2
  echo >&2
  echo "  Install it into the backend environment:" >&2
  echo "    $PYTHON -m pip install torch" >&2
  echo >&2
  echo "  Or rebuild the environment with CPU-only torch (no multi-gigabyte CUDA build):" >&2
  echo "    TORCH_INDEX=https://download.pytorch.org/whl/cpu ./setup.sh" >&2
  echo >&2
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  echo "note: no backend/.env found — running on defaults (.env.example documents every knob)"
fi

echo "JaiSadguru API → http://localhost:${PORT}   (docs: http://localhost:${PORT}/docs)"
echo "                $ENV_LABEL · $("$PYTHON" -V 2>&1)"

# `-m uvicorn` rather than the uvicorn entry point: it works identically for a conda env, a
# venv and a system interpreter, with no need to resolve where the script happens to live.
exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
