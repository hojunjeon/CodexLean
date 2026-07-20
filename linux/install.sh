#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
INSTALL_HOME=${CODEXLEAN_HOME:-"$DATA_HOME/codexlean"}
BIN_DIR=${CODEXLEAN_BIN_DIR:-"$HOME/.local/bin"}
VENV="$INSTALL_HOME/venv"
MARKER="$INSTALL_HOME/.codexlean-install"
LAUNCHER="$BIN_DIR/codexlean"
PYTHON=${PYTHON:-python3}
SCOPE=${CODEXLEAN_SCOPE:-user}

case "$SCOPE" in
  user|project) ;;
  *) printf '%s\n' "codexlean: CODEXLEAN_SCOPE must be user or project" >&2; exit 2 ;;
esac

[ "$INSTALL_HOME" != "/" ] || {
  printf '%s\n' "codexlean: refusing to use / as CODEXLEAN_HOME" >&2
  exit 1
}

if [ -e "$INSTALL_HOME" ] && [ ! -f "$MARKER" ]; then
  printf '%s\n' "codexlean: refusing to overwrite unrecognized directory: $INSTALL_HOME" >&2
  exit 1
fi

if [ -e "$LAUNCHER" ] || [ -L "$LAUNCHER" ]; then
  TARGET=$(readlink "$LAUNCHER" 2>/dev/null || true)
  if [ "$TARGET" != "$VENV/bin/codexlean" ]; then
    printf '%s\n' "codexlean: refusing to replace unrelated launcher: $LAUNCHER" >&2
    exit 1
  fi
fi

command -v "$PYTHON" >/dev/null 2>&1 || {
  printf '%s\n' "codexlean: Python 3.10+ is required" >&2
  exit 1
}
"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  printf '%s\n' "codexlean: Python 3.10+ is required" >&2
  exit 1
}

mkdir -p "$INSTALL_HOME" "$BIN_DIR"
printf '%s\n' "CodexLean managed installation" > "$MARKER"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check "$ROOT"
ln -sfn "$VENV/bin/codexlean" "$LAUNCHER"

set -- install --scope "$SCOPE"
if [ "$SCOPE" = project ]; then
  PROJECT=${CODEXLEAN_PROJECT:-$PWD}
  set -- "$@" --project "$PROJECT"
fi
"$VENV/bin/codexlean" "$@"

set -- doctor --scope "$SCOPE"
if [ "$SCOPE" = project ]; then
  set -- "$@" --project "$PROJECT"
fi
"$VENV/bin/codexlean" "$@"

printf '%s\n' "Installed CodexLean in $VENV"
printf '%s\n' "Launcher: $BIN_DIR/codexlean"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) printf '%s\n' "Add $BIN_DIR to PATH to run codexlean directly." ;;
esac
