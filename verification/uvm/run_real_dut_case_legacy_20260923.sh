#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
simv=$(realpath -- "${1:?usage: run_real_dut_case.sh SIMV ELF TESTCASE NEW_OUTPUT_DIR}")
elf=$(realpath -- "${2:?usage: run_real_dut_case.sh SIMV ELF TESTCASE NEW_OUTPUT_DIR}")
testcase=${3:?usage: run_real_dut_case.sh SIMV ELF TESTCASE NEW_OUTPUT_DIR [read|write]}
out=$(realpath -m -- "${4:?usage: run_real_dut_case.sh SIMV ELF TESTCASE NEW_OUTPUT_DIR [read|write]}")
reset_kind=${5:-}
if [[ ! ${testcase} =~ ^[A-Za-z0-9_+.-]+$ || -e ${out} ]]; then
  printf 'invalid testcase or output already exists: %s %s\n' "${testcase}" "${out}" >&2
  exit 2
fi
if [[ -n ${reset_kind} && ${reset_kind} != read && ${reset_kind} != write ]]; then
  printf 'reset kind must be read or write: %s\n' "${reset_kind}" >&2
  exit 2
fi
sim_config=${simv%/*}/simulator.conf
if [[ ! -x ${simv} || ! -d ${simv}.daidir || ! -f ${sim_config} || ! -f ${elf} ]]; then
  printf 'complete VCS image, configuration and ELF are required\n' >&2
  exit 2
fi
mkdir -p -- "${out}/work"
cp -p -- "${elf}" "${out}/work/input.elf"
(
  cd -- "${out}"
  sha256sum -- "${simv}" "${sim_config}" \
    "${root}/verification/uvm/run_real_dut_case.sh" work/input.elf > INPUT_SHA256SUMS
  find "${simv}.daidir" -type f -name '*.so' -print0 | sort -z | \
    xargs -0 -r sha256sum >> INPUT_SHA256SUMS
  sha256sum -c --status INPUT_SHA256SUMS
)
work=${out}/work
sim_args=("+PRELOAD=${work}/input.elf" "+TESTCASE=${testcase}" +NO_FSDB
  +ARA_CONTRACT_TRACE_LIMIT=100000 +ARA_UVM_TRACE_LIMIT=100000
  "+VECTOR_TRACE=${work}/vector_trace.csv")
check_args=()
if [[ -n ${reset_kind} ]]; then
  sim_args+=("+ARA_UVM_RESET_ON_AXI=${reset_kind}")
  check_args+=(--expect-reset-abort "${reset_kind}")
fi
(
  cd -- "${work}"
  timeout --foreground 900 "${simv}" -no_save -l "${work}/run.vcs.log" \
    "${sim_args[@]}" > "${work}/console.log" 2>&1
)
PYTHONPATH="${root}/verification" python3 -m ara_verify.uvm_dut \
  --require-events --require-backend --require-axi --require-axi-write \
  --vector-trace "${work}/vector_trace.csv" \
  "${check_args[@]}" \
  --log "${work}/run.vcs.log" --simv "${simv}" \
  --elf "${work}/input.elf" --output "${out}/uvm_result.json"
(
  cd -- "${out}"
  sha256sum -- work/run.vcs.log work/vector_trace.csv work/console.log \
    uvm_result.json INPUT_SHA256SUMS > RUN_SHA256SUMS
  sha256sum -c --status INPUT_SHA256SUMS
  sha256sum -c --status RUN_SHA256SUMS
)
printf 'wrote %s\n' "${out}/uvm_result.json"
