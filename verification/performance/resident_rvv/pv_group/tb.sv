// SPDX-License-Identifier: Apache-2.0
// Directed protocol driver, not an arithmetic model or a real-lane integration.
module resident_pv_group_tb;
  timeunit 1ns;
  timeprecision 1ps;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic start_valid, start_ready, abort_req, abort_rejected, busy, authorized, fatal_error;
  logic [3:0] start_active, active, lane_abort;
  logic [3:0] lv, lr, rv, rr, ldv, ldr, lde;
  logic [3:0][63:0] data_in, data_out;
  logic [3:0][3:0] slot_in, slot_out;
  logic [3:0][7:0] be_in, be_out;
  logic [3:0][4:0] lf;
  logic dv, dr, de;
  logic [4:0] df;
  int cycles = 0, cases = 0, terminals = 0, writes = 0;
  int lane_writes[4], lane_dones[4];
  int stalled = 0, rejected = 0, cancel_cycles = 0, done_stalls = 0;
  logic [3:0] mask_model, stalled_prev;
  logic [3:0][63:0] data_prev;
  logic [3:0][3:0] slot_prev;
  logic [3:0][7:0] be_prev;
  logic authorized_prev, may_authorize;

  akv_resident_pv_group dut (
    .clk_i(clk), .rst_ni(rst_n), .start_valid_i(start_valid),
    .start_ready_o(start_ready), .start_active_i(start_active),
    .abort_i(abort_req), .abort_rejected_o(abort_rejected), .busy_o(busy),
    .active_o(active), .commit_authorized_o(authorized), .fatal_error_o(fatal_error),
    .lane_abort_o(lane_abort),
    .lane_result_valid_i(lv), .lane_result_ready_o(lr),
    .lane_result_data_i(data_in), .lane_result_slot_i(slot_in),
    .lane_result_be_i(be_in), .result_valid_o(rv), .result_ready_i(rr),
    .result_data_o(data_out), .result_slot_o(slot_out), .result_be_o(be_out),
    .lane_done_valid_i(ldv), .lane_done_ready_o(ldr), .lane_done_error_i(lde),
    .lane_done_flags_i(lf), .done_valid_o(dv), .done_ready_i(dr),
    .done_error_o(de), .done_flags_o(df)
  );

  task automatic check(input bit condition, input string message);
    if (!condition) $fatal(1, "case=%0d cycle=%0d: %s", cases, cycles, message);
  endtask

  task automatic tick;
    @(posedge clk);
    #1;
    @(negedge clk);
    #1;
  endtask

  task automatic quiet;
    start_valid = 0; start_active = 0; abort_req = 0;
    lv = 0; rr = 0; ldv = 0; lde = 0; lf = 0; dr = 0;
    for (int i = 0; i < 4; i++) begin
      data_in[i] = 64'h1234_5678_0000_0000 + 64'(i);
      slot_in[i] = 4'(i);
      be_in[i] = 8'hff >> i;
    end
  endtask

  task automatic begin_case(input logic [3:0] mask, input bit abort_at_start = 0);
    quiet();
    check(start_ready && !busy, "start not ready");
    cases++;
    start_active = mask; start_valid = 1; abort_req = abort_at_start;
    tick();
    start_valid = 0; start_active = ~mask; abort_req = 0;
    #1;
    check(active == mask && busy && !start_ready, "active mask was not latched");
    check(!authorized && rv == 0 && lr == 0, "start exposed writes");
  endtask

  task automatic finish_case(input bit error_expected, input logic [4:0] flags_expected,
                             input int writes_expected);
    int terminal_before;
    terminal_before = terminals;
    #1;
    check(dv && de == error_expected && df == flags_expected, "terminal mismatch");
    check(writes == writes_expected, "write count mismatch");
    for (int i = 0; i < 4; i++)
      check(lane_dones[i] == int'(active[i]), "missing/duplicate lane done");
    // A held start must not replace the transaction while terminal is stalled.
    start_valid = 1; start_active = 4'hf;
    repeat (3) begin
      tick();
      check(dv && de == error_expected && df == flags_expected && !start_ready,
            "terminal not held under backpressure");
      check(rv == 0 && lr == 0 && ldr == 0 && lane_abort == 0,
            "terminal still transferring lane work");
    end
    start_valid = 0; dr = 1;
    tick();
    dr = 0;
    check(terminals == terminal_before + 1 && start_ready && !dv && !busy && !authorized,
          "terminal not consumed exactly once");
    repeat (2) tick();
    check(terminals == terminal_before + 1 && !dv, "duplicate terminal");
    $display("PV_GROUP_CASE_PASS id=%0d error=%0d flags=%0d writes=%0d",
             cases, error_expected, flags_expected, writes);
  endtask

  task automatic complete(input logic [3:0] lanes, input logic [3:0] errors,
                          input logic [3:0][4:0] flags);
    ldv = lanes; lde = errors; lf = flags;
    #1;
    check((ldr & lanes) == lanes, "independent lane done not accepted");
    tick();
    ldv = 0; lde = 0; lf = 0;
    #1;
  endtask

  // Cycle-level checks deliberately do not inspect internal DUT state.
  always @(posedge clk) begin
    cycles++;
    if (cycles > 500) $fatal(1, "500-cycle watchdog");
    if (!rst_n) begin
      mask_model = 0; stalled_prev = 0; authorized_prev = 0; may_authorize = 0;
    end else begin
      if (start_valid && start_ready) begin
        mask_model = start_active;
        writes = 0;
        for (int i = 0; i < 4; i++) begin
          lane_writes[i] = 0;
          lane_dones[i] = 0;
        end
      end
      check((rv & ~mask_model) == 0 && (lr & ~mask_model) == 0 &&
            (ldr & ~mask_model) == 0 && (lane_abort & ~mask_model) == 0,
            "inactive lane participated");
      check(authorized || (rv == 0 && lr == 0), "external exposure before authorization");
      if (authorized && !authorized_prev)
        check(may_authorize, "authorization without all-lane successful barrier");
      if (authorized) check(lane_abort == 0, "abort leaked after authorization");
      if (abort_req && authorized) begin
        check(abort_rejected, "late abort not reported");
        rejected++;
      end
      if (lane_abort != 0) begin
        check(lane_abort == mask_model && rv == 0 && lr == 0, "partial cancel/write on cancel");
        cancel_cycles++;
      end
      for (int i = 0; i < 4; i++) begin
        if (stalled_prev[i])
          check(rv[i] && data_out[i] == data_prev[i] && slot_out[i] == slot_prev[i] &&
                be_out[i] == be_prev[i], "stalled valid/payload withdrawn or changed");
        if (rv[i]) begin
          check(data_out[i] == data_in[i] && slot_out[i] == slot_in[i] &&
                be_out[i] == be_in[i], "lane payload/metadata misrouted");
          if (!rr[i]) stalled++;
        end else check(data_out[i] == 0 && slot_out[i] == 0 && be_out[i] == 0,
                       "invalid lane payload not gated");
        check((rv[i] && rr[i]) == (lv[i] && lr[i]), "ready bypass/duplicate write");
        if (rv[i] && rr[i]) begin
          lane_writes[i]++;
          writes++;
        end
        if (ldv[i] && ldr[i]) begin
          lane_dones[i]++;
          check(lane_dones[i] == 1, "duplicate lane completion consumed");
        end
      end
      if (dv) begin
        for (int i = 0; i < 4; i++)
          check(lane_dones[i] == int'(mask_model[i]), "terminal before all lanes drained");
        if (dr) terminals++;
        else done_stalls++;
      end
      stalled_prev = rv & ~rr;
      data_prev = data_out; slot_prev = slot_out; be_prev = be_out;
      authorized_prev = authorized;
      may_authorize = busy && !authorized && mask_model != 0 &&
                      (lv & mask_model) == mask_model && !abort_req &&
                      (ldv & mask_model) == 0 && lane_abort == 0;
    end
  end

  initial begin
    quiet();
    repeat (2) tick();
    rst_n = 1;
    tick();

    if ($test$plusargs("POSTCOMMIT_ERROR")) begin
      begin_case(4'h3);
      lv = 4'h3; rr = 4'h1; tick(); tick(); lv[0] = 0;
      #1;
      check(writes == 1 && rv == 4'h2 && authorized, "negative test not partially written");
      $display("PV_GROUP_EXPECT_POSTCOMMIT_FATAL writes=1");
      complete(4'h1, 4'h1, '1);
      $fatal(1, "MISSING post-authorization lane error assertion");
    end

    // An idle abort must never be routed to a lane or disturb a previous owner.
    abort_req = 1;
    repeat (2) tick();
    check(lane_abort == 0 && !busy && !authorized && !dv, "idle abort leaked to lanes");
    abort_req = 0;

    // 1: staggered first results; no write until all four are ready. Stall the
    // first exposed writes, then abort BEFORE any grant. It must be rejected.
    begin_case(4'hf);
    rr = 4'hf; lv = 4'h1; tick();
    check(!authorized && rv == 0 && lr == 0, "single lane crossed barrier");
    lv = 4'h7; tick();
    check(!authorized && rv == 0, "partial group crossed barrier");
    lv = 4'hf; rr = 0;
    #1; check(rv == 0, "authorization combinationally bypassed");
    tick();
    check(authorized && rv == 4'hf && writes == 0, "barrier not registered");
    abort_req = 1;
    repeat (3) tick();
    check(abort_rejected && rv == 4'hf && lane_abort == 0 && writes == 0,
          "late abort cancelled a stalled first exposure");
    rr = 4'h5; tick(); lv = 4'ha;
    complete(4'h1, 0, {5'd0, 5'd0, 5'd0, 5'd1});
    check(!dv && authorized, "terminal before other lanes complete");
    // Keep an already-consumed done high: it must never be consumed twice.
    ldv = 4'h1; lf[0] = 5'h1f;
    rr = 4'ha; tick(); lv = 0; ldv = 0;
    complete(4'h4, 0, {5'd0, 5'd4, 5'd0, 5'd0});
    complete(4'ha, 0, {5'd8, 5'd0, 5'd2, 5'd0});
    finish_case(0, 5'd15, 4);

    // 2: subset, inactive noise, two beats on one lane and independent grants.
    begin_case(4'h5);
    ldv = 4'ha; lde = 4'ha; lf = '1;
    lv = 4'hb; rr = 4'hf; tick();
    check(!authorized && lane_abort == 0, "inactive fault affected group");
    lv = 4'hf; tick();
    check(rv == 4'h5 && lr == 4'h5, "subset gating mismatch");
    rr = 4'h1; tick();
    data_in[0]++; slot_in[0] = 4'd8; be_in[0] = 8'h03;
    tick(); lv[0] = 0;
    complete(4'h1, 0, {5'd0, 5'd0, 5'd0, 5'd16});
    rr = 4'h4; tick(); lv = 0;
    complete(4'h4, 0, {5'd0, 5'd1, 5'd0, 5'd0});
    check(lane_writes[0] == 2 && lane_writes[2] == 1, "per-lane beat count");
    finish_case(0, 5'd17, 3);

    // 3: early lane error while peers have private results; drain done pulses
    // independently, including one successful drain whose flags must be hidden.
    begin_case(4'hf);
    lv = 4'h5; rr = 4'hf;
    complete(4'h2, 4'h2, '1);
    check(lane_abort == 4'hf && !authorized, "peer error did not cancel all lanes");
    lv = 0; repeat (4) tick();
    check(!dv && ldr == 4'hd, "cancel did not wait for outstanding lanes");
    complete(4'h8, 0, '1);
    complete(4'h1, 4'h1, '1);
    check(!dv, "cancel terminal too early");
    complete(4'h4, 4'h4, '1);
    finish_case(1, 0, 0);

    // 4: abort wins on the very edge that would authorize the final lane.
    begin_case(4'h3);
    lv = 4'h1; rr = 4'hf; tick();
    lv = 4'h3; abort_req = 1; tick();
    check(!authorized && lane_abort == 4'h3 && rv == 0, "abort lost barrier race");
    abort_req = 0; lv = 0;
    complete(4'h1, 4'h1, '1);
    repeat (3) tick(); check(!dv, "abort failed to drain slow lane");
    complete(4'h2, 4'h2, '1);
    finish_case(1, 0, 0);

    // 5: error also wins the authorization edge, even with all result valids.
    begin_case(4'hf);
    lv = 4'hf; rr = 4'hf;
    complete(4'h8, 4'h8, '1);
    check(!authorized && lane_abort == 4'hf, "error lost barrier race");
    lv = 0; complete(4'h7, 4'h7, '1);
    finish_case(1, 0, 0);

    // 6: all lanes reject together; terminal still requires the sampled dones.
    begin_case(4'hf);
    complete(4'hf, 4'hf, '1);
    finish_case(1, 0, 0);

    // 7: empty mask is accepted as one rejected transaction, never authorized.
    begin_case(0);
    lv = 4'hf; ldv = 4'hf; lde = 4'hf; rr = 4'hf;
    finish_case(1, 0, 0);

    // 8: abort concurrent with start cancels every launched active lane.
    begin_case(4'ha, 1);
    check(lane_abort == 4'ha, "start abort not broadcast");
    complete(4'h2, 4'h2, '1);
    complete(4'h8, 4'h8, '1);
    finish_case(1, 0, 0);

    // 9: success done before a result violates the lane protocol: fail closed.
    begin_case(4'h3);
    complete(4'h1, 0, '1);
    check(lane_abort == 4'h3 && !authorized, "early success done did not fail closed");
    complete(4'h2, 4'h2, '1);
    finish_case(1, 0, 0);

    // 10: single active lane, simultaneous success flags from one lane only.
    begin_case(4'h8);
    lv = 4'h8; rr = 4'hf; tick(); tick(); lv = 0;
    complete(4'h8, 0, {5'd4, 5'd0, 5'd0, 5'd0});
    finish_case(0, 5'd4, 1);

    check(cases == 10 && terminals == 10 && stalled > 0 && rejected > 0 &&
          cancel_cycles > 0 && done_stalls > 0 && !fatal_error, "directed coverage missing");
    $display("PV_GROUP_PASS cases=%0d terminals=%0d cycles=%0d stalled=%0d rejected=%0d cancel=%0d done_stalls=%0d",
             cases, terminals, cycles, stalled, rejected, cancel_cycles, done_stalls);
    $finish;
  end
  initial begin
    #10000;
    $fatal(1, "wall simulation watchdog");
  end
endmodule
