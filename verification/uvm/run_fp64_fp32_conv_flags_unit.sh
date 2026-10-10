#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_fp64_fp32_conv_flags_unit.sh NEW_OUTPUT_DIR}")
common="${root}/hardware/deps/common_cells"
fpnew="${root}/hardware/deps/fpnew"
sources=(
  "${common}/src/cf_math_pkg.sv"
  "${fpnew}/src/fpnew_pkg.sv"
  "${common}/src/lzc.sv"
  "${fpnew}/src/fpnew_classifier.sv"
  "${fpnew}/src/fpnew_rounding.sv"
  "${fpnew}/src/fpnew_cast_multi.sv"
  "${fpnew}/src/fpnew_opgroup_multifmt_slice.sv"
  "${root}/verification/uvm/fp64_fp32_conv_flags_tb.sv"
)
test ! -e "${out}"
mkdir -p "${out}"
cd "${out}"
sha256sum "${sources[@]}" "${common}"/include/common_cells/*.svh \
  "${root}/verification/uvm/run_fp64_fp32_conv_flags_unit.sh" > sources.sha256
timeout --foreground --kill-after=10s 120s vcs \
  -full64 -sverilog -assert svaext -timescale=1ns/1ps \
  "+incdir+${common}/include" -top fp64_fp32_conv_flags_tb "${sources[@]}" \
  -o simv -l compile.log > compile.console.log 2>&1
set +e
timeout --foreground --kill-after=10s 30s ./simv -l run.log > run.console.log 2>&1
rc=$?
set -e
printf '%s\n' "${rc}" > run.exitcode
sha256sum --check sources.sha256 > sources.check.log
rg '^(CONFIG|FIRST_FAILURE|SUMMARY|PASS fp64)' run.log || true
if ((rc != 0)); then exit "${rc}"; fi
rg '^PASS fp64_fp32_conv_flags$' run.log
if rg 'Error:|Fatal:|Error-|Fatal-|Assertion.*failed' compile.log run.log; then exit 1; fi
