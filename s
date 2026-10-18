#!/usr/bin/env bash
# Repository-local synthesis entry; no shell aliases or global environment edits.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")" && pwd)
if (( $# == 0 )); then
    exec python3 "$root/hardware/scripts/synthesis/unified.py" --help
fi
exec python3 "$root/hardware/scripts/synthesis/unified.py" "$@"
