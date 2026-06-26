#!/usr/bin/env bash
# B-tier (BLAS-2/3 + GEMM) sweep for HDV.  Companion to avl_sweep.sh (which
# covers the 1D streaming kernels).  Two axes, both one-click:
#
#   ./blas_sweep.sh vsgemm              # vsgemm {size 32/64/128} x {rows 1/2/4}
#   ./blas_sweep.sh blas                # BLAS-2/3 square kernels, sweep dim N
#   ./blas_sweep.sh all                 # both
#   ./blas_sweep.sh vsgemm "32 64"      # restrict the size/N list
#
# Why a separate script: the 1D sweep varies AVL purely via an RTL TB param
# (+HDV_INITIAL / static data, no app rebuild).  The B-tier needs either an app
# REBUILD per point (vsgemm: the {size,rows} variant is a compile-time -D) or a
# RUNTIME dimension register (BLAS: +HDV_A<k>=N).  In both cases the pointer args
# are passed as +HDV_A<k>=<addr> plusargs read live from the linked .dump (the
# src1/src2 addresses shift when code size changes), exactly like vsgemm has
# always been driven.
#
# Output: blas_sweep_out/<tag>.csv (per kernel/variant) + blas_sweep_out/all.csv
# + a live console table.  Same column set as avl_sweep.sh.

set -uo pipefail
cd "$(dirname "$0")"                 # hardware/
APPS=../apps

MODE="${1:-all}"
LIST="${2:-}"

OUT=blas_sweep_out
mkdir -p "$OUT"
COMBINED="$OUT/all.csv"

# ── perf-counter column set (identical order to avl_sweep.sh) ─────────────────
H_ID="tag,size,rows,n,result,task_cycles,cyc_per_macc,wall_cycles,eps,vec_busy,imem_outstanding"
H_HDV="ep_ack,ep_vset_ack,vq_push,vq_pop,vq_max_occ,vq_bypass,vq_full_stall,dispatch_slots,dispatch_cycles,fsm_could_bypass,operand_wait_cyc,ara_backpressure,real_wait_stall,resp_meta_stall,resp_meta_max"
H_IPU="ipu_ready_cyc,ipu_ready_stall,ipu_sram_stall,ipu_serve_cyc,packets,bypass_hits,demand_reads,avg_cyc_per_pkt"
H_AG="demand_ar,pf_ar,pf_hit,loads,pf_en_cyc,demand_aw,demand_B,pf_B"
H_SEQ="seq_issue,seq_blocked,seq_raw,seq_war,seq_waw,seq_waw_block,seq_ep_bypass,seq_full"
ROWHDR="$H_ID,$H_HDV,$H_IPU,$H_AG,$H_SEQ"
echo "$ROWHDR" > "$COMBINED"

log=""
kv() { grep -hE "$1" "$log" 2>/dev/null | grep -oE "$2[[:space:]]*=[[:space:]]*[0-9]+" | head -1 | grep -oE '[0-9]+$'; }
d()  { grep -hE "$1" "$log" 2>/dev/null | grep -oE "$2=[0-9]+" | head -1 | grep -oE '[0-9]+'; }

# addr_of <appdir> <symbol> -> decimal address of a .global from the .dump
# (the binary is stripped, but <app>.dump keeps the pre-strip `llvm-nm -n`).
addr_of() {
  local hex
  hex=$(grep -E "[0-9a-f]+ [A-Za-z] $2\$" "$APPS/$1/$1.dump" 2>/dev/null | head -1 | awk '{print $1}')
  [ -z "$hex" ] && { echo ""; return 1; }
  printf '%d' "0x$hex"
}

