// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
// Full adapter write cone with registered inputs and observable SRAM windows.
// This is a local before/after comparison, not an integrated SoC timing result.
module qbs_adapter_pipeline_timing import qbs_pkg::*; (
  input logic clk_i, rst_ni,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input qbs_activation_layout_e activation_layout_i,
  input logic [2:0] rows_i,
  input logic [3:0] m_i,
  input logic clear_weight_i, clear_activation_i,
  input logic weight_valid_i, activation_valid_i,
  input logic weight_group_i,
  input logic [1:0] weight_row_i, activation_context_i,
  input logic [9:0] weight_offset_i,
  input logic [11:0] activation_offset_i,
  input logic [127:0] weight_data_i, activation_data_i,
  input logic [15:0] weight_strb_i, activation_strb_i,
  input logic weight_read_i, activation_read_i,
  input logic [7:0] read_k_i,
  output logic weight_ready_o, activation_ready_o,
  output logic all_weight_complete_o, all_activation_complete_o,
  output logic [31:0] weight_bytes_o, activation_bytes_o,
  output logic [255:0] weight_window_o [4][2], activation_window_o [4],
  output logic [7:0] weight_side_o [4][20], activation_side_o [4][36]
);
  typedef struct packed {
    qbs_weight_profile_e weight_profile;
    qbs_activation_profile_e activation_profile;
    qbs_activation_layout_e activation_layout;
    logic [2:0] rows;
    logic [3:0] m;
    logic clear_weight, clear_activation;
    logic weight_valid, activation_valid;
    logic weight_group;
    logic [1:0] weight_row, activation_context;
    logic [9:0] weight_offset;
    logic [11:0] activation_offset;
    logic [127:0] weight_data, activation_data;
    logic [15:0] weight_strb, activation_strb;
    logic weight_read, activation_read;
    logic [7:0] read_k;
  } inputs_t;
  inputs_t inputs_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) inputs_q <= '0;
    else inputs_q <= '{
      weight_profile: weight_profile_i, activation_profile: activation_profile_i,
      activation_layout: activation_layout_i, rows: rows_i, m: m_i,
      clear_weight: clear_weight_i, clear_activation: clear_activation_i,
      weight_valid: weight_valid_i, activation_valid: activation_valid_i,
      weight_group: weight_group_i, weight_row: weight_row_i,
      activation_context: activation_context_i, weight_offset: weight_offset_i,
      activation_offset: activation_offset_i, weight_data: weight_data_i,
      activation_data: activation_data_i, weight_strb: weight_strb_i,
      activation_strb: activation_strb_i, weight_read: weight_read_i,
      activation_read: activation_read_i, read_k: read_k_i
    };
  end
  qbs_block_adapter #(.NativeView(1'b0)) i_adapter (
    .clk_i, .rst_ni,
    .clear_weight_i(inputs_q.clear_weight), .clear_activation_i(inputs_q.clear_activation),
    .weight_profile_i(inputs_q.weight_profile),
    .activation_profile_i(inputs_q.activation_profile),
    .weight_row_count_i(inputs_q.rows), .activation_layout_i(inputs_q.activation_layout),
    .m_i(inputs_q.m),
    .weight_write_valid_i(inputs_q.weight_valid), .weight_write_ready_o(weight_ready_o),
    .weight_write_group_i(inputs_q.weight_group), .weight_write_row_i(inputs_q.weight_row),
    .weight_write_offset_i(inputs_q.weight_offset), .weight_write_data_i(inputs_q.weight_data),
    .weight_write_strb_i(inputs_q.weight_strb),
    .activation_write_valid_i(inputs_q.activation_valid),
    .activation_write_ready_o(activation_ready_o),
    .activation_write_context_i(inputs_q.activation_context),
    .activation_write_offset_i(inputs_q.activation_offset),
    .activation_write_data_i(inputs_q.activation_data),
    .activation_write_strb_i(inputs_q.activation_strb),
    .weight_read_i(inputs_q.weight_read), .activation_read_i(inputs_q.activation_read),
    .read_k_i(inputs_q.read_k), .weight_block_o(), .activation_block_o(),
    .weight_window_o, .activation_window_o, .weight_side_o, .activation_side_o,
    .weight_complete_o(), .activation_complete_o(),
    .all_weight_complete_o, .all_activation_complete_o,
    .accepted_weight_bytes_o(weight_bytes_o), .accepted_activation_bytes_o(activation_bytes_o)
  );
endmodule
