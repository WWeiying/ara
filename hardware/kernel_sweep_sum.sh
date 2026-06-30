#!/usr/bin/env bash
# Generate kernel_all.csv directly from sweep logs.
#
# Usage:
#   ./kernel_sweep_sum.sh [kernel_sweep_out]
#
# The per-kernel CSVs are intentionally not read here.  They are rewritten from
# the same log-derived rows used for kernel_all.csv, so stale CSV contents cannot
# leak into the aggregate.
set -uo pipefail
cd "$(dirname "$0")"

OUT="${1:-kernel_sweep_out}"
mkdir -p "$OUT"

log=""
LAST_ROW=""
kv() { grep -hE "$1" "$log" 2>/dev/null | grep -oE "$2[[:space:]]*=[[:space:]]*[0-9]+" | head -1 | grep -oE '[0-9]+$'; }
d()  { grep -hE "$1" "$log" 2>/dev/null | grep -oE "$2=[0-9]+" | head -1 | grep -oE '[0-9]+'; }

KERNEL_H_ID="group,kernel,tag,avl,size,rows,n,result,task_cycles,cyc_per_elem,cyc_per_macc,wall_cycles,eps,vec_busy,imem_outstanding"
KERNEL_H_HDV="ep_ack,ep_vset_ack,vq_push,vq_pop,vq_max_occ,vq_bypass,vq_full_stall,dispatch_slots,dispatch_cycles,fsm_could_bypass,operand_wait_cyc,ara_backpressure,real_wait_stall,resp_meta_stall,resp_meta_max"
KERNEL_H_IPU="ipu_ready_cyc,ipu_ready_stall,ipu_sram_stall,ipu_serve_cyc,packets,bypass_hits,demand_reads,avg_cyc_per_pkt"
KERNEL_H_AG="demand_ar,pf_ar,pf_hit,loads,pf_en_cyc,demand_aw,demand_B,pf_B"
KERNEL_H_AGPF="pf_ar_rob_full,pf_ar_lkup_full,pf_ar_pending,pf_ar_dis,pf_2nd,dem_rob_block,pf_disabled,pf_page_cross,pf_queue_full,pf_avl_low"
KERNEL_H_SEQ="seq_issue,seq_blocked,seq_raw,seq_war,seq_waw,seq_waw_block,seq_ep_bypass,seq_full"
KERNEL_H_DERIV="pf_hit_rate"
KERNEL_ROWHDR="$KERNEL_H_ID,$KERNEL_H_HDV,$KERNEL_H_IPU,$KERNEL_H_AG,$KERNEL_H_AGPF,$KERNEL_H_SEQ,$KERNEL_H_DERIV"

write_kernel_csv_row() {
  local group=$1 kernel=$2 tag=$3 avl=$4 size=$5 rows=$6 n=$7 elem_work=$8 macc_work=$9 csv=${10}

  local r tc wc eps vbusy imem cpe cpm
  r=$(grep -E 'mock host' "$log" | head -1 | grep -oE 'PASSED|FAILED'); [ -z "$r" ] && r="ERR"
  tc=$(kv 'mock host' 'total_task_cycles')
  wc=$(d 'HDV-CSR.*DONE' 'wall_cycle')
  eps=$(d 'HDV-CSR.*DONE' 'accepted'); [ -z "$eps" ] && eps=$(grep -E 'mock host' "$log" | grep -oE 'got [0-9]+' | grep -oE '[0-9]+')
  vbusy=$(d 'HDV-CSR.*DONE' 'vec_busy')
  imem=$(d 'HDV-CSR.*DONE' 'imem_outstanding')
  cpe=""; [ -n "$tc" ] && [ "${elem_work:-0}" -gt 0 ] 2>/dev/null && cpe=$(echo "scale=3; $tc/$elem_work" | bc)
  cpm=""; [ -n "$tc" ] && [ "${macc_work:-0}" -gt 0 ] 2>/dev/null && cpm=$(echo "scale=4; $tc/$macc_work" | bc)

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

  local parf palf pap pad p2nd drb pdis ppc pqf pal
  parf=$(kv 'PERF-ADDRGEN-PF' 'pf_ar_rob_full'); palf=$(kv 'PERF-ADDRGEN-PF' 'pf_ar_lkup_full')
  pap=$(kv 'PERF-ADDRGEN-PF' 'pf_ar_pending'); pad=$(kv 'PERF-ADDRGEN-PF' 'pf_ar_dis')
  p2nd=$(kv 'PERF-ADDRGEN-PF' 'pf_2nd'); drb=$(kv 'PERF-ADDRGEN-PF' 'dem_rob_block')
  pdis=$(kv 'PERF-ADDRGEN-PF' 'pf_disabled'); ppc=$(kv 'PERF-ADDRGEN-PF' 'pf_page_cross')
  pqf=$(kv 'PERF-ADDRGEN-PF' 'pf_queue_full'); pal=$(kv 'PERF-ADDRGEN-PF' 'pf_avl_low')

  local sissue sblk sraw swar swaw swawb sepb sfull
  sissue=$(kv 'PERF-SEQ' 'issue'); sblk=$(kv 'PERF-SEQ' 'blocked')
  sraw=$(kv 'PERF-SEQ' 'raw'); swar=$(kv 'PERF-SEQ' 'war'); swaw=$(kv 'PERF-SEQ' 'waw')
  swawb=$(kv 'PERF-SEQ' 'waw_block'); sepb=$(kv 'PERF-SEQ' 'ep_bypass'); sfull=$(kv 'PERF-SEQ' 'full')

  local pfhr=""
  if [ -n "$pfa" ] && [ "$pfa" -gt 0 ] 2>/dev/null; then
    pfhr=$(echo "scale=3; ${pfh:-0}/$pfa" | bc)
  fi

  local row="$group,$kernel,$tag,$avl,$size,$rows,$n,$r,${tc:-},$cpe,$cpm,${wc:-},${eps:-},${vbusy:-},${imem:-}"
  row="$row,${ep_ack:-},${ep_vack:-},${vqpush:-},${vqpop:-},${vqmax:-},${vqbyp:-},${vqfs:-},${dslots:-},${dcyc:-},${fbyp:-},${owc:-},${abp:-},${rwfs:-},${rmfs:-},${rmmax:-}"
  row="$row,${irc:-},${irs:-},${isr:-},${isc:-},${pk:-},${byh:-},${dmr:-},${acp:-}"
  row="$row,${dar:-},${pfa:-},${pfh:-},${lds:-},${pfen:-},${daw:-},${dB:-},${pfB:-}"
  row="$row,${parf:-},${palf:-},${pap:-},${pad:-},${p2nd:-},${drb:-},${pdis:-},${ppc:-},${pqf:-},${pal:-}"
  row="$row,${sissue:-},${sblk:-},${sraw:-},${swar:-},${swaw:-},${swawb:-},${sepb:-},${sfull:-},$pfhr"

  LAST_ROW="$row"
  echo "$row" >> "$csv"
}

