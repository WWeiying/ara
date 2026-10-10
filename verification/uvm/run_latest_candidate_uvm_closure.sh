#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=${1:-"${root}/verification/out/masked-indexed-latest-uvm-closure-20260924-01"}
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
  qbs=1 akv_v2=1 sim_l2_mb=2 no_fsdb=1 verify_axi_delay=1 \
  verify_uvm_cvxif=1 verify_source_manifest=1 \
  verify_extra_sources="${sources[*]}" > "${out}/compile.log" 2>&1

simv="${out}/sim/simv"
"${root}/verification/uvm/run_real_dut_case.sh" \
  "${simv}" "${root}/apps/bin/llama_qwen25_small_qbs_akv" \
  llama_qwen25_small_qbs_akv "${out}/qwen" > "${out}/qwen.log" 2>&1
"${root}/verification/uvm/run_real_dut_case.sh" \
  "${simv}" \
  "${root}/verification/out/masked-indexed-fix-delay2m-resetread-20260924-01/work/input.elf" \
  rv64uv-ara-vfredmax_boundary "${out}/reset_read" read \
  > "${out}/reset_read.log" 2>&1
"${root}/verification/uvm/run_real_dut_case.sh" \
  "${simv}" \
  "${root}/verification/out/masked-indexed-fix-delay2m-resetwrite-20260924-01/work/input.elf" \
  rv64uv-ara-linux_vector_context "${out}/reset_write" write \
  > "${out}/reset_write.log" 2>&1

python3 "${root}/verification/run_signoff.py" --stage uvm \
  --uvm-audit "${out}/qwen/uvm_result.json" \
  --uvm-audit "${out}/reset_read/uvm_result.json" \
  --uvm-audit "${out}/reset_write/uvm_result.json" \
  --output "${out}/signoff" > "${out}/signoff.log" 2>&1
test "$(jq -r .status "${out}/signoff/signoff.json")" = PASS
printf 'PASS: latest candidate three-case UVM protocol gate\n' > "${out}/result.txt"
