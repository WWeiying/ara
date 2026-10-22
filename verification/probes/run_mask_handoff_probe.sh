#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
base="${root}/verification/out/masked-indexed-latest-uvm-closure-20260924-01"
source="${root}/verification/out/final-rvv-load_store-seeds1-10-20260924-01/tests/ara_dsa_rvv1_load_store_5/input.elf"
out="${root}/verification/out/final-mask-handoff-probe-20260925-01"
test ! -e "${out}"
mkdir -p -- "${out}"
(
  cd -- "${out}"
  vcs -full64 -sverilog +v2k -Mlib=./incremental_db -Mupdate -j16 -lca -kdb \
    -debug_access+all +nospecify +notimingchecks +lint=TFIPC-L +vpi \
    +lint=PCWM +error+30 -ntb_opts uvm-1.2 -top ara_tb -timescale=1ns/100fs \
    +define+SIMULATION +define+no_warning +define+TSMC_NO_WARNING \
    +define+ARA_VERIFY_UVM_CVXIF +define+ARA_VERIFY_AXI_DELAY +define+ARA_NO_FSDB \
    -f "${base}/build/vcs/bender_script_default" \
    "${base}/build/work-dpi/elfloader.o" \
    "${root}/verification/uvm/ara_cvxif_if.sv" \
    "${root}/verification/uvm/ara_cvxif_uvm_pkg.sv" \
    "${root}/verification/uvm/ara_acc_contract_monitor.sv" \
    "${root}/verification/uvm/ara_cvxif_dut_bind.sv" \
    "${root}/verification/probes/mask_atomic_candidate/vldu.sv" \
    "${root}/verification/probes/mask_atomic_candidate/vstu.sv" \
    "${root}/verification/probes/mask_handoff_probe.sv" \
    -l comp.vcs.log > build.stdout.log 2>&1
  sha256sum -- simv "${source}" "${root}/verification/probes/mask_handoff_probe.sv" \
    "${root}/verification/probes/mask_atomic_candidate/vldu.sv" \
    "${root}/verification/probes/mask_atomic_candidate/vstu.sv" > INPUT_SHA256SUMS
  mkdir -p -- run
  cd -- run
  timeout --foreground 120 ../simv -no_save -l run.vcs.log \
    +ntb_random_seed=6 "+PRELOAD=${source}" +TESTCASE=ara_dsa_rvv1_load_store_5 \
    +NO_FSDB +MASK_HANDOFF_PROBE +MASK_HANDOFF_START=1118 \
    +MASK_HANDOFF_STOP=1140 "+COMMIT_TOHOST=0000000080004000" \
    "+COMMIT_EXIT_PC=0000000080002dce" > console.log 2>&1
  sha256sum -- run.vcs.log console.log > RUN_SHA256SUMS
)
