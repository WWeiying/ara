// Restricted payload-shape synthesis probe, not full LSU/MMU equivalence.
module lsu_bypass_probe (
  input logic clk_i, rst_ni, flush_i, push_i, pop_ld_i, pop_st_i,
  input logic [255:0] data_i,
  output logic ready_o, valid_o,
  output logic [255:0] data_o
);
  typedef struct packed { logic valid; logic [255:0] payload; } ctrl_t;
  ctrl_t req, resp;
  assign req = {push_i, data_i};
  assign valid_o = resp.valid;
  assign data_o = resp.payload;
  lsu_bypass #(.lsu_ctrl_t(ctrl_t)) dut (
    .clk_i, .rst_ni, .flush_i, .lsu_req_i(req),
    .lsu_req_valid_i(push_i), .pop_ld_i, .pop_st_i,
    .lsu_ctrl_o(resp), .ready_o
  );
endmodule
