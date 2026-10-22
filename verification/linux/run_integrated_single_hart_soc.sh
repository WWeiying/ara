#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-integrated-linux-soc-compile-20260925-02.service
run="${root}/verification/out/integrated-linux-soc-compile-20260925-01"
python="${root}/verification/tools/soc-venv/bin/python"

while systemctl --user is-active --quiet "${unit}"; do
  sleep 30
done

jq -e '.status == "COMPILED_NOT_RUN" and .compile.returncode == 0 and .technology.passed == true' \
  "${run}/summary.json" >/dev/null

set +e
"${python}" "${root}/verification/fpga/run_soc_smoke.py" --mode linux \
  --output "${run}" --run-only --run-timeout 7200 \
  --linux-fail-fast --linux-first-progress-timeout 900 \
  --linux-no-progress-timeout 900 --linux-min-cycle-target 20000000 \
  --budget-check-after 900 --cache-tag-probe \
  > "${run}/linux_run_driver.log" 2>&1
run_status=$?
"${python}" "${root}/verification/fpga/check_soc_linux.py" "${run}" \
  --report "${run}/independent_boot_audit.json" \
  > "${run}/linux_audit_driver.log" 2>&1
audit_status=$?
set -e

if ((run_status != 0 || audit_status != 0)); then
  printf 'Final-source Linux RTL run failed: runner=%d audit=%d\n' \
    "$run_status" "$audit_status" >&2
  exit 1
fi
printf 'Final-source Linux RTL boot and independent audit PASS: %s\n' "$run"
