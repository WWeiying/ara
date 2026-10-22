#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
build_unit=ara-dsa-integrated-verilator-coverage-build-20260925-01.service
audit_unit=ara-dsa-integrated-rvv-corners-audit-20260925-01.service
image="${root}/verification/out/integrated-verilator-coverage-20260925-01"
source="${root}/verification/out/integrated-rvv-corners-20260925-02"
output="${root}/verification/out/integrated-coverage-corners-20260925-01"
python="${root}/verification/tools/soc-venv/bin/python"

for unit in "${build_unit}" "${audit_unit}"; do
  while systemctl --user is-active --quiet "${unit}"; do
    sleep 30
  done
done

test -x "${image}/build/verilator/Vara_tb_verilator"
jq -e '.status == "PASS" and .case_count == 35 and .passed_cases == 35 and .failed_cases == 0' \
  "${source}/verification_audit_directed.json" >/dev/null
"${python}" "${root}/verification/coverage/build_provenance.py" \
  --output "${image}/source_manifest.json" --check
"${python}" "${root}/verification/coverage/run_directed_coverage.py" \
  --summary "${source}/summary.json" \
  --audit "${source}/verification_audit_directed.json" \
  --simv "${image}/build/verilator/Vara_tb_verilator" \
  --source-manifest "${image}/source_manifest.json" \
  --ram-bytes 2097152 --jobs 2 --term-cycles 100000 --timeout 1800 \
  --output "${output}"
jq -e '.status == "PASS"' "${output}/merged/independent_audit.json" >/dev/null
jq -e '.status == "PASS"' "${output}/merged/signoff/signoff.json" >/dev/null