find "$OUT" -maxdepth 1 -type f -name '*.csv' -delete

ALL="$OUT/kernel_all.csv"
echo "$KERNEL_ROWHDR" > "$ALL"
declare -A SINGLE_CSV_INIT=()

append_log_row() {
  local group=$1 kernel=$2 tag=$3 avl=$4 size=$5 rows=$6 n=$7 elem_work=$8 macc_work=$9
  local single="$OUT/${kernel}.csv"

  if [ -z "${SINGLE_CSV_INIT[$kernel]+x}" ]; then
    echo "$KERNEL_ROWHDR" > "$single"
    SINGLE_CSV_INIT[$kernel]=1
  fi

  write_kernel_csv_row "$group" "$kernel" "$tag" "$avl" "$size" "$rows" "$n" "$elem_work" "$macc_work" "$ALL"
  echo "$LAST_ROW" >> "$single"
}

while IFS= read -r log; do
  base=$(basename "$log")
  stem=${base%.log}

  case "$base" in
    build_*.log)
      continue
      ;;
    log_avl_*.log)
      rest=${stem#log_avl_}
      avl=${rest##*_}
      kernel=${rest%_*}
      append_log_row "avl" "$kernel" "" "$avl" "" "" "" "$avl" 0
      ;;
    log_blas_*.log)
      rest=${stem#log_blas_}
      n=${rest##*_}
      tag=${rest%_*}
      rows=""
      size="$n"
      macc=$((n*n))
      if [[ "$tag" =~ ^vsgemm_m([0-9]+)_([0-9]+)r$ ]]; then
        rows="${BASH_REMATCH[2]}"
        macc=$((n*n*n))
      fi
      append_log_row "blas" "$tag" "$tag" "" "$size" "$rows" "$n" 0 "$macc"
      ;;
    log_blaspf_*.log)
      rest=${stem#log_blaspf_}
      n=${rest##*_}
      rest=${rest%_*}
      lm=${rest##*_}
      kernel=${rest%_*}
      tag="${kernel}_m${lm}"
      macc=$((n*lm*32))
      append_log_row "blas" "$tag" "$tag" "" "$lm" "$n" "$n" 0 "$macc"
      ;;
    vssyrk_m1_fix.log|vstrsm_m1_fix.log|vsspmv_fix.log|fconv2d_fix.log|jacobi2d_fix.log|lavamd_fix.log|softmax_fix.log)
      append_log_row "fixed" "$stem" "$stem" "" "" "" "" 0 0
      ;;
    *_fix.log)
      continue
      ;;
  esac
done < <(find "$OUT" -maxdepth 1 -type f -name '*.log' | sort)

echo "  -> $ALL"
