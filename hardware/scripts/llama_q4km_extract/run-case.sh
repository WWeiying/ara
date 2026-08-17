#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
root=${Q4KM_CAPTURE_ROOT:-/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m}

if [[ $# -eq 0 ]]; then
  exec "${script_dir}/cases.py" --root "${root}" list
fi

exec "${script_dir}/cases.py" --root "${root}" run "$1"
