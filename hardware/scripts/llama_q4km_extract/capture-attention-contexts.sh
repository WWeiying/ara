#!/usr/bin/env bash
set -euo pipefail

llama_root=${LLAMA_CAPTURE_SOURCE:-/home/wangwy/llama/llama-q4km-extract}
capture_binary=${LLAMA_CAPTURE_BINARY:-/home/wangwy/llama/platforms/cva6-qemu/build/llama-format-capture-host/bin/llama-completion}
tokenizer=${LLAMA_TOKENIZER:-/home/wangwy/llama/platforms/cva6-qemu/build/llama-format-capture-host/bin/llama-tokenize}
model=${LLAMA_MODEL:-/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}
capture_base=${LLAMA_CAPTURE_BASE:-/home/wangwy/llama/captures}
capture_timeout=${LLAMA_CAPTURE_TIMEOUT:-600}
normalizer=$(cd -- "$(dirname -- "$0")" && pwd)/normalize-attention-capture.py
stamp=$(date +%Y%m%d_%H%M%S)
set_root=${LLAMA_ATTN_CAPTURE_SET:-${capture_base}/qwen2.5-1.5b-q4_k_m-attention-contexts-${stamp}}
base_prompt='Explain why low-bit vector inference benefits from packed arithmetic and data reuse.'
if [[ $# -gt 0 ]]; then
  targets=("$@")
else
  targets=(16 128 256)
fi

for required in "${capture_binary}" "${tokenizer}" "${model}"; do
  if [[ ! -f ${required} ]]; then
    echo "missing required file: ${required}" >&2
    exit 1
  fi
done
if [[ ! -x ${capture_binary} || ! -x ${tokenizer} ]]; then
  echo "capture binary and tokenizer must be executable" >&2
  exit 1
fi

make_prompt() {
  local target=$1
  local repeats suffix prompt=""
  case ${target} in
    16) repeats=1; suffix="" ;;
    128) repeats=9; suffix="" ;;
    256) repeats=18; suffix=" attention attention" ;;
    *) echo "unsupported effective KV length: ${target}" >&2; return 1 ;;
  esac
  for ((index = 0; index < repeats; ++index)); do
    prompt+="${prompt:+ }${base_prompt}"
  done
  printf '%s%s' "${prompt}" "${suffix}"
}

source_commit=$(git -C "${llama_root}" rev-parse HEAD)
source_dirty=false
if [[ -n $(git -C "${llama_root}" status --porcelain) ]]; then
  source_dirty=true
fi
source_sha=$(sha256sum "${llama_root}/common/q4km-capture.cpp" | cut -d' ' -f1)
binary_sha=$(sha256sum "${capture_binary}" | cut -d' ' -f1)
model_sha=$(sha256sum "${model}" | cut -d' ' -f1)
mkdir -p "${set_root}"

