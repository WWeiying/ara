// Verification-only passive UVM adapter for the actual CVA6/Ara boundary.
module ara_cvxif_dut_bind #(
  parameter int unsigned XLEN = 64,
  parameter int unsigned TRANS_ID_BITS = 3,
  parameter int unsigned AXI_ID_WIDTH = 4
) (
  input logic                         clk_i,
  input logic                         rst_ni,
  input logic                         req_valid_i,
  input logic                         req_ready_i,
  input logic [31:0]                  req_insn_i,
  input logic [XLEN-1:0]              req_rs1_i,
  input logic [XLEN-1:0]              req_rs2_i,
  input logic [TRANS_ID_BITS-1:0]     req_id_i,
  input logic                         resp_valid_i,
  input logic                         resp_ready_i,
  input logic [XLEN-1:0]              resp_result_i,
  input logic [TRANS_ID_BITS-1:0]     resp_id_i,
  input logic                         resp_exception_valid_i,
  input logic                         backend_alloc_i,
  input logic [2:0]                   backend_alloc_id_i,
  input logic [7:0]                   backend_done_i,
  input logic                         axi_ar_valid_i,
  input logic                         axi_ar_ready_i,
  input logic [7:0]                   axi_ar_id_i,
  input logic [7:0]                   axi_ar_len_i,
  input logic                         axi_r_valid_i,
  input logic                         axi_r_ready_i,
  input logic [7:0]                   axi_r_id_i,
  input logic                         axi_r_last_i,
  input logic                         axi_aw_valid_i,
  input logic                         axi_aw_ready_i,
  input logic [7:0]                   axi_aw_id_i,
  input logic [7:0]                   axi_aw_len_i,
  input logic                         axi_w_valid_i,
  input logic                         axi_w_ready_i,
  input logic                         axi_w_last_i,
  input logic                         axi_b_valid_i,
  input logic                         axi_b_ready_i,
  input logic [7:0]                   axi_b_id_i,
  input logic [1023:0]                axi_ar_payload_i,
  input logic [1023:0]                axi_r_payload_i,
  input logic [1023:0]                axi_aw_payload_i,
  input logic [1023:0]                axi_w_payload_i,
  input logic [1023:0]                axi_b_payload_i,
  input logic                         test_done_i,
  input logic                         test_pass_i
);
  import uvm_pkg::*;
  import ara_cvxif_uvm_pkg::*;

  ara_cvxif_if #(64, 4) cvxif(clk_i, rst_ni);

  initial begin
    if (XLEN != 64 || TRANS_ID_BITS > 4 || AXI_ID_WIDTH > 8)
      $fatal(1, "CVXIF UVM adapter requires XLEN=64, CVXIF ID <=4, AXI ID <=8");
    $display("[DUT_BOUNDARY_CONTRACT] atomic_cvxif=0 delayed_result_tracking=1 b_always_ready=1");
    uvm_config_db#(virtual ara_cvxif_if #(64, 4))::set(null, "*", "vif", cvxif);
    run_test("ara_cvxif_dut_test");
  end

  // The independent contract monitor and UVM scoreboard track outstanding
  // transaction IDs across delayed CVXIF results. VSTU accepts every valid B.
  always @(posedge clk_i) begin
    if (rst_ni) begin
      if (axi_b_valid_i)
        assert (axi_b_ready_i)
          else $error("Ara B response was backpressured");
    end
  end

  assign cvxif.req_valid = req_valid_i;
  assign cvxif.req_ready = req_ready_i;
  assign cvxif.insn = req_insn_i;
  assign cvxif.rs1 = req_rs1_i;
  assign cvxif.rs2 = req_rs2_i;
  assign cvxif.req_trans_id = 4'(req_id_i);
  assign cvxif.resp_valid = resp_valid_i;
  assign cvxif.resp_ready = resp_ready_i;
  assign cvxif.result = resp_result_i;
  assign cvxif.resp_trans_id = 4'(resp_id_i);
  assign cvxif.exception_valid = resp_exception_valid_i;
  assign cvxif.backend_alloc = backend_alloc_i;
  assign cvxif.backend_alloc_id = backend_alloc_id_i;
  assign cvxif.backend_done = backend_done_i;
  assign cvxif.axi_enable = 1'b1;
  assign cvxif.axi_ar_valid = axi_ar_valid_i;
  assign cvxif.axi_ar_ready = axi_ar_ready_i;
  assign cvxif.axi_ar_id = axi_ar_id_i;
  assign cvxif.axi_ar_len = axi_ar_len_i;
  assign cvxif.axi_r_valid = axi_r_valid_i;
  assign cvxif.axi_r_ready = axi_r_ready_i;
  assign cvxif.axi_r_id = axi_r_id_i;
  assign cvxif.axi_r_last = axi_r_last_i;
  assign cvxif.axi_aw_valid = axi_aw_valid_i;
  assign cvxif.axi_aw_ready = axi_aw_ready_i;
  assign cvxif.axi_aw_id = axi_aw_id_i;
  assign cvxif.axi_aw_len = axi_aw_len_i;
  assign cvxif.axi_w_valid = axi_w_valid_i;
  assign cvxif.axi_w_ready = axi_w_ready_i;
  assign cvxif.axi_w_last = axi_w_last_i;
  assign cvxif.axi_b_valid = axi_b_valid_i;
  assign cvxif.axi_b_ready = axi_b_ready_i;
  assign cvxif.axi_b_id = axi_b_id_i;
  assign cvxif.axi_ar_payload = axi_ar_payload_i;
  assign cvxif.axi_r_payload = axi_r_payload_i;
  assign cvxif.axi_aw_payload = axi_aw_payload_i;
  assign cvxif.axi_w_payload = axi_w_payload_i;
  assign cvxif.axi_b_payload = axi_b_payload_i;
  assign cvxif.smoke_done = test_done_i;
  assign cvxif.smoke_pass = test_pass_i;
  assign cvxif.store_pending = 1'b0;
  assign cvxif.store_complete = 1'b0;
  assign cvxif.load_complete = 1'b0;

