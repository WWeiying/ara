#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
hardware_dir=$(cd -- "${script_dir}/../.." && pwd)
run_root=${1:-"${hardware_dir}/llama_eval_runs/latest"}
run_root=$(readlink -f "${run_root}")
manifest="${run_root}/manifest.tsv"

if [[ ! -f "${manifest}" ]]; then
  echo "missing eval manifest: ${manifest}" >&2
  exit 2
fi

printf '%-28s %-9s %-9s %s\n' case state elapsed run_dir
while IFS=$'\t' read -r case_id pid run_dir; do
  [[ "${case_id}" == case ]] && continue
  if [[ -s "${run_dir}/status" ]]; then
    state=$(<"${run_dir}/status")
  elif kill -0 "${pid}" 2>/dev/null; then
    state=RUNNING
  else
    state=LOST
  fi
  if [[ -s "${run_dir}/started_at" ]]; then
    start_epoch=$(date -d "$(<"${run_dir}/started_at")" +%s)
    if [[ -s "${run_dir}/finished_at" ]]; then
      end_epoch=$(date -d "$(<"${run_dir}/finished_at")" +%s)
    else
      end_epoch=$(date +%s)
    fi
    elapsed=$((end_epoch - start_epoch))s
  else
    elapsed=-
  fi
  printf '%-28s %-9s %-9s %s\n' "${case_id}" "${state}" "${elapsed}" "${run_dir}"
done < "${manifest}"
