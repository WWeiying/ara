#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-integrated-rvv-corners-20260925-02.service
run="${root}/verification/out/integrated-rvv-corners-20260925-02"

while systemctl --user is-active --quiet "${unit}"; do
  sleep 30
done

python="${root}/verification/tools/soc-venv/bin/python"
"${python}" "${root}/verification/verify.py" audit \
  --run "${run}" --require-trace \
  --output "${run}/verification_audit_directed.json"
jq -e '.status == "PASS" and .case_count == 35 and .passed_cases == 35 and .failed_cases == 0' \
  "${run}/verification_audit_directed.json" >/dev/null
