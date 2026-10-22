#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-integrated-random-preflight-20260925-01.service
run="${root}/verification/out/integrated-random-loadstore-preflight-20260925-01"
while systemctl --user is-active --quiet "${unit}"; do
  sleep 30
done
python="${root}/verification/tools/soc-venv/bin/python"
"${python}" "${root}/verification/verify.py" audit --run "${run}" \
  --require-trace --require-vector --require-full-match \
  --output "${run}/independent_audit.json"
jq -e '.status == "PASS" and .case_count == 1 and .passed_cases == 1 and .failed_cases == 0' \
  "${run}/independent_audit.json" >/dev/null