# parse_perf <tag> <size> <rows> <n> <macc> -> append a CSV row from $log
parse_perf() {
  local tag=$1 size=$2 rows=$3 n=$4 macc=$5
  local r tc wc eps vbusy imem cpm
  r=$(grep -E 'mock host' "$log" | head -1 | grep -oE 'PASSED|FAILED'); [ -z "$r" ] && r="ERR"
  tc=$(kv 'mock host' 'total_task_cycles')
  wc=$(d 'HDV-CSR.*DONE' 'wall_cycle')
  eps=$(d 'HDV-CSR.*DONE' 'accepted'); [ -z "$eps" ] && eps=$(grep -E 'mock host' "$log" | grep -oE 'got [0-9]+' | grep -oE '[0-9]+')
  vbusy=$(d 'HDV-CSR.*DONE' 'vec_busy')
  imem=$(d 'HDV-CSR.*DONE' 'imem_outstanding')
  cpm="-"; [ -n "$tc" ] && [ "$macc" -gt 0 ] 2>/dev/null && cpm=$(echo "scale=4; $tc/$macc" | bc)

  local ep_ack ep_vack vqpush vqpop vqmax vqbyp vqfs dslots dcyc fbyp owc abp rwfs rmfs rmmax
  ep_ack=$(kv 'HDV-PERF' 'ep_acknowledged'); ep_vack=$(kv 'HDV-PERF' 'ep_vset_acknowledged')
  vqpush=$(kv 'HDV-PERF' 'vq_push'); vqpop=$(kv 'HDV-PERF' 'vq_pop')
  vqmax=$(kv 'HDV-PERF' 'vq_max_occupancy'); vqbyp=$(kv 'HDV-PERF' 'vq_bypass')
  vqfs=$(kv 'HDV-PERF' 'vq_full_stall')
  dslots=$(kv 'HDV-PERF' 'dispatch_slots'); dcyc=$(kv 'HDV-PERF' 'dispatch_total_cycles')
  fbyp=$(kv 'HDV-PERF' 'fsm_could_bypass'); owc=$(kv 'HDV-PERF' 'operand_wait_cycles')
  abp=$(kv 'HDV-PERF' 'ara_backpressure'); rwfs=$(kv 'HDV-PERF' 'real_wait_full_stall')
  rmfs=$(kv 'HDV-PERF' 'resp_meta_full_stall'); rmmax=$(kv 'HDV-PERF' 'resp_meta_max')

  local irc irs isr isc pk byh dmr acp
  irc=$(kv 'IPU-PERF' 'ready_cyc'); irs=$(kv 'IPU-PERF' 'ready_stall')
  isr=$(kv 'IPU-PERF' 'stall_due_to_sram'); isc=$(kv 'IPU-PERF' 'serve_cycles')
  pk=$(kv 'IPU-PERF' 'packets'); byh=$(kv 'IPU-PERF' 'bypass_hits')
  dmr=$(kv 'IPU-PERF' 'demand_reads'); acp=$(kv 'IPU-PERF' 'avg_cycles_per_pkt')

  local dar pfa pfh lds pfen daw dB pfB
  dar=$(kv 'PERF-ADDRGEN\]' 'demand_ar'); pfa=$(kv 'PERF-ADDRGEN\]' 'pf_ar')
  pfh=$(kv 'PERF-ADDRGEN\]' 'pf_hit'); lds=$(kv 'PERF-ADDRGEN\]' 'loads')
  pfen=$(kv 'PERF-ADDRGEN\]' 'pf_en_cyc'); daw=$(kv 'PERF-ADDRGEN\]' 'demand_aw')
  dB=$(kv 'PERF-ADDRGEN\]' 'demand_B'); pfB=$(kv 'PERF-ADDRGEN\]' 'pf_B')

  local sissue sblk sraw swar swaw swawb sepb sfull
  sissue=$(kv 'PERF-SEQ' 'issue'); sblk=$(kv 'PERF-SEQ' 'blocked')
  sraw=$(kv 'PERF-SEQ' 'raw'); swar=$(kv 'PERF-SEQ' 'war'); swaw=$(kv 'PERF-SEQ' 'waw')
  swawb=$(kv 'PERF-SEQ' 'waw_block'); sepb=$(kv 'PERF-SEQ' 'ep_bypass'); sfull=$(kv 'PERF-SEQ' 'full')

  local row="$tag,$size,$rows,$n,$r,${tc:-},$cpm,${wc:-},${eps:-},${vbusy:-},${imem:-}"
  row="$row,${ep_ack:-},${ep_vack:-},${vqpush:-},${vqpop:-},${vqmax:-},${vqbyp:-},${vqfs:-},${dslots:-},${dcyc:-},${fbyp:-},${owc:-},${abp:-},${rwfs:-},${rmfs:-},${rmmax:-}"
  row="$row,${irc:-},${irs:-},${isr:-},${isc:-},${pk:-},${byh:-},${dmr:-},${acp:-}"
  row="$row,${dar:-},${pfa:-},${pfh:-},${lds:-},${pfen:-},${daw:-},${dB:-},${pfB:-}"
  row="$row,${sissue:-},${sblk:-},${sraw:-},${swar:-},${swaw:-},${swawb:-},${sepb:-},${sfull:-}"
  echo "$row" >> "$COMBINED"
  echo "$row" >> "$OUT/${tag}.csv"
  printf "%-18s %-5s %-5s %-7s %-8s %-9s %-7s %-7s %s\n" \
         "$tag" "$size" "$rows" "$r" "${tc:--}" "$cpm" "${eps:--}" "${vqmax:--}" "${sblk:--}seq_blk"
}

