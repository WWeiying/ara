  // Simulation-only observers. No ready/valid or datapath signal is driven.
  integer resource_main [6], resource_cast [6];
  integer resource_half, resource_dot, resource_groups, resource_corrections;
  integer resource_requests, resource_main_blocked, resource_cast_blocked;
  integer resource_request_blocked, resource_fp_occupied, resource_busy;

`define RESOURCE_FP dut.i_fp_accumulator
`define RESOURCE_INT dut.i_profile_engine_int
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n || probe_clear) begin
      for (int s = 0; s < 6; s++) begin
        resource_main[s] = 0;
        resource_cast[s] = 0;
      end
      resource_half = 0;
      resource_dot = 0;
      resource_groups = 0;
      resource_corrections = 0;
      resource_requests = 0;
      resource_main_blocked = 0;
      resource_cast_blocked = 0;
      resource_request_blocked = 0;
      resource_fp_occupied = 0;
      resource_busy = 0;
    end else begin
      if (`RESOURCE_FP.fp_fire)
        resource_main[`RESOURCE_FP.entry_state_q[`RESOURCE_FP.fp_tag_in]]++;
      if (`RESOURCE_FP.cast_fire)
        resource_cast[`RESOURCE_FP.entry_state_q[`RESOURCE_FP.cast_index]]++;
      if (`RESOURCE_FP.half_fire) resource_half++;
      if (`RESOURCE_INT.s0_valid_q) resource_dot++;
      if (`RESOURCE_INT.dot_valid && `RESOURCE_INT.meta_group_end_q)
        resource_groups += $countones(`RESOURCE_INT.dot_stream_valid);
      resource_corrections += $countones(`RESOURCE_INT.correction_valid);
      if (dut.integer_result_valid && dut.integer_result_ready) resource_requests++;
      if (`RESOURCE_FP.fp_in_valid && !`RESOURCE_FP.fp_in_ready) resource_main_blocked++;
      if (`RESOURCE_FP.cast_found && !`RESOURCE_FP.cast_ready) resource_cast_blocked++;
      if (dut.integer_result_valid && !dut.integer_result_ready) resource_request_blocked++;
      if (`RESOURCE_FP.entry_occupancy != 0) resource_fp_occupied++;
      if (busy) resource_busy++;
    end
  end

  task automatic snapshot_resources(input integer id);
    integer main_total, cast_total;
    // Sample after the final result and all counter nonblocking assignments.
    @(negedge clk);
    main_total = 0;
    cast_total = 0;
    for (int s = 0; s < 6; s++) begin
      main_total += resource_main[s];
      cast_total += resource_cast[s];
    end
    assert (main_total + cast_total + resource_half == fp_uops &&
            resource_dot == dot_active_cycles &&
            resource_requests == accumulator_updates &&
            resource_groups == resource_corrections)
      else $fatal(1, "Resource monitor conservation case=%0d", id);
    assert (resource_main[0] == 0 && resource_main[1] == 0 &&
            resource_cast[2] == 0 && resource_cast[3] == 0 &&
            resource_cast[4] == 0 && resource_cast[5] == 0)
      else $fatal(1, "Unexpected FP port/state mapping");
    $display("QBS_RESOURCE case=%0d dot=%0d pairs=%0d groups=%0d corrections=%0d requests=%0d main=%0d cast=%0d half=%0d scale=%0d min_scale=%0d accum_dot=%0d accum_min=%0d cast_dot=%0d cast_aux=%0d main_blocked=%0d cast_blocked=%0d request_blocked=%0d fp_occupied=%0d busy=%0d",
      id, resource_dot, useful_pairs, resource_groups, resource_corrections,
      resource_requests, main_total, cast_total, resource_half,
      resource_main[2], resource_main[3], resource_main[4], resource_main[5],
      resource_cast[0], resource_cast[1], resource_main_blocked,
      resource_cast_blocked, resource_request_blocked, resource_fp_occupied, resource_busy);
  endtask
`undef RESOURCE_FP
`undef RESOURCE_INT
