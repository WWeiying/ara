// SPDX-License-Identifier: SHL-0.51
// Checks the physical descriptor queue independently of sequencer reservations.
module reduction_sldu_capacity_check #(
  parameter int Depth = 2,
  parameter int CountWidth = 2,
  parameter int PointerWidth = 1
) (
  input logic clk_i, rst_ni,
  input logic [CountWidth-1:0] issue_count, commit_count,
  input logic [PointerWidth-1:0] accept_pointer, issue_pointer, commit_pointer
);
  longint unsigned above_two;
  always @(posedge clk_i)
    if (!rst_ni) above_two = 0;
    else if (commit_count > 2) above_two++;
  a_capacity: assert property (@(posedge clk_i) disable iff (!rst_ni)
    commit_count <= Depth && issue_count <= commit_count);
  a_pointers: assert property (@(posedge clk_i) disable iff (!rst_ni)
    accept_pointer < Depth && issue_pointer < Depth && commit_pointer < Depth);
  final if ($test$plusargs("RCE_STALL_PROFILE"))
    $display("SLDU_CAPACITY depth=%0d above_two=%0d", Depth, above_two);
endmodule

bind sldu reduction_sldu_capacity_check #(
  .Depth(VInsnQueueDepth),
  .CountWidth($bits(vinsn_queue_q.commit_cnt)),
  .PointerWidth($bits(vinsn_queue_q.commit_pnt))
) i_descriptor_capacity_check (
  .clk_i, .rst_ni,
  .issue_count(vinsn_queue_q.issue_cnt), .commit_count(vinsn_queue_q.commit_cnt),
  .accept_pointer(vinsn_queue_q.accept_pnt), .issue_pointer(vinsn_queue_q.issue_pnt),
  .commit_pointer(vinsn_queue_q.commit_pnt)
);
