// SPDX-License-Identifier: SHL-0.51
// Actual exact accumulator input acceptance and central receive landmarks.
// Observe issuing ownership; normal FPU input handshakes do not cover this path.
module reduction_exact_input_profile import ara_pkg::*; (
  input logic clk_i,rst_ni,fire_i,start_i,
  input vid_t id_i
);
  longint unsigned cycles;
  always_ff @(posedge clk_i) begin
    if(!rst_ni) cycles<=0;
    else begin
      cycles<=cycles+1;
      if($test$plusargs("RCE_EXACT_SEED_PROFILE") && fire_i)
        $display("EXACT_SEED local_compute cycle=%0d id=%0d start=%0d",cycles,id_i,start_i);
    end
  end
endmodule
bind vmfpu reduction_exact_input_profile i_exact_seed_input_profile (
  .clk_i,.rst_ni,.id_i(vinsn_issue_q.id),
  .fire_i(lane_id_i==0 && exact_sum_in_valid && exact_sum_in_ready),
  .start_i(exact_sum_start)
);
module reduction_exact_receive_profile import ara_pkg::*; import ara_rce_pkg::*; (
  input logic clk_i,rst_ni,complete_i,
  input rce_exact_events_t events_i,
  input vid_t id_i,
  input logic seed_ready_i
);
  longint unsigned cycles;
  always_ff @(posedge clk_i) begin
    if(!rst_ni)cycles<=0;
    else begin
      cycles<=cycles+1;
      if($test$plusargs("RCE_EXACT_SEED_PROFILE"))begin
        if(events_i.header_fire)$display("EXACT_SEED header cycle=%0d id=%0d seed_ready=%0d",cycles,id_i,seed_ready_i);
        if(events_i.limb_fire)$display("EXACT_SEED limb cycle=%0d id=%0d",cycles,id_i);
        if(events_i.seed_bind)$display("EXACT_SEED seed_bind cycle=%0d id=%0d",cycles,id_i);
        if(complete_i)$display("EXACT_SEED local_complete cycle=%0d id=%0d",cycles,id_i);
      end
    end
  end
endmodule
// The SLDU retains this descriptor until exact_local_complete_o.
bind reduction_completion_engine reduction_exact_receive_profile i_exact_seed_receive_profile (
  .clk_i,.rst_ni,.id_i(exact_cmd_i.id),.events_i(exact_events_o),
  .complete_i(exact_local_complete_o),.seed_ready_i(exact_seed_ready_i)
);
