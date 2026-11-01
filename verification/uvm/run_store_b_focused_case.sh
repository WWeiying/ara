#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
verify_root=$root
simv=$(realpath -- "${1:?usage: run_store_b_focused_case.sh SIMV ELF NEW_OUTPUT_DIR}")
elf=$(realpath -- "${2:?missing ELF}")
out=$(realpath -m -- "${3:?missing new output directory}")
test -x "$simv"
test ! -e "$out"
mkdir -p "$out/work"
cp -p "$elf" "$out/work/input.elf"
cd "$out/work"
probe_args=()
if [[ ${ARA_FOCUSED_FP_CSR_TRACE:-0} == 1 ]]; then
  probe_args=(+FP_CSR_TRACE +FP_CSR_TRACE_START=0 +FP_CSR_TRACE_END=5000)
fi
timeout --foreground "${ARA_FOCUSED_TIMEOUT_SECONDS:-300}" "$simv" -no_save -l run.vcs.log \
  "+PRELOAD=$out/work/input.elf" +TESTCASE=store_b_focused +NO_FSDB \
  +ARA_CONTRACT_TRACE_LIMIT=100000 +ARA_UVM_TRACE_LIMIT=100000 +VSET_PREVIEW_TRACE \
  "+VECTOR_TRACE=$out/work/vector_trace.csv" \
  "${probe_args[@]}" \
  > console.log 2>&1
rg 'PASSED|smoke: PASS' run.vcs.log
if rg '^FAIL([ :]|$)|FAILED|Error:|Fatal:|Error-|Fatal-' run.vcs.log; then exit 1; fi
axi_read_args=(--require-axi)
case ${ARA_FOCUSED_AXI_READ_REQUIRED:-1} in
  0) axi_read_args=() ;;
  1) ;;
  *) printf 'Invalid AXI read expectation\n' >&2; exit 2 ;;
esac
PYTHONPATH="$verify_root/verification" python3 -m ara_verify.uvm_dut \
  --require-events --require-backend "${axi_read_args[@]}" --require-axi-write \
  --vector-trace vector_trace.csv --log run.vcs.log --simv "$simv" \
  --elf input.elf --output "$out/uvm_result.json"
test "$(jq -r .status "$out/uvm_result.json")" = PASS
sha256sum input.elf run.vcs.log vector_trace.csv > "$out/SHA256SUMS"
