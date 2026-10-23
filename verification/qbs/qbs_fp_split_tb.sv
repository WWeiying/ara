module qbs_fp_split_tb;
  import qbs_pkg::*;
  localparam int Outputs = 128;
  localparam int Rounds = 4;
  localparam int Count = Outputs * Rounds;
  localparam int Modes = 3;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, clear = 0;
  int cursor[Modes];
  logic ready[Modes], busy[Modes], update[Modes];
  logic [6:0] update_index[Modes];
  logic [31:0] update_data[Modes], issues[Modes], updates[Modes];
  logic [4:0] flags[Modes];
  logic [31:0] observed[Modes][Outputs][Rounds];
  int seen[Modes][Outputs];
  int cycles, dual_issue, dual_return, different_return_flags;
  int half_issue, half_return_overlap;
  int half_cast_return, half_arith_return, triple_return, scale_read_pair;
  int epoch;
  bit live_reset_checked = 0;
  logic [31:0] seed = 32'h91be73d5;
  logic [31:0] dots[Count], aux[Count], activation[Count];
  logic [15:0] scales[Count], minima[Count];
  qbs_weight_profile_e profiles[Count];
  qbs_activation_profile_e activations[Count];
  localparam logic [15:0] HalfEdges[12] = '{
      16'h0000, 16'h8000, 16'h0001, 16'h03ff, 16'h0400, 16'h3c00,
      16'hbc00, 16'h7bff, 16'h7c00, 16'hfc00, 16'h7e13, 16'h7c01};
  localparam logic [31:0] FloatEdges[12] = '{
      32'h00000000, 32'h80000000, 32'h00000001, 32'h007fffff,
      32'h00800000, 32'h3f800000, 32'hbf800000, 32'h7f7fffff,
      32'h7f800000, 32'hff800000, 32'h7fc12345, 32'h7f800001};

  for (genvar mode = 0; mode < Modes; mode++) begin : gen_dut
    logic [4:0] expected_flags;
    wire valid = rst_n && !clear && cursor[mode] < Count;
    wire [$clog2(Count)-1:0] index = $clog2(Count)'(cursor[mode]);
    qbs_fp_accumulator #(.SplitIssue(mode != 0), .HalfScaleIssue(mode == 2)) dut (
      .clk_i(clk), .rst_ni(rst_n), .clear_i(clear),
      .request_valid_i(valid), .request_ready_o(ready[mode]),
      .request_slot_i(4'(cursor[mode] * 5)),
      .request_profile_i(profiles[index]),
      .request_activation_profile_i(activations[index]),
      .request_accumulator_index_i(7'(cursor[mode])),
      .request_first_block_i(cursor[mode] < Outputs),
      .request_dot_i(dots[index]), .request_aux_i(aux[index]),
      .request_weight_d_i(scales[index]), .request_weight_dmin_i(minima[index]),
      .request_activation_d_i(activation[index]),
      .read_index_i('0), .read_valid_o(), .read_data_o(),
      .bank_read_row_i('0), .bank_read_valid_o(), .bank_read_data_o(),
      .raw_seed_valid_i(1'b0), .raw_seed_ready_o(), .raw_seed_row_i('0),
      .raw_seed_mask_i('0), .raw_seed_data_i('{default:'0}),
      .update_valid_o(update[mode]), .update_index_o(update_index[mode]),
      .update_data_o(update_data[mode]), .fflags_o(flags[mode]), .busy_o(busy[mode]),
      .fp_uop_issue_o(issues[mode]), .table_occupancy_sum_o(),
      .table_occupancy_max_o(), .table_full_cycles_o(), .accumulator_updates_o(updates[mode])
    );
    always @(posedge clk) begin
      if (!rst_n || clear) cursor[mode] <= 0;
      else if (valid && ready[mode]) cursor[mode] <= cursor[mode] + 1;
    end
    // Sample both completion ports before the edge and check the registered OR.
    always @(posedge clk) begin
      if (!rst_n || clear) expected_flags = '0;
      else begin
        if (dut.fp_out_valid) expected_flags |= dut.fp_status;
        if (dut.cast_out_valid) expected_flags |= dut.cast_status;
      end
      #1;
      assert (flags[mode] === expected_flags)
        else $fatal(1, "Lost completion flags mode=%0d got=%h expected=%h",
                    mode, flags[mode], expected_flags);
    end
    always @(negedge clk) begin
      if (!rst_n || clear) begin
        for (int i = 0; i < Outputs; i++) seen[mode][i] = 0;
      end else if (update[mode]) begin
        assert (seen[mode][update_index[mode]] < Rounds)
          else $fatal(1, "Extra accumulator update");
        observed[mode][update_index[mode]][seen[mode][update_index[mode]]] = update_data[mode];
        seen[mode][update_index[mode]]++;
      end
    end
  end

  always @(posedge clk) begin
    if (rst_n && !clear) begin
      cycles++;
      if (gen_dut[1].dut.fp_fire && gen_dut[1].dut.cast_fire) dual_issue++;
      if (gen_dut[1].dut.fp_out_valid && gen_dut[1].dut.cast_out_valid) begin
        dual_return++;
        if (gen_dut[1].dut.fp_status != gen_dut[1].dut.cast_status)
          different_return_flags++;
      end
      if (gen_dut[2].dut.half_fire) half_issue++;
      if (gen_dut[2].dut.half_out_valid &&
          (gen_dut[2].dut.fp_out_valid || gen_dut[2].dut.cast_out_valid))
        half_return_overlap++;
      if (gen_dut[2].dut.half_out_valid && gen_dut[2].dut.cast_out_valid)
        half_cast_return++;
      if (gen_dut[2].dut.half_out_valid && gen_dut[2].dut.fp_out_valid) begin
        half_arith_return++;
        if (gen_dut[2].dut.cast_out_valid) triple_return++;
        if (gen_dut[2].dut.entry_state_q[gen_dut[2].dut.fp_tag_out] ==
            gen_dut[2].dut.FP_SCALE_MULTIPLY)
          scale_read_pair++;
      end
    end
    if (cycles > 50000) $fatal(1, "FP split watchdog");
  end

  initial begin
    cycles = 0;
    dual_issue = 0;
    dual_return = 0;
    different_return_flags = 0;
    half_issue = 0;
    half_return_overlap = 0;
    half_cast_return = 0;
    half_arith_return = 0;
    triple_return = 0;
    scale_read_pair = 0;
    for (int i = 0; i < Count; i++) begin
      seed = seed * 32'd1664525 + 32'd1013904223;
      dots[i] = i % 5 == 0 ? 32'h01000001 : seed;
      aux[i] = seed ^ 32'hcaa55aac;
      scales[i] = HalfEdges[(i / 9) % 12];
      minima[i] = HalfEdges[(i / 7 + 3) % 12];
      profiles[i] = qbs_weight_profile_e'(1 + i % 9);
      activations[i] = qbs_default_activation_profile(profiles[i]);
      activation[i] = activations[i] == QBS_ACTIVATION_PROFILE_Q8_0
          ? {16'b0, HalfEdges[(i / 3 + 5) % 12]} : FloatEdges[(i / 3 + 5) % 12];
    end
    repeat (3) @(negedge clk);
    #1;
    rst_n = 1;
    // Reset, unlike idle-only clear, must cancel both live FP pipelines.
    wait (gen_dut[1].dut.fp_busy && gen_dut[1].dut.cast_busy &&
          (|gen_dut[1].dut.entry_inflight_q));
    @(negedge clk);
    #1;
    assert (busy[1]) else $fatal(1, "Live reset did not target active work");
    rst_n = 0;
    repeat (3) @(negedge clk);
    #1;
    assert (!busy[0] && !busy[1] && !update[0] && !update[1] &&
            flags[0] == 0 && flags[1] == 0 && issues[0] == 0 && issues[1] == 0 &&
            updates[0] == 0 && updates[1] == 0)
      else $fatal(1, "Live reset left stale FP state");
    assert (!busy[2] && !update[2] && flags[2] == 0 && issues[2] == 0 && updates[2] == 0)
      else $fatal(1, "Live reset left stale half-scale state");
    live_reset_checked = 1;
    dual_issue = 0;
    dual_return = 0;
    different_return_flags = 0;
    rst_n = 1;
    wait (gen_dut[2].dut.half_busy);
    @(negedge clk);
    #1;
    assert (gen_dut[2].dut.half_busy) else $fatal(1, "Missing live half-scale reset");
    rst_n = 0;
    repeat (3) @(negedge clk);
    #1;
    assert (!busy[2] && !update[2] && flags[2] == 0 && issues[2] == 0)
      else $fatal(1, "Reset did not cancel half-scale work");
    half_issue = 0;
    half_return_overlap = 0;
    half_cast_return = 0;
    half_arith_return = 0;
    triple_return = 0;
    scale_read_pair = 0;
    rst_n = 1;
    for (epoch = 0; epoch < 2; epoch++) begin
      wait (cursor[0] == Count && cursor[1] == Count && cursor[2] == Count &&
            !busy[0] && !busy[1] && !busy[2]);
      repeat (2) @(negedge clk);
      for (int index = 0; index < Outputs; index++) begin
        assert (seen[0][index] == Rounds && seen[1][index] == Rounds && seen[2][index] == Rounds)
          else $fatal(1, "Missing update at %0d", index);
        for (int round_index = 0; round_index < Rounds; round_index++) begin
          assert (observed[0][index][round_index] === observed[1][index][round_index])
            else $fatal(1, "FP split differs index=%0d round=%0d old=%h new=%h",
                        index, round_index, observed[0][index][round_index],
                        observed[1][index][round_index]);
          assert (observed[0][index][round_index] === observed[2][index][round_index])
            else $fatal(1, "Half scale differs index=%0d round=%0d old=%h new=%h",
                        index, round_index, observed[0][index][round_index],
                        observed[2][index][round_index]);
        end
      end
      assert (flags[0] === flags[1] && issues[0] == issues[1] && updates[0] == Count && updates[1] == Count)
        else $fatal(1, "FP split flags or work mismatch");
      assert (flags[0] === flags[2] && issues[0] == issues[2] && updates[2] == Count)
        else $fatal(1, "Half scale flags or work mismatch");
      assert (half_issue > 0 && half_return_overlap > 0)
        else $fatal(1, "Half scale path not exercised");
      assert (half_cast_return > 0 && half_arith_return > 0 &&
              triple_return > 0 && scale_read_pair > 0)
        else $fatal(1, "Missing half return combination: cast=%0d arith=%0d triple=%0d scales=%0d",
                    half_cast_return, half_arith_return, triple_return, scale_read_pair);
      assert (dual_issue > 0 && dual_return > 0 && different_return_flags > 0)
        else $fatal(1, "Missing dual-return flag stress");
      $display("FP split epoch=%0d PASS updates=%0d flags=%h issues=%0d dual_issue=%0d dual_return=%0d mixed_flags=%0d",
               epoch, updates[1], flags[1], issues[1], dual_issue, dual_return, different_return_flags);
      $display("QBS half scale epoch=%0d PASS issues=%0d overlapped_returns=%0d",
               epoch, half_issue, half_return_overlap);
      $display("QBS half return combinations cast=%0d arith=%0d triple=%0d scale_read_pair=%0d",
               half_cast_return, half_arith_return, triple_return, scale_read_pair);
      if (epoch == 0) begin
        #1;
        clear = 1;
        repeat (2) @(negedge clk);
        #1;
        clear = 0;
      end
    end
    assert (live_reset_checked) else $fatal(1, "Missing live reset test");
    $display("QBS FP split PASS: live reset, two epochs, all intermediate outputs and per-cycle fflags");
    $finish;
  end
endmodule
