#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
for unit in \
  ara-dsa-integrated-coverage-first-matrix-20260925-02.service \
  ara-dsa-integrated-coverage-directed-traced-20260925-02.service \
  ara-dsa-integrated-coverage-corners-20260925-01.service \
  ara-dsa-integrated-coverage-masked-indexed-20260925-01.service; do
  while systemctl --user is-active --quiet "${unit}"; do
    sleep 30
  done
done

for run in \
  integrated-coverage-first-matrix-20260925-01 \
  integrated-coverage-directed-20260925-02 \
  integrated-coverage-corners-20260925-01 \
  integrated-coverage-masked-indexed-20260925-01; do
  jq -e '.status == "PASS" and .issues == []' \
    "${root}/verification/out/${run}/merged/independent_audit.json" >/dev/null
done

"${root}/verification/tools/soc-venv/bin/python" \
  "${root}/verification/coverage/merge_integrated_final.py" \
  --output "${root}/verification/out/integrated-coverage-global-20260925-01"
