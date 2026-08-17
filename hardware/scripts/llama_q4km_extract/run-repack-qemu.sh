#!/usr/bin/env bash
set -euo pipefail

platform=/home/wangwy/llama/platforms/cva6-qemu
image=${platform}/images/qwen2.5-q4km-capture.ext4
log=/home/wangwy/llama/captures/q4k-repack-qemu-console.log
result=/home/wangwy/llama/captures/q4k-repack-qemu-result.log

if pgrep -f 'qemu-system-riscv64.*q4kmdata' >/dev/null; then
  echo "Q4_K_M QEMU is already running" >&2
  exit 1
fi

request=$(mktemp)
trap 'rm -f "${request}"' EXIT
printf 'selftest unused\n' > "${request}"

debugfs -w -R 'rm /q4km-replay.log' "${image}" >/dev/null 2>&1 || true
debugfs -w -R 'rm /q4km-replay.request' "${image}" >/dev/null 2>&1 || true
debugfs -w -R "write ${request} /q4km-replay.request" "${image}" >/dev/null

source "${platform}/env.sh"
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

rm -f "${result}"
debugfs -R "dump /q4km-replay.log ${result}" "${image}" >/dev/null
cat "${result}"

status=$(sed -n 's/^exit_status=//p' "${result}" | tail -n 1)
if [[ ! ${status} =~ ^[0-9]+$ ]]; then
  echo "Q4_Kx32 self-test result has no valid exit_status" >&2
  exit 2
fi
exit "${status}"
