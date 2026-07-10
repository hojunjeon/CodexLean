#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WHEEL=$(find "$ROOT/dist" -maxdepth 1 -name 'codexlean-*.whl' -print 2>/dev/null | sort | tail -n 1 || true)
if [ -n "$WHEEL" ]; then
  python3 -m pip install "$WHEEL"
else
  python3 -m pip install "$ROOT"
fi
codexlean install --scope "${CODEXLEAN_SCOPE:-user}"
codexlean doctor --scope "${CODEXLEAN_SCOPE:-user}" || true
