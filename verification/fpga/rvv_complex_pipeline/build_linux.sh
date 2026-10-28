#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
cross=${RISCV_CROSS:-riscv64-buildroot-linux-gnu-}
out=${1:?usage: build_linux.sh OUTPUT_ELF}
mkdir -p "$(dirname -- "$out")"
"${cross}gcc" -O2 -march=rv64gcv_zfh_zvfh -mabi=lp64d \
  -mcmodel=medany -msmall-data-limit=0 -fno-pic -fno-pie \
  -fno-tree-vectorize -fno-tree-slp-vectorize -fno-builtin \
  -fno-stack-protector -nostdlib -static -no-pie \
  -Wl,-e,_start -Wl,--build-id=none -include stdio.h \
  -I"$root/apps/riscv-tests/env" \
  -I"$root/apps/riscv-tests/isa/macros/vector" \
  -I"$root/apps/riscv-tests/isa/macros/scalar" \
  "$root/apps/riscv-tests/isa/rv64uv/rvv_complex_pipeline.c" \
  "$(dirname -- "$0")/linux_runtime.c" -lgcc -o "$out"
