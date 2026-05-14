#!/usr/bin/env bash
# Build the standalone app and ad-hoc code-sign it.
#
# Ad-hoc signing gives the bundle a stable identity, which is what lets the
# Accessibility / Input Monitoring permission you grant actually persist instead
# of silently resetting (a common gotcha with unsigned apps).
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "› Generating icon…"
"$PY" tools/make_icon.py

echo "› Building standalone app (py2app)…"
rm -rf build dist
"$PY" setup.py py2app

echo "› Ad-hoc code-signing…"
codesign --force --deep --sign - dist/TremorAssist.app
codesign --verify --deep --strict dist/TremorAssist.app && echo "  signature OK"

echo "✓ Built dist/TremorAssist.app"
echo "  First run: grant Accessibility (mouse) and Input Monitoring (keys) in"
echo "  System Settings ▸ Privacy & Security, then reopen the app."
