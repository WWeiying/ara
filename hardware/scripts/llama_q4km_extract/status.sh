#!/usr/bin/env bash
set -euo pipefail

capture=/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m
pgrep -af 'qemu-system-riscv64.*q4kmdata' || true
if [[ -d ${capture} ]]; then
  find "${capture}" -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' | sort
else
  echo "No capture directory yet: ${capture}"
fi
