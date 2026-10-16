#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
OUT=${1:?new output directory required}
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$ROOT"
D=hardware/fpga/ara_dsa_vcu118/linux/diagnostics
R=hardware/fpga/ara_dsa_vcu118/rtl
# Reuse the exact interface declarations, rather than maintaining a second ABI.
sed -n '/^  \/\/ Interfaces between Ara.s dispatcher/,/^  } ara_resp_t;/p' \
  "$R/ara/hardware/src/ara.sv" > "$OUT/sequencer_types.svh"
grep -q '} ara_resp_t;' "$OUT/sequencer_types.svh"
sources=("$R/common_cells/src/cf_math_pkg.sv" "$R/axi/src/axi_pkg.sv"
  "$R/cva6/core/include/config_pkg.sv" "$R/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv"
  "$R/cva6/core/include/riscv_pkg.sv" "$R/ara/hardware/include/rvv_pkg.sv"
  "$R/fpnew/src/fpnew_pkg.sv" "$R/ara/hardware/include/ara_pkg.sv")
extra=()
aliases=(0)
if [[ -n ${NETLIST:-} ]]; then
  [[ "$NETLIST" = /* && -s "$NETLIST" ]] || exit 2
  python3 "$D/bind_sequencer_netlist.py" "$NETLIST" "$OUT/sequencer_mapped.svh"
  sources+=("$NETLIST")
  extra+=(-top glbl +define+MAPPED_SEQ)
  # vd is always a multiple of eight here. ALIAS=1 deliberately supplies
  # inconsistent replicated low bits and is a negative harness control.
  aliases=("${ALIAS:-0}")
else
  sources+=("$R/common_cells/src/lzc.sv" "$R/common_cells/src/delta_counter.sv"
    "$R/common_cells/src/counter.sv" "$R/ara/hardware/src/ara_sequencer.sv")
fi
sources+=("$D/sequencer_restore_tb.sv")
sha256sum "${sources[@]}" "$OUT/sequencer_types.svh" > "$OUT/sources.sha256"
vcs -full64 -sverilog -timescale=1ns/1ps -top sequencer_restore_tb "${extra[@]}" \
  +incdir+"$R/common_cells/include" +incdir+"$R/ara/hardware/include" +incdir+"$OUT" \
  "${sources[@]}" -o "$OUT/simv" -Mdir="$OUT/csrc" -l "$OUT/compile.log" \
  > "$OUT/compile_console.log" 2>&1
for alias in "${aliases[@]}"; do
 for serial in 0 1; do
  for gap in 0 7; do
    log="$OUT/alias${alias}_serial${serial}_gap${gap}.log"
    (cd "$OUT"; timeout 60 ./simv -no_save +ALIAS="$alias" +SERIAL="$serial" +GAP="$gap" -l "$log")
    grep -q SEQUENCER_RESTORE_PASS "$log"
  done
done
done
