#!/usr/bin/env bash
# AVL sweep for HDV 1D streaming kernels.
#
# For the B-tier (BLAS-2/3 + GEMM) kernels — vsgemm {size}x{rows} load-stream
# variants and the square BLAS dim-N sweep — use the companion ./blas_sweep.sh
# (separate because they need an app rebuild / runtime dimension register, not
# the pure RTL-param AVL injection used here).
#
# Each kernel's application vector length (AVL) is driven by the unified `avl`
# Makefile knob (see hardware/Makefile).  Data arrays are static, so AVL is
# capped per kernel by its array size (MAXAVL below); regenerate the data via
# the app gen scripts (apps/<orig>/script/gen_data.py) to raise a cap.
#
# Usage:
#   ./avl_sweep.sh                          # all wired kernels, default AVL list
#   ./avl_sweep.sh vsdot_hdv                # one kernel, default AVL list
#   ./avl_sweep.sh vsdot_hdv "32 64 128"    # one kernel, custom AVL list
#   ./avl_sweep.sh all "16 64 256 1024"     # all kernels, custom AVL list
#
# Output: avl_sweep_out/<kernel>.csv (per kernel) + avl_sweep_out/all.csv
# (combined) + a live console table.  The CSV captures the FULL set of perf
# counters the HDV mock-host sim emits: HDV-CSR (cycles/EPs/idle), HDV-PERF
# (dispatch path), IPU-PERF (operand serve), PERF-ADDRGEN / -PF (LSU + data
# prefetcher), PERF-SEQ (sequencer hazards).  ~60 columns; the console shows a
# compact subset.

set -uo pipefail
cd "$(dirname "$0")"            # hardware/

# Per-kernel max AVL = static data-array element limit.
# 数组元素数（= data.S 提供的存储）。vsaxpy/vscopy/vsscal 的 data.S 实为 4096，
# 其余 TOTAL_ELEMENTS=1024。超出即越界（vsswap 4096 实测 FAIL）。
# 数组元素数（data.S 实际存储）。vsswap/vsdot 本就 4096；vmc/vvaddint32 已平铺到
# 4096。dropout 改造为干净 HDV 核（main 极简、task 落在 0x80001000、a1/a2/a3 4KB 对齐
# 不跨页）后已能随 AVL 缩放，放开到 4096。
# fdotp 已退出 sweep：它的预取对自身地址/时序病态敏感（非单调），任何描述符消费时
# 序的改动都会大幅改变其命中率；点积类由 vsdot 覆盖（vsdot 对所有改动逐位一致）。
# Prefetch micro-benchmarks (LMUL x stream-count x lead).  a0 = iteration count
# (the swept "AVL"), a1..a4 = stream bases, a5 = output base — all from plusargs.
# AVL (count) is capped low so even m8 (chunk = VLMAX*4 = 1024 B) keeps each of the
# up-to-5 regions inside the 1 MB L2 at the 0x20000-spaced bases below.
PF_KERNELS="vspf_m1k1_hdv vspf_m1k2_hdv vspf_m1k4_hdv vspf_m2k2_hdv vspf_m4k2_hdv vspf_m8k2_hdv"
# a1..a5 = 0x80010000, 0x80030000, 0x80050000, 0x80070000, 0x80090000 (decimal).
PF_PTRS="+HDV_A1=2147549184 +HDV_A2=2147680256 +HDV_A3=2147811328 +HDV_A4=2147942400 +HDV_A5=2148073472"

declare -A MAXAVL=(
  [vsaxpy_hdv]=4096   [vscopy_hdv]=4096   [vsscal_hdv]=4096
  [vsswap_hdv]=4096   [vsdot_hdv]=4096    [vvaddint32_hdv]=4096
  [vmc_hdv]=4096      [dropout_hdv]=4096  [vsdwt_hdv]=4096
  [vspf_m1k1_hdv]=64  [vspf_m1k2_hdv]=64  [vspf_m1k4_hdv]=64
  [vspf_m2k2_hdv]=64  [vspf_m4k2_hdv]=64  [vspf_m8k2_hdv]=64
)
ALL_KERNELS="vsaxpy_hdv vvaddint32_hdv vscopy_hdv vsswap_hdv vsdot_hdv vsscal_hdv vmc_hdv dropout_hdv vsdwt_hdv"
DEFAULT_AVLS="8 16 32 64 128 256 512 1024 2048 4096"

