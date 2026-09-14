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
  echo "  incorrect: source frontend/run.sh   /   . frontend/run.sh" >&2
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

if [ ! -f package.json ]; then
  echo "error: package.json not found under $SCRIPT_DIR" >&2
  echo "       Run this script from a full checkout of the project." >&2
  exit 1
fi

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
