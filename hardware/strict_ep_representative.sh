#!/usr/bin/env bash
# Run the paper workload points with the suffixed *_hdv_1 apps.
#
# Full paper point set:
#   HDV_ABLATION=full ./strict_ep_representative.sh all
#
# Seven-point paper ablation set for one hardware configuration:
#   HDV_ABLATION=base|pf|haz|pf_haz ./strict_ep_representative.sh ablation
set -uo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
cd "$SCRIPT_DIR"

APPS=../apps
HDV_ABLATION="${HDV_ABLATION:-full}"
HDV_SRC_LIFETIME="${HDV_SRC_LIFETIME:-1}"
case "$HDV_ABLATION" in
  full|base|vdu|pf|pf_only|ovlp|haz|pf_haz) ;;
  *)
    echo "ERROR: invalid HDV_ABLATION=$HDV_ABLATION" >&2
    exit 2
    ;;
esac
case "$HDV_SRC_LIFETIME" in
  0|1) ;;
  *)
    echo "ERROR: invalid HDV_SRC_LIFETIME=$HDV_SRC_LIFETIME (use 0 or 1)" >&2
    exit 2
    ;;
esac

DEFAULT_OUT=kernel_sweep_out_hdv1_paper
DEFAULT_SIM_DIR=sim_strict_ep
if [ "$HDV_ABLATION" != "full" ]; then
  DEFAULT_OUT="${DEFAULT_OUT}_${HDV_ABLATION}"
  DEFAULT_SIM_DIR="${DEFAULT_SIM_DIR}_${HDV_ABLATION}"
fi
OUT="${STRICT_EP_OUT:-$DEFAULT_OUT}"
SIM_DIR="${STRICT_EP_SIM_DIR:-$DEFAULT_SIM_DIR}"
MODE="${1:-short}"
PAPER_AVLS="${STRICT_EP_AVLS:-32 64 128 256 512 1024 2048 4096}"
REMAINING_AVLS="${STRICT_EP_REMAINING_AVLS:-32 64 128 256 512 2048 4096}"
mkdir -p "$OUT"

addr_of() {
  local app=$1 symbol=$2 hex
  hex=$(grep -E "[0-9a-f]+ [A-Za-z] ${symbol}\$" "$APPS/$app/$app.dump" |
        head -1 | awk '{print $1}')
  [ -n "$hex" ] || return 1
  printf '%d' "0x$hex"
}

build_all() {
  # These objects depend on command-line variant selectors that Make cannot
  # infer from timestamps. Rebuild them before selecting the paper variants.
  rm -f \
    "$APPS/vstrsm_hdv_1/main.c.o" \
    "$APPS/vsgemv_hdv_1/main.c.o" \
    "$APPS/vssymv_hdv_1/main.c.o" \
    "$APPS/vsgemm_hdv_1/main.c.o" \
    "$APPS/vssyrk_hdv_1/main.c.o" \
    "$APPS/bin/vstrsm_hdv_1" \
    "$APPS/bin/vsgemv_hdv_1" \
    "$APPS/bin/vssymv_hdv_1" \
    "$APPS/bin/vsgemm_hdv_1" \
    "$APPS/bin/vssyrk_hdv_1"

  make -C "$APPS" -j4 \
    bin/vsaxpy_hdv_1 bin/vsdot_hdv_1 bin/vsswap_hdv_1 \
    bin/vsdwt_hdv_1 bin/vstencil3_hdv_1 bin/vfir5_hdv_1 \
    bin/vstrsm_hdv_1 bin/vsger_hdv_1 bin/vsgemv_hdv_1 \
    bin/vssymv_hdv_1 bin/vsgemm_hdv_1 bin/vssyrk_hdv_1 \
    bin/jacobi2d_hdv_1 bin/fconv2d_hdv_1 bin/vsspmv_hdv_1 \
    bin/lavamd_hdv_1 bin/softmax_hdv_1 \
    blas_lmul=4 gemm_lmul=1 gemm_rows=4 gemm_n=64 \
    > "$OUT/build_all.log" 2>&1
}

