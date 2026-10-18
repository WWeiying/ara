// SPDX-License-Identifier: SHL-0.51
// TEST ONLY: mask the operand requester input net before the first ordinary
// result request, leaving the producer output asserted and observable, then release before the younger exact packet's first sampling edge.
// No producer data, tags, arithmetic, instruction state or grant is forced.
`timescale 1ns/1ps
module reduction_normal_packet_stall_test import ara_pkg::*; #(
  parameter int LaneWidth=2
)(
  input logic clk_i,rst_ni,
  input logic [LaneWidth-1:0] lane_i,
  input logic accepted_i,
  input vid_t accepted_id_i,
  input logic req_i,consumer_req_i,gnt_i,rce_wb_i,normal_drain_i,
  input elen_t wb_data_i,
  input vid_t wb_id_i,
  input vreg_version_t wb_version_i,
  input logic head_valid_i,
  input elen_t head_data_i,
  input vid_t head_id_i,
  input vreg_version_t head_version_i,
  input logic packet_valid_i,packet_ready_i,
  input vid_t packet_id_i
);
  bit enabled,used=0,arm_pending=0,blocked=0,released=0,held_valid=0;
  vid_t owner_q,held_id;
  vreg_version_t held_version;
  elen_t held_data;
  int profile_cycle=0,hold_cycles=0,held_queue_cycles=0;
  initial enabled=$test$plusargs("PACKET_NORMAL_WB_STALL_TEST");
  always @(posedge clk_i) if(lane_i==0) begin
    if(!rst_ni) begin
      used=0;arm_pending=0;blocked=0;released=0;held_valid=0;
      profile_cycle=0;hold_cycles=0;held_queue_cycles=0;
    end else if(enabled) begin
      profile_cycle++;
      if(!used && accepted_i) begin
        if(req_i || gnt_i) $fatal(1,"PACKET_NORMAL_STALL_FAIL first output preceded ordinary consumer gate");
        used=1;arm_pending=1;owner_q=accepted_id_i;
        $display("PACKET_NORMAL_STALL_ARM profile_cycle=%0d owner=%0d",profile_cycle,owner_q);
      end
      if(blocked) begin
        hold_cycles++;
        if(consumer_req_i || gnt_i || rce_wb_i)
          $fatal(1,"PACKET_NORMAL_STALL_FAIL ordinary request gate allowed false consumer handshake");
        if(packet_valid_i)
          $fatal(1,"PACKET_NORMAL_STALL_FAIL missed first packet sampling boundary");
        if(head_valid_i) begin
          held_queue_cycles++;
          if(req_i!==1'b1)
            $fatal(1,"PACKET_NORMAL_STALL_FAIL consumer port force changed producer request (alias), producer=%b consumer=%b",req_i,consumer_req_i);
          if(head_id_i!==owner_q) $fatal(1,"PACKET_NORMAL_STALL_FAIL wrong ordinary owner held");
          if(held_valid && {head_data_i,head_id_i,head_version_i}!=={held_data,held_id,held_version})
            $fatal(1,"PACKET_NORMAL_STALL_FAIL queue data/tag changed without a grant");
          held_valid=1;held_data=head_data_i;held_id=head_id_i;held_version=head_version_i;
        end else if(held_valid)
          $fatal(1,"PACKET_NORMAL_STALL_FAIL queued ordinary result disappeared");
        if(hold_cycles>3000) $fatal(1,"PACKET_NORMAL_STALL_FAIL young exact packet did not arrive");
      end
    end
  end
  always @(negedge clk_i) if(enabled && lane_i==0) begin
    if(!rst_ni)
      release ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.mfpu_result_req_i;
    else if(arm_pending) begin
      if(req_i || gnt_i) $fatal(1,"PACKET_NORMAL_STALL_FAIL output appeared before request gate");
      force ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.mfpu_result_req_i=1'b0;
      blocked=1;arm_pending=0;
    end else if(blocked && packet_valid_i && packet_id_i!=owner_q) begin
      if(req_i!==1'b1 || consumer_req_i!==1'b0) $fatal(1,"PACKET_NORMAL_STALL_FAIL producer/consumer separation not established");
      if(!head_valid_i) $fatal(1,"PACKET_NORMAL_STALL_FAIL no queued result at packet release");
      $display("PACKET_NORMAL_STALL_RELEASE profile_cycle=%0d normal_owner=%0d packet_owner=%0d packet_ready=%0d hold=%0d queue_hold=%0d producer_req=%b consumer_req=%b grant=%b",profile_cycle,owner_q,packet_id_i,packet_ready_i,hold_cycles,held_queue_cycles,req_i,consumer_req_i,gnt_i);
      release ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.mfpu_result_req_i;
      blocked=0;released=1;
      #0.1;
      if(req_i!==1'b1 || consumer_req_i!==1'b1) $fatal(1,"PACKET_NORMAL_STALL_FAIL consumer net did not restore immediately");
      $display("PACKET_NORMAL_STALL_AFTER_RELEASE producer_req=%b consumer_req=%b grant=%b drain=%b data=%h expected=%h id=%0d expected_id=%0d version=%0d expected_version=%0d",req_i,consumer_req_i,gnt_i,normal_drain_i,wb_data_i,head_data_i,wb_id_i,head_id_i,wb_version_i,head_version_i);
    end
  end
  final if(enabled && lane_i==0)
    $display("PACKET_NORMAL_STALL_SUMMARY used=%0d released=%0d hold=%0d queue_hold=%0d",used,released,hold_cycles,held_queue_cycles);
endmodule
bind vmfpu reduction_normal_packet_stall_test #(.LaneWidth($bits(lane_id_i))) i_normal_packet_stall_test (
  .clk_i,.rst_ni,.lane_i(lane_id_i),
  .accepted_i(vfpu_in_valid && vfpu_in_ready && vfpu_exec_vinsn.op==VFADD && vfpu_exec_vinsn.vd==12),
  .accepted_id_i(vfpu_exec_vinsn.id),
  .req_i(mfpu_result_req_o),
  .consumer_req_i(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester.mfpu_result_req_i),.gnt_i(mfpu_result_gnt_i),.rce_wb_i(rce_writeback),
  .normal_drain_i(rce_ordinary_drain),.wb_data_i(mfpu_result_wdata_o),
  .wb_id_i(mfpu_result_id_o),.wb_version_i(mfpu_result_version_o),
  .head_valid_i(result_queue_valid_q[result_queue_read_pnt_q]),
  .head_data_i(result_queue_q[result_queue_read_pnt_q].wdata),
  .head_id_i(result_queue_q[result_queue_read_pnt_q].id),
  .head_version_i(result_queue_q[result_queue_read_pnt_q].version),
  .packet_valid_i((mfpu_state_q==EXACT_GLOBAL_TX || exact_header_bypass) && mfpu_red_valid_o),
  .packet_ready_i(mfpu_red_ready_i),.packet_id_i(vinsn_processing_q.id)
);
