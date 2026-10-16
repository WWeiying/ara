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
  end
  initial begin
    start = 8; sew = 2; down = 0;
    void'($value$plusargs("START=%d", start));
    void'($value$plusargs("SEW=%d", sew));
    void'($value$plusargs("DOWN=%d", down));
    rst = 0; valid = 0; req = '0; operand_valid = '0;
    beats = 0; done = 0;
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
    if (start == 0) begin
      assert(done && beats == 2) else $fatal(1, "Control did not complete");
    end else begin
      assert(!done && beats == 1 && m.read_cnt_q == 0 &&
        m.mask_queue_cnt_q == 0 && s.issue_cnt_q != 0 &&
        s.mask_valid_q == 0 && &s.sldu_operand_valid && !s.result_queue_full)
        else $fatal(1, "Predicted mask-starvation signature not observed");
    end
    $display("MASK_SLIDE_HYPOTHESIS_CONFIRMED");
    $finish;
  end
endmodule
