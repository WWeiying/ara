// ALU-B production parameters; the surrounding queue/control is included.
module operand_ext_timing import ara_pkg::*; import operand_ext_pkg::*; (
  input logic clk_i, rst_ni, flush_i,
  input logic [1:0] lane_id_i,
  input cmd_t cmd_i,
  input logic cmd_valid_i,
  input elen_t data_i,
  input logic valid_i, issued_i, ready_i,
  output logic credit_o, valid_o, pop_o,
  output elen_t data_o,
  output target_fu_e target_o
);
  operand_queue #(.CmdBufDepth(4), .DataBufDepth(5), .NrSlaves(1), .NrLanes(4),
    .VLEN(1024), .AccessCmdPop(1), .FPUSupport(FPUSupportNone),
    .SupportIntExt2(1), .SupportIntExt4(1), .SupportIntExt8(1),
    .SupportReduct(1), .SupportNtrVal(1), .operand_queue_cmd_t(cmd_t)) i_queue (
    .clk_i, .rst_ni, .flush_i, .lane_id_i, .operand_queue_cmd_i(cmd_i),
    .operand_queue_cmd_valid_i(cmd_valid_i), .cmd_pop_o(pop_o),
    .operand_i(data_i), .operand_valid_i(valid_i), .operand_issued_i(issued_i),
    .operand_queue_ready_o(credit_o), .operand_o(data_o), .operand_target_fu_o(target_o),
    .operand_valid_o(valid_o), .operand_ready_i(ready_i));
endmodule
