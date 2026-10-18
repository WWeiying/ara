// SPDX-License-Identifier: SHL-0.51
// Two concurrent contexts, independently skewed lane arrivals, delayed/wrong
// seed versions, ID wraparound, and output backpressure. Expected values come
// from a Python scalar model, never from the RTL merge implementation.
module reduction_completion_engine_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import ara_rce_pkg::*;
  localparam int MaxTests = 20000;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  rce_command_t cmd;
  logic cmd_valid = 0, cmd_ready;
  rce_partial_t [3:0] partial;
  logic [3:0] partial_valid = '0, partial_ready;
  rce_seed_t seed;
  logic seed_valid = 0, seed_ready;
  rce_result_t result;
  logic result_valid, result_ready = 0;
  logic [1:0] occupancy;
  rce_command_t commands [MaxTests];
  rce_partial_t [3:0] inputs [MaxTests];
  rce_result_t expected [MaxTests];
  logic [3:0] sent [MaxTests];
  bit seed_sent [MaxTests];
  bit [2:0] wrong_seed_probed [MaxTests];
  bit wrong_seed_broadcast = 0;
  int wrong_seed_kind;
  int bad_seed_counts [3] = '{default:0};
  int hold_cycles = 0, hold_left = 0, last_hold_case = -1;
  int consecutive_stalls = 0, max_consecutive_stalls = 0;
  int command_stalls = 0;
  int full_refills = 0, ready_successors = 0;
  int fp_sparse_jumps = 0;
  int fp_sparse_feedback_jumps = 0;
  int fp_feedback_fires = 0;
  int fp_seed_feedback_fires = 0;
  int sparse_lane_jumps = 0;
  int sparse_empty_tails = 0;
  int seed_lookahead_completions = 0;
  int empty_results = 0, empty_arithmetic_cycles = 0, empty_seed_wait_cycles = 0;
  bit stress_seed_tuple, result_was_stalled = 0;
  rce_result_t stalled_result;
  int admitted = 0, completed = 0, total = 0, cycles = 0;
  int partial_owner [4];
  int seed_owner;
  int overlap_cycles = 0, partial_stalls = 0, result_stalls = 0, wrong_seeds = 0;
  ara_op_e ops [14] = '{VREDSUM,VREDAND,VREDOR,VREDXOR,VREDMINU,VREDMIN,
    VREDMAXU,VREDMAX,VWREDSUMU,VWREDSUM,VFREDMIN,VFREDMAX,VFREDUSUM,VFWREDUSUM};
`ifdef ARA_RED_TEST_SHARED_COMPLETION
  ordered_add_request_t [4:0] add_request;
  ordered_add_response_t [4:0] add_response;
  logic [4:0] add_valid,add_ready,add_out_valid,add_out_ready;
  logic [3:0] synthetic_accepted;
  int shared_blocked=0,shared_contended=0;
  shared_ordered_adder #(.NrClients(5),.NrUnits(1)) shared_add (
    .clk_i(clk),.rst_ni(rst_n),.request_i(add_request),.valid_i(add_valid),.ready_o(add_ready),
    .response_o(add_response),.response_valid_o(add_out_valid),.response_ready_i(add_out_ready));
  always @(posedge clk) begin
    synthetic_accepted=add_valid[3:0]&add_ready[3:0];
    if (rst_n) begin
      if (add_valid[4]&&!add_ready[4]) shared_blocked++;
      if (add_valid[4]&&(|add_valid[3:0])) shared_contended++;
    end
  end
  // Stable requests from four unrelated clients force arbitration while the
  // RCE model independently checks seed ownership, flags and partial results.
  always @(negedge clk) for (int client=0;client<4;client++) begin
    if (!rst_n) begin add_valid[client]=0;add_request[client]='0;add_out_ready[client]=0;end
    else begin
      add_out_ready[client]=!(client==1&&cycles%128<24);
      if (!add_valid[client]||synthetic_accepted[client]) begin
        // Alternate pressure and quiet intervals. Drain a held request before
        // withdrawing valid, allowing both blocked and accepted RCE feedback.
        add_valid[client]=cycles%256<128;
        add_request[client]='{operands:{64'h3ff0000000000000,64'h3ff0000000000000,64'h3ff0000000000000},
          rm:fpnew_pkg::RNE,src_fmt:fpnew_pkg::FP64,dst_fmt:fpnew_pkg::FP64,
          int_fmt:fpnew_pkg::INT64,tag:9'(cycles+client),mask:1'b1};
      end
    end
  end
`endif
  reduction_completion_engine #(.EnableExact(1'b0)
