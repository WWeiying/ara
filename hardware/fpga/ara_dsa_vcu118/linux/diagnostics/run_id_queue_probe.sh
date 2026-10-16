#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
OUT=${1:?new output directory required}
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$ROOT"
D=hardware/fpga/ara_dsa_vcu118/linux/diagnostics
C=hardware/fpga/ara_dsa_vcu118/rtl/common_cells
sources=("$C/src/onehot_to_bin.sv" "$C/src/lzc.sv" "$C/src/id_queue.sv" "$D/id_queue_probe.sv")
extra=()
if [[ -n ${NETLIST:-} ]]; then
  [[ "$NETLIST" = /* && -s "$NETLIST" ]] || { echo 'NETLIST must be an existing absolute path' >&2; exit 2; }
  sources=("$NETLIST"); extra=(-top glbl +define+MAPPED_PROBE)
fi
sha256sum "${sources[@]}" "$D/id_queue_probe_tb.sv" "$D/run_id_queue_probe.sh" > "$OUT/sources.sha256"
vcs -full64 -sverilog -timescale=1ns/1ps -top id_queue_probe_tb "${extra[@]}" \
  +incdir+"$C/include" +define+COMMON_CELLS_ASSERTS_OFF \
  "$C/src/cf_math_pkg.sv" "${sources[@]}" "$D/id_queue_probe_tb.sv" \
  -o "$OUT/simv" -Mdir="$OUT/csrc" -l "$OUT/compile.log" > "$OUT/compile_console.log" 2>&1
for seed in 1 12345 987654; do
  log="$OUT/seed${seed}.log"
  (cd "$OUT"; timeout 60 ./simv -no_save +SEED="$seed" -l "$log")
  grep -q ID_QUEUE_PASS "$log"
done
