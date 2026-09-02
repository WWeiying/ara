#!/usr/bin/env bash
set -euo pipefail

max_abs_tolerance=${AKV_LOGITS_MAX_ABS_TOLERANCE:-0.001}
model_max_kl_tolerance=${AKV_MODEL_LOGITS_MAX_KL_TOLERANCE:-0.02}
model_min_cosine_tolerance=${AKV_MODEL_LOGITS_MIN_COSINE_TOLERANCE:-0.98}
model_min_top5_overlap_tolerance=${AKV_MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE:-0.8}
model_mode=${AKV_MODEL_MODE:-akv-v1}
default_model_guest_path=/model/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
model_guest_path=${AKV_MODEL_GUEST_PATH:-${default_model_guest_path}}
model_tokens=${AKV_MODEL_TOKENS:-2}
model_prompt=${AKV_MODEL_PROMPT:-The quick brown fox jumps over the lazy dog.}
qemu_memory=${AKV_QEMU_MEMORY:-4G}
require_prefill=${AKV_REQUIRE_PREFILL:-0}
ara_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
number_re='^([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
grep -Eq "${number_re}" <<< "${max_abs_tolerance}" || {
  printf 'invalid AKV_LOGITS_MAX_ABS_TOLERANCE: %s\n' "${max_abs_tolerance}" >&2
  exit 2
}
for metric in \
  "AKV_MODEL_LOGITS_MAX_KL_TOLERANCE:${model_max_kl_tolerance}" \
  "AKV_MODEL_LOGITS_MIN_COSINE_TOLERANCE:${model_min_cosine_tolerance}" \
  "AKV_MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE:${model_min_top5_overlap_tolerance}"; do
  name=${metric%%:*}
  value=${metric#*:}
  grep -Eq "${number_re}" <<< "${value}" || {
    printf 'invalid %s: %s\n' "${name}" "${value}" >&2
    exit 2
  }
done
awk -v value="${model_min_cosine_tolerance}" \
  'BEGIN { exit !((value + 0.0) >= 0.0 && (value + 0.0) <= 1.0) }' || {
  printf 'AKV_MODEL_LOGITS_MIN_COSINE_TOLERANCE must be in [0,1]\n' >&2
  exit 2
}
awk -v value="${model_min_top5_overlap_tolerance}" \
  'BEGIN { exit !((value + 0.0) >= 0.0 && (value + 0.0) <= 1.0) }' || {
  printf 'AKV_MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE must be in [0,1]\n' >&2
  exit 2
}

metric_value() {
  local log_file=$1
  local key=$2
  sed -n "s/^${key}=//p" "${log_file}" | tr -d '\r' | tail -n 1
}

require_metric_le() {
  local log_file=$1
  local key=$2
  local limit=$3
  local value
  value=$(metric_value "${log_file}" "${key}")
  grep -Eq "${number_re}" <<< "${value}"
  awk -v value="${value}" -v limit="${limit}" \
    'BEGIN { exit !((value + 0.0) <= (limit + 0.0)) }'
}

require_metric_ge() {
  local log_file=$1
  local key=$2
  local limit=$3
  local value
  value=$(metric_value "${log_file}" "${key}")
  grep -Eq "${number_re}" <<< "${value}"
  awk -v value="${value}" -v limit="${limit}" \
    'BEGIN { exit !((value + 0.0) >= (limit + 0.0)) }'
}

validate_log() {
  local log_file=$1
  local result_file=$2
  local coverage_line
  local candidate_ops
  local executed_ops
  local accounted_ops
  local max_abs
  local expected_runs
  local prompt_token_count
  local -a prompt_token_counts=()
  local -a qbs_profiles=()

  case ${model_mode} in
    combined|combined-fallback) expected_runs=3 ;;
    akv-v1|qbs-lifetime) expected_runs=2 ;;
  esac
  mapfile -t prompt_token_counts < <(
    sed -n 's/.*prompt eval time.*\/[[:space:]]*\([0-9][0-9]*\)[[:space:]]*tokens.*/\1/p' \
      "${log_file}"
  )
  (( ${#prompt_token_counts[@]} == expected_runs ))
  prompt_token_count=${prompt_token_counts[0]}
  for value in "${prompt_token_counts[@]}"; do
    [[ ${value} == "${prompt_token_count}" ]]
  done
  if [[ ${require_prefill} == 1 ]]; then
    (( prompt_token_count >= 15 ))
  fi

  if [[ ${model_mode} == qbs-lifetime ]]; then
    grep -q 'AKV_TOKEN_RUN_EXIT=QBS_CONTEXT_BASELINE:0' "${log_file}"
    grep -q 'AKV_TOKEN_RUN_EXIT=QBS_CROSS_OP:0' "${log_file}"
    grep -Eq 'GGML_RISCV_QBS_LIFETIME_SUMMARY quantizations=[1-9][0-9]* .*exact_reuse_candidates=[1-9][0-9]*' \
      "${log_file}"
    grep -Eq 'GGML_RISCV_QBS_LIFETIME_SUMMARY .*graph_epochs=[1-9][0-9]*' "${log_file}"
    grep -Eq 'GGML_RISCV_QBS_LIFETIME_SUMMARY .*cross_op_quantization_skips=[1-9][0-9]*' "${log_file}"
    grep -Eq 'GGML_RISCV_QBS_CROSS_OP .*quantization_skipped=1' "${log_file}"
    grep -Eq 'GGML_RISCV_QBS_COMMAND .*linked=1' "${log_file}"
    ! grep -Eq 'GGML_RISCV_QBS_COMMAND .*linked=0' "${log_file}"
    grep -Eq 'QBS_CROSS_OP_LOGITS_RECORDS=[1-9][0-9]*' "${log_file}"
    grep -Eq 'QBS_CROSS_OP_LOGITS_COMPARABLE_RECORDS=[1-9][0-9]*' "${log_file}"
    grep -q 'QBS_CROSS_OP_LOGITS_TOP1_EQUAL=1' "${log_file}"
    grep -q 'QBS_CROSS_OP_TOKEN_OUTPUT_EQUAL=1' "${log_file}"
    max_abs=$(sed -n 's/^QBS_CROSS_OP_LOGITS_MAX_ABS=//p' "${log_file}" | tr -d '\r' | tail -n 1)
    grep -Eq "${number_re}" <<< "${max_abs}"
    awk -v value="${max_abs}" -v tolerance="${max_abs_tolerance}" \
      'BEGIN { exit !((value + 0.0) <= (tolerance + 0.0)) }'
    grep -q 'LLAMA_GUEST_EXIT=0' "${log_file}"
    grep -E '^(GGML_RISCV_QBS_(LIFETIME|LIFETIME_SUMMARY|CROSS_OP|COMMAND|COVERAGE|EXEC)|QBS_CROSS_OP_|AKV_TOKEN_RUN_(BEGIN|EXIT)|LLAMA_GUEST_EXIT)' \
      "${log_file}" | tr -d '\r' > "${result_file}"
    printf 'AKV_MODEL_PROMPT_TOKENS=%s\n' "${prompt_token_count}" >> "${result_file}"
    python3 "${ara_root}/hardware/scripts/qbs/compare_activation_lifetime_runs.py" \
      "${log_file}" --output "$(dirname -- "${log_file}")/qbs_cross_operator_summary.json"
    return
  fi

  if [[ ${model_mode} == combined-fallback ]]; then
    coverage_line=$(grep -E 'GGML_RISCV_AKV_COVERAGE .*candidate_ops=[1-9][0-9]*' "${log_file}" | tail -n 1)
  else
    coverage_line=$(grep -E 'GGML_RISCV_AKV_COVERAGE .*executed_ops=[1-9][0-9]*' "${log_file}" | tail -n 1)
    grep -Eq 'executed_ops=[1-9][0-9]*' <<< "${coverage_line}"
  fi
  grep -Eq 'fallback_threading=0([[:space:]]|$)' <<< "${coverage_line}"
  if [[ ${model_mode} == combined || ${model_mode} == combined-fallback ]]; then
    grep -q 'AKV_TOKEN_RUN_EXIT=RVV:0' "${log_file}"
    grep -q 'AKV_TOKEN_RUN_EXIT=QBS_ONLY:0' "${log_file}"
    grep -q 'AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:0' "${log_file}"
    grep -Eq 'QBS_RVV_LOGITS_RECORDS=[1-9][0-9]*' "${log_file}"
    grep -Eq 'QBS_RVV_LOGITS_COMPARABLE_RECORDS=[1-9][0-9]*' "${log_file}"
    grep -Eq 'executed_v1=0([[:space:]]|$)' <<< "${coverage_line}"
    grep -Eq 'groups_v1=0([[:space:]]|$)' <<< "${coverage_line}"
    grep -Eq 'fallback_capability=0([[:space:]]|$)' <<< "${coverage_line}"
    grep -Eq 'fallback_feature=0([[:space:]]|$)' <<< "${coverage_line}"
    grep -Eq 'fallback_layout=0([[:space:]]|$)' <<< "${coverage_line}"
    grep -Eq 'fallback_mask=0([[:space:]]|$)' <<< "${coverage_line}"
    if [[ ${model_mode} == combined ]]; then
      grep -Eq 'executed_v2=[1-9][0-9]*' <<< "${coverage_line}"
      grep -Eq 'groups_v2=[1-9][0-9]*' <<< "${coverage_line}"
      grep -Eq 'kv_group_tokens=[1-9][0-9]*' <<< "${coverage_line}"
      grep -Eq 'attention_macs=[1-9][0-9]*' <<< "${coverage_line}"
    else
      grep -Eq 'executed_ops=0([[:space:]]|$)' <<< "${coverage_line}"
      grep -Eq 'executed_v2=0([[:space:]]|$)' <<< "${coverage_line}"
      grep -Eq 'groups_v2=0([[:space:]]|$)' <<< "${coverage_line}"
      grep -Eq 'kv_group_tokens=0([[:space:]]|$)' <<< "${coverage_line}"
      grep -Eq 'attention_macs=0([[:space:]]|$)' <<< "${coverage_line}"
    fi

    mapfile -t qbs_profiles < <(
      sed -n 's/^GGML_RISCV_QBS_COVERAGE type=\([^[:space:]]\+\) .*/\1/p' \
        "${log_file}" | sort -u
    )
    (( ${#qbs_profiles[@]} > 0 ))
    for profile in "${qbs_profiles[@]}"; do
      local qbs_coverage
      local qbs_exec
      local candidate_tensors
      local selected_tensors
      local candidate_elements
      local selected_elements

      qbs_coverage=$(grep -E "GGML_RISCV_QBS_COVERAGE type=${profile} " "${log_file}" | tail -n 1)
      qbs_exec=$(grep -E "GGML_RISCV_QBS_EXEC type=${profile} " "${log_file}" | tail -n 1)
      candidate_tensors=$(sed -n 's/.*candidate_tensors=\([0-9][0-9]*\).*/\1/p' <<< "${qbs_coverage}")
      selected_tensors=$(sed -n 's/.*selected_tensors=\([0-9][0-9]*\).*/\1/p' <<< "${qbs_coverage}")
      candidate_elements=$(sed -n 's/.*candidate_elements=\([0-9][0-9]*\).*/\1/p' <<< "${qbs_coverage}")
      selected_elements=$(sed -n 's/.*selected_elements=\([0-9][0-9]*\).*/\1/p' <<< "${qbs_coverage}")
      [[ ${candidate_tensors} =~ ^[1-9][0-9]*$ && ${candidate_tensors} == "${selected_tensors}" ]]
      [[ ${candidate_elements} =~ ^[1-9][0-9]*$ && ${candidate_elements} == "${selected_elements}" ]]
      grep -Eq 'fallback_runtime=0([[:space:]]|$)' <<< "${qbs_coverage}"
      grep -Eq 'fallback_format_filter=0([[:space:]]|$)' <<< "${qbs_coverage}"
      grep -Eq 'fallback_capability=0([[:space:]]|$)' <<< "${qbs_coverage}"
      grep -Eq 'fallback_dimensions=0([[:space:]]|$)' <<< "${qbs_coverage}"
      grep -Eq 'fallback_shape=0([[:space:]]|$)' <<< "${qbs_coverage}"
      grep -Eq 'fallback_layout=0([[:space:]]|$)' <<< "${qbs_coverage}"
      grep -Eq 'fallback_profile=0([[:space:]]|$)' <<< "${qbs_coverage}"
      grep -Eq 'fallback_dispatch=0([[:space:]]|$)' <<< "${qbs_coverage}"
      grep -Eq 'native_qbexec=[1-9][0-9]*' <<< "${qbs_exec}"
      grep -Eq 'emulated_commands=0([[:space:]]|$)' <<< "${qbs_exec}"
      grep -Eq 'command_dot_elements=[1-9][0-9]*' <<< "${qbs_exec}"
    done

    candidate_ops=$(sed -n 's/.*candidate_ops=\([0-9][0-9]*\).*/\1/p' <<< "${coverage_line}")
    executed_ops=$(sed -n 's/.*executed_ops=\([0-9][0-9]*\).*/\1/p' <<< "${coverage_line}")
    accounted_ops=$(awk -v line="${coverage_line}" 'BEGIN {
      total = 0;
      count = split(line, fields, " ");
      for (i = 1; i <= count; ++i) {
        if (fields[i] ~ /^fallback_/) {
          split(fields[i], pair, "=");
          total += pair[2] + 0;
        }
      }
      print total;
    }')
    [[ ${candidate_ops} =~ ^[1-9][0-9]*$ && ${executed_ops} =~ ^[0-9][0-9]*$ ]]
    if [[ ${model_mode} == combined ]]; then
      [[ ${executed_ops} =~ ^[1-9][0-9]*$ ]]
    fi
    (( candidate_ops == executed_ops + accounted_ops ))
    if [[ ${require_prefill} == 1 ]]; then
      grep -Eq 'executed_prefill=[1-9][0-9]*' <<< "${coverage_line}"
      grep -Eq 'prefill_query_tokens=[1-9][0-9]*' <<< "${coverage_line}"
      grep -Eq 'prefill_attention_pairs=[1-9][0-9]*' <<< "${coverage_line}"
      grep -Eq 'fallback_size=0([[:space:]]|$)' <<< "${coverage_line}"
      grep -Eq '^GGML_RISCV_AKV_EXEC mode=prefill ' "${log_file}"
    fi
    if [[ ${model_mode} == combined-fallback ]]; then
      local fallback_shape
      fallback_shape=$(sed -n 's/.*fallback_shape=\([0-9][0-9]*\).*/\1/p' <<< "${coverage_line}")
      (( candidate_ops == fallback_shape ))
    fi
  else
    grep -Eq 'executed_v1=[1-9][0-9]*' <<< "${coverage_line}"
    grep -Eq 'executed_v2=0([[:space:]]|$)' <<< "${coverage_line}"
  fi
  grep -Eq 'AKV_LOGITS_RECORDS=[1-9][0-9]*' "${log_file}"
  grep -Eq 'AKV_LOGITS_COMPARABLE_RECORDS=[1-9][0-9]*' "${log_file}"
  grep -q 'AKV_LOGITS_TOP1_EQUAL=1' "${log_file}"
  grep -q 'AKV_TOKEN_OUTPUT_EQUAL=1' "${log_file}"
  grep -q 'LLAMA_GUEST_EXIT=0' "${log_file}"

  if [[ ${model_mode} == combined || ${model_mode} == combined-fallback ]]; then
    for prefix in QBS_RVV AKV; do
      local records
      local comparable_records
      records=$(metric_value "${log_file}" "${prefix}_LOGITS_RECORDS")
      comparable_records=$(metric_value "${log_file}" "${prefix}_LOGITS_COMPARABLE_RECORDS")
      [[ ${records} =~ ^[1-9][0-9]*$ && ${records} == "${comparable_records}" ]]
    done
    require_metric_le "${log_file}" AKV_LOGITS_MAX_KL \
      "${model_max_kl_tolerance}"
    require_metric_ge "${log_file}" AKV_LOGITS_MIN_COSINE \
      "${model_min_cosine_tolerance}"
    require_metric_ge "${log_file}" AKV_LOGITS_MIN_TOP5_OVERLAP \
      "${model_min_top5_overlap_tolerance}"
    [[ $(metric_value "${log_file}" MODEL_NUMERICAL_CONTRACT) == \
       decision-preserving-v1 ]]
  fi
  if [[ ${model_mode} != combined ]]; then
    max_abs=$(metric_value "${log_file}" AKV_LOGITS_MAX_ABS)
    grep -Eq "${number_re}" <<< "${max_abs}"
    awk -v value="${max_abs}" -v tolerance="${max_abs_tolerance}" \
      'BEGIN { exit !((value + 0.0) <= (tolerance + 0.0)) }'
  fi

  grep -E '^(GGML_RISCV_(QBS_(COVERAGE|EXEC)|AKV_(COVERAGE|EXEC))|QBS_RVV_|AKV_LOGITS_|MODEL_(LOGITS|NUMERICAL)|AKV_TOKEN_(RUN_EXIT|OUTPUT_EQUAL)|LLAMA_GUEST_EXIT)' \
    "${log_file}" | tr -d '\r' > "${result_file}"
  printf 'AKV_MODEL_PROMPT_TOKENS=%s\n' "${prompt_token_count}" >> "${result_file}"
}

write_manifest() {
  local manifest_file=$1
  local ara_revision
  local llama_revision

  ara_revision=$(git -C "${ara_root}" rev-parse HEAD 2>/dev/null || printf unknown)
  llama_revision=$(git -C "${llama_src}" rev-parse HEAD 2>/dev/null || printf unknown)
  {
    printf 'MODEL_MODE=%s\n' "${model_mode}"
    printf 'ARA_REVISION=%s\n' "${ara_revision}"
    printf 'LLAMA_REVISION=%s\n' "${llama_revision}"
    printf 'LLAMA_BINARY=%s\n' "${llama_binary}"
    printf 'LLAMA_BINARY_SHA256=%s\n' "$(sha256sum "${llama_binary}" | awk '{print $1}')"
    printf 'QEMU_BINARY=%s\n' "${qemu_binary}"
    printf 'QEMU_BINARY_SHA256=%s\n' "$(sha256sum "${qemu_binary}" | awk '{print $1}')"
    printf 'QEMU_CPU=%s\n' "${qemu_cpu}"
    printf 'QEMU_MEMORY=%s\n' "${qemu_memory}"
    printf 'MODEL_DISK=%s\n' "${model_disk}"
    printf 'MODEL_DISK_SHA256=%s\n' "$(sha256sum "${model_disk}" | awk '{print $1}')"
    printf 'MODEL_GUEST_PATH=%s\n' "${model_guest_path}"
    printf 'MODEL_TOKENS=%s\n' "${model_tokens}"
    printf 'MODEL_PROMPT=%s\n' "${model_prompt}"
    printf 'REQUIRE_PREFILL=%s\n' "${require_prefill}"
    printf 'LOGITS_MAX_ABS_TOLERANCE=%s\n' "${max_abs_tolerance}"
    printf 'MODEL_LOGITS_MAX_KL_TOLERANCE=%s\n' "${model_max_kl_tolerance}"
    printf 'MODEL_LOGITS_MIN_COSINE_TOLERANCE=%s\n' "${model_min_cosine_tolerance}"
    printf 'MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE=%s\n' \
      "${model_min_top5_overlap_tolerance}"
    if [[ ${model_mode} == combined || ${model_mode} == combined-fallback ]]; then
      printf 'MODEL_NUMERICAL_CONTRACT=decision-preserving-v1\n'
    else
      printf 'MODEL_NUMERICAL_CONTRACT=exact-max-abs-v1\n'
    fi
  } > "${manifest_file}"
}

case ${model_mode} in
  akv-v1|combined|combined-fallback|qbs-lifetime) ;;
  *)
    printf 'invalid AKV_MODEL_MODE: %s (expected akv-v1, combined, combined-fallback, or qbs-lifetime)\n' "${model_mode}" >&2
    exit 2
    ;;
esac
[[ ${require_prefill} == 0 || ${require_prefill} == 1 ]] || {
  printf 'invalid AKV_REQUIRE_PREFILL: %s (expected 0 or 1)\n' "${require_prefill}" >&2
  exit 2
}
if [[ ${require_prefill} == 1 && ${model_mode} != combined ]]; then
  printf 'AKV_REQUIRE_PREFILL=1 requires AKV_MODEL_MODE=combined\n' >&2
  exit 2
fi
[[ ${model_guest_path} =~ ^/[A-Za-z0-9._/-]+$ ]] || {
  printf 'invalid AKV_MODEL_GUEST_PATH: %s\n' "${model_guest_path}" >&2
  exit 2
}
[[ ${model_tokens} =~ ^[1-9][0-9]*$ ]] || {
  printf 'invalid AKV_MODEL_TOKENS: %s\n' "${model_tokens}" >&2
  exit 2
}
[[ ${qemu_memory} =~ ^[1-9][0-9]*[GM]$ ]] || {
  printf 'invalid AKV_QEMU_MEMORY: %s (expected positive G/M size, for example 4G)\n' \
    "${qemu_memory}" >&2
  exit 2
}
[[ ${model_prompt} != *$'\n'* && ${model_prompt} != *$'\r'* ]] || {
  printf 'AKV_MODEL_PROMPT must be one line\n' >&2
  exit 2
}
[[ ${model_prompt} != *'"'* && ${model_prompt} != *'\'* ]] || {
  printf 'AKV_MODEL_PROMPT cannot contain a quote or backslash\n' >&2
  exit 2
}

if [[ ${1:-} == --check-log ]]; then
  if [[ $# -ne 2 ]]; then
    printf 'usage: %s --check-log QEMU_LOG\n' "$0" >&2
    exit 2
  fi
  log_file=$2
  result_file=$(dirname -- "${log_file}")/result.txt
  test -s "${log_file}"
  validate_log "${log_file}" "${result_file}"
  if [[ ${model_mode} == combined || ${model_mode} == combined-fallback ]]; then
    summary_args=("${log_file}")
    if [[ ${model_guest_path} != "${default_model_guest_path}" || ${require_prefill} == 1 ]]; then
      summary_args+=(--dynamic-only)
    fi
    "${ara_root}/hardware/scripts/akv/summarize-model-closure.py" \
      "${summary_args[@]}"
  fi
  printf 'AKV model log passed: %s\n' "${log_file}"
  exit 0
elif [[ $# -ne 0 ]]; then
  printf 'usage: %s [--check-log QEMU_LOG]\n' "$0" >&2
  exit 2
fi

platform=${AKV_QEMU_PLATFORM:-/home/wangwy/llama/platforms/cva6-qemu}
llama_src=${AKV_LLAMA_SRC:-/home/wangwy/llama/llama.cpp}
llama_binary=${AKV_LLAMA_BINARY:-${llama_src}/build-rv64-cva6-akv-static/bin/llama-simple}
model_disk=${AKV_MODEL_DISK:-${platform}/images/qwen2.5-q4km-capture.ext4}
timestamp=$(date +%Y%m%d_%H%M%S)
run_dir=${AKV_RUN_DIR:-${ara_root}/hardware/akv_jobs/qemu_model_${model_mode}_${timestamp}}

source "${platform}/env.sh"

if [[ ${model_mode} == combined || ${model_mode} == combined-fallback ||
      ${model_mode} == qbs-lifetime ]]; then
  qemu_binary=${AKV_QEMU_BINARY:-${platform}/build/qemu-10.2.0-build/qemu-system-riscv64}
  qemu_cpu=${AKV_QEMU_CPU:-rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true}
else
  qemu_binary=${AKV_QEMU_BINARY:-${CROSS_BIN}/qemu-system-riscv64}
  qemu_cpu=${AKV_QEMU_CPU:-rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true}
fi

test -x "${llama_binary}"
test -s "${model_disk}"
test -x "${qemu_binary}"
mkdir -p "${run_dir}"

init_binary="${run_dir}/akv-token-init"
initramfs="${run_dir}/akv-token-check.cpio"
binary_disk="${run_dir}/llama-akv-token.ext4"
initramfs_list="${run_dir}/initramfs.list"
log_file="${run_dir}/qemu.log"
result_file="${run_dir}/result.txt"
manifest_file="${run_dir}/manifest.txt"

init_defines=()
if [[ ${model_mode} == combined || ${model_mode} == combined-fallback ]]; then
  init_defines+=(-DAKV_MODEL_QBS_AKV_V2=1)
elif [[ ${model_mode} == qbs-lifetime ]]; then
  init_defines+=(-DAKV_MODEL_QBS_LIFETIME=1)
fi

"${CROSS_BIN}/riscv64-linux-gcc" \
  -march=rv64gc -mabi=lp64d -O2 -static \
  "-DAKV_LOGITS_MAX_ABS_TOLERANCE=${max_abs_tolerance}" \
  "-DAKV_MODEL_LOGITS_MAX_KL_TOLERANCE=${model_max_kl_tolerance}" \
  "-DAKV_MODEL_LOGITS_MIN_COSINE_TOLERANCE=${model_min_cosine_tolerance}" \
  "-DAKV_MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE=${model_min_top5_overlap_tolerance}" \
  "-DAKV_MODEL_GUEST_PATH=\"${model_guest_path}\"" \
  "-DAKV_MODEL_TOKENS=\"${model_tokens}\"" \
  "-DAKV_MODEL_PROMPT=\"${model_prompt}\"" \
  "${init_defines[@]}" \
  "${ara_root}/hardware/scripts/akv/akv-token-init.c" \
  -lm -o "${init_binary}"

truncate -s 128M "${binary_disk}"
mkfs.ext4 -q -F "${binary_disk}"
debugfs -w -R "write ${llama_binary} /llama-simple" "${binary_disk}" >/dev/null 2>&1
debugfs -w -R "set_inode_field /llama-simple mode 0100755" "${binary_disk}" >/dev/null 2>&1

printf '%s\n' \
  'dir /dev 755 0 0' \
  'nod /dev/console 600 0 0 c 5 1' \
  'dir /run 755 0 0' \
  'dir /model 755 0 0' \
  "file /init ${init_binary} 755 0 0" > "${initramfs_list}"

gen_init_cpio=${AKV_GEN_INIT_CPIO:-}
if [[ -z ${gen_init_cpio} ]]; then
  gen_init_cpio=$(find "${CVA6_SDK}/buildroot/output/build" \
    -path '*/usr/gen_init_cpio' -type f -print -quit 2>/dev/null || true)
fi
if [[ -z ${gen_init_cpio} ]]; then
  gen_init_cpio=$(command -v gen_init_cpio || true)
fi
if [[ ! -x ${gen_init_cpio} ]]; then
  printf 'gen_init_cpio not found; set AKV_GEN_INIT_CPIO to an executable Linux gen_init_cpio\n' >&2
  exit 2
fi
"${gen_init_cpio}" "${initramfs_list}" > "${initramfs}"

write_manifest "${manifest_file}"

"${qemu_binary}" \
  -M virt \
  -cpu "${qemu_cpu}" \
  -smp 1 \
  -m "${qemu_memory}" \
  -display none \
  -monitor none \
  -serial stdio \
  -bios "${QEMU_IMAGES}/fw_dynamic.bin" \
  -initrd "${initramfs}" \
  -kernel "${QEMU_IMAGES}/Image" \
  -drive "file=${binary_disk},if=virtio,format=raw,readonly=on" \
  -drive "file=${model_disk},if=virtio,format=raw,readonly=on" \
  -append "console=ttyS0 rdinit=/init" \
  2>&1 | tee "${log_file}"

validate_log "${log_file}" "${result_file}"
if [[ ${model_mode} == combined || ${model_mode} == combined-fallback ]]; then
  summary_args=("${log_file}")
  if [[ ${model_guest_path} != "${default_model_guest_path}" || ${require_prefill} == 1 ]]; then
    summary_args+=(--dynamic-only)
  fi
  "${ara_root}/hardware/scripts/akv/summarize-model-closure.py" \
    "${summary_args[@]}"
fi
ln -sfn "${run_dir}" \
  "${ara_root}/hardware/akv_jobs/qemu_model_${model_mode}_latest"
printf 'AKV model check passed: %s\n' "${run_dir}"
