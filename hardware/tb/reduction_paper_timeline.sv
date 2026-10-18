// SPDX-License-Identifier: SHL-0.51
// Read-only paper observer. Explicit bind; no DUT drivers. Timestamps count
// rising clock edges after reset, not software cycle-CSR measurement windows.
module reduction_paper_timeline #(
  parameter string Kind = "alu",
  parameter int IdWidth = 3
)(
  input logic clk_i,rst_ni,
  input logic lane_zero_i,compute_i,reduction_i,release_i,retire_i,
  input logic pending_i,
  input logic [IdWidth-1:0] issue_id_i,release_id_i,commit_id_i
);
  longint unsigned cycle_q;
  bit enabled;
  initial enabled=$test$plusargs("PAPER_TIMELINE");
  always @(posedge clk_i) begin
    if(!rst_ni) cycle_q=0;
    else begin
      cycle_q++;
      if(enabled && lane_zero_i) begin
        if(compute_i) $display("[PAPER_EVENT] unit=%s cycle=%0d event=compute id=%0d reduction=%0d pending=%0d commit=%0d",Kind,cycle_q,issue_id_i,reduction_i,pending_i,commit_id_i);
        if(release_i) $display("[PAPER_EVENT] unit=%s cycle=%0d event=handoff id=%0d",Kind,cycle_q,release_id_i);
        if(retire_i) $display("[PAPER_EVENT] unit=%s cycle=%0d event=retire id=%0d",Kind,cycle_q,commit_id_i);
      end
    end
  end
endmodule
bind valu reduction_paper_timeline #(.Kind("alu"),.IdWidth($bits(vid_t))) i_paper_timeline (
 .clk_i,.rst_ni,.lane_zero_i(lane_id_i==0),.compute_i(valu_valid),
 .reduction_i(is_reduction(vinsn_issue_q.op)),
 .release_i(alu_state_q==RCE_SEND && rce_partial_ready_i),
 .retire_i(rce_retire_i && uses_rce(vinsn_commit)),
 .pending_i(uses_rce(vinsn_commit)),
 .issue_id_i(vinsn_issue_q.id),.release_id_i(vinsn_issue_q.id),.commit_id_i(vinsn_commit.id)
);
