#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-final-mask-atomic-overlay-build-20260925-01.service
image="${root}/verification/out/final-mask-atomic-overlay-image-20260925-01/sim"
base="${root}/verification/out/masked-indexed-latest-uvm-closure-20260924-01"
source="${root}/verification/out/final-rvv-load_store-seeds1-10-20260924-01"
output="${root}/verification/out/final-mask-atomic-seed6-replay-20260925-01"
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
  --output "${image}/vcs_source_manifest.json"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
test ! -e "${output}"
sha256sum "${image}/simv" "${spike}" "${source}/tests/ara_dsa_rvv1_load_store_5/input.elf" \
  > "${image}/replay_inputs.sha256"
PYTHONPATH="${root}/verification" python3 "${root}/verification/verify.py" replay-failed-rvv \
  --summary "${source}/summary.json" \
  --case ara_dsa_rvv1_load_store_5 \
  --output "${output}" \
  --simv "${image}/simv" --spike "${spike}" \
  --timeout 900 --spike-timeout 30 --watchdog-cycles 1000000
PYTHONPATH="${root}/verification" python3 "${root}/verification/verify.py" audit \
  --run "${output}" --require-trace --require-vector --require-full-match \
  --output "${output}/independent_audit.json"
test "$(jq -r .status "${output}/independent_audit.json")" = PASS
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
