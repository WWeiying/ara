#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_fp16_conv_mask_unit.sh NEW_OUTPUT_DIR [half|byte|scalar] [focused|extended]}")
mode=${2:-half}
profile=${3:-focused}
defines=()
plusargs=()
case ${mode} in
  half) ;;
  byte) defines+=(+define+CONV_MASK_FINE8) ;;
  scalar) defines+=(+define+CONV_MASK_SCALAR_ONLY) ;;
  *) printf 'unknown configuration: %s\n' "${mode}" >&2; exit 2 ;;
esac
case ${profile} in
  focused) plusargs+=(+CONV_FOCUSED) ;;
  extended) ;;
  *) printf 'unknown profile: %s\n' "${profile}" >&2; exit 2 ;;
esac
common=${root}/hardware/deps/common_cells
fpnew=${root}/hardware/deps/fpnew
sources=(
  "${common}/src/cf_math_pkg.sv"
  "${fpnew}/src/fpnew_pkg.sv"
  "${common}/src/lzc.sv"
  "${fpnew}/src/fpnew_classifier.sv"
  "${fpnew}/src/fpnew_rounding.sv"
  "${fpnew}/src/fpnew_cast_multi.sv"
  "${fpnew}/src/fpnew_opgroup_multifmt_slice.sv"
  "${root}/verification/uvm/fp16_conv_mask_tb.sv"
)
test ! -e "${out}"
mkdir -p "${out}"
cd "${out}"
cp -- "${fpnew}/src/fpnew_opgroup_multifmt_slice.sv" slice_snapshot.sv
cp -- "${root}/verification/uvm/fp16_conv_mask_tb.sv" tb_snapshot.sv
printf '%s %s\n' "${mode}" "${profile}" > configuration.txt
sha256sum "${sources[@]}" "${common}"/include/common_cells/*.svh \
  "${root}/verification/uvm/run_fp16_conv_mask_unit.sh" slice_snapshot.sv > sources.sha256
timeout --foreground --kill-after=10s 120s vcs \
  -full64 -sverilog -assert svaext -timescale=1ns/1ps "${defines[@]}" \
  "+incdir+${common}/include" -top fp16_conv_mask_tb "${sources[@]}" \
  -o simv -l compile.log > compile.console.log 2>&1
set +e
timeout --foreground --kill-after=10s 30s ./simv "${plusargs[@]}" -l run.log > run.console.log 2>&1
rc=$?
set -e
printf '%s\n' "${rc}" > run.exitcode
sha256sum --check sources.sha256 > sources.check.log
sha256sum simv run.log lane_probes.csv first_failure.log > results.sha256
rg '^(CONFIG|FIRST_FAILURE|SUMMARY|PASS fp16_conv_mask)' run.log || true
if ((rc != 0)); then exit "${rc}"; fi
rg '^PASS fp16_conv_mask$' run.log
if rg 'Error:|Fatal:|Error-|Fatal-|Assertion.*failed' compile.log run.log; then exit 1; fi