for target in "${targets[@]}"; do
  prompt=$(make_prompt "${target}")
  expected_tokens=$((target - 1))
  actual_tokens=$("${tokenizer}" -m "${model}" -p "${prompt}" --show-count --ids 2>&1 |
    sed -n 's/^Total number of tokens: *//p' | tail -1)
  if [[ ${actual_tokens} != "${expected_tokens}" ]]; then
    echo "prompt token mismatch for KV ${target}: expected ${expected_tokens}, got ${actual_tokens:-none}" >&2
    exit 1
  fi

  capture_root=${set_root}/kv${target}
  block=${capture_root}/decode/block
  context_size=256
  if [[ ${target} -eq 256 ]]; then
    context_size=512
  fi
  mkdir -p "${capture_root}"
  printf '%s\n' "${prompt}" > "${capture_root}/prompt.txt"
  printf 'effective_kv=%s\nprompt_tokens=%s\nmodel=%s\nmodel_sha256=%s\n' \
    "${target}" "${actual_tokens}" "${model}" "${model_sha}" > "${capture_root}/run.conf"
  printf 'capture_binary=%s\ncapture_binary_sha256=%s\nsource_commit=%s\nsource_dirty=%s\ncapture_source_sha256=%s\n' \
    "${capture_binary}" "${binary_sha}" "${source_commit}" "${source_dirty}" "${source_sha}" >> "${capture_root}/run.conf"
  printf 'runtime_context=%s\nnormalized_kv_capacity=256\n' "${context_size}" >> "${capture_root}/run.conf"

  LLAMA_Q4KM_CAPTURE_DIR=${capture_root} \
  LLAMA_Q4KM_CAPTURE_LAYER=0 \
  LLAMA_Q4KM_CAPTURE_PHASE=decode \
  LLAMA_Q4KM_CAPTURE_PROFILE=attention_core \
    timeout --foreground "${capture_timeout}" "${capture_binary}" \
      -m "${model}" -p "${prompt}" -n 2 -c "${context_size}" -t 16 -tb 16 \
      -no-cnv --load-mode mmap --no-warmup --no-display-prompt \
      --seed 1 --temp 0 > "${capture_root}/completion.log" 2>&1

  grep -q 'phase decode, profile attention_core' "${capture_root}/completion.log"
  for stem in attn_q_input-0 attn_k_input-0 attn_v_input-0 attn_mask_input-0 kqv_out-0; do
    test -s "${block}/${stem}.json"
    test -s "${block}/${stem}.bin"
  done
  "${normalizer}" "${capture_root}" --capacity 256
  jq -e '.type == "f32" and .shape == [128,1,12,1] and .nbytes == 6144' "${block}/attn_q_input-0.json" >/dev/null
  jq -e '.type == "f16" and .shape == [128,256,2,1] and .nbytes == 131072' "${block}/attn_k_input-0.json" >/dev/null
  jq -e '.type == "f16" and .shape == [128,256,2,1] and .nbytes == 131072' "${block}/attn_v_input-0.json" >/dev/null
  jq -e '.type == "f16" and .shape == [256,1,1,1] and .nbytes == 512' "${block}/attn_mask_input-0.json" >/dev/null
  jq -e '.type == "f32" and .shape == [1536,1,1,1] and .nbytes == 6144' "${block}/kqv_out-0.json" >/dev/null

  read -r active masked other < <(
    od -An -v -t x2 "${block}/attn_mask_input-0.bin" |
      awk '{for(i=1;i<=NF;i++){if($i=="0000") a++; else if($i=="fc00") m++; else o++}}
           END{printf "%d %d %d\n",a,m,o}'
  )
  if [[ ${active} -ne ${target} || ${masked} -ne $((256 - target)) || ${other} -ne 0 ]]; then
    echo "mask mismatch for KV ${target}: active=${active} masked=${masked} other=${other}" >&2
    exit 1
  fi

  case_dir=${capture_root}/replay/cases/operator/decode/attention_core
  mkdir -p "${case_dir}"
  printf '%s\n' \
    '{' \
    '  "kind": "attention_core",' \
    '  "input_a": "../../../../../decode/block/attn_q_input-0.json",' \
    '  "key": "../../../../../decode/block/attn_k_input-0.json",' \
    '  "value": "../../../../../decode/block/attn_v_input-0.json",' \
    '  "mask": "../../../../../decode/block/attn_mask_input-0.json",' \
    '  "golden": "../../../../../decode/block/kqv_out-0.json",' \
    '  "scale": 0.08838834764831843,' \
    '  "max_bias": 0.0,' \
    '  "v_transposed": false,' \
    '  "atol": 0.004,' \
    '  "rtol": 0.002' \
    '}' > "${case_dir}/case.json"
  mkdir -p "${capture_root}/replay"
  printf '%s\n' \
    '{' \
    '  "schema_version": 1,' \
    '  "model": "Qwen2.5-1.5B-Instruct-Q4_K_M",' \
    '  "source": "real host llama.cpp decode inference",' \
    "  \"effective_kv\": ${target}," \
    '  "cases": [' \
    '    {' \
    '      "id": "operator/decode/attention_core",' \
    '      "level": "operator-leaf",' \
    '      "kind": "attention_core",' \
    '      "path": "replay/cases/operator/decode/attention_core"' \
    '    }' \
    '  ]' \
    '}' > "${capture_root}/replay/manifest.json"
  (
    cd "${block}"
    sha256sum attn_q_input-0.bin attn_k_input-0.bin attn_v_input-0.bin \
      attn_mask_input-0.bin kqv_out-0.bin > "${capture_root}/tensor.sha256"
  )
  echo "captured effective KV ${target}: ${capture_root}"
done

if [[ ${#targets[@]} -eq 3 ]]; then
  ln -sfn "${set_root}" "${capture_base}/qwen2.5-1.5b-q4_k_m-attention-contexts-latest"
fi
echo "capture set: ${set_root}"
