#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_dir}/../../.." && pwd)
build_dir=${QBS_CONTRACT_BUILD_DIR:-${script_dir}/build/contract-test}
cc=${QBS_RISCV_CC:-/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc}
qemu=${QBS_QEMU:?set QBS_QEMU to the patched qemu-system-riscv64 binary}
qemu_cpu=${QBS_QEMU_CPU:-rv64,v=true,vlen=1024,elen=64,xaraqbs=true}

mkdir -p "${build_dir}"
"${cc}" -march=rv64gcv_zicsr -mabi=lp64d -mcmodel=medany \
  -O2 -ffreestanding -fno-builtin -nostdlib -nostartfiles \
  -I"${repo_root}/apps/common" \
  -T"${script_dir}/qbs_contract_test.ld" \
  "${script_dir}/qbs_contract_test.S" \
  "${script_dir}/qbs_contract_test.c" \
  -o "${build_dir}/qbs_contract_test.elf"

if ! timeout "${QBS_CONTRACT_TIMEOUT:-20}" "${qemu}" \
    -M virt -cpu "${qemu_cpu}" \
    -m 128M -smp 1 -bios none -kernel "${build_dir}/qbs_contract_test.elf" \
    -display none -serial none -monitor none; then
  printf 'QBS v3 contract failed: qemu=%s cpu=%s\n' "${qemu}" "${qemu_cpu}" >&2
  exit 1
fi

echo "QBS v3 capability, M5/M8, shape, tail, fault, fixed-RNE, and fflags contract: PASS"
