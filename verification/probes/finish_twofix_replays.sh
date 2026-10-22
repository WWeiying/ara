#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-final-twofix-overlay-build-20260925-01.service
image="${root}/verification/out/final-twofix-overlay-image-20260925-01/sim"
base="${root}/verification/out/masked-indexed-latest-uvm-closure-20260924-01"
output="${root}/verification/out/final-twofix-frozen-replays-20260925-01"
spike=/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike

while systemctl --user is-active --quiet "${unit}"; do
  sleep 60
done

test -x "${image}/simv"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --filelist "${base}/build/vcs/bender_script_default" \
  --repo-root "${root}" \
  --extra-source "${base}/build/work-dpi/elfloader.o" \
  --extra-source "${root}/verification/uvm/ara_cvxif_if.sv" \
  --extra-source "${root}/verification/uvm/ara_cvxif_uvm_pkg.sv" \
  --extra-source "${root}/verification/uvm/ara_acc_contract_monitor.sv" \
  --extra-source "${root}/verification/uvm/ara_cvxif_dut_bind.sv" \
  --extra-source "${root}/verification/probes/mask_atomic_candidate/vldu.sv" \
  --extra-source "${root}/verification/probes/mask_atomic_candidate/vstu.sv" \
  --extra-source "${root}/verification/probes/gather_candidate/masku.sv" \
  --output "${image}/vcs_source_manifest.json"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
test ! -e "${output}"
mkdir -p "${output}"
sha256sum "${image}/simv" "${spike}" \
  "${root}/verification/out/final-rvv-load_store-seeds1-10-20260924-01/tests/ara_dsa_rvv1_load_store_5/input.elf" \
  "${root}/verification/out/final-rvv-integer_stress-seeds1-10-20260924-01/tests/ara_dsa_rvv1_integer_stress_4/input.elf" \
  > "${output}/INPUT_SHA256SUMS"

export PYTHONPATH="${root}/verification"
python3 "${root}/verification/verify.py" replay-failed-rvv \
  --summary "${root}/verification/out/final-rvv-load_store-seeds1-10-20260924-01/summary.json" \
  --case ara_dsa_rvv1_load_store_5 --output "${output}/load_store" \
  --simv "${image}/simv" --spike "${spike}" \
  --timeout 1200 --spike-timeout 30 --watchdog-cycles 1000000 \
  > "${output}/load_store.log" 2>&1 &
load_pid=$!
python3 "${root}/verification/verify.py" replay-failed-rvv \
  --summary "${root}/verification/out/final-rvv-integer_stress-seeds1-10-20260924-01/summary.json" \
  --case ara_dsa_rvv1_integer_stress_4 --output "${output}/integer_stress" \
  --simv "${image}/simv" --spike "${spike}" \
  --timeout 1200 --spike-timeout 30 --watchdog-cycles 1000000 \
  > "${output}/integer_stress.log" 2>&1 &
integer_pid=$!

load_status=0
integer_status=0
wait "${load_pid}" || load_status=$?
wait "${integer_pid}" || integer_status=$?
printf 'load_store=%d\ninteger_stress=%d\n' \
  "${load_status}" "${integer_status}" > "${output}/runner_status.txt"

audit_status=0
for profile in load_store integer_stress; do
  python3 "${root}/verification/verify.py" audit \
    --run "${output}/${profile}" --require-trace --require-vector \
    --require-full-match --output "${output}/${profile}/independent_audit.json" \
    || audit_status=1
  test "$(jq -r .status "${output}/${profile}/independent_audit.json")" = PASS \
    || audit_status=1
done
sha256sum -c --status "${output}/INPUT_SHA256SUMS"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
test "${load_status}" -eq 0 && test "${integer_status}" -eq 0 &&
  test "${audit_status}" -eq 0
