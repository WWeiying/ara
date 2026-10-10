#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
verify_root=$(cd -- "${root}/../ara_dsa_signoff_integration" && pwd)
out=${1:?usage: run_store_b_probe_ab.sh NEW_OUTPUT_DIR}
out=$(realpath -m -- "${out}")
test ! -e "${out}"
mkdir -p -- "${out}"

elf="${root}/verification/out/store-b-vsaxpy-baseline-20260925-01/tests/app_vsaxpy_asm/input.elf"
test "$(sha256sum "${elf}" | cut -d ' ' -f 1)" = \
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
  work="${image}/axpy/work"
  mkdir -p -- "${work}"
  timeout --foreground 10800 make -C "${root}/hardware" compile \
    buildpath="${image}/build" sim_dir="${image}/sim" \
    qbs=1 akv=1 akv_v2=1 sim_l2_mb=2 no_fsdb=1 verify_axi_delay=1 \
    verify_uvm_cvxif=1 verify_source_manifest=1 \
    store_b_ab_baseline="${baseline}" \
    verify_extra_sources="${sources[*]}" > "${image}/compile.log" 2>&1
  simv="${image}/sim/simv"
  test -x "${simv}"
  PYTHONPATH="${verify_root}/verification" python3 -m ara_verify.vcs_source_manifest \
    --output "${image}/sim/vcs_source_manifest.json" --check \
    > "${image}/source_check.json"
  cp -p -- "${elf}" "${work}/input.elf"
  (
    cd -- "${work}"
    timeout --foreground 900 "${simv}" -no_save -l "${work}/run.vcs.log" \
      "+PRELOAD=${work}/input.elf" +TESTCASE=app_vsaxpy_asm +NO_FSDB \
      +ARA_CONTRACT_TRACE_LIMIT=100000 +ARA_UVM_TRACE_LIMIT=100000 \
      "+VECTOR_TRACE=${work}/vector_trace.csv" \
      "+STORE_B_PROBE_FILE=${work}/store_b_probe.csv" \
      +STORE_B_PROBE_START=400 +STORE_B_PROBE_END=1200 \
      > "${work}/console.log" 2>&1
  )
  PYTHONPATH="${verify_root}/verification" python3 -m ara_verify.uvm_dut \
    --require-events --require-backend --require-axi --require-axi-write \
    --vector-trace "${work}/vector_trace.csv" \
    --log "${work}/run.vcs.log" --simv "${simv}" \
    --elf "${work}/input.elf" --output "${image}/axpy/uvm_result.json"
  test "$(jq -r .status "${image}/axpy/uvm_result.json")" = PASS
  (
    cd -- "${image}"
    sha256sum -- sim/simv sim/vcs_source_manifest.json axpy/work/input.elf \
      axpy/work/run.vcs.log axpy/work/vector_trace.csv \
      axpy/work/store_b_probe.csv axpy/uvm_result.json > SHA256SUMS
    sha256sum -c --status SHA256SUMS
  )
done

python3 "${root}/verification/uvm/analyze_store_b_ab.py" \
  --baseline-log "${out}/baseline/axpy/work/run.vcs.log" \
  --precise-log "${out}/precise/axpy/work/run.vcs.log" \
  --output "${out}/cvxif_store_timing.json"
