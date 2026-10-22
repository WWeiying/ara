#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "${root}"
python="${root}/verification/tools/soc-venv/bin/python"
test -x "${python}"
out=${1:?usage: run_final_toggle_stage1.sh NEW_OUTPUT_DIR}
out=$(realpath -m -- "${out}")
case "${out}" in "${root}/verification/out/"*) ;; *) exit 2 ;; esac
test ! -e "${out}"

build=verification/out/integrated-verilator-toggle-20260925-02
simv="${build}/build/verilator/Vara_tb_verilator"
manifest="${build}/source_manifest.json"
reporter=install/verilator/bin/verilator_coverage
service=ara-dsa-wred-m8-verilator-toggle-build-20260925-02.service
if [[ ${ARA_WAIT_FOR_TOGGLE_BUILD:-0} == 1 ]]; then
  for ((minute = 0; minute < 720; minute++)); do
    state=$(systemctl --user show -p ActiveState --value "${service}")
    [[ ${state} == active || ${state} == activating ]] || break
    sleep 60
  done
fi
test "$(systemctl --user show -p ActiveState --value "${service}")" = inactive
test "$(systemctl --user show -p Result --value "${service}")" = success
test -x "${simv}"
test "${simv}" -nt "${manifest}"
rg -q -- '--coverage-toggle' "${build}/build/verilator/Vara_tb_verilator__verFiles.dat"
rg -q -- '-GL2SizeBytes=2097152' "${build}/build/verilator/Vara_tb_verilator__verFiles.dat"
"${python}" verification/coverage/build_provenance.py --output "${manifest}" --check

"${python}" - <<'PY'
import json
from pathlib import Path
out = Path('verification/out')
line = json.loads((out / 'integrated-verilator-coverage-20260925-01/source_manifest_wred.json').read_text())
toggle = json.loads((out / 'integrated-verilator-toggle-20260925-02/source_manifest.json').read_text())
def sources(manifest):
    return {item['path']: item['sha256'] for item in manifest['files']
            if any(part in item['path'] for part in ('/hardware/src/', '/hardware/deps/',
                                                     '/hardware/tb/'))}
assert sources(line) == sources(toggle), 'line/expression and toggle source files differ'
PY

directed=verification/out/integrated-wred-m8-state-layout-20260925-01
test "$(jq -r .status "${directed}/independent_audit.json")" = PASS
"${python}" verification/coverage/run_directed_coverage.py \
  --summary "${directed}/summary.json" --audit "${directed}/independent_audit.json" \
  --case-name rvv_vregister_group_illegal --simv "${simv}" \
  --source-manifest "${manifest}" --verilator-coverage "${reporter}" \
  --ram-bytes 2097152 --jobs 1 --term-cycles 180000 --timeout 900 \
  --output "${out}/rvv_control"

handoff=verification/out/integrated-wred-m8-qbs-akv-handoff-20260925-02
test "$(jq -r .status "${handoff}/independent_audit.json")" = PASS
elf="${handoff}/tests/app_qbs_akv_handoff_smoke/input.elf"
test "$(sha256sum "${elf}" | cut -d ' ' -f 1)" = \
  "$(jq -r .binary.sha256 "${handoff}/tests/app_qbs_akv_handoff_smoke/inputs.json")"
"${python}" verification/coverage/run_verilator_coverage.py \
  --simv "${simv}" --elf "${elf}" --output "${out}/qbs_akv_handoff" \
  --verilator-coverage "${reporter}" --term-cycles 100000 --timeout 900

"${python}" verification/coverage/merge_verilator_coverage.py \
  --case "${out}/rvv_control/rvv_vregister_group_illegal/result.json" \
  --case "${out}/qbs_akv_handoff/result.json" --output "${out}/merged" \
  --verilator-coverage "${reporter}" \
  --hierarchy-prefix ara_tb_verilator.dut.i_ara_soc \
  --include-path /hardware/src/ara_dispatcher.sv \
  --include-path /hardware/src/ara_sequencer.sv \
  --include-path /hardware/src/vlsu/vlsu.sv \
  --include-path /hardware/src/vlsu/qbs/ \
  --include-path /hardware/src/vlsu/akv/
"${python}" verification/coverage/audit_merged.py \
  --audit "${out}/merged/audit.json" --minimum-cases 2 \
  --report "${out}/merged/independent_audit.json"
"${python}" verification/coverage/review_uncovered.py \
  --audit "${out}/merged/audit.json" --minimum-cases 2 \
  --output "${out}/merged/review.json"
