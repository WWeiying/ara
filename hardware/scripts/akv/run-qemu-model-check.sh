#!/usr/bin/env bash
set -euo pipefail

max_abs_tolerance=${AKV_LOGITS_MAX_ABS_TOLERANCE:-0.001}
number_re='^([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
grep -Eq "${number_re}" <<< "${max_abs_tolerance}" || {
  printf 'invalid AKV_LOGITS_MAX_ABS_TOLERANCE: %s\n' "${max_abs_tolerance}" >&2
  exit 2
}

validate_log() {
  local log_file=$1
  local result_file=$2
  local coverage_line
  local max_abs

  coverage_line=$(grep -E 'GGML_RISCV_AKV_COVERAGE .*executed_ops=[1-9][0-9]*' "${log_file}" | tail -n 1)
  grep -Eq 'executed_ops=[1-9][0-9]*' <<< "${coverage_line}"
  grep -Eq 'fallback_threading=0([[:space:]]|$)' <<< "${coverage_line}"
  grep -Eq 'AKV_LOGITS_RECORDS=[1-9][0-9]*' "${log_file}"
  grep -q 'AKV_LOGITS_TOP1_EQUAL=1' "${log_file}"
  grep -q 'AKV_TOKEN_OUTPUT_EQUAL=1' "${log_file}"
  grep -q 'LLAMA_GUEST_EXIT=0' "${log_file}"

  max_abs=$(sed -n 's/^AKV_LOGITS_MAX_ABS=//p' "${log_file}" | tr -d '\r' | tail -n 1)
  grep -Eq "${number_re}" <<< "${max_abs}"
  awk -v value="${max_abs}" -v tolerance="${max_abs_tolerance}" \
    'BEGIN { exit !((value + 0.0) <= (tolerance + 0.0)) }'

  grep -E '^(GGML_RISCV_AKV_COVERAGE|AKV_LOGITS_|AKV_TOKEN_OUTPUT_EQUAL|LLAMA_GUEST_EXIT)' \
    "${log_file}" | tr -d '\r' > "${result_file}"
}

if [[ ${1:-} == --check-log ]]; then
  if [[ $# -ne 2 ]]; then
    printf 'usage: %s --check-log QEMU_LOG\n' "$0" >&2
    exit 2
  fi
  log_file=$2
  result_file=$(dirname -- "${log_file}")/result.txt
  test -s "${log_file}"
  validate_log "${log_file}" "${result_file}"
  printf 'AKV model log passed: %s\n' "${log_file}"
  exit 0
elif [[ $# -ne 0 ]]; then
  printf 'usage: %s [--check-log QEMU_LOG]\n' "$0" >&2
  exit 2
fi

ara_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
platform=${AKV_QEMU_PLATFORM:-/home/wangwy/llama/platforms/cva6-qemu}
llama_src=${AKV_LLAMA_SRC:-/home/wangwy/llama/llama.cpp}
llama_binary=${AKV_LLAMA_BINARY:-${llama_src}/build-rv64-cva6-akv-static/bin/llama-simple}
model_disk=${AKV_MODEL_DISK:-${platform}/images/qwen2.5-q4km-capture.ext4}
timestamp=$(date +%Y%m%d_%H%M%S)
run_dir=${AKV_RUN_DIR:-${ara_root}/hardware/akv_jobs/qemu_model_${timestamp}}

source "${platform}/env.sh"

test -x "${llama_binary}"
test -s "${model_disk}"
mkdir -p "${run_dir}"

init_binary="${run_dir}/akv-token-init"
initramfs="${run_dir}/akv-token-check.cpio"
binary_disk="${run_dir}/llama-akv-token.ext4"
initramfs_list="${run_dir}/initramfs.list"
log_file="${run_dir}/qemu.log"
result_file="${run_dir}/result.txt"

"${CROSS_BIN}/riscv64-linux-gcc" \
  -march=rv64gc -mabi=lp64d -O2 -static \
  "-DAKV_LOGITS_MAX_ABS_TOLERANCE=${max_abs_tolerance}" \
  "${ara_root}/hardware/scripts/akv/akv-token-init.c" \
  -o "${init_binary}"

truncate -s 128M "${binary_disk}"
mkfs.ext4 -q -F "${binary_disk}"
debugfs -w -R "write ${llama_binary} /llama-simple" "${binary_disk}" >/dev/null 2>&1
debugfs -w -R "set_inode_field /llama-simple mode 0100755" "${binary_disk}" >/dev/null 2>&1

printf '%s\n' \
  'dir /dev 755 0 0' \
  'nod /dev/console 600 0 0 c 5 1' \
  'dir /run 755 0 0' \
  'dir /model 755 0 0' \
  "file /init ${init_binary} 755 0 0" > "${initramfs_list}"

gen_init_cpio=$(find "${CVA6_SDK}/buildroot/output/build" \
  -path '*/usr/gen_init_cpio' -type f -print -quit)
test -x "${gen_init_cpio}"
"${gen_init_cpio}" "${initramfs_list}" > "${initramfs}"

"${CROSS_BIN}/qemu-system-riscv64" \
  -M virt \
  -cpu "rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true" \
  -smp 1 \
  -m 4G \
  -display none \
  -monitor none \
  -serial stdio \
  -bios "${QEMU_IMAGES}/fw_dynamic.bin" \
  -initrd "${initramfs}" \
  -kernel "${QEMU_IMAGES}/Image" \
  -drive "file=${binary_disk},if=virtio,format=raw,readonly=on" \
  -drive "file=${model_disk},if=virtio,format=raw,readonly=on" \
  -append "console=ttyS0 rdinit=/init" \
  2>&1 | tee "${log_file}"

validate_log "${log_file}" "${result_file}"
printf 'AKV model check passed: %s\n' "${run_dir}"
