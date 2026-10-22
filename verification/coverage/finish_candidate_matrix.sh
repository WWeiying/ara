#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
base="${root}/verification/out/verilator-coverage-masked-indexed-2m-20260924-01"
unit=ara-dsa-masked-indexed-verilator-coverage-build-20260924-01.service
python="${root}/verification/tools/soc-venv/bin/python"

while systemctl --user is-active --quiet "${unit}"; do
  sleep 60
done

simv="${base}/build/verilator/Vara_tb_verilator"
test -x "${simv}"
"${python}" "${root}/verification/coverage/build_provenance.py" \
  --output "${base}/source_manifest.json" --check
"${python}" "${root}/verification/coverage/run_passed_matrix.py" \
  --matrix "${root}/verification/coverage/candidate_final_matrix_20260924.json" \
  --simv "${simv}" --source-manifest "${base}/source_manifest.json" \
  --output "${base}/matrix_11case" --jobs 2 --ram-bytes 2097152 \
  --verilator-coverage "${root}/install/verilator/bin/verilator_coverage"
test "$(jq -r .status "${base}/matrix_11case/merged/independent_audit.json")" = PASS
test "$(jq -r .status "${base}/matrix_11case/merged/signoff/signoff.json")" = PASS
