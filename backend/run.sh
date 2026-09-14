#!/usr/bin/env bash
#
# Start the JaiSadguru backend.
#
# Must run from backend/ so that `vendor` is importable as a sibling of `app`.
# Extra arguments are forwarded to uvicorn, e.g.:
#
#   ./run.sh --reload
#
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ] && ! python3 -c "import fastapi" >/dev/null 2>&1; then
  echo "warning: FastAPI is not importable. Create a virtualenv and install deps first:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
fi

exec uvicorn app.main:app \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8000}" \
  "$@"
