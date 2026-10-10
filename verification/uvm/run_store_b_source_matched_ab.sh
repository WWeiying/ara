#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
verify_root=$(cd -- "${root}/../ara_dsa_signoff_integration" && pwd)
out=${1:?usage: run_store_b_source_matched_ab.sh NEW_OUTPUT_DIR}
out=$(realpath -m -- "${out}")
test ! -e "${out}"
mkdir -p -- "${out}"

axpy_elf="${root}/verification/out/store-b-vsaxpy-baseline-20260925-01/tests/app_vsaxpy_asm/input.elf"
fault_elf="${root}/verification/out/store-b-delayed-checker-fault-20260925-04/work/input.elf"
test "$(sha256sum "${axpy_elf}" | cut -d ' ' -f 1)" = \
  95d17384bb80addb04586b1884dbd0c8084b1cf26134d80c7c5ff6b0247fea3d
sources=(
  "${verify_root}/verification/uvm/ara_cvxif_if.sv"
  "${verify_root}/verification/uvm/ara_cvxif_uvm_pkg.sv"
  "${verify_root}/verification/uvm/ara_acc_contract_monitor.sv"
  "${root}/verification/uvm/ara_cvxif_dut_bind.sv"
)

for mode in baseline precise; do
  baseline=0
  if [[ ${mode} == baseline ]]; then baseline=1; fi
  image="${out}/${mode}"
  mkdir -p -- "${image}"
  timeout --foreground 10800 make -C "${root}/hardware" compile \
    buildpath="${image}/build" sim_dir="${image}/sim" \
    qbs=1 akv=1 akv_v2=1 sim_l2_mb=2 no_fsdb=1 verify_axi_delay=1 \
    verify_uvm_cvxif=1 verify_source_manifest=1 \
    store_b_ab_baseline="${baseline}" \
    verify_extra_sources="${sources[*]}" > "${image}/compile.log" 2>&1
  test -x "${image}/sim/simv"
  PYTHONPATH="${verify_root}/verification" python3 -m ara_verify.vcs_source_manifest \
    --output "${image}/sim/vcs_source_manifest.json" --check \
    > "${image}/source_check.json"
  ARA_VCS_TIMEOUT_SECONDS=900 "${verify_root}/verification/uvm/run_real_dut_case.sh" \
    "${image}/sim/simv" "${axpy_elf}" app_vsaxpy_asm "${image}/axpy" \
    > "${image}/axpy.log" 2>&1
done

ARA_UVM_TRACE_AXI_WRITE=1 ARA_VCS_TIMEOUT_SECONDS=900 \
  "${verify_root}/verification/uvm/run_real_dut_case.sh" \
  "${out}/precise/sim/simv" "${fault_elf}" \
  rv64uv-ara-vstore_axi_error_bursts "${out}/precise/fault" \
  > "${out}/precise/fault.log" 2>&1

for mode in baseline precise; do
  (cd "${out}/${mode}/axpy" && sha256sum -c --status INPUT_SHA256SUMS &&
    sha256sum -c --status RUN_SHA256SUMS)
  test "$(jq -r .status "${out}/${mode}/axpy/uvm_result.json")" = PASS
done
(cd "${out}/precise/fault" && sha256sum -c --status INPUT_SHA256SUMS &&
  sha256sum -c --status RUN_SHA256SUMS)
test "$(jq -r .status "${out}/precise/fault/uvm_result.json")" = PASS

for mode in baseline precise; do
  report="${out}/${mode}/axpy/work/perf_report_app_vsaxpy_asm.log"
  printf '%s ' "${mode}"
  rg '^\[PERF\] total_cycles' "${report}"
done | tee "${out}/cycles.txt"
