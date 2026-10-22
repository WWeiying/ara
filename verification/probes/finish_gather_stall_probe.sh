#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-final-gather-probe-build-20260925-01.service
image="${root}/verification/out/final-gather-probe-image-20260925-01/sim"
source="${root}/verification/out/final-rvv-integer_stress-seeds1-10-20260924-01/tests/ara_dsa_rvv1_integer_stress_4"
output="${root}/verification/out/final-integer-seed5-gather-bound-20260925-01"
base="${root}/verification/out/masked-indexed-latest-uvm-closure-20260924-01"

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
  --extra-source "${root}/verification/probes/gather_stall_probe.sv" \
  --output "${image}/vcs_source_manifest.json"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
test ! -e "${output}"
mkdir -p "${output}"
cp -- "${source}/input.elf" "${output}/input.elf"
test "$(sha256sum "${output}/input.elf" | cut -d ' ' -f 1)" = \
  "$(jq -r .binary.sha256 "${source}/inputs.json")"
(
  cd "${output}"
  sha256sum "${image}/simv" "${root}/verification/probes/gather_stall_probe.sv" \
    input.elf > INPUT_SHA256SUMS
  timeout --foreground 600 "${image}/simv" -l run.vcs.log \
    +ntb_random_seed=5 +PRELOAD="${output}/input.elf" \
    +TESTCASE=ara_dsa_rvv1_integer_stress_4 +NO_FSDB \
    +COMMIT_TRACE="${output}/ara_commit_trace.csv" \
    +VECTOR_TRACE="${output}/ara_vector_trace.csv" \
    +COMMIT_WATCHDOG=1000000 +COMMIT_TOHOST=0000000080008000 \
    +COMMIT_EXIT_PC=000000008000710c \
    +GATHER_STALL_PROBE +GATHER_PROBE_START=86000 +GATHER_PROBE_STOP=86800 \
    > console.log 2>&1
  sha256sum -c --status INPUT_SHA256SUMS
  rg -q '^\[GATHER_STALL\] cyc=86800 ' console.log
  sha256sum console.log run.vcs.log ara_commit_trace.csv \
    ara_vector_trace.csv INPUT_SHA256SUMS > RUN_SHA256SUMS
)
