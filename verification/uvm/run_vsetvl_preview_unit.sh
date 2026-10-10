#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_vsetvl_preview_unit.sh NEW_OUTPUT_DIR}")
test ! -e "${out}"
mkdir -p "${out}"
cd "${out}"
timeout --foreground 120 vcs -full64 -sverilog -timescale=1ns/1ps \
  -top vsetvl_preview_tb \
  "${root}/hardware/src/vsetvl_preview.sv" \
  "${root}/verification/uvm/vsetvl_preview_tb.sv" \
  -o simv -l compile.log > compile.console.log 2>&1
timeout --foreground 60 ./simv -l run.log > run.console.log 2>&1
rg '^PASS cases=' run.log
if rg 'Error:|Fatal:|Error-|Fatal-' run.log; then exit 1; fi
