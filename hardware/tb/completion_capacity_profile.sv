// SPDX-License-Identifier: SHL-0.51
// Read-only, whole-program demand trace. Not an area/Fmax estimate or a
// simulation of a shared RCE/ordered backend. No design signals are driven.
module completion_capacity_profile #(
  parameter int NrLanes=4
)(
  input logic clk_i,rst_ni,
  input logic [NrLanes-1:0] ordered_valid_i,ordered_ready_i,
  input logic rce_valid_i,rce_ready_i,rce_wait_i
);
  bit enabled;
  longint unsigned cycle,ordered_requests,ordered_fires,rce_requests,rce_fires;
  longint unsigned simultaneous_request_cycles,ordered_during_rce_wait;
  initial enabled=$test$plusargs("AREA_COMPLETION_PROFILE");
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      cycle=0;ordered_requests=0;ordered_fires=0;rce_requests=0;rce_fires=0;
      simultaneous_request_cycles=0;ordered_during_rce_wait=0;
    end else begin
      cycle++;
      if (enabled) begin
        ordered_requests+=$countones(ordered_valid_i);
        ordered_fires+=$countones(ordered_valid_i&ordered_ready_i);
        rce_requests+=rce_valid_i;rce_fires+=rce_valid_i&&rce_ready_i;
        simultaneous_request_cycles+=(|ordered_valid_i)&&rce_valid_i;
        ordered_during_rce_wait+=(|ordered_valid_i)&&rce_wait_i;
        if ((|ordered_valid_i)||rce_valid_i)
          $display("[AREA_COMPLETION] cycle=%0d ordered=%h fired=%h rce=%0d rce_fire=%0d rce_wait=%0d",
            cycle,ordered_valid_i,ordered_valid_i&ordered_ready_i,
            rce_valid_i,rce_valid_i&&rce_ready_i,rce_wait_i);
      end
    end
  end
  final if (enabled)
    $display("[AREA_COMPLETION_SUMMARY] ordered_requests=%0d ordered_fires=%0d rce_requests=%0d rce_fires=%0d simultaneous_request_cycles=%0d ordered_during_rce_wait=%0d",
      ordered_requests,ordered_fires,rce_requests,rce_fires,
      simultaneous_request_cycles,ordered_during_rce_wait);
endmodule

`ifdef ARA_RED_SHARED_ORDERED_ADD
`ifdef ARA_RED_RCE_FP64_SUM
bind ara completion_capacity_profile #(.NrLanes(NrLanes)) i_completion_capacity_profile (
  .clk_i,.rst_ni,.ordered_valid_i(ordered_add_valid[NrLanes-1:0]),.ordered_ready_i(ordered_add_ready[NrLanes-1:0]),
  .rce_valid_i(gen_rce.i_rce.fp_in_valid),.rce_ready_i(gen_rce.i_rce.fp_in_ready),
  .rce_wait_i(gen_rce.i_rce.state_q==gen_rce.i_rce.FP_WAIT));
`endif
`endif
