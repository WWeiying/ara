// SPDX-License-Identifier: SHL-0.51
// Read-only profiling bind. Explicitly add to a simulation filelist; not RTL.
module reduction_stall_profile #(
  parameter string Kind = "word",
  parameter int N = 16
) (
  input logic clk_i, rst_ni,
  input logic [63:0] lane_i,
  input logic [N-1:0] events_i
);
  longint unsigned counts[N];
  bit enabled;
  initial enabled = $test$plusargs("RCE_STALL_PROFILE");
  always @(posedge clk_i)
    if (!rst_ni) begin
      for (int i=0; i<N; i++) counts[i] = 0;
    end else if (enabled)
      for (int i=0; i<N; i++) counts[i] += events_i[i] === 1'b1;
  final if (enabled)
    for (int i=0; i<N; i++)
      $display("[RCE_STALL] kind=%s lane=%0d event=%0d cycles=%0d", Kind, lane_i, i, counts[i]);
endmodule

// Events are overlapping predicates, not an additive cycle breakdown.
bind reduction_completion_engine reduction_stall_profile #(.Kind("word")) i_stall_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    (result_fire && count_q == ContextDepth),                    // 15 full + pop
    (state_q == FP_WAIT && fp_out_valid && !fp_seed_q && lane_q != NrLanes-1), // 14 feedback boundary
    (state_q == MERGE && !active_q[read_q][lane_q]),              // 13 inactive merge lane
    ((state_q == MERGE || state_q == FOLD) && !(|active_q[read_q])), // 12 globally empty compute
    (state_q == HOLD && !result_ready_i),                        // 11 output backpressure
    (state_q == SEED && !seed_ready_q[read_q]),                   // 10 seed wait
    (state_q == IDLE && valid_q[read_q] && !(&received_q[read_q])), // 9 partial wait
    (state_q == IDLE && valid_q[read_q] && (&received_q[read_q])),  // 8 startup bubble
    result_fire,                                               // 7 completions
    (state_q == FP_WAIT),                                       // 6
    (state_q == HOLD),                                          // 5
    (state_q == SEED),                                          // 4
    (state_q == FOLD),                                          // 3
    (state_q == MERGE),                                         // 2
    (state_q == IDLE && valid_q[read_q]),                         // 1
    command_fire                                               // 0 commands
  })
);

bind valu reduction_stall_profile #(.Kind("valu"), .N(8)) i_stall_profile (
  .clk_i, .rst_ni, .lane_i(64'(lane_id_i)), .events_i({
    (alu_state_q == RCE_SEND && !rce_partial_ready_i),            // 7
    (alu_state_q == RCE_SEND && rce_partial_ready_i),             // 6
    (result_queue_full && alu_result_gnt_i && !rce_writeback),    // 5 full + pop
    (vinsn_issue_valid && !is_reduction(vinsn_issue_q.op) && uses_rce(vinsn_commit) &&
      alu_state_q == NO_REDUCTION && result_queue_full &&
      (alu_operand_valid_i[1] || !vinsn_issue_q.use_vs2) &&
      (alu_operand_valid_i[0] || !vinsn_issue_q.use_vs1) &&
      (mask_valid_i || vinsn_issue_q.vm)),                        // 4 ready normal op blocked by full queue
    (uses_rce(vinsn_commit) && result_queue_full),                // 3
    (valu_valid && !is_reduction(vinsn_issue_q.op) && uses_rce(vinsn_commit)), // 2 mixed normal fires
    (valu_valid && uses_rce(vinsn_issue_q)),                      // 1 local computes
    (rce_pending_q != '0)                                       // 0 pending completion
  })
);

bind vmfpu reduction_stall_profile #(.Kind("vmfpu"), .N(8)) i_stall_profile (
  .clk_i, .rst_ni, .lane_i(64'(lane_id_i)), .events_i({
    (mfpu_state_d == NO_REDUCTION && vinsn_queue_d.issue_cnt != 0 &&
      result_queue_cnt_d != 0 && uses_rce(vinsn_issue_d) &&
      vinsn_queue_d.processing_pnt == vinsn_queue_d.issue_pnt),  // 7 next reduction waits queue drain
    (result_queue_full && mfpu_result_gnt_i && !rce_writeback), // 6 full + pop
    (unit_out_valid && result_queue_full),                     // 5 execution result cannot enqueue
    (uses_rce(vinsn_commit) && result_queue_full),              // 4
    (rce_result_valid_i && rce_can_retire_o && lane_id_i == 0 && !mfpu_result_gnt_i), // 3 VRF wait
    rce_handoff,                                              // 2 local release
    (vinsn_issue_q_valid && !is_reduction(vinsn_issue_q.op) && uses_rce(vinsn_commit)), // 1 younger normal at issue
    (vinsn_commit_valid && uses_rce(vinsn_commit))              // 0 RCE at commit head
  })
);

bind sldu reduction_stall_profile #(.Kind("sldu"), .N(8)) i_stall_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    rce_completion_valid_o && !rce_completion_ready_i,          // 7 completed exact waits retirement
    rce_exact_local_complete_i,                               // 6
    rce_exact_events_i.seed_bind,                              // 5
    rce_exact_events_i.seed_wait,                              // 4
    rce_exact_events_i.limb_fire,                              // 3
    rce_exact_events_i.header_wait,                            // 2
    (state_q == SLIDE_WAIT_EXACT),                             // 1
    (state_q == SLIDE_RUN_EXACT)                               // 0
  })
);
