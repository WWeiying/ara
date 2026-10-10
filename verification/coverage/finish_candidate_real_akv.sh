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

source_case="${root}/verification/out/masked-indexed-latest-akv-real-20260924-01"
(
  cd "${source_case}"
  sha256sum -c --status INPUT_SHA256SUMS
  sha256sum -c --status RUN_SHA256SUMS
)
test "$(jq -r .status "${source_case}/uvm_result.json")" = PASS

"${python}" "${root}/verification/coverage/run_verilator_coverage.py" \
  --simv "${simv}" --elf "${source_case}/work/input.elf" \
  --output "${base}/akv_real" \
  --verilator-coverage "${root}/install/verilator/bin/verilator_coverage" \
  --term-cycles 100000 --timeout 7200
test "$(jq -r .status "${base}/akv_real/result.json")" = PASS
