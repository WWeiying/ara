#!/bin/sh
# Run only on the reviewed board image, after staging this bundle.
set -eu

if [ "$#" -ne 5 ]; then
    echo "Usage: $0 accepted|generic|auto MODEL PROMPT_FILE TOKENS NEW_OUTPUT_DIR" >&2
    exit 2
fi
arm=$1
model=$2
prompt_file=$3
tokens=$4
out=$5
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$arm" in
    accepted) binary="$root/llama-f16-accepted" ;;
    generic|auto) binary="$root/llama-f16-unified" ;;
    *) echo "Unknown arm: $arm" >&2; exit 2 ;;
esac
case "$tokens" in ''|*[!0-9]*|0) echo "Invalid token limit" >&2; exit 2 ;; esac
test -s "$model"
test -s "$prompt_file"
test -x "$binary"
test ! -e "$out"
(cd "$root" && sha256sum -c SHA256SUMS)
mkdir -- "$out"
out=$(CDPATH= cd -- "$out" && pwd)
model=$(readlink -f -- "$model")
prompt_file=$(readlink -f -- "$prompt_file")
# The suffix prevents command substitution from removing prompt newlines.
prompt=$(cat -- "$prompt_file"; printf '.')
prompt=${prompt%.}
printf 'arm=%s\nbinary=%s\nmodel=%s\nprompt_file=%s\ntokens=%s\n' \
    "$arm" "$binary" "$model" "$prompt_file" "$tokens" > "$out/identity.txt"
sha256sum "$binary" "$prompt_file" >> "$out/identity.txt"

set -- env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C \
    GGML_RISCV_QBS=1 GGML_RISCV_AKV=1 \
    GGML_RISCV_QBS_TRACE=1 GGML_RISCV_AKV_TRACE=1 \
    GGML_RISCV_QBS_EMULATE=0 GGML_RISCV_AKV_EMULATE=0 GGML_RISCV_AKV_PORTABLE=0 \
    GGML_RISCV_QBS_M4_PREPARE=1 GGML_RISCV_QBS_M4_PACKED=1 \
    GGML_RISCV_QBS_M4_PARALLEL_SUMS=1 GGML_RISCV_QBS_M4_CACHE=1 \
    GGML_RISCV_QBS_CROSS_OP_CONTEXT=1 GGML_RISCV_QBS_ACTIVATION_CONTEXT=1 \
    GGML_RISCV_QBS_WIDE_M=0 GGML_RISCV_QBS_TRACE_M4_PREPARE=0 \
    GGML_RISCV_QBS_TRACE_LIFETIME=0 GGML_RISCV_QBS_TRACE_CALLS=0 \
    GGML_RISCV_AKV_QUANT_KV=0 GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY=0 \
    GGML_RISCV_AKV_REGISTER_PV=0 GGML_RISCV_AKV_QUANT_PREFILL=0 GGML_RISCV_AKV_GROUPED_PV=0 \
    LLAMA_SIMPLE_LOGITS_FILE="$out/logits.bin"
if [ "$arm" = generic ]; then
    set -- "$@" AKV_PAIR_HEADS=0
fi
# The auto arm deliberately leaves AKV_PAIR_HEADS absent, not "1".
printf '%s\n' "$@" > "$out/environment.txt"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/started_at"
status=0
"$@" "$binary" -m "$model" -ngl 0 -t 1 -n "$tokens" "$prompt" \
    > "$out/stdout.log" 2> "$out/stderr.log" || status=$?
printf '%s\n' "$status" > "$out/exit_code"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/finished_at"
if [ "$status" -eq 0 ]; then
    test -s "$out/logits.bin"
fi
exit "$status"
