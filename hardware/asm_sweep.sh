#!/usr/bin/env bash
# ============================================================================
# asm_sweep.sh — batch-run the tightly-coupled *_asm kernels on the MAIN branch
# (standard cva6+Ara) across AVL / LMUL, in BOTH performance modes, → CSV.
#
#   ./asm_sweep.sh [1d|blas|gemm|fixed|all]        (default: all)
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
#
# Problem size / variant is compile-time; passed via ENV_DEFINES (NOT DEFINES=,
# which would drop -DNR_LANES/-DVLEN).  `make` can't see -D changes, so stale
# objects are removed before each point.
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")"                       # hardware/
HW="$(pwd)"; ROOT="$(cd .. && pwd)"; APPS="$ROOT/apps"; SIM="$HW/sim"; APP_BIN="$APPS/bin"
MODES="${MODES:-both}"
SIM_TIMEOUT="${SIM_TIMEOUT:-600}"   # per-point sim timeout (s); 0 = unlimited
run_sim() {                          # run_sim <logfile> <cmd...>; honors SIM_TIMEOUT
  local log="$1"; shift
  if [ "$SIM_TIMEOUT" = 0 ]; then "$@" >"$log" 2>&1; return $?; fi
  timeout "$SIM_TIMEOUT" "$@" >"$log" 2>&1
}
OUT="$HW/asm_sweep_out"; mkdir -p "$OUT"
BUILDLOG="$OUT/build.log"; : > "$BUILDLOG"
CSV="$OUT/asm_sweep.csv"
HDR="kernel,tag,avl,blas_lmul,gemm_rows,ideal_rvv_cycles,ideal_lane_util,real_total_cycles,real_rvv_cycles,real_vector_insns,real_insns,real_ipc,hw_cycles,dcache_stalls,icache_stalls,sb_full,axi_ar,axi_r,axi_aw,axi_w,axi_b"
[ -f "$CSV" ] || echo "$HDR" > "$CSV"

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

POINTS="$(gen_points "$GROUP")"
NP=$(printf '%s\n' "$POINTS" | grep -c .)
echo "asm_sweep: group=$GROUP  points=$NP  modes=$MODES"
declare -A REALD IDEALD

# ===== REAL phase: compile non-ideal RTL ONCE, reuse simv per point =====
if [ "$MODES" = both ] || [ "$MODES" = real ]; then
  echo "########## REAL phase (compile RTL once, reuse simv) ##########"
  rtl_ready=0
  while IFS='|' read -r app tag avl bl gr defs; do
    [ -z "$app" ] && continue
    echo ">>> real  $app [$tag]"
    if ! ( cd "$APPS" && rm -f "${app}/main.c.o" "${app}/main.c.o.spike" "bin/${app}" \
           && make "bin/${app}" ENV_DEFINES="$defs" ) >>"$BUILDLOG" 2>&1; then
      REALD["$app|$tag"]="BUILD_FAIL,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA"; continue
    fi
    rm -f "$SIM/perf_report_${app}.log"
    rlog="$OUT/${app}__${tag}__real.log"
    if [ "$rtl_ready" = 0 ]; then
      run_sim "$rlog" bash -c "cd '$HW' && make -B sim app='$app'"     # first point: compile + run
      rtl_ready=1
    else
      run_sim "$rlog" bash -c "cd '$SIM' && ./simv -l run.vcs.log +PRELOAD='$APP_BIN/${app}' +TESTCASE='${app}'"   # reuse RTL
    fi
    if [ $? -ne 0 ]; then
      echo "    *** TIMEOUT/FAIL real $app [$tag]" | tee -a "$rlog"
      REALD["$app|$tag"]="TIMEOUT,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA"; continue
    fi
    rpt="$SIM/perf_report_${app}.log"
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
    if ! ( cd "$APPS" && rm -f "${app}/main.c.o" "${app}/main.c.o.spike" "bin/${app}.spike" \
           "bin/${app}.ideal" "ideal_dispatcher/vtrace/${app}.vtrace" \
           && make "bin/${app}.ideal" ENV_DEFINES="$defs" ) >>"$BUILDLOG" 2>&1; then
      IDEALD["$app|$tag"]="BUILD_FAIL,NA"; continue
    fi
    ilog="$OUT/${app}__${tag}__ideal.log"
    run_sim "$ilog" bash -c "cd '$HW' && make -B sim app='$app' ideal_dispatcher=1"
    if [ $? -ne 0 ]; then
      echo "    *** TIMEOUT/FAIL ideal $app [$tag]" | tee -a "$ilog"
      IDEALD["$app|$tag"]="TIMEOUT,NA"; continue
    fi
    ipt="$SIM/perf_report_${app}_ideal.log"
    IDEALD["$app|$tag"]="$(pf "$ipt" total_rvv_cycles),$(pf "$ipt" 'lane utilization')"
    echo "    ideal_rvv=$(echo "${IDEALD[$app|$tag]}" | cut -d, -f1)"
  done <<< "$POINTS"
fi

# ===== write CSV (merge real + ideal per point) =====
while IFS='|' read -r app tag avl bl gr defs; do
  [ -z "$app" ] && continue
  echo "$app,$tag,$avl,$bl,$gr,${IDEALD[$app|$tag]:-NA,NA},${REALD[$app|$tag]:-NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA}" >> "$CSV"
done <<< "$POINTS"

echo ""
echo "==== done. $NP points -> $CSV ===="
column -t -s, "$CSV" 2>/dev/null | tail -n +1 | head -50
