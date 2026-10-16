#!/usr/bin/env bash
set -euo pipefail
# Usage: bash run_scalar_mapped.sh bypass|load|load_slots|store CELL.v UNISIMS NEW_OUTPUT
case "${1:-}" in bypass|load|load_slots|store) kind=$1;; *) exit 2;; esac
netlist=$(realpath "${2:?exported whole-design cell}")
models=$(realpath "${3:?matching Vivado unisims directory}")
mkdir "${4:?new output directory}"
out=$(realpath "$4")
here=$(cd "$(dirname "$0")" && pwd)
tb="$here/scalar_${kind}_mapped_tb.sv"
top="scalar_${kind}_mapped_tb"
sha256sum "$netlist" "$tb" "$models"/*.v > "$out/sources.sha256"
cd "$out"
vcs -full64 -sverilog -timescale=1ns/1ps -top "$top" -top glbl \
  +libext+.v -y "$models" "$netlist" "$tb" -o simv -Mdir=csrc \
  -l compile.log > compile_console.log 2>&1
timeout 30 ./simv -no_save -l run.log
grep -q "SCALAR_${kind^^}_MAPPED_PASS" run.log
