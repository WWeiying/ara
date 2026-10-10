#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
verify_root=$(cd -- "${root}/../ara_dsa_signoff_integration" && pwd)
out=$(realpath -m -- "${1:?usage: run_store_b_structural_probe.sh OUTPUT_DIR [--resume-build]}")
if [[ ${2:-} == --resume-build ]]; then
  # Only an unrun compile may be resumed; never overwrite a measured image.
  test -d "${out}/sim/incremental_db"
  test ! -e "${out}/work/input.elf"
  test ! -e "${out}/uvm_result.json"
  backup=$(mktemp -d "${out}/compile-attempt.XXXXXXXX")
  cp -p "${out}/compile.log" "${backup}/"
  mv "${out}/sim/vcs_source_manifest.json" "${backup}/"
else
  test "$#" = 1
  test ! -e "${out}"
fi
mkdir -p "${out}/work"
elf="${root}/verification/out/store-b-vsaxpy-baseline-20260925-01/tests/app_vsaxpy_asm/input.elf"
sources=("${verify_root}/verification/uvm/ara_cvxif_if.sv"
  "${verify_root}/verification/uvm/ara_cvxif_uvm_pkg.sv"
  "${verify_root}/verification/uvm/ara_acc_contract_monitor.sv"
  "${root}/verification/uvm/ara_cvxif_dut_bind.sv")
timeout --foreground 1800 make -C "${root}/hardware" compile \
  buildpath="${out}/build" sim_dir="${out}/sim" qbs=1 akv=1 akv_v2=1 \
  sim_l2_mb=2 no_fsdb=1 verify_axi_delay=1 verify_uvm_cvxif=1 \
  verify_source_manifest=1 "verify_extra_sources=${sources[*]}" \
  > "${out}/compile.log" 2>&1
PYTHONPATH="${verify_root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${out}/sim/vcs_source_manifest.json" --check > "${out}/source_check.json"
cp -p "${elf}" "${out}/work/input.elf"
cd "${out}/work"
timeout --foreground 300 "${out}/sim/simv" -no_save -l run.vcs.log \
  "+PRELOAD=${out}/work/input.elf" +TESTCASE=app_vsaxpy_asm +NO_FSDB \
  +ARA_CONTRACT_TRACE_LIMIT=100000 +ARA_UVM_TRACE_LIMIT=100000 \
  "+VECTOR_TRACE=${out}/work/vector_trace.csv" \
  "+STORE_B_PROBE_FILE=${out}/work/store_b_probe.csv" \
  +STORE_B_PROBE_START=400 +STORE_B_PROBE_END=1200 \
  +STORE_LOAD_PREPARE_TRACE +VSET_PREVIEW_TRACE +ARA_UVM_TRACE_AXI_WRITE > console.log 2>&1
PYTHONPATH="${verify_root}/verification" python3 -m ara_verify.uvm_dut \
  --require-events --require-backend --require-axi --require-axi-write \
  --vector-trace vector_trace.csv --log run.vcs.log --simv "${out}/sim/simv" \
  --elf input.elf --output "${out}/uvm_result.json"
test "$(jq -r .status "${out}/uvm_result.json")" = PASS
