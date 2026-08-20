#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
hardware_dir=$(cd -- "${script_dir}/../.." && pwd)
repo_dir=$(cd -- "${hardware_dir}/.." && pwd)
large_l2_mb=${QBS_EVAL_L2_MB:-16}
default_template="${hardware_dir}/sim_qbs_llama_eval_${large_l2_mb}m_template"
legacy_template="${hardware_dir}/sim_qbs_llama_${large_l2_mb}m"
sim_template=${QBS_EVAL_SIM_TEMPLATE:-"${default_template}"}
timestamp=$(date +%Y%m%d_%H%M%S)
run_root=${QBS_EVAL_RUN_ROOT:-"${hardware_dir}/qbs_eval_runs/${timestamp}"}

cases=(
  decode_attn_q_qbs
  decode_ffn_gate_qbs
  decode_ffn_down_qbs
  prefill_attn_q_qbs
  prefill_ffn_gate_qbs
  prefill_ffn_down_qbs
)

if [[ ! -x "${sim_template}/simv" || ! -d "${sim_template}/simv.daidir" ]]; then
  if [[ -z "${QBS_EVAL_SIM_TEMPLATE:-}" && -x "${legacy_template}/simv" &&
        -d "${legacy_template}/simv.daidir" ]]; then
    sim_template=${legacy_template}
  else
    echo "missing QBS simulation template: ${sim_template}" >&2
    echo "run: make -C ${hardware_dir} llama_qbs_eval_compile" >&2
    exit 2
  fi
fi

mkdir -p "${run_root}"
printf 'case\tpid\trun_dir\n' > "${run_root}/manifest.tsv"
printf '%s\n' "${sim_template}" > "${run_root}/sim_template"
for case_id in "${cases[@]}"; do
  app_bin="${repo_dir}/apps/bin/llama_qwen25_${case_id}"
  if [[ ! -x "${app_bin}" ]]; then
    echo "missing benchmark ELF: ${app_bin}" >&2
    exit 2
  fi

  run_dir="${run_root}/${case_id}"
  mkdir -p "${run_dir}"
  cp -a "${sim_template}/simv" "${run_dir}/simv"
  cp -a "${sim_template}/simv.daidir" "${run_dir}/simv.daidir"

  setsid -f "${script_dir}/run_eval_one.sh" \
    "${case_id}" "${run_dir}" "${app_bin}" \
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

ln -sfn "${run_root}" "${hardware_dir}/qbs_eval_runs/latest"
printf '%s\n' "${run_root}"
