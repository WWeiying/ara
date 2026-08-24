#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ( "$1" != rvv && "$1" != qbs ) ]]; then
  echo "usage: $0 <rvv|qbs>" >&2
  exit 2
fi

mode=$1
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
hardware_dir=$(cd -- "${script_dir}/../.." && pwd)
repo_dir=$(cd -- "${hardware_dir}/.." && pwd)
l2_mb=${LLAMA_FORMAT_L2_MB:-1}
timestamp=$(date +%Y%m%d_%H%M%S)

if [[ "${mode}" == rvv ]]; then
  sim_template=${LLAMA_FORMAT_SIM_TEMPLATE:-"${hardware_dir}/sim_rvv_real_formats_${l2_mb}m_template"}
  run_root=${LLAMA_FORMAT_RUN_ROOT:-"${hardware_dir}/rvv_format_eval_runs/${timestamp}"}
  run_one=${script_dir}/run_eval_one.sh
else
  sim_template=${LLAMA_FORMAT_SIM_TEMPLATE:-"${hardware_dir}/sim_qbs_real_formats_${l2_mb}m_template"}
  run_root=${LLAMA_FORMAT_RUN_ROOT:-"${hardware_dir}/qbs_format_eval_runs/${timestamp}"}
  run_one=${hardware_dir}/scripts/qbs/run_eval_one.sh
fi

case_stems=(
  q3k_decode_attn_q
  q5k_decode_attn_q
  q6k_decode_attn_q
  q8_0_decode_attn_q
)

if [[ ! -x "${sim_template}/simv" || ! -d "${sim_template}/simv.daidir" ]]; then
  echo "missing ${mode} format simulation template: ${sim_template}" >&2
  echo "run: make -C ${hardware_dir} llama_format_${mode}_compile" >&2
  exit 2
fi

mkdir -p "${run_root}"
printf 'case\tpid\trun_dir\n' > "${run_root}/manifest.tsv"
printf 'case\tapp_bin\tsha256\n' > "${run_root}/apps.tsv"
printf '%s\n' "${sim_template}" > "${run_root}/sim_template"
printf '%s\n' "${mode}" > "${run_root}/mode"
printf '%s\n' "${l2_mb}" > "${run_root}/l2_mb"
git -C "${repo_dir}" rev-parse HEAD > "${run_root}/git_head"
git -C "${repo_dir}" status --short > "${run_root}/git_status"
sha256sum "${sim_template}/simv" > "${run_root}/simv.sha256"

for stem in "${case_stems[@]}"; do
  case_id=${stem}_${mode}
  app_bin=${repo_dir}/apps/bin/llama_qwen25_${case_id}
  if [[ ! -x "${app_bin}" ]]; then
    echo "missing benchmark ELF: ${app_bin}" >&2
    exit 2
  fi
  printf '%s\t%s\t%s\n' "${case_id}" "${app_bin}" \
    "$(sha256sum "${app_bin}" | awk '{print $1}')" >> "${run_root}/apps.tsv"

  run_dir=${run_root}/${case_id}
  mkdir -p "${run_dir}"
  cp -a "${sim_template}/simv" "${run_dir}/simv"
  cp -a "${sim_template}/simv.daidir" "${run_dir}/simv.daidir"

  setsid -f "${run_one}" "${case_id}" "${run_dir}" "${app_bin}" \
    > "${run_dir}/driver.log" 2>&1 < /dev/null &
  for _ in {1..50}; do
    [[ -s "${run_dir}/worker_pid" ]] && break
    sleep 0.1
  done
  if [[ ! -s "${run_dir}/worker_pid" ]]; then
    echo "worker did not start: ${case_id}" >&2
    exit 1
  fi
  pid=$(<"${run_dir}/worker_pid")
  printf '%s\n' "${pid}" > "${run_dir}/pid"
  printf '%s\t%s\t%s\n' "${case_id}" "${pid}" "${run_dir}" \
    >> "${run_root}/manifest.tsv"
done

ln -sfn "${run_root}" "${hardware_dir}/${mode}_format_eval_runs/latest"
printf '%s\n' "${run_root}"
