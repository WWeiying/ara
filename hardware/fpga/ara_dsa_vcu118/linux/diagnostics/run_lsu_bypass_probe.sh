#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
mkdir "${1:?new output directory}"
OUT=$(cd "$1" && pwd)
cd "$ROOT"
R=hardware/fpga/ara_dsa_vcu118/rtl
D=hardware/fpga/ara_dsa_vcu118/linux/diagnostics
sources=("$R/common_cells/src/cf_math_pkg.sv" "$R/axi/src/axi_pkg.sv"
 "$R/cva6/core/include/config_pkg.sv" "$R/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv"
 "$R/cva6/core/include/riscv_pkg.sv" "$R/ara/hardware/include/rvv_pkg.sv"
 "$R/fpnew/src/fpnew_pkg.sv" "$R/ara/hardware/include/ara_pkg.sv"
 "$R/cva6/core/include/ariane_pkg.sv" "$R/cva6/core/lsu_bypass.sv" "$D/lsu_bypass_probe.sv")
extra=()
if [[ -n ${NETLIST:-} ]]; then sources=("$NETLIST"); extra=(-top glbl); fi
sha256sum "${sources[@]}" "$D/lsu_bypass_probe_tb.sv" > "$OUT/sources.sha256"
vcs -full64 -sverilog -timescale=1ns/1ps -top lsu_bypass_probe_tb "${extra[@]}" \
 "+incdir+$R/common_cells/include" "+incdir+$R/ara/hardware/include" \
 "${sources[@]}" "$D/lsu_bypass_probe_tb.sv" -o "$OUT/simv" \
 -Mdir="$OUT/csrc" -l "$OUT/compile.log" > "$OUT/compile_console.log" 2>&1
(cd "$OUT"; timeout 30 ./simv -no_save -l run.log)
grep -q LSU_BYPASS_PASS "$OUT/run.log"
