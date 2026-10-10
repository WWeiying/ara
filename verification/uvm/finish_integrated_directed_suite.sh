#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
suite=${1:?usage: finish_integrated_directed_suite.sh reductions|failure-regression|masked-indexed}
case "${suite}" in
  reductions)
    unit=ara-dsa-integrated-rvv-reductions-20260925-01.service
    run="${root}/verification/out/integrated-rvv-reductions-20260925-01"
    expected=18
    ;;
  failure-regression)
    unit=ara-dsa-integrated-rvv-failure-regression-20260925-01.service
    run="${root}/verification/out/integrated-rvv-failure-regression-20260925-01"
    expected=14
    ;;
  masked-indexed)
    unit=ara-dsa-integrated-rvv-masked-indexed-20260925-01.service
    run="${root}/verification/out/integrated-rvv-masked-indexed-20260925-01"
    expected=3
    ;;
  *)
    printf 'unsupported suite: %s\n' "${suite}" >&2
    exit 2
    ;;
esac

while systemctl --user is-active --quiet "${unit}"; do
  sleep 30
done

python="${root}/verification/tools/soc-venv/bin/python"
"${python}" "${root}/verification/verify.py" audit \
  --run "${run}" --require-trace \
  --output "${run}/verification_audit_directed.json"
jq -e --argjson expected "${expected}" \
  '.status == "PASS" and .case_count == $expected and .passed_cases == $expected and .failed_cases == 0' \
  "${run}/verification_audit_directed.json" >/dev/null
