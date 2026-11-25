#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ "$#" -eq 1 ] || { echo 'usage: sh run_cost_pair.sh NEW_RESULT_DIRECTORY' >&2; exit 2; }
[ "${RESIDENT_PHASE_STATS:-0}" = 0 ] || { echo 'Primary measurements require phase probes OFF' >&2; exit 2; }
profile=/sys/module/ara_resident/parameters/profile
[ -r "$profile" ] || { echo 'New Resident module is not loaded' >&2; exit 2; }
case "$(cat "$profile")" in N|0) ;; *) echo 'Reload with profile=0 before timing' >&2; exit 2 ;; esac
actual=$(sha256sum "$here/ara_resident.ko" | cut -d' ' -f1)
[ "${RESIDENT_MODULE_SHA256:-}" = "$actual" ] || { echo 'Declared module SHA must match this bundle; verify loaded version' >&2; exit 2; }
exec sh "$here/run_board.sh" "$1"
