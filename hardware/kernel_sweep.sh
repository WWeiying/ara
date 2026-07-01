#!/usr/bin/env bash
# ============================================================================
# kernel_sweep.sh — batch-run the tightly-coupled *_asm kernels on the MAIN branch
# (standard cva6+Ara) across AVL / LMUL, in BOTH performance modes, → CSV.
#
#   ./kernel_sweep.sh [1d|blas|gemm|fixed|all]     (default: all)
#
# TWO-PHASE for speed:
#   * REAL phase (non-ideal): the RTL is identical across every point, so it is
#     COMPILED ONCE and then every point just rebuilds its app binary and re-runs
#     `simv` directly (seconds/point instead of a full RTL recompile).
#   * IDEAL phase (ideal_dispatcher=1): each point bakes its own spike vtrace
#     (VTRACE / N_VINSN) into the RTL, so it MUST recompile per point (minutes
#     each) — unavoidable.  Run `MODES=real` to skip it.
#
# Metrics — ideal: total_rvv_cycles (Ara peak), lane util.
#           real (non-ideal-only): total_cycles (real wall), IPC, vector_insns,
#           AXI counts, and the cva6 stall counters [hw-cycles] / [cva6-d$-stalls]
#           / [cva6-i$-stalls] / [cva6-sb-full] (scalar-dispatch back-pressure).
#   ideal total_rvv_cycles vs real total_cycles = the cost the ideal path hides.
#
# Knobs (env):
#   MODES=both|real|ideal            (default both)
#   AVLS_1D="32 ... 4096"            1D ASM_AVL list
#   AVLS_BLAS="32 64 128"            BLAS/GEMM runtime-N list
#   BLAS_LMULS="2 4 8"               BLAS m{N} families (m1 fixed is always added)
#   GEMM_ROWS_L="1 2 4"              GEMM register-blocking rows
#   KERNELS_1D / KERNELS_BLAS=...    restrict the kernel list
#   POINT_FILTER="app:tag ..."       exact points only, e.g. vstrsm_asm:m2_avl32
#   APP_FILTER="app ..."             exact apps only
#   TAG_FILTER="tag ..."             exact tags only
#
# Problem size / variant is compile-time; passed via ENV_DEFINES (NOT DEFINES=,
# which would drop -DNR_LANES/-DVLEN).  `make` can't see -D changes, so stale
# objects are removed before each point.
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")"                       # hardware/
HW="$(pwd)"; ROOT="$(cd .. && pwd)"; APPS="$ROOT/apps"; SIM="$HW/sim"; APP_BIN="$APPS/bin"
MODES="${MODES:-both}"
SIM_TIMEOUT="${SIM_TIMEOUT:-600}"       # per-point sim timeout (s); 0 = unlimited
SIM_KILL_GRACE="${SIM_KILL_GRACE:-10}"  # seconds between TERM and KILL
LOG_MAX_MB="${LOG_MAX_MB:-1024}"        # per-point log cap; 0 = unlimited

run_sim() {                             # run_sim <logfile> <cmd...>
  local log="$1"; shift
  local max_bytes=0 start now size rc timed_out=0 log_full=0 pid

  : >"$log"
  if [ "${LOG_MAX_MB:-0}" != 0 ]; then
    max_bytes=$((LOG_MAX_MB * 1024 * 1024))
  fi

  # Run each point in its own process group so a timeout kills make/simv and
  # any VCS children, instead of only killing the wrapper shell.
  setsid "$@" >"$log" 2>&1 &
  pid=$!
  start=$(date +%s)

  while kill -0 "$pid" 2>/dev/null; do
    sleep 2

    if [ "$SIM_TIMEOUT" != 0 ]; then
      now=$(date +%s)
      if [ $((now - start)) -ge "$SIM_TIMEOUT" ]; then
        timed_out=1
        break
      fi
    fi

    if [ "$max_bytes" -gt 0 ] && [ -f "$log" ]; then
      size=$(wc -c <"$log" 2>/dev/null || echo 0)
      if [ "$size" -ge "$max_bytes" ]; then
        log_full=1
        break
      fi
    fi
  done

  if [ "$timed_out" = 1 ] || [ "$log_full" = 1 ]; then
    if [ "$timed_out" = 1 ]; then
      echo "SIM_TIMEOUT after ${SIM_TIMEOUT}s" >>"$log"
      rc=124
    else
      echo "LOG_LIMIT exceeded ${LOG_MAX_MB}MiB" >>"$log"
      rc=125
    fi

    kill -TERM "-$pid" 2>/dev/null || true
    sleep "$SIM_KILL_GRACE"
    kill -KILL "-$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    return "$rc"
  fi

  wait "$pid"
}
OUT="$HW/kernel_sweep_out"; mkdir -p "$OUT"
BUILDLOG="$OUT/build.log"; : > "$BUILDLOG"
HDR="kernel,tag,avl,blas_lmul,gemm_rows,ideal_rvv_cycles,ideal_lane_util,real_total_cycles,real_rvv_cycles,real_vector_insns,real_insns,real_ipc,hw_cycles,dcache_stalls,icache_stalls,sb_full,axi_ar,axi_r,axi_aw,axi_w,axi_b"

