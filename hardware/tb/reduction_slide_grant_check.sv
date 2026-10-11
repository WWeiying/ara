// SPDX-License-Identifier: SHL-0.51
// A Slide write may outlive its source-stream ownership. Its acknowledgement
// must come from the VRF write receiver, never a younger reduction's token port.
module reduction_slide_grant_check (
  input logic clk_i, rst_ni,
  input logic [63:0] lane_i,
  input logic write_req, returned_grant, vrf_accept,
  input logic source_switched, token_ready
);
  longint unsigned handover_writes, token_would_ack, invalid_acks;
  always @(posedge clk_i)
    if (!rst_ni) begin
      handover_writes = 0;
      token_would_ack = 0;
      invalid_acks = 0;
    end else begin
      if (write_req && source_switched) handover_writes++;
      if (write_req && source_switched && token_ready && !vrf_accept) token_would_ack++;
      if (write_req && returned_grant && !vrf_accept) invalid_acks++;
    end
  a_slide_write_receiver: assert property (@(posedge clk_i) disable iff (!rst_ni)
    write_req && returned_grant |-> vrf_accept)
    else $error("Slide write acknowledged without VRF acceptance, lane=%0d", lane_i);
  final if ($test$plusargs("RCE_STALL_PROFILE"))
    $display("SLIDE_GRANT lane=%0d handover=%0d token_would_ack=%0d invalid=%0d",
             lane_i, handover_writes, token_would_ack, invalid_acks);
endmodule

bind lane reduction_slide_grant_check i_slide_grant_check (
  .clk_i, .rst_ni, .lane_i(64'(lane_id_i)),
  .write_req(sldu_result_req_i), .returned_grant(sldu_result_gnt_o),
  .vrf_accept(sldu_result_gnt_opqueues),
  .source_switched(sldu_addrgen_sel_q != SLDU_SEL),
  .token_ready(sldu_addrgen_sel_q == ALU_RED_SEL ? sldu_alu_ready : sldu_mfpu_ready)
);
