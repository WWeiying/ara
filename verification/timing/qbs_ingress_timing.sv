// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
// Local timing cone, not an engine benchmark. Keep the real two-adapter
// ready broadcast and observe the metadata byte at the reported ICG endpoint.
module qbs_ingress_timing import qbs_pkg::*; (
  input logic clk_i, rst_ni,
  input qbs_activation_profile_e profile_i,
  input qbs_activation_layout_e layout_i,
  input logic [3:0] m_i,
  input logic clear_i, valid_i,
  input logic [1:0] context_i,
  input logic [11:0] offset_i,
  input logic [127:0] data_i,
  input logic [15:0] strb_i,
  output logic [1:0] ready_o,
  output logic [15:0] side_o
);
  qbs_activation_profile_e profile_q;
  qbs_activation_layout_e layout_q;
  logic [3:0] m_q;
  logic clear_q, valid_q;
  logic [1:0] context_q;
  logic [11:0] offset_q;
  logic [127:0] data_q;
  logic [15:0] strb_q;
  logic [7:0] side [2][4][36];
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      profile_q <= QBS_ACTIVATION_PROFILE_INVALID;
      layout_q <= QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
      m_q <= 0;
      clear_q <= 0;
      valid_q <= 0;
      context_q <= 0;
      offset_q <= 0;
      data_q <= 0;
      strb_q <= 0;
    end else begin
      profile_q <= profile_i;
      layout_q <= layout_i;
      m_q <= m_i;
      clear_q <= clear_i;
      valid_q <= valid_i;
      context_q <= context_i;
      offset_q <= offset_i;
      data_q <= data_i;
      strb_q <= strb_i;
    end
  end
  for (genvar b = 0; b < 2; b++) begin : gen_bank
    qbs_block_adapter #(.ActivationContextBase(4*b), .NativeView(1'b0)) i_adapter (
      .clk_i, .rst_ni,
      .clear_weight_i(1'b0), .clear_activation_i(clear_q),
      .weight_profile_i(QBS_WEIGHT_PROFILE_Q4_K), .activation_profile_i(profile_q),
      .weight_row_count_i(3'd1), .activation_layout_i(layout_q), .m_i(m_q),
      .weight_write_valid_i(1'b0), .weight_write_ready_o(),
      .weight_write_group_i(1'b0), .weight_write_row_i(2'b0),
      .weight_write_offset_i(10'b0), .weight_write_data_i(128'b0),
      .weight_write_strb_i(16'b0),
      .activation_write_valid_i(valid_q && (&ready_o)),
      .activation_write_ready_o(ready_o[b]), .activation_write_context_i(context_q),
      .activation_write_offset_i(offset_q), .activation_write_data_i(data_q),
      .activation_write_strb_i(strb_q),
      .weight_read_i(1'b0), .activation_read_i(1'b0), .read_k_i(8'b0),
      .weight_block_o(), .activation_block_o(), .weight_window_o(),
      .activation_window_o(), .weight_side_o(), .activation_side_o(side[b]),
      .weight_complete_o(), .activation_complete_o(),
      .all_weight_complete_o(), .all_activation_complete_o(),
      .accepted_weight_bytes_o(), .accepted_activation_bytes_o()
    );
    assign side_o[8*b +: 8] = side[b][2][15];
  end
endmodule
