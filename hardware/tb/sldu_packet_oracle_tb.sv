// SPDX-License-Identifier: SHL-0.51
// Drive the real SLDU queues and spills; compare complete roots and FP tokens
// against Python integer expectations, with skew and independent backpressure.
module sldu_packet_oracle_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
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
  sldu #(.NrLanes(4), .VLEN(VLEN), .vaddr_t(vaddr_t),
         .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .pe_req_i(req), .pe_req_valid_i(req_valid),
    .pe_vinsn_running_i(running), .pe_req_ready_o(req_ready), .pe_resp_o(resp),
    .sldu_operand_i(input_data), .sldu_operand_valid_i(input_valid),
    .sldu_operand_ready_o(input_ready), .sldu_result_req_o(),
    .sldu_result_id_o(output_id), .sldu_result_addr_o(),
    .sldu_result_wdata_o(output_data), .sldu_result_be_o(),
    .sldu_result_gnt_i(grants), .sldu_result_final_gnt_i(4'b0),
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
    path = "";
    req = '0;
    input_data = '0;
    random_seed = 32'h71002026;
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
      received = '0;
      root_checked = 0;
      held = 0;
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
          grants[lane] = hold_cycles >= 5 && $urandom_range(0,2) != 0;
        end
        @(posedge clk);
        input_fire = input_valid & input_ready;
        if (|output_valid) hold_cycles++;
        if (dut.exact_limb_merge_fire && dut.exact_packet_beat_q == dut.exact_limb_count_q) begin
          if (dut.exact_root_d !== expected_root)
            $fatal(1, "FAIL: root test=%0d got=%072x expected=%072x", tests, dut.exact_root_d, expected_root);
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
          if (input_fire[lane]) cursor[lane]++;
        end
        done = resp.vinsn_done[req.id];
        if (++cycles > 1000) $fatal(1, "FAIL: SLDU test=%0d timeout",tests);
        @(negedge clk);
        input_valid &= ~input_fire;
      end
      if (!(&received) || !root_checked) $fatal(1,"FAIL: early retirement");
      for (int lane=0; lane<4; lane++)
        if (cursor[lane] != count[lane]+1) $fatal(1,"FAIL: unconsumed packet");
      input_valid = 0;
      grants = 0;
      running = 0;
      repeat (3) @(negedge clk);
      tests++;
      scanned = $fscanf(fd, "%d %d %h %h %h %h", fp16, rm, seed,
                        expected_root, expected_result, expected_flags);
    end
    if (!$feof(fd) || tests == 0) $fatal(1,"FAIL: malformed SLDU oracle");
    $display("PASS: %0d SLDU packet cases, skew, stale tokens, output stalls, root and result",tests);
    $finish;
  end
endmodule
