// Verification-only CVXIF transaction interface.
// The field names mirror the architectural handshake at ara_system; the
// adapter to a concrete DUT may bind the packed Ara structs to these fields.
interface ara_cvxif_if #(
  parameter int unsigned Xlen       = 64,
  parameter int unsigned TransIdW   = 4
) (
  input logic clk_i,
  input logic rst_ni
);
  logic                    req_valid;
  logic                    req_ready;
  logic                    resp_valid;
  logic                    resp_ready;
  logic [31:0]             insn;
  logic [Xlen-1:0]         rs1;
  logic [Xlen-1:0]         rs2;
  logic [TransIdW-1:0]     req_trans_id;
  logic [TransIdW-1:0]     resp_trans_id;
  logic [Xlen-1:0]         result;
  logic                    store_pending;
  logic                    store_complete;
  logic                    load_complete;
  logic                    exception_valid;
  logic                    backend_alloc;
  logic [2:0]              backend_alloc_id;
  logic [7:0]              backend_done;
  logic                    axi_enable;
  logic                    axi_ar_valid;
  logic                    axi_ar_ready;
  logic [7:0]              axi_ar_id;
  logic [7:0]              axi_ar_len;
  logic                    axi_r_valid;
  logic                    axi_r_ready;
  logic [7:0]              axi_r_id;
  logic                    axi_r_last;
  logic                    axi_aw_valid;
  logic                    axi_aw_ready;
  logic [7:0]              axi_aw_id;
  logic [7:0]              axi_aw_len;
  logic                    axi_w_valid;
  logic                    axi_w_ready;
  logic                    axi_w_last;
  logic                    axi_b_valid;
  logic                    axi_b_ready;
  logic [7:0]              axi_b_id;
  // Full packed AXI payloads, zero-extended by the DUT bind for hold checks.
  logic [1023:0]           axi_ar_payload;
  logic [1023:0]           axi_r_payload;
  logic [1023:0]           axi_aw_payload;
  logic [1023:0]           axi_w_payload;
  logic [1023:0]           axi_b_payload;
  logic                    smoke_done;
  logic                    smoke_pass;

  clocking monitor_cb @(posedge clk_i);
    default input #1step;
    input rst_ni, req_valid, req_ready, resp_valid, resp_ready;
    input insn, rs1, rs2, req_trans_id, resp_trans_id;
    input result, exception_valid;
    input backend_alloc, backend_alloc_id, backend_done;
    input axi_enable, axi_ar_valid, axi_ar_ready, axi_ar_id, axi_ar_len;
    input axi_r_valid, axi_r_ready, axi_r_id, axi_r_last;
    input axi_aw_valid, axi_aw_ready, axi_aw_id, axi_aw_len;
    input axi_w_valid, axi_w_ready, axi_w_last;
    input axi_b_valid, axi_b_ready, axi_b_id;
    input axi_ar_payload, axi_r_payload, axi_aw_payload, axi_w_payload, axi_b_payload;
  endclocking
endinterface
