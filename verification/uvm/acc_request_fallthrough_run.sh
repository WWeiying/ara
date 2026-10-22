#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: acc_request_fallthrough_run.sh NEW_OUTPUT_DIR}")
common="${root}/hardware/deps/common_cells"
sources=(
  "${common}/src/fifo_v3.sv"
  "${root}/hardware/src/common_cells_compat/fall_through_register_v1.sv"
  "${root}/verification/uvm/acc_request_fallthrough_tb.sv"
)

# Separate work directory and source hashes preserve existing frozen images.
test ! -e "${out}"
mkdir -p "${out}"
cd "${out}"
sha256sum "${sources[@]}" "${common}"/include/common_cells/*.svh \
  "${root}/verification/uvm/acc_request_fallthrough_run.sh" > sources.sha256
timeout --foreground --kill-after=10s 120s vcs \
  -full64 -sverilog -assert svaext -timescale=1ns/1ps \
  "+incdir+${common}/include" -top acc_request_fallthrough_tb "${sources[@]}" \
  -o simv -l compile.log > compile.console.log 2>&1
set +e
timeout --foreground --kill-after=10s 30s ./simv \
  -l run.log > run.console.log 2>&1
run_rc=$?
set -e
printf '%s\n' "${run_rc}" > run.exitcode
sha256sum --check sources.sha256 > sources.check.log
sha256sum simv > binary.sha256
rg '^(SUMMARY|COVER|PASS acc_request_fallthrough)' run.log || true
if (( run_rc != 0 )); then exit "${run_rc}"; fi
rg '^PASS acc_request_fallthrough actual_module=fall_through_register_v1 depth=2 nonflushable=1$' run.log
if rg 'Error:|Fatal:|Error-|Fatal-|FAIL|Assertion.*failed' compile.log run.log; then exit 1; fi
