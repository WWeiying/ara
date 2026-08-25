// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_profile_decoder import qbs_pkg::*; (
  input  qbs_weight_profile_e profile_i,
  input  qbs_activation_profile_e activation_profile_i,
  input  logic [2:0]          m_i,
  input  logic [2:0]          row_count_i,
  input  logic [7:0]          k_base_i,
  input  logic [7:0]          weight_block_i [4][QbsMaxWeightBlockBytes],
  input  logic [7:0]          activation_block_i [4][QbsMaxActivationBlockBytes],
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

  function automatic logic signed [7:0] iq4_nl_value(input logic [3:0] index);
    begin
      unique case (index)
        4'h0: iq4_nl_value = -8'sd127;
        4'h1: iq4_nl_value = -8'sd104;
        4'h2: iq4_nl_value = -8'sd83;
        4'h3: iq4_nl_value = -8'sd65;
        4'h4: iq4_nl_value = -8'sd49;
        4'h5: iq4_nl_value = -8'sd35;
        4'h6: iq4_nl_value = -8'sd22;
        4'h7: iq4_nl_value = -8'sd10;
        4'h8: iq4_nl_value = 8'sd1;
        4'h9: iq4_nl_value = 8'sd13;
        4'ha: iq4_nl_value = 8'sd25;
        4'hb: iq4_nl_value = 8'sd38;
        4'hc: iq4_nl_value = 8'sd53;
        4'hd: iq4_nl_value = 8'sd69;
        4'he: iq4_nl_value = 8'sd89;
        default: iq4_nl_value = 8'sd113;
      endcase
    end
  endfunction

  function automatic logic signed [7:0] decode_weight_quant(
      input int unsigned row, input int unsigned element);
    int unsigned packet;
    int unsigned within_index;
    int unsigned ql_index;
    int unsigned qh_index;
    int unsigned quarter;
    int unsigned half;
    int unsigned lane;
    int unsigned subgroup;
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
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q5_K) begin
        packet = element >> 6;
        within_index = element & 8'h3f;
        packed_byte = weight_block_i[row]
            [48 + packet * 32 + (within_index & 8'h1f)];
        low = within_index < 32
            ? {4'b0, packed_byte[3:0]}
            : {4'b0, packed_byte[7:4]};
        // Keep the four packet cases explicit so Q5_K does not synthesize a
        // variable eight-bit shifter on the decoder-to-dot critical stage.
        unique case (packet)
          0: high[0] = within_index < 32
              ? weight_block_i[row][16 + (within_index & 8'h1f)][0]
              : weight_block_i[row][16 + (within_index & 8'h1f)][1];
          1: high[0] = within_index < 32
              ? weight_block_i[row][16 + (within_index & 8'h1f)][2]
              : weight_block_i[row][16 + (within_index & 8'h1f)][3];
          2: high[0] = within_index < 32
              ? weight_block_i[row][16 + (within_index & 8'h1f)][4]
              : weight_block_i[row][16 + (within_index & 8'h1f)][5];
          default: high[0] = within_index < 32
              ? weight_block_i[row][16 + (within_index & 8'h1f)][6]
              : weight_block_i[row][16 + (within_index & 8'h1f)][7];
        endcase
        decode_weight_quant = $signed({3'b000, high[0], low[3:0]});
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q3_K) begin
        packet = element >> 5;
        lane = element & 8'h1f;
        packed_byte = weight_block_i[row]
            [32 + (packet >= 4 ? 32 : 0) + lane];
        low = '0;
        unique case (packet[1:0])
          0: low[1:0] = packed_byte[1:0];
          1: low[1:0] = packed_byte[3:2];
          2: low[1:0] = packed_byte[5:4];
          default: low[1:0] = packed_byte[7:6];
        endcase
        high = '0;
        unique case (packet)
          0: high[0] = weight_block_i[row][lane][0];
          1: high[0] = weight_block_i[row][lane][1];
          2: high[0] = weight_block_i[row][lane][2];
          3: high[0] = weight_block_i[row][lane][3];
          4: high[0] = weight_block_i[row][lane][4];
          5: high[0] = weight_block_i[row][lane][5];
          6: high[0] = weight_block_i[row][lane][6];
          default: high[0] = weight_block_i[row][lane][7];
        endcase
        decode_weight_quant =
            $signed({6'b000000, low[1:0]}) - (high[0] ? 8'sd0 : 8'sd4);
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
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT) begin
        decode_weight_quant =
            $signed(weight_block_i[row][2 + element]);
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q4_0) begin
        packed_byte = weight_block_i[row][2 + (element & 8'h0f)];
        decode_weight_quant = (element < 16
            ? $signed({4'b0, packed_byte[3:0]})
            : $signed({4'b0, packed_byte[7:4]})) - 8'sd8;
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q2_K) begin
        half = element >> 7;
        subgroup = (element & 8'h7f) >> 4;
        lane = element & 8'h0f;
        packed_byte = weight_block_i[row]
            [16 + half * 32 + ((subgroup & 1) != 0 ? 16 : 0) + lane];
        unique case (subgroup[2:1])
          0: decode_weight_quant = $signed({6'b0, packed_byte[1:0]});
          1: decode_weight_quant = $signed({6'b0, packed_byte[3:2]});
          2: decode_weight_quant = $signed({6'b0, packed_byte[5:4]});
          default: decode_weight_quant = $signed({6'b0, packed_byte[7:6]});
        endcase
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q5_0) begin
        packed_byte = weight_block_i[row][6 + (element & 8'h0f)];
        low = element < 16
            ? {4'b0, packed_byte[3:0]}
            : {4'b0, packed_byte[7:4]};
        high = '0;
        high[0] = weight_block_i[row][2 + (element >> 3)][element & 7];
        decode_weight_quant =
            $signed({3'b000, high[0], low[3:0]}) - 8'sd16;
      end else if (profile_i == QBS_WEIGHT_PROFILE_IQ4_NL) begin
        packed_byte = weight_block_i[row][2 + (element & 8'h0f)];
        decode_weight_quant = iq4_nl_value(
            element < 16 ? packed_byte[3:0] : packed_byte[7:4]);
      end
    end
  endfunction

  function automatic logic signed [7:0] decode_q3_scale(
      input int unsigned row, input int unsigned group_index);
    int unsigned group_slot;
    logic [7:0] low_meta;
    logic [7:0] high_meta;
    logic [3:0] low_nibble;
    logic [1:0] high_bits;
    begin
      group_slot = group_index & 3;
      low_meta = '0;
      high_meta = weight_block_i[row][104 + group_slot];
      low_nibble = '0;
      high_bits = '0;
      unique case (group_index >> 2)
        0: begin
          low_meta = weight_block_i[row][96 + group_slot];
          low_nibble = low_meta[3:0];
          high_bits = high_meta[1:0];
        end
        1: begin
          low_meta = weight_block_i[row][100 + group_slot];
          low_nibble = low_meta[3:0];
          high_bits = high_meta[3:2];
        end
        2: begin
          low_meta = weight_block_i[row][96 + group_slot];
          low_nibble = low_meta[7:4];
          high_bits = high_meta[5:4];
        end
        default: begin
          low_meta = weight_block_i[row][100 + group_slot];
          low_nibble = low_meta[7:4];
          high_bits = high_meta[7:6];
        end
      endcase
      decode_q3_scale =
          $signed({2'b00, high_bits, low_nibble}) - 8'sd32;
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

    group_index_o = '0;
    group_end_o = 1'b0;
    unique case (profile_i)
      QBS_WEIGHT_PROFILE_Q4_K,
      QBS_WEIGHT_PROFILE_Q5_K: begin
        group_index_o = {1'b0, k_base_i[7:5]};
        group_end_o = (k_base_i[4:0] + k_per_context_o) == 32;
      end
      QBS_WEIGHT_PROFILE_Q6_K: begin
        group_index_o = k_base_i[7:4];
        group_end_o = (k_base_i[3:0] + k_per_context_o) == 16;
      end
      QBS_WEIGHT_PROFILE_Q3_K: begin
        group_index_o = k_base_i[7:4];
        group_end_o = (k_base_i[3:0] + k_per_context_o) == 16;
      end
      QBS_WEIGHT_PROFILE_Q2_K: begin
        group_index_o = k_base_i[7:4];
        group_end_o = (k_base_i[3:0] + k_per_context_o) == 16;
      end
      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
      QBS_WEIGHT_PROFILE_Q4_0,
      QBS_WEIGHT_PROFILE_Q5_0,
      QBS_WEIGHT_PROFILE_IQ4_NL: begin
        group_index_o = '0;
        group_end_o = (k_base_i[5:0] + k_per_context_o) == 32;
      end
      default: ;
    endcase

    stream_valid_o = '0;
    for (int row = 0; row < 4; row++) begin
      weight_d_o[row] = '0;
      weight_dmin_o[row] = '0;
      unique case (profile_i)
        QBS_WEIGHT_PROFILE_Q4_K,
        QBS_WEIGHT_PROFILE_Q5_K: begin
          weight_d_o[row] = {weight_block_i[row][1],
                             weight_block_i[row][0]};
          weight_dmin_o[row] = {weight_block_i[row][3],
                                weight_block_i[row][2]};
        end
        QBS_WEIGHT_PROFILE_Q6_K:
          weight_d_o[row] = {weight_block_i[row][209],
                             weight_block_i[row][208]};
        QBS_WEIGHT_PROFILE_Q3_K:
          weight_d_o[row] = {weight_block_i[row][109],
                             weight_block_i[row][108]};
        QBS_WEIGHT_PROFILE_Q2_K: begin
          weight_d_o[row] = {weight_block_i[row][81],
                             weight_block_i[row][80]};
          weight_dmin_o[row] = {weight_block_i[row][83],
                                weight_block_i[row][82]};
        end
        QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
        QBS_WEIGHT_PROFILE_Q4_0,
        QBS_WEIGHT_PROFILE_Q5_0,
        QBS_WEIGHT_PROFILE_IQ4_NL:
          weight_d_o[row] = {weight_block_i[row][1],
                             weight_block_i[row][0]};
        default: ;
      endcase
      for (int lane = 0; lane < 8; lane++) begin
        weight_quant_o[row][lane] = '0;
        if (row < row_count_i && lane < k_per_context_o)
          weight_quant_o[row][lane] =
              decode_weight_quant(row, unsigned'(k_base_i) + lane);
      end
    end

    for (int ctx = 0; ctx < 4; ctx++) begin
      activation_d_o[ctx] = '0;
      unique case (activation_profile_i)
        QBS_ACTIVATION_PROFILE_Q8_K:
          activation_d_o[ctx] = {
              activation_block_i[ctx][3], activation_block_i[ctx][2],
              activation_block_i[ctx][1], activation_block_i[ctx][0]};
        QBS_ACTIVATION_PROFILE_Q8_0:
          activation_d_o[ctx] = {16'b0, activation_block_i[ctx][1],
                                 activation_block_i[ctx][0]};
        default: ;
      endcase
      for (int lane = 0; lane < 8; lane++) begin
        activation_quant_o[ctx][lane] = '0;
        if (ctx < m_i && lane < k_per_context_o)
          activation_quant_o[ctx][lane] = $signed(activation_block_i[ctx][
              (activation_profile_i == QBS_ACTIVATION_PROFILE_Q8_K ? 4 : 2) +
              unsigned'(k_base_i) + lane]);
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
        if (profile_i == QBS_WEIGHT_PROFILE_Q4_K ||
            profile_i == QBS_WEIGHT_PROFILE_Q5_K) begin
          group_scale_o[stream] = $signed(
              decode_q4_scale(row, group_index_o));
          group_min_o[stream] = decode_q4_min(row, group_index_o);
          group_aux_o[stream] =
              activation_bsum(ctx, 2 * group_index_o) +
              activation_bsum(ctx, 2 * group_index_o + 1);
        end else if (profile_i == QBS_WEIGHT_PROFILE_Q6_K) begin
          group_scale_o[stream] = $signed(
              weight_block_i[row][192 + group_index_o]);
        end else if (profile_i == QBS_WEIGHT_PROFILE_Q3_K) begin
          group_scale_o[stream] = decode_q3_scale(row, group_index_o);
        end else if (profile_i == QBS_WEIGHT_PROFILE_Q2_K) begin
          group_scale_o[stream] = $signed({4'b0,
              weight_block_i[row][group_index_o][3:0]});
          group_min_o[stream] = {4'b0,
              weight_block_i[row][group_index_o][7:4]};
          group_aux_o[stream] = activation_bsum(ctx, group_index_o);
        end else if (profile_i == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT ||
                     profile_i == QBS_WEIGHT_PROFILE_Q4_0 ||
                     profile_i == QBS_WEIGHT_PROFILE_Q5_0 ||
                     profile_i == QBS_WEIGHT_PROFILE_IQ4_NL) begin
          group_scale_o[stream] = 8'sd1;
        end
      end
    end
  end

endmodule : qbs_profile_decoder
