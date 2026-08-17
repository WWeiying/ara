#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
platform=/home/wangwy/llama/platforms/cva6-qemu
image=${platform}/images/qwen2.5-q4km-capture.ext4
capture_root=/home/wangwy/llama/captures
host_output=${capture_root}/qwen2.5-1.5b-q4_k_m
extract_tmp=${capture_root}/.qwen2.5-1.5b-q4_k_m.extracting
log=${capture_root}/qwen2.5-1.5b-q4_k_m-qemu.log

source "${platform}/env.sh"
"${platform}/setup.sh" >/dev/null

mkdir -p "${capture_root}"
"${repo_root}/hardware/scripts/llama_q4km_extract/prepare-disk.sh"

set +e
"${CROSS_BIN}/qemu-system-riscv64" \
  -M virt \
  -cpu "rv64,v=true,vlen=1024,elen=64" \
  -smp 1 \
  -m 8G \
  -nographic \
  -bios "${QEMU_IMAGES}/fw_dynamic.bin" \
  -initrd "${QEMU_IMAGES}/rootfs.cpio" \
  -kernel "${QEMU_IMAGES}/Image" \
  -drive "file=${image},format=raw,if=none,id=q4kmdata" \
  -device "virtio-blk-pci,drive=q4kmdata" \
  -append "rootwait root=/dev/ram ro console=ttyS0" \
  > "${log}" 2>&1
status=$?
set -e

if [[ ${status} -eq 0 ]]; then
  rm -rf "${extract_tmp}"
  mkdir -p "${extract_tmp}"
  debugfs -R "rdump /captures/qwen2.5-1.5b-q4_k_m ${extract_tmp}" "${image}" \
    >> "${log}" 2>&1 || true
  extracted=${extract_tmp}/qwen2.5-1.5b-q4_k_m
  test -s "${extracted}/model.json"
  test -s "${extracted}/qemu-console.log"
  rm -rf "${host_output}"
  mv "${extracted}" "${host_output}"
  rmdir "${extract_tmp}"
fi
exit "${status}"