prepare_apps() {
  local app

  if [ "${STRICT_EP_REUSE_APPS:-0}" != 1 ]; then
    build_all
    return
  fi

  for app in \
    vsaxpy_hdv_1 vsdot_hdv_1 vsswap_hdv_1 vsdwt_hdv_1 \
    vstencil3_hdv_1 vfir5_hdv_1 vstrsm_hdv_1 vsger_hdv_1 \
    vsgemv_hdv_1 vssymv_hdv_1 vsgemm_hdv_1 vssyrk_hdv_1 \
    jacobi2d_hdv_1 fconv2d_hdv_1 vsspmv_hdv_1 \
    lavamd_hdv_1 softmax_hdv_1; do
    if [ ! -x "$APPS/bin/$app" ]; then
      echo "ERROR: missing reusable app binary: $APPS/bin/$app" >&2
      return 1
    fi
  done
}

prepare_sim() {
  if [ ! -x "$SIM_DIR/simv" ] || [ "${STRICT_EP_REUSE_SIM:-0}" != 1 ]; then
    echo "[compile] RTL mode=$HDV_ABLATION src_lifetime=$HDV_SRC_LIFETIME -> $SIM_DIR"
    make compile \
      sim_dir="$SIM_DIR" \
      hdv_ablation="$HDV_ABLATION" \
      hdv_src_lifetime="$HDV_SRC_LIFETIME" \
      > "$OUT/build_sim.log" 2>&1
  fi
}

run_sim() {
  local timeout_s=$1 app=$2 log=$3 plusargs=$4
  local binary
  binary="$(realpath "$APPS/bin/$app")"
  echo "[run] $app -> $log"
  (
    cd "$SIM_DIR"
    # plusargs is intentionally split into individual simulator arguments.
    timeout "$timeout_s" ./simv -l "run_${app}.vcs.log" \
      $plusargs +HDV_EXPECTED_EP=8000000 \
      +PRELOAD="$binary" +TESTCASE="$app"
  ) > "$OUT/$log" 2>&1
  local result cycles
  result=$(grep -E 'mock host' "$OUT/$log" | head -1 |
           grep -oE 'PASSED|FAILED' || true)
  cycles=$(grep -E 'mock host' "$OUT/$log" | head -1 |
           grep -oE 'total_task_cycles[[:space:]]*=[[:space:]]*[0-9]+' |
           grep -oE '[0-9]+$' || true)
  echo "      result=${result:-TIMEOUT/ERR} cycles=${cycles:-NA}"
}

run_1d_point() {
  local app=$1 reg=$2 avl=$3 extra=${4:-}
  run_sim 600 "$app" "log_avl_${app}_${avl}.log" \
    "+HDV_${reg}=$avl $extra"
}

run_1d_apps_points() {
  local avls=$1
  shift
  local app reg avl extra s1 s2

  for app in "$@"; do
    reg=A0
    extra=""
    case "$app" in
      vsdot_hdv_1|vsdwt_hdv_1)
        reg=A2
        ;;
      vstencil3_hdv_1)
        s1=$(addr_of "$app" src1)
        s2=$(addr_of "$app" src2)
        extra="+HDV_A1=$((s1 + 4)) +HDV_A2=$s2 +HDV_PACKET_WATCHDOG=20000"
        ;;
      vfir5_hdv_1)
        s1=$(addr_of "$app" src1)
        s2=$(addr_of "$app" src2)
        extra="+HDV_A1=$s1 +HDV_A2=$s2 +HDV_PACKET_WATCHDOG=20000"
        ;;
    esac

    for avl in $avls; do
      run_1d_point "$app" "$reg" "$avl" "$extra"
    done
  done
}

run_1d_points() {
  run_1d_apps_points "$1" \
    vsaxpy_hdv_1 vsdot_hdv_1 vsswap_hdv_1 vsdwt_hdv_1 \
    vstencil3_hdv_1 vfir5_hdv_1
}

run_ger_point() {
  local s1 s2

  s1=$(addr_of vsger_hdv_1 src1)
  s2=$(addr_of vsger_hdv_1 src2)
  run_sim 600 vsger_hdv_1 log_blas_vsger_hdv_1_128.log \
    "+HDV_A0=128 +HDV_A1=128 +HDV_A2=$s2 +HDV_A3=$((s2 + 512)) +HDV_A4=$s1"
}

