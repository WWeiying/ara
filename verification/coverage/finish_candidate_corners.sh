#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
base="${root}/verification/out/verilator-coverage-masked-indexed-2m-20260924-01"
source="${root}/verification/out/masked-indexed-latest-rvv-corners-run-20260924-02"
unit=ara-dsa-masked-indexed-verilator-coverage-build-20260924-01.service
python="${root}/verification/tools/soc-venv/bin/python"

while systemctl --user is-active --quiet "${unit}"; do
  sleep 60
done

simv="${base}/build/verilator/Vara_tb_verilator"
test -x "${simv}"
"${python}" "${root}/verification/coverage/build_provenance.py" \
  --output "${base}/source_manifest.json" --check
"${python}" "${root}/verification/coverage/run_directed_coverage.py" \
  --summary "${source}/summary.json" \
  --audit "${source}/verification_audit_directed.json" \
  --simv "${simv}" --source-manifest "${base}/source_manifest.json" \
  --output "${base}/rvv_corners_35case" --jobs 2 --ram-bytes 2097152 \
  --term-cycles 100000 --timeout 1800 \
  --verilator-coverage "${root}/install/verilator/bin/verilator_coverage"
test "$(jq -r .status "${base}/rvv_corners_35case/merged/independent_audit.json")" = PASS
test "$(jq -r .status "${base}/rvv_corners_35case/merged/signoff/signoff.json")" = PASS
