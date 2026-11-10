// Passive accounting at the actual VMFPU core, not the engine fixture.
module stage2_soc_loan_monitor #(
  parameter int LaneWidth = 2
) (
  input logic clk_i, rst_ni,
  input logic [LaneWidth-1:0] lane_i,
  input logic lease_i, owned_i, valid_i, ready_i,
  input logic core_valid_i, core_ready_i, core_done_i, result_valid_i
);
  logic previous_lease;
  longint unsigned sequence_id, accepted, core_issued, core_completed, returned;
  longint unsigned total_accepted, total_returned;
  logic [2:0] due;
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      previous_lease <= 0;
      sequence_id = 0;
      accepted = 0; core_issued = 0; core_completed = 0; returned = 0;
      total_accepted = 0; total_returned = 0;
      due <= 0;
    end else begin
      assert (result_valid_i === due[2])
        else $fatal(1, "STAGE2_SOC_LOAN response alignment lane=%0d", lane_i);
      due <= {due[1:0], valid_i && ready_i};
      previous_lease <= lease_i;
      if (lease_i && !previous_lease) begin
        sequence_id++;
        accepted = 0; core_issued = 0; core_completed = 0; returned = 0;
      end
      if (valid_i && ready_i) begin
        assert (lease_i && owned_i)
          else $fatal(1, "STAGE2_SOC_LOAN accepted without ownership");
        accepted++;
        total_accepted++;
      end
      if (core_valid_i && core_ready_i) core_issued++;
      if (core_done_i) core_completed++;
      if (result_valid_i) begin returned++; total_returned++; end
      if (!lease_i && previous_lease) begin
        assert (due == 0 && accepted == core_issued && accepted == core_completed &&
                accepted == returned)
          else $fatal(1, "STAGE2_SOC_LOAN release before actual core drain");
        $display("STAGE2_SOC_LOAN lane=%0d seq=%0d accepted=%0d core_issued=%0d core_completed=%0d returned=%0d",
          lane_i, sequence_id, accepted, core_issued, core_completed, returned);
      end
    end
  end
  final begin
    $display("STAGE2_SOC_LOAN_DONE lane=%0d commands=%0d accepted=%0d returned=%0d",
             lane_i, sequence_id, total_accepted, total_returned);
  end
endmodule

bind vmfpu stage2_soc_loan_monitor #(.LaneWidth($bits(lane_id_i))) i_stage2_soc_loan_monitor (
  .clk_i, .rst_ni, .lane_i(lane_id_i),
  .lease_i(qbs_mul_requested), .owned_i(qbs_mul_owned),
  .valid_i(qbs_mul_valid_i), .ready_i(qbs_mul_ready_o),
  .core_valid_i(qbs_mul_issue), .core_ready_i(qbs_mul_core_ready),
  .core_done_i(qbs_mul_core_valid), .result_valid_i(qbs_mul_result_valid_o)
);