run_gemv_symv_points() {
  local app s1 s2

  for app in vsgemv_hdv_1 vssymv_hdv_1; do
    s1=$(addr_of "$app" src1)
    s2=$(addr_of "$app" src2)
    if [ "$app" = vsgemv_hdv_1 ]; then
      run_sim 600 "$app" "log_blaspf_${app}_4_128_8g.log" \
        "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$((s2 + 512)) +HDV_A3=128 +HDV_A4=8"
    else
      run_sim 600 "$app" "log_blaspf_${app}_4_128_8g.log" \
        "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$s1 +HDV_A3=128 +HDV_A4=8"
    fi
  done
}

run_spmv_point() {
  local s1 s2 ci

  s1=$(addr_of vsspmv_hdv_1 src1)
  s2=$(addr_of vsspmv_hdv_1 src2)
  ci=$(addr_of vsspmv_hdv_1 col_idx)
  run_sim 600 vsspmv_hdv_1 vsspmv_hdv_1_fix.log \
    "+HDV_A0=$s1 +HDV_A1=$ci +HDV_A2=$s2 +HDV_A3=$((s2 + 256)) +HDV_TASK_WATCHDOG=400000"
}

run_conv2d_point() {
  local o i f

  o=$(addr_of fconv2d_hdv_1 o)
  i=$(addr_of fconv2d_hdv_1 i)
  f=$(addr_of fconv2d_hdv_1 f)
  run_sim 600 fconv2d_hdv_1 fconv2d_hdv_1_fix.log \
    "+HDV_A0=$o +HDV_A1=$i +HDV_A2=$f +HDV_A3=64 +HDV_A4=32 +HDV_A5=3 +HDV_TASK_WATCHDOG=400000"
}

run_jacobi2d_point() {
  local av bv

  av=$(addr_of jacobi2d_hdv_1 A_v)
  bv=$(addr_of jacobi2d_hdv_1 B_v)
  run_sim 600 jacobi2d_hdv_1 jacobi2d_hdv_1_fix.log \
    "+HDV_A0=128 +HDV_A1=64 +HDV_A2=$av +HDV_A3=$bv +HDV_TASK_WATCHDOG=400000"
}

run_lavamd_point() {
  local bx by bz lbv bq ap fo

  bx=$(addr_of lavamd_hdv_1 bx)
  by=$(addr_of lavamd_hdv_1 by)
  bz=$(addr_of lavamd_hdv_1 bz)
  lbv=$(addr_of lavamd_hdv_1 bv)
  bq=$(addr_of lavamd_hdv_1 bq)
  ap=$(addr_of lavamd_hdv_1 aparams)
  fo=$(addr_of lavamd_hdv_1 fout_v)
  run_sim 600 lavamd_hdv_1 lavamd_hdv_1_fix.log \
    "+HDV_A0=$bx +HDV_A1=$by +HDV_A2=$bz +HDV_A3=$lbv +HDV_A4=$bq +HDV_A5=$ap +HDV_A6=$fo +HDV_A7=256 +HDV_TASK_WATCHDOG=400000"
}

run_softmax_point() {
  local si so

  si=$(addr_of softmax_hdv_1 i)
  so=$(addr_of softmax_hdv_1 o_v)
  run_sim 600 softmax_hdv_1 softmax_hdv_1_fix.log \
    "+HDV_A0=$si +HDV_A1=$so +HDV_A2=3 +HDV_A3=256 +HDV_TASK_WATCHDOG=400000"
}

run_nonlong_representatives() {
  run_ger_point
  run_gemv_symv_points
  run_spmv_point
  run_conv2d_point
  run_jacobi2d_point
  run_lavamd_point
  run_softmax_point
}

run_short() {
  run_1d_points "1024"
  run_nonlong_representatives
}

run_paper_short() {
  run_1d_points "$PAPER_AVLS"
  run_nonlong_representatives
}

run_gemm_ablation_point() {
  local s1 s2

  s1=$(addr_of vsgemm_hdv_1 src1)
  s2=$(addr_of vsgemm_hdv_1 src2)
  run_sim 3600 vsgemm_hdv_1 log_blas_vsgemm_hdv_1_m1_4r_64.log \
    "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$s1 +HDV_A3=64 +HDV_TASK_WATCHDOG=1000000"
}

