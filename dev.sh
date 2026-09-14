#!/usr/bin/env bash
#
# Run the backend and the dashboard together, and shut both down on Ctrl-C.
#
#   ./dev.sh
#
# To work on one side only, run ./backend/run.sh or ./frontend/run.sh in its own terminal
# instead — separate terminals give you separate, readable logs.
#
# Both services print a banner naming their own URL, so the interleaved output stays
# tellable apart without prefixing (prefixing would mean running each through a pipe, and
# the PID we would then be tracking would be the pipe's, not the server's).
#
# Do NOT source this file (`. dev.sh`) — it installs signal traps and would hijack your shell.
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
  echo "  incorrect: source dev.sh   /   . dev.sh" >&2
  echo >&2
  echo "  It installs signal traps and would take over your interactive shell." >&2
  return 1 2>/dev/null || exit 1
fi

# Strict mode is enabled only *after* the guard. Enabling it earlier would leak
# `set -euo pipefail` into an interactive shell that sources this file, and the `return 1`
# above would then make that shell exit rather than simply report the mistake.
set -euo pipefail

cd -- "$SCRIPT_DIR"

for required in backend/run.sh frontend/run.sh; do
  if [ ! -x "$required" ]; then
    echo "error: $required is missing or not executable." >&2
    echo "       Restore it with: chmod +x $required" >&2
    exit 1
  fi
done

pids=()

cleanup() {
  # Disarm the trap first: kill/wait below must not re-enter this handler.
  trap - EXIT INT TERM
  echo
  echo "shutting down…"
  if [ "${#pids[@]}" -gt 0 ]; then
    for pid in "${pids[@]}"; do
      kill "$pid" 2>/dev/null || true
    done
    for pid in "${pids[@]}"; do
      wait "$pid" 2>/dev/null || true
    done
  fi
}
trap cleanup EXIT INT TERM

# Both scripts `exec` their server, so each PID *is* the server process — killing it works
# without hunting for children.
./backend/run.sh &
pids+=("$!")

./frontend/run.sh &
pids+=("$!")

echo "backend + dashboard starting — press Ctrl-C to stop both"

# Wait for whichever finishes first and then tear the other down, so a crashed backend
# cannot leave a dashboard serving against a dead API.
if [ "${BASH_VERSINFO[0]}" -gt 4 ] ||
  { [ "${BASH_VERSINFO[0]}" -eq 4 ] && [ "${BASH_VERSINFO[1]}" -ge 3 ]; }; then
  wait -n
else
  wait
fi
