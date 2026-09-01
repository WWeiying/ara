#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
runner=${root}/hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh
capture=/home/wangwy/llama/captures/akv-v2-derived-real-qwen-v3
sim_dir=${root}/hardware/sim_akv_generalized_qbs_20260901
filelist=${root}/hardware/build_akv_generalized_qbs_20260901/vcs/bender_script_default
output=${root}/hardware/akv_generalization_regress_20260901

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

if [[ ! -x ${sim_dir}/simv ]]; then
  echo "missing current AKV simulator: ${sim_dir}/simv" >&2
  exit 1
fi
if [[ ! -f ${capture}/replay/manifest.json ]]; then
  echo "missing derived-real capture: ${capture}" >&2
  exit 1
fi
if [[ ! -f ${filelist} ]]; then
  echo "missing simulator filelist: ${filelist}" >&2
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
  echo "current AKV simulator is stale; rebuild before regression" >&2
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
  local case_id=$1
  local kv=$2
  LLAMA_ATTN_CASE_ID=${case_id} \
  Q4KM_CAPTURE_ROOT=${capture} \
  LLAMA_ATTN_SIM_DIR=${sim_dir} \
  LLAMA_ATTN_RUN_ROOT=${output} \
    "${runner}" akv_v2 "${kv}" --ara-only
}

run_point akv-v2/derived-real/d64-g8-kv64 64
run_point akv-v2/derived-real/d128-g6-kv128 128
run_point akv-v2/derived-real/d128-g4-kv63 63
run_point akv-v2/derived-real/d64-g1-kv65 65

printf 'PASS\n' > "${output}/status"
touch "${output}/complete"
final_status=PASS
