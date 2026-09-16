#!/usr/bin/env bash
set -euo pipefail
root=/home/wangwy/openproject/ara_dsa
out=$(cd -- "$(dirname -- "$0")" && pwd)
capture=/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m
mkdir -p "$out/decode"
for entry in q4_K:1536:attn_q q6_K:8960:ffn_down; do
  IFS=: read -r profile k layer <<< "$entry"
  vectors="$out/decode/${profile}.vectors"
  "$root/verification/qbs/qbs_command_vectors" "$vectors" --real "$profile" \
    "$capture/decode/operators/blk_0_${layer}_weight" 1536 "$k" 0 1 0 32
  dir="$out/decode/${profile}"
  mkdir -p "$dir"
  (cd "$dir" && timeout 300 "$out/engine/simv" -l run.log +QBS_FUNCTIONAL_ONLY \
    +QBS_COMMAND_VECTOR_FILE="$vectors" > console.log 2>&1)
  grep -q 'QBS engine PASS: 1 functional cases' "$dir/run.log"
  ! grep -Eq 'Fatal:|Error:' "$dir/run.log"
  grep -E '^QBS (end-to-end|traffic|phase)' "$dir/run.log"
done
