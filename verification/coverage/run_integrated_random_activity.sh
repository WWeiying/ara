#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out="${root}/verification/out"
objdump=/home/wangwy/software/toolchains/riscv-gcc-rv64gcv/bin/riscv64-unknown-elf-objdump
output="${out}/integrated-random-retired-70case-20260925-01.json"
test -x "${objdump}"
test ! -e "${output}"

args=()
for profile in loadstore integer arithmetic fp32 fp64 mixed vtype_churn; do
  run="${out}/integrated-random-${profile}-10seed-20260925-01"
  jq -e '.status == "PASS" and .case_count == 10 and .passed_cases == 10 and
         .failed_cases == 0 and .policy.require_trace == true and
         .policy.require_vector == true and .policy.require_full_match == true' \
    "${run}/independent_audit.json" >/dev/null
  for result in "${run}"/tests/*/result.json; do
    test -f "${result}"
    args+=(--case "${result%/result.json}")
  done
done
test "${#args[@]}" -eq 140

PYTHONPATH="${root}/verification" \
  "${root}/verification/tools/soc-venv/bin/python" \
  -m ara_verify.coverage_matrix \
  "${args[@]}" --objdump "${objdump}" --jobs 7 --require-same-image \
  --output "${output}"
