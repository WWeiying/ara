#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
simv=$(realpath -- "${1:?usage: run_dispatcher_reset_matrix.sh SIMV NEW_OUTPUT_DIR [JOBS]}")
out=$(realpath -m -- "${2:?usage: run_dispatcher_reset_matrix.sh SIMV NEW_OUTPUT_DIR [JOBS]}")
jobs=${3:-8}
[[ ${jobs} =~ ^[1-9][0-9]*$ ]] || { printf 'JOBS must be positive\n' >&2; exit 2; }
[[ ! -e ${out} ]] || { printf 'output already exists: %s\n' "${out}" >&2; exit 2; }
elf=${root}/apps/bin/rv64uv-ara-vwiden_overlap_edges
[[ -x ${simv} && -f ${elf} ]] || { printf 'missing simv or ELF\n' >&2; exit 2; }
mkdir -p -- "${out}"

targets=(
  disp_overlap_capture
  disp_overlap_fixup
  disp_overlap_issue_original
  disp_overlap_prefix_fixup
  disp_overlap_respond
  disp_overlap_wait_capture
  disp_overlap_wait_fixup
  disp_overlap_wait_original
  disp_overlap_wait_prefix_fixup
  disp_reshuffle
  disp_source_snapshot_capture
  disp_source_snapshot_wait
  disp_wait_idle
)

for target in "${targets[@]}"; do
  while (( $(jobs -rp | wc -l) >= jobs )); do
    wait -n || true
  done
  (
    if env ARA_VCS_CODE_COVERAGE=1 ARA_VCS_TIMEOUT_SECONDS=900 \
        ARA_UVM_RESET_STATE_TARGET="${target}" \
        bash "${root}/verification/uvm/run_real_dut_case.sh" \
          "${simv}" "${elf}" rv64uv-ara-vwiden_overlap_edges \
          "${out}/${target}" state > "${out}/${target}.launch.log" 2>&1; then
      printf 'PASS\n' > "${out}/${target}.status"
    else
      printf 'FAIL\n' > "${out}/${target}.status"
    fi
  ) &
done
wait || true

failures=0
for target in "${targets[@]}"; do
  result=$(<"${out}/${target}.status")
  printf '%s %s\n' "${target}" "${result}"
  [[ ${result} == PASS ]] || (( failures += 1 ))
done
(( failures == 0 ))
