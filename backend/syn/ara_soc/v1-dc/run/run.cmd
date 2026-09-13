#!/usr/bin/env bash
set -o pipefail

cd -- "$(dirname -- "$0")" || exit 1
source ../global_scripts/dc_lock.sh || exit 1
dc_acquire_lock .dc.lock || exit 1
stamp="$(date -u +%Y%m%d_%H%M%S)_$$"
mkdir -p log_archive || exit 1
for previous in dc.log dc.status; do
    if [ -f "$previous" ]; then
        cp -p -- "$previous" "log_archive/${stamp}_${previous}" || exit 1
    fi
done
printf 'stage=STARTING\n' > dc.status
trap 'printf "runner_exit_code=%s\n" "$?" >> dc.status' EXIT
export DC_BATCH=1
dc_shell-t -64bit -f ../global_scripts/dc.tcl 2>&1 | tee dc.log
rc=$?
if [ "$rc" -ne 0 ]; then exit "$rc"; fi
# DC may report Tcl/HDL errors while returning zero. Do not collect old outputs.
if grep -Eq '^(Error:|Fatal:)|^DC_FLOW_ERROR_COUNT=[1-9][0-9]*' dc.log; then exit 1; fi
if [ "${DC_ELAB_ONLY:-0}" = 1 ]; then
    grep -qx 'DC_ELAB_COMPLETE' dc.log
else
    grep -qx 'DC_FLOW_COMPLETE' dc.log
fi
