module operand_ext_soc_monitor import ara_pkg::*; #(
  parameter int CmdBufDepth=2, DataBufDepth=2, NrSlaves=1, NrLanes=4, VLEN=1024,
  parameter bit AccessCmdPop=0,
  parameter fpu_support_e FPUSupport=FPUSupportHalfSingleDouble,
  parameter logic SupportIntExt2=0, SupportIntExt4=0, SupportIntExt8=0,
  parameter logic SupportReduct=0, SupportNtrVal=0,
  parameter type operand_queue_cmd_t=logic
)(
  input logic clk_i,rst_ni,flush_i,
  input logic [cf_math_pkg::idx_width(NrLanes)-1:0] lane_id_i,
  input operand_queue_cmd_t operand_queue_cmd_i,
  input logic operand_queue_cmd_valid_i,
  input elen_t operand_i,
  input logic operand_valid_i,operand_issued_i,
  input logic [NrSlaves-1:0] operand_ready_i,
  input elen_t actual,
  input target_fu_e actual_target,
  input logic actual_valid,actual_credit,actual_pop
);
  elen_t expected;
  target_fu_e expected_target;
  logic expected_valid,expected_credit,expected_pop;
  longint unsigned checks=0;
  operand_queue_reference #(.CmdBufDepth(CmdBufDepth),.DataBufDepth(DataBufDepth),
    .NrSlaves(NrSlaves),.NrLanes(NrLanes),.VLEN(VLEN),.AccessCmdPop(AccessCmdPop),
    .FPUSupport(FPUSupport),.SupportIntExt2(SupportIntExt2),.SupportIntExt4(SupportIntExt4),
    .SupportIntExt8(SupportIntExt8),.SupportReduct(SupportReduct),.SupportNtrVal(SupportNtrVal),
    .operand_queue_cmd_t(operand_queue_cmd_t)) old_queue (
    .clk_i,.rst_ni,.flush_i,.lane_id_i,.operand_queue_cmd_i,.operand_queue_cmd_valid_i,
    .operand_i,.operand_valid_i,.operand_issued_i,.operand_ready_i,
    .operand_o(expected),.operand_target_fu_o(expected_target),
    .operand_valid_o(expected_valid),.operand_queue_ready_o(expected_credit),.cmd_pop_o(expected_pop));
  always @(posedge clk_i) if(rst_ni) begin
    if ({actual_valid,actual_credit,actual_pop} !== {expected_valid,expected_credit,expected_pop})
      $fatal(1,"EXT_SOC_HANDSHAKE_MISMATCH %m");
    if(actual_valid) begin
      if(actual !== expected || actual_target !== expected_target) $fatal(1,"EXT_SOC_DATA_MISMATCH %m");
      checks++;
    end
  end
  final $display("EXT_SOC_CHECKED %m cycles=%0d",checks);
endmodule

bind operand_queue operand_ext_soc_monitor #(.CmdBufDepth(CmdBufDepth),.DataBufDepth(DataBufDepth),
  .NrSlaves(NrSlaves),.NrLanes(NrLanes),.VLEN(VLEN),.AccessCmdPop(AccessCmdPop),
  .FPUSupport(FPUSupport),.SupportIntExt2(SupportIntExt2),.SupportIntExt4(SupportIntExt4),
  .SupportIntExt8(SupportIntExt8),.SupportReduct(SupportReduct),.SupportNtrVal(SupportNtrVal),
  .operand_queue_cmd_t(operand_queue_cmd_t)) i_ext_monitor (
  .clk_i,.rst_ni,.flush_i,.lane_id_i,.operand_queue_cmd_i,.operand_queue_cmd_valid_i,
  .operand_i,.operand_valid_i,.operand_issued_i,.operand_ready_i,
  .actual(operand_o),.actual_target(operand_target_fu_o),.actual_valid(operand_valid_o),
  .actual_credit(operand_queue_ready_o),.actual_pop(cmd_pop_o));
