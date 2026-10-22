#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
base="${root}/verification/out/masked-indexed-latest-uvm-closure-20260924-01"
image="${root}/verification/out/final-mask-bundle-image-20260925-02/sim"
out="${root}/verification/out/final-mask-bundle-replays-20260925-02"
spike=/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike
test ! -e "${image}"
test ! -e "${out}"
mkdir -p -- "${image}" "${out}"
(
  cd -- "${image}"
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
    "${root}/verification/probes/mask_bundle_candidate/vldu.sv" \
    "${root}/verification/probes/mask_bundle_candidate/vstu.sv" \
    "${root}/verification/probes/gather_candidate/masku.sv" \
    -l comp.vcs.log > build.stdout.log 2>&1
)
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --filelist "${base}/build/vcs/bender_script_default" --repo-root "${root}" \
  --extra-source "${base}/build/work-dpi/elfloader.o" \
  --extra-source "${root}/verification/uvm/ara_cvxif_if.sv" \
  --extra-source "${root}/verification/uvm/ara_cvxif_uvm_pkg.sv" \
  --extra-source "${root}/verification/uvm/ara_acc_contract_monitor.sv" \
  --extra-source "${root}/verification/uvm/ara_cvxif_dut_bind.sv" \
  --extra-source "${root}/verification/probes/mask_bundle_candidate/vldu.sv" \
  --extra-source "${root}/verification/probes/mask_bundle_candidate/vstu.sv" \
  --extra-source "${root}/verification/probes/gather_candidate/masku.sv" \
  --output "${image}/vcs_source_manifest.json"
sha256sum "${image}/simv" "${spike}" \
  "${root}/verification/out/final-rvv-load_store-seeds1-10-20260924-01/tests/ara_dsa_rvv1_load_store_5/input.elf" \
  "${root}/verification/out/final-rvv-integer_stress-seeds1-10-20260924-01/tests/ara_dsa_rvv1_integer_stress_4/input.elf" \
  > "${out}/INPUT_SHA256SUMS"
export PYTHONPATH="${root}/verification"
python3 "${root}/verification/verify.py" replay-failed-rvv \
  --summary "${root}/verification/out/final-rvv-load_store-seeds1-10-20260924-01/summary.json" \
  --case ara_dsa_rvv1_load_store_5 --output "${out}/load_store" \
  --simv "${image}/simv" --spike "${spike}" \
  --timeout 1200 --spike-timeout 30 --watchdog-cycles 1000000 \
  > "${out}/load_store.log" 2>&1 &
load_pid=$!
python3 "${root}/verification/verify.py" replay-failed-rvv \
  --summary "${root}/verification/out/final-rvv-integer_stress-seeds1-10-20260924-01/summary.json" \
  --case ara_dsa_rvv1_integer_stress_4 --output "${out}/integer_stress" \
  --simv "${image}/simv" --spike "${spike}" \
  --timeout 1200 --spike-timeout 30 --watchdog-cycles 1000000 \
  > "${out}/integer_stress.log" 2>&1 &
integer_pid=$!
load_status=0
integer_status=0
wait "${load_pid}" || load_status=$?
wait "${integer_pid}" || integer_status=$?
printf 'load_store=%d\ninteger_stress=%d\n' \
  "${load_status}" "${integer_status}" > "${out}/runner_status.txt"
audit_status=0
for profile in load_store integer_stress; do
  python3 "${root}/verification/verify.py" audit \
    --run "${out}/${profile}" --require-trace --require-vector \
    --require-full-match --output "${out}/${profile}/independent_audit.json" \
    || audit_status=1
  test "$(jq -r .status "${out}/${profile}/independent_audit.json")" = PASS \
    || audit_status=1
  test "$(jq -r .status "${out}/${profile}/tests/ara_dsa_rvv1_${profile}_$([[ ${profile} == load_store ]] && echo 5 || echo 4)/result.json")" = PASS \
    || audit_status=1
done
sha256sum -c --status "${out}/INPUT_SHA256SUMS"
python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
test "${load_status}" -eq 0 && test "${integer_status}" -eq 0 && \
  test "${audit_status}" -eq 0
