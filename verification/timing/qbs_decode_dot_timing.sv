// SPDX-License-Identifier: SHL-0.51
// Isolates the native-window decode/dot cone. Input FFs do not model SRAM
// clock-to-Q or the two-bank mux; absolute slack is not whole-engine timing.
module qbs_decode_dot_timing import qbs_pkg::*; (
  input logic clk_i, rst_ni, valid_i,
  input qbs_weight_profile_e profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input logic [2:0] m_i, row_count_i,
  input logic [7:0] k_base_i,
  input logic [127:0] weight_window_i [4][2],
  input logic [255:0] activation_window_i [4],
  input logic [7:0] weight_side_i [4][20], activation_side_i [4][36],
  output logic valid_o,
  output logic [15:0] stream_valid_o,
  output logic signed [18:0] stream_sum_o [16]
);
  qbs_weight_profile_e profile_q;
  qbs_activation_profile_e activation_profile_q;
  logic [2:0] m_q, row_count_q;
  logic [7:0] k_base_q;
  logic [127:0] weight_window_q [4][2];
  logic [255:0] activation_window_q [4];
  logic [7:0] weight_side_q [4][20], activation_side_q [4][36];
  logic valid_q;
  wire [7:0] unused_weight [4][QbsMaxWeightBlockBytes];
  wire [7:0] unused_activation [4][QbsMaxActivationBlockBytes];
  for (genvar row = 0; row < 4; row++) begin : gen_unused
    for (genvar byte_index = 0; byte_index < QbsMaxWeightBlockBytes; byte_index++)
      assign unused_weight[row][byte_index] = 8'b0;
    for (genvar byte_index = 0; byte_index < QbsMaxActivationBlockBytes; byte_index++)
      assign unused_activation[row][byte_index] = 8'b0;
  end
  logic [15:0] stream_valid;
  logic signed [7:0] weight_quant [4][8], activation_quant [4][8];
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      profile_q <= QBS_WEIGHT_PROFILE_INVALID;
      activation_profile_q <= QBS_ACTIVATION_PROFILE_INVALID;
      m_q <= 0; row_count_q <= 0; k_base_q <= 0; valid_q <= 0;
      for (int row = 0; row < 4; row++) begin
        for (int plane = 0; plane < 2; plane++) weight_window_q[row][plane] <= '0;
        activation_window_q[row] <= '0;
        for (int index = 0; index < 20; index++) weight_side_q[row][index] <= '0;
        for (int index = 0; index < 36; index++) activation_side_q[row][index] <= '0;
      end
    end else begin
      profile_q <= profile_i; activation_profile_q <= activation_profile_i;
      m_q <= m_i; row_count_q <= row_count_i; k_base_q <= k_base_i; valid_q <= valid_i;
      weight_window_q <= weight_window_i; activation_window_q <= activation_window_i;
      weight_side_q <= weight_side_i; activation_side_q <= activation_side_i;
    end
  end
  qbs_profile_decoder #(.CompactRead(1)) i_decoder (
      .profile_i(profile_q), .activation_profile_i(activation_profile_q),
      .m_i(m_q), .row_count_i(row_count_q), .k_base_i(k_base_q),
      .weight_block_i(unused_weight), .activation_block_i(unused_activation),
      .weight_window_i(weight_window_q), .activation_window_i(activation_window_q),
      .weight_side_i(weight_side_q), .activation_side_i(activation_side_q),
      .stream_valid_o(stream_valid), .weight_quant_o(weight_quant),
      .activation_quant_o(activation_quant), .k_per_context_o(), .group_index_o(),
      .group_end_o(), .group_scale_o(), .group_min_o(), .group_aux_o(),
      .weight_d_o(), .weight_dmin_o(), .activation_d_o());
  qbs_dot_array i_dot (.clk_i, .rst_ni, .valid_i(valid_q), .m_i(m_q),
      .row_count_i(row_count_q), .stream_valid_i(stream_valid),
      .weight_quant_i(weight_quant), .activation_quant_i(activation_quant),
      .valid_o, .stream_valid_o, .stream_sum_o);
endmodule
