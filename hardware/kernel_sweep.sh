#!/usr/bin/env bash
# ============================================================================
# Unified ONE-CLICK HDV kernel sweep — covers EVERY existing hdv kernel config.
#
#   ./kernel_sweep.sh [1d|blas|fixed|all]   (default: all)
#
# A single `all` run touches every configured kernel variant that exists, by
# orchestrating the two sweep engines + a fixed/app group:
#
#   1d    — avl_sweep.sh:  9 active 1D streaming kernels (vsaxpy/vvaddint32/
#           vscopy/vsswap/vsdot/vsscal/vmc/dropout/vsdwt, AVL 32..4096).
#           fdotp and vspf are excluded from active testing.
#   blas  — blas_sweep.sh: BLAS-2/3 m4 dim sweep (vsger/vssymv/vssyrk/vstrsm/vsgemv)
#                        + m2/4/8 prefetch sweep (vssymv/vsgemv/vstrsm)
#                        + vsgemm {m1,m4} x {rows 1/2/4} x N.
#   fixed — app-shaped + sparse: fconv2d/jacobi2d/lavamd/softmax
#                        + vsspmv (sparse 32x32)
#                        + vssyrk/vstrsm m1 fixed points (the m1 variant the BLAS
#                          dim/pf sweeps don't cover).
#
# Excluded (no such config exists): fmatmul (== sgemm, deferred by request),
# vgemm/vsfft (stubs, no kernel).  NOTE: vssyrk fails on hdv at every LMUL
# (m1/m2/m4/m8 all hit task_error/watchdog — WAR-hazard + strided vlse); its
# points are kept for 1:1 parity with asm_sweep and record as FAILED rows.
#
# Outputs: avl_sweep_out/*.csv + blas_sweep_out/*.csv (full per-point metrics)
# and kernel_sweep_out/summary.txt (the fixed group's pass/cycles table).
# Big-N / quadratic points use +HDV_TASK_WATCHDOG; budget time (vsgemm N=128 etc.).
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")"                       # hardware/
APPS=../apps
WD=400000
SIM_TIMEOUT=3600
OUT=kernel_sweep_out
mkdir -p "$OUT"
SUMMARY="$OUT/summary.txt"; : > "$SUMMARY"

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

# ---------------- Group 1: active 1D kernels (avl_sweep engine) ----------------
if [ "$MODE" = 1d ] || [ "$MODE" = all ]; then
  echo "########## Group 1: active 1D 流式核 (AVL 扫) ##########" | tee -a "$SUMMARY"
  ./avl_sweep.sh all       "32 64 128 256 512 1024 2048 4096"   # 9 个 1D 核(含 vsdwt)
  echo "  -> avl_sweep_out/*.csv" | tee -a "$SUMMARY"
fi