run_trsm_point() {
  local s1 s2

  s1=$(addr_of vstrsm_hdv_1 src1)
  s2=$(addr_of vstrsm_hdv_1 src2)
  run_sim 3600 vstrsm_hdv_1 log_blas_vstrsm_hdv_1_128.log \
    "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=128 +HDV_TASK_WATCHDOG=800000"
}

run_syrk_point() {
  local s1 s2

  s1=$(addr_of vssyrk_hdv_1 src1)
  s2=$(addr_of vssyrk_hdv_1 src2)
  run_sim 3600 vssyrk_hdv_1 log_blas_vssyrk_hdv_1_64.log \
      "+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=64 +HDV_TASK_WATCHDOG=800000"
}

run_long() {
  run_gemm_ablation_point
  run_trsm_point
  run_syrk_point
}

run_long_rest() {
  run_trsm_point
  run_syrk_point
}

launch_worker() {
  local worker=$1 session=$2 runner_log=$3 command

  if tmux has-session -t "$session" 2>/dev/null; then
    echo "[long] already running in tmux session: $session"
    return
  fi

  printf -v command \
    'cd %q && HDV_ABLATION=%q HDV_SRC_LIFETIME=%q STRICT_EP_OUT=%q STRICT_EP_SIM_DIR=%q STRICT_EP_REUSE_SIM=1 %q %q > %q 2>&1' \
    "$PWD" "$HDV_ABLATION" "$HDV_SRC_LIFETIME" "$OUT" "$SIM_DIR" \
    "$SCRIPT" "$worker" "$OUT/$runner_log"
  tmux new-session -d -s "$session" "$command"
  printf '%s\n' "$session" > "$OUT/long_runner.session"
  echo "[long] started in tmux session: $session"
  echo "       log: $OUT/$runner_log"
}

launch_long() {
  launch_worker long-worker \
    "${STRICT_EP_TMUX_SESSION:-hdv1_paper_long}" long_runner.log
}

launch_long_rest() {
  launch_worker long-rest-worker \
    "${STRICT_EP_TMUX_SESSION:-hdv1_paper_long_rest}" long_rest_runner.log
}

launch_ablation_gemm() {
  launch_worker ablation-gemm-worker \
    "${STRICT_EP_TMUX_SESSION:-hdv1_paper_${HDV_ABLATION}_gemm}" \
    ablation_gemm_runner.log
}

list_points() {
  local app avl count=0

  echo "1D AVL sweep:"
  for app in \
    vsaxpy_hdv_1 vsdot_hdv_1 vsswap_hdv_1 vsdwt_hdv_1 \
    vstencil3_hdv_1 vfir5_hdv_1; do
    for avl in $PAPER_AVLS; do
      printf '  %-22s AVL=%s\n' "$app" "$avl"
      count=$((count + 1))
    done
  done

  cat <<'EOF'
Representative matrix/application points:
  vsger_hdv_1           FP32, 128x128, LMUL=1
  vsgemv_hdv_1          FP32, N=128, G=8, LMUL=4
  vssymv_hdv_1          FP32, N=128, G=8, LMUL=4
  vsgemm_hdv_1          FP32, 64x64x64, 4-row, LMUL=1
  vstrsm_hdv_1          FP32, 128x128, LMUL=4
  vssyrk_hdv_1          FP32, 64x64, LMUL=4
  vsspmv_hdv_1          FP32, 32x32, 32 nnz/row, LMUL=1
  fconv2d_hdv_1         FP64, R=64, C=32, F=3, LMUL=2
  jacobi2d_hdv_1        FP64, 5-point 128x64, LMUL=4
  lavamd_hdv_1          FP32, NPAR=256, LMUL=1
  softmax_hdv_1         FP32, channels=3, inner=256, LMUL=1
EOF
  count=$((count + 11))
  echo "Total unique kernel/dimension points: $count"
}

run_remaining_a() {
  run_1d_apps_points "$REMAINING_AVLS" vsaxpy_hdv_1 vsdot_hdv_1
  run_ger_point
  run_gemv_symv_points
}

