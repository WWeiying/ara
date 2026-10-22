#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
simv=$(realpath -- "${1:?usage: run_real_dut_case.sh SIMV ELF TESTCASE NEW_OUTPUT_DIR}")
elf=$(realpath -- "${2:?usage: run_real_dut_case.sh SIMV ELF TESTCASE NEW_OUTPUT_DIR}")
testcase=${3:?usage: run_real_dut_case.sh SIMV ELF TESTCASE NEW_OUTPUT_DIR [read|write]}
out=$(realpath -m -- "${4:?usage: run_real_dut_case.sh SIMV ELF TESTCASE NEW_OUTPUT_DIR [read|write]}")
reset_kind=${5:-}
contract_trace_limit=${ARA_CONTRACT_TRACE_LIMIT:-100000}
uvm_trace_limit=${ARA_UVM_TRACE_LIMIT:-100000}
timeout_seconds=${ARA_VCS_TIMEOUT_SECONDS:-900}
for value in "${contract_trace_limit}" "${uvm_trace_limit}" "${timeout_seconds}"; do
  if [[ ! ${value} =~ ^[1-9][0-9]*$ ]]; then
    printf 'trace limits and timeout must be positive decimal integers: %s\n' "${value}" >&2
    exit 2
  fi
done
if [[ ! ${testcase} =~ ^[A-Za-z0-9_+.-]+$ || -e ${out} ]]; then
  printf 'invalid testcase or output already exists: %s %s\n' "${testcase}" "${out}" >&2
  exit 2
fi
if [[ -n ${reset_kind} && ${reset_kind} != read && ${reset_kind} != write && ${reset_kind} != state ]]; then
  printf 'reset kind must be read, write or state: %s\n' "${reset_kind}" >&2
  exit 2
fi
sim_config=${simv%/*}/simulator.conf
source_manifest=${simv%/*}/vcs_source_manifest.json
if [[ ! -x ${simv} || ! -d ${simv}.daidir || ! -f ${sim_config} || ! -f ${elf} ]]; then
  printf 'complete VCS image, configuration and ELF are required\n' >&2
  exit 2
fi
if [[ -f ${source_manifest} ]]; then
  PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
    --output "${source_manifest}" --check
fi
mkdir -p -- "${out}/work"
cp -p -- "${elf}" "${out}/work/input.elf"
(
  cd -- "${out}"
  sha256sum -- "${simv}" "${sim_config}" \
    "${root}/verification/uvm/run_real_dut_case.sh" work/input.elf > INPUT_SHA256SUMS
  if [[ -f ${source_manifest} ]]; then
    sha256sum -- "${source_manifest}" >> INPUT_SHA256SUMS
  fi
  find "${simv}.daidir" -type f -name '*.so' -print0 | sort -z | \
    xargs -0 -r sha256sum >> INPUT_SHA256SUMS
  sha256sum -c --status INPUT_SHA256SUMS
)
work=${out}/work
sim_args=("+PRELOAD=${work}/input.elf" "+TESTCASE=${testcase}" +NO_FSDB
  "+ARA_CONTRACT_TRACE_LIMIT=${contract_trace_limit}"
  "+ARA_UVM_TRACE_LIMIT=${uvm_trace_limit}"
  "+VECTOR_TRACE=${work}/vector_trace.csv")
if [[ ${ARA_VCS_CODE_COVERAGE:-0} == 1 ]]; then
  sim_args+=(-cm line+cond+fsm+tgl+branch -cm_dir "${out}/code.vdb" -cm_name "${testcase}")
fi
if [[ ${ARA_UVM_TRACE_AXI_WRITE:-0} == 1 ]]; then
  sim_args+=(+ARA_UVM_TRACE_AXI_WRITE)
fi
check_args=()
if [[ -n ${reset_kind} ]]; then
  sim_args+=("+ARA_UVM_RESET_ON_AXI=${reset_kind}")
  check_args+=(--expect-reset-abort "${reset_kind}")
  if [[ ${reset_kind} == read && -n ${ARA_UVM_RESET_READ_INDEX:-} ]]; then
    if [[ ! ${ARA_UVM_RESET_READ_INDEX} =~ ^[1-9][0-9]*$ ]]; then
      printf 'ARA_UVM_RESET_READ_INDEX must be positive decimal\n' >&2
      exit 2
    fi
    sim_args+=("+ARA_UVM_RESET_READ_INDEX=${ARA_UVM_RESET_READ_INDEX}")
  fi
  if [[ ${reset_kind} == state ]]; then
    if [[ ! ${ARA_UVM_RESET_STATE_TARGET:-} =~ ^(qbs|akv|disp)_[a-z_]+$ ]]; then
      printf 'ARA_UVM_RESET_STATE_TARGET must name a supported engine state\n' >&2
      exit 2
    fi
    sim_args+=("+ARA_UVM_RESET_STATE_TARGET=${ARA_UVM_RESET_STATE_TARGET}")
  fi
fi
(
  cd -- "${work}"
  timeout --foreground "${timeout_seconds}" "${simv}" -no_save -l "${work}/run.vcs.log" \
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
if [[ ${ARA_VCS_CODE_COVERAGE:-0} == 1 && ! -f ${out}/code.vdb/snps/coverage/db/testdata/${testcase}/fsm.verilog.data.xml ]]; then
  printf 'missing FSM coverage data for %s\n' "${testcase}" >&2
  exit 1
fi
printf 'wrote %s\n' "${out}/uvm_result.json"
