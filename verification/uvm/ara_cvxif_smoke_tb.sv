module ara_cvxif_smoke_tb;
  import uvm_pkg::*;
  import ara_cvxif_uvm_pkg::*;

  logic clk_i = 1'b0;
  logic rst_ni = 1'b0;
  ara_cvxif_if #(64, 4) cvxif(clk_i, rst_ni);

  always #5 clk_i = ~clk_i;

  task automatic send_request(input logic [3:0] id, input logic [31:0] insn);
    @(negedge clk_i);
    cvxif.req_valid = 1'b1;
    cvxif.req_trans_id = id;
    cvxif.insn = insn;
    cvxif.rs1 = '0;
    cvxif.rs2 = '0;
    do @(posedge clk_i); while (!cvxif.req_ready);
    @(negedge clk_i);
    cvxif.req_valid = 1'b0;
  endtask

  task automatic send_response(input logic [3:0] id, input logic [63:0] result);
    @(negedge clk_i);
    cvxif.resp_valid = 1'b1;
    cvxif.resp_trans_id = id;
    cvxif.result = result;
    cvxif.exception_valid = 1'b0;
    do @(posedge clk_i); while (!cvxif.resp_ready);
    @(negedge clk_i);
    cvxif.resp_valid = 1'b0;
  endtask

  task automatic send_simultaneous(input logic [3:0] req_id,
                                   input logic [3:0] resp_id);
    @(negedge clk_i);
    cvxif.req_valid = 1'b1;
    cvxif.req_trans_id = req_id;
    cvxif.resp_valid = 1'b1;
    cvxif.resp_trans_id = resp_id;
    do @(posedge clk_i); while (!cvxif.req_ready || !cvxif.resp_ready);
    @(negedge clk_i);
    cvxif.req_valid = 1'b0;
    cvxif.resp_valid = 1'b0;
  endtask

  task automatic send_backend_event(input logic alloc,
                                    input logic [2:0] id,
                                    input logic [7:0] done_mask);
    @(negedge clk_i);
    cvxif.backend_alloc = alloc;
    cvxif.backend_alloc_id = id;
    cvxif.backend_done = done_mask;
    @(negedge clk_i);
    cvxif.backend_alloc = 1'b0;
    cvxif.backend_done = '0;
  endtask

  task automatic send_axi_ar(input logic [7:0] id, input logic [7:0] len);
    @(negedge clk_i);
    cvxif.axi_ar_id = id;
    cvxif.axi_ar_len = len;
    cvxif.axi_ar_valid = 1'b1;
    @(negedge clk_i);
    cvxif.axi_ar_valid = 1'b0;
  endtask

  task automatic send_axi_r(input logic [7:0] id, input logic last);
    @(negedge clk_i);
    cvxif.axi_r_id = id;
    cvxif.axi_r_last = last;
    cvxif.axi_r_valid = 1'b1;
    @(negedge clk_i);
    cvxif.axi_r_valid = 1'b0;
  endtask

  task automatic send_axi_immediate(input logic [7:0] id);
    @(negedge clk_i);
    cvxif.axi_ar_id = id;
    cvxif.axi_ar_len = 0;
    cvxif.axi_ar_valid = 1'b1;
    cvxif.axi_r_id = id;
    cvxif.axi_r_last = 1'b1;
    cvxif.axi_r_valid = 1'b1;
    @(negedge clk_i);
    cvxif.axi_ar_valid = 1'b0;
    cvxif.axi_r_valid = 1'b0;
  endtask

  task automatic send_axi_aw(input logic [7:0] id, input logic [7:0] len);
    @(negedge clk_i);
    cvxif.axi_aw_id = id;
    cvxif.axi_aw_len = len;
    cvxif.axi_aw_valid = 1'b1;
    @(negedge clk_i);
    cvxif.axi_aw_valid = 1'b0;
  endtask

  task automatic send_axi_w(input logic last);
    @(negedge clk_i);
    cvxif.axi_w_last = last;
    cvxif.axi_w_valid = 1'b1;
    @(negedge clk_i);
    cvxif.axi_w_valid = 1'b0;
  endtask

  task automatic send_axi_b(input logic [7:0] id);
    @(negedge clk_i);
    cvxif.axi_b_id = id;
    cvxif.axi_b_valid = 1'b1;
    @(negedge clk_i);
    cvxif.axi_b_valid = 1'b0;
  endtask

  task automatic send_axi_write_immediate(input logic [7:0] id);
    @(negedge clk_i);
    cvxif.axi_aw_id = id;
    cvxif.axi_aw_len = 0;
    cvxif.axi_aw_valid = 1'b1;
    cvxif.axi_w_last = 1'b1;
    cvxif.axi_w_valid = 1'b1;
    cvxif.axi_b_id = id;
    cvxif.axi_b_valid = 1'b1;
    @(negedge clk_i);
    cvxif.axi_aw_valid = 1'b0;
    cvxif.axi_w_valid = 1'b0;
    cvxif.axi_b_valid = 1'b0;
  endtask

  task automatic inject_axi_hold_violation(input int unsigned channel);
    @(negedge clk_i);
    case (channel)
      0: begin cvxif.axi_ar_valid = 1'b1; cvxif.axi_ar_ready = 1'b0; end
      1: begin cvxif.axi_r_valid = 1'b1; cvxif.axi_r_ready = 1'b0; end
      2: begin cvxif.axi_aw_valid = 1'b1; cvxif.axi_aw_ready = 1'b0; end
      3: begin cvxif.axi_w_valid = 1'b1; cvxif.axi_w_ready = 1'b0; end
      4: begin cvxif.axi_b_valid = 1'b1; cvxif.axi_b_ready = 1'b0; end
    endcase
    @(negedge clk_i);
    case (channel)
      0: cvxif.axi_ar_payload ^= 1024'(1);
      1: cvxif.axi_r_payload ^= 1024'(1);
      2: cvxif.axi_aw_payload ^= 1024'(1);
      3: cvxif.axi_w_payload ^= 1024'(1);
      4: cvxif.axi_b_payload ^= 1024'(1);
    endcase
    @(negedge clk_i);
    rst_ni = 1'b0;
    cvxif.axi_ar_valid = 1'b0;
    cvxif.axi_r_valid = 1'b0;
    cvxif.axi_aw_valid = 1'b0;
    cvxif.axi_w_valid = 1'b0;
    cvxif.axi_b_valid = 1'b0;
    cvxif.axi_ar_ready = 1'b1;
    cvxif.axi_r_ready = 1'b1;
    cvxif.axi_aw_ready = 1'b1;
    cvxif.axi_w_ready = 1'b1;
    cvxif.axi_b_ready = 1'b1;
    repeat (2) @(negedge clk_i);
    rst_ni = 1'b1;
  endtask

  initial begin
    cvxif.req_valid = 1'b0;
    cvxif.req_ready = 1'b1;
    cvxif.resp_valid = 1'b0;
    cvxif.resp_ready = 1'b1;
    cvxif.req_trans_id = '0;
    cvxif.resp_trans_id = '0;
    cvxif.insn = '0;
    cvxif.rs1 = '0;
    cvxif.rs2 = '0;
    cvxif.result = '0;
    cvxif.exception_valid = 1'b0;
    cvxif.backend_alloc = 1'b0;
    cvxif.backend_alloc_id = '0;
    cvxif.backend_done = '0;
    cvxif.axi_enable = 1'b1;
    cvxif.axi_ar_valid = 1'b0;
    cvxif.axi_ar_ready = 1'b1;
    cvxif.axi_ar_id = '0;
    cvxif.axi_ar_len = '0;
    cvxif.axi_r_valid = 1'b0;
    cvxif.axi_r_ready = 1'b1;
    cvxif.axi_r_id = '0;
    cvxif.axi_r_last = 1'b0;
    cvxif.axi_aw_valid = 1'b0;
    cvxif.axi_aw_ready = 1'b1;
    cvxif.axi_aw_id = '0;
    cvxif.axi_aw_len = '0;
    cvxif.axi_w_valid = 1'b0;
    cvxif.axi_w_ready = 1'b1;
    cvxif.axi_w_last = 1'b0;
    cvxif.axi_b_valid = 1'b0;
    cvxif.axi_b_ready = 1'b1;
    cvxif.axi_b_id = '0;
    cvxif.axi_ar_payload = '0;
    cvxif.axi_r_payload = '0;
    cvxif.axi_aw_payload = '0;
    cvxif.axi_w_payload = '0;
    cvxif.axi_b_payload = '0;
    cvxif.store_pending = 1'b0;
    cvxif.store_complete = 1'b0;
    cvxif.load_complete = 1'b0;
    cvxif.smoke_done = 1'b0;
    cvxif.smoke_pass = 1'b1;
    repeat (2) @(negedge clk_i);
    rst_ni = 1'b1;
    send_request(4'd3, 32'h00000057);
    send_response(4'd3, 64'h0000000000000042);
    send_request(4'd7, 32'h00000057);
    send_response(4'd7, 64'h0000000000000043);
    send_request(4'd5, 32'h00000057);
    send_simultaneous(4'd5, 4'd5);
    send_response(4'd5, 64'h0000000000000044);
    send_simultaneous(4'd6, 4'd6);
    send_backend_event(1'b1, 3'd1, 8'h00);
    send_backend_event(1'b1, 3'd1, 8'h02);
    send_backend_event(1'b0, 3'd0, 8'h02);
    send_backend_event(1'b1, 3'd2, 8'h00);
    if ($test$plusargs("VID_INJECT_ORPHAN"))
      send_backend_event(1'b0, 3'd0, 8'h80);
    if ($test$plusargs("VID_INJECT_DUP")) begin
      send_backend_event(1'b1, 3'd3, 8'h00);
      send_backend_event(1'b1, 3'd3, 8'h00);
    end
    send_axi_ar(8'd1, 8'd0);
    send_axi_r(8'd1, 1'b1);
    send_axi_ar(8'd2, 8'd1);
    send_axi_r(8'd2, 1'b0);
    send_axi_r(8'd2, 1'b1);
    send_axi_ar(8'd3, 8'd2);
    send_axi_aw(8'd1, 8'd1);
    send_axi_w(1'b0);
    send_axi_w(1'b1);
    send_axi_b(8'd1);
    send_axi_w(1'b1);
    send_axi_aw(8'd2, 8'd0);
    send_axi_b(8'd2);
    send_axi_aw(8'd3, 8'd2);
    send_request(4'd2, 32'h00000057);
    @(negedge clk_i);
    rst_ni = 1'b0;
    repeat (2) @(negedge clk_i);
    rst_ni = 1'b1;
    send_axi_ar(8'd4, 8'd0);
    send_axi_ar(8'd4, 8'd1);
    send_axi_r(8'd4, 1'b1);
    send_axi_r(8'd4, 1'b0);
    send_axi_r(8'd4, 1'b1);
    send_axi_immediate(8'd6);
    send_axi_aw(8'd4, 8'd0);
    send_axi_aw(8'd4, 8'd0);
    send_axi_w(1'b1);
    send_axi_w(1'b1);
    send_axi_b(8'd4);
    send_axi_b(8'd4);
    send_axi_write_immediate(8'd6);
    @(negedge clk_i);
    cvxif.axi_aw_ready = 1'b0;
    cvxif.axi_aw_valid = 1'b1;
    cvxif.axi_aw_id = 8'd8;
    cvxif.axi_aw_len = 8'd0;
    cvxif.axi_aw_payload = 1024'(64'h1234);
    @(negedge clk_i);
    if ($test$plusargs("AXI_INJECT_AW_HOLD"))
      cvxif.axi_aw_payload ^= 1024'(1);
    @(negedge clk_i);
    cvxif.axi_aw_ready = 1'b1;
    @(negedge clk_i);
    cvxif.axi_aw_valid = 1'b0;
    send_axi_w(1'b1);
    send_axi_b(8'd8);
    if ($test$plusargs("AXI_INJECT_R_ORPHAN"))
      send_axi_r(8'd7, 1'b1);
    if ($test$plusargs("AXI_INJECT_RLAST")) begin
      send_axi_ar(8'd5, 8'd1);
      send_axi_r(8'd5, 1'b1);
      send_axi_r(8'd5, 1'b1);
    end
    if ($test$plusargs("AXI_INJECT_B_ORPHAN"))
      send_axi_b(8'd7);
    if ($test$plusargs("AXI_INJECT_WLAST")) begin
      send_axi_aw(8'd5, 8'd1);
      send_axi_w(1'b1);
      send_axi_b(8'd5);
    end
    if ($test$plusargs("AXI_INJECT_AR_HOLD")) inject_axi_hold_violation(0);
    if ($test$plusargs("AXI_INJECT_R_HOLD")) inject_axi_hold_violation(1);
    if ($test$plusargs("AXI_INJECT_W_HOLD")) inject_axi_hold_violation(3);
    if ($test$plusargs("AXI_INJECT_B_HOLD")) inject_axi_hold_violation(4);
    repeat (3) @(negedge clk_i);
    $display("UVM CVXIF contract smoke PASS");
    cvxif.smoke_done = 1'b1;
  end

  initial begin
    uvm_config_db#(virtual ara_cvxif_if #(64, 4))::set(
        null, "*", "vif", cvxif);
    run_test("ara_cvxif_smoke_test");
  end
endmodule
