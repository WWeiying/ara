#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../../.." && pwd)
OUT=${1:?new output directory required}
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
trap 'rc=$?; printf "EXIT_CODE=%s\n" "$rc" > "$OUT/exit_status.txt"' EXIT
extra="$ROOT/verification/uvm/ara_cvxif_if.sv $ROOT/verification/uvm/ara_cvxif_uvm_pkg.sv $ROOT/verification/uvm/ara_acc_contract_monitor.sv $ROOT/verification/uvm/ara_cvxif_dut_bind.sv"
make -C "$ROOT/hardware" compile config=default nr_lanes=4 vlen=1024 \
  qbs=1 akv=1 akv_v2=1 sim_l2_mb=2 no_fsdb=1 \
  verify_uvm_cvxif=1 verify_axi_delay=1 verify_source_manifest=1 \
  "verify_extra_sources=$extra" buildpath="$OUT/build" sim_dir="$OUT/sim"
python3 "$ROOT/verification/verify.py" run --simv "$OUT/sim/simv" \
  --output "$OUT/regression" --jobs 2 --timeout 300 --contract-monitor \
  --test rvv:vadd --test rvv:vmerge --test rvv:vnclip_edges \
  --test rvv:vreduction_lmul_edges --test rvv:vreduction_overlap_edges \
  --test rvv:vnsrl --test rvv:vnsra --test rvv:vredsum
