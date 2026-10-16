#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
OUT=${1:?output directory required}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$ROOT"
extra=()
sources=(hardware/deps/common_cells/src/spill_register_flushable.sv
  hardware/deps/common_cells/src/spill_register.sv
  hardware/src/lane/fixed_p_rounding.sv hardware/src/lane/simd_alu.sv
  "${RTL_VALU_SOURCE:-hardware/src/lane/valu.sv}")
if [[ -n ${NETLIST:-} ]]; then
  [[ -f "$NETLIST" ]] || { echo 'Missing NETLIST' >&2; exit 1; }
  extra=(-top glbl "+define+MAPPED_VALU=${MAPPED_VALU:?mapped module name required}")
  sources=("$NETLIST")
fi
vcs -full64 -sverilog -timescale=1ns/1ps -top valu_discard_tb "${extra[@]}" \
  +incdir+hardware/deps/common_cells/include \
  hardware/deps/common_cells/src/cf_math_pkg.sv \
  hardware/deps/axi/src/axi_pkg.sv \
  hardware/deps/cva6/core/include/config_pkg.sv \
  hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv \
  hardware/deps/cva6/core/include/riscv_pkg.sv \
  hardware/include/rvv_pkg.sv hardware/deps/fpnew/src/fpnew_pkg.sv \
  hardware/include/ara_pkg.sv \
  "${sources[@]}" \
  hardware/fpga/ara_dsa_vcu118/linux/diagnostics/valu_discard_tb.sv \
  -o "$OUT/simv" -Mdir="$OUT/csrc" -l "$OUT/compile.log"
cd "$OUT"
for gap in 0 1 2 7 31; do
  for pressure in 0 1; do
    log="gap${gap}_pressure${pressure}.log"
    timeout 60 ./simv -no_save +GAP="$gap" +BACKPRESSURE="$pressure" -l "$log"
    grep -q 'VALU_DISCARD_PASS' "$log"
  done
done
