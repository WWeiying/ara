#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-masked-indexed-rvv-corners-retry-20260924-01.service
run="${root}/verification/out/masked-indexed-latest-rvv-corners-run-20260924-02"

while systemctl --user is-active --quiet "${unit}"; do
  sleep 60
done

python3 "${root}/verification/verify.py" audit \
  --run "${run}" --require-trace \
  --output "${run}/verification_audit_directed.json"
jq -e '.status == "PASS" and .case_count == 35 and .passed_cases == 35 and .failed_cases == 0' \
  "${run}/verification_audit_directed.json" >/dev/null
