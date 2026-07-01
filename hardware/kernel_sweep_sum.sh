#!/usr/bin/env bash
# Rebuild kernel_sweep_out/kernel_sweep.csv from per-point sweep logs.
#
# Usage:
#   ./kernel_sweep_sum.sh [1d|blas|gemm|fixed|all] [csv_path]
#
# This is useful after rerunning only a subset of kernels: the newest
# *_real.log / *_ideal.log files become the source of truth, and the CSV is
# regenerated without rerunning simulations.
set -uo pipefail

cd "$(dirname "$0")"
HW="$(pwd)"
OUT="$HW/kernel_sweep_out"
CSV="${2:-$OUT/kernel_sweep.csv}"

HDR="kernel,tag,avl,blas_lmul,gemm_rows,ideal_rvv_cycles,ideal_lane_util,real_total_cycles,real_rvv_cycles,real_vector_insns,real_insns,real_ipc,hw_cycles,dcache_stalls,icache_stalls,sb_full,axi_ar,axi_r,axi_aw,axi_w,axi_b"

pf() {
  grep -E "\[PERF\] $2[ ]*:" "$1" 2>/dev/null | tail -1 | sed -E 's/.*:[ ]*//; s/[ ]*$//'
}

st() {
  grep -F "$2" "$1" 2>/dev/null | tail -1 | grep -oE '[0-9]+' | tail -1
}

has_timeout() {
  grep -qE "SIM_TIMEOUT|LOG_LIMIT|TIMEOUT/FAIL" "$1" 2>/dev/null
}

has_build_fail() {
  grep -q "BUILD_FAIL" "$1" 2>/dev/null
}

real_na() {
  echo "NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA"
}

real_timeout() {
  echo "TIMEOUT,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA"
}

real_build_fail() {
  echo "BUILD_FAIL,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA"
}

declare -A OLD_IDEAL OLD_REAL
if [ -f "$CSV" ]; then
  while IFS=, read -r kernel tag avl bl gr ideal_rvv ideal_util real_total real_rvv real_vinsns real_insns real_ipc hw dc ic sb ar r aw w b; do
    [ "$kernel" = "kernel" ] && continue
    key="$kernel|$tag"
    OLD_IDEAL["$key"]="$ideal_rvv,$ideal_util"
    OLD_REAL["$key"]="$real_total,$real_rvv,$real_vinsns,$real_insns,$real_ipc,$hw,$dc,$ic,$sb,$ar,$r,$aw,$w,$b"
  done <"$CSV"
fi

merge_real_with_old() {
  local cur="$1" old="$2" i
  local -a c o

  if [ -z "$old" ]; then
    echo "$cur"
    return
  fi

  IFS=, read -r -a c <<<"$cur"
  case "${c[0]:-}" in
    NA|TIMEOUT|BUILD_FAIL)
      echo "$cur"
      return
      ;;
  esac

  IFS=, read -r -a o <<<"$old"
  for i in 9 10 11 12 13; do
    if [ -z "${c[$i]:-}" ] || [ "${c[$i]:-}" = "NA" ]; then
      c[$i]="${o[$i]:-${c[$i]:-NA}}"
    fi
  done

  (IFS=,; echo "${c[*]}")
}

summarize_ideal() {
  local log="$1" total util

  if [ ! -f "$log" ]; then
    echo "NA,NA"
    return
  fi
  if has_build_fail "$log"; then
    echo "BUILD_FAIL,NA"
    return
  fi
  if has_timeout "$log"; then
    echo "TIMEOUT,NA"
    return
  fi
  if grep -q "Fatal:" "$log" 2>/dev/null; then
    echo "TIMEOUT,NA"
    return
  fi

  total="$(pf "$log" total_rvv_cycles)"
  util="$(pf "$log" 'lane utilization')"
  echo "${total:-NA},${util:-NA}"
}

