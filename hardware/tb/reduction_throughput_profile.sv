// SPDX-License-Identifier: SHL-0.51
// Additional read-only events for independent completion-throughput ablations.
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
