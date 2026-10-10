#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
simv=$(realpath -- "${1:?usage: run_qbs_compute_reset_matrix.sh SIMV NEW_OUTPUT_DIR [JOBS]}")
out=$(realpath -m -- "${2:?usage: run_qbs_compute_reset_matrix.sh SIMV NEW_OUTPUT_DIR [JOBS]}")
jobs=${3:-6}
[[ ${jobs} =~ ^[1-9][0-9]*$ ]] || { printf 'JOBS must be positive\n' >&2; exit 2; }
[[ ! -e ${out} ]] || { printf 'output already exists: %s\n' "${out}" >&2; exit 2; }
[[ -x ${simv} ]] || { printf 'missing simv: %s\n' "${simv}" >&2; exit 2; }
mkdir -p -- "${out}"

cases=(
  'normal_one|-|qbs_reset_read_cov'
  'normal_two_block|-|qbs_two_block_phase_cov'
  'normal_multi_row|-|qbs_control_smoke'
  'normal_q6k_wait|-|llama_qwen25_q6k_wait_cov_qbs'
  'normal_m8|-|qbs_wide_phase_cov'
  'normal_weight_fault|-|qbs_weight_fault_cov'
  'reset_init|qbs_compute_init|qbs_reset_read_cov'
  'reset_load_tile|qbs_compute_load_tile|qbs_reset_read_cov'
  'reset_compute_tile|qbs_compute_tile|qbs_reset_read_cov'
  'reset_wait_weight|qbs_compute_wait_weight|llama_qwen25_q6k_wait_cov_qbs'
  'reset_start_weight|qbs_compute_start_weight|qbs_control_smoke'
  'reset_start_context_wave|qbs_compute_start_context_wave|qbs_wide_phase_cov'
  'reset_clear_block|qbs_compute_clear_block|qbs_two_block_phase_cov'
  'reset_final_drain|qbs_compute_final_drain|qbs_reset_read_cov'
  'reset_result|qbs_compute_result|qbs_reset_read_cov'
  'reset_fault_drain|qbs_compute_fault_drain|qbs_weight_fault_cov'
  'reset_fault_clear|qbs_compute_fault_clear|qbs_weight_fault_cov'
)

for entry in "${cases[@]}"; do
  IFS='|' read -r name target app <<< "${entry}"
  elf=${root}/apps/bin/${app}
  [[ -f ${elf} ]] || { printf 'missing ELF: %s\n' "${elf}" >&2; exit 2; }
  while (( $(jobs -rp | wc -l) >= jobs )); do
    wait -n || true
  done
  (
    args=("${simv}" "${elf}" "${app}" "${out}/${name}")
    if [[ ${target} != - ]]; then
      args+=(state)
    fi
    if env ARA_VCS_CODE_COVERAGE=1 ARA_VCS_TIMEOUT_SECONDS=900 \
        ARA_UVM_RESET_STATE_TARGET="${target}" \
        bash "${root}/verification/uvm/run_real_dut_case.sh" \
          "${args[@]}" > "${out}/${name}.launch.log" 2>&1; then
      printf 'PASS\n' > "${out}/${name}.status"
    else
      printf 'FAIL\n' > "${out}/${name}.status"
    fi
  ) &
done
wait || true

failures=0
for entry in "${cases[@]}"; do
  IFS='|' read -r name target app <<< "${entry}"
  result=$(<"${out}/${name}.status")
  printf '%s %s\n' "${name}" "${result}"
  [[ ${result} == PASS ]] || (( failures += 1 ))
done
(( failures == 0 ))
