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
set -euo pipefail

cd "$(dirname "$0")"

TORCH_INDEX="${TORCH_INDEX:-}"

# ------------------------------------------------------------------ backend

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 was not found. Install Python 3.10+ and re-run." >&2
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