# ---------------- Group 2: BLAS 全 LMUL + GEMM (blas_sweep engine) ----------------
if [ "$MODE" = blas ] || [ "$MODE" = all ]; then
  echo "########## Group 2: BLAS-2/3 全 LMUL + GEMM ##########" | tee -a "$SUMMARY"
  ./blas_sweep.sh blas    "16 32 64 128"   # m4 维度扫: vsger/vssymv/vssyrk/vstrsm/vsgemv
  ./blas_sweep.sh blas_pf "32 64"          # m2/4/8 预取扫: vssymv/vsgemv/vstrsm
  ./blas_sweep.sh vsgemm  "16 32 64 128"   # vsgemm {m1,m4} x {rows 1/2/4} x N

  # ── asm 对齐补点:asm_sweep 有、hdv 之前没扫的 4 个 LMUL 配置 ──────────────
  # vssymv/vsgemv m1(固定 32x32,实测 PASS) + vssyrk m2/m8。
  # 注意:vssyrk 在 hdv 上**任何** LMUL 都跑不通(m1/m4 历史亦 FAILED,m2/m8 实测
  # task_error=1 撞看门狗 — WAR 冒险阻塞几乎全程 + strided vlse 热点)。这两点保留
  # 是为了与 asm_sweep 一一对应、完整记录,产出的就是 FAILED 行(非有效性能数据)。
  # 每点独立隔离:build 失败 → BUILD_FAIL 跳过;sim 失败/超时 → run() 的 subshell+
  # timeout 兜住,标 FAILED/TIMEOUT 后继续。脚本无 set -e,一点失败不影响其它点。
  if ( cd "$APPS" && rm -f vssymv_hdv/main.c.o && make bin/vssymv_hdv blas_lmul=1 >/dev/null 2>&1 ); then
    s1=$(addr_of vssymv_hdv src1); s2=$(addr_of vssymv_hdv src2)
    run vssymv_hdv "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$s1 +HDV_A3=32 +HDV_TASK_WATCHDOG=$WD" "vssymv_m1" "vssymv m1 32x32"
  else printf "%-34s %s\n" "vssymv m1" BUILD_FAIL | tee -a "$SUMMARY"; fi
  if ( cd "$APPS" && rm -f vsgemv_hdv/main.c.o && make bin/vsgemv_hdv blas_lmul=1 >/dev/null 2>&1 ); then
    s1=$(addr_of vsgemv_hdv src1); s2=$(addr_of vsgemv_hdv src2)
    run vsgemv_hdv "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$((s2+512)) +HDV_A3=32 +HDV_TASK_WATCHDOG=$WD" "vsgemv_m1" "vsgemv m1 32x128"
  else printf "%-34s %s\n" "vsgemv m1" BUILD_FAIL | tee -a "$SUMMARY"; fi
  for lm in 2 8; do
    if ( cd "$APPS" && rm -f vssyrk_hdv/main.c.o && make bin/vssyrk_hdv blas_lmul=$lm >/dev/null 2>&1 ); then
      s1=$(addr_of vssyrk_hdv src1); s2=$(addr_of vssyrk_hdv src2)
      for n in 32 64 128; do
        run vssyrk_hdv "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$n +HDV_TASK_WATCHDOG=$WD" "vssyrk_m${lm}_n${n}" "vssyrk m${lm} N=${n}"
      done
    else printf "%-34s %s\n" "vssyrk m${lm}" BUILD_FAIL | tee -a "$SUMMARY"; fi
  done

  echo "  -> blas_sweep_out/*.csv" | tee -a "$SUMMARY"
fi

# ---------------- Group 3: 固定/应用核 + vsspmv + m1 单点 ----------------
if [ "$MODE" = fixed ] || [ "$MODE" = all ]; then
  echo "########## Group 3: 固定尺寸/应用核(大看门狗)##########" | tee -a "$SUMMARY"

  # vssyrk / vstrsm 的 m1 固定点(blas_sweep 只扫 m4 / m2-4-8,m1 在这补)
  ( cd "$APPS" && make bin/vssyrk_hdv blas_lmul=1 >/dev/null 2>&1 )
  s1=$(addr_of vssyrk_hdv src1); s2=$(addr_of vssyrk_hdv src2)
  run vssyrk_hdv "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=32 +HDV_TASK_WATCHDOG=$WD" "vssyrk_m1_fix" "vssyrk m1 32x32 (strided)"
  ( cd "$APPS" && make bin/vstrsm_hdv blas_lmul=1 >/dev/null 2>&1 )
  s1=$(addr_of vstrsm_hdv src1); s2=$(addr_of vstrsm_hdv src2)
  run vstrsm_hdv "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=32 +HDV_TASK_WATCHDOG=$WD" "vstrsm_m1_fix" "vstrsm m1 32x32"

  # vsspmv 稀疏 32x32(a0=val a1=col_idx a2=x a3=y;指针也在 Makefile InitialA 里烘了)
  ( cd "$APPS" && make bin/vsspmv_hdv >/dev/null 2>&1 )
  s1=$(addr_of vsspmv_hdv src1); s2=$(addr_of vsspmv_hdv src2); ci=$(addr_of vsspmv_hdv col_idx)
  run vsspmv_hdv "+HDV_A0=$s1 +HDV_A1=$ci +HDV_A2=$s2 +HDV_A3=$((s2+256)) +HDV_TASK_WATCHDOG=$WD" "vsspmv_fix" "vsspmv sparse 32x32"

  # 应用形状核
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
echo "==== 汇总 -> $OUT/summary.txt ; 详细 CSV -> avl_sweep_out/ + blas_sweep_out/ ===="
