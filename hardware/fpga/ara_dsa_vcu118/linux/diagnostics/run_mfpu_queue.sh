#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
OUT=${1:?new output directory required}
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$ROOT"
D=hardware/fpga/ara_dsa_vcu118/linux/diagnostics
R=hardware/fpga/ara_dsa_vcu118/rtl
packages=("$R/common_cells/src/cf_math_pkg.sv" "$R/axi/src/axi_pkg.sv"
  "$R/cva6/core/include/config_pkg.sv" "$R/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv"
  "$R/cva6/core/include/riscv_pkg.sv" "$R/ara/hardware/include/rvv_pkg.sv"
  "$R/fpnew/src/fpnew_pkg.sv" "$R/ara/hardware/include/ara_pkg.sv"
  "$R/cva6/core/include/ariane_pkg.sv" "$R/cva6/core/include/build_config_pkg.sv")
sources=("$R/common_cells/src/spill_register_flushable.sv" "$R/common_cells/src/spill_register.sv"
  "$R/tech_cells_generic/src/fpga/tc_clk_xilinx.sv"
  "$R/common_cells/src/lzc.sv" "$R/cva6/core/serdiv.sv"
  "$R/ara/hardware/src/lane/power_gating_generic.sv" "$R/ara/hardware/src/lane/simd_mul.sv"
  "$R/ara/hardware/src/lane/simd_div.sv" "${VMFPU_SOURCE:-$R/ara/hardware/src/lane/vmfpu.sv}"
  "$D/mfpu_queue_probe.sv")
while IFS= read -r source; do sources+=("$source"); done < <(
  python3 "$D/mfpu_sources.py" hardware/fpga/ara_dsa_vcu118
)
extra=()
if [[ ${NO_FPU:-0} == 1 ]]; then extra+=(+define+MFPU_PROBE_NO_FPU); fi
if [[ -n ${NETLIST:-} ]]; then
  [[ "$NETLIST" = /* && -s "$NETLIST" ]] || exit 2
  sources=("$NETLIST")
  packages=()
  extra=(-top glbl)
fi
sha256sum "${packages[@]}" "${sources[@]}" "$D/mfpu_queue_tb.sv" > "$OUT/sources.sha256"
vcs -full64 -sverilog -timescale=1ns/1ps -top mfpu_queue_tb "${extra[@]}" \
  "+incdir+$R/common_cells/include" "+incdir+$R/ara/hardware/include" \
  "${packages[@]}" "${sources[@]}" "$D/mfpu_queue_tb.sv" \
  -o "$OUT/simv" -Mdir="$OUT/csrc" -l "$OUT/compile.log" > "$OUT/compile_console.log" 2>&1
for length in 1 4 32; do
  for pressure in 0 1; do
    log="$OUT/vl${length}_pressure${pressure}.log"
    (cd "$OUT"; timeout 60 ./simv -no_save +VL="$length" +PRESSURE="$pressure" -l "$log")
    grep -q MFPU_QUEUE_PASS "$log"
  done
done