pf() { grep -E "\[PERF\] $2[ ]+:" "$1" 2>/dev/null | tail -1 | sed -E 's/.*:[ ]*//; s/[ ]*$//'; }
st() { grep -F "$2" "$1" 2>/dev/null | tail -1 | grep -oE '[0-9]+' | tail -1; }

GROUP="${1:-all}"
AVLS_1D="${AVLS_1D:-32 64 128 256 512 1024 2048 4096}"
AVLS_BLAS="${AVLS_BLAS:-32 64 128}"
BLAS_LMULS="${BLAS_LMULS:-2 4 8}"          # m2/m4/m8; m1 (fixed 32x32) added per kernel
GEMM_ROWS_L="${GEMM_ROWS_L:-1 2 4}"

# ---- point list: app|tag|avl|bl|gr|defs (defs may contain spaces; last field) ----
gen_points() {
  local g=$1 k a L r
  if [ "$g" = 1d ] || [ "$g" = all ]; then
    for k in ${KERNELS_1D:-vsaxpy vscopy vsswap vsdot vsscal vvaddint32 vmc vsdwt}; do
      for a in $AVLS_1D; do echo "${k}_asm|avl${a}|$a|||-DASM_AVL=$a"; done
    done
  fi
  if [ "$g" = blas ] || [ "$g" = all ]; then
    for k in ${KERNELS_BLAS:-vssymv vsgemv vssyrk vstrsm}; do
      echo "${k}_asm|m1|32|1||-DBLAS_LMUL=1"
      for L in $BLAS_LMULS; do for a in $AVLS_BLAS; do
        echo "${k}_asm|m${L}_avl${a}|$a|$L||-DBLAS_LMUL=$L -DASM_AVL=$a"
      done; done
    done
    for a in 32 64 128; do echo "vsger_asm|n${a}|$a|||-DASM_AVL=$a"; done
  fi
  if [ "$g" = gemm ] || [ "$g" = all ]; then
    for r in $GEMM_ROWS_L; do echo "vsgemm_asm|m1_${r}row|32|1|$r|-DGEMM_LMUL=1 -DGEMM_ROWS=$r"; done
    for r in $GEMM_ROWS_L; do for a in $AVLS_BLAS; do
      echo "vsgemm_asm|m4_${r}row_avl${a}|$a|4|$r|-DGEMM_LMUL=4 -DGEMM_ROWS=$r -DASM_AVL=$a"
    done; done
  fi
  if [ "$g" = fixed ] || [ "$g" = all ]; then
    echo "vsspmv_asm|fixed32|1024|||"
  fi
}

word_has() {
  local needle="$1" word
  shift
  for word in "$@"; do
    [ "$word" = "$needle" ] && return 0
  done
  return 1
}

point_selected() {
  local app="$1" tag="$2" point

  if [ -n "${POINT_FILTER:-}" ]; then
    for point in $POINT_FILTER; do
      case "$point" in
        "$app:$tag"|"$app|$tag") return 0 ;;
      esac
    done
    return 1
  fi

  if [ -n "${APP_FILTER:-}" ] && ! word_has "$app" $APP_FILTER; then
    return 1
  fi
  if [ -n "${TAG_FILTER:-}" ] && ! word_has "$tag" $TAG_FILTER; then
    return 1
  fi
  return 0
}

filter_points() {
  local app tag avl bl gr defs
  while IFS='|' read -r app tag avl bl gr defs; do
    [ -z "$app" ] && continue
    if point_selected "$app" "$tag"; then
      echo "$app|$tag|$avl|$bl|$gr|$defs"
    fi
  done
}

POINTS="$(gen_points "$GROUP" | filter_points)"
NP=$(printf '%s\n' "$POINTS" | grep -c .)
if [ "$NP" -eq 0 ]; then
  echo "error: no points selected for group=$GROUP" >&2
  exit 2
fi
echo "kernel_sweep: group=$GROUP  points=$NP  modes=$MODES"
declare -A REALD IDEALD

