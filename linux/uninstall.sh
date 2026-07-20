#!/usr/bin/env sh
set -eu

DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
INSTALL_HOME=${CODEXLEAN_HOME:-"$DATA_HOME/codexlean"}
BIN_DIR=${CODEXLEAN_BIN_DIR:-"$HOME/.local/bin"}
VENV="$INSTALL_HOME/venv"
MARKER="$INSTALL_HOME/.codexlean-install"
CODEXLEAN="$VENV/bin/codexlean"
SCOPE=${CODEXLEAN_SCOPE:-user}

case "$SCOPE" in
  user|project) ;;
  *) printf '%s\n' "codexlean: CODEXLEAN_SCOPE must be user or project" >&2; exit 2 ;;
esac

[ "$INSTALL_HOME" != "/" ] || {
  printf '%s\n' "codexlean: refusing to remove /" >&2
  exit 1
}

if [ -e "$INSTALL_HOME" ] && [ ! -f "$MARKER" ]; then
  printf '%s\n' "codexlean: refusing to remove unrecognized directory: $INSTALL_HOME" >&2
  exit 1
fi

if [ -x "$CODEXLEAN" ]; then
  set -- uninstall --scope "$SCOPE"
  if [ "$SCOPE" = project ]; then
    PROJECT=${CODEXLEAN_PROJECT:-$PWD}
    set -- "$@" --project "$PROJECT"
  fi
  "$CODEXLEAN" "$@"
fi

if [ -L "$BIN_DIR/codexlean" ]; then
  TARGET=$(readlink "$BIN_DIR/codexlean" || true)
  if [ "$TARGET" = "$CODEXLEAN" ]; then
    rm -f "$BIN_DIR/codexlean"
  fi
fi
rm -rf "$INSTALL_HOME"
printf '%s\n' "Removed CodexLean from $INSTALL_HOME"
