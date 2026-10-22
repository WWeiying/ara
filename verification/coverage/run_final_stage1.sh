#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "${root}"
python="${root}/verification/tools/soc-venv/bin/python"
test -x "${python}"
out=${1:?usage: run_final_stage1.sh NEW_OUTPUT_DIR}
out=$(realpath -m -- "${out}")
case "${out}" in "${root}/verification/out/"*) ;; *) exit 2 ;; esac
test ! -e "${out}"

build=verification/out/integrated-verilator-coverage-20260925-01
simv="${build}/build/verilator/Vara_tb_verilator"
manifest="${ARA_COVERAGE_SOURCE_MANIFEST:-${build}/source_manifest_tohost.json}"
reporter=install/verilator/bin/verilator_coverage
service=ara-dsa-wred-m8-verilator-coverage-build-20260925-01.service
if [[ ${ARA_WAIT_FOR_COVERAGE_BUILD:-0} == 1 ]]; then
  for ((minute = 0; minute < 720; minute++)); do
    state=$(systemctl --user show -p ActiveState --value "${service}")
    [[ ${state} == active || ${state} == activating ]] || break
    sleep 60
  done
fi
test "$(systemctl --user show -p ActiveState --value "${service}")" = inactive
test "$(systemctl --user show -p Result --value "${service}")" = success
test -x "${simv}"
verfiles="${build}/build/verilator/Vara_tb_verilator__verFiles.dat"
test -f "${verfiles}"
rg -q -- '--coverage-line --coverage-expr' "${verfiles}"
rg -q -- '-GL2SizeBytes=2097152' "${verfiles}"
"${python}" verification/coverage/build_provenance.py --output "${manifest}" --check
mkdir -p -- "${out}"
reuse_args=()
if [[ -n ${ARA_COVERAGE_REUSE_AUDIT:-} ]]; then
  reuse_args=(--reuse-audit "${ARA_COVERAGE_REUSE_AUDIT}")
fi

sources=(
  integrated-wred-m8-memory101-replay-20260925-01
  integrated-wred-m8-arithmetic10-replay-20260925-02
  integrated-wred-m8-loadstore10-replay-20260925-01
  integrated-wred-m8-fp32-10-replay-20260925-01
  integrated-wred-m8-fp64-10-replay-20260925-01
  integrated-wred-m8-vtype10-replay-20260925-01
)
results=()
for source in "${sources[@]}"; do
  run="verification/out/${source}"
  test "$(jq -r .status "${run}/independent_audit.json")" = PASS
  case_name=$(jq -r '.[0].artifact_dir | split("/")[-1]' "${run}/summary.json")
  target="${out}/${source}"
  "${python}" verification/coverage/run_directed_coverage.py \
    --random-source --summary "${run}/summary.json" \
    --audit "${run}/independent_audit.json" --case-name "${case_name}" \
    --simv "${simv}" --source-manifest "${manifest}" \
    "${reuse_args[@]}" \
    --verilator-coverage "${reporter}" --ram-bytes 2097152 \
    --jobs 1 --term-cycles 250000 --timeout 3600 --output "${target}"
  results+=("$(jq -r '.cases[0].result' "${target}/case_replay.json")")
done

directed=verification/out/integrated-wred-m8-state-layout-20260925-01
test "$(jq -r .status "${directed}/independent_audit.json")" = PASS
"${python}" verification/coverage/run_directed_coverage.py \
  --summary "${directed}/summary.json" \
  --audit "${directed}/independent_audit.json" \
  --simv "${simv}" --source-manifest "${manifest}" \
  "${reuse_args[@]}" \
  --verilator-coverage "${reporter}" --ram-bytes 2097152 \
  --jobs 2 --term-cycles 180000 --timeout 3600 --output "${out}/state_layout"
while IFS= read -r result; do results+=("${result}"); done < <(
  jq -r '.cases[].result' "${out}/state_layout/case_replay.json")

handoff=verification/out/integrated-wred-m8-qbs-akv-handoff-20260925-02
test "$(jq -r .status "${handoff}/independent_audit.json")" = PASS
elf="${handoff}/tests/app_qbs_akv_handoff_smoke/input.elf"
test "$(sha256sum "${elf}" | cut -d ' ' -f 1)" = \
  "$(jq -r .binary.sha256 "${handoff}/tests/app_qbs_akv_handoff_smoke/inputs.json")"
"${python}" verification/coverage/run_verilator_coverage.py \
  --simv "${simv}" --elf "${elf}" --output "${out}/qbs_akv_handoff" \
  --verilator-coverage "${reporter}" --term-cycles 100000 --timeout 3600
results+=("${out}/qbs_akv_handoff/result.json")

merge=("${python}" verification/coverage/merge_verilator_coverage.py)
for result in "${results[@]}"; do merge+=(--case "${result}"); done
"${merge[@]}" --output "${out}/merged" --verilator-coverage "${reporter}" \
  --hierarchy-prefix ara_tb_verilator.dut.i_ara_soc \
  --include-path /hardware/src/ --include-path /hardware/deps/cva6/
"${python}" verification/coverage/audit_merged.py \
  --audit "${out}/merged/audit.json" --minimum-cases 12 \
  --report "${out}/merged/independent_audit.json"
"${python}" verification/coverage/review_uncovered.py \
  --audit "${out}/merged/audit.json" --minimum-cases 12 \
  --output "${out}/merged/review.json"
