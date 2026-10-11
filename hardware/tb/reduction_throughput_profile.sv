// SPDX-License-Identifier: SHL-0.51
// Additional read-only events for independent completion-throughput ablations.
bind ara_sequencer reduction_stall_profile #(.Kind("word_credit"),.N(5)) i_word_credit_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    ara_req_valid_i && ara_req_ready_o && word_credit_request &&
      insn_queue_cnt_q[VFU_SlideUnit] >= InsnQueueDepth[VFU_SlideUnit],
    word_credit_count_q == WordCreditDepth+1,
    ara_req_valid_i && !word_credit_issue,
    word_credit_down,
    word_credit_up
  })
);
bind reduction_completion_engine reduction_stall_profile #(.Kind("seed_lookahead"),.N(3)) i_seed_lookahead_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    prepared_valid_q && result_fire,
    background_q && state_q == HOLD,
    background_q
  })
);
bind valu reduction_stall_profile #(.Kind("queue_valu"),.N(4)) i_queue_profile (
  .clk_i, .rst_ni, .lane_i(64'(lane_id_i)), .events_i({
    result_queue_recycle && result_queue_full && valu_valid && narrowing(vinsn_issue_q.op),
    result_queue_recycle && result_queue_full && valu_valid,
    result_queue_recycle && result_queue_full,
    result_queue_recycle
  })
);
bind vmfpu reduction_stall_profile #(.Kind("queue_vmfpu"),.N(4)) i_queue_profile (
  .clk_i, .rst_ni, .lane_i(64'(lane_id_i)), .events_i({
    result_queue_recycle && result_queue_full && unit_out_valid && narrowing(vinsn_processing_q.cvt_resize),
    result_queue_recycle && result_queue_full && unit_out_valid,
    result_queue_recycle && result_queue_full,
    result_queue_recycle
  })
);
bind vmfpu reduction_stall_profile #(.Kind("exact_egress"),.N(4)) i_egress_profile (
  .clk_i, .rst_ni, .lane_i(64'(lane_id_i)), .events_i({
    mfpu_red_valid_o && mfpu_red_ready_i && uses_exact_rce(vinsn_processing_q) &&
      uses_exact_rce(vinsn_commit) && vinsn_processing_q.id != vinsn_commit.id,
    fpu_red_complete_d && rce_handoff && uses_exact_rce(vinsn_processing_q),
    rce_handoff && uses_exact_rce(vinsn_processing_q),
    RceExactEgressReleaseEnable && rce_pending_q != '0
  })
);
bind reduction_completion_engine reduction_stall_profile #(.Kind("word_turnaround"),.N(4)) i_turnaround_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    RceWordTurnaroundEnable && result_fire && count_q > 1 &&
      (&received_now[next_ptr(read_q)]) && !command_q[next_ptr(read_q)].vl_zero,
    RceWordTurnaroundEnable && state_q == IDLE && valid_q[read_q] &&
      (&received_now[read_q]) && !(&received_q[read_q]) && !command_q[read_q].vl_zero,
    result_fire && command_fire && count_q == ContextDepth,
    result_fire && command_fire
  })
);
// Restart events separate admission, actual overlap, and retirement.
bind vmfpu reduction_stall_profile #(.Kind("mfpu_restart"),.N(4)) i_restart_profile (
  .clk_i, .rst_ni, .lane_i(64'(lane_id_i)), .events_i({
    (mfpu_state_q == INTRA_LANE_REDUCTION && result_queue_cnt_q != 0 &&
      ((vfpu_in_valid && vfpu_in_ready) || (exact_sum_in_valid && exact_sum_in_ready))),
    (mfpu_state_q != NO_REDUCTION && vinsn_commit_valid &&
      !is_reduction(vinsn_commit.op) && mfpu_vinsn_done_o[vinsn_commit.id]),
    (mfpu_state_q != NO_REDUCTION && rce_ordinary_drain &&
      ((mfpu_result_gnt_i && !rce_writeback) || mask_operand_gnt)),
    (mfpu_state_q == NO_REDUCTION && mfpu_state_d == INTRA_LANE_REDUCTION &&
      result_queue_cnt_d != 0)
  })
);
bind reduction_completion_engine reduction_stall_profile #(.Kind("fp_feedback"),.N(2)) i_feedback_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    fp_feedback_request && !fp_in_ready,
    fp_feedback_request && fp_in_ready
  })
);
`ifdef ARA_RED_REGISTER_VERSIONS
bind ara_sequencer reduction_stall_profile #(.Kind("seed_dispatch"),.N(4)) i_seed_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    late_seed_candidate && pe_req_valid_d && writer_external_q[late_seed_producer],
    late_seed_candidate && pe_req_valid_d && writer_ordinary_q[late_seed_producer] &&
      !writer_external_q[late_seed_producer] &&
      (writer_mfpu_q[late_seed_producer] == (vfu(ara_req_i.op) == VFU_MFpu)),
    late_seed_candidate && pe_req_valid_d && writer_ordinary_q[late_seed_producer],
    late_seed_candidate && pe_req_valid_d
  })
);
`endif
bind vmfpu reduction_stall_profile #(.Kind("hetero_compute"),.N(3)) i_hetero_profile (
  .clk_i, .rst_ni, .lane_i(64'(lane_id_i)), .events_i({
    uses_rce(vinsn_issue_q) && uses_rce(vinsn_commit) && vinsn_issue_q.id != vinsn_commit.id &&
      ((vfpu_in_valid && vfpu_in_ready) || (exact_sum_in_valid && exact_sum_in_ready)) &&
      vinsn_issue_q.vm != vinsn_commit.vm,
    uses_rce(vinsn_issue_q) && uses_rce(vinsn_commit) && vinsn_issue_q.id != vinsn_commit.id &&
      ((vfpu_in_valid && vfpu_in_ready) || (exact_sum_in_valid && exact_sum_in_ready)) &&
      vinsn_issue_q.vtype.vsew != vinsn_commit.vtype.vsew,
    uses_rce(vinsn_issue_q) && uses_rce(vinsn_commit) && vinsn_issue_q.id != vinsn_commit.id &&
      ((vfpu_in_valid && vfpu_in_ready) || (exact_sum_in_valid && exact_sum_in_ready)) &&
      vinsn_issue_q.global_vl != vinsn_commit.global_vl
  })
);
