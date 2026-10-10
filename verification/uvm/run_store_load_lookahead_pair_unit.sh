#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_store_load_lookahead_pair_unit.sh NEW_OUTPUT_DIR}")
test ! -e "${out}"
mkdir -p "${out}"
cd "${out}"
timeout --foreground 120 vcs -full64 -sverilog -assert svaext -timescale=1ns/1ps \
  -top store_load_lookahead_pair_tb \
  "+incdir+${root}/hardware/deps/axi/include" \
  "${root}/hardware/deps/axi/src/axi_pkg.sv" \
  "${root}/hardware/src/vlsu/store_load_lookahead_pair.sv" \
  "${root}/verification/uvm/store_load_lookahead_pair_tb.sv" \
  -o simv -l compile.log > compile.console.log 2>&1
timeout --foreground 60 ./simv -l run.log > run.console.log 2>&1
rg '^PASS cases=' run.log
if rg 'Error:|Fatal:|Error-|Fatal-' run.log; then exit 1; fi
