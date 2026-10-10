#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
simv=$(realpath -- "${1:?usage: run_real_context_pair.sh SIMV NEW_OUTPUT_DIR}")
out=$(realpath -m -- "${2:?usage: run_real_context_pair.sh SIMV NEW_OUTPUT_DIR}")
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
if [[ ${capabilities[qbs_enabled]:-} != 1 ]]; then
  printf 'VCS image does not enable QBS: %s\n' "${sim_config}" >&2
  exit 2
fi

direct=llama_qwen25_decode_attn_q_qbs_direct2
context=llama_qwen25_decode_attn_q_qbs_ctx2
mkdir -p -- "${out}/${direct}/work" "${out}/${context}/work"
for name in "${direct}" "${context}"; do
  cp -p -- "${root}/apps/bin/${name}" "${out}/${name}/work/input.elf"
  cp -a -- "${root}/apps/${name}/generated" "${out}/${name}/input_data"
done
(
  cd -- "${out}"
  sha256sum -- "${simv}" "${sim_config}" \
    "${root}/verification/qbs/run_real_context_pair.sh" > INPUT_SHA256SUMS
  find "${simv}.daidir" -type f -name '*.so' -print0 | sort -z | \
    xargs -0 -r sha256sum >> INPUT_SHA256SUMS
  sha256sum -- "${direct}/work/input.elf" "${context}/work/input.elf" \
    "${direct}/input_data/"* "${context}/input_data/"* >> INPUT_SHA256SUMS
  sha256sum -c --status INPUT_SHA256SUMS
)

run_case() {
  local name=$1
  local work=${out}/${name}/work
  cd -- "${work}"
  timeout --foreground 900 "${simv}" -no_save -l "${work}/run.vcs.log" \
    "+PRELOAD=${work}/input.elf" "+TESTCASE=${name}" +NO_FSDB +QBS_PERF \
    +ARA_CONTRACT_TRACE_LIMIT=100000 +ARA_UVM_TRACE_LIMIT=100000 \
    "+VECTOR_TRACE=${work}/vector_trace.csv" > "${work}/console.log" 2>&1
}

run_case "${direct}" & direct_pid=$!
run_case "${context}" & context_pid=$!
direct_rc=0
context_rc=0
wait "${direct_pid}" || direct_rc=$?
wait "${context_pid}" || context_rc=$?
if ((direct_rc != 0 || context_rc != 0)); then
  printf 'VCS case failed: DIRECT=%d CONTEXT=%d\n' "${direct_rc}" "${context_rc}" >&2
  exit 1
fi

for name in "${direct}" "${context}"; do
  work=${out}/${name}/work
  PYTHONPATH="${root}/verification" python3 -m ara_verify.uvm_dut \
    --require-events --require-backend --require-axi \
    --vector-trace "${work}/vector_trace.csv" \
    --log "${work}/run.vcs.log" --simv "${simv}" \
    --elf "${work}/input.elf" --output "${out}/${name}/uvm_result.json"
done
python3 "${root}/verification/qbs/check_activation_context_evidence.py" \
  --direct "${out}/${direct}/work/run.vcs.log" \
  --context "${out}/${context}/work/run.vcs.log" > "${out}/comparison.txt"
(
  cd -- "${out}"
  sha256sum -- "${direct}/work/run.vcs.log" "${direct}/work/vector_trace.csv" \
    "${direct}/work/console.log" "${direct}/uvm_result.json" \
    "${context}/work/run.vcs.log" "${context}/work/vector_trace.csv" \
    "${context}/work/console.log" "${context}/uvm_result.json" \
    comparison.txt INPUT_SHA256SUMS > RUN_SHA256SUMS
  sha256sum -c --status INPUT_SHA256SUMS
  sha256sum -c --status RUN_SHA256SUMS
)
printf 'wrote %s\n' "${out}/comparison.txt"
