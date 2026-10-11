// SPDX-License-Identifier: SHL-0.51
// Read-only diagnostic: distinguish a waiting head from usable younger work.
// These predicates overlap and are not an additive latency decomposition.
bind reduction_completion_engine reduction_stall_profile #(
  .Kind("completion_wait"), .N(6)
) i_completion_wait_profile (
  .clk_i, .rst_ni, .lane_i(64'd0), .events_i({
    // 5: a returned final lane sum must still proceed through seed control.
    state_q == FP_WAIT && fp_out_valid && !fp_seed_q && lane_q == NrLanes-1,
    // 4: a ready successor has its own seed and complete source state.
    count_q > 1 && (&received_q[next_ptr(read_q)]) &&
      seed_ready_q[next_ptr(read_q)] &&
      !background_q && !prepared_valid_q &&
      ((state_q == SEED && !seed_ready_q[read_q]) ||
       (result_valid_o && !result_ready_i)),
    // 3: complete younger source state behind an incomplete head.
    count_q > 1 && (&received_q[next_ptr(read_q)]) &&
      state_q == IDLE && valid_q[read_q] && !(&received_q[read_q]),
    // 2: complete younger source state behind output backpressure.
    count_q > 1 && (&received_q[next_ptr(read_q)]) &&
      !prepared_valid_q && result_valid_o && !result_ready_i,
    // 1: complete younger source state behind a missing head seed.
    count_q > 1 && (&received_q[next_ptr(read_q)]) &&
      !background_q && !prepared_valid_q && state_q == SEED && !seed_ready_q[read_q],
    // 0: head waits for seed, whether or not useful younger work exists.
    !background_q && state_q == SEED && !seed_ready_q[read_q]
  })
);