summarize_real() {
  local log="$1"
  local total rvv vinsns insns ipc hw dc ic sb ar r aw w b

  if [ ! -f "$log" ]; then
    real_na
    return
  fi
  if has_build_fail "$log"; then
    real_build_fail
    return
  fi
  if has_timeout "$log"; then
    real_timeout
    return
  fi
  if grep -q "Fatal:" "$log" 2>/dev/null; then
    real_timeout
    return
  fi

  total="$(pf "$log" total_cycles)"
  rvv="$(pf "$log" total_rvv_cycles)"
  vinsns="$(pf "$log" total_vector_insns)"
  insns="$(pf "$log" total_insns)"
  ipc="$(pf "$log" IPC)"
  hw="$(st "$log" '[hw-cycles]')"
  dc="$(st "$log" '[cva6-d$-stalls]')"
  ic="$(st "$log" '[cva6-i$-stalls]')"
  sb="$(st "$log" '[cva6-sb-full]')"
  ar="$(pf "$log" rvv_axi_ar_count)"
  r="$(pf "$log" rvv_axi_r_count)"
  aw="$(pf "$log" rvv_axi_aw_count)"
  w="$(pf "$log" rvv_axi_w_count)"
  b="$(pf "$log" rvv_axi_b_count)"

  echo "${total:-NA},${rvv:-NA},${vinsns:-NA},${insns:-NA},${ipc:-NA},${hw},${dc},${ic},${sb},${ar:-NA},${r:-NA},${aw:-NA},${w:-NA},${b:-NA}"
}

GROUP="${1:-all}"
AVLS_1D="${AVLS_1D:-32 64 128 256 512 1024 2048 4096}"
AVLS_BLAS="${AVLS_BLAS:-32 64 128}"
BLAS_LMULS="${BLAS_LMULS:-2 4 8}"
GEMM_ROWS_L="${GEMM_ROWS_L:-1 2 4}"

gen_points() {
  local g=$1 k a L r
  if [ "$g" = 1d ] || [ "$g" = all ]; then
    for k in ${KERNELS_1D:-vsaxpy vscopy vsswap vsdot vsscal vvaddint32 vmc vsdwt}; do
      for a in $AVLS_1D; do echo "${k}_asm|avl${a}|$a|||"; done
    done
  fi
  if [ "$g" = blas ] || [ "$g" = all ]; then
    for k in ${KERNELS_BLAS:-vssymv vsgemv vssyrk vstrsm}; do
      echo "${k}_asm|m1|32|1||"
      for L in $BLAS_LMULS; do
        for a in $AVLS_BLAS; do echo "${k}_asm|m${L}_avl${a}|$a|$L||"; done
      done
    done
    for a in 32 64 128; do echo "vsger_asm|n${a}|$a|||"; done
  fi
  if [ "$g" = gemm ] || [ "$g" = all ]; then
    for r in $GEMM_ROWS_L; do echo "vsgemm_asm|m1_${r}row|32|1|$r|"; done
    for r in $GEMM_ROWS_L; do
      for a in $AVLS_BLAS; do echo "vsgemm_asm|m4_${r}row_avl${a}|$a|4|$r|"; done
    done
  fi
  if [ "$g" = fixed ] || [ "$g" = all ]; then
    echo "vsspmv_asm|fixed32|1024|||"
  fi
}

if [ ! -d "$OUT" ]; then
  echo "error: missing output directory: $OUT" >&2
  exit 1
fi

tmp="${CSV}.tmp"
mkdir -p "$(dirname "$CSV")"
echo "$HDR" >"$tmp"

while IFS='|' read -r app tag avl bl gr _; do
  [ -z "$app" ] && continue
  key="$app|$tag"
  ideal="$(summarize_ideal "$OUT/${app}__${tag}__ideal.log")"
  real="$(summarize_real "$OUT/${app}__${tag}__real.log")"
  if [ "$ideal" = "NA,NA" ] && [ -n "${OLD_IDEAL[$key]:-}" ]; then
    ideal="${OLD_IDEAL[$key]}"
  fi
  if [ "$real" = "$(real_na)" ] && [ -n "${OLD_REAL[$key]:-}" ]; then
    real="${OLD_REAL[$key]}"
  else
    real="$(merge_real_with_old "$real" "${OLD_REAL[$key]:-}")"
  fi
  echo "$app,$tag,$avl,$bl,$gr,$ideal,$real" >>"$tmp"
done < <(gen_points "$GROUP")

mv "$tmp" "$CSV"
echo "wrote $CSV"
