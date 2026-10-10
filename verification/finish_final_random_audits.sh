#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python="${root}/verification/tools/soc-venv/bin/python"
profiles=(arithmetic load_store integer_stress fp32 fp64 vtype_churn mixed)

for profile in "${profiles[@]}"; do
  unit="ara-dsa-final-rvv-${profile}-seeds1-10-20260924-01.service"
  while systemctl --user is-active --quiet "${unit}"; do
    sleep 60
  done
done

failed=0
for profile in "${profiles[@]}"; do
  output="${root}/verification/out/final-rvv-${profile}-seeds1-10-20260924-01"
  if ! test -f "${output}/run.json"; then
    printf 'MISSING %s\n' "${profile}"
    failed=1
    continue
  fi
  if ! "${python}" "${root}/verification/verify.py" audit \
      --run "${output}" --require-trace --require-vector \
      --require-coverage --require-full-match \
      --output "${output}/final_audit.json"; then
    failed=1
  fi
done

exit "${failed}"
