module qbs_vrf_seed_mapper_tb;
  import qbs_pkg::*;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  int cycles = 0, checks = 0, cases = 0;
  int current_m = 1, current_n = 1, current_mode = 0;
  logic [31:0] source_acc [128];
  logic [63:0] vrf [4][128];
  logic [31:0] expected [128];
  logic [127:0] expected_valid;
  int seed_words = 0, drained_words = 0;
  bit expect_discard = 0;
  logic check_stream = 0;

  logic commit_start = 0, commit_ready, commit_done, commit_busy;
  logic [3:0] commit_row;
  logic [31:0] commit_bank [8];
  logic [3:0] ldu_req, ldu_gnt, final_gnt;
  logic [3:0][2:0] ldu_ids;
  logic [3:0][6:0] ldu_addr;
  logic [63:0] ldu_data [4];
  logic [7:0] ldu_be [4];
  logic [31:0] commit_count;
  logic start = 0, start_ready, start_discard = 0, abort_seed = 0;
  logic [3:0] lane_valid = 0, lane_ready;
  logic [63:0] lane_data [4];
  logic seed_valid, seed_ready, seed_sink_ready, sink_enable = 1;
  logic [3:0] seed_row;
  logic [7:0] seed_mask;
  logic [31:0] seed_data [8];
  logic done, done_ready = 0, aborted, mapper_busy;
  logic clear = 0;
  logic [3:0] read_row = 0;
  logic [7:0] read_valid;
  logic [31:0] read_data [8];
  logic [4:0] flags;
  logic [31:0] updates;

  always_comb begin
    for (int b = 0; b < 8; b++) commit_bank[b] = source_acc[int'(commit_row)*8+b];
    for (int l = 0; l < 4; l++) begin
      ldu_gnt[l] = cycles % 5 != l && cycles % 7 != l;
      final_gnt[l] = ldu_gnt[l] && ldu_req[l];
    end
  end
  qbs_commit #(.vid_t(logic [2:0]), .vaddr_t(logic [6:0])) commit_dut (
    .clk_i(clk), .rst_ni(rst_n), .start_valid_i(commit_start), .start_ready_o(commit_ready),
    .start_id_i(3'd3), .start_vd_i(5'd8), .start_m_i(4'(current_m)), .start_n_i(6'(current_n)),
    .accumulator_bank_row_o(commit_row), .accumulator_bank_valid_i(8'hff),
    .accumulator_bank_data_i(commit_bank), .ldu_result_req_o(ldu_req), .ldu_result_id_o(ldu_ids),
    .ldu_result_addr_o(ldu_addr), .ldu_result_wdata_o(ldu_data), .ldu_result_be_o(ldu_be),
    .ldu_result_gnt_i(ldu_gnt), .ldu_result_final_gnt_i(final_gnt),
    .done_valid_o(commit_done), .done_ready_i(1'b1), .busy_o(commit_busy),
    .commit_word_count_o(commit_count), .commit_backpressure_cycles_o()
  );
  qbs_vrf_seed_mapper mapper_dut (
    .clk_i(clk), .rst_ni(rst_n), .start_valid_i(start), .start_ready_o(start_ready),
    .start_m_i(4'(current_m)), .start_n_i(6'(current_n)), .start_discard_i(start_discard),
    .abort_i(abort_seed), .lane_valid_i(lane_valid), .lane_ready_o(lane_ready), .lane_data_i(lane_data),
    .seed_valid_o(seed_valid), .seed_ready_i(seed_ready), .seed_row_o(seed_row),
    .seed_mask_o(seed_mask), .seed_data_o(seed_data), .done_valid_o(done),
    .done_ready_i(done_ready), .done_aborted_o(aborted), .busy_o(mapper_busy)
  );
  assign seed_ready = seed_sink_ready && sink_enable;
  qbs_fp_accumulator_seeded accumulator_dut (
    .clk_i(clk), .rst_ni(rst_n), .clear_i(clear),
    .request_valid_i(1'b0), .request_ready_o(), .request_slot_i('0),
    .request_profile_i(QBS_WEIGHT_PROFILE_Q8_0_WEIGHT),
    .request_activation_profile_i(QBS_ACTIVATION_PROFILE_Q8_0),
    .request_accumulator_index_i('0), .request_first_block_i(1'b0),
    .request_dot_i('0), .request_aux_i('0), .request_weight_d_i('0),
    .request_weight_dmin_i('0), .request_activation_d_i('0),
    .read_index_i('0), .read_valid_o(), .read_data_o(),
    .bank_read_row_i(read_row), .bank_read_valid_o(read_valid), .bank_read_data_o(read_data),
    .raw_seed_valid_i(seed_valid && sink_enable), .raw_seed_ready_o(seed_sink_ready),
    .raw_seed_row_i(seed_row), .raw_seed_mask_i(seed_mask), .raw_seed_data_i(seed_data),
    .update_valid_o(), .update_index_o(), .update_data_o(), .fflags_o(flags),
    .busy_o(), .fp_uop_issue_o(), .table_occupancy_sum_o(), .table_occupancy_max_o(),
    .table_full_cycles_o(), .accumulator_updates_o(updates)
  );

  always @(posedge clk) begin : scoreboard
    int row, word_index, acc_index, col;
    logic [7:0] mask;
    cycles++;
    if (cycles > 200000) $fatal(1, "VRF seed roundtrip watchdog");
    if (rst_n) begin
      for (int l = 0; l < 4; l++)
        if (ldu_req[l] && ldu_gnt[l]) begin
          assert (ldu_ids[l] === 3'd3) else $fatal(1, "Commit VID drift");
          for (int b = 0; b < 8; b++)
            if (ldu_be[l][b]) vrf[l][ldu_addr[l]][8*b+:8] <= ldu_data[l][8*b+:8];
        end
      if (check_stream) begin
        row = drained_words / 4;
        word_index = drained_words % 4;
        mask = 0;
        for (int b = 0; b < 8; b++)
          if (word_index*8+b < current_n) mask[b] = 1;
        if (abort_seed) expect_discard = 1;
        if (seed_valid) begin
          assert (!expect_discard && |mask && &lane_valid)
            else $fatal(1, "Invalid seed valid mode=%0d", current_mode);
          assert (seed_row === 4'(row*(current_m>4 ? 2:4)+word_index) && seed_mask === mask)
            else $fatal(1, "Seed addressing m=%0d n=%0d word=%0d", current_m,current_n,drained_words);
          for (int b = 0; b < 8; b++) if (mask[b]) begin
            acc_index = row*(current_m>4 ? 16:32)+word_index*8+b;
            assert (seed_data[b] === source_acc[acc_index])
              else $fatal(1, "EW32 inverse mapping m=%0d n=%0d element=%0d",current_m,current_n,acc_index);
            checks++;
            if (seed_ready) begin
              expected[acc_index] = source_acc[acc_index];
              expected_valid[acc_index] = 1;
            end
          end
        end
        if (seed_valid && seed_ready) seed_words++;
        if (|lane_ready) begin
          assert (&lane_ready && &lane_valid &&
                  (expect_discard || !(|mask) || (seed_valid && seed_ready)))
            else $fatal(1, "Partial or premature source consumption");
          drained_words++;
        end
        if (done) assert (drained_words == current_m*4)
          else $fatal(1, "Done before owned VRF stream drained");
      end
    end
  end

  task automatic prepare;
    @(negedge clk); clear = 1;
    expected_valid = 0;
    for (int i = 0; i < 128; i++) begin
      source_acc[i] = 32'h7f800001 ^ (32'(cases)*32'h00102101) ^ (32'(i)*32'h9e3779b9);
      expected[i] = 0;
      for (int l = 0; l < 4; l++) vrf[l][i] = 64'hbad0feeddeadbeef ^ 64'(i*4+l);
    end
    @(negedge clk); clear = 0;
    assert (commit_ready && start_ready) else $fatal(1, "Previous owner not retired");
    commit_start = 1;
    @(negedge clk); commit_start = 0;
    while (!commit_done) @(negedge clk);
    // Validate actual writes and preserved tails independently of seed mapper.
    for (int r = 0; r < current_m; r++)
      for (int c = 0; c < 32; c++) begin
        int addr, lane;
        logic [31:0] got, want;
        addr = (8+r)*4+c/8; lane = c%4;
        got = c%8 < 4 ? vrf[lane][addr][31:0] : vrf[lane][addr][63:32];
        if (c < current_n) want = source_acc[r*(current_m>4 ? 16:32)+c];
        else if (current_m <= 4) want = 0;
        else begin
          logic [63:0] old;
          old = 64'hbad0feeddeadbeef ^ 64'(addr*4+lane);
          want = c%8 < 4 ? old[31:0] : old[63:32];
        end
        assert (got === want) else $fatal(1, "Commit data/tail changed m=%0d n=%0d row=%0d c=%0d",current_m,current_n,r,c);
        checks++;
      end
    @(negedge clk);
  endtask

  task automatic stream(input bit reset_midway = 0);
    int beat, phase, expected_seed_words;
    bit abort_sent;
    logic [3:0] present;
    seed_words = 0; drained_words = 0; expect_discard = current_mode == 2;
    abort_sent = 0; check_stream = 1; beat = 0; phase = 0; present = 0;
    start_discard = current_mode == 2;
    start = 1;
    @(negedge clk); start = 0; start_discard = 0;
    while (beat < current_m*4) begin
      sink_enable = current_mode == 4 && !abort_sent ? 0 : cycles%4 != 0;
      if (current_mode == 0) sink_enable = 1;
      if ((current_mode == 3 && beat >= 3 || current_mode == 4 && phase >= 5) && !abort_sent) begin
        abort_seed = 1; abort_sent = 1;
      end else abort_seed = 0;
      if (current_mode == 0) present = 4'hf;
      else for (int l = 0; l < 4; l++)
        if (phase >= l) present[l] = 1;
      lane_valid = present;
      for (int l = 0; l < 4; l++) lane_data[l] = vrf[l][32+beat];
      #1;
      if (reset_midway && beat == 1 && phase == 2) begin
        // Reset requires the external source queues to be flushed as well.
        rst_n = 0; lane_valid = 0; check_stream = 0; abort_seed = 0;
        repeat (2) @(negedge clk);
        rst_n = 1;
        #1; assert (start_ready && !done && !seed_valid && !mapper_busy)
          else $fatal(1, "Reset left a seed owner");
        return;
      end
      @(posedge clk);
      if (&lane_ready) begin beat++; phase = 0; present = 0; end
      else phase++;
      @(negedge clk);
    end
    lane_valid = 0; abort_seed = 0; sink_enable = 1;
    assert (done && aborted === expect_discard && drained_words == current_m*4)
      else $fatal(1, "Terminal status does not match drained stream");
    if (current_mode <= 1) begin
      expected_seed_words = current_m*((current_n+7)/8);
      assert (seed_words == expected_seed_words) else $fatal(1, "Missing active seed word");
    end
    if (current_mode == 2 || current_mode == 4)
      assert (seed_words == 0) else $fatal(1, "Aborted stream modified accumulator");
    repeat (3) begin
      assert (done && !start_ready && lane_ready == 0 && !seed_valid)
        else $fatal(1, "Done handshake did not retain ownership");
      @(negedge clk);
    end
    for (int r = 0; r < 16; r++) begin
      read_row = 4'(r); #1;
      assert (read_valid === expected_valid[r*8+:8]) else $fatal(1, "Seed validity drift");
      for (int b = 0; b < 8; b++) if (expected_valid[r*8+b]) begin
        assert (read_data[b] === expected[r*8+b]) else $fatal(1, "Restored accumulator bit drift");
        checks++;
      end
    end
    assert (flags === 0 && updates === 0) else $fatal(1, "Raw restore executed FP arithmetic");
    @(negedge clk); check_stream = 0; done_ready = 1;
    @(negedge clk); done_ready = 0;
    assert (start_ready && !mapper_busy) else $fatal(1, "Seed owner not released");
  endtask

  initial begin
    repeat (3) @(negedge clk); rst_n = 1;
    for (int m = 1; m <= 8; m++)
      for (int n = 1; n <= (m>4 ? 16:32); n++)
        for (int mode = 0; mode < 5; mode++) begin
          current_m = m; current_n = n; current_mode = mode;
          prepare(); stream(); cases++;
        end
    current_m = 8; current_n = 15; current_mode = 1;
    prepare(); stream(1);
    prepare(); stream(); cases++;
    assert (cases == 961 && checks > 100000) else $fatal(1, "Incomplete shape matrix");
    $display("QBS_VRF_SEED_PASS cases=%0d checks=%0d reset_flush=1", cases, checks);
    $finish;
  end
endmodule
