#!/usr/bin/env bash
# Convenience launcher: sets up the venv on first run, then starts the app.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "First run: creating virtual environment and installing dependencies…"
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python -m tremor_assist "$@"
