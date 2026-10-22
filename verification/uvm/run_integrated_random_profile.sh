#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
profile=${1:?usage: run_integrated_random_profile.sh loadstore|integer|arithmetic|fp32|fp64|mixed|vtype_churn}
case "${profile}" in
  loadstore|integer|arithmetic|fp32|fp64|mixed|vtype_churn) ;;
  *) printf 'unsupported profile: %s\n' "${profile}" >&2; exit 2 ;;
esac

preflight_unit=ara-dsa-integrated-random-preflight-audit-20260925-01.service
preflight="${root}/verification/out/integrated-random-loadstore-preflight-20260925-01"
while systemctl --user is-active --quiet "${preflight_unit}"; do
  sleep 30
done
jq -e '.status == "PASS" and .case_count == 1 and .passed_cases == 1 and .failed_cases == 0' \
  "${preflight}/independent_audit.json" >/dev/null

source="/home/wangwy/openproject/ara_dsa_masked_indexed_fix/verification/out/final-mask-bundle-${profile}-10seed-20260925-01/summary.json"
output="${root}/verification/out/integrated-random-${profile}-10seed-20260925-01"
simv="${root}/verification/out/integrated-vcs-image-20260925-01/sim/simv"
spike=/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike
python="${root}/verification/tools/soc-venv/bin/python"

test -f "${source}"
test -x "${simv}"
test -x "${spike}"
test ! -e "${output}"
set +e
"${python}" "${root}/verification/verify.py" replay-failed-rvv \
  --summary "${source}" --include-passed --output "${output}" \
  --simv "${simv}" --spike "${spike}" --jobs 1 \
  --timeout 900 --spike-timeout 120 \
  > "${root}/verification/out/integrated-random-${profile}-driver-20260925-01.log" 2>&1
run_status=$?
"${python}" "${root}/verification/verify.py" audit --run "${output}" \
  --require-trace --require-vector --require-full-match \
  --output "${output}/independent_audit.json"
audit_status=$?
set -e
if ((run_status != 0 || audit_status != 0)); then
  printf 'random profile failed: %s runner=%d audit=%d\n' \
    "$profile" "$run_status" "$audit_status" >&2
  exit 1
fi
jq -e '.status == "PASS" and .case_count == 10 and .passed_cases == 10 and .failed_cases == 0' \
  "${output}/independent_audit.json" >/dev/null
