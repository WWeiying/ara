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
if [ "${KERNEL_SWEEP_LOCK_HELD:-0}" != "1" ]; then
  LOCK_NAME="${PWD//\//_}_${OUT//\//_}"
  exec 9>"/tmp/ara_hdv_kernel_sweep_${LOCK_NAME}.lock"
  if ! flock -n 9; then
    echo "[lock] another kernel sweep/sum is using $OUT; waiting..."
    flock 9
  fi
  export KERNEL_SWEEP_LOCK_HELD=1
fi

log=""
LAST_ROW=""
kv() { grep -hE "$1" "$log" 2>/dev/null | grep -oE "$2[[:space:]]*=[[:space:]]*[0-9]+" | head -1 | grep -oE '[0-9]+$'; }
d()  { grep -hE "$1" "$log" 2>/dev/null | grep -oE "$2=[0-9]+" | head -1 | grep -oE '[0-9]+'; }

KERNEL_H_ID="group,kernel,tag,avl,size,rows,n,result,task_cycles,cyc_per_elem,cyc_per_macc,wall_cycles,eps,vec_busy,imem_outstanding"
KERNEL_H_HDV="ep_ack,ep_vset_ack,vq_push,vq_pop,vq_max_occ,vq_bypass,vq_full_stall,dispatch_slots,dispatch_cycles,fsm_could_bypass,operand_wait_cycles_raw,ara_backpressure_cycles,real_wait_stall,resp_meta_stall,resp_meta_max"
KERNEL_H_HEU_EP="ep_count,packed_inst_count,packed_scalar_inst_count,packed_vector_inst_count,ep_width_sum,ep_width_gt1_count,ep_scalar_vector_count,used_issue_slots,available_issue_slots,heu_to_current,heu_to_buffer,heu_scalar_only,heu_vector_only,heu_pf_hint_ep,heu_pf_disable_ep,heu_pf_mode_1x,heu_pf_mode_2x,heu_pf_mode_4x,heu_pf_mode_8x"
KERNEL_H_HEU_FE="heu_valid_cyc,heu_ready_block_cyc,heu_block_buffer_cyc,heu_block_branch_cyc,heu_current_busy_cyc,heu_buffer_valid_cyc,heu_scalar_out_cyc,heu_vector_out_cyc"
KERNEL_H_HEU_OVLP="early_issue_attempts,early_issue_grants,early_issue_blocked_by_dispatch,early_issue_blocked_by_queue,early_issue_blocked_by_branch,early_issue_blocked_by_scalar_mem,early_issue_blocked_by_dependency,early_issue_blocked_by_gpr_dependency,early_issue_blocked_by_fpr_dependency,early_issue_blocked_by_vector_dependency,cross_ep_inflight_cycles,overlap_cycles"
KERNEL_H_VDU_CMD="vector_cmd_valid_cycles,vector_cmd_fire_count,vector_cmd_blocked_cycles,cmd_window_avg_occ,cmd_window_sum_occ,cmd_window_sample_cycles,cmd_window_max_occ,cmd_window_full_cycles,cmd_window_empty_cycles,vq_avg_occ,vq_empty_cycles,vq_full_cycles,resp_meta_sum_occ,resp_meta_sample_cycles"
KERNEL_H_VDU_OPERAND="scalar_operand_capture_count,scalar_operand_bypass_hit,scalar_operand_wait_cycles,vset_visible_wait_cycles,scalar_operand_bypass,scalar_operand_lookahead_req,scalar_operand_lookahead_hit,scalar_operand_port_busy,vector_ep_enqueue,vector_ep_pending_enqueue,vector_ep_ready_block"
KERNEL_H_IPU="ipu_ready_cyc,ipu_ready_stall,ipu_sram_stall,ipu_serve_cyc,packets,bypass_hits,demand_reads,avg_cyc_per_pkt,task_ifetch_packets,seamv_ifetch_bytes,hint_instruction_count,hint_bytes,tc_equiv_ifetch_bytes"
KERNEL_H_AG="demand_ar,pf_ar,pf_hit,loads,pf_en_cyc,demand_aw,demand_B,pf_B"
KERNEL_H_AGPF="pf_ar_rob_full,pf_ar_lkup_full,pf_ar_pending,pf_ar_dis,pf_2nd,dem_rob_block,pf_disabled,pf_page_cross,pf_queue_full,pf_avl_low"
KERNEL_H_AGPF2="pf_throttled_cycles,pf_late,pf_unused,pf_wait_match_cyc,pf_wait_match_evt,pf_queue_valid_cyc,pf_queue_block_cyc,pf_lkup_full_cyc,pf_rob_full_cyc,pf_pending_cyc,pf_stream_break,pf_future_keep,pf_queue_match_cyc,pf_rob_match_cyc,pf_page_wait_cyc"
KERNEL_H_SEQ="seq_issue,seq_blocked_cycles,seq_raw_cycles,seq_war_cycles,seq_waw_cycles,seq_waw_block,seq_ep_bypass,seq_full"
KERNEL_H_SEQHDV="hazard_check_count,same_ep_hazard_candidate,hazard_pruned_by_ep,seq_true_hazard_stall,seq_false_hazard_stall,seq_queue_full_stall,seq_lane_desync_stall,seq_operand_req_stall,seq_wait_state_cyc,seq_mem_wait_cyc"
KERNEL_H_DERIV="pf_hit_rate,seamv_tc_ifetch_ratio"
KERNEL_ROWHDR="$KERNEL_H_ID,$KERNEL_H_HDV,$KERNEL_H_HEU_EP,$KERNEL_H_HEU_FE,$KERNEL_H_HEU_OVLP,$KERNEL_H_VDU_CMD,$KERNEL_H_VDU_OPERAND,$KERNEL_H_IPU,$KERNEL_H_AG,$KERNEL_H_AGPF,$KERNEL_H_AGPF2,$KERNEL_H_SEQ,$KERNEL_H_SEQHDV,$KERNEL_H_DERIV"

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

  local hacc hcur hbuf hws hsc hvc hwgt hm hso hvo his hpfh hpfd hpf1 hpf2 hpf4 hpf8
  hacc=$(kv 'PERF-HEU-EP' 'accept'); hcur=$(kv 'PERF-HEU-EP' 'to_current')
  hbuf=$(kv 'PERF-HEU-EP' 'to_buffer'); hws=$(kv 'PERF-HEU-EP' 'width_sum')
  hsc=$(kv 'PERF-HEU-EP' 'scalar_inst'); hvc=$(kv 'PERF-HEU-EP' 'vector_inst')
  hwgt=$(kv 'PERF-HEU-EP' 'width_gt1'); hm=$(kv 'PERF-HEU-EP' 'mixed')
  hso=$(kv 'PERF-HEU-EP' 'scalar_only'); hvo=$(kv 'PERF-HEU-EP' 'vector_only')
  his=$(kv 'PERF-HEU-EP' 'issue_slots'); hpfh=$(kv 'PERF-HEU-EP' 'pf_hint_ep')
  hpfd=$(kv 'PERF-HEU-EP' 'pf_disable_ep'); hpf1=$(kv 'PERF-HEU-EP' 'pf_mode_1x')
  hpf2=$(kv 'PERF-HEU-EP' 'pf_mode_2x'); hpf4=$(kv 'PERF-HEU-EP' 'pf_mode_4x')
  hpf8=$(kv 'PERF-HEU-EP' 'pf_mode_8x')

  local hfv hfb hbb hbr hcb hbv hso_c hvo_c
  hfv=$(kv 'PERF-HEU-FE' 'valid_cyc'); hfb=$(kv 'PERF-HEU-FE' 'ready_block_cyc')
  hbb=$(kv 'PERF-HEU-FE' 'block_buffer_cyc'); hbr=$(kv 'PERF-HEU-FE' 'block_branch_cyc')
  hcb=$(kv 'PERF-HEU-FE' 'current_busy_cyc'); hbv=$(kv 'PERF-HEU-FE' 'buffer_valid_cyc')
  hso_c=$(kv 'PERF-HEU-FE' 'scalar_out_cyc'); hvo_c=$(kv 'PERF-HEU-FE' 'vector_out_cyc')

  local hea heg hebd hebq hebb hebm hegd hefd hevd hcross hover
  hea=$(kv 'PERF-HEU-OVLP' 'early_attempt'); heg=$(kv 'PERF-HEU-OVLP' 'early_grant')
  hebd=$(kv 'PERF-HEU-OVLP' 'early_blk_dispatch'); hebq=$(kv 'PERF-HEU-OVLP' 'early_blk_queue')
  hebb=$(kv 'PERF-HEU-OVLP' 'early_blk_branch')
  hebm=$(kv 'PERF-HEU-OVLP' 'early_blk_scalar_mem'); hegd=$(kv 'PERF-HEU-OVLP' 'early_blk_gpr_dep')
  hefd=$(kv 'PERF-HEU-OVLP' 'early_blk_fpr_dep'); hevd=$(kv 'PERF-HEU-OVLP' 'early_blk_vec_dep')
  hcross=$(kv 'PERF-HEU-OVLP' 'cross_ep_cyc'); hover=$(kv 'PERF-HEU-OVLP' 'overlap_cyc')

  local vcv vcf vcb vcso vcsc vcfc vcec vrso vrsc
  vcv=$(kv 'PERF-VDU-CMD' 'vector_cmd_valid'); vcf=$(kv 'PERF-VDU-CMD' 'vector_cmd_fire')
  vcb=$(kv 'PERF-VDU-CMD' 'vector_cmd_blocked'); vcso=$(kv 'PERF-VDU-CMD' 'cmd_window_sum_occ')
  vcsc=$(kv 'PERF-VDU-CMD' 'cmd_window_sample_cyc'); vcfc=$(kv 'PERF-VDU-CMD' 'cmd_window_full_cyc')
  vcec=$(kv 'PERF-VDU-CMD' 'cmd_window_empty_cyc'); vrso=$(kv 'PERF-VDU-CMD' 'resp_meta_sum_occ')
  vrsc=$(kv 'PERF-VDU-CMD' 'resp_meta_sample_cyc')

  local soc sob solr solh sopb vep vep_p vep_b vsetw
  soc=$(kv 'PERF-VDU-OPERAND' 'scalar_operand_capture')
  sob=$(kv 'PERF-VDU-OPERAND' 'scalar_operand_bypass')
  solr=$(kv 'PERF-VDU-OPERAND' 'scalar_operand_lookahead_req')
  solh=$(kv 'PERF-VDU-OPERAND' 'scalar_operand_lookahead_hit')
  sopb=$(kv 'PERF-VDU-OPERAND' 'scalar_operand_port_busy')
  vep=$(kv 'PERF-VDU-OPERAND' 'vector_ep_enqueue')
  vep_p=$(kv 'PERF-VDU-OPERAND' 'vector_ep_pending_enqueue')
  vep_b=$(kv 'PERF-VDU-OPERAND' 'vector_ep_ready_block')
  vsetw=$(kv 'PERF-VDU-OPERAND' 'vset_visible_wait_cycles')

  local irc irs isr isc pk byh dmr acp tip sib hic hib tib
  irc=$(kv 'IPU-PERF' 'ready_cyc'); irs=$(kv 'IPU-PERF' 'ready_stall')
  isr=$(kv 'IPU-PERF' 'stall_due_to_sram'); isc=$(kv 'IPU-PERF' 'serve_cycles')
  pk=$(kv 'IPU-PERF' 'packets'); byh=$(kv 'IPU-PERF' 'bypass_hits')
  dmr=$(kv 'IPU-PERF' 'demand_reads'); acp=$(kv 'IPU-PERF' 'avg_cycles_per_pkt')
  tip=$(kv 'IPU-PERF' 'task_ifetch_packets')
  sib=$(kv 'IPU-PERF' 'seamv_ifetch_bytes')
  hic=$(kv 'IPU-PERF' 'hint_instruction_count')
  hib=$(kv 'IPU-PERF' 'hint_bytes')
  tib=$(kv 'IPU-PERF' 'tc_equiv_ifetch_bytes')

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

  local pth plt pun pwm pwe pqvc pqbc plfc prfc ppc2 psb pfk pqmc prmc ppwc
  pth=$(kv 'PERF-ADDRGEN-PF2' 'pf_throttle_cyc'); plt=$(kv 'PERF-ADDRGEN-PF2' 'pf_late')
  pun=$(kv 'PERF-ADDRGEN-PF2' 'pf_unused'); pwm=$(kv 'PERF-ADDRGEN-PF2' 'pf_wait_match_cyc')
  pwe=$(kv 'PERF-ADDRGEN-PF2' 'pf_wait_match_evt'); pqvc=$(kv 'PERF-ADDRGEN-PF2' 'pf_queue_valid_cyc')
  pqbc=$(kv 'PERF-ADDRGEN-PF2' 'pf_queue_block_cyc'); plfc=$(kv 'PERF-ADDRGEN-PF2' 'pf_lkup_full_cyc')
  prfc=$(kv 'PERF-ADDRGEN-PF2' 'pf_rob_full_cyc'); ppc2=$(kv 'PERF-ADDRGEN-PF2' 'pf_pending_cyc')
  psb=$(kv 'PERF-ADDRGEN-PF2' 'pf_stream_break'); pfk=$(kv 'PERF-ADDRGEN-PF2' 'pf_future_keep')
  pqmc=$(kv 'PERF-ADDRGEN-PF2' 'pf_queue_match_cyc'); prmc=$(kv 'PERF-ADDRGEN-PF2' 'pf_rob_match_cyc')
  ppwc=$(kv 'PERF-ADDRGEN-PF2' 'pf_page_wait_cyc')

  local sissue sblk sraw swar swaw swawb sepb sfull
  sissue=$(kv 'PERF-SEQ' 'issue'); sblk=$(kv 'PERF-SEQ' 'blocked')
  sraw=$(kv 'PERF-SEQ' 'raw'); swar=$(kv 'PERF-SEQ' 'war'); swaw=$(kv 'PERF-SEQ' 'waw')
  swawb=$(kv 'PERF-SEQ' 'waw_block'); sepb=$(kv 'PERF-SEQ' 'ep_bypass'); sfull=$(kv 'PERF-SEQ' 'full')

  local shc ssec shpr sth sfh sqfs slds sors swsc smwc
  shc=$(kv 'PERF-SEQ-HDV' 'hazard_check'); ssec=$(kv 'PERF-SEQ-HDV' 'same_ep_candidate')
  shpr=$(kv 'PERF-SEQ-HDV' 'hazard_pruned'); sth=$(kv 'PERF-SEQ-HDV' 'true_hazard_stall')
  sfh=$(kv 'PERF-SEQ-HDV' 'false_hazard_stall'); sqfs=$(kv 'PERF-SEQ-HDV' 'queue_full_stall')
  slds=$(kv 'PERF-SEQ-HDV' 'lane_desync_stall'); sors=$(kv 'PERF-SEQ-HDV' 'operand_req_stall')
  swsc=$(kv 'PERF-SEQ-HDV' 'wait_state_cyc'); smwc=$(kv 'PERF-SEQ-HDV' 'mem_wait_cyc')

  local pfhr="" stir=""
  if [ -n "$pfa" ] && [ "$pfa" -gt 0 ] 2>/dev/null; then
    pfhr=$(echo "scale=3; ${pfh:-0}/$pfa" | bc)
  fi
  if [ -n "$tib" ] && [ "$tib" -gt 0 ] 2>/dev/null; then
    stir=$(echo "scale=6; ${sib:-0}/$tib" | bc)
  fi
  local depblk="" sbph="" cmdavg="" vqavg=""
  if [ -n "$hegd" ] || [ -n "$hefd" ] || [ -n "$hevd" ]; then
    depblk=$(( ${hegd:-0} + ${hefd:-0} + ${hevd:-0} ))
  fi
  if [ -n "$sob" ] || [ -n "$solh" ]; then
    sbph=$(( ${sob:-0} + ${solh:-0} ))
  fi
  if [ -n "$vcso" ] && [ -n "$vcsc" ] && [ "$vcsc" -gt 0 ] 2>/dev/null; then
    cmdavg=$(echo "scale=3; $vcso/$vcsc" | bc)
    vqavg="$cmdavg"
  fi

  local row="$group,$kernel,$tag,$avl,$size,$rows,$n,$r,${tc:-},$cpe,$cpm,${wc:-},${eps:-},${vbusy:-},${imem:-}"
  row="$row,${ep_ack:-},${ep_vack:-},${vqpush:-},${vqpop:-},${vqmax:-},${vqbyp:-},${vqfs:-},${dslots:-},${dcyc:-},${fbyp:-},${owc:-},${abp:-},${rwfs:-},${rmfs:-},${rmmax:-}"
  row="$row,${hacc:-},${hws:-},${hsc:-},${hvc:-},${hws:-},${hwgt:-},${hm:-},${hws:-},${his:-},${hcur:-},${hbuf:-},${hso:-},${hvo:-},${hpfh:-},${hpfd:-},${hpf1:-},${hpf2:-},${hpf4:-},${hpf8:-}"
  row="$row,${hfv:-},${hfb:-},${hbb:-},${hbr:-},${hcb:-},${hbv:-},${hso_c:-},${hvo_c:-}"
  row="$row,${hea:-},${heg:-},${hebd:-},${hebq:-},${hebb:-},${hebm:-},${depblk:-},${hegd:-},${hefd:-},${hevd:-},${hcross:-},${hover:-}"
  row="$row,${vcv:-},${vcf:-},${vcb:-},${cmdavg:-},${vcso:-},${vcsc:-},${vqmax:-},${vcfc:-},${vcec:-},${vqavg:-},${vcec:-},${vcfc:-},${vrso:-},${vrsc:-}"
  row="$row,${soc:-},${sbph:-},${owc:-},${vsetw:-},${sob:-},${solr:-},${solh:-},${sopb:-},${vep:-},${vep_p:-},${vep_b:-}"
  row="$row,${irc:-},${irs:-},${isr:-},${isc:-},${pk:-},${byh:-},${dmr:-},${acp:-},${tip:-},${sib:-},${hic:-},${hib:-},${tib:-}"
  row="$row,${dar:-},${pfa:-},${pfh:-},${lds:-},${pfen:-},${daw:-},${dB:-},${pfB:-}"
  row="$row,${parf:-},${palf:-},${pap:-},${pad:-},${p2nd:-},${drb:-},${pdis:-},${ppc:-},${pqf:-},${pal:-}"
  row="$row,${pth:-},${plt:-},${pun:-},${pwm:-},${pwe:-},${pqvc:-},${pqbc:-},${plfc:-},${prfc:-},${ppc2:-},${psb:-},${pfk:-},${pqmc:-},${prmc:-},${ppwc:-}"
  row="$row,${sissue:-},${sblk:-},${sraw:-},${swar:-},${swaw:-},${swawb:-},${sepb:-},${sfull:-}"
  row="$row,${shc:-},${ssec:-},${shpr:-},${sth:-},${sfh:-},${sqfs:-},${slds:-},${sors:-},${swsc:-},${smwc:-},$pfhr,$stir"

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
      if [[ "$tag" == "vsger_hdv" ]]; then
        macc=$((128*n))
      else
        macc=$((n*n))
      fi
      if [[ "$tag" =~ ^vsgemm_m([0-9]+)_([0-9]+)r$ ]]; then
        rows="${BASH_REMATCH[2]}"
        if [ "${BASH_REMATCH[1]}" = "1" ] && [ "$rows" != "4" ]; then
          macc=32768
        else
          macc=$((n*n*n))
        fi
      fi
      append_log_row "blas" "$tag" "$tag" "" "$size" "$rows" "$n" 0 "$macc"
      ;;
    log_blaspf_*.log)
      rest=${stem#log_blaspf_}
      groups=""
      if [[ "$rest" =~ ^(.+)_([0-9]+)_([0-9]+)_([0-9]+)g$ ]]; then
        kernel="${BASH_REMATCH[1]}"
        lm="${BASH_REMATCH[2]}"
        n="${BASH_REMATCH[3]}"
        groups="${BASH_REMATCH[4]}"
        tag="${kernel}_m${lm}_${groups}g"
        macc=$((n*groups))
        append_log_row "blas" "$tag" "$tag" "" "$lm" "$groups" "$n" 0 "$macc"
      else
        n=${rest##*_}
        rest=${rest%_*}
        lm=${rest##*_}
        kernel=${rest%_*}
        tag="${kernel}_m${lm}"
        macc=$((n*lm*32))
        append_log_row "blas" "$tag" "$tag" "" "$lm" "$n" "$n" 0 "$macc"
      fi
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
