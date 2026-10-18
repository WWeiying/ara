// SPDX-License-Identifier: SHL-0.51
// TEST ONLY. The sole DUT force is the SLDU completion-valid consumer boundary.
// Raw RCE ready must fall as a consequence; no producer/data/control is forced.
`timescale 1ns/1ps
package reduction_packet_wb_stall_test_pkg;
  import ara_pkg::*;
  logic lane0_packet_active=0, lane0_packet_valid=0, lane0_packet_ready=0;
  vid_t lane0_packet_id='0;
endpackage
module reduction_packet_wb_stall_lane_probe import ara_pkg::*; #(
  parameter int LaneWidth=2
)(
  input logic [LaneWidth-1:0] lane_i,
  input logic active_i, valid_i, ready_i,
  input vid_t id_i
);
  // Only physical lane zero writes these test-owned observation variables.
  always @* if(lane_i==0) begin
    reduction_packet_wb_stall_test_pkg::lane0_packet_active=active_i;
    reduction_packet_wb_stall_test_pkg::lane0_packet_valid=valid_i;
    reduction_packet_wb_stall_test_pkg::lane0_packet_ready=ready_i;
    reduction_packet_wb_stall_test_pkg::lane0_packet_id=id_i;
  end
endmodule
bind vmfpu reduction_packet_wb_stall_lane_probe #(.LaneWidth($bits(lane_id_i))) i_packet_wb_stall_lane_probe (
  .lane_i(lane_id_i),.active_i(mfpu_state_q==EXACT_GLOBAL_TX),
  .valid_i(mfpu_red_valid_o),.ready_i(mfpu_red_ready_i),.id_i(vinsn_processing_q.id)
);
module reduction_packet_wb_stall_consumer import ara_pkg::*; import ara_rce_pkg::*; (
  input logic clk_i,rst_ni,
  input logic command_fire_i, seed_chain_i,
  input vid_t command_id_i,
  input logic result_valid_i,result_ready_i,completion_valid_i,completion_ready_i,
  input rce_exact_result_t result_i
);
  import reduction_packet_wb_stall_test_pkg::*;
  bit enabled,used=0,arm_pending=0,blocked=0,released=0;
  vid_t owner_q;
  logic held_valid=0;
  rce_exact_result_t held_result;
  int profile_cycle=0,hold_cycles=0,blocked_result_cycles=0;
  int young_packets_while_blocked=0,young_commands=0;
  initial enabled=$test$plusargs("PACKET_WB_STALL_TEST");
  always @(posedge clk_i) begin
    if(!rst_ni) begin
      used=0;arm_pending=0;blocked=0;released=0;
      held_valid=0;profile_cycle=0;hold_cycles=0;blocked_result_cycles=0;
      young_packets_while_blocked=0;young_commands=0;
    end else if(enabled) begin
      profile_cycle++;
      if(!used && command_fire_i && seed_chain_i) begin
        if(result_valid_i) $fatal(1,"PACKET_WB_STALL_FAIL stale result before arm");
        used=1;arm_pending=1;owner_q=command_id_i;
        $display("PACKET_WB_STALL_ARM profile_cycle=%0d owner=%0d",profile_cycle,owner_q);
      end
      if(blocked) begin
        hold_cycles++;
        if(result_ready_i || completion_valid_i)
          $fatal(1,"PACKET_WB_STALL_FAIL gated consumer allowed a false handshake");
        if(result_valid_i) begin
          blocked_result_cycles++;
          if(result_i.id!==owner_q) $fatal(1,"PACKET_WB_STALL_FAIL held result owner changed");
          if(held_valid && result_i!==held_result)
            $fatal(1,"PACKET_WB_STALL_FAIL RCE result changed under consumer backpressure");
          held_valid=1;held_result=result_i;
        end else if(held_valid)
          $fatal(1,"PACKET_WB_STALL_FAIL held result valid disappeared");
        if(command_fire_i && command_id_i!=owner_q) young_commands++;
        if(lane0_packet_active && lane0_packet_valid && lane0_packet_id!=owner_q)
          young_packets_while_blocked++;
        if(hold_cycles>3000) $fatal(1,"PACKET_WB_STALL_FAIL no young packet before gate timeout");
      end
    end
  end
  always @(negedge clk_i) if(enabled) begin
    if(!rst_ni) begin
      release ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.rce_completion_valid_o;
    end else if(arm_pending) begin
      if(result_valid_i) $fatal(1,"PACKET_WB_STALL_FAIL result appeared before consumer gate");
      force ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.rce_completion_valid_o=1'b0;
      arm_pending=0;blocked=1;
    end else if(blocked && result_valid_i && lane0_packet_active && lane0_packet_valid && lane0_packet_id!=owner_q) begin
      $display("PACKET_WB_STALL_RELEASE profile_cycle=%0d owner=%0d packet_owner=%0d packet_ready=%0d completion_ready=%0d hold=%0d",profile_cycle,owner_q,lane0_packet_id,lane0_packet_ready,completion_ready_i,hold_cycles);
      release ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.rce_completion_valid_o;
      blocked=0;released=1;
    end
  end
  final if(enabled)
    $display("PACKET_WB_STALL_SUMMARY used=%0d released=%0d hold=%0d blocked_result=%0d young_packet=%0d young_command=%0d",used,released,hold_cycles,blocked_result_cycles,young_packets_while_blocked,young_commands);
endmodule
bind sldu reduction_packet_wb_stall_consumer i_packet_wb_stall_consumer (
  .clk_i,.rst_ni,
  .command_fire_i(rce_exact_cmd_valid_o && rce_exact_cmd_ready_i),
  .seed_chain_i(vinsn_issue_q.vs1==vinsn_issue_q.vd),.command_id_i(rce_exact_cmd_o.id),
  .result_valid_i(rce_exact_result_valid_i),.result_ready_i(rce_exact_result_ready_o),
  .completion_valid_i(rce_completion_valid_o),.completion_ready_i(rce_completion_ready_i),
  .result_i(rce_exact_result_i)
);
