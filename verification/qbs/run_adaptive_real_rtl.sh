#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
capture_root=${QBS_REAL_CAPTURE_ROOT:-${HOME}/llama/captures/qwen2.5-1.5b-q4_k_m}
result_dir=${QBS_ADAPTIVE_RTL_RESULT_DIR:-${script_dir}/rtl_engine_build/adaptive_real}
case_timeout=${QBS_ADAPTIVE_RTL_TIMEOUT:-180}
generator=${script_dir}/qbs_command_vectors
simulator=${script_dir}/rtl_engine_build/simv

q4_capture=${capture_root}/prefill/operators/blk_0_attn_q_weight
q6_capture=${capture_root}/prefill/operators/blk_0_ffn_down_weight

for required in \
  "${q4_capture}/weight_q4_K.bin" \
  "${q4_capture}/activation_f32.bin" \
  "${q4_capture}/output_f32.bin" \
  "${q6_capture}/weight_q6_K.bin" \
  "${q6_capture}/activation_f32.bin" \
  "${q6_capture}/output_f32.bin"; do
  if [[ ! -f ${required} ]]; then
    printf 'missing real-model capture: %s\n' "${required}" >&2
    exit 2
  fi
done

if [[ ! -x ${generator} || ! -x ${simulator} ]]; then
  printf 'build qbs_command_vectors and rtl-engine-compile first\n' >&2
  exit 2
fi

mkdir -p "${result_dir}"
summary=${result_dir}/summary.csv
printf '%s\n' \
  'case,profile,m,n,k,cycles,weight_bytes,activation_bytes,payload_bytes,ranges,dot_cycles,prefetch_wait_cycles' \
  > "${summary}"

run_case() {
  local name=$1
  local profile=$2
  local capture=$3
  local full_n=$4
  local k=$5
  local input_start=$6
  local m=$7
  local output_start=$8
  local n=$9
  local vectors=${result_dir}/${name}.vectors
  local log=${result_dir}/${name}.log

  "${generator}" "${vectors}" --real "${profile}" "${capture}" \
    "${full_n}" "${k}" "${input_start}" "${m}" "${output_start}" "${n}"
  timeout "${case_timeout}" "${simulator}" -l "${log}" +QBS_FUNCTIONAL_ONLY \
    +QBS_COMMAND_VECTOR_FILE="${vectors}" >/dev/null

  python3 - "${name}" "${profile}" "${m}" "${n}" "${k}" \
      "${log}" "${summary}" <<'PY'
import csv
import re
import sys

name, profile, m, n, k, log_path, summary_path = sys.argv[1:]
text = open(log_path, encoding="utf-8").read()
cycle = re.search(r"QBS end-to-end case 0 PASS .* cycles=(\d+)", text)
traffic = re.search(
    r"QBS traffic case=0 weight=(\d+) activation=(\d+) payload=(\d+) "
    r"ranges=(\d+) dot=(\d+) prefetch_wait=(\d+)", text)
if (cycle is None or traffic is None or
        "QBS engine PASS: 1 functional cases" not in text or
        "Fatal:" in text):
    raise SystemExit(f"incomplete QBS RTL result: {log_path}")
with open(summary_path, "a", newline="", encoding="utf-8") as output:
    csv.writer(output).writerow(
        [name, profile, m, n, k, cycle.group(1), *traffic.groups()]
    )
PY
  printf '%-14s PASS\n' "${name}"
}

# Full captured reduction dimensions are retained. Only the output slice is
# narrowed so each focused VCS run remains short and directly comparable.
run_case q4_m4n32 q4_K "${q4_capture}" 1536 1536 0 4 0 32
run_case q4_m8n16 q4_K "${q4_capture}" 1536 1536 0 8 0 16
run_case q4_m7n16 q4_K "${q4_capture}" 1536 1536 8 7 0 16
run_case q6_m4n32 q6_K "${q6_capture}" 1536 8960 0 4 0 32
run_case q6_m8n16 q6_K "${q6_capture}" 1536 8960 0 8 0 16
run_case q6_m7n16 q6_K "${q6_capture}" 1536 8960 8 7 0 16

printf 'wrote %s\n' "${summary}"
