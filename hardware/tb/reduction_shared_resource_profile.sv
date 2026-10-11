// SPDX-License-Identifier: SHL-0.51
// Read-only diagnostics. Predicates overlap; do not sum them as latency.
// "Only credit" excludes other queue limits, not register/mask dependencies.
bind ara_sequencer reduction_stall_profile #(.Kind("shared_credit"), .N(6))
  i_shared_credit_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    ara_req_valid_i && !vinsn_queue_issue[VFU_SlideUnit] &&
      (&(vinsn_queue_issue | (NrVFUs'(1) << VFU_SlideUnit))), // 5 sole queue limit
    accepted_insn && target_vfus_vec[VFU_SlideUnit],        // 4 reservations
    ara_req_valid_i && !vinsn_queue_issue[VFU_SlideUnit] &&
      (ara_req_i.op inside {VSLIDEUP, VSLIDEDOWN}),          // 3 Slide held
    ara_req_valid_i && !vinsn_queue_issue[VFU_SlideUnit] &&
      ((ara_rce_pkg::RceIntEnable &&
        ara_req_i.op inside {[VREDSUM:VWREDSUM]}) ||
       ara_rce_pkg::rce_fp_word(ara_req_i.op, ara_req_i.vtype.vsew)), // 2 Word held
    ara_req_valid_i && !vinsn_queue_issue[VFU_SlideUnit],    // 1 shared credit held
    insn_queue_cnt_q[VFU_SlideUnit] >= InsnQueueDepth[VFU_SlideUnit] // 0 full
  })
);

// Used only with an RCE-enabled simulation profile.
bind ara reduction_stall_profile #(.Kind("shared_completion"), .N(5))
  i_shared_completion_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    gen_rce.word_result_valid && gen_rce.select_exact,       // 4 exact wins Word
    gen_rce.command_valid && !gen_rce.command_ready,        // 3 RCE receive full
    gen_rce.result_valid && (&rce_can_retire) &&
      !(|sldu_pe_resp.vinsn_done) && !rce_wb_ready[0],       // 2 VRF wait
    gen_rce.result_valid && !(&rce_can_retire),              // 1 commit owner wait
    gen_rce.result_valid && (&rce_can_retire) &&
      (|sldu_pe_resp.vinsn_done)                            // 0 completion collision
  })
);
