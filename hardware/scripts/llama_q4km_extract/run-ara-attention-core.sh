#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
apps_dir=${repo_root}/apps
app=llama_q4km_operator
case_id=${LLAMA_ATTN_CASE_ID:-operator/decode/attention_core}
implementation=${1:-rvv}
kvlen=16
execution=--all
if [[ ${2:-} == --* ]]; then
  execution=$2
elif [[ -n ${2:-} ]]; then
  kvlen=$2
  execution=${3:---all}
fi
default_sim_dir=${repo_root}/hardware/sim_llama_attention_16m_template
if [[ ${implementation} == akv ]]; then
  default_sim_dir=${repo_root}/hardware/sim_akv_m3_compile
elif [[ ${implementation} == akv_v2 ||
        ${implementation} == akv_v2_prefill ]]; then
  default_sim_dir=${repo_root}/hardware/sim_akv_v2_compile
fi
sim_dir=${LLAMA_ATTN_SIM_DIR:-${default_sim_dir}}
simv=${sim_dir}/simv
l2_contract_checker=${repo_root}/hardware/scripts/llama_q4km_extract/check-sim-l2.sh
run_root=${LLAMA_ATTN_RUN_ROOT:-${repo_root}/hardware/llama_attention_runs}
build_lock=${apps_dir}/bin/.llama-q4km-operator-build.lock
spike=${SPIKE:-${repo_root}/install/riscv-isa-sim/bin/spike}
spike_timeout=${LLAMA_ATTN_SPIKE_TIMEOUT:-600}
ara_timeout=${LLAMA_ATTN_ARA_TIMEOUT:-14400}
capture_root=${Q4KM_CAPTURE_ROOT:-}
if [[ -z ${capture_root} ]]; then
  capture_set=/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-latest
  if [[ -d ${capture_set}/kv${kvlen} ]]; then
    capture_root=${capture_set}/kv${kvlen}
  elif [[ ${kvlen} == 16 ]]; then
    capture_root=/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m
  else
    echo "missing capture for effective KV length ${kvlen}: ${capture_set}/kv${kvlen}" >&2
    exit 1
  fi
fi
export Q4KM_CAPTURE_ROOT=${capture_root}
if [[ -f ${capture_root}/run.conf ]]; then
  captured_kv=$(sed -n 's/^effective_kv=//p' "${capture_root}/run.conf" | tail -n 1)
  if [[ -n ${captured_kv} && ${captured_kv} != "${kvlen}" ]]; then
    echo "capture effective KV ${captured_kv} does not match requested KV ${kvlen}: ${capture_root}" >&2
    exit 2
  fi
fi
if [[ -f ${capture_root}/replay/manifest.json ]]; then
  captured_kv=$(jq -r '.topology.active_kv // .effective_kv // empty' \
    "${capture_root}/replay/manifest.json")
  if [[ -n ${captured_kv} && ${captured_kv} != "${kvlen}" ]]; then
    echo "capture effective KV ${captured_kv} does not match requested KV ${kvlen}: ${capture_root}" >&2
    exit 2
  fi
fi
stamp=$(date +%Y%m%d_%H%M%S)
run_dir=${run_root}/decode_attention_core_${implementation}_kv${kvlen}_${stamp}
testcase=llama_q4km_decode_attention_core_${implementation}_kv${kvlen}

if [[ ${implementation} != ref && ${implementation} != rvv &&
      ${implementation} != tiled_rvv && ${implementation} != q64_rvv &&
      ${implementation} != akv &&
      ${implementation} != akv_v2 &&
      ${implementation} != akv_v2_prefill ]]; then
  echo "usage: $0 [ref|rvv|tiled_rvv|q64_rvv|akv|akv_v2|akv_v2_prefill] [KV_LENGTH] [--all|--spike-only|--ara-only]" >&2
  exit 2
fi
if [[ ! ${kvlen} =~ ^[1-9][0-9]*$ ]] || (( kvlen > 65535 )); then
  echo "unsupported effective KV length: ${kvlen}" >&2
  exit 2
fi
if [[ ${execution} != --all && ${execution} != --spike-only &&
      ${execution} != --ara-only ]]; then
  echo "usage: $0 [ref|rvv|tiled_rvv|q64_rvv|akv|akv_v2|akv_v2_prefill] [KV_LENGTH] [--all|--spike-only|--ara-only]" >&2
  exit 2
fi
if [[ (${implementation} == akv || ${implementation} == akv_v2 ||
       ${implementation} == akv_v2_prefill) &&
      ${execution} != --ara-only ]]; then
  echo "AKV custom instructions currently require --ara-only; use ref or rvv for Spike" >&2
  exit 2
fi
if [[ ! -x ${spike} ]]; then
  echo "missing Spike executable: ${spike}" >&2
  exit 1
fi
if [[ ${execution} != --spike-only && ! -x ${simv} ]]; then
  echo "missing Ara simulator: ${simv}" >&2
  exit 1
fi

