#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
platform_dir=${QBS_PLATFORM_DIR:-${HOME}/llama/platforms/cva6-qemu}
source "${platform_dir}/env.sh"

qemu_binary=${QBS_QEMU:-${script_dir}/build/qemu-10.2.0-build/qemu-system-riscv64}
qemu_cpu=${QBS_QEMU_CPU:-rv64,v=true,vlen=1024,elen=64,xaraqbs=true}
llama_binary=${QBS_LLAMA_BINARY:-${LLAMA_SRC}/build-rv64-cva6-qbs-emulate/bin/llama-simple}
token_count=${QBS_TOKEN_COUNT:-2}
prompt_text=${QBS_PROMPT:-The quick brown fox jumps over the lazy dog.}
expected_profiles=${QBS_EXPECTED_PROFILES:-Q4_K Q6_K}
run_mode=${QBS_RUN_MODE:-compare}
require_equal=${QBS_REQUIRE_EQUAL:-1}
require_activation_context=${QBS_REQUIRE_ACTIVATION_CONTEXT:-0}
qbs_formats=${QBS_FORMATS:-}
teacher_force=${QBS_TEACHER_FORCE:-0}
work_dir=${QBS_QWEN_WORK_DIR:-${script_dir}/build/qwen-native-check}
log_file=${QBS_QWEN_LOG:-${work_dir}/qwen-native-check.log}
model_file=${QBS_MODEL_FILE:-}
if [[ -n "${model_file}" ]]; then
  model_name=${QBS_MODEL_NAME:-$(basename -- "${model_file}")}
  model_path=${QBS_MODEL_PATH:-/model/models/${model_name}}
  model_disk=${QBS_MODEL_DISK:-${work_dir}/model.ext4}
else
  model_path=${QBS_MODEL_PATH:-/model/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}
  model_disk=${QBS_MODEL_DISK:-${QEMU_IMAGES}/qwen2.5-q4km-capture.ext4}
fi
init_binary=${work_dir}/qbs-token-init
initramfs_list=${work_dir}/qbs-token-initramfs.list
initramfs=${work_dir}/qbs-token-initramfs.cpio
binary_disk=${work_dir}/llama-simple.ext4

if [[ ! -x "${qemu_binary}" ]]; then
  "${script_dir}/build_qemu_xaraqbs.sh"
fi
test -x "${qemu_binary}"
test -x "${llama_binary}"
mkdir -p "${work_dir}" "$(dirname -- "${log_file}")"

if [[ -n "${model_file}" ]]; then
  test -s "${model_file}"
  model_bytes=$(stat -c '%s' "${model_file}")
  model_disk_mib=$(((model_bytes + 128 * 1024 * 1024 + 1024 * 1024 - 1) / (1024 * 1024)))
  truncate -s "${model_disk_mib}M" "${model_disk}"
  mkfs.ext4 -q -F "${model_disk}"
  debugfs -w -R "mkdir /models" "${model_disk}" >/dev/null 2>&1
  debugfs -w -R "write ${model_file} /models/${model_name}" \
    "${model_disk}" >/dev/null 2>&1
fi
test -s "${model_disk}"

"${CROSS_BIN}/riscv64-linux-gcc" \
  -march=rv64gc -mabi=lp64d -O2 -static \
  -DQBS_MODEL_PATH="\"${model_path}\"" \
  -DQBS_TOKEN_COUNT="\"${token_count}\"" \
  -DQBS_PROMPT_TEXT="\"${prompt_text}\"" \
  -DQBS_RUN_MODE="\"${run_mode}\"" \
  -DQBS_REQUIRE_EQUAL="${require_equal}" \
  -DQBS_FORMATS="\"${qbs_formats}\"" \
  -DQBS_TEACHER_FORCE="${teacher_force}" \
  "${script_dir}/qbs_token_init.c" -lm -o "${init_binary}"

truncate -s 128M "${binary_disk}"
mkfs.ext4 -q -F "${binary_disk}"
debugfs -w -R "write ${llama_binary} /llama-simple" \
  "${binary_disk}" >/dev/null 2>&1
debugfs -w -R "set_inode_field /llama-simple mode 0100755" \
  "${binary_disk}" >/dev/null 2>&1

cat > "${initramfs_list}" <<EOF
dir /dev 755 0 0
nod /dev/console 600 0 0 c 5 1
dir /run 755 0 0
dir /model 755 0 0
file /init ${init_binary} 755 0 0
EOF
gen_init_cpio=$(printf '%s\n' \
  "${CVA6_SDK}"/buildroot/output/build/linux-*/usr/gen_init_cpio | head -n 1)
test -x "${gen_init_cpio}"
"${gen_init_cpio}" "${initramfs_list}" > "${initramfs}"

"${qemu_binary}" \
  -M virt \
  -cpu "${qemu_cpu}" \
  -smp 1 -m 4G -display none -monitor none -serial stdio \
  -bios "${QEMU_IMAGES}/fw_dynamic.bin" \
  -initrd "${initramfs}" \
  -kernel "${QEMU_IMAGES}/Image" \
  -drive "file=${binary_disk},if=virtio,format=raw,readonly=on" \
  -drive "file=${model_disk},if=virtio,format=raw,readonly=on" \
  -append "console=ttyS0 rdinit=/init" \
  2>&1 | tee "${log_file}"

grep -q 'GGML_RISCV_REPACK=QBS' "${log_file}"
for profile in ${expected_profiles}; do
  if [[ "${teacher_force}" == "1" ]]; then
    grep -Eq "GGML_RISCV_QBS_EXEC type=${profile} .*native_qbexec=[1-9]" "${log_file}"
  else
    grep -Eq "GGML_RISCV_QBS_EXEC type=${profile} .*gemv_calls=[1-9]" "${log_file}"
    grep -Eq "GGML_RISCV_QBS_EXEC type=${profile} .*gemm_calls=[1-9]" "${log_file}"
  fi
done
if [[ "${require_activation_context}" == "1" ]]; then
  grep -Eq 'GGML_RISCV_QBS_EXEC type=.* context_reuse=[1-9]' "${log_file}"
fi
grep -q 'QBS_TOKEN_RUN_EXIT=QBS_NATIVE:0' "${log_file}"
if [[ "${run_mode}" == "compare" ]]; then
  grep -q 'QBS_LOGITS_RECORDS=' "${log_file}"
  if [[ "${teacher_force}" == "1" ]]; then
    grep -q 'QBS_MODEL_METRICS records=' "${log_file}"
  fi
  if [[ "${require_equal}" == "1" ]]; then
    grep -q 'QBS_TOKEN_OUTPUT_EQUAL=1' "${log_file}"
  fi
else
  grep -q 'QBS_TOKEN_OUTPUT_EQUAL=NA' "${log_file}"
fi
grep -q 'LLAMA_GUEST_EXIT=0' "${log_file}"
