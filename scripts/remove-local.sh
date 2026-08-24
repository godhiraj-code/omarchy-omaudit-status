#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ID="godhiraj.omaudit-status"

command -v omarchy >/dev/null 2>&1 || {
  printf 'error: omarchy is not available on PATH\n' >&2
  exit 1
}

# Use Omarchy's lifecycle commands so shell configuration and plugin files are
# updated through the supported path rather than overwritten manually.
omarchy plugin disable "$PLUGIN_ID"
omarchy plugin remove "$PLUGIN_ID" --yes

printf 'Omaudit Status removed. Omaudit was left installed as a separate tool.\n'