# ───────────────────────────── vsgemm variant sweep ──────────────────────────
# Two LMUL families x load-streams {1,2,4} x dimension N:
#   m1 (gemm_lmul=1): original fixed 32x32x32, validated; N is fixed 32.
#   m4 (gemm_lmul=4): unified, runtime N (+HDV_A3, no rebuild) over the N list.
# Load-streams {1,2,4} are compile-time (-DGEMM_ROWS, rebuild once each).
sweep_vsgemm() {
  local ns="${1:-16 32 64 128}"
  echo "==================== vsgemm  {lmul}x{rows}x{N} ===================="
  printf "%-18s %-5s %-5s %-7s %-8s %-9s %-7s %-7s %s\n" \
         "tag" "N" "rows" "result" "cycles" "cyc/macc" "EPs" "vq_max" "seq"
  for lmul in 1 4; do
    local nlist="$ns"
    [ "$lmul" = "1" ] && nlist="32"          # m1 kernels are fixed 32
    for rows in 1 2 4; do
      rm -f "$APPS/vsgemm_hdv/main.c.o"
      ( cd "$APPS" && timeout 300 make bin/vsgemm_hdv gemm_lmul=$lmul gemm_rows=$rows ) \
        > "/tmp/blas_build_vsgemm_m${lmul}_${rows}r.log" 2>&1
      local s1 s2
      s1=$(addr_of vsgemm_hdv src1); s2=$(addr_of vsgemm_hdv src2)
      if [ -z "$s1" ] || [ -z "$s2" ]; then
        echo "  vsgemm m${lmul} ${rows}r: BUILD/ADDR FAIL"; continue
      fi
      for n in $nlist; do
        local tag="vsgemm_m${lmul}_${rows}r"
        log=/tmp/blas_${tag}_${n}.log
        # m1 ignores +HDV_A3 (fixed 32); m4 reads it as N.
        timeout 600 make sim app=vsgemm_hdv \
          hdv_plusargs="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$s1 +HDV_A3=$n +HDV_EXPECTED_EP=8000000" \
          > "$log" 2>&1
        local macc=$((n*n*n))
        parse_perf "$tag" "$n" "$rows" "$n" "$macc"
      done
    done
  done
}

# ───────────────────────────── BLAS-2/3 dim-N sweep ──────────────────────────
# Each kernel reads its dimension N from a dedicated arg register (B_DIMREG);
# pointer args are fixed (static 128^2 data).  N swept at runtime via +HDV_A<k>.
# NOTE: requires the stride-register-ized kernels (see commit) — until then the
# fixed-32 kernels ignore N and this just runs a single effective size.
declare -A B_DIMREG=( [vssymv_hdv]=A3 [vssyrk_hdv]=A2 [vstrsm_hdv]=A2
                      [vsger_hdv]=A1  [vsgemv_hdv]=A3 )
