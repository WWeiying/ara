#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_fp16_int8_cast_unit.sh NEW_OUTPUT_DIR [SIM_PLUSARGS...]}")
shift
common="${root}/hardware/deps/common_cells"
fpnew="${root}/hardware/deps/fpnew"
tb="${root}/verification/uvm/fp16_int8_cast_tb.sv"
sources=(
  "${common}/src/cf_math_pkg.sv"
  "${fpnew}/src/fpnew_pkg.sv"
  "${common}/src/lzc.sv"
  "${fpnew}/src/fpnew_classifier.sv"
  "${fpnew}/src/fpnew_rounding.sv"
  "${fpnew}/src/fpnew_cast_multi.sv"
  "${tb}"
)

# Never overwrite the frozen first-failure evidence from an earlier run.
test ! -e "${out}"
mkdir -p "${out}"
cd "${out}"
sha256sum "${sources[@]}" "${common}"/include/common_cells/*.svh \
  "${root}/verification/uvm/run_fp16_int8_cast_unit.sh" \
  "${root}/hardware/src/ara_dispatcher.sv" \
  "${root}/hardware/src/lane/vmfpu.sv" > sources.sha256
timeout --foreground --kill-after=10s 120s vcs \
  -full64 -sverilog -assert svaext -timescale=1ns/1ps \
  "+incdir+${common}/include" -top fp16_int8_cast_tb "${sources[@]}" \
  -o simv -l compile.log > compile.console.log 2>&1

set +e
timeout --foreground --kill-after=10s 30s ./simv "$@" \
  -l run.log > run.console.log 2>&1
run_rc=$?
set -e
printf '%s\n' "${run_rc}" > run.exitcode
sha256sum --check sources.sha256 > sources.check.log
rg '^(CONFIG|FIRST_FAILURE|SUMMARY|PASS fp16_int8_cast)' run.log || true
if (( run_rc != 0 )); then exit "${run_rc}"; fi
rg '^PASS fp16_int8_cast$' run.log
if rg 'Error:|Fatal:|Error-|Fatal-|Assertion.*failed' compile.log run.log; then exit 1; fi
