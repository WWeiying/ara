#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
OUT=${1:?new output directory required}
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$ROOT"
D=hardware/fpga/ara_dsa_vcu118/linux/diagnostics
R=hardware/fpga/ara_dsa_vcu118/rtl
A=$R/ara/hardware
sources=( "$R/common_cells/src/cf_math_pkg.sv" "$R/axi/src/axi_pkg.sv"
  "$R/cva6/core/include/config_pkg.sv" "$R/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv"
  "$R/cva6/core/include/riscv_pkg.sv" "$A/include/rvv_pkg.sv"
  "$R/fpnew/src/fpnew_pkg.sv" "$A/include/ara_pkg.sv" )
for file in spill_register_flushable spill_register lzc popcount delta_counter fifo_v3; do
  sources+=("$R/common_cells/src/$file.sv")
done
sources+=("$A/src/sldu/p2_stride_gen.sv" "$A/src/sldu/sldu_op_dp.sv"
  "${ARCHIVED_MODULES:-$A/src/sldu}/sldu.sv" "$A/src/masku/masku_operands.sv"
  "${ARCHIVED_MODULES:-$A/src/masku}/masku.sv" "$D/mask_slide_restart_tb.sv")
sha256sum "${sources[@]}" "$A/include/ara/ara_typedef.svh" > "$OUT/sources.sha256"
vcs -full64 -sverilog -timescale=1ns/1ps -top mask_slide_restart_tb \
  +incdir+"$R/common_cells/include" +incdir+"$A/include" \
  "${sources[@]}" -o "$OUT/simv" -Mdir="$OUT/csrc" \
  -l "$OUT/compile.log" > "$OUT/compile_console.log" 2>&1
for spec in '2 0 0' '2 8 0' '3 0 0' '3 4 0' '1 0 1' '1 16 1'; do
  read -r sew start down <<< "$spec"
  (cd "$OUT"; timeout 30 ./simv -no_save +SEW="$sew" +START="$start" +DOWN="$down" \
    -l "sew${sew}_start${start}_down${down}.log")
  grep -q MASK_SLIDE_HYPOTHESIS_CONFIRMED "$OUT/sew${sew}_start${start}_down${down}.log"
done