# pointer plusargs template per kernel (filled with live addresses below).
sweep_blas() {
  local ns="${1:-16 32 64 128}"
  for k in vsger_hdv vssymv_hdv vssyrk_hdv vstrsm_hdv vsgemv_hdv; do
    rm -f "$APPS/$k/main.c.o"
    # m4 variant: runtime dimension N, sweepable (vsger is already register-param).
    ( cd "$APPS" && timeout 300 make bin/$k blas_lmul=4 ) > "/tmp/blas_build_${k}.log" 2>&1
    local s1 s2
    s1=$(addr_of "$k" src1); s2=$(addr_of "$k" src2)
    if [ -z "$s1" ]; then echo "  $k: BUILD/ADDR FAIL"; continue; fi
    echo "==================== $k  (dim sweep) ===================="
    printf "%-18s %-5s %-5s %-7s %-8s %-9s %-7s %-7s %s\n" \
           "tag" "size" "rows" "result" "cycles" "cyc/macc" "EPs" "vq_max" "seq"
    local reg=${B_DIMREG[$k]}
    for n in $ns; do
      # ABI per kernel: pointers in a0..a2, dimension N in $reg.  src2 holds the
      # second matrix/vectors; y/C alias as the kernel expects (see main.c).
      local ptrs
      case "$k" in
        vsger_hdv)  ptrs="+HDV_A0=32 +HDV_A2=$s2 +HDV_A3=$((s2+512)) +HDV_A4=$s1 +HDV_A1=$n" ;;
        vssymv_hdv) ptrs="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$s1 +HDV_A3=$n" ;;
        vssyrk_hdv) ptrs="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$n" ;;
        vstrsm_hdv) ptrs="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$n" ;;
        vsgemv_hdv) ptrs="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$((s2+512)) +HDV_A3=$n" ;;
      esac
      log=/tmp/blas_${k}_${n}.log
      timeout 600 make sim app=$k \
        hdv_plusargs="$ptrs +HDV_EXPECTED_EP=8000000" > "$log" 2>&1
      local macc=$((n*n))
      parse_perf "$k" "$n" "-" "$n" "$macc"
    done
  done
}

# Prefetch-enabled LMUL sweep of the suitable BLAS kernels (vssymv/vsgemv/vstrsm,
# all K=1 unit-stride matrix-row streams; vssyrk excluded — its hot load is strided
# vlse).  For each LMUL in {2,4,8} the kernel runs VL=VLMAX (AVL=2*VLMAX so the
# prefetch enable gate avl>=2*vl holds) over M rows of a VLMAX-wide matrix read from
# the 16384-float buffer (so M*VLMAX<=16384 -> M<=64 at m8).  Lead is 1X (next row).
sweep_blas_pf() {
  local ms="${1:-32 64}"
  for k in vssymv_hdv vsgemv_hdv vstrsm_hdv; do
    for lm in 2 4 8; do
      rm -f "$APPS/$k/main.c.o"
      ( cd "$APPS" && timeout 300 make bin/$k blas_lmul=$lm ) > "/tmp/blaspf_build_${k}_${lm}.log" 2>&1
      local s1 s2 yoff
      s1=$(addr_of "$k" src1); s2=$(addr_of "$k" src2)
      if [ -z "$s1" ]; then echo "  $k m$lm: BUILD/ADDR FAIL"; continue; fi
      yoff=$((lm*128))   # y/out past x = VLMAX*4 bytes into src2
      echo "============== $k  m$lm  (LMUL prefetch sweep) =============="
      printf "%-18s %-5s %-5s %-7s %-8s %-9s %-7s %-7s %s\n" \
             "tag" "m$lm" "rows" "result" "cycles" "cyc/macc" "EPs" "vq_max" "seq"
      for M in $ms; do
        local ptrs
        case "$k" in
          vssymv_hdv) ptrs="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$s1 +HDV_A3=$M" ;;
          vsgemv_hdv) ptrs="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$((s2+yoff)) +HDV_A3=$M" ;;
          vstrsm_hdv) ptrs="+HDV_A0=$s1 +HDV_A1=$s2 +HDV_A2=$M" ;;
        esac
        log=/tmp/blaspf_${k}_${lm}_${M}.log
        timeout 600 make sim app=$k \
          hdv_plusargs="$ptrs +HDV_EXPECTED_EP=8000000" > "$log" 2>&1
        parse_perf "${k}_m${lm}" "$lm" "$M" "$M" "$((M*lm*32))"
      done
    done
  done
}

case "$MODE" in
  vsgemm)  sweep_vsgemm "${LIST:-16 32 64 128}" ;;
  blas)    sweep_blas   "${LIST:-16 32 64 128}" ;;
  blas_pf) sweep_blas_pf "${LIST:-32 64}" ;;
  all)     sweep_vsgemm "16 32 64 128"; sweep_blas "16 32 64 128" ;;
  *) echo "usage: $0 {vsgemm|blas|blas_pf|all} [list]"; exit 1 ;;
esac
echo ""
echo "combined: $COMBINED"
