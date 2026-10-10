#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-final-seed6-probe-build-20260925-04.service
image="${root}/verification/out/final-seed6-probe-image-20260925-04/sim"
source="${root}/verification/out/final-rvv-load_store-seeds1-10-20260924-01/tests/ara_dsa_rvv1_load_store_5"
output="${root}/verification/out/final-seed6-indexed-segment-probe-20260925-05"

while systemctl --user is-active --quiet "${unit}"; do
  sleep 60
done

test -x "${image}/simv"
if [[ ! -e "${image}/vcs_source_manifest.json" ]]; then
  PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
    --filelist "${root}/verification/out/masked-indexed-latest-uvm-closure-20260924-01/build/vcs/bender_script_default" \
    --repo-root "${root}" \
    --extra-source "${root}/verification/out/masked-indexed-latest-uvm-closure-20260924-01/build/work-dpi/elfloader.o" \
    --extra-source "${root}/verification/uvm/ara_cvxif_if.sv" \
    --extra-source "${root}/verification/uvm/ara_cvxif_uvm_pkg.sv" \
    --extra-source "${root}/verification/uvm/ara_acc_contract_monitor.sv" \
    --extra-source "${root}/verification/uvm/ara_cvxif_dut_bind.sv" \
    --extra-source "${root}/verification/probes/indexed_segment_stall_probe.sv" \
    --output "${image}/vcs_source_manifest.json"
fi
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
test ! -e "${output}"
mkdir -p "${output}"
cp -- "${source}/input.elf" "${output}/input.elf"
test "$(sha256sum "${output}/input.elf" | cut -d ' ' -f 1)" = \
  "$(jq -r .binary.sha256 "${source}/inputs.json")"
(
  cd "${output}"
  sha256sum "${image}/simv" \
    "${root}/verification/probes/indexed_segment_stall_probe.sv" \
    input.elf > INPUT_SHA256SUMS
  timeout --foreground 30 "${image}/simv" -l run.vcs.log \
    +ntb_random_seed=6 +PRELOAD="${output}/input.elf" \
    +TESTCASE=ara_dsa_rvv1_load_store_5 +NO_FSDB +NO_INSTR_TRACE \
    +INDEXED_SEG_STALL_PROBE +COMMIT_WATCHDOG=1000000 \
    > console.log 2>&1
  sha256sum -c --status INPUT_SHA256SUMS
  rg -q '^\[IDX_SEG_STALL\] cyc=8300 ' console.log
  sha256sum console.log run.vcs.log INPUT_SHA256SUMS > RUN_SHA256SUMS
)