# Which xrf reg holds the AVL per kernel (a0=A0, a2=A2).  Injected at RUNTIME via
# the scalar backend's +HDV_A<n> plusarg (see hdv_scalar_backend.sv), so the
# simv is NOT re-elaborated per AVL point (VCS keeps it "up to date"); only the
# first run of each kernel recompiles its address defines.
declare -A AVLREG=( [vsdot_hdv]=A2 [vsdwt_hdv]=A2 )   # vspf + others default to A0 (count)
# Per-kernel extra plusargs (pointer args that aren't the swept AVL register).
declare -A EXTRA_PLUSARGS=(
  [vspf_m1k1_hdv]="$PF_PTRS" [vspf_m1k2_hdv]="$PF_PTRS" [vspf_m1k4_hdv]="$PF_PTRS"
  [vspf_m2k2_hdv]="$PF_PTRS" [vspf_m4k2_hdv]="$PF_PTRS" [vspf_m8k2_hdv]="$PF_PTRS"
)

ARG_K="${1:-all}"
AVLS="${2:-$DEFAULT_AVLS}"
if   [ "$ARG_K" = "all" ]; then KERNELS="$ALL_KERNELS"
elif [ "$ARG_K" = "pf"  ]; then KERNELS="$PF_KERNELS"; AVLS="${2:-16 64}"
else KERNELS="$ARG_K"; fi

OUT=avl_sweep_out
mkdir -p "$OUT"
COMBINED="$OUT/all.csv"

# ── Full column set (order matters: the row is assembled in this exact order) ──
H_ID="avl,result,task_cycles,cyc_per_elem,wall_cycles,eps,vec_busy,imem_outstanding"
H_HDV="ep_ack,ep_vset_ack,vq_push,vq_pop,vq_max_occ,vq_bypass,vq_full_stall,dispatch_slots,dispatch_cycles,fsm_could_bypass,operand_wait_cyc,ara_backpressure,real_wait_stall,resp_meta_stall,resp_meta_max"
H_IPU="ipu_ready_cyc,ipu_ready_stall,ipu_sram_stall,ipu_serve_cyc,packets,bypass_hits,demand_reads,avg_cyc_per_pkt"
H_AG="demand_ar,pf_ar,pf_hit,loads,pf_en_cyc,demand_aw,demand_B,pf_B"
H_AGPF="pf_ar_rob_full,pf_ar_lkup_full,pf_ar_pending,pf_ar_dis,pf_2nd,dem_rob_block,pf_disabled,pf_page_cross,pf_queue_full,pf_avl_low"
H_SEQ="seq_issue,seq_blocked,seq_raw,seq_war,seq_waw,seq_waw_block,seq_ep_bypass,seq_full"
H_DERIV="pf_hit_rate"
ROWHDR="$H_ID,$H_HDV,$H_IPU,$H_AG,$H_AGPF,$H_SEQ,$H_DERIV"     # per-kernel CSV header
echo "kernel,$ROWHDR" > "$COMBINED"                            # combined adds kernel col

# kv TAG KEY -> first numeric value of `KEY=<n>` (or `KEY = <n>`) on a line
# matching TAG.  Scoping to TAG avoids cross-group prefix collisions (e.g. SEQ
# `full=` vs ADDRGEN-PF `pf_queue_full=`).  KEY must be immediately followed by
# optional spaces then `=`, so `waw=` never matches `waw_block=`.
log=""
kv() { grep -hE "$1" "$log" 2>/dev/null | grep -oE "$2[[:space:]]*=[[:space:]]*[0-9]+" | head -1 | grep -oE '[0-9]+$'; }
d() { local v; v=$(grep -hE "$1" "$log" 2>/dev/null | grep -oE "$2=[0-9]+" | head -1 | grep -oE '[0-9]+'); echo "$v"; }

