#!/usr/bin/env bash
# ============================================================================
# Unified one-click HDV kernel sweep.
#
#   ./kernel_sweep.sh [1d|blas|fixed|all]   (default: all)
#
# Three groups:
#   1d    — 1D streaming kernels + vsdwt, swept over AVL 32..4096 (continuous
#           scaling curve).  Delegates to avl_sweep.sh.
#   blas  — range-sweepable matrix kernels:
#             vssymv/vsgemv : sweep TOTAL elements (a3 = rows*VLMAX) 1K..16K
#             vsger         : sweep N  32/64/128
#             vsgemm        : sweep N  32/64/128 (quadratic work -> big watchdog)
#   fixed — kernels that don't sweep cleanly (quadratic/strided/app-shaped):
#           run ONE typical larger size each.  vstrsm/vssyrk (N x N),
#           fconv2d/jacobi2d/lavamd/softmax (typical app size).
#
# Big-N / quadratic kernels exceed the default 65536 task watchdog, so this
# script raises it via +HDV_TASK_WATCHDOG.  Those points are SLOW (vsgemm N=128
# ~30 min of sim); budget time when running the blas/fixed groups.
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")"                       # hardware/
APPS=../apps
WD=400000                                  # task watchdog for quadratic-work kernels
SIM_TIMEOUT=3600                           # per-sim wall cap (big N takes ~30 min)
OUT=kernel_sweep_out
mkdir -p "$OUT"
SUMMARY="$OUT/summary.txt"
: > "$SUMMARY"

addr_of() { local h; h=$(grep -E "[0-9a-f]+ [A-Za-z] $2\$" "$APPS/$1/$1.dump" 2>/dev/null | head -1 | awk '{print $1}'); [ -n "$h" ] && printf '%d' "0x$h"; }

# run <app> <plusargs> <tag> <label>
run() {
  local app=$1 pa=$2 tag=$3 label=$4 log="$OUT/$3.log"
  ( timeout "$SIM_TIMEOUT" make sim app="$app" hdv_plusargs="$pa +HDV_EXPECTED_EP=8000000" >"$log" 2>&1 )
  local r c
  r=$(grep -iE 'mock host' "$log" | grep -oE 'PASSED|FAILED' | head -1)
  c=$(grep -iE 'mock host' "$log" | grep -oE 'cycle=[0-9]+' | grep -oE '[0-9]+' | head -1)
  printf "%-34s %-7s cyc=%s\n" "$label" "${r:-TIMEOUT}" "${c:-NA}" | tee -a "$SUMMARY"
}

MODE="${1:-all}"

# ---------------- Group 1: 1D + vsdwt (AVL 32..4096) ----------------
if [ "$MODE" = 1d ] || [ "$MODE" = all ]; then
  echo "########## Group 1: 1D 流式核 + vsdwt (AVL 32..4096) ##########" | tee -a "$SUMMARY"
  ./avl_sweep.sh all "32 64 128 256 512 1024 2048 4096"
  echo "  -> avl_sweep_out/all.csv" | tee -a "$SUMMARY"
fi

# ---------------- Group 2: BLAS-2 / GEMM range sweep ----------------
if [ "$MODE" = blas ] || [ "$MODE" = all ]; then
  echo "########## Group 2: BLAS-2 总元素扫 + vsger/vsgemm N 扫 ##########" | tee -a "$SUMMARY"
  for k in vssymv vsgemv; do
    ( cd "$APPS" && make bin/${k}_hdv blas_lmul=4 >/dev/null 2>&1 )
    s1=$(addr_of ${k}_hdv src1); s2=$(addr_of ${k}_hdv src2)
    for tot in 1024 2048 4096 8192 16384; do
      if [ "$k" = vssymv ]; then pa="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$s1 +HDV_A3=$tot"
      else pa="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$((s2+512)) +HDV_A3=$tot"; fi
      run ${k}_hdv "$pa" "${k}_t${tot}" "${k} m4 total=${tot}"
    done
  done
  ( cd "$APPS" && make bin/vsger_hdv blas_lmul=4 >/dev/null 2>&1 )
  s1=$(addr_of vsger_hdv src1); s2=$(addr_of vsger_hdv src2)
  for N in 32 64 128; do
    run vsger_hdv "+HDV_A0=32 +HDV_A1=$N +HDV_A2=$s2 +HDV_A3=$((s2+512)) +HDV_A4=$s1" "vsger_N${N}" "vsger  m4 N=${N}"
  done
  ( cd "$APPS" && make bin/vsgemm_hdv gemm_lmul=4 gemm_rows=4 >/dev/null 2>&1 )
  s1=$(addr_of vsgemm_hdv src1); s2=$(addr_of vsgemm_hdv src2)
  for N in 32 64 128; do
    run vsgemm_hdv "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A3=$N +HDV_TASK_WATCHDOG=$WD" "vsgemm_N${N}" "vsgemm m4 4row N=${N}"
  done
