#!/usr/bin/env bash
set -uo pipefail

repo_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
apps_dir=${repo_root}/apps
app_dir=${apps_dir}/llama_q4km_operator
app=llama_q4km_operator
case_tool=${repo_root}/hardware/scripts/llama_q4km_extract/cases.py
capture_root=${Q4KM_CAPTURE_ROOT:-/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m}
spike=${SPIKE:-${repo_root}/install/riscv-isa-sim/bin/spike}
sim_dir=${repo_root}/hardware/sim_l2_16m
simv=${sim_dir}/simv
mode=${1:---all}
selection=${2:-operator/all}
spike_timeout=${LLAMA_SPIKE_TIMEOUT:-3600}
ara_timeout=${LLAMA_ARA_TIMEOUT:-86400}
run_root=${LLAMA_ARA_RUN_ROOT:-${repo_root}/hardware/llama_benchmark_runs}
stamp=$(date +%Y%m%d_%H%M%S)
run_dir=${run_root}/operator_ara_l2_16m_${stamp}

if [[ ${mode} != --all && ${mode} != --spike-only && ${mode} != --ara-only ]]; then
  echo "usage: $0 [--all|--spike-only|--ara-only] [case-or-suite]" >&2
  exit 2
fi
if [[ ! -x ${case_tool} || ! -x ${spike} ]]; then
  echo "missing case tool or Spike executable" >&2
  exit 1
fi
if [[ ${mode} != --spike-only && ! -x ${simv} ]]; then
  echo "missing 16 MiB simv: ${simv}" >&2
  echo "run: make -C hardware compile_large large_l2_mb=16" >&2
  exit 1
fi

mkdir -p "${run_dir}"
ln -sfn "${run_dir}" "${run_root}/operator_ara_latest"
printf 'case_id\tspike\tara\telf_bytes\tlog\n' > "${run_dir}/summary.tsv"

if [[ ${selection} == operator/ara-compact ]]; then
  compact_cases=(
    operator/decode/attention_norm
    operator/decode/blk_0_attn_k_weight
    operator/decode/blk_0_attn_v_weight
    operator/decode/rope_q
    operator/decode/attention_residual
    operator/decode/ffn_activation
    operator/decode/ffn_residual
    operator/prefill/attention_norm
    operator/prefill/rope_k
    operator/prefill/attention_residual
  )
  leaves=()
  for compact_case in "${compact_cases[@]}"; do
    mapfile -t resolved < <(
      "${case_tool}" --root "${capture_root}" resolve-all "${compact_case}"
    )
    leaves+=("${resolved[@]}")
  done
elif [[ ${selection} == operator/all ]]; then
  # Finish the shorter single-token cases first, then run the heavier prefill set.
  mapfile -t leaves < <(
    "${case_tool}" --root "${capture_root}" resolve-all operator/decode/all
    "${case_tool}" --root "${capture_root}" resolve-all operator/prefill/all
  )
else
  mapfile -t leaves < <("${case_tool}" --root "${capture_root}" resolve-all "${selection}")
fi
if [[ ${#leaves[@]} -eq 0 ]]; then
  echo "selection resolved to no leaves: ${selection}" >&2
  exit 2
fi

clean_case() {
  rm -f \
    "${app_dir}/data.S" \
    "${app_dir}/data.S.o" \
    "${app_dir}/data.S.o.spike" \
    "${apps_dir}/bin/${app}" \
    "${apps_dir}/bin/${app}.spike"
}

build_spike() {
  local case_id=$1
  make -C "${apps_dir}" "bin/${app}.spike" \
    "def_args_${app}=${case_id}"
}

build_ara() {
  local case_id=$1
  make -C "${apps_dir}" "${app}" sim_l2_mb=16 \
    "def_args_${app}=${case_id}"
}

overall=0
index=0
for leaf in "${leaves[@]}"; do
  IFS=$'\t' read -r case_id level relative_path <<< "${leaf}"
  safe_id=$(printf '%s' "${case_id}" | tr '/:' '__')
  prefix=$(printf '%03d_%s' "${index}" "${safe_id}")
  build_log=${run_dir}/${prefix}.build.log
  spike_log=${run_dir}/${prefix}.spike.log
  ara_log=${run_dir}/${prefix}.ara.log
  vcs_log=${run_dir}/${prefix}.vcs.log
  spike_status=SKIP
  ara_status=SKIP
  elf_bytes=0

  echo "== ${case_id} =="
  clean_case

  if [[ ${mode} != --ara-only ]]; then
    if build_spike "${case_id}" >"${build_log}" 2>&1; then
      if timeout --foreground "${spike_timeout}" "${spike}" \
          --isa=rv64gcv_zfh --varch="vlen:1024,elen:64" \
          "${apps_dir}/bin/${app}.spike" >"${spike_log}" 2>&1; then
        spike_status=PASS
      else
        rc=$?
        spike_status=$([[ ${rc} -eq 124 ]] && echo TIMEOUT || echo FAIL)
        overall=1
      fi
    else
      spike_status=BUILD_FAIL
      overall=1
    fi
  fi

  if [[ ${mode} != --spike-only && (${mode} == --ara-only || ${spike_status} == PASS) ]]; then
    rm -f "${app_dir}/data.S.o" "${apps_dir}/bin/${app}"
    if build_ara "${case_id}" >>"${build_log}" 2>&1; then
      elf_bytes=$(stat -c %s "${apps_dir}/bin/${app}")
      if timeout --foreground "${ara_timeout}" "${simv}" \
          -l "${vcs_log}" +fsdb+power +fsdb+all \
          +PRELOAD="${apps_dir}/bin/${app}" +TESTCASE="${app}" +NO_FSDB \
          >"${ara_log}" 2>&1; then
        if grep -q 'Core Test \*\*\* SUCCESS' "${ara_log}" &&
           grep -q "LLAMA_OPERATOR ${case_id} PASS" "${ara_log}"; then
          ara_status=PASS
        else
          ara_status=FAIL
          overall=1
        fi
      else
        rc=$?
        ara_status=$([[ ${rc} -eq 124 ]] && echo TIMEOUT || echo FAIL)
        overall=1
      fi
    else
      ara_status=BUILD_FAIL
      overall=1
    fi
  fi

  printf '%s\t%s\t%s\t%s\t%s\n' \
    "${case_id}" "${spike_status}" "${ara_status}" "${elf_bytes}" "${prefix}" \
    >> "${run_dir}/summary.tsv"
  echo "   Spike=${spike_status} Ara=${ara_status} ELF=${elf_bytes}"
  index=$((index + 1))
done

echo "results: ${run_dir}"
exit "${overall}"
