#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 CASE_ID" >&2
  exit 2
fi

repo_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
script_dir=${repo_root}/hardware/scripts/llama_q4km_extract
platform=/home/wangwy/llama/platforms/cva6-qemu
capture_root=${Q4KM_CAPTURE_ROOT:-/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m}
replay=${platform}/build/llama-q4km-spike/bin/llama-q4km-replay
spike=${SPIKE:-/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike}
pk=${PK:-/home/wangwy/openproject/riscv-pk/build/pk}
timeout_s=${LLAMA_SPIKE_TIMEOUT:-3600}
run_root=${Q4KM_SPIKE_RUN_ROOT:-/home/wangwy/llama/captures/spike-runs}

for executable in "${replay}" "${spike}" "${pk}"; do
  if [[ ! -x ${executable} ]]; then
    echo "missing executable: ${executable}" >&2
    exit 1
  fi
done

if [[ ! ${timeout_s} =~ ^[1-9][0-9]*$ ]]; then
  echo "LLAMA_SPIKE_TIMEOUT must be a positive integer: ${timeout_s}" >&2
  exit 2
fi

mapfile -t leaves < <("${script_dir}/cases.py" --root "${capture_root}" resolve-all "$1")
if [[ ${#leaves[@]} -eq 0 ]]; then
  echo "case selection resolved to no leaves: $1" >&2
  exit 2
fi

stamp=$(date +%Y%m%d_%H%M%S)
safe_id=$(printf '%s' "$1" | tr '/:' '__')
run_dir=${run_root}/${stamp}_${safe_id}
mkdir -p "${run_dir}"
ln -sfn "${run_dir}" "${run_root}/latest"

{
  printf 'selection=%s\n' "$1"
  printf 'leaf_count=%d\n' "${#leaves[@]}"
  printf 'isa=rv64gcv_zvl1024b\n'
  printf 'timeout_seconds=%s\n' "${timeout_s}"
  printf 'spike=%s\n' "${spike}"
  printf 'pk=%s\n' "${pk}"
  printf 'replay=%s\n' "${replay}"
  printf 'capture_root=%s\n' "${capture_root}"
  printf 'spike_sha256=%s\n' "$(sha256sum "${spike}" | cut -d' ' -f1)"
  printf 'pk_sha256=%s\n' "$(sha256sum "${pk}" | cut -d' ' -f1)"
  printf 'replay_sha256=%s\n' "$(sha256sum "${replay}" | cut -d' ' -f1)"
  printf 'manifest_sha256=%s\n' "$(sha256sum "${capture_root}/replay/manifest.json" | cut -d' ' -f1)"
} > "${run_dir}/environment.txt"

printf 'case_id\tstatus\texit_code\tlog\n' > "${run_dir}/summary.tsv"
overall=0
index=0
for leaf in "${leaves[@]}"; do
  IFS=$'\t' read -r case_id level relative_path <<< "${leaf}"
  case_path=${capture_root}/${relative_path}
  leaf_name=$(printf '%03d_%s' "${index}" "$(printf '%s' "${case_id}" | tr '/:' '__')")
  log=${run_dir}/${leaf_name}.log
  command_file=${run_dir}/${leaf_name}.command
  printf '%q ' timeout --foreground "${timeout_s}" "${spike}" \
    --isa=rv64gcv_zvl1024b -m2048 "${pk}" "${replay}" "${level}" "${case_path}" \
    > "${command_file}"
  printf '\n' >> "${command_file}"

  echo "== ${case_id} =="
  set +e
  timeout --foreground "${timeout_s}" "${spike}" \
    --isa=rv64gcv_zvl1024b \
    -m2048 \
    "${pk}" "${replay}" "${level}" "${case_path}" \
    2>&1 | tee "${log}"
  rc=${PIPESTATUS[0]}
  set -e

  status=PASS
  if [[ ${rc} -eq 124 ]]; then
    status=TIMEOUT
  elif [[ ${rc} -ne 0 ]]; then
    status=FAIL
  fi
  printf '%s\t%s\t%d\t%s\n' "${case_id}" "${status}" "${rc}" "${log}" \
    >> "${run_dir}/summary.tsv"
  if [[ ${rc} -ne 0 ]]; then
    overall=${rc}
    break
  fi
  index=$((index + 1))
done

echo "results: ${run_dir}"
exit "${overall}"
