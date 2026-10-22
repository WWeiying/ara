#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
unit=ara-dsa-linux-no-raid6-final-v2-vcs-compile-20260924-01.service
out="$root/verification/out/soc-no-raid6-bench-final-rtl-v2-compile-20260924-01"
python="$root/verification/tools/soc-venv/bin/python"

while [[ $(systemctl --user show "$unit" -p ActiveState --value) == active ]]; do
  sleep 30
done
[[ $(systemctl --user show "$unit" -p Result --value) == success ]]
[[ $(systemctl --user show "$unit" -p ExecMainStatus --value) == 0 ]]
[[ -s "$out/compile/simv" && -s "$out/summary.json" ]]

set +e
"$python" "$root/verification/fpga/run_soc_smoke.py" \
  --mode linux --output "$out" --run-only --run-timeout 10800 \
  --linux-fail-fast --linux-no-progress-timeout 900 \
  --linux-first-progress-timeout 900 --cache-tag-probe \
  > "$out/linux_run_driver.log" 2>&1
run_status=$?
"$python" "$root/verification/fpga/check_soc_linux.py" "$out" \
  --report "$out/independent_boot_audit.json" \
  > "$out/linux_audit_driver.log" 2>&1
audit_status=$?
set -e

if ((run_status != 0 || audit_status != 0)); then
  printf 'Linux RTL run failed: runner=%d audit=%d\n' "$run_status" "$audit_status" >&2
  exit 1
fi
printf 'Linux RTL run and independent audit passed: %s\n' "$out"
