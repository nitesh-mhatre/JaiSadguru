#!/usr/bin/env bash
#
# One-time dependency setup: backend environment + frontend npm install.
#
#   ./setup.sh
#
# The backend environment is built with conda when conda is available, and with a stdlib
# venv otherwise. Either way nothing is installed globally — the environment lives under
# conda's envs directory (or backend/.venv), and Node packages in frontend/node_modules.
# Both are git-ignored.
#
#   CONDA_ENV_NAME=jaisadguru ./setup.sh                    # override the env name
#   TORCH_INDEX=https://download.pytorch.org/whl/cpu ./setup.sh   # CPU-only torch
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

CONDA_ENV_NAME="${CONDA_ENV_NAME:-jaisadguru}"
TORCH_INDEX="${TORCH_INDEX:-}"

# ------------------------------------------------------------------ layout check
# Fail before touching anything if this is not a full checkout. Otherwise a wrong directory
# shows up much later as a confusing pip error about a missing requirements file.
missing=0
for required in backend/requirements.txt backend/environment.yml frontend/package.json; do
  if [ ! -f "$required" ]; then
    echo "error: $required not found under $SCRIPT_DIR" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo >&2
  echo "Run this from a full checkout of the project, or clear the partial install and" >&2
  echo "re-run:" >&2
  echo "  rm -rf backend/.venv && ./setup.sh" >&2
  exit 1
fi

echo "==> project root: $SCRIPT_DIR"

# ------------------------------------------------------------------ interpreter
# Resolution order: existing conda env -> create conda env -> stdlib venv.
# conda comes first because conda-forge supplies prebuilt aarch64 numpy/pandas, which is
# the difference between a two-minute setup and a failed source compile.

# Prints the filesystem prefix of a named conda env, or nothing. `conda env list` puts the
# name first and the prefix last, with an optional `*` marking the active env.
conda_env_prefix() {
  conda env list 2>/dev/null | awk -v n="$1" '$1 == n { print $NF; exit }'
}

PYTHON=""
ENV_LABEL=""

if command -v conda >/dev/null 2>&1; then
  PREFIX="$(conda_env_prefix "$CONDA_ENV_NAME")"
  if [ -z "$PREFIX" ] || [ ! -x "$PREFIX/bin/python" ]; then
    echo "==> creating conda env '$CONDA_ENV_NAME' (python 3.12 + numpy + pandas, conda-forge)"
    conda env create -y -n "$CONDA_ENV_NAME" -f backend/environment.yml
    PREFIX="$(conda_env_prefix "$CONDA_ENV_NAME")"
  else
    echo "==> reusing conda env '$CONDA_ENV_NAME'"
  fi

  if [ -n "$PREFIX" ] && [ -x "$PREFIX/bin/python" ]; then
    PYTHON="$PREFIX/bin/python"
    ENV_LABEL="conda env '$CONDA_ENV_NAME'"
  else
    echo "error: created the conda env but could not locate its interpreter." >&2
    echo "       Looked for an env named '$CONDA_ENV_NAME' in: conda env list" >&2
    exit 1
  fi
else
  echo "==> conda not found, falling back to a stdlib venv"
  echo "    (install Miniconda if pip has to compile numpy/pandas from source)"

  if ! command -v python3 >/dev/null 2>&1; then
    echo "error: neither conda nor python3 was found. Install Miniconda and re-run." >&2
    exit 1
  fi

  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "error: Python 3.10+ is required, found $(python3 -V 2>&1)." >&2
    exit 1
  fi

  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info < (3, 14) else 1)'; then
    cat >&2 <<'MSG'
warning: this Python has no numpy/pandas wheels yet, so pip will try to build them from
         source and will fail unless the Python development headers are installed.

         Install Miniconda and re-run (recommended):
           curl -fsSLO https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh

MSG
  fi

  if [ ! -d backend/.venv ]; then
    echo "==> creating backend/.venv"
    python3 -m venv backend/.venv
  else
    echo "==> reusing backend/.venv"
  fi
  PYTHON="backend/.venv/bin/python"
  ENV_LABEL="backend/.venv"
fi

echo "==> interpreter: $PYTHON ($("$PYTHON" -V 2>&1))"

# ------------------------------------------------------------------ python packages

echo "==> upgrading pip"
"$PYTHON" -m pip install --upgrade pip

if [ -n "$TORCH_INDEX" ]; then
  echo "==> installing torch from $TORCH_INDEX"
  "$PYTHON" -m pip install torch --index-url "$TORCH_INDEX"
fi

echo "==> installing backend requirements (this pulls torch, ~200 MB on first run)"
"$PYTHON" -m pip install -r backend/requirements.txt

# ------------------------------------------------------------------ frontend

if ! command -v npm >/dev/null 2>&1; then
  echo "error: npm was not found. Install Node.js 20+ and re-run." >&2
  exit 1
fi

echo "==> installing frontend dependencies"
(cd frontend && npm install --no-audit --no-fund)

# ------------------------------------------------------------------ done

cat <<MSG

Setup complete. Backend environment: $ENV_LABEL

  ./dev.sh            backend + dashboard together
  ./backend/run.sh    API only       -> http://localhost:8000   (docs at /docs)
  ./frontend/run.sh   dashboard only -> http://localhost:5173

The first forecast downloads the Kronos weights from Hugging Face (~100 MB for
kronos-small) into ~/.cache/huggingface. Nothing needs to be installed for that, and no
API keys are required anywhere in this project.

MSG
