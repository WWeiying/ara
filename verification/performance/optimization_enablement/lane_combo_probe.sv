// SPDX-License-Identifier: Apache-2.0
module lane_combo_probe #(
  parameter bit Shared = 0, Resident = 0, Borrower = 0
) (
  input logic clk, rst, owned, fp32, valid, ready, returned,
  input logic borrowed, borrow_ready, borrow_returned, borrow_owned,
  input logic native_valid, native_ready
);
  int fp16_issued = 0, fp32_issued = 0, private_returns = 0;
  int borrow_issued = 0, borrow_returns = 0, native_issued = 0;
  initial begin
`ifndef ARA_SHARED_SIMD_MUL
    $fatal(1, "LANE_COMBO missing shared integer multiplier");
`endif
`ifndef ARA_SHARED_FMA
    $fatal(1, "LANE_COMBO missing shared FMA macro");
`endif
    if (!Shared || !Resident || !Borrower || !ara_pkg::EnableSharedFma ||
        !ara_pkg::QbsLaneMulLatencySupported || ara_pkg::LatFCompEW64 != 5)
      $fatal(1, "LANE_COMBO wrong actual configuration");
    $display("LANE_COMBO_CONFIG shared_fma=1 shared_mul=1 resident=1 borrower=1 fma_latency=5");
  end
  always @(posedge clk) if (rst) begin
    if (owned && borrow_owned) $fatal(1, "LANE_COMBO double ownership");
    if (valid && ready) begin
      if (!owned) $fatal(1, "LANE_COMBO unowned private issue");
      if (fp32) fp32_issued++; else fp16_issued++;
    end
    if (returned) private_returns++;
    if (borrowed && borrow_ready) borrow_issued++;
    if (borrow_returned) borrow_returns++;
    if (native_valid && native_ready) native_issued++;
  end
  final $display("LANE_COMBO_WORK fp16=%0d fp32=%0d private_returns=%0d borrowed=%0d returned=%0d native=%0d",
                 fp16_issued, fp32_issued, private_returns, borrow_issued, borrow_returns, native_issued);
endmodule

bind vmfpu lane_combo_probe #(.Shared(SharedFma), .Resident(EnableResidentPv),
  .Borrower(EnableQbsLaneMul)) i_lane_combo_probe (
  .clk(clk_i), .rst(rst_ni), .owned(resident_owned_q), .fp32(resident_fp32_i),
  .valid(resident_valid_i), .ready(resident_ready_o),
  .returned(resident_result_valid_o && resident_result_ready_i),
  .borrowed(qbs_mul_valid_i), .borrow_ready(qbs_mul_ready_o),
  .borrow_returned(qbs_mul_result_valid_o), .borrow_owned(qbs_mul_owned),
  .native_valid(vfu_operation_valid_i), .native_ready(mfpu_ready_o)
);
