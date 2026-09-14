#!/usr/bin/env bash
#
# One-time dependency setup: backend virtualenv + frontend npm install.
#
#   ./setup.sh
#
# Idempotent — safe to re-run. Nothing is installed globally; the Python environment is
# confined to backend/.venv and Node packages to frontend/node_modules (both git-ignored).
#
# CPU-only machines should set TORCH_INDEX to avoid pip pulling a multi-gigabyte CUDA build:
#
#   TORCH_INDEX=https://download.pytorch.org/whl/cpu ./setup.sh
#
# Do NOT source this file (`. setup.sh`). See the guard below.
#
# Resolve our own directory from BASH_SOURCE rather than $0: when a file is *sourced*, $0 is
# the invoking shell's name, so `dirname "$0"` silently resolves to the wrong place.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Refuse to run if sourced. Sourcing would leak `set -euo pipefail` into your interactive
# shell, and any relative path would resolve against wherever you happened to be.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  echo "error: this script must be run, not sourced." >&2
  echo >&2
  echo "  correct:   ${SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" >&2
  echo "  incorrect: source setup.sh   /   . setup.sh" >&2
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

# Fail before touching anything if this is not a full checkout. Otherwise a wrong directory
# shows up much later as a confusing pip error about a missing requirements file.
missing=0
for required in backend/requirements.txt frontend/package.json; do
  if [ ! -f "$required" ]; then
    echo "error: $required not found under $SCRIPT_DIR" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo >&2
  echo "Run this from a full checkout of the project, or delete the partial install and" >&2
  echo "re-clone:" >&2
  echo "  rm -rf backend/.venv && ./setup.sh" >&2
  exit 1
fi

TORCH_INDEX="${TORCH_INDEX:-}"

echo "==> project root: $SCRIPT_DIR"

# ------------------------------------------------------------------ backend

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 was not found. Install Python 3.10+ and re-run." >&2
  exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "error: Python 3.10+ is required, found $(python3 -V 2>&1)." >&2
  exit 1
fi

if [ ! -d backend/.venv ]; then
  echo "==> creating backend/.venv"
  python3 -m venv backend/.venv
else
  echo "==> reusing backend/.venv"
fi

echo "==> upgrading pip"
backend/.venv/bin/python -m pip install --upgrade pip

if [ -n "$TORCH_INDEX" ]; then
  echo "==> installing torch from $TORCH_INDEX"
  backend/.venv/bin/python -m pip install torch --index-url "$TORCH_INDEX"
fi

echo "==> installing backend requirements (this pulls torch if not already installed)"
backend/.venv/bin/python -m pip install -r backend/requirements.txt

# ------------------------------------------------------------------ frontend

if ! command -v npm >/dev/null 2>&1; then
  echo "error: npm was not found. Install Node.js 20+ and re-run." >&2
  exit 1
fi

echo "==> installing frontend dependencies"
(cd frontend && npm install --no-audit --no-fund)

# ------------------------------------------------------------------ done

cat <<'MSG'

Setup complete.

  ./dev.sh            backend + dashboard together
  ./backend/run.sh    API only       -> http://localhost:8000   (docs at /docs)
  ./frontend/run.sh   dashboard only -> http://localhost:5173

The first forecast downloads the Kronos weights from Hugging Face (~100 MB for
kronos-small) into ~/.cache/huggingface. Nothing needs to be installed for that, and no
API keys are required anywhere in this project.

MSG
