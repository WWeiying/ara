#!/bin/sh
# Run manually only after the FPGA owner grants an idle-board window.
set -eu
if [ "$#" -ne 7 ]; then
    echo "Usage: $0 BUNDLE MODEL PROMPT HISTORY OUT plain|metadata|timed STEPS" >&2
    exit 2
fi
bundle=$1 model=$2 prompt=$3 history=$4 out=$5 mode=$6 steps=$7
case "$mode" in
    plain) binary=$bundle/stage1-plain; active=0 ;;
    metadata) binary=$bundle/stage1-probe; active=0 ;;
    timed) binary=$bundle/stage1-probe; active=1 ;;
    *) exit 2 ;;
esac
case "$steps" in ''|*[!0-9]*) exit 2 ;; esac
test "$steps" -ge 1 && test "$steps" -le 32
test -x "$binary" && test -f "$model" && test -f "$prompt" && test -f "$history"
test ! -e "$out"
mkdir "$out"
sha256sum "$binary" "$prompt" "$history" > "$out/identity.txt"
set -- env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C \
 STAGE1_NODE_TIMING="$active" \
 GGML_RISCV_QBS=1 GGML_RISCV_AKV=1 \
 GGML_RISCV_QBS_TRACE=0 GGML_RISCV_AKV_TRACE=0 \
 GGML_RISCV_QBS_EMULATE=0 GGML_RISCV_AKV_EMULATE=0 GGML_RISCV_AKV_PORTABLE=0 \
 GGML_RISCV_QBS_M4_PREPARE=1 GGML_RISCV_QBS_M4_PACKED=1 \
 GGML_RISCV_QBS_M4_PARALLEL_SUMS=1 GGML_RISCV_QBS_M4_CACHE=1 \
 GGML_RISCV_QBS_CROSS_OP_CONTEXT=1 GGML_RISCV_QBS_ACTIVATION_CONTEXT=1 \
 GGML_RISCV_QBS_WIDE_M=0 GGML_RISCV_QBS_TRACE_M4_PREPARE=0 \
 GGML_RISCV_QBS_TRACE_LIFETIME=0 GGML_RISCV_QBS_TRACE_CALLS=0 \
 GGML_RISCV_AKV_QUANT_KV=0 GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY=0 \
 GGML_RISCV_AKV_REGISTER_PV=0 GGML_RISCV_AKV_QUANT_PREFILL=0 GGML_RISCV_AKV_GROUPED_PV=0
printf '%s\n' "$@" > "$out/environment.txt"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/started_at"
rc=0
"$@" "$binary" "$model" "$prompt" "$history" "$out" literal qbs_akv "$steps" \
    > "$out/stdout.log" 2> "$out/stderr.log" || rc=$?
printf '%s\n' "$rc" > "$out/exit_code"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/finished_at"
exit "$rc"