`ifdef ARA_RED_TEST_SHARED_COMPLETION
    ,.UseSharedFp64Add(1'b1)
`endif
  ) dut (
`ifdef ARA_RED_TEST_SHARED_COMPLETION
    .shared_add_request_o(add_request[4]),.shared_add_valid_o(add_valid[4]),.shared_add_ready_i(add_ready[4]),
    .shared_add_response_i(add_response[4]),.shared_add_response_valid_i(add_out_valid[4]),
    .shared_add_response_ready_o(add_out_ready[4]),
`endif
    .clk_i(clk), .rst_ni(rst_n), .cmd_i(cmd), .cmd_valid_i(cmd_valid),
    .cmd_ready_o(cmd_ready), .partial_i(partial), .partial_valid_i(partial_valid),
    .partial_ready_o(partial_ready), .seed_lifetime_i('0), .external_seed_i('0), .external_seed_valid_i('0), .ordinary_seed_i('0), .ordinary_seed_valid_i('0),
    .seed_i(seed), .seed_valid_i(seed_valid),
    .seed_ready_o(seed_ready), .result_o(result), .result_valid_o(result_valid),
    .result_ready_i(result_ready), .occupancy_o(occupancy),
    .exact_cmd_i('0), .exact_cmd_valid_i(1'b0), .exact_cmd_ready_o(),
    .exact_operand_i('0), .exact_operand_valid_i('0), .exact_operand_ready_o(),
    .exact_seed_ready_i(1'b0), .exact_seed_data_i('0), .exact_local_complete_o(),
    .exact_result_o(), .exact_result_valid_o(), .exact_result_ready_i(1'b0),
    .exact_events_o()
  );
  initial begin
    string path;
    int fd, op, eew, mode, zero_vl, active, scanned, random_seed;
    logic [63:0] scalar_seed, data, answer;
    logic [4:0] flags, answer_flags;
    path = "";
    void'($value$plusargs("VECTOR_FILE=%s", path));
    fd = $fopen(path, "r");
    if (!fd) $fatal(1, "FAIL: RCE vector file missing");
    scanned = $fscanf(fd, "%d %d %d %d %h %h %h %h", op, eew, mode, zero_vl,
                      scalar_seed, active, answer, answer_flags);
    while (scanned == 8) begin
      if (total == MaxTests) $fatal(1, "FAIL: too many RCE vectors");
      commands[total] = '{id: vid_t'(total % NrVInsn), op: ops[op & 255], fp_rm: fpnew_pkg::roundmode_e'(op >> 8), eew: vew_e'(eew),
        vd: 5'(total % 32), vd_version: vreg_version_t'(total / 8), vl_zero: 1'(zero_vl),
        seed_mode: rce_seed_mode_e'(mode), seed: scalar_seed,
        seed_producer: vid_t'((total + 7) % NrVInsn), seed_register: 5'((total+1)%32),
        seed_version: vreg_version_t'(total / 3)};
      expected[total] = '{id: commands[total].id, vd: commands[total].vd,
        version: commands[total].vd_version, data: answer,
        be: zero_vl ? 8'b0 : 8'((9'd1 << (1 << eew)) - 1), fflags: answer_flags,
        write_enable: !zero_vl, is_fp: op >= 10};
      sent[total] = zero_vl ? '1 : '0;
      seed_sent[total] = mode != 2 || zero_vl;
      for (int lane = 0; lane < 4; lane++) begin
        scanned = $fscanf(fd, "%h %h", data, flags);
        if (scanned != 2) $fatal(1, "FAIL: malformed partial");
        inputs[total][lane] = '{id: commands[total].id, data: data,
          source_active: 1'((active >> lane) & 1), fflags: flags,
          seed_valid: lane == 0 && mode != 2, seed: scalar_seed};
      end
      total++;
      scanned = $fscanf(fd, "%d %d %d %d %h %h %h %h", op, eew, mode, zero_vl,
                        scalar_seed, active, answer, answer_flags);
    end
    $fclose(fd);
    if (total < 1) $fatal(1, "FAIL: no RCE cases");
    random_seed = 32'h52434526;
    void'($value$plusargs("SCHEDULE_SEED=%d", random_seed));
    void'($value$plusargs("HOLD_CYCLES=%d", hold_cycles));
    if (hold_cycles < 0 || hold_cycles > 1024)
      $fatal(1, "FAIL: invalid HOLD_CYCLES");
    stress_seed_tuple = $test$plusargs("STRESS_SEED_TUPLE");
    void'($urandom(random_seed));
    cmd = '0; partial = '0; seed = '0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    while (completed < total && cycles < total * 200) begin
      @(negedge clk);
      // Keep commands and partials stable while stalled; independently choose a live
      // context for each lane, deliberately delivering younger partials first.
      if (!cmd_valid && admitted < total && $urandom_range(0,3) != 0) begin
        cmd = commands[admitted];
        // Exercise both late binding and the lane-zero eager-seed transfer.
        if (!cmd.vl_zero) cmd.seed = 64'hdeadbeef;
        cmd_valid = 1;
      end
      for (int lane = 0; lane < 4; lane++) begin
        if (!partial_valid[lane]) begin
          for (int n = admitted-1; n >= completed; n--) begin
            if (!sent[n][lane] && !partial_valid[lane] && $urandom_range(0,3) == 0) begin
              partial[lane] = inputs[n][lane];
              partial_valid[lane] = 1;
              partial_owner[lane] = n;
            end
          end
        end
      end
      if (!seed_valid) begin
        for (int n = completed; n < admitted; n++) begin
          if (!seed_sent[n] && !seed_valid && $urandom_range(0,7) == 0) begin
            seed = '{producer: commands[n].seed_producer, vd: commands[n].seed_register,
                     version: commands[n].seed_version, data: commands[n].seed};
            seed_owner = n;
            seed_valid = 1;
            // An unrelated completion broadcast must not bind this seed.
            // Probe a stale version once, then publish the real producer.
            wrong_seed_broadcast = stress_seed_tuple ?
              wrong_seed_probed[n] != 3'b111 : !wrong_seed_probed[n][0];
            if (wrong_seed_broadcast) begin
              wrong_seed_kind = !wrong_seed_probed[n][0] ? 0 :
                                !wrong_seed_probed[n][1] ? 1 : 2;
              case (wrong_seed_kind)
                0: seed.version ^= vreg_version_t'(8'h80);
                1: seed.producer ^= vid_t'(1);
                2: seed.vd ^= 5'd1;
              endcase
            end
          end
        end
      end
      result_ready = $urandom_range(0,3) == 0;
      // Start a deterministic long stall only after a result is available.
      // New commands/partials/seeds continue attempting handshakes meanwhile.
      if (hold_cycles != 0 && result_valid && completed % 37 == 0 &&
          last_hold_case != completed) begin
        hold_left = hold_cycles;
        last_hold_case = completed;
      end
      if (hold_left != 0) begin
        result_ready = 0;
        hold_left--;
      end
      @(posedge clk);
      if (result_was_stalled && (!result_valid || result !== stalled_result))
        $fatal(1, "FAIL: result ownership/data changed during backpressure");
      result_was_stalled = result_valid && !result_ready;
      stalled_result = result;
      consecutive_stalls = result_was_stalled ? consecutive_stalls + 1 : 0;
      if (consecutive_stalls > max_consecutive_stalls)
        max_consecutive_stalls = consecutive_stalls;
      if (dut.valid_q[dut.work_ptr] && (&dut.received_q[dut.work_ptr]) &&
          !dut.command_q[dut.work_ptr].vl_zero && !(|dut.active_q[dut.work_ptr])) begin
        if (dut.state_q == dut.MERGE || dut.state_q == dut.FOLD) begin
          empty_arithmetic_cycles++;
          if (RceEmptyBypassEnable)
            $fatal(1, "FAIL: inactive source entered arithmetic with bypass enabled");
        end
        if (dut.state_q == dut.SEED && !dut.seed_ready_q[dut.work_ptr])
          empty_seed_wait_cycles++;
      end
      if (result_valid && result_ready && !dut.command_q[dut.read_q].vl_zero &&
          !(|dut.active_q[dut.read_q])) empty_results++;
      if (dut.background_q && dut.state_q == dut.HOLD) seed_lookahead_completions++;
      if (dut.fp_feedback_request && dut.fp_in_ready) begin
        fp_feedback_fires++;
        if (int'(dut.fp_next_lane) > int'(dut.lane_q)+1) fp_sparse_feedback_jumps++;
      end
      if (dut.sparse_fp && dut.state_q == dut.MERGE && dut.fp_in_valid && dut.fp_in_ready &&
          dut.merge_lane != dut.lane_q) fp_sparse_jumps++;
      if (dut.fp_seed_feedback_request && dut.fp_in_ready) fp_seed_feedback_fires++;
      if (dut.state_q == dut.MERGE && dut.sparse_integer) begin
        if (dut.merge_lane_found && dut.merge_lane != dut.lane_q) sparse_lane_jumps++;
        if (!dut.merge_lane_found) sparse_empty_tails++;
      end
      if (cmd_valid && !cmd_ready) command_stalls++;
      if (occupancy == 2) overlap_cycles++;
      if (occupancy == 2 && result_valid && result_ready) begin
        if (cmd_valid && cmd_ready) full_refills++;
        if ((&dut.received_q[dut.next_ptr(dut.read_q)]) &&
            !dut.command_q[dut.next_ptr(dut.read_q)].vl_zero) ready_successors++;
      end
      if (result_valid && !result_ready) result_stalls++;
      for (int lane = 0; lane < 4; lane++)
        if (partial_valid[lane] && !partial_ready[lane]) partial_stalls++;
      if (cmd_valid && cmd_ready) begin admitted++; cmd_valid <= 0; end
      for (int lane = 0; lane < 4; lane++)
        if (partial_valid[lane] && partial_ready[lane]) begin
          sent[partial_owner[lane]][lane] = 1;
          partial_valid[lane] <= 0;
        end
      if (seed_valid && wrong_seed_broadcast) begin
        if (seed_ready) $fatal(1, "FAIL: RCE accepted mismatched seed tuple kind=%0d", wrong_seed_kind);
        wrong_seed_probed[seed_owner][wrong_seed_kind] = 1;
        bad_seed_counts[wrong_seed_kind]++;
        wrong_seeds++;
        seed_valid <= 0;
        wrong_seed_broadcast = 0;
      end else if (seed_valid && seed_ready) begin
        seed_sent[seed_owner] = 1;
        seed_valid <= 0;
      end
      if (result_valid && result_ready) begin
        if (result !== expected[completed]) begin
          $display("case=%0d op=%s eew=%0d seedmode=%0d seed=%h", completed,
            commands[completed].op.name(), commands[completed].eew,
            commands[completed].seed_mode, commands[completed].seed);
          $display("got=%h flags=%h be=%h expected=%h flags=%h be=%h", result.data,
            result.fflags, result.be, expected[completed].data,
            expected[completed].fflags, expected[completed].be);
          $fatal(1, "FAIL: RCE result mismatch");
        end
        completed++;
      end
      cycles++;
    end
    if (completed != total) $fatal(1, "FAIL: RCE watchdog %0d/%0d", completed, total);
    if (overlap_cycles == 0 || result_stalls == 0 || wrong_seeds == 0)
      $fatal(1, "FAIL: missing protocol coverage");
    if (hold_cycles != 0 && (max_consecutive_stalls < hold_cycles || command_stalls == 0))
      $fatal(1, "FAIL: missing long-backpressure coverage");
    if (stress_seed_tuple && (bad_seed_counts[0] == 0 ||
        bad_seed_counts[1] == 0 || bad_seed_counts[2] == 0))
      $fatal(1, "FAIL: missing bad seed ID/register/version coverage");
    if (RceWordTurnaroundEnable && (full_refills == 0 || ready_successors == 0))
      $fatal(1, "FAIL: missing full-refill or ready-successor coverage");
    if (empty_results == 0 || empty_seed_wait_cycles == 0)
      $fatal(1, "FAIL: missing empty-source completion or late-seed wait coverage");
    $display("FP_SPARSE: merge_jumps=%0d feedback_jumps=%0d", fp_sparse_jumps, fp_sparse_feedback_jumps);
    $display("FP_FEEDBACK: fires=%0d", fp_feedback_fires);
    $display("FP_SEED_FEEDBACK: fires=%0d", fp_seed_feedback_fires);
    $display("WORD_SPARSE: jumps=%0d empty_tails=%0d", sparse_lane_jumps, sparse_empty_tails);
    if ($test$plusargs("REQUIRE_FP_SEED_FEEDBACK") && fp_seed_feedback_fires == 0)
      $fatal(1, "FP64 seed feedback was not exercised");
    $display("SEED_LOOKAHEAD: completions=%0d", seed_lookahead_completions);
    $display("EMPTY: results=%0d arithmetic_cycles=%0d seed_wait_cycles=%0d",
      empty_results, empty_arithmetic_cycles, empty_seed_wait_cycles);
    $display("TURNAROUND: full_refills=%0d ready_successors=%0d", full_refills, ready_successors);
    $display("PROTOCOL: command_stalls=%0d max_result_stall=%0d bad_version=%0d bad_id=%0d bad_register=%0d",
      command_stalls, max_consecutive_stalls, bad_seed_counts[0], bad_seed_counts[1], bad_seed_counts[2]);
`ifdef ARA_RED_TEST_SHARED_COMPLETION
    if (shared_blocked==0||shared_contended==0) $fatal(1,"shared RCE arbitration not exercised");
    if (RceFp64FeedbackEnable&&fp_feedback_fires==0)
      $fatal(1,"shared RCE accepted feedback was not exercised");
    if (RceFp64SeedFeedbackEnable&&fp_seed_feedback_fires==0)
      $fatal(1,"shared RCE accepted seed feedback was not exercised");
    $display("SHARED_RCE_CONTENTION blocked=%0d contended=%0d",shared_blocked,shared_contended);
`endif
    $display("PASS: %0d RCE word cases; cycles=%0d two_context_cycles=%0d result_stalls=%0d wrong_seed_versions=%0d",
      completed, cycles, overlap_cycles, result_stalls, wrong_seeds);
    $finish;
  end
endmodule
