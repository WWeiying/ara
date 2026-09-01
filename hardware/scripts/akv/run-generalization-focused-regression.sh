#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
runner=${root}/hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh
sim_dir=${root}/hardware/sim_akv_generalized_qbs_20260901
filelist=${root}/hardware/build_akv_generalized_qbs_20260901/vcs/bender_script_default
output=${root}/hardware/akv_generalization_focused_current_20260901

mkdir -p "${output}"
rm -f "${output}/complete"
printf 'RUNNING\n' > "${output}/status"
printf '%s\n' "$$" > "${output}/worker_pid"
date --iso-8601=seconds > "${output}/started_at"
final_status=
on_exit() {
  local rc=$?
  date --iso-8601=seconds > "${output}/finished_at"
  if [[ -z ${final_status} ]]; then
    printf 'FAILED\n' > "${output}/status"
  fi
  return "${rc}"
}
on_signal() {
  final_status=INTERRUPTED
  printf 'INTERRUPTED\n' > "${output}/status"
  exit 130
}
trap on_exit EXIT
trap on_signal INT TERM

if [[ ! -x ${sim_dir}/simv || ! -f ${filelist} ]]; then
  echo "missing current QBS+AKV simulator or filelist" >&2
  exit 1
fi

stale_sources=()
while IFS= read -r source; do
  [[ -z ${source} ]] && continue
  if [[ ! -f ${source} ]]; then
    echo "simulator input no longer exists: ${source}" >&2
    exit 1
  fi
  [[ ${source} -nt ${sim_dir}/simv ]] && stale_sources+=("${source}")
done < <(awk '/^\// {print}' "${filelist}")
for source in "${filelist}" "${root}/Bender.yml" \
              "${root}/hardware/Makefile" \
              "${root}/hardware/build_akv_generalized_qbs_20260901/work-dpi/elfloader.o" \
              "${root}/config/default.mk" "${root}/config/sram.mk"; do
  if [[ ! -f ${source} ]]; then
    echo "simulator input no longer exists: ${source}" >&2
    exit 1
  fi
  [[ ${source} -nt ${sim_dir}/simv ]] && stale_sources+=("${source}")
done
if (( ${#stale_sources[@]} != 0 )); then
  echo "current QBS+AKV simulator is stale; rebuild before regression" >&2
  printf '  newer input: %s\n' "${stale_sources[@]:0:8}" >&2
  exit 1
fi

required_defines=(
  NR_LANES=4
  VLEN=1024
  ARA_QBS_ENABLE=1
  ARA_AKV_ENABLE=1
  ARA_AKV_V2_ENABLE=1
  SIM_L2_SIZE_BYTES=16777216
)
for define in "${required_defines[@]}"; do
  if ! grep -Fxq "+define+${define}" "${filelist}"; then
    echo "current simulator is missing required define: ${define}" >&2
    exit 1
  fi
done

run_point() {
  local implementation=$1
  local case_id=$2
  local kv=$3
  local capture=$4
  if [[ ! -f ${capture}/replay/manifest.json ]]; then
    echo "missing capture manifest: ${capture}/replay/manifest.json" >&2
    exit 1
  fi
  LLAMA_ATTN_CASE_ID=${case_id} \
  Q4KM_CAPTURE_ROOT=${capture} \
  LLAMA_ATTN_SIM_DIR=${sim_dir} \
  LLAMA_ATTN_RUN_ROOT=${output} \
    "${runner}" "${implementation}" "${kv}" --ara-only
}

run_point akv_v2 operator/decode/attention_core 16 \
  /home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-latest/kv16
run_point akv_v2 operator/decode/attention_core 5 \
  /home/wangwy/llama/captures/smollm2-135m-q4_k_m-attention-gqa3-dag-probe
run_point akv_v2 operator/decode/attention_core 18 \
  /home/wangwy/llama/captures/phi35-mini-q4km-attention-d96-head0-meta-20260901
run_point akv_v2 operator/decode/attention_core 17 \
  /home/wangwy/llama/captures/gemma3-1b-q4km-attention-d256-head0-meta-20260901
run_point tiled_rvv operator/decode/attention_core 17 \
  /home/wangwy/llama/captures/gemma3-1b-q4km-attention-d256-head0-meta-20260901

printf 'PASS\n' > "${output}/status"
touch "${output}/complete"
final_status=PASS
