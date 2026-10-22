// Focused liveness test of the real FPGA MASKU -> SLDU interface.
module mask_slide_restart_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst, valid, mr, sr, mask_ready;
  pe_req_t req;
  pe_resp_t mresp, sresp;
  logic [3:0][7:0] mask;
  logic [3:0] mv, sv, opready, final_grant;
  logic [3:0][NrMaskFUnits+1:0] operand_valid;
  vfu_e target;
  integer start, sew, down, beats, cycles;
  bit done;
  integer prefix_errors, written_bytes;
  // Independent inverse of the four-lane, bit-reversed subword VRF layout.
  function automatic int sequential_byte(int lane, int byte_in_lane, int ew);
    int slot, reversed;
    slot = byte_in_lane >> ew;
    reversed = 0;
    for (int bitidx = 0; bitidx < 3-ew; bitidx++)
      reversed = (reversed << 1) | ((slot >> bitidx) & 1);
    return ((reversed * 4 + lane) << ew) + (byte_in_lane & ((1 << ew)-1));
  endfunction
  masku #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic[9:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) m (
    .clk_i(clk), .rst_ni(rst), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('1), .pe_req_ready_o(mr), .pe_resp_o(mresp),
    .masku_operand_i('1), .masku_operand_valid_i(operand_valid),
    .masku_result_gnt_i('1), .masku_result_final_gnt_i('1),
    .masku_vrgat_req_ready_i('1), .mask_o(mask), .mask_valid_o(mv),
    .mask_target_fu_o(target), .lane_mask_ready_i('0),
    .vldu_mask_ready_i(1'b0), .vstu_mask_ready_i(1'b0),
    .sldu_mask_ready_i(mask_ready));
  sldu #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic[9:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) s (
    .clk_i(clk), .rst_ni(rst), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('1), .pe_req_ready_o(sr), .pe_resp_o(sresp),
    .maintenance_drain_i(1'b0), .sldu_operand_i('0),
    .sldu_operand_valid_i(4'b1111), .sldu_operand_reduction_i('0),
    .sldu_operand_ready_o(opready), .sldu_result_req_o(sv),
    .sldu_result_gnt_i(sv), .sldu_result_final_gnt_i(final_grant),
    .mask_i(mask), .mask_valid_i(target == VFU_SlideUnit ? mv : 4'b0),
    .mask_ready_o(mask_ready));
  // Normal grant transfers into the lane stream register; final grant follows.
  always @(posedge clk) final_grant <= rst ? sv : '0;
  always @(posedge clk) if (rst) begin
    if (mask_ready && |mv) beats = beats + 1;
    if (sresp.vinsn_done[3]) done = 1;
    for (int lane = 0; lane < 4; lane++) begin
      if (sv[lane]) begin
        for (int b = 0; b < 8; b++) begin
          if (s.sldu_result_be_o[lane][b]) begin
            automatic int index;
            index = (int'(s.sldu_result_addr_o[lane]) - 24*4)*32 +
                    sequential_byte(lane, b, sew);
            written_bytes++;
            if (index < (start << sew)) begin
              prefix_errors++;
              $display("PREFIX_WRITE index=%0d vstart_bytes=%0d", index, start << sew);
            end
          end
        end
      end
    end
  end
  initial begin
    start = 8; sew = 2; down = 0;
    void'($value$plusargs("START=%d", start));
    void'($value$plusargs("SEW=%d", sew));
    void'($value$plusargs("DOWN=%d", down));
    rst = 0; valid = 0; req = '0; operand_valid = '0;
    beats = 0; done = 0; prefix_errors = 0; written_bytes = 0;
    repeat (5) @(negedge clk);
    rst = 1;
    req.id = 3; req.op = down ? VSLIDEDOWN : VSLIDEUP;
    req.vfu = VFU_SlideUnit; req.vm = 0; req.vd = 24; req.use_vd = 1;
    req.vs2 = 8; req.use_vs2 = 1; req.vl = 64 >> sew;
    req.vstart = start; req.stride = down ? 0 : 1;
    req.use_scalar_op = !down; req.vtype.vsew = vew_e'(sew);
    req.eew_vs2 = vew_e'(sew); req.eew_vmask = EW8;
    req.vtype.vlmul = LMUL_1; req.emul = LMUL_1;
    @(negedge clk); valid = 1;
    @(negedge clk); valid = 0;
    for (int lane=0; lane<4; lane++) operand_valid[lane][0] = 1;
    repeat (100) @(negedge clk);
    $display("RESULT sew=%0d down=%0d vstart=%0d vl=%0d done=%0b mask_beats=%0d mask_read=%0d mask_queue=%0d slide_issue=%0d slide_commit=%0d slide_state=%0d slide_mask_valid=%b operand_valid=%b result_full=%b",
      sew, down, start, req.vl, done, beats, m.read_cnt_q, m.mask_queue_cnt_q,
      s.issue_cnt_q, s.commit_cnt_q, s.state_q, s.mask_valid_q,
      s.sldu_operand_valid, s.result_queue_full);
    if (start == 0 || !$test$plusargs("EXPECT_STARVATION")) begin
      assert(done && beats == 2) else $fatal(1, "Control did not complete");
      assert(prefix_errors == 0 && written_bytes == (64 - (start << sew)))
        else $fatal(1, "Restart write footprint wrong: prefix=%0d written=%0d", prefix_errors, written_bytes);
    end else begin
      assert(!done && beats == 1 && m.read_cnt_q == 0 &&
        m.mask_queue_cnt_q == 0 && s.issue_cnt_q != 0 &&
        s.mask_valid_q == 0 && &s.sldu_operand_valid && !s.result_queue_full)
        else $fatal(1, "Predicted mask-starvation signature not observed");
    end
    $display("FOOTPRINT prefix_errors=%0d written_bytes=%0d", prefix_errors, written_bytes);
    $display("MASK_SLIDE_CHECK_PASS expected_starvation=%0b", $test$plusargs("EXPECT_STARVATION"));
    $finish;
  end
endmodule
