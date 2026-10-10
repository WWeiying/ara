#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=${1:-"${root}/verification/out/masked-indexed-latest-qwen-gate-20260924-01"}
test ! -e "${out}"
mkdir -p "${out}"

sources=(
  "${root}/verification/uvm/ara_cvxif_if.sv"
  "${root}/verification/uvm/ara_cvxif_uvm_pkg.sv"
  "${root}/verification/uvm/ara_acc_contract_monitor.sv"
  "${root}/verification/uvm/ara_cvxif_dut_bind.sv"
)
make -C "${root}/hardware" compile \
  buildpath="${out}/build" sim_dir="${out}/sim" \
  qbs=1 akv_v2=1 sim_l2_mb=2 no_fsdb=1 \
  verify_uvm_cvxif=1 verify_source_manifest=1 \
  verify_extra_sources="${sources[*]}" > "${out}/compile.log" 2>&1

"${root}/verification/uvm/run_real_dut_case.sh" \
  "${out}/sim/simv" "${root}/apps/bin/llama_qwen25_small_qbs_akv" \
  llama_qwen25_small_qbs_akv "${out}/real_qwen" \
  > "${out}/run.log" 2>&1

PYTHONPATH="${root}/verification" python3 -m ara_verify.uvm_dut \
  --require-events --require-backend --require-axi --require-axi-write \
  --vector-trace "${out}/real_qwen/work/vector_trace.csv" \
  --log "${out}/real_qwen/work/run.vcs.log" \
  --simv "${out}/sim/simv" \
  --elf "${out}/real_qwen/work/input.elf" \
  --output "${out}/independent_reaudit.json" \
  >> "${out}/run.log" 2>&1

test "$(jq -r .status "${out}/real_qwen/uvm_result.json")" = PASS
test "$(jq -r .status "${out}/independent_reaudit.json")" = PASS
(
  cd -- "${out}/real_qwen"
  sha256sum --check INPUT_SHA256SUMS
) > "${out}/hash_check.log"
printf 'PASS: current candidate QBS+AKV real-model program and UVM re-audit\n' \
  > "${out}/result.txt"
