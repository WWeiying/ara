#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
simv=$(realpath -- "${1:?usage: run_main_engine_reset_matrix.sh SIMV NEW_OUTPUT_DIR [JOBS]}")
out=$(realpath -m -- "${2:?usage: run_main_engine_reset_matrix.sh SIMV NEW_OUTPUT_DIR [JOBS]}")
limit=${3:-6}
[[ ${limit} =~ ^[1-9][0-9]*$ ]] || { printf 'JOBS must be positive\n' >&2; exit 2; }
[[ ! -e ${out} ]] || { printf 'output already exists: %s\n' "${out}" >&2; exit 2; }
[[ -x ${simv} ]] || { printf 'missing simv: %s\n' "${simv}" >&2; exit 2; }
mkdir -p -- "${out}"

cases=(
  'qbs_request|qbs_reset_read_cov'
  'qbs_validate|qbs_reset_read_cov'
  'qbs_compute_start|qbs_reset_read_cov'
  'qbs_commit|qbs_reset_read_cov'
  'qbs_fault_drain|qbs_weight_fault_cov'
  'akv_request|akv_d96_gap29'
  'akv_validate|akv_d96_gap29'
  'akv_column_gather|akv_column_coverage_smoke'
  'akv_replay_read|akv_context_smoke'
  'akv_replay_write|akv_context_smoke'
  'read_qbs_descriptor|qbs_reset_read_cov'
  'read_akv_descriptor|akv_d96_gap29'
  'read_akv_payload|akv_context_smoke'
)

for entry in "${cases[@]}"; do
  IFS='|' read -r target app <<< "${entry}"
  elf=${root}/apps/bin/${app}
  [[ -f ${elf} ]] || { printf 'missing ELF: %s\n' "${elf}" >&2; exit 2; }
  while (( $(jobs -rp | wc -l) >= limit )); do
    wait -n || true
  done
  (
    reset_kind=state
    reset_target=${target}
    reset_read_index=1
    if [[ ${target} == read_* ]]; then
      reset_kind=read
      reset_target=-
      [[ ${target} != read_akv_payload ]] || reset_read_index=2
    fi
    if env ARA_VCS_CODE_COVERAGE=1 ARA_VCS_TIMEOUT_SECONDS=900 \
        ARA_UVM_RESET_STATE_TARGET="${reset_target}" \
        ARA_UVM_RESET_READ_INDEX="${reset_read_index}" \
        bash "${root}/verification/uvm/run_real_dut_case.sh" \
          "${simv}" "${elf}" "${app}" "${out}/${target}" "${reset_kind}" \
          > "${out}/${target}.launch.log" 2>&1; then
      printf 'PASS\n' > "${out}/${target}.status"
    else
      printf 'FAIL\n' > "${out}/${target}.status"
    fi
  ) &
done
wait || true

failures=0
for entry in "${cases[@]}"; do
  IFS='|' read -r target app <<< "${entry}"
  result=$(<"${out}/${target}.status")
  printf '%s %s\n' "${target}" "${result}"
  [[ ${result} == PASS ]] || (( failures += 1 ))
done
(( failures == 0 ))
