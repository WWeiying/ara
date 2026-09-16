// SPDX-License-Identifier: SHL-0.51
// Complete integer profile pipeline, including arbitration and correction.
// Input FFs approximate a registered window, not SRAM clock-to-Q/bank selection.
module qbs_profile_pipeline_timing import qbs_pkg::*; (
  input logic clk_i, rst_ni, start_valid_i, result_ready_i,
  input qbs_weight_profile_e profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input logic [2:0] m_i, rows_i, context_base_i,
  input logic [5:0] row_base_i,
  input logic first_block_i,
  input logic [127:0] weight_window_i [4][2],
  input logic [255:0] activation_window_i [4],
  input logic [7:0] weight_side_i [4][20], activation_side_i [4][36],
  output logic start_ready_o, busy_o, done_o, result_valid_o,
  output logic [3:0] result_stream_o,
  output logic signed [31:0] result_dot_o, result_aux_o,
  output logic [15:0] weight_d_o, weight_dmin_o,
  output logic [31:0] activation_d_o,
  output logic read_valid_o,
  output logic [7:0] read_k_o
);
  qbs_weight_profile_e profile_q;
  qbs_activation_profile_e activation_profile_q;
  logic [2:0] m_q, rows_q, context_base_q;
  logic [5:0] row_base_q;
  logic first_block_q, start_valid_q, result_ready_q;
  logic [127:0] weight_window_q [4][2];
  logic [255:0] activation_window_q [4];
  logic [7:0] weight_side_q [4][20], activation_side_q [4][36];
  wire [7:0] unused_weight [4][QbsMaxWeightBlockBytes];
  wire [7:0] unused_activation [4][QbsMaxActivationBlockBytes];
  for (genvar row = 0; row < 4; row++) begin : gen_unused
    for (genvar index = 0; index < QbsMaxWeightBlockBytes; index++)
      assign unused_weight[row][index] = '0;
    for (genvar index = 0; index < QbsMaxActivationBlockBytes; index++)
      assign unused_activation[row][index] = '0;
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      profile_q <= QBS_WEIGHT_PROFILE_INVALID;
      activation_profile_q <= QBS_ACTIVATION_PROFILE_INVALID;
      m_q <= 0; rows_q <= 0; context_base_q <= 0; row_base_q <= 0;
      first_block_q <= 0; start_valid_q <= 0; result_ready_q <= 0;
      weight_window_q <= '{default: '0};
      activation_window_q <= '{default: '0};
      weight_side_q <= '{default: '0};
      activation_side_q <= '{default: '0};
    end else begin
      profile_q <= profile_i; activation_profile_q <= activation_profile_i;
      m_q <= m_i; rows_q <= rows_i; context_base_q <= context_base_i;
      row_base_q <= row_base_i; first_block_q <= first_block_i;
      start_valid_q <= start_valid_i; result_ready_q <= result_ready_i;
      weight_window_q <= weight_window_i; activation_window_q <= activation_window_i;
      weight_side_q <= weight_side_i; activation_side_q <= activation_side_i;
    end
  end
  qbs_profile_engine_int #(.CompactRead(1)) i_profile (
      .clk_i, .rst_ni,
      .weight_block_i(unused_weight), .activation_block_i(unused_activation),
      .weight_window_i(weight_window_q), .activation_window_i(activation_window_q),
      .weight_side_i(weight_side_q), .activation_side_i(activation_side_q),
      .start_valid_i(start_valid_q), .start_ready_o,
      .start_profile_i(profile_q), .start_activation_profile_i(activation_profile_q),
      .start_m_i(m_q), .start_row_count_i(rows_q), .start_context_base_i(context_base_q),
      .start_row_base_i(row_base_q), .start_first_block_i(first_block_q),
      .busy_o, .done_o, .result_valid_o, .result_ready_i(result_ready_q),
      .result_stream_o, .result_dot_o, .result_aux_o,
      .result_weight_d_o(weight_d_o), .result_weight_dmin_o(weight_dmin_o),
      .result_activation_d_o(activation_d_o), .result_context_base_o(),
      .result_row_base_o(), .result_row_count_o(), .result_first_block_o(),
      .buffer_read_valid_o(read_valid_o), .buffer_read_k_base_o(read_k_o),
      .decode_valid_o(), .decode_k_base_o(), .decode_k_per_context_o(),
      .decode_stream_valid_o(), .decode_weight_quant_o(), .decode_activation_quant_o(),
      .group_valid_o(), .group_index_o(), .group_dot_o(), .group_aux_o(),
      .group_scale_o(), .group_min_o(), .useful_pairs_o(), .pair_capacity_o(),
      .dot_active_cycles_o());
endmodule
