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
set -euo pipefail

cd "$(dirname "$0")"

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
