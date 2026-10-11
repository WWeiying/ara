// SPDX-License-Identifier: SHL-0.51
// Read-only cycle landmarks for Load/Slide seed-producer experiments.
// Logs are whole-program events, not additive software-window stall counts.
module reduction_external_seed_dispatch_profile import ara_pkg::*; (
  input logic clk_i, rst_ni, fire_i,
  input vid_t id_i,
  input ara_op_e op_i,
  input logic [NrVInsn-1:0] seed_hazard_i,
  input logic late_i
);
  longint unsigned cycles;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) cycles <= 0;
    else begin
      cycles <= cycles + 1;
      if ($test$plusargs("RCE_EXTERNAL_SEED_PROFILE") && fire_i &&
          (is_load(op_i) || op_i inside {VSLIDEUP,VSLIDEDOWN,VFREDUSUM,VREDSUM}))
        $display("EXTERNAL_SEED dispatch cycle=%0d id=%0d op=%0d hazard=%h late=%0d",
          cycles,id_i,op_i,seed_hazard_i,late_i);
    end
  end
endmodule
bind lane reduction_external_seed_dispatch_profile i_external_seed_dispatch (
  .clk_i, .rst_ni,
  .fire_i(lane_id_i == 0 && pe_req_valid_i && pe_req_ready_o),
  .id_i(pe_req.id), .op_i(pe_req.op), .seed_hazard_i(pe_req.hazard_vs1), .late_i(pe_req.late_seed)
);
module reduction_external_seed_write_profile import ara_pkg::*; (
  input logic clk_i, rst_ni, load_i, slide_i,
  input vid_t load_id_i, slide_id_i,
  input logic [63:0] load_addr_i, slide_addr_i
);
  longint unsigned cycles;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) cycles <= 0;
    else begin
      cycles <= cycles + 1;
      if ($test$plusargs("RCE_EXTERNAL_SEED_PROFILE")) begin
        if (load_i) $display("EXTERNAL_SEED load_write cycle=%0d id=%0d addr=%0d",cycles,load_id_i,load_addr_i);
        if (slide_i) $display("EXTERNAL_SEED slide_write cycle=%0d id=%0d addr=%0d",cycles,slide_id_i,slide_addr_i);
      end
    end
  end
endmodule
bind lane reduction_external_seed_write_profile i_external_seed_write (
  .clk_i, .rst_ni, .load_i(lane_id_i == 0 && i_operand_requester.ldu_result_req && i_operand_requester.ldu_result_gnt),
  .slide_i(lane_id_i == 0 && i_operand_requester.sldu_result_req && i_operand_requester.sldu_result_gnt),
  .load_id_i(i_operand_requester.ldu_result_id), .slide_id_i(i_operand_requester.sldu_result_id),
  .load_addr_i(64'(i_operand_requester.ldu_result_addr)), .slide_addr_i(64'(i_operand_requester.sldu_result_addr))
);

module reduction_external_seed_compute_profile import ara_pkg::*; (
  input logic clk_i, rst_ni, start_i, compute_i,
  input vid_t id_i
);
  longint unsigned cycles;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) cycles <= 0;
    else begin
      cycles <= cycles + 1;
      if ($test$plusargs("RCE_EXTERNAL_SEED_PROFILE")) begin
        if (start_i) $display("EXTERNAL_SEED local_enter cycle=%0d id=%0d",cycles,id_i);
        if (compute_i) $display("EXTERNAL_SEED local_compute cycle=%0d id=%0d",cycles,id_i);
      end
    end
  end
endmodule
// Attribute input handshakes to the issuing instruction; processing may lag.
bind vmfpu reduction_external_seed_compute_profile i_external_seed_compute (
  .clk_i, .rst_ni, .id_i(vinsn_issue_q.id),
  .start_i(lane_id_i == 0 && mfpu_state_q == NO_REDUCTION && mfpu_state_d == INTRA_LANE_REDUCTION),
  .compute_i(lane_id_i == 0 && mfpu_state_q == INTRA_LANE_REDUCTION && vfpu_in_valid && vfpu_in_ready)
);
