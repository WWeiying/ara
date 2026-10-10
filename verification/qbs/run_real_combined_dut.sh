#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
simv=$(realpath -- "${1:?usage: run_real_combined_dut.sh SIMV NEW_OUTPUT_DIR}")
out=$(realpath -m -- "${2:?usage: run_real_combined_dut.sh SIMV NEW_OUTPUT_DIR}")
case_name=llama_qwen25_small_qbs_akv
if [[ -e ${out} ]]; then
  printf 'output already exists: %s\n' "${out}" >&2
  exit 2
fi
if [[ ! -x ${simv} || ! -d ${simv}.daidir ]]; then
  printf 'complete VCS image is required: %s\n' "${simv}" >&2
  exit 2
fi
sim_config=${simv%/*}/simulator.conf
if [[ ! -f ${sim_config} ]]; then
  printf 'VCS configuration is required: %s\n' "${sim_config}" >&2
  exit 2
fi
declare -A capabilities=()
while IFS='=' read -r key value; do
  if [[ -n ${key} ]]; then capabilities["${key}"]=${value}; fi
done < "${sim_config}"
if [[ ${capabilities[qbs_enabled]:-} != 1 ||
      ${capabilities[akv_v2_enabled]:-} != 1 ||
      ${capabilities[sim_l2_mb]:-} != 4 ]]; then
  printf 'VCS image requires QBS, AKV-v2 and 4 MiB L2: %s\n' "${sim_config}" >&2
  exit 2
fi

mkdir -p -- "${out}/work" "${out}/input_data"
cp -p -- "${root}/apps/bin/${case_name}" "${out}/work/input.elf"
cp -p -- "${root}/apps/${case_name}/data.S" \
  "${root}/apps/${case_name}/case.json" "${out}/input_data/"
(
  cd -- "${out}"
  sha256sum -- "${simv}" "${sim_config}" \
    "${root}/verification/qbs/run_real_combined_dut.sh" \
    "${root}/verification/qbs/check_combined_real_evidence.py" > INPUT_SHA256SUMS
  find "${simv}.daidir" -type f -name '*.so' -print0 | sort -z | \
    xargs -0 -r sha256sum >> INPUT_SHA256SUMS
  sha256sum -- work/input.elf input_data/data.S input_data/case.json >> INPUT_SHA256SUMS
  sha256sum -c --status INPUT_SHA256SUMS
)

work=${out}/work
(
  cd -- "${work}"
  timeout --foreground 3600 "${simv}" -no_save -l "${work}/run.vcs.log" \
    "+PRELOAD=${work}/input.elf" "+TESTCASE=${case_name}" \
    +NO_FSDB +QBS_PERF +AKV_PERF \
    +ARA_CONTRACT_TRACE_LIMIT=100000 +ARA_UVM_TRACE_LIMIT=100000 \
    "+VECTOR_TRACE=${work}/vector_trace.csv" > "${work}/console.log" 2>&1
)
PYTHONPATH="${root}/verification" python3 -m ara_verify.uvm_dut \
  --require-events --require-backend --require-axi --require-axi-write \
  --vector-trace "${work}/vector_trace.csv" \
  --log "${work}/run.vcs.log" --simv "${simv}" \
  --elf "${work}/input.elf" --output "${out}/uvm_result.json"
python3 "${root}/verification/qbs/check_combined_real_evidence.py" \
  --log "${work}/run.vcs.log" --output "${out}/combined_result.json"
(
  cd -- "${out}"
  sha256sum -- work/run.vcs.log work/vector_trace.csv work/console.log \
    uvm_result.json combined_result.json INPUT_SHA256SUMS > RUN_SHA256SUMS
  sha256sum -c --status INPUT_SHA256SUMS
  sha256sum -c --status RUN_SHA256SUMS
)
printf 'wrote %s\n' "${out}/combined_result.json"