fi

# ---------------- Group 3: fixed-size kernels ----------------
if [ "$MODE" = fixed ] || [ "$MODE" = all ]; then
  echo "########## Group 3: 固定尺寸核(典型规模,大看门狗)##########" | tee -a "$SUMMARY"

  ( cd "$APPS" && make bin/vstrsm_hdv blas_lmul=4 >/dev/null 2>&1 )
  s1=$(addr_of vstrsm_hdv src1); s2=$(addr_of vstrsm_hdv src2)
  run vstrsm_hdv "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=32 +HDV_TASK_WATCHDOG=$WD" "vstrsm_fix" "vstrsm m4 32x32"

  ( cd "$APPS" && make bin/vssyrk_hdv blas_lmul=1 >/dev/null 2>&1 )
  s1=$(addr_of vssyrk_hdv src1); s2=$(addr_of vssyrk_hdv src2)
  run vssyrk_hdv "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=32 +HDV_TASK_WATCHDOG=$WD" "vssyrk_fix" "vssyrk m1 32x32 (strided)"

  ( cd "$APPS" && make bin/fconv2d_hdv >/dev/null 2>&1 )
  o=$(addr_of fconv2d_hdv o); i=$(addr_of fconv2d_hdv i); f=$(addr_of fconv2d_hdv f)
  run fconv2d_hdv "+HDV_A0=$o +HDV_A1=$i +HDV_A2=$f +HDV_A3=64 +HDV_A4=32 +HDV_A5=3 +HDV_TASK_WATCHDOG=$WD" "fconv2d_fix" "fconv2d 3x3 e64 R64xC32"

  ( cd "$APPS" && make bin/jacobi2d_hdv >/dev/null 2>&1 )
  av=$(addr_of jacobi2d_hdv A_v); bv=$(addr_of jacobi2d_hdv B_v)
  run jacobi2d_hdv "+HDV_A0=128 +HDV_A1=64 +HDV_A2=$av +HDV_A3=$bv +HDV_TASK_WATCHDOG=$WD" "jacobi2d_fix" "jacobi2d 5pt e64 128x64"

  ( cd "$APPS" && make bin/lavamd_hdv >/dev/null 2>&1 )
  bx=$(addr_of lavamd_hdv bx); by=$(addr_of lavamd_hdv by); bz=$(addr_of lavamd_hdv bz)
  lbv=$(addr_of lavamd_hdv bv); bq=$(addr_of lavamd_hdv bq); ap=$(addr_of lavamd_hdv aparams); fo=$(addr_of lavamd_hdv fout_v)
  run lavamd_hdv "+HDV_A0=$bx +HDV_A1=$by +HDV_A2=$bz +HDV_A3=$lbv +HDV_A4=$bq +HDV_A5=$ap +HDV_A6=$fo +HDV_A7=256 +HDV_TASK_WATCHDOG=$WD" "lavamd_fix" "lavamd N-body NPAR=256"

  ( cd "$APPS" && make bin/softmax_hdv >/dev/null 2>&1 )
  si=$(addr_of softmax_hdv i); so=$(addr_of softmax_hdv o_v)
  run softmax_hdv "+HDV_A0=$si +HDV_A1=$so +HDV_A2=3 +HDV_A3=256 +HDV_TASK_WATCHDOG=$WD" "softmax_fix" "softmax ch3 x inner256"
fi

echo ""
echo "==== 汇总写入 $OUT/summary.txt ===="
