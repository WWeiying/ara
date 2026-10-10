#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-masked-indexed-random-slide-10seed-20260924-01.service
run="${root}/verification/out/masked-indexed-latest-random-slide-10seed-20260924-01"

while systemctl --user is-active --quiet "${unit}"; do
  sleep 60
done

python3 "${root}/verification/verify.py" audit \
  --run "${run}" --require-trace --require-vector \
  --require-full-match --require-coverage \
  --output "${run}/verification_audit_strict.json"
jq -e '.status == "PASS" and .case_count == 10 and .passed_cases == 10 and .failed_cases == 0' \
  "${run}/verification_audit_strict.json" >/dev/null