source_commit=$(git -C "${repo_root}" rev-parse HEAD)
source_dirty=false
if ! git -C "${repo_root}" diff-index --quiet HEAD --; then
  source_dirty=true
fi
capture_manifest_sha256=missing
if [[ -f ${capture_root}/tensor.sha256 ]]; then
  capture_manifest_sha256=$(sha256sum -- "${capture_root}/tensor.sha256" | awk '{print $1}')
elif [[ -f ${capture_root}/replay/manifest.json ]]; then
  capture_manifest_sha256=$(sha256sum -- \
    "${capture_root}/replay/manifest.json" | awk '{print $1}')
fi
simv_sha256=not-applicable
if [[ ${execution} != --spike-only ]]; then
  simv_sha256=$(sha256sum -- "${simv}" | awk '{print $1}')
fi

mkdir -p "${run_dir}" "${apps_dir}/bin"
ln -sfn "${run_dir}" "${run_root}/decode_attention_core_${implementation}_latest"
ln -sfn "${run_dir}" "${run_root}/decode_attention_core_${implementation}_kv${kvlen}_latest"
printf 'implementation=%s\ncase_id=%s\nsimv=%s\n' \
  "${implementation}" "${case_id}" "${simv}" > "${run_dir}/run.conf"
printf 'effective_kv=%s\ncapture_root=%s\nsource_commit=%s\nsource_dirty=%s\n' \
  "${kvlen}" "${capture_root}" "${source_commit}" "${source_dirty}" \
  >> "${run_dir}/run.conf"
printf 'capture_manifest_sha256=%s\nsimv_sha256=%s\n' \
  "${capture_manifest_sha256}" "${simv_sha256}" >> "${run_dir}/run.conf"

# Data generation and application objects are shared by all invocations. Keep
# this section atomic so ref and RVV simulations may run concurrently without
# snapshotting an ELF generated for the other implementation.
(
  flock 9
  make -C "${apps_dir}" "bin/${app}.spike" \
    "def_args_${app}=\"${case_id} ${implementation}\"" \
    > "${run_dir}/build_spike.log" 2>&1
  cp "${apps_dir}/bin/${app}.spike" \
    "${run_dir}/${app}.${implementation}.spike"
  cp "${apps_dir}/bin/${app}.spike.dump" \
    "${run_dir}/${app}.${implementation}.spike.dump"
  printf 'spike_elf_sha256=%s\n' \
    "$(sha256sum -- "${run_dir}/${app}.${implementation}.spike" | awk '{print $1}')" \
    >> "${run_dir}/run.conf"

  if [[ ${execution} != --spike-only ]]; then
    make -C "${apps_dir}" "${app}" sim_l2_mb=16 \
      "def_args_${app}=\"${case_id} ${implementation}\"" \
      > "${run_dir}/build_ara.log" 2>&1
    cp "${apps_dir}/bin/${app}" "${run_dir}/${app}.${implementation}.elf"
    cp "${apps_dir}/${app}/${app}.dump" \
      "${run_dir}/${app}.${implementation}.dump"
    printf 'ara_elf_sha256=%s\n' \
      "$(sha256sum -- "${run_dir}/${app}.${implementation}.elf" | awk '{print $1}')" \
      >> "${run_dir}/run.conf"
    l2_contract=$("${l2_contract_checker}" "${sim_dir}" \
      "${run_dir}/${app}.${implementation}.elf")
    printf '%s\n' "${l2_contract}" >> "${run_dir}/run.conf"
  fi
) 9> "${build_lock}"

if [[ ${execution} != --ara-only ]]; then
  timeout --foreground "${spike_timeout}" "${spike}" \
    --isa=rv64gcv_zfh --varch="vlen:1024,elen:64" \
    "${run_dir}/${app}.${implementation}.spike" \
    > "${run_dir}/spike.log" 2>&1
fi

if [[ ${execution} != --spike-only ]]; then
  sim_args=(
    -no_save
    -l vcs.log
    "+PRELOAD=${run_dir}/${app}.${implementation}.elf"
    "+TESTCASE=${testcase}"
    +NO_FSDB
  )
  if [[ ${implementation} == akv || ${implementation} == akv_v2 ||
        ${implementation} == akv_v2_prefill ]]; then
    sim_args+=(+AKV_PERF)
  fi
  if [[ -n ${LLAMA_ATTN_EXTRA_SIM_ARGS:-} ]]; then
    read -r -a extra_sim_args <<< "${LLAMA_ATTN_EXTRA_SIM_ARGS}"
    sim_args+=("${extra_sim_args[@]}")
  fi
  (
    cd "${run_dir}"
    timeout --foreground "${ara_timeout}" "${simv}" \
      "${sim_args[@]}" > ara.log 2>&1
  )
  grep -q 'Core Test \*\*\* SUCCESS' "${run_dir}/ara.log"
  grep -q "LLAMA_OPERATOR ${case_id}/${implementation} PASS" \
    "${run_dir}/ara.log"
fi

: > "${run_dir}/complete"
echo "results: ${run_dir}"
