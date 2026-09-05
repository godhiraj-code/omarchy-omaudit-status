#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ID="godhiraj.omaudit-status"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PLUGIN_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins"
TARGET_DIR="$PLUGIN_ROOT/$PLUGIN_ID"

command -v omarchy >/dev/null 2>&1 || {
  printf 'error: omarchy is not available on PATH\n' >&2
  exit 1
}
command -v omaudit >/dev/null 2>&1 || {
  printf 'error: Omaudit v0.1.0 or newer must be installed separately\n' >&2
  exit 1
}

if [[ -e "$TARGET_DIR" || -L "$TARGET_DIR" ]]; then
  printf 'error: %s already exists; refusing to overwrite it\n' "$TARGET_DIR" >&2
  exit 1
fi

omarchy plugin validate "$SOURCE_DIR"
mkdir -p -- "$PLUGIN_ROOT"
# Atomic mkdir establishes ownership; a concurrent install is never removed.
mkdir -- "$TARGET_DIR"

cleanup_new_copy() {
  rm -rf -- "$TARGET_DIR"
  omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
}
trap cleanup_new_copy ERR
cp -a -- "$SOURCE_DIR/." "$TARGET_DIR"
omarchy-shell shell rescanPlugins
omarchy plugin enable "$PLUGIN_ID" --section right
trap - ERR

printf 'Omaudit Status installed and enabled from %s\n' "$SOURCE_DIR"
