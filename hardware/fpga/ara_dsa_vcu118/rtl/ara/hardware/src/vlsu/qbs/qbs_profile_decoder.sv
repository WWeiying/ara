// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_profile_decoder import qbs_pkg::*; #(
  parameter bit CompactRead = 1'b0
) (
  input  qbs_weight_profile_e profile_i,
  input  qbs_activation_profile_e activation_profile_i,
  input  logic [2:0]          m_i,
  input  logic [2:0]          row_count_i,
  input  logic [7:0]          k_base_i,
  input  logic [7:0]          weight_block_i [4][QbsMaxWeightBlockBytes],
  input  logic [7:0]          activation_block_i [4][QbsMaxActivationBlockBytes],
  input logic [255:0] weight_window_i [4][2], activation_window_i [4],
  input logic [7:0] weight_side_i [4][20], activation_side_i [4][36],
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

  logic [7:0] compact_low [4][8], compact_high [4][8];
  logic [7:0] compact_activation [4][8];

  // Each issue consumes consecutive bytes within one SRAM window. Share the
  // alignment network across the eight outputs, instead of reading the
  // 32-byte window independently for every format/element combination.
  function automatic logic [255:0] align_window(
      input logic [255:0] data, input logic [4:0] offset);
    logic [255:0] stage [6];
    stage[0] = data;
    for (int level = 0; level < 5; level++)
      for (int b = 0; b < 32; b++)
        stage[level+1][8*b +: 8] = offset[level]
            ? stage[level][8*((b + (1 << level)) % 32) +: 8]
            : stage[level][8*b +: 8];
    return stage[5];
  endfunction

  if (CompactRead) begin : gen_compact_alignment
    wire short_payload = profile_i inside {
        QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q5_0, QBS_WEIGHT_PROFILE_IQ4_NL};
    for (genvar row = 0; row < 4; row++) begin : gen_row
      wire [255:0] low_source = short_payload
          ? {2{weight_window_i[row][0][127:0]}} : weight_window_i[row][0];
      wire [255:0] low_aligned = align_window(low_source, k_base_i[4:0]);
      wire [255:0] high_aligned = align_window(weight_window_i[row][1], k_base_i[4:0]);
      wire [255:0] activation_aligned = align_window(activation_window_i[row], k_base_i[4:0]);
      for (genvar lane = 0; lane < 8; lane++) begin : gen_byte
        assign compact_low[row][lane] = low_aligned[8*lane +: 8];
        assign compact_high[row][lane] = high_aligned[8*lane +: 8];
        assign compact_activation[row][lane] = activation_aligned[8*lane +: 8];
      end
    end
  end else begin : gen_native_alignment
    assign compact_low = '{default:'0};
    assign compact_high = '{default:'0};
    assign compact_activation = '{default:'0};
  end

  function automatic logic signed [7:0] compact_weight_quant(
      input int unsigned row, lane, element);
    logic [7:0] low, high;
    logic [3:0] nibble;
    logic [1:0] pair_bits, high_pair;
    logic high_bit;
    logic [31:0] q5_high_bits;
    low = compact_low[row][lane];
    high = compact_high[row][lane];
    nibble = (profile_i == QBS_WEIGHT_PROFILE_Q6_K ? element[6] :
        (profile_i inside {QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q5_0,
                           QBS_WEIGHT_PROFILE_IQ4_NL}) ? element[4] : element[5])
        ? low[7:4] : low[3:0];
    pair_bits = 2'(low >> {element[6:5], 1'b0});
    high_pair = 2'(high >> {element[6:5], 1'b0});
    high_bit = high[element[7:5]];
    q5_high_bits = {weight_side_i[row][5], weight_side_i[row][4],
                    weight_side_i[row][3], weight_side_i[row][2]};
    case (profile_i)
      QBS_WEIGHT_PROFILE_Q4_K: return $signed({4'b0, nibble});
      QBS_WEIGHT_PROFILE_Q5_K: return $signed({3'b0, high_bit, nibble});
      QBS_WEIGHT_PROFILE_Q6_K: return 8'($signed({~high_pair[1], high_pair[0], nibble}));
      QBS_WEIGHT_PROFILE_Q3_K: return 8'($signed({~high_bit, pair_bits}));
      QBS_WEIGHT_PROFILE_Q2_K: return $signed({6'b0, pair_bits});
      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT: return $signed(low);
      QBS_WEIGHT_PROFILE_Q4_0: return 8'($signed({~nibble[3], nibble[2:0]}));
      QBS_WEIGHT_PROFILE_Q5_0: return 8'($signed({~q5_high_bits[element[4:0]], nibble}));
      QBS_WEIGHT_PROFILE_IQ4_NL: return iq4_nl_value(nibble);
      default: return '0;
    endcase
  endfunction

  // Translate only the bytes consumed this cycle. The compatibility input is
  // retained for standalone profile tests; the integrated path uses windows.
  function automatic logic [7:0] weight_byte(input int unsigned row, offset);
    logic [1:0] plane;
    logic [7:0] local_offset;
    if (!CompactRead) return weight_block_i[row][offset];
    if (offset >= QbsMaxWeightBlockBytes) return 'x;
    if (offset >= qbs_weight_block_bytes(profile_i)) return '0;
    plane = 2;
    local_offset = 8'(offset);
    case (profile_i)
      QBS_WEIGHT_PROFILE_Q4_K:
        if (offset >= 16) begin plane = 0; local_offset = 8'(offset - 16); end
      QBS_WEIGHT_PROFILE_Q5_K:
        if (offset >= 48) begin plane = 0; local_offset = 8'(offset - 48); end
        else if (offset >= 16) begin plane = 1; local_offset = 8'(offset - 16); end
      QBS_WEIGHT_PROFILE_Q6_K:
        if (offset < 128) plane = 0;
        else if (offset < 192) begin plane = 1; local_offset = 8'(offset - 128); end
        else local_offset = 8'(offset - 192);
      QBS_WEIGHT_PROFILE_Q3_K:
        if (offset < 32) plane = 1;
        else if (offset < 96) begin plane = 0; local_offset = 8'(offset - 32); end
        else local_offset = 8'(offset - 96);
      QBS_WEIGHT_PROFILE_Q2_K:
        if (offset >= 80) local_offset = 8'(offset - 64);
        else if (offset >= 16) begin plane = 0; local_offset = 8'(offset - 16); end
      QBS_WEIGHT_PROFILE_Q5_0:
        if (offset >= 6) begin plane = 0; local_offset = 8'(offset - 6); end
      QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT, QBS_WEIGHT_PROFILE_IQ4_NL:
        if (offset >= 2) begin plane = 0; local_offset = 8'(offset - 2); end
      default: ;
    endcase
    if (plane == 2) return weight_side_i[row][local_offset];
    return weight_window_i[row][plane][8*local_offset[4:0] +: 8];
  endfunction

  function automatic logic [7:0] activation_byte(input int unsigned ctx, offset);
    int unsigned scale, quants;
    logic [8:0] local_offset;
    if (!CompactRead) return activation_block_i[ctx][offset];
    if (offset >= QbsMaxActivationBlockBytes) return 'x;
    if (offset >= qbs_activation_block_bytes(activation_profile_i)) return '0;
    scale = qbs_activation_scale_bytes(activation_profile_i);
    quants = qbs_activation_quant_bytes(activation_profile_i);
    if (offset < scale) return activation_side_i[ctx][offset];
    if (offset >= scale + quants) return activation_side_i[ctx][offset - quants];
    local_offset = 9'(offset - scale);
    return activation_window_i[ctx][8*local_offset[4:0] +: 8];
  endfunction

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
        packed_byte = weight_byte(row, 16 + packet * 32 + (within_index & 8'h1f));
        decode_weight_quant = within_index < 32
            ? $signed({4'b0, packed_byte[3:0]})
            : $signed({4'b0, packed_byte[7:4]});
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q5_K) begin
        packet = element >> 6;
        within_index = element & 8'h3f;
        packed_byte = weight_byte(row, 48 + packet * 32 + (within_index & 8'h1f));
        low = within_index < 32
            ? {4'b0, packed_byte[3:0]}
            : {4'b0, packed_byte[7:4]};
        // Keep the four packet cases explicit so Q5_K does not synthesize a
        // variable eight-bit shifter on the decoder-to-dot critical stage.
        unique case (packet)
          0: high[0] = within_index < 32
              ? 1'(weight_byte(row, 16 + (within_index & 8'h1f)) >> (0))
              : 1'(weight_byte(row, 16 + (within_index & 8'h1f)) >> (1));
          1: high[0] = within_index < 32
              ? 1'(weight_byte(row, 16 + (within_index & 8'h1f)) >> (2))
              : 1'(weight_byte(row, 16 + (within_index & 8'h1f)) >> (3));
          2: high[0] = within_index < 32
              ? 1'(weight_byte(row, 16 + (within_index & 8'h1f)) >> (4))
              : 1'(weight_byte(row, 16 + (within_index & 8'h1f)) >> (5));
          default: high[0] = within_index < 32
              ? 1'(weight_byte(row, 16 + (within_index & 8'h1f)) >> (6))
              : 1'(weight_byte(row, 16 + (within_index & 8'h1f)) >> (7));
        endcase
        decode_weight_quant = $signed({3'b000, high[0], low[3:0]});
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q3_K) begin
        packet = element >> 5;
        lane = element & 8'h1f;
        packed_byte = weight_byte(row, 32 + (packet >= 4 ? 32 : 0) + lane);
        low = '0;
        unique case (packet[1:0])
          0: low[1:0] = packed_byte[1:0];
          1: low[1:0] = packed_byte[3:2];
          2: low[1:0] = packed_byte[5:4];
          default: low[1:0] = packed_byte[7:6];
        endcase
        high = '0;
        unique case (packet)
          0: high[0] = 1'(weight_byte(row, lane) >> (0));
          1: high[0] = 1'(weight_byte(row, lane) >> (1));
          2: high[0] = 1'(weight_byte(row, lane) >> (2));
          3: high[0] = 1'(weight_byte(row, lane) >> (3));
          4: high[0] = 1'(weight_byte(row, lane) >> (4));
          5: high[0] = 1'(weight_byte(row, lane) >> (5));
          6: high[0] = 1'(weight_byte(row, lane) >> (6));
          default: high[0] = 1'(weight_byte(row, lane) >> (7));
        endcase
        decode_weight_quant =
            $signed({6'b000000, low[1:0]}) - (high[0] ? 8'sd0 : 8'sd4);
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q6_K) begin
        half = element >> 7;
        quarter = (element & 8'h7f) >> 5;
        lane = element & 8'h1f;
        ql_index = half * 64 + ((quarter & 1) != 0 ? 32 : 0) + lane;
        qh_index = 128 + half * 32 + lane;
        low = (weight_byte(row, ql_index) >>
               (quarter >= 2 ? 4 : 0)) & 8'h0f;
        high = (weight_byte(row, qh_index) >> (quarter * 2)) & 8'h03;
        decode_weight_quant =
            $signed({2'b00, high[1:0], low[3:0]}) - 8'sd32;
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT) begin
        decode_weight_quant =
            $signed(weight_byte(row, 2 + element));
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q4_0) begin
        packed_byte = weight_byte(row, 2 + (element & 8'h0f));
        decode_weight_quant = (element < 16
            ? $signed({4'b0, packed_byte[3:0]})
            : $signed({4'b0, packed_byte[7:4]})) - 8'sd8;
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q2_K) begin
        half = element >> 7;
        subgroup = (element & 8'h7f) >> 4;
        lane = element & 8'h0f;
        packed_byte = weight_byte(row, 16 + half * 32 + ((subgroup & 1) != 0 ? 16 : 0) + lane);
        unique case (subgroup[2:1])
          0: decode_weight_quant = $signed({6'b0, packed_byte[1:0]});
          1: decode_weight_quant = $signed({6'b0, packed_byte[3:2]});
          2: decode_weight_quant = $signed({6'b0, packed_byte[5:4]});
          default: decode_weight_quant = $signed({6'b0, packed_byte[7:6]});
        endcase
      end else if (profile_i == QBS_WEIGHT_PROFILE_Q5_0) begin
        packed_byte = weight_byte(row, 6 + (element & 8'h0f));
        low = element < 16
            ? {4'b0, packed_byte[3:0]}
            : {4'b0, packed_byte[7:4]};
        high = '0;
        high[0] = 1'(weight_byte(row, 2 + (element >> 3)) >> (element & 7));
        decode_weight_quant =
            $signed({3'b000, high[0], low[3:0]}) - 8'sd16;
      end else if (profile_i == QBS_WEIGHT_PROFILE_IQ4_NL) begin
        packed_byte = weight_byte(row, 2 + (element & 8'h0f));
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
      high_meta = weight_byte(row, 104 + group_slot);
      low_nibble = '0;
      high_bits = '0;
      unique case (group_index >> 2)
        0: begin
          low_meta = weight_byte(row, 96 + group_slot);
          low_nibble = low_meta[3:0];
          high_bits = high_meta[1:0];
        end
        1: begin
          low_meta = weight_byte(row, 100 + group_slot);
          low_nibble = low_meta[3:0];
          high_bits = high_meta[3:2];
        end
        2: begin
          low_meta = weight_byte(row, 96 + group_slot);
          low_nibble = low_meta[7:4];
          high_bits = high_meta[5:4];
        end
        default: begin
          low_meta = weight_byte(row, 100 + group_slot);
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
      for (int i = 0; i < 12; i++) meta[i] = weight_byte(row, 4 + i);
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
      for (int i = 0; i < 12; i++) meta[i] = weight_byte(row, 4 + i);
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
      bits = {activation_byte(ctx, offset + 1),
              activation_byte(ctx, offset)};
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
          weight_d_o[row] = {weight_byte(row, 1),
                             weight_byte(row, 0)};
          weight_dmin_o[row] = {weight_byte(row, 3),
                                weight_byte(row, 2)};
        end
        QBS_WEIGHT_PROFILE_Q6_K:
          weight_d_o[row] = {weight_byte(row, 209),
                             weight_byte(row, 208)};
        QBS_WEIGHT_PROFILE_Q3_K:
          weight_d_o[row] = {weight_byte(row, 109),
                             weight_byte(row, 108)};
        QBS_WEIGHT_PROFILE_Q2_K: begin
          weight_d_o[row] = {weight_byte(row, 81),
                             weight_byte(row, 80)};
          weight_dmin_o[row] = {weight_byte(row, 83),
                                weight_byte(row, 82)};
        end
        QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
        QBS_WEIGHT_PROFILE_Q4_0,
        QBS_WEIGHT_PROFILE_Q5_0,
        QBS_WEIGHT_PROFILE_IQ4_NL:
          weight_d_o[row] = {weight_byte(row, 1),
                             weight_byte(row, 0)};
        default: ;
      endcase
      for (int lane = 0; lane < 8; lane++) begin
        weight_quant_o[row][lane] = '0;
        if (row < row_count_i && lane < k_per_context_o)
          weight_quant_o[row][lane] = CompactRead
              ? compact_weight_quant(row, lane, unsigned'(k_base_i) + lane)
              : decode_weight_quant(row, unsigned'(k_base_i) + lane);
      end
    end

    for (int ctx = 0; ctx < 4; ctx++) begin
      activation_d_o[ctx] = '0;
      unique case (activation_profile_i)
        QBS_ACTIVATION_PROFILE_Q8_K:
          activation_d_o[ctx] = {
              activation_byte(ctx, 3), activation_byte(ctx, 2),
              activation_byte(ctx, 1), activation_byte(ctx, 0)};
        QBS_ACTIVATION_PROFILE_Q8_0:
          activation_d_o[ctx] = {16'b0, activation_byte(ctx, 1),
                                 activation_byte(ctx, 0)};
        default: ;
      endcase
      for (int lane = 0; lane < 8; lane++) begin
        activation_quant_o[ctx][lane] = '0;
        if (ctx < m_i && lane < k_per_context_o)
          activation_quant_o[ctx][lane] = CompactRead ? $signed(compact_activation[ctx][lane]) : $signed(activation_byte(ctx,
              (activation_profile_i == QBS_ACTIVATION_PROFILE_Q8_K ? 4 : 2) +
              unsigned'(k_base_i) + lane));
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
              weight_byte(row, 192 + group_index_o));
        end else if (profile_i == QBS_WEIGHT_PROFILE_Q3_K) begin
          group_scale_o[stream] = decode_q3_scale(row, group_index_o);
        end else if (profile_i == QBS_WEIGHT_PROFILE_Q2_K) begin
          group_scale_o[stream] = $signed({4'b0,
              4'(weight_byte(row, group_index_o) >> 0)});
          group_min_o[stream] = {4'b0,
              4'(weight_byte(row, group_index_o) >> 4)};
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
