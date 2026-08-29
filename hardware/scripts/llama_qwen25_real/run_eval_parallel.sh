#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
hardware_dir=$(cd -- "${script_dir}/../.." && pwd)
repo_dir=$(cd -- "${hardware_dir}/.." && pwd)
large_l2_mb=${LLAMA_EVAL_L2_MB:-16}
sim_template=${LLAMA_EVAL_SIM_TEMPLATE:-"${hardware_dir}/sim_llama_eval_${large_l2_mb}m_template"}
timestamp=$(date +%Y%m%d_%H%M%S)
run_root=${LLAMA_EVAL_RUN_ROOT:-"${hardware_dir}/llama_eval_runs/${timestamp}"}

cases=(
  decode_attn_q_eval
  decode_ffn_gate_eval
  decode_ffn_down_eval
  prefill_attn_q_eval
  prefill_ffn_gate_eval
  prefill_ffn_down_eval
)

if [[ ! -x "${sim_template}/simv" || ! -d "${sim_template}/simv.daidir" ]]; then
  echo "missing simulation template: ${sim_template}" >&2
  echo "run: make -C ${hardware_dir} llama_real_eval_compile" >&2
  exit 2
fi

mkdir -p "${run_root}"
printf 'case\tpid\trun_dir\n' > "${run_root}/manifest.tsv"
printf 'case\tapp_bin\tapp_sha256\tprovenance_sha256\n' \
  > "${run_root}/apps.tsv"
printf '%s\n' "${sim_template}" > "${run_root}/sim_template"
printf '%s\n' rvv > "${run_root}/mode"
printf '%s\n' "${large_l2_mb}" > "${run_root}/l2_mb"
git -C "${repo_dir}" rev-parse HEAD > "${run_root}/git_head"
git -C "${repo_dir}" status --short > "${run_root}/git_status"
git -C "${repo_dir}" diff --binary > "${run_root}/git_diff.patch"
sha256sum "${sim_template}/simv" > "${run_root}/simv.sha256"
find "${sim_template}/simv.daidir" -type f -print0 | sort -z | \
  xargs -0 sha256sum > "${run_root}/simv_daidir.sha256"
for case_id in "${cases[@]}"; do
  app_bin="${repo_dir}/apps/bin/llama_qwen25_${case_id}"
  provenance="${repo_dir}/apps/llama_qwen25_${case_id}/generated/provenance.json"
  if [[ ! -x "${app_bin}" ]]; then
    echo "missing benchmark ELF: ${app_bin}" >&2
    exit 2
  fi
  if [[ ! -s "${provenance}" ]]; then
    echo "missing benchmark provenance: ${provenance}" >&2
    exit 2
  fi

  run_dir="${run_root}/${case_id}"
  mkdir -p "${run_dir}"
  cp -a "${sim_template}/simv" "${run_dir}/simv"
  cp -a "${sim_template}/simv.daidir" "${run_dir}/simv.daidir"
  cp -a "${app_bin}" "${run_dir}/benchmark.elf"
  cp -a "${provenance}" "${run_dir}/provenance.json"
  printf '%s\n' "${app_bin}" > "${run_dir}/app_source"
  sha256sum "${run_dir}/benchmark.elf" > "${run_dir}/benchmark.elf.sha256"
  sha256sum "${run_dir}/provenance.json" > "${run_dir}/provenance.json.sha256"
  printf '%s\t%s\t%s\t%s\n' "${case_id}" "${app_bin}" \
    "$(sha256sum "${run_dir}/benchmark.elf" | awk '{print $1}')" \
    "$(sha256sum "${run_dir}/provenance.json" | awk '{print $1}')" \
    >> "${run_root}/apps.tsv"

  setsid -f "${script_dir}/run_eval_one.sh" \
    "${case_id}" "${run_dir}" "${run_dir}/benchmark.elf" \
    > "${run_dir}/driver.log" 2>&1 < /dev/null &
  for _ in {1..50}; do
    [[ -s "${run_dir}/worker_pid" ]] && break
    sleep 0.1
  done
  if [[ ! -s "${run_dir}/worker_pid" ]]; then
    echo "worker did not start: ${case_id}" >&2
    exit 1
  fi
  pid=$(cat "${run_dir}/worker_pid")
  printf '%s\n' "${pid}" > "${run_dir}/pid"
  printf '%s\t%s\t%s\n' "${case_id}" "${pid}" "${run_dir}" \
    >> "${run_root}/manifest.tsv"
done

ln -sfn "${run_root}" "${hardware_dir}/llama_eval_runs/latest"
printf '%s\n' "${run_root}"
