// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_profile_decoder import qbs_pkg::*; (
  input  qbs_weight_profile_e profile_i,
  input  logic [2:0]          m_i,
  input  logic [2:0]          row_count_i,
  input  logic [7:0]          k_base_i,
  input  logic [7:0]          weight_block_i [4][QbsQ6KBlockBytes],
  input  logic [7:0]          activation_block_i [4][QbsQ8KBlockBytes],
  output logic [3:0]          k_per_context_o,
  output logic [3:0]          group_index_o,
  output logic                group_end_o,
  output logic [15:0]         stream_valid_o,
  output logic signed [7:0]   weight_quant_o [4][8],
  output logic signed [7:0]   activation_quant_o [4][8],
  output logic signed [7:0]   group_scale_o [16],
  output logic [7:0]          group_min_o [16],
  output logic signed [15:0]  group_aux_o [16],
  output logic [15:0]         weight_d_o [4],
  output logic [15:0]         weight_dmin_o [4],
  output logic [31:0]         activation_d_o [4]
);

  function automatic logic signed [7:0] decode_weight_quant(
      input int unsigned row, input int unsigned element);
    int unsigned packet;
    int unsigned within_index;
    int unsigned ql_index;
    int unsigned qh_index;
    int unsigned quarter;
    int unsigned half;
    int unsigned lane;
    logic [7:0] packed_byte;
    logic [7:0] low;
    logic [7:0] high;
    begin
      decode_weight_quant = '0;
      if (profile_i == QBS_WEIGHT_PROFILE_Q4_K) begin
        packet = element >> 6;
        within_index = element & 8'h3f;
        packed_byte = weight_block_i[row]
            [16 + packet * 32 + (within_index & 8'h1f)];
        decode_weight_quant = within_index < 32
            ? $signed({4'b0, packed_byte[3:0]})
            : $signed({4'b0, packed_byte[7:4]});
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q6_K) begin
        half = element >> 7;
        quarter = (element & 8'h7f) >> 5;
        lane = element & 8'h1f;
        ql_index = half * 64 + ((quarter & 1) != 0 ? 32 : 0) + lane;
        qh_index = 128 + half * 32 + lane;
        low = (weight_block_i[row][ql_index] >>
               (quarter >= 2 ? 4 : 0)) & 8'h0f;
        high = (weight_block_i[row][qh_index] >> (quarter * 2)) & 8'h03;
        decode_weight_quant =
            $signed({2'b00, high[1:0], low[3:0]}) - 8'sd32;
      end
    end
  endfunction

  function automatic logic [7:0] decode_q4_scale(
      input int unsigned row, input int unsigned group_index);
    logic [7:0] meta [12];
    begin
      for (int i = 0; i < 12; i++) meta[i] = weight_block_i[row][4 + i];
      if (group_index < 4)
        decode_q4_scale = meta[group_index] & 8'h3f;
      else
        decode_q4_scale = (meta[group_index + 4] & 8'h0f) |
                          ((meta[group_index - 4] >> 6) << 4);
    end
  endfunction

  function automatic logic [7:0] decode_q4_min(
      input int unsigned row, input int unsigned group_index);
    logic [7:0] meta [12];
    begin
      for (int i = 0; i < 12; i++) meta[i] = weight_block_i[row][4 + i];
      if (group_index < 4)
        decode_q4_min = meta[group_index + 4] & 8'h3f;
      else
        decode_q4_min = (meta[group_index + 4] >> 4) |
                        ((meta[group_index] >> 6) << 4);
    end
  endfunction

  function automatic logic signed [15:0] activation_bsum(
      input int unsigned ctx, input int unsigned subgroup);
    int unsigned offset;
    logic [15:0] bits;
    begin
      offset = 260 + subgroup * 2;
      bits = {activation_block_i[ctx][offset + 1],
              activation_block_i[ctx][offset]};
      activation_bsum = $signed(bits);
    end
  endfunction

  always_comb begin
    k_per_context_o = 4'd2;
    if (m_i == 1) k_per_context_o = 4'd8;
    else if (m_i == 2) k_per_context_o = 4'd4;

    group_index_o = profile_i == QBS_WEIGHT_PROFILE_Q4_K
        ? {1'b0, k_base_i[7:5]} : k_base_i[7:4];
    group_end_o = profile_i == QBS_WEIGHT_PROFILE_Q4_K
        ? ((k_base_i[4:0] + k_per_context_o) == 32)
        : ((k_base_i[3:0] + k_per_context_o) == 16);

    stream_valid_o = '0;
    for (int row = 0; row < 4; row++) begin
      weight_d_o[row] = profile_i == QBS_WEIGHT_PROFILE_Q4_K
          ? {weight_block_i[row][1], weight_block_i[row][0]}
          : {weight_block_i[row][209], weight_block_i[row][208]};
      weight_dmin_o[row] = profile_i == QBS_WEIGHT_PROFILE_Q4_K
          ? {weight_block_i[row][3], weight_block_i[row][2]} : '0;
      for (int lane = 0; lane < 8; lane++) begin
        weight_quant_o[row][lane] = '0;
        if (row < row_count_i && lane < k_per_context_o)
          weight_quant_o[row][lane] =
              decode_weight_quant(row, unsigned'(k_base_i) + lane);
      end
    end

    for (int ctx = 0; ctx < 4; ctx++) begin
      activation_d_o[ctx] = {
          activation_block_i[ctx][3], activation_block_i[ctx][2],
          activation_block_i[ctx][1], activation_block_i[ctx][0]};
      for (int lane = 0; lane < 8; lane++) begin
        activation_quant_o[ctx][lane] = '0;
        if (ctx < m_i && lane < k_per_context_o)
          activation_quant_o[ctx][lane] = $signed(
              activation_block_i[ctx][4 + unsigned'(k_base_i) + lane]);
      end
    end

    for (int stream = 0; stream < 16; stream++) begin
      automatic int unsigned row = stream / 4;
      automatic int unsigned ctx = stream % 4;
      stream_valid_o[stream] = row < row_count_i && ctx < m_i;
      group_scale_o[stream] = '0;
      group_min_o[stream] = '0;
      group_aux_o[stream] = '0;
      if (stream_valid_o[stream]) begin
        if (profile_i == QBS_WEIGHT_PROFILE_Q4_K) begin
          group_scale_o[stream] = $signed(
              decode_q4_scale(row, group_index_o));
          group_min_o[stream] = decode_q4_min(row, group_index_o);
          group_aux_o[stream] =
              activation_bsum(ctx, 2 * group_index_o) +
              activation_bsum(ctx, 2 * group_index_o + 1);
        end else begin
          group_scale_o[stream] = $signed(
              weight_block_i[row][192 + group_index_o]);
        end
      end
    end
  end

endmodule : qbs_profile_decoder
