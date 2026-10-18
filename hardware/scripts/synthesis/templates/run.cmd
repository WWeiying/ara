#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
exec 9>.dc.lock
flock -n 9 || { echo 'Another DC process owns this run directory.' >&2; exit 1; }
test ! -e dc.log || { echo 'Run already attempted; prepare a new directory.' >&2; exit 1; }
export DC_HOME="${DC_HOME:-/home/wangwy/software/synopsys/install/syn/syn/T-2022.03-SP2}"
export PATH="$DC_HOME/bin:$PATH"
export SNPSLMD_LICENSE_FILE="${SNPSLMD_LICENSE_FILE:-27000@t7920}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-/home/wangwy/software/synopsys/license/Synopsys.dat}"
printf 'stage=STARTING\n' > dc.status
trap 'printf "runner_exit_code=%s\n" "$?" >> dc.status' EXIT
"$DC_HOME/bin/dc_shell-t" -64bit -f ../global_scripts/dc.tcl 2>&1 | tee dc.log
if grep -Eq '^(Error:|Fatal:|RCE_DC_FAILURE:)|^DC_FLOW_ERROR_COUNT=[1-9]' dc.log; then exit 1; fi
if [[ ${RCE_ELAB_ONLY:-0} == 1 ]]; then
    grep -qx DC_ELAB_COMPLETE dc.log
else
    grep -qx DC_FLOW_COMPLETE dc.log
    test -s ../outputs/ara_soc_dc.ddc
    test -s ../outputs/ara_soc_dc.v
    test -s ../outputs/ara_soc_dc.sdc
fi