for k in $KERNELS; do
  max=${MAXAVL[$k]:-1024}
  csv="$OUT/${k}.csv"
  echo "$ROWHDR" > "$csv"
  echo "==================== $k  (max AVL=$max) ===================="
  printf "%-7s %-7s %-8s %-7s %-6s %-7s %-7s %-9s %s\n" \
         "AVL" "result" "cycles" "cyc/el" "EPs" "pkts" "avg/pk" "pf_ar→hit" "seq_blk"
  for n in $AVLS; do
    if [ "$n" -gt "$max" ]; then continue; fi
    log=/tmp/avl_${k}_${n}.log
    reg=${AVLREG[$k]:-A0}
    # +HDV_EXPECTED_EP huge: don't cap the task at the compile-time EP count;
    # let the kernel run its full AVL and `ret` naturally.
    timeout 600 make sim app="$k" hdv_plusargs="+HDV_${reg}=${n} ${EXTRA_PLUSARGS[$k]:-} +HDV_EXPECTED_EP=8000000" > "$log" 2>&1

    # ── identity / result ──
    r=$(grep -E 'mock host' "$log" | head -1 | grep -oE 'PASSED|FAILED'); [ -z "$r" ] && r="ERR"
    tc=$(kv 'mock host' 'total_task_cycles')
    wc=$(d 'HDV-CSR.*DONE' 'wall_cycle')
    eps=$(d 'HDV-CSR.*DONE' 'accepted'); [ -z "$eps" ] && eps=$(grep -E 'mock host' "$log" | grep -oE 'got [0-9]+' | grep -oE '[0-9]+')
    vbusy=$(d 'HDV-CSR.*DONE' 'vec_busy')
    imem=$(d 'HDV-CSR.*DONE' 'imem_outstanding')
    cpe="-"; [ -n "$tc" ] && cpe=$(echo "scale=3; $tc/$n" | bc)

    # ── HDV-PERF (dispatch path) ──
    ep_ack=$(kv 'HDV-PERF' 'ep_acknowledged')
    ep_vack=$(kv 'HDV-PERF' 'ep_vset_acknowledged')
    vqpush=$(kv 'HDV-PERF' 'vq_push'); vqpop=$(kv 'HDV-PERF' 'vq_pop')
    vqmax=$(kv 'HDV-PERF' 'vq_max_occupancy'); vqbyp=$(kv 'HDV-PERF' 'vq_bypass')
    vqfs=$(kv 'HDV-PERF' 'vq_full_stall')
    dslots=$(kv 'HDV-PERF' 'dispatch_slots'); dcyc=$(kv 'HDV-PERF' 'dispatch_total_cycles')
    fbyp=$(kv 'HDV-PERF' 'fsm_could_bypass'); owc=$(kv 'HDV-PERF' 'operand_wait_cycles')
    abp=$(kv 'HDV-PERF' 'ara_backpressure'); rwfs=$(kv 'HDV-PERF' 'real_wait_full_stall')
    rmfs=$(kv 'HDV-PERF' 'resp_meta_full_stall'); rmmax=$(kv 'HDV-PERF' 'resp_meta_max')

    # ── IPU-PERF (operand serve) ──
    irc=$(kv 'IPU-PERF' 'ready_cyc'); irs=$(kv 'IPU-PERF' 'ready_stall')
    isr=$(kv 'IPU-PERF' 'stall_due_to_sram'); isc=$(kv 'IPU-PERF' 'serve_cycles')
    pk=$(kv 'IPU-PERF' 'packets'); byh=$(kv 'IPU-PERF' 'bypass_hits')
    dmr=$(kv 'IPU-PERF' 'demand_reads'); acp=$(kv 'IPU-PERF' 'avg_cycles_per_pkt')

    # ── PERF-ADDRGEN (LSU + data prefetcher) ──  ']' in tag excludes -PF lines
    dar=$(kv 'PERF-ADDRGEN\]' 'demand_ar'); pfa=$(kv 'PERF-ADDRGEN\]' 'pf_ar')
    pfh=$(kv 'PERF-ADDRGEN\]' 'pf_hit'); lds=$(kv 'PERF-ADDRGEN\]' 'loads')
    pfen=$(kv 'PERF-ADDRGEN\]' 'pf_en_cyc'); daw=$(kv 'PERF-ADDRGEN\]' 'demand_aw')
    dB=$(kv 'PERF-ADDRGEN\]' 'demand_B'); pfB=$(kv 'PERF-ADDRGEN\]' 'pf_B')

    # ── PERF-ADDRGEN-PF (prefetch back-pressure breakdown) ──
    parf=$(kv 'PERF-ADDRGEN-PF' 'pf_ar_rob_full'); palf=$(kv 'PERF-ADDRGEN-PF' 'pf_ar_lkup_full')
    pap=$(kv 'PERF-ADDRGEN-PF' 'pf_ar_pending'); pad=$(kv 'PERF-ADDRGEN-PF' 'pf_ar_dis')
    p2nd=$(kv 'PERF-ADDRGEN-PF' 'pf_2nd'); drb=$(kv 'PERF-ADDRGEN-PF' 'dem_rob_block')
    pdis=$(kv 'PERF-ADDRGEN-PF' 'pf_disabled'); ppc=$(kv 'PERF-ADDRGEN-PF' 'pf_page_cross')
    pqf=$(kv 'PERF-ADDRGEN-PF' 'pf_queue_full'); pal=$(kv 'PERF-ADDRGEN-PF' 'pf_avl_low')

    # ── PERF-SEQ (sequencer hazards) ──
    sissue=$(kv 'PERF-SEQ' 'issue'); sblk=$(kv 'PERF-SEQ' 'blocked')
    sraw=$(kv 'PERF-SEQ' 'raw'); swar=$(kv 'PERF-SEQ' 'war'); swaw=$(kv 'PERF-SEQ' 'waw')
    swawb=$(kv 'PERF-SEQ' 'waw_block'); sepb=$(kv 'PERF-SEQ' 'ep_bypass'); sfull=$(kv 'PERF-SEQ' 'full')

    # ── derived ──
    pfhr="-"; if [ -n "$pfa" ] && [ "$pfa" -gt 0 ] 2>/dev/null; then pfhr=$(echo "scale=3; ${pfh:-0}/$pfa" | bc); fi

    row="$n,$r,${tc:-},$cpe,${wc:-},${eps:-},${vbusy:-},${imem:-}"
    row="$row,${ep_ack:-},${ep_vack:-},${vqpush:-},${vqpop:-},${vqmax:-},${vqbyp:-},${vqfs:-},${dslots:-},${dcyc:-},${fbyp:-},${owc:-},${abp:-},${rwfs:-},${rmfs:-},${rmmax:-}"
    row="$row,${irc:-},${irs:-},${isr:-},${isc:-},${pk:-},${byh:-},${dmr:-},${acp:-}"
    row="$row,${dar:-},${pfa:-},${pfh:-},${lds:-},${pfen:-},${daw:-},${dB:-},${pfB:-}"
    row="$row,${parf:-},${palf:-},${pap:-},${pad:-},${p2nd:-},${drb:-},${pdis:-},${ppc:-},${pqf:-},${pal:-}"
    row="$row,${sissue:-},${sblk:-},${sraw:-},${swar:-},${swaw:-},${swawb:-},${sepb:-},${sfull:-}"
    row="$row,$pfhr"

    echo "$row"       >> "$csv"
    echo "$k,$row"    >> "$COMBINED"
    printf "%-7s %-7s %-8s %-7s %-6s %-7s %-7s %-9s %s\n" \
           "$n" "$r" "${tc:--}" "$cpe" "${eps:--}" "${pk:--}" "${acp:--}" "${pfa:--}→${pfh:--}" "${sblk:--}"
  done
  echo "  -> $csv  ($(($(head -1 "$csv" | tr ',' '\n' | wc -l))) columns)"
done
echo ""
echo "combined: $COMBINED"
