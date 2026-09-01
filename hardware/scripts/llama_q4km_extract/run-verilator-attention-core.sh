#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
apps_dir=${repo_root}/apps
app=llama_q4km_operator
implementation=${1:-}
case_id=${2:-${LLAMA_ATTN_CASE_ID:-operator/decode/attention_core}}
capture_root=${Q4KM_CAPTURE_ROOT:-}
sim_l2_mb=${LLAMA_ATTN_SIM_L2_MB:-16}
sim_l2_bytes=$((sim_l2_mb * 1024 * 1024))
verilator=${LLAMA_ATTN_VERILATOR:-${repo_root}/hardware/build_sim_l2_${sim_l2_mb}m/verilator/Vara_tb_verilator}
run_root=${LLAMA_ATTN_RUN_ROOT:-${repo_root}/hardware/llama_attention_verilator_runs}
term_cycles=${LLAMA_ATTN_TERM_CYCLES:-1500000000}
wall_timeout=${LLAMA_ATTN_WALL_TIMEOUT:-43200}
build_lock=${apps_dir}/bin/.llama-q4km-operator-build.lock
l2_checker=${repo_root}/hardware/scripts/llama_q4km_extract/check-sim-l2.sh

case ${implementation} in
  ref|rvv|tiled_rvv|q64_rvv|akv|akv_v2|akv_v2_prefill) ;;
  *)
    echo "usage: $0 IMPLEMENTATION [CASE_ID]" >&2
    exit 2
    ;;
esac
if [[ -z ${capture_root} || ! -f ${capture_root}/replay/manifest.json ]]; then
  echo "Q4KM_CAPTURE_ROOT must name a packaged llama.cpp capture" >&2
  exit 2
fi
if [[ ! ${sim_l2_mb} =~ ^(1|2|4|8|16|32|64)$ ]]; then
  echo "unsupported LLAMA_ATTN_SIM_L2_MB: ${sim_l2_mb}" >&2
  exit 2
fi
if [[ ! ${term_cycles} =~ ^[1-9][0-9]*$ ||
      ! ${wall_timeout} =~ ^[1-9][0-9]*$ ]]; then
  echo "cycle and wall-time limits must be positive integers" >&2
  exit 2
fi
[[ -x ${verilator} ]] || {
  echo "missing Verilator simulator: ${verilator}" >&2
  exit 1
}

case_tag=${case_id//\//_}
stamp=$(date +%Y%m%d_%H%M%S)
run_dir=${run_root}/${case_tag}_${implementation}_${stamp}
mkdir -p "${run_dir}" "${apps_dir}/bin"

source_commit=$(git -C "${repo_root}" rev-parse HEAD)
source_dirty=false
if ! git -C "${repo_root}" diff-index --quiet HEAD --; then
  source_dirty=true
fi
capture_manifest_sha256=$(sha256sum -- \
  "${capture_root}/replay/manifest.json" | awk '{print $1}')
verilator_sha256=$(sha256sum -- "${verilator}" | awk '{print $1}')

printf 'schema_version=1\nimplementation=%s\ncase_id=%s\n' \
  "${implementation}" "${case_id}" > "${run_dir}/run.conf"
printf 'capture_root=%s\nsource_commit=%s\nsource_dirty=%s\n' \
  "${capture_root}" "${source_commit}" "${source_dirty}" \
  >> "${run_dir}/run.conf"
printf 'capture_manifest_sha256=%s\nverilator=%s\nverilator_sha256=%s\n' \
  "${capture_manifest_sha256}" "${verilator}" "${verilator_sha256}" \
  >> "${run_dir}/run.conf"
printf 'sim_l2_mb=%s\nsim_l2_bytes=%s\nterm_cycles=%s\nwall_timeout=%s\n' \
  "${sim_l2_mb}" "${sim_l2_bytes}" "${term_cycles}" "${wall_timeout}" \
  >> "${run_dir}/run.conf"

(
  flock 9
  Q4KM_CAPTURE_ROOT=${capture_root} make -C "${apps_dir}" "${app}" \
    sim_l2_mb="${sim_l2_mb}" \
    "def_args_${app}=${case_id} ${implementation}" \
    > "${run_dir}/build.log" 2>&1
  cp "${apps_dir}/bin/${app}" "${run_dir}/${app}.${implementation}.elf"
  cp "${apps_dir}/${app}/${app}.dump" \
    "${run_dir}/${app}.${implementation}.dump"
) 9> "${build_lock}"

elf=${run_dir}/${app}.${implementation}.elf
printf 'elf_sha256=%s\n' "$(sha256sum -- "${elf}" | awk '{print $1}')" \
  >> "${run_dir}/run.conf"
LLAMA_ATTN_SIM_L2_BYTES=${sim_l2_bytes} \
  "${l2_checker}" "$(dirname -- "${verilator}")" "${elf}" \
  >> "${run_dir}/run.conf"

set +e
(
  cd "${run_dir}"
  timeout --foreground "${wall_timeout}" "${verilator}" \
    -l "ram,${elf},elf" --term-after-cycles="${term_cycles}" +AKV_PERF \
    > verilator.log 2>&1
)
status=$?
set -e
printf 'exit_status=%s\n' "${status}" >> "${run_dir}/run.conf"
if (( status != 0 )); then
  echo "Verilator run failed with status ${status}: ${run_dir}" >&2
  exit "${status}"
fi
grep -q 'Core Test .*\*\*\* SUCCESS \*\*\*' "${run_dir}/verilator.log"
grep -q "LLAMA_OPERATOR ${case_id}/${implementation} PASS" \
  "${run_dir}/verilator.log"

: > "${run_dir}/complete"
ln -sfn "${run_dir}" "${run_root}/${case_tag}_${implementation}_latest"
echo "results: ${run_dir}"
