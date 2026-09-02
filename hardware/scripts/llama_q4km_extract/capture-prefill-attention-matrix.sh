#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
capture_binary=${LLAMA_CAPTURE_BINARY:-/home/wangwy/llama/platforms/cva6-qemu/build/llama-format-capture-host/bin/llama-completion}
tokenizer=${LLAMA_TOKENIZER:-/home/wangwy/llama/platforms/cva6-qemu/build/llama-format-capture-host/bin/llama-tokenize}
model=${LLAMA_MODEL:-/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}
capture_timeout=${LLAMA_CAPTURE_TIMEOUT:-900}
target_tokens=${2:-3072}
batch_tokens=${3:-512}
output_root=${1:-/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-prefill-m${target_tokens}-$(date +%Y%m%d)}
base_prompt='Explain why low-bit vector inference benefits from packed arithmetic and data reuse.'

if [[ ! ${target_tokens} =~ ^[1-9][0-9]*$ ||
      ! ${batch_tokens} =~ ^[1-9][0-9]*$ ]]; then
  echo "target and batch token counts must be positive integers" >&2
  exit 2
fi
if (( target_tokens < 15 || batch_tokens > target_tokens )); then
  echo "require target_tokens >= 15 and batch_tokens <= target_tokens" >&2
  exit 2
fi
if [[ -e ${output_root} ]]; then
  echo "output root already exists: ${output_root}" >&2
  exit 1
fi
for required in "${capture_binary}" "${tokenizer}" "${model}"; do
  if [[ ! -f ${required} ]]; then
    echo "missing required file: ${required}" >&2
    exit 1
  fi
done

prompt=${base_prompt}
for ((index = 15; index < target_tokens; ++index)); do
  prompt+=' a'
done
actual_tokens=$("${tokenizer}" -m "${model}" -p "${prompt}" --show-count --ids 2>&1 |
  sed -n 's/^Total number of tokens: *//p' | tail -n 1)
if [[ ${actual_tokens} != "${target_tokens}" ]]; then
  echo "prompt token mismatch: expected ${target_tokens}, got ${actual_tokens:-none}" >&2
  exit 1
fi

context_tokens=$((target_tokens + batch_tokens))
mkdir -p "${output_root}"
printf '%s\n' "${prompt}" > "${output_root}/prompt.txt"
printf 'target_tokens=%s\nbatch_tokens=%s\ncontext_tokens=%s\nmodel=%s\n' \
  "${target_tokens}" "${batch_tokens}" "${context_tokens}" "${model}" \
  > "${output_root}/run.conf"
printf 'model_sha256=%s\ncapture_binary=%s\ncapture_binary_sha256=%s\n' \
  "$(sha256sum "${model}" | awk '{print $1}')" \
  "${capture_binary}" "$(sha256sum "${capture_binary}" | awk '{print $1}')" \
  >> "${output_root}/run.conf"

LLAMA_Q4KM_CAPTURE_DIR=${output_root} \
LLAMA_Q4KM_CAPTURE_LAYER=0 \
LLAMA_Q4KM_CAPTURE_PHASE=prefill \
LLAMA_Q4KM_CAPTURE_PROFILE=attention_core \
LLAMA_Q4KM_CAPTURE_PREFILL_CHUNK=all \
  timeout --foreground "${capture_timeout}" "${capture_binary}" \
    -m "${model}" -p "${prompt}" -n 1 -c "${context_tokens}" \
    -b "${batch_tokens}" -ub "${batch_tokens}" -t 16 -tb 16 \
    -no-cnv -lm mmap --no-warmup --no-display-prompt \
    --seed 1 --temp 0 > "${output_root}/completion.log" 2>&1

python3 "${script_dir}/package_prefill_attention_capture.py" "${output_root}" \
  > "${output_root}/package.log"
summary=${output_root}/replay/prefill_package_summary.json
expected_chunks=$(((target_tokens + batch_tokens - 1) / batch_tokens))
jq -e --argjson target "${target_tokens}" --argjson chunks "${expected_chunks}" '
  . as $root |
  .status == "PASS" and
  .chunk_count == $chunks and
  ([.chunks[].M_query_tokens] | add) == $target and
  .chunks[0].P_past_tokens == 0 and
  all(range(1; $root.chunk_count);
      . as $i |
      $root.chunks[$i].P_past_tokens ==
      ($root.chunks[$i - 1].P_past_tokens +
       $root.chunks[$i - 1].M_query_tokens))
' "${summary}" >/dev/null

printf 'capture_manifest_sha256=%s\npackage_summary_sha256=%s\n' \
  "$(sha256sum "${output_root}/replay/manifest.json" | awk '{print $1}')" \
  "$(sha256sum "${summary}" | awk '{print $1}')" >> "${output_root}/run.conf"
echo "captured real Prefill matrix source: ${output_root}"
