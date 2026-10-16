#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
OUT=${1:?new output directory required}
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$ROOT"
D=hardware/fpga/ara_dsa_vcu118/linux/diagnostics
R=hardware/fpga/ara_dsa_vcu118/rtl
sources=("$R/common_cells/src/cf_math_pkg.sv" "$R/axi/src/axi_pkg.sv"
  "$R/cva6/core/include/config_pkg.sv" "$R/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv"
  "$R/cva6/core/include/riscv_pkg.sv" "$R/ara/hardware/include/rvv_pkg.sv"
  "$R/fpnew/src/fpnew_pkg.sv" "$R/ara/hardware/include/ara_pkg.sv")
extra=()
if [[ -n ${NETLIST:-} ]]; then
  [[ "$NETLIST" = /* && -s "$NETLIST" ]] || { echo 'NETLIST must be an existing absolute path' >&2; exit 2; }
  sources+=("$NETLIST")
  extra+=(-top glbl +define+MAPPED_RESTORE)
else
  sources+=("$R/common_cells/src/spill_register_flushable.sv" "$R/ara/hardware/src/vlsu/vldu.sv")
fi
sources+=("$D/vldu_restore_tb.sv")
sha256sum "${sources[@]}" "$R/ara/hardware/include/ara/ara_typedef.svh" \
  "$D/vldu_restore_mapped.svh" "$D/run_vldu_restore.sh" > "$OUT/sources.sha256"
vcs -full64 -sverilog -timescale=1ns/1ps -top vldu_restore_tb "${extra[@]}" \
  +incdir+"$R/common_cells/include" +incdir+"$R/ara/hardware/include" +incdir+"$D" \
  "${sources[@]}" -o "$OUT/simv" -Mdir="$OUT/csrc" -l "$OUT/compile.log" \
  > "$OUT/compile_console.log" 2>&1
for pressure in 0 1; do
  for seed in 0 1; do
    log="$OUT/pressure${pressure}_seed${seed}.log"
    (cd "$OUT"; timeout 60 ./simv -no_save +SHORT="${SHORT:-0}" +PRESSURE="$pressure" +SEED="$seed" -l "$log")
    grep -q VLDU_RESTORE_PASS "$log"
  done
done