run_remaining_b() {
  run_1d_apps_points "$REMAINING_AVLS" vsswap_hdv_1 vsdwt_hdv_1
  run_spmv_point
  run_jacobi2d_point
}

run_remaining_c() {
  run_1d_apps_points "$REMAINING_AVLS" vstencil3_hdv_1 vfir5_hdv_1
  run_conv2d_point
  run_lavamd_point
  run_softmax_point
}

run_remaining_shard() {
  local shard=$1

  prepare_apps || { echo "app preparation failed"; return 1; }
  prepare_sim || { echo "RTL compile failed: $OUT/build_sim.log"; return 1; }

  case "$shard" in
    a) run_remaining_a ;;
    b) run_remaining_b ;;
    c) run_remaining_c ;;
    trsm) run_trsm_point ;;
    syrk) run_syrk_point ;;
    *) echo "ERROR: invalid remaining shard: $shard" >&2; return 2 ;;
  esac

  ./kernel_sweep_sum.sh "$OUT"
}

case "$MODE" in
  build-only)
    build_all || { echo "build failed: $OUT/build_all.log"; exit 1; }
    ;;
  short)
    prepare_apps || { echo "app preparation failed"; exit 1; }
    prepare_sim || { echo "RTL compile failed: $OUT/build_sim.log"; exit 1; }
    run_short
    ./kernel_sweep_sum.sh "$OUT"
    ;;
  sweep-1d)
    prepare_apps || { echo "app preparation failed"; exit 1; }
    prepare_sim || { echo "RTL compile failed: $OUT/build_sim.log"; exit 1; }
    run_1d_points "$PAPER_AVLS"
    ./kernel_sweep_sum.sh "$OUT"
    ;;
  paper-short)
    prepare_apps || { echo "app preparation failed"; exit 1; }
    prepare_sim || { echo "RTL compile failed: $OUT/build_sim.log"; exit 1; }
    run_paper_short
    ./kernel_sweep_sum.sh "$OUT"
    ;;
  long)
    prepare_apps || { echo "app preparation failed"; exit 1; }
    prepare_sim || { echo "RTL compile failed: $OUT/build_sim.log"; exit 1; }
    launch_long
    ;;
  long-worker)
    run_long
    ./kernel_sweep_sum.sh "$OUT"
    ;;
  long-rest)
    prepare_apps || { echo "app preparation failed"; exit 1; }
    prepare_sim || { echo "RTL compile failed: $OUT/build_sim.log"; exit 1; }
    launch_long_rest
    ;;
  long-rest-worker)
    run_long_rest
    ./kernel_sweep_sum.sh "$OUT"
    ;;
  ablation)
    prepare_apps || { echo "app preparation failed"; exit 1; }
    prepare_sim || { echo "RTL compile failed: $OUT/build_sim.log"; exit 1; }
    run_1d_points "1024"
    ./kernel_sweep_sum.sh "$OUT"
    launch_ablation_gemm
    ;;
  ablation-gemm-worker)
    run_gemm_ablation_point
    ./kernel_sweep_sum.sh "$OUT"
    ;;
  all)
    prepare_apps || { echo "app preparation failed"; exit 1; }
    prepare_sim || { echo "RTL compile failed: $OUT/build_sim.log"; exit 1; }
    run_paper_short
    ./kernel_sweep_sum.sh "$OUT"
    launch_long
    ;;
  list)
    list_points
    ;;
  sum)
    ./kernel_sweep_sum.sh "$OUT"
    ;;
  remaining-a)
    run_remaining_shard a
    ;;
  remaining-b)
    run_remaining_shard b
    ;;
  remaining-c)
    run_remaining_shard c
    ;;
  remaining-trsm)
    run_remaining_shard trsm
    ;;
  remaining-syrk)
    run_remaining_shard syrk
    ;;
  *)
    echo "usage: $0 {build-only|short|sweep-1d|paper-short|long|long-rest|ablation|all|list|sum|remaining-a|remaining-b|remaining-c|remaining-trsm|remaining-syrk}" >&2
    exit 2
    ;;
esac
