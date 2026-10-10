#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python="${root}/verification/tools/soc-venv/bin/python"
groups=(73-76 77-80)

for group in "${groups[@]}"; do
  unit="ara-dsa-final-slide-seeds${group}-20260924-01.service"
  while systemctl --user is-active --quiet "${unit}"; do
    sleep 60
  done
done

failed=0
for group in "${groups[@]}"; do
  output="${root}/verification/out/final-slide-seeds${group}-20260924-01"
  if ! test -f "${output}/run.json"; then
    printf 'MISSING %s\n' "${group}"
    failed=1
    continue
  fi
  if ! "${python}" "${root}/verification/verify.py" audit \
      --run "${output}" --require-trace --require-vector \
      --require-full-match --output "${output}/final_audit.json"; then
    failed=1
  fi
done

exit "${failed}"
