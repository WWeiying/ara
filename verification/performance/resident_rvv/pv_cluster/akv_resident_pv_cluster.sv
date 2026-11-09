// SPDX-License-Identifier: Apache-2.0
// Experimental parent. final_ack_i is NOT a production native-LDU connection.
module akv_resident_pv_cluster (
  input logic clk_i, rst_ni,
  input logic start_valid_i,
  output logic start_ready_o,
  input logic [3:0] start_active_i,
  input logic [5:0] cmd_elements_i,
  input logic cmd_two_heads_i,
  input logic [6:0] cmd_tokens_i,
  input logic [2:0] cmd_rm_i,
  input logic abort_i,
  output logic abort_rejected_o, busy_o,
  output logic [3:0] active_o,
  output logic commit_authorized_o, fatal_error_o,
  input logic [3:0] seed_valid_i,
  output logic [3:0] seed_ready_o,
  input logic [3:0][63:0] seed_data_i,
  input logic stream_valid_i,
  output logic stream_ready_o,
  input logic stream_is_value_i,
  input logic [3:0][63:0] stream_data_i,
  output logic [3:0] fpu_valid_o,
  input logic [3:0] fpu_ready_i,
  output logic [3:0][2:0][63:0] fpu_operands_o,
  output logic [3:0][3:0] fpu_tag_o, fpu_mask_o,
  output logic [3:0][2:0] fpu_rm_o,
  input logic [3:0] fpu_result_valid_i,
  output logic [3:0] fpu_result_ready_o,
  input logic [3:0][63:0] fpu_result_i,
  input logic [3:0][3:0] fpu_result_tag_i,
  input logic [3:0][4:0] fpu_result_flags_i,
  output logic [3:0] result_valid_o,
  input logic [3:0] result_ready_i,
  output logic [3:0][63:0] result_data_o,
  output logic [3:0][3:0] result_slot_o,
  output logic [3:0][7:0] result_be_o,
  input logic [3:0] final_ack_i,
  output logic [3:0] ack_rejected_o,
  output logic [3:0][4:0] outstanding_o,
  output logic done_valid_o,
  input logic done_ready_i,
  output logic done_error_o,
  output logic [4:0] done_flags_o
);
  logic launch, group_ready, private_enable, fanout_ready, fanout_empty;
  logic group_done, group_done_ready, group_error, group_fatal, count_fault_q;
  logic [4:0] group_flags;
  logic [3:0] lane_cmd_ready, lane_cmd_valid, lane_abort, lane_seed_ready;
  logic [3:0] lane_stream_ready, payload_valid, payload_ready;
  logic payload_kind;
  logic [3:0][63:0] payload_data;
  logic [3:0] lane_result_valid, lane_result_ready, lane_done, lane_done_ready;
  logic [3:0] lane_error, accepted, ack_owned;
  logic [3:0][63:0] lane_data;
  logic [3:0][3:0] lane_slot;
  logic [3:0][7:0] lane_be;
  logic [3:0][4:0] lane_flags, outstanding_q;
  logic [3:0] ingress_word_q, ingress_words_q;
  logic [6:0] ingress_token_q, ingress_tokens_q;
  logic ingress_enable;

  // Do not forward external abort directly to lanes: it would suppress their
  // command ready on abort+start, leaving the group waiting for unlaunched lanes.
  assign start_ready_o = group_ready && !fatal_error_o &&
                        ((lane_cmd_ready & start_active_i) == start_active_i);
  assign launch = start_valid_i && start_ready_o;
  assign lane_cmd_valid = {4{launch}} & start_active_i;
  assign private_enable = busy_o && !commit_authorized_o && !group_done &&
                          !(|lane_abort) && !fatal_error_o;
  assign ingress_enable = private_enable && (|active_o) &&
                          ingress_token_q < ingress_tokens_q;
  assign stream_ready_o = ingress_enable && fanout_ready;
  assign seed_ready_o = lane_seed_ready & active_o & {4{private_enable}};
  assign payload_ready = lane_stream_ready & active_o & {4{private_enable}};

  resident_payload_fanout i_payload (
    .clk_i, .rst_ni, .cancel_i(!private_enable),
    .valid_i(stream_valid_i && ingress_enable),
    .ready_o(fanout_ready), .active_i(active_o),
    .is_value_i(stream_is_value_i), .data_i(stream_data_i),
    .valid_o(payload_valid), .ready_i(payload_ready),
    .is_value_o(payload_kind), .data_o(payload_data), .empty_o(fanout_empty)
  );

  // One coefficient plus ceil(elements/4) values per token, shared by heads.
  // Bound admission itself, not just delivery: never accept then discard a tail.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      ingress_word_q <= '0; ingress_token_q <= '0;
      ingress_words_q <= '0; ingress_tokens_q <= '0;
    end else if (launch) begin
      ingress_word_q <= '0; ingress_token_q <= '0;
      ingress_words_q <= (cmd_elements_i + 6'd3) >> 2;
      ingress_tokens_q <= cmd_tokens_i;
    end else if (stream_valid_i && stream_ready_o) begin
      if (ingress_word_q == ingress_words_q) begin
        ingress_word_q <= '0;
        ingress_token_q <= ingress_token_q + 1'b1;
      end else ingress_word_q <= ingress_word_q + 1'b1;
    end
  end

  for (genvar l = 0; l < 4; l++) begin : gen_lane
    akv_resident_pv_lane i_lane (
      .clk_i, .rst_ni, .abort_i(lane_abort[l]),
      .cmd_valid_i(lane_cmd_valid[l]), .cmd_ready_o(lane_cmd_ready[l]),
      .cmd_elements_i, .cmd_two_heads_i, .cmd_tokens_i, .cmd_rm_i,
      .seed_valid_i(seed_valid_i[l] && private_enable && active_o[l]),
      .seed_ready_o(lane_seed_ready[l]), .seed_data_i(seed_data_i[l]),
      .stream_valid_i(payload_valid[l] && private_enable && active_o[l]),
      .stream_ready_o(lane_stream_ready[l]),
      .stream_is_value_i(payload_kind), .stream_data_i(payload_data[l]),
      .fpu_valid_o(fpu_valid_o[l]), .fpu_ready_i(fpu_ready_i[l]),
      .fpu_operands_o(fpu_operands_o[l]), .fpu_tag_o(fpu_tag_o[l]),
      .fpu_mask_o(fpu_mask_o[l]), .fpu_rm_o(fpu_rm_o[l]),
      .fpu_result_valid_i(fpu_result_valid_i[l]),
      .fpu_result_ready_o(fpu_result_ready_o[l]), .fpu_result_i(fpu_result_i[l]),
      .fpu_result_tag_i(fpu_result_tag_i[l]), .fpu_result_flags_i(fpu_result_flags_i[l]),
      .result_valid_o(lane_result_valid[l]), .result_ready_i(lane_result_ready[l]),
      .result_data_o(lane_data[l]), .result_slot_o(lane_slot[l]),
      .result_be_o(lane_be[l]), .done_valid_o(lane_done[l]),
      .done_ready_i(lane_done_ready[l]), .done_error_o(lane_error[l]),
      .done_flags_o(lane_flags[l]), .busy_o()
    );
  end

  akv_resident_pv_group i_group (
    .clk_i, .rst_ni, .start_valid_i(launch), .start_ready_o(group_ready),
    .start_active_i, .abort_i, .abort_rejected_o, .busy_o, .active_o,
    .commit_authorized_o, .fatal_error_o(group_fatal), .lane_abort_o(lane_abort),
    .lane_result_valid_i(lane_result_valid), .lane_result_ready_o(lane_result_ready),
    .lane_result_data_i(lane_data), .lane_result_slot_i(lane_slot), .lane_result_be_i(lane_be),
    .result_valid_o, .result_ready_i, .result_data_o, .result_slot_o, .result_be_o,
    .lane_done_valid_i(lane_done), .lane_done_ready_o(lane_done_ready),
    .lane_done_error_i(lane_error), .lane_done_flags_i(lane_flags),
    .done_valid_o(group_done), .done_ready_i(group_done_ready),
    .done_error_o(group_error), .done_flags_o(group_flags)
  );

  // Acceptance advances the lane. Only a separate final acknowledgment retires
  // the debt. Keep counting after lane Done/Idle; the group stays held Terminal.
  assign accepted = result_valid_o & result_ready_i;
  assign outstanding_o = outstanding_q;
  for (genvar l = 0; l < 4; l++) begin : gen_ack
    assign ack_owned[l] = busy_o && active_o[l] &&
                         (outstanding_q[l] != 0 || accepted[l]);
    assign ack_rejected_o[l] = final_ack_i[l] && !ack_owned[l];
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) outstanding_q[l] <= '0;
      else if (launch) outstanding_q[l] <= '0;
      else case ({accepted[l], final_ack_i[l] && ack_owned[l]})
        2'b10: if (outstanding_q[l] < 16) outstanding_q[l] <= outstanding_q[l] + 1'b1;
        2'b01: outstanding_q[l] <= outstanding_q[l] - 1'b1;
        default: ;
      endcase
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) count_fault_q <= 1'b0;
    else for (int l = 0; l < 4; l++)
      if (accepted[l] && outstanding_q[l] == 16 && !final_ack_i[l]) count_fault_q <= 1'b1;
  end
  assign fatal_error_o = group_fatal || count_fault_q;
  assign done_valid_o = group_done && outstanding_q == '0 && !fatal_error_o;
  assign group_done_ready = done_ready_i && done_valid_o;
  // Zero outside terminal-valid, including the final-ack drain interval.
  assign done_error_o = done_valid_o && group_error;
  assign done_flags_o = done_valid_o ? group_flags : '0;
endmodule
