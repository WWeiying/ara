#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runner="${root}/verification/qbs/qbs_real_test"
data_root="${QBS_REAL_DATA_ROOT:-${root}/apps}"

run_case() {
  local name="$1"
  local profile="$2"
  local m="$3"
  local n="$4"
  local k="$5"
  "${runner}" "${name}" "${profile}" "${m}" "${n}" "${k}" \
    "${data_root}/llama_qwen25_${name}/generated"
}

run_case decode_attn_q_eval q4_K 1 1536 1536
run_case decode_ffn_gate_eval q4_K 1 4096 1536
run_case decode_ffn_down_eval q6_K 1 256 8960
run_case prefill_attn_q_eval q4_K 4 1536 1536
run_case prefill_ffn_gate_eval q4_K 4 4096 1536
run_case prefill_ffn_down_eval q6_K 4 64 8960
run_case prefill_attn_q_qbs_m8 q4_K 8 1536 1536
run_case q3k_decode_attn_q_qbs q3_K 1 256 1536
run_case q5k_decode_attn_q_qbs q5_K 1 256 1536
run_case q8_0_decode_attn_q_qbs q8_0 1 256 896
