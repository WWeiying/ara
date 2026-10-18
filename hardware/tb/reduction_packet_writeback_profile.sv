// SPDX-License-Identifier: SHL-0.51
// Read-only observers for independent reduction transport and RCE VRF writes.
// +PACKET_WB_PROFILE enables event/coverage output; checks never drive the DUT.
module reduction_packet_writeback_profile import ara_pkg::*; #(
  parameter string Kind = "mfpu",
  parameter int LaneWidth = 2
)(
  input logic clk_i, rst_ni,
  input logic [LaneWidth-1:0] lane_i,
  input logic packet_active_i, packet_valid_i, packet_ready_i, packet_header_i, packet_bypass_i,
  input elen_t packet_data_i, expected_packet_data_i,
  input vid_t packet_id_i,
  input logic wb_select_i, wb_req_i, wb_gnt_i, expected_wb_req_i,
  input elen_t wb_data_i, expected_wb_data_i,
  input vid_t wb_id_i, expected_wb_id_i,
  input vreg_version_t wb_version_i, expected_wb_version_i,
  input logic normal_select_i, expected_normal_req_i,
  input elen_t expected_normal_data_i,
  input vid_t expected_normal_id_i,
  input vreg_version_t expected_normal_version_i
);
  bit enabled;
  longint unsigned cycles=0, packet_valid_cycles=0, packet_fires=0, headers=0;
  longint unsigned wb_cycles=0, wb_fires=0, stalled_packets=0;
  longint unsigned overlap_cycles=0, overlap_packet_fires=0, overlap_both_fires=0;
  longint unsigned different_owners=0, distinct_data_overlap=0, stall_wb_overlap=0;
  longint unsigned bypass_fires=0;
  longint unsigned normal_drain_fires=0,normal_packet_both_fires=0;
  longint unsigned normal_packet_cycles=0,normal_distinct_data=0;
  logic stalled_q=0;
  elen_t held_data_q;
  vid_t held_id_q;
  initial enabled=$test$plusargs("PACKET_WB_PROFILE");
  always @(posedge clk_i) begin
    if(!rst_ni) begin
      cycles=0;packet_valid_cycles=0;packet_fires=0;headers=0;
      wb_cycles=0;wb_fires=0;stalled_packets=0;
      overlap_cycles=0;overlap_packet_fires=0;overlap_both_fires=0;
      different_owners=0;distinct_data_overlap=0;stall_wb_overlap=0;
      bypass_fires=0;
      normal_drain_fires=0;normal_packet_both_fires=0;
      normal_packet_cycles=0;normal_distinct_data=0;
      stalled_q=0;
    end else begin
      cycles++;
      if(stalled_q && (!packet_active_i || !packet_valid_i ||
                      packet_data_i!==held_data_q || packet_id_i!==held_id_q))
        $fatal(1,"PACKET_WB_PROFILE_FAIL kind=%s lane=%0d packet changed under backpressure",Kind,lane_i);
      stalled_q=packet_active_i && packet_valid_i && !packet_ready_i;
      if(stalled_q) begin held_data_q=packet_data_i;held_id_q=packet_id_i;end
      if(packet_active_i && packet_valid_i) begin
        packet_valid_cycles++;
        if(packet_data_i!==expected_packet_data_i)
          $fatal(1,"PACKET_WB_PROFILE_FAIL kind=%s lane=%0d packet owner=%0d data=%h expected=%h",Kind,lane_i,packet_id_i,packet_data_i,expected_packet_data_i);
        if(packet_header_i && packet_data_i[4:0]!==5'(packet_id_i))
          $fatal(1,"PACKET_WB_PROFILE_FAIL kind=%s lane=%0d header owner mismatch",Kind,lane_i);
        if(packet_ready_i) begin
          packet_fires++;if(packet_header_i) headers++;
          if(packet_bypass_i) bypass_fires++;
        end
        else stalled_packets++;
      end
      if(wb_select_i) begin
        wb_cycles++;
        if(wb_data_i!==expected_wb_data_i || wb_id_i!==expected_wb_id_i ||
           wb_version_i!==expected_wb_version_i || wb_req_i!==expected_wb_req_i)
          $fatal(1,"PACKET_WB_PROFILE_FAIL kind=%s lane=%0d RCE writeback data/tag/request mismatch id=%0d expected_id=%0d",Kind,lane_i,wb_id_i,expected_wb_id_i);
        if(wb_req_i && wb_gnt_i) wb_fires++;
      end
      if(normal_select_i && wb_req_i && wb_gnt_i) normal_drain_fires++;
      if(normal_select_i && packet_active_i && packet_valid_i) begin
        normal_packet_cycles++;
        if(wb_data_i!==expected_normal_data_i || wb_id_i!==expected_normal_id_i ||
           wb_version_i!==expected_normal_version_i || wb_req_i!==expected_normal_req_i)
          $fatal(1,"PACKET_WB_PROFILE_FAIL kind=%s lane=%0d ordinary drain data/tag/request mismatch",Kind,lane_i);
        if(packet_id_i===expected_normal_id_i)
          $fatal(1,"PACKET_WB_PROFILE_FAIL kind=%s lane=%0d packet and ordinary drain share owner",Kind,lane_i);
        if(packet_data_i!==wb_data_i) normal_distinct_data++;
        if(packet_ready_i && wb_req_i && wb_gnt_i) begin
          normal_packet_both_fires++;
          if(enabled && normal_packet_both_fires<=8)
            $display("PACKET_NORMAL_WB_PROFILE_EVENT kind=%s lane=%0d cycle=%0d packet_id=%0d normal_id=%0d packet=%h normal=%h",Kind,lane_i,cycles,packet_id_i,wb_id_i,packet_data_i,wb_data_i);
        end
      end
      if(packet_active_i && packet_valid_i && wb_select_i) begin
        overlap_cycles++;
        if(packet_id_i===expected_wb_id_i)
          $fatal(1,"PACKET_WB_PROFILE_FAIL kind=%s lane=%0d packet and older writeback share owner=%0d",Kind,lane_i,packet_id_i);
        different_owners++;
        if(packet_data_i!==wb_data_i) distinct_data_overlap++;
        if(!packet_ready_i) stall_wb_overlap++;
        if(packet_ready_i) begin
          overlap_packet_fires++;
          if(wb_req_i && wb_gnt_i) overlap_both_fires++;
          if(enabled && overlap_packet_fires<=8)
            $display("PACKET_WB_PROFILE_EVENT kind=%s lane=%0d cycle=%0d packet_id=%0d wb_id=%0d packet=%h wb=%h wb_fire=%0d",Kind,lane_i,cycles,packet_id_i,wb_id_i,packet_data_i,wb_data_i,wb_req_i&&wb_gnt_i);
        end
      end
    end
  end
  final if(enabled)
    $display("PACKET_WB_PROFILE_SUMMARY kind=%s lane=%0d profile_cycles=%0d packet_valid=%0d packet_fire=%0d headers=%0d packet_stall=%0d wb=%0d wb_fire=%0d overlap=%0d overlap_packet_fire=%0d overlap_both_fire=%0d different_owner=%0d distinct_data=%0d stall_wb_overlap=%0d bypass_fire=%0d normal_drain_fire=%0d normal_packet_both_fire=%0d normal_packet_overlap=%0d normal_distinct_data=%0d",Kind,lane_i,cycles,packet_valid_cycles,packet_fires,headers,stalled_packets,wb_cycles,wb_fires,overlap_cycles,overlap_packet_fires,overlap_both_fires,different_owners,distinct_data_overlap,stall_wb_overlap,bypass_fires,normal_drain_fires,normal_packet_both_fires,normal_packet_cycles,normal_distinct_data);
endmodule

bind valu reduction_packet_writeback_profile #(
  .Kind("alu"),.LaneWidth($bits(lane_id_i))
) i_packet_writeback_profile (
  .clk_i,.rst_ni,.lane_i(lane_id_i),
  .packet_active_i(alu_red_valid_o),.packet_valid_i(alu_red_valid_o),
  .packet_ready_i(alu_red_ready_i),.packet_header_i(1'b0),
  .packet_bypass_i(1'b0),
  .packet_data_i(alu_red_data_o),
  .expected_packet_data_i(result_queue_q[result_queue_write_pnt_q].wdata),
  .packet_id_i(vinsn_issue_q.id),
  .wb_select_i(rce_writeback),.wb_req_i(alu_result_req_o),.wb_gnt_i(alu_result_gnt_i),
  .expected_wb_req_i(rce_result_i.write_enable),
  .wb_data_i(alu_result_wdata_o),.expected_wb_data_i(rce_result_i.data),
  .wb_id_i(alu_result_id_o),.expected_wb_id_i(rce_result_i.id),
  .wb_version_i(alu_result_version_o),.expected_wb_version_i(rce_result_i.version),
  .normal_select_i(1'b0),.expected_normal_req_i(1'b0),.expected_normal_data_i('0),
  .expected_normal_id_i('0),.expected_normal_version_i('0)
);
`ifdef ARA_RED_EXACT_GLOBAL_4LANE
bind vmfpu reduction_packet_writeback_profile #(
  .Kind("mfpu_exact"),.LaneWidth($bits(lane_id_i))
) i_packet_writeback_profile (
  .clk_i,.rst_ni,.lane_i(lane_id_i),
  .packet_active_i(mfpu_state_q==EXACT_GLOBAL_TX || exact_header_bypass),.packet_valid_i(mfpu_red_valid_o),
  .packet_ready_i(mfpu_red_ready_i),.packet_header_i(exact_packet_beat==0),
  .packet_bypass_i(exact_header_bypass),
  .packet_data_i(mfpu_red_data_o),.expected_packet_data_i(exact_packet_word),
  .packet_id_i(vinsn_processing_q.id),
  .wb_select_i(rce_writeback),.wb_req_i(mfpu_result_req_o),.wb_gnt_i(mfpu_result_gnt_i),
  .expected_wb_req_i(rce_result_i.write_enable),
  .wb_data_i(mfpu_result_wdata_o),.expected_wb_data_i(rce_result_i.data),
  .wb_id_i(mfpu_result_id_o),.expected_wb_id_i(rce_result_i.id),
  .wb_version_i(mfpu_result_version_o),.expected_wb_version_i(rce_result_i.version),
  .normal_select_i(rce_ordinary_drain && !rce_writeback),
  .expected_normal_req_i(result_queue_valid_q[result_queue_read_pnt_q] && !result_queue_q[result_queue_read_pnt_q].mask),
  .expected_normal_data_i(result_queue_q[result_queue_read_pnt_q].wdata),
  .expected_normal_id_i(result_queue_q[result_queue_read_pnt_q].id),
  .expected_normal_version_i(result_queue_q[result_queue_read_pnt_q].version)
);
`endif
