#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
filelist=$(realpath -- "${1:?VCS_FILELIST NEW_OUTPUT_DIR}")
out=$(realpath -m -- "${2:?missing new output directory}")
test ! -e "$out"
mkdir -p "$out"
cd "$out"
rg '^\+|/hardware/deps/(common_cells|fpnew)/' "$filelist" > unit.f
sha256sum "$root/hardware/deps/fpnew/src/fpnew_opgroup_multifmt_slice.sv" \
  "$root/verification/uvm/fp_div_flags_tb.sv" > sources.sha256
timeout 180 vcs -full64 -sverilog -timescale=1ns/1ps \
  -f unit.f "$root/verification/uvm/fp_div_flags_tb.sv" \
  -top fp_div_flags_tb -o simv -l compile.log > compile.console.log 2>&1
set +e
timeout 30 ./simv -l run.log > run.console.log 2>&1
rc=$?
set -e
sha256sum --check sources.sha256 > sources.check.log
rg 'DIV_PROBE|DIV_FAILURE|DIV_SUMMARY|PASS fp_div_flags' run.log
if (( rc != 0 )); then exit "$rc"; fi
rg '^PASS fp_div_flags$' run.log
if rg 'DIV_FAILURE|Error:|Fatal:|Error-|Fatal-' compile.log run.log; then exit 1; fi