endmodule

bind ara_system ara_cvxif_dut_bind #(
  .XLEN(CVA6Cfg.XLEN),
  .TRANS_ID_BITS(CVA6Cfg.TRANS_ID_BITS),
  .AXI_ID_WIDTH(AxiIdWidth)
) i_ara_cvxif_dut_bind (
  .clk_i(clk_i),
  .rst_ni(rst_ni),
  .req_valid_i(acc_req.acc_req.req_valid),
  .req_ready_i(acc_resp.acc_resp.req_ready),
  .req_insn_i(acc_req.acc_req.insn),
  .req_rs1_i(acc_req.acc_req.rs1),
  .req_rs2_i(acc_req.acc_req.rs2),
  .req_id_i(acc_req.acc_req.trans_id),
  .resp_valid_i(acc_resp.acc_resp.resp_valid),
  .resp_ready_i(acc_req.acc_req.resp_ready),
  .resp_result_i(acc_resp.acc_resp.result),
  .resp_id_i(acc_resp.acc_resp.trans_id),
  .resp_exception_valid_i(acc_resp.acc_resp.exception.valid),
  .backend_alloc_i(i_ara.i_sequencer.verify_vinsn_alloc),
  .backend_alloc_id_i(i_ara.i_sequencer.vinsn_id_n),
  .backend_done_i(i_ara.i_sequencer.verify_vinsn_done),
  .axi_ar_valid_i(ara_axi_req.ar_valid),
  .axi_ar_ready_i(ara_axi_resp.ar_ready),
  .axi_ar_id_i(8'(ara_axi_req.ar.id)),
  .axi_ar_len_i(ara_axi_req.ar.len),
  .axi_r_valid_i(ara_axi_resp.r_valid),
  .axi_r_ready_i(ara_axi_req.r_ready),
  .axi_r_id_i(8'(ara_axi_resp.r.id)),
  .axi_r_last_i(ara_axi_resp.r.last),
  .axi_aw_valid_i(ara_axi_req.aw_valid),
  .axi_aw_ready_i(ara_axi_resp.aw_ready),
  .axi_aw_id_i(8'(ara_axi_req.aw.id)),
  .axi_aw_len_i(ara_axi_req.aw.len),
  .axi_w_valid_i(ara_axi_req.w_valid),
  .axi_w_ready_i(ara_axi_resp.w_ready),
  .axi_w_last_i(ara_axi_req.w.last),
  .axi_b_valid_i(ara_axi_resp.b_valid),
  .axi_b_ready_i(ara_axi_req.b_ready),
  .axi_b_id_i(8'(ara_axi_resp.b.id)),
  .axi_ar_payload_i(1024'(ara_axi_req.ar)),
  .axi_r_payload_i(1024'(ara_axi_resp.r)),
  .axi_aw_payload_i(1024'(ara_axi_req.aw)),
  .axi_w_payload_i(1024'(ara_axi_req.w)),
  .axi_b_payload_i(1024'(ara_axi_resp.b)),
  .test_done_i(ara_tb.exit[0]),
  .test_pass_i(ara_tb.exit == 64'd1)
);
