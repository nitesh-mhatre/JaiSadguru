#!/usr/bin/env bash
#
# Start the JaiSadguru dashboard (Vite dev server).
#
#   ./run.sh                 # http://localhost:5173
#   ./run.sh --open          # extra arguments are forwarded to vite
#   PORT=4000 ./run.sh
#
# The dev server proxies /api to the backend, so the browser stays on a single origin and
# development never needs CORS. Point it elsewhere with VITE_API_TARGET.
#
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-5173}"
HOST="${HOST:-0.0.0.0}"
export VITE_API_TARGET="${VITE_API_TARGET:-http://localhost:8000}"

if [ ! -x node_modules/.bin/vite ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "error: npm was not found and node_modules is missing." >&2
    echo "       Install Node.js 20+ and re-run, or run ./setup.sh from the project root." >&2
    exit 1
  fi
  echo "node_modules is missing — installing dependencies (first run only, ~30s)…"
  npm install --no-audit --no-fund
fi

echo "JaiSadguru dashboard → http://localhost:${PORT}   (proxying /api to ${VITE_API_TARGET})"

# exec the vite binary directly rather than `npm run dev`: with npm in between, this PID
# would be npm and Ctrl-C would leave vite running as an orphan.
exec node_modules/.bin/vite --host "$HOST" --port "$PORT" "$@"
