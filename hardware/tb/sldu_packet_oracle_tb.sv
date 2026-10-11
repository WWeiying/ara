// SPDX-License-Identifier: SHL-0.51
// Drive the real SLDU queues and spills; compare complete roots and FP tokens
// against Python integer expectations, with skew and independent backpressure.
module sldu_packet_oracle_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import ara_rce_pkg::*;
  localparam int NrLanes = 4;
  localparam int VLEN = 1024;
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef logic [9:0] vaddr_t;
  `include "ara/ara_typedef.svh"
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, req_valid = 0, req_ready;
  pe_req_t req;
  pe_resp_t resp;
  logic [NrVInsn-1:0] running = '0;
  elen_t [3:0] input_data, output_data;
  logic [3:0] input_valid = 0, input_ready, output_valid, grants = 0;
  vid_t [3:0] output_id;
  logic [287:0] partial [4], expected_root;
  logic [31:0] seed, expected_result;
  logic [4:0] expected_flags;
  int count [4], cursor [4];
  int fp16, rm, tests = 0;
  logic [63:0] held_output [4];
  logic [3:0] held = 0;
  logic [3:0] slide_valid, slide_final_grants;
  bit trailing_slide = 0, early_slide = 0;
  logic [3:0] early_received;
  int early_slide_consumed_cycles = 0;
  logic [3:0] trailing_sent;
  int trailing_frames = 0, trailing_wait_cycles = 0;
  function automatic logic [63:0] trailing_word(int lane);
    return 64'hace0123456780000 | (64'(tests) << 2) | 64'(lane);
  endfunction
  // Model the final VRF grant one cycle after a Slide write is accepted.
  always_ff @(posedge clk)
    slide_final_grants <= rst_n ? slide_valid & grants : '0;
  rce_exact_command_t exact_cmd;
  rce_exact_result_t exact_result;
  rce_exact_events_t exact_events;
  elen_t [3:0] exact_operand;
  logic [3:0] exact_operand_valid, exact_operand_ready;
  logic exact_cmd_valid, exact_cmd_ready, exact_seed_ready;
  logic [31:0] exact_seed_data;
  logic exact_local_complete, exact_result_valid, exact_result_ready;
  rce_result_t completion, held_completion;
  logic completion_valid, completion_ready = 0;
  bit completion_held = 0, completion_seen;
  int boundary_hold = 0, output_hold = 5;
  int direct_stall_cycles = 0, direct_results = 0;
  // Independently stall the RCE-to-adapter boundary, in addition to the
  // existing per-lane output grants. Both sides see the same handshake.
  logic exact_result_transfer_enable;
  int unsigned exact_result_wait_q;
  int unsigned exact_boundary_stall_cycles;
  int unsigned exact_raw_transfers = 0, exact_buffered_transfers = 0;
  if (RceExactEnable) begin : gen_exact_transfer_coverage
    always @(posedge clk) if (rst_n && exact_result_valid &&
        exact_result_ready && exact_result_transfer_enable) begin
      if (RceExactDecoupleEnable && rce.gen_exact.completed_valid_q)
        exact_buffered_transfers++;
      else exact_raw_transfers++;
    end
  end
  assign exact_result_transfer_enable = exact_result_wait_q >=
    (boundary_hold != 0 ? boundary_hold : tests % 8);
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      exact_result_wait_q <= 0;
      exact_boundary_stall_cycles <= 0;
    end else if (!exact_result_valid) exact_result_wait_q <= 0;
    else if (!exact_result_transfer_enable) begin
      exact_result_wait_q <= exact_result_wait_q + 1;
      exact_boundary_stall_cycles <= exact_boundary_stall_cycles + 1;
    end
  end

  logic root_complete;
  logic [287:0] observed_root;
  logic [3:0] exact_lane_consumed;
  reduction_completion_engine #(.EnableExact(RceExactEnable)) rce (
    .clk_i(clk), .rst_ni(rst_n), .cmd_i('0), .cmd_valid_i(1'b0), .cmd_ready_o(),
    .partial_i('0), .partial_valid_i('0), .partial_ready_o(),
    .seed_lifetime_i('0), .external_seed_i('0), .external_seed_valid_i('0), .ordinary_seed_i('0), .ordinary_seed_valid_i('0),
    .seed_i('0), .seed_valid_i(1'b0), .seed_ready_o(),
    .result_o(), .result_valid_o(), .result_ready_i(1'b0), .occupancy_o(),
    .exact_cmd_i(exact_cmd), .exact_cmd_valid_i(exact_cmd_valid),
    .exact_cmd_ready_o(exact_cmd_ready), .exact_operand_i(exact_operand),
    .exact_operand_valid_i(exact_operand_valid), .exact_operand_ready_o(exact_operand_ready),
    .exact_seed_ready_i(exact_seed_ready), .exact_seed_data_i(exact_seed_data),
    .exact_local_complete_o(exact_local_complete),
    .exact_lane_consumed_o(exact_lane_consumed), .exact_result_o(exact_result),
    .exact_result_valid_o(exact_result_valid),
    .exact_result_ready_i(exact_result_ready && exact_result_transfer_enable),
    .exact_events_o(exact_events)
  );
  if (RceExactEnable) begin : gen_rce_root_probe
    assign root_complete = exact_local_complete;
    assign observed_root = rce.gen_exact.exact_root_d;
  end else begin : gen_legacy_root_probe
    assign root_complete = dut.exact_limb_merge_fire &&
      dut.exact_packet_beat_q == dut.exact_limb_count_q;
    assign observed_root = dut.exact_root_d;
  end
  sldu #(.NrLanes(4), .VLEN(VLEN), .vaddr_t(vaddr_t),
         .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) dut (
    .rce_exact_cmd_o(exact_cmd), .rce_exact_cmd_valid_o(exact_cmd_valid),
    .rce_exact_cmd_ready_i(exact_cmd_ready), .rce_exact_operand_o(exact_operand),
    .rce_exact_operand_valid_o(exact_operand_valid), .rce_exact_operand_ready_i(exact_operand_ready),
    .rce_exact_seed_ready_o(exact_seed_ready), .rce_exact_seed_data_o(exact_seed_data),
    .rce_exact_local_complete_i(exact_local_complete),
    .rce_exact_lane_consumed_i(exact_lane_consumed), .rce_exact_result_i(exact_result),
    .rce_exact_result_valid_i(exact_result_valid && exact_result_transfer_enable),
    .rce_exact_result_ready_o(exact_result_ready),
    .rce_exact_events_i(exact_events),
    .rce_completion_o(completion), .rce_completion_valid_o(completion_valid),
    .rce_completion_ready_i(completion_ready),
    .clk_i(clk), .rst_ni(rst_n), .pe_req_i(req), .pe_req_valid_i(req_valid),
    .pe_vinsn_running_i(running), .pe_req_ready_o(req_ready), .pe_resp_o(resp),
    .sldu_operand_i(input_data), .sldu_operand_valid_i(input_valid),
    .sldu_operand_ready_o(input_ready), .sldu_result_req_o(slide_valid),
    .sldu_result_id_o(output_id), .sldu_result_addr_o(),
    .sldu_result_wdata_o(output_data), .sldu_result_be_o(),
    .sldu_result_gnt_i(grants), .sldu_result_final_gnt_i(slide_final_grants),
    .sldu_mux_sel_o(), .sldu_red_valid_o(output_valid),
    .mask_i('0), .mask_valid_i('0), .mask_ready_o()
  );

  function automatic logic [63:0] packet_word(int lane, int beat);
    logic [63:0] word;
    word = '0;
    if (beat < 0) return 64'h123456789abcdef0; // old dummy token before header
    if (beat == 0) begin
      word[63:32] = lane == 0 ? seed : 0;
      word[31:28] = 4'he;
      word[27:26] = 2'(lane);
      word[21] = 1'b1;
      word[20] = partial[lane] != 0;
      word[19] = partial[lane] == 0;
      word[17] = lane == 0;
      word[16:14] = 3'(rm);
      word[13:11] = 3'(count[lane]);
      word[10] = 1'(fp16);
      word[8] = partial[lane][287];
      word[7:0] = 8'(req.id);
    end else if (beat == 5)
      word = {{32{partial[lane][287]}}, partial[lane][287:256]};
    else word = 64'(partial[lane] >> (64*(beat-1)));
    return word;
  endfunction

  initial begin
    #100000000;
    $fatal(1, "FAIL: SLDU packet watchdog");
  end
  initial begin
    string path;
    int fd, scanned, random_seed, cycles, hold_cycles;
    logic [3:0] received, input_fire;
    logic root_checked, done;
    pe_req_t saved_exact_req;
    path = "";
    req = '0;
    input_data = '0;
    random_seed = 32'h71002026;
    void'($value$plusargs("SCHEDULE_SEED=%d", random_seed));
    void'($value$plusargs("BOUNDARY_HOLD=%d", boundary_hold));
    void'($value$plusargs("OUTPUT_HOLD=%d", output_hold));
    if (boundary_hold < 0 || boundary_hold > 256 || output_hold < 0 || output_hold > 256)
      $fatal(1, "FAIL: invalid exact hold interval");
    trailing_slide = $test$plusargs("TRAILING_SLIDE");
    early_slide = $test$plusargs("EARLY_SLIDE");
    if (early_slide && (!trailing_slide || !RceExactDecoupleEnable))
      $fatal(1, "FAIL: early Slide requires trailing data and decoupled completion");
    if (trailing_slide && (!RceExactEgressReleaseEnable || !RceExactDirectEnable || output_hold < 8))
      $fatal(1, "FAIL: trailing Slide requires early egress, direct results and OUTPUT_HOLD>=8");
    void'($urandom(random_seed));
    void'($value$plusargs("VECTOR_FILE=%s", path));
    fd = $fopen(path, "r");
    if (!fd) $fatal(1, "FAIL: missing SLDU oracle file");
    repeat (3) @(negedge clk);
    rst_n = 1;
    scanned = $fscanf(fd, "%d %d %h %h %h %h", fp16, rm, seed,
                      expected_root, expected_result, expected_flags);
    while (scanned == 6) begin
      for (int lane=0; lane<4; lane++) begin
        if ($fscanf(fd, "%h %d", partial[lane], count[lane]) != 2)
          $fatal(1, "FAIL: truncated SLDU input");
        cursor[lane] = (tests % 7 == lane) ? -1 : 0;
      end
      @(negedge clk);
      req = '0;
      req.id = vid_t'(tests % NrVInsn);
      req.op = VFREDUSUM;
      req.vfu = VFU_MFpu;
      req.vm = 1;
      req.vd = 8;
      req.use_vd = 1;
      req.vd_version = vreg_version_t'(tests + 1);
      req.vs1 = 2;
      req.vs2 = 16;
      req.vl = 256;
      req.vtype.vsew = fp16 ? EW16 : EW32;
      req.vtype.vlmul = LMUL_8;
      req_valid = 1;
      running[req.id] = 1;
      do @(posedge clk); while (!req_ready);
      @(negedge clk);
      req_valid = 0;
      if (early_slide) begin
        saved_exact_req = req;
        req = '0;
        req.id = vid_t'((tests+1)%NrVInsn);
        req.op = VSLIDEDOWN; req.vfu = VFU_SlideUnit;
        req.vm = 1; req.vl = 4; req.vtype.vsew = EW64; req.eew_vs2 = EW64;
        req.vtype.vlmul = LMUL_1; req.vs2 = 16; req.use_vs2 = 1;
        req.vd = 20; req.use_vd = 1; req.stride = 0;
        req_valid = 1; running[req.id] = 1;
        do @(posedge clk); while (!req_ready);
        @(negedge clk); req_valid = 0;
        req = saved_exact_req;
      end
      early_received = '0;
      received = '0;
      trailing_sent = '0;
      root_checked = 0;
      held = 0;
      completion_held = 0;
      completion_seen = 0;
      hold_cycles = 0;
      done = 0;
      cycles = 0;
      while (!done) begin
        for (int lane=0; lane<4; lane++) begin
          // Retain an unaccepted word verbatim; add bubbles only between words.
          if (!input_valid[lane] && cursor[lane] <= count[lane] && $urandom_range(0,3) != 0) begin
            input_valid[lane] = 1;
            input_data[lane] = packet_word(lane, cursor[lane]);
          end
          if (trailing_slide && !input_valid[lane] && cursor[lane] == count[lane]+1 &&
              !trailing_sent[lane]) begin
            input_valid[lane] = 1;
            input_data[lane] = trailing_word(lane);
          end
          grants[lane] = hold_cycles >= output_hold && $urandom_range(0,2) != 0;
        end
        completion_ready = hold_cycles >= output_hold && $urandom_range(0,2) != 0;
        @(posedge clk);
        input_fire = input_valid & input_ready;
        if (early_slide && !completion_seen && dut.state_q == dut.SLIDE_RUN &&
            (|dut.sldu_operand_ready)) early_slide_consumed_cycles++;
        for (int lane=0; lane<4; lane++) if (early_slide && slide_valid[lane] && grants[lane]) begin
          if (!completion_seen || early_received[lane] ||
              output_id[lane] != vid_t'((tests+1)%NrVInsn) ||
              output_data[lane] !== trailing_word(lane))
            $fatal(1,"FAIL: early Slide writeback data/order");
          early_received[lane] = 1;
        end
        if (|output_valid || completion_valid) hold_cycles++;
        if (RceExactDirectEnable) begin
          if (completion_held && (!completion_valid || completion !== held_completion))
            $fatal(1, "FAIL: exact direct completion changed under backpressure");
          completion_held = completion_valid && !completion_ready;
          held_completion = completion;
          if (completion_held) direct_stall_cycles++;
          if (completion_valid && completion_ready) begin
            if (completion_seen || completion !== rce_result_t'{
                id: req.id, vd: req.vd, version: req.vd_version,
                data: {32'b0,expected_result}, be: (fp16 ? 8'h03 : 8'h0f),
                fflags: expected_flags, write_enable: 1'b1, is_fp: 1'b1})
              $fatal(1, "FAIL: exact direct result/tag/byte-enable test=%0d", tests);
            completion_seen = 1;
            direct_results++;
          end
        end
        if (root_complete) begin
          if (observed_root !== expected_root)
            $fatal(1, "FAIL: root test=%0d got=%072x expected=%072x", tests, observed_root, expected_root);
          root_checked = 1;
        end
        for (int lane=0; lane<4; lane++) begin
          if (held[lane] && (!output_valid[lane] || output_data[lane] !== held_output[lane]))
            $fatal(1, "FAIL: output changed under backpressure");
          held[lane] = output_valid[lane] && !grants[lane];
          held_output[lane] = output_data[lane];
          if (output_valid[lane] && grants[lane]) begin
            if (received[lane] || output_id[lane] !== req.id ||
                output_data[lane] !== {8'hf7,19'b0,expected_flags,expected_result})
              $fatal(1, "FAIL: token test=%0d lane=%0d got=%016x expected=%02x/%08x", tests,lane,output_data[lane],expected_flags,expected_result);
            received[lane] = 1;
          end
          if (input_fire[lane]) begin
            if (trailing_slide && cursor[lane] == count[lane]+1)
              trailing_sent[lane] = 1;
            else cursor[lane]++;
          end
          if (trailing_slide && exact_lane_consumed[lane] && dut.sldu_operand_valid[lane] &&
              (!early_slide || dut.state_q == dut.SLIDE_RUN_EXACT)) begin
            if (dut.sldu_operand_ready[lane] ||
                dut.sldu_operand[lane] !== trailing_word(lane))
              $fatal(1, "FAIL: trailing Slide word consumed/corrupted by exact frame");
            trailing_wait_cycles++;
          end
        end
        done = resp.vinsn_done[req.id];
        if (++cycles > 1000) $fatal(1, "FAIL: SLDU test=%0d timeout",tests);
        @(negedge clk);
        input_valid &= ~input_fire;
      end
      if (!(RceExactDirectEnable ? completion_seen : &received) || !root_checked)
        $fatal(1,"FAIL: early retirement");
      for (int lane=0; lane<4; lane++)
        if (cursor[lane] != count[lane]+1) $fatal(1,"FAIL: unconsumed packet");
      input_valid = 0;
      if (trailing_slide) begin
        if (!(&trailing_sent)) $fatal(1,"FAIL: trailing words were not buffered");
        running[req.id] = 0;
        // No new data is supplied: the following Slide must consume exactly
        // the four words queued while the preceding reduction was live.
        req = '0;
        req.id = vid_t'((tests+1)%NrVInsn);
        req.op = VSLIDEDOWN; req.vfu = VFU_SlideUnit;
        req.vm = 1; req.vl = 4; req.vtype.vsew = EW64; req.eew_vs2 = EW64;
        req.vtype.vlmul = LMUL_1; req.vs2 = 16; req.use_vs2 = 1;
        req.vd = 20; req.use_vd = 1; req.stride = 0;
        if (!early_slide) begin
          req_valid = 1; running[req.id] = 1;
          do @(posedge clk); while (!req_ready);
          @(negedge clk); req_valid = 0;
        end
        received = early_received; done = 0; cycles = 0;
        while (!done) begin
          for (int lane=0; lane<4; lane++) grants[lane] = $urandom_range(0,2) != 0;
          @(posedge clk);
          for (int lane=0; lane<4; lane++) if (slide_valid[lane] && grants[lane]) begin
            if (received[lane] || output_data[lane] !== trailing_word(lane) || output_id[lane] != req.id)
              $fatal(1,"FAIL: trailing Slide data/owner mismatch lane=%0d got=%h expected=%h id=%0d expected_id=%0d",lane,output_data[lane],trailing_word(lane),output_id[lane],req.id);
            received[lane] = 1;
          end
          done = resp.vinsn_done[req.id];
          if (++cycles > 100) $fatal(1,"FAIL: trailing Slide timeout");
          @(negedge clk);
        end
        if (!(&received)) $fatal(1,"FAIL: trailing Slide retired early");
        trailing_frames++;
      end
      grants = 0;
      running = 0;
      repeat (3) @(negedge clk);
      tests++;
      scanned = $fscanf(fd, "%d %d %h %h %h %h", fp16, rm, seed,
                        expected_root, expected_result, expected_flags);
    end
    if (!$feof(fd) || tests == 0) $fatal(1,"FAIL: malformed SLDU oracle");
    $display("PASS: %0d SLDU packet cases, skew, stale tokens, output stalls, root and result",tests);
    if (RceExactEnable && tests >= 8 && exact_boundary_stall_cycles == 0)
      $fatal(1, "FAIL: exact completion boundary stalls were not exercised");
    $display("RCE exact boundary stalls: %0d", exact_boundary_stall_cycles);
    $display("EXACT_RESULT_PATH: raw=%0d buffered=%0d", exact_raw_transfers, exact_buffered_transfers);
    if ($test$plusargs("REQUIRE_EXACT_FALLTHROUGH") &&
        (!RceExactDecoupleEnable || exact_raw_transfers == 0))
      $fatal(1, "FAIL: exact result fallthrough was not exercised");
    if (RceExactDirectEnable && (direct_results != tests ||
        (output_hold > 0 && direct_stall_cycles < tests * output_hold)))
      $fatal(1, "FAIL: missing direct completion/backpressure coverage");
    $display("RCE exact direct results=%0d stalls=%0d", direct_results, direct_stall_cycles);
    if (trailing_slide && (trailing_frames != tests || trailing_wait_cycles == 0))
      $fatal(1,"FAIL: missing trailing-frame ownership coverage");
    $display("TRAILING_SLIDE: frames=%0d protected_lane_cycles=%0d",trailing_frames,trailing_wait_cycles);
    if (early_slide && early_slide_consumed_cycles == 0)
      $fatal(1,"FAIL: no Slide communication before exact completion");
    $display("EARLY_SLIDE: communication_cycles=%0d", early_slide_consumed_cycles);
    $finish;
  end
endmodule
