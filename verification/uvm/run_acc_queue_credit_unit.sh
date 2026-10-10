#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_acc_queue_credit_unit.sh NEW_OUTPUT_DIR}")
fifo="${root}/hardware/deps/cva6/core/cva6_fifo_v3.sv"
dispatcher="${root}/hardware/deps/cva6/core/acc_dispatcher.sv"
tb="${root}/verification/uvm/acc_queue_credit_tb.sv"

# Fail instead of silently testing a copied rule after the dispatcher changes.
rg -Uq 'assign\s+acc_ready\s*=\s*!acc_insn_queue_full\s*&&\s*acc_insn_queue_usage\s*<\s*\(InstructionQueueDepth\s*-\s*1\)\s*;' "${dispatcher}"
rg -q '\.push_i\s*\(acc_valid_q\)' "${dispatcher}"
rg -q '\.FALL_THROUGH\s*\(1.b1\)' "${dispatcher}"
test ! -e "${out}"
mkdir -p "${out}"
cd "${out}"
sha256sum "${fifo}" "${dispatcher}" "${tb}" \
  "${root}/verification/uvm/run_acc_queue_credit_unit.sh" > sources.sha256
timeout --foreground --kill-after=10s 120s vcs \
  -full64 -sverilog -assert svaext -timescale=1ns/1ps \
  -top acc_queue_credit_tb "${fifo}" "${tb}" \
  -o simv -l compile.log > compile.console.log 2>&1
timeout --foreground --kill-after=10s 30s ./simv \
  -l run.log > run.console.log 2>&1
sha256sum --check sources.sha256 > sources.check.log
rg '^OLD_WOULD_ISSUE_FULL depth=4 .*usage=0 new_ready=0$' run.log
rg '^OLD_WOULD_PUSH_FULL depth=4 ' run.log
rg '^PASS depth=3 ' run.log
rg '^PASS depth=4 ' run.log
rg '^PASS acc_queue_credit depths=3,4 actual_cva6_fifo_v3$' run.log
if rg 'Error:|Fatal:|Error-|Fatal-|Assertion.*failed' compile.log run.log; then exit 1; fi