# ===== REAL phase: compile non-ideal RTL ONCE, reuse simv per point =====
if [ "$MODES" = both ] || [ "$MODES" = real ]; then
  echo "########## REAL phase (compile RTL once, reuse simv) ##########"
  rtl_ready=0
  while IFS='|' read -r app tag avl bl gr defs; do
    [ -z "$app" ] && continue
    echo ">>> real  $app [$tag]"
    rlog="$OUT/${app}__${tag}__real.log"
    if ! ( cd "$APPS" && rm -f "${app}/main.c.o" "${app}/main.c.o.spike" "bin/${app}" \
           && make "bin/${app}" ENV_DEFINES="$defs" ) >>"$BUILDLOG" 2>&1; then
      echo "BUILD_FAIL real $app [$tag]" >"$rlog"
      REALD["$app|$tag"]="BUILD_FAIL,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA"; continue
    fi
    rm -f "$SIM/perf_report_${app}.log"
    if [ "$rtl_ready" = 0 ]; then
      run_sim "$rlog" bash -c "cd '$HW' && make -B sim app='$app' fail_on_assert=1 no_fsdb=1"     # first point: compile + run
      rtl_ready=1
    else
      run_sim "$rlog" bash -c "cd '$SIM' && ./simv -l run.vcs.log +PRELOAD='$APP_BIN/${app}' +TESTCASE='${app}' +NO_FSDB"   # reuse RTL
    fi
    if [ $? -ne 0 ]; then
      echo "    *** TIMEOUT/FAIL real $app [$tag]" | tee -a "$rlog"
      REALD["$app|$tag"]="TIMEOUT,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA"; continue
    fi
    rpt="$SIM/perf_report_${app}.log"
    if [ -f "$rpt" ]; then
      {
        echo ""
        echo "===== per-point perf report: $(basename "$rpt") ====="
        cat "$rpt"
      } >>"$rlog"
    fi
    REALD["$app|$tag"]="$(pf "$rpt" total_cycles),$(pf "$rpt" total_rvv_cycles),$(pf "$rpt" total_vector_insns),$(pf "$rpt" total_insns),$(pf "$rpt" IPC),$(st "$rlog" '[hw-cycles]'),$(st "$rlog" '[cva6-d$-stalls]'),$(st "$rlog" '[cva6-i$-stalls]'),$(st "$rlog" '[cva6-sb-full]'),$(pf "$rpt" rvv_axi_ar_count),$(pf "$rpt" rvv_axi_r_count),$(pf "$rpt" rvv_axi_aw_count),$(pf "$rpt" rvv_axi_w_count),$(pf "$rpt" rvv_axi_b_count)"
    echo "    real_total=$(echo "${REALD[$app|$tag]}" | cut -d, -f1)  sb_full=$(echo "${REALD[$app|$tag]}" | cut -d, -f9)"
  done <<< "$POINTS"
fi

# ===== IDEAL phase: per-point recompile (vtrace baked into RTL) =====
if [ "$MODES" = both ] || [ "$MODES" = ideal ]; then
  echo "########## IDEAL phase (recompile RTL per point) ##########"
  while IFS='|' read -r app tag avl bl gr defs; do
    [ -z "$app" ] && continue
    echo ">>> ideal $app [$tag]"
    ilog="$OUT/${app}__${tag}__ideal.log"
    if ! ( cd "$APPS" && rm -f "${app}/main.c.o" "${app}/main.c.o.spike" "bin/${app}.spike" \
           "bin/${app}.ideal" "ideal_dispatcher/vtrace/${app}.vtrace" \
           && make "bin/${app}.ideal" ENV_DEFINES="$defs" ) >>"$BUILDLOG" 2>&1; then
      echo "BUILD_FAIL ideal $app [$tag]" >"$ilog"
      IDEALD["$app|$tag"]="BUILD_FAIL,NA"; continue
    fi
    run_sim "$ilog" bash -c "cd '$HW' && make -B sim app='$app' ideal_dispatcher=1 fail_on_assert=1"
    if [ $? -ne 0 ]; then
      echo "    *** TIMEOUT/FAIL ideal $app [$tag]" | tee -a "$ilog"
      IDEALD["$app|$tag"]="TIMEOUT,NA"; continue
    fi
    ipt="$SIM/perf_report_${app}_ideal.log"
    if [ -f "$ipt" ]; then
      {
        echo ""
        echo "===== per-point perf report: $(basename "$ipt") ====="
        cat "$ipt"
      } >>"$ilog"
    fi
    IDEALD["$app|$tag"]="$(pf "$ipt" total_rvv_cycles),$(pf "$ipt" 'lane utilization')"
    echo "    ideal_rvv=$(echo "${IDEALD[$app|$tag]}" | cut -d, -f1)"
  done <<< "$POINTS"
fi

echo ""
echo "==== done. $NP points -> $OUT/*.log ===="
echo "Run ./kernel_sweep_sum.sh $GROUP to rebuild $OUT/kernel_sweep.csv from logs."
