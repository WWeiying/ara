// Observe the real SRAM outputs; compare only data a queue can consume.
module vrf_return_soc_monitor import ara_pkg::*; #(parameter int Banks = 8)(
  input logic clk_i, rst_ni,
  input elen_t [Banks-1:0] data,
  input logic [Banks-1:0] valid,
  input opqueue_e [Banks-1:0] target,
  input elen_t [NrOperandQueues-1:0] actual,
  input logic [NrOperandQueues-1:0] actual_valid
);
  elen_t [NrOperandQueues-1:0] expected;
  logic [NrOperandQueues-1:0] expected_valid;
  longint unsigned returns = 0;
  stream_xbar #(.NumInp(Banks), .NumOut(NrOperandQueues), .DataWidth(64), .AxiVldRdy(1)) old_router (
    .clk_i, .rst_ni, .flush_i(1'b0), .rr_i('0), .data_i(data), .valid_i(valid),
    .ready_o(), .sel_i(target), .data_o(expected), .valid_o(expected_valid), .idx_o(), .ready_i('1));
  always @(posedge clk_i) if (rst_ni) begin
    if (actual_valid !== expected_valid) $fatal(1, "VRF_SOC_VALID_MISMATCH %m");
    for (int q = 0; q < NrOperandQueues; q++) if (actual_valid[q]) begin
      if (actual[q] !== expected[q]) $fatal(1, "VRF_SOC_DATA_MISMATCH %m queue=%0d", q);
      returns++;
    end
  end
  final $display("VRF_SOC_CHECKED %m returns=%0d", returns);
endmodule

bind vector_regfile vrf_return_soc_monitor #(.Banks(NrBanks)) i_return_monitor (
  .clk_i, .rst_ni, .data(rdata), .valid(rdata_valid_q), .target(tgt_opqueue_q),
  .actual(operand_o), .actual_valid(operand_valid_o));
