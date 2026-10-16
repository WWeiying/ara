#!/usr/bin/env bash
set -euo pipefail
netlist=$(realpath "${1:?exported MMU netlist}")
models=$(realpath "${2:?matching unisims}")
mkdir "${3:?new output}"
out=$(realpath "$3")
here=$(cd "$(dirname "$0")" && pwd)
tb="$here/mmu_ppn_mapped_tb.sv"
sha256sum "$netlist" "$tb" "$models"/*.v > "$out/sources.sha256"
cd "$out"
timeout 180 vcs -full64 -sverilog -timescale=1ns/1ps -top mmu_ppn_mapped_tb -top glbl \
  +libext+.v -y "$models" "$netlist" "$tb" -o simv -Mdir=csrc \
  -l compile.log > compile_console.log 2>&1
timeout 30 ./simv -no_save -l run.log
grep -q "MMU_PPN_MAPPED_PASS" run.log
