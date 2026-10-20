#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Python 3 was not found. Install python3, then run this script again.' >&2
    exit 127
fi
exec python3 "$SCRIPT_DIR/manage_frog.py" restore "$@"
