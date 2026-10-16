#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
OUT=${1:?new output directory required}
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$ROOT"
D=hardware/fpga/ara_dsa_vcu118/linux/diagnostics
case ${PROBE:-vldu} in vldu|sldu) ;; *) echo 'Unknown PROBE' >&2; exit 2;; esac
sources=(hardware/deps/common_cells/src/spill_register_flushable.sv
  hardware/deps/common_cells/src/spill_register.sv hardware/src/vlsu/vldu.sv
  "$D/vldu_queue_probe.sv")
extra=()
marker=VLDU_QUEUE_PASS
if [[ ${PROBE:-vldu} == sldu ]]; then
  sources=(hardware/deps/common_cells/src/spill_register_flushable.sv
    hardware/deps/common_cells/src/lzc.sv hardware/deps/common_cells/src/popcount.sv
    hardware/src/sldu/p2_stride_gen.sv hardware/src/sldu/sldu_op_dp.sv
    hardware/src/sldu/sldu.sv "$D/sldu_queue_probe.sv")
  extra+=(+define+SLDU_PROBE)
  marker=SLDU_QUEUE_PASS
fi
if [[ -n ${NETLIST:-} ]]; then
  [[ "$NETLIST" = /* && -s "$NETLIST" ]] || { echo 'NETLIST must be an existing absolute path' >&2; exit 2; }
  sources=("$NETLIST")
  extra+=(-top glbl +define+MAPPED_PROBE)
fi
sha256sum "${sources[@]}" "$D/vldu_queue_tb.sv" "$D/run_vldu_queue.sh" > "$OUT/sources.sha256"
vcs -full64 -sverilog -timescale=1ns/1ps -top vldu_queue_tb "${extra[@]}" \
  +incdir+hardware/deps/common_cells/include +incdir+hardware/include \
  hardware/deps/common_cells/src/cf_math_pkg.sv hardware/deps/axi/src/axi_pkg.sv \
  hardware/deps/cva6/core/include/config_pkg.sv \
  hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv \
  hardware/deps/cva6/core/include/riscv_pkg.sv hardware/include/rvv_pkg.sv \
  hardware/deps/fpnew/src/fpnew_pkg.sv hardware/include/ara_pkg.sv \
  "${sources[@]}" "$D/vldu_queue_tb.sv" \
  -o "$OUT/simv" -Mdir="$OUT/csrc" -l "$OUT/compile.log" > "$OUT/compile_console.log" 2>&1
for sew in 0 1 2 3; do
  for bytes in "$((1<<sew))" "$((32+(1<<sew)))" 128 512; do
    for pressure in 0 1; do
      log="$OUT/sew${sew}_bytes${bytes}_pressure${pressure}.log"
      (cd "$OUT"; timeout 60 ./simv -no_save +SEW="$sew" +BYTES="$bytes" +PRESSURE="$pressure" -l "$log")
      grep -q "$marker" "$log"
    done
  done
done
