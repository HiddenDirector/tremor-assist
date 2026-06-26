#!/usr/bin/env bash
# Build the native backend:
#   libtremorcore.dylib    - portable C hot-path math (One Euro / dead-zone / scroll)
#   libtremorengine.dylib  - Swift CGEventTap engine that links the C core
#
# Output goes to native/build/. The Python side (tremor_assist/native.py) loads
# these if present and otherwise falls back to the pure-Python implementation.
set -euo pipefail
cd "$(dirname "$0")"

OUT="build"
mkdir -p "$OUT"

CFLAGS="-O3 -fPIC -Wall -Wextra"

echo "[1/3] compiling C core -> object"
cc $CFLAGS -c tremor_core.c -o "$OUT/tremor_core.o"

echo "[2/3] linking libtremorcore.dylib"
cc -dynamiclib -install_name @rpath/libtremorcore.dylib \
   "$OUT/tremor_core.o" -o "$OUT/libtremorcore.dylib"

# The Swift engine is macOS-only (needs CoreGraphics + an event tap).
if command -v swiftc >/dev/null 2>&1; then
  echo "[3/3] building Swift event-tap engine -> libtremorengine.dylib"
  swiftc -O -emit-library \
    -import-objc-header tremor_core.h \
    "$OUT/tremor_core.o" tremor_engine.swift \
    -framework CoreGraphics -framework Foundation \
    -o "$OUT/libtremorengine.dylib"
else
  echo "[3/3] swiftc not found - skipping Swift engine (C core still built)"
fi

echo "done -> $OUT/"
ls -la "$OUT"
