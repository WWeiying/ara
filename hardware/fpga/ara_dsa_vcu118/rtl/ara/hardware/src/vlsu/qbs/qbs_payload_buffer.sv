// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Four rows/contexts, three independent single-port SRAM planes per row.
// Native block offsets are translated without expanding quantized values.
module qbs_payload_buffer import qbs_pkg::*; #(
  parameter bit NativeView = 1'b1,
  parameter bit PredecodedWriteLocations = 1'b0,
  // The adapter maps bytes of one contiguous 16-byte source beat. Standalone
  // arbitrary-target clients retain the generic last-writer data selection.
  parameter bit StreamWriteData = 1'b0,
  parameter int unsigned ActivationContextBase = 0
) (
  input logic clk_i, rst_ni,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  // Slot 0 is the older pending beat; slot 1 is the accepted input beat.
  input logic [1:0] weight_valid_i, activation_valid_i,
  input logic [31:0] weight_mask_i, activation_mask_i,
  input logic [1:0] weight_row_i [32], activation_context_i [32],
  input logic [7:0] weight_offset_i [32],
  input logic [8:0] activation_offset_i [32],
  input qbs_payload_location_t weight_location_i [32], activation_location_i [32],
  input logic [255:0] weight_data_i, activation_data_i,
  input logic [3:0] weight_source_phase_i [2], activation_source_phase_i [2],
  input qbs_activation_layout_e activation_layout_i,
  output logic [31:0] weight_consumed_o, activation_consumed_o,
  // Independent of live valid: can every slot-0 byte use one word per bank?
  output logic weight_pending_multiword_o, activation_pending_multiword_o,
  input logic weight_read_i, activation_read_i,
  input logic [7:0] read_k_i,
  // Only the payload window addressed by read_k_i is meaningful. Side
  // metadata retains its native indices; repeated payload wires are a view,
  // not a full-block register copy. The profile decoder reads this window.
  output logic [7:0] weight_view_o [4][QbsMaxWeightBlockBytes],
  output logic [7:0] activation_view_o [4][QbsMaxActivationBlockBytes],
  output logic [127:0] weight_window_o [4][2],
  output logic [255:0] activation_window_o [4],
  output logic [7:0] weight_side_o [4][20], activation_side_o [4][36]
);
  localparam int unsigned WeightSideBytes = 20;
  localparam int unsigned ActivationSideBytes = 36;
  logic [7:0] weight_side_q [4][WeightSideBytes];
  logic [7:0] activation_side_q [4][ActivationSideBytes];
  qbs_payload_location_t weight_location [32], activation_location [32];
  logic write_req [2][3][4];
  logic [2:0] write_addr [2][3][4];
  logic [255:0] write_data [2][3][4], read_data [3][4];
  logic [31:0] write_be [2][3][4];
  logic [2:0] read_addr [3];

  always_comb begin
    read_addr[0] = '0;
    read_addr[1] = '0;
    read_addr[2] = activation_profile_i == QBS_ACTIVATION_PROFILE_Q8_K
        ? read_k_i[7:5] : 3'b0;
    case (weight_profile_i)
      QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q5_K: begin
        read_addr[0] = {read_k_i[7:6], read_k_i[4]};
        read_addr[1] = {2'b0, read_k_i[4]};
      end
      QBS_WEIGHT_PROFILE_Q6_K: begin
        read_addr[0] = {read_k_i[7], read_k_i[5:4]};
        read_addr[1] = {1'b0, read_k_i[7], read_k_i[4]};
      end
      QBS_WEIGHT_PROFILE_Q3_K, QBS_WEIGHT_PROFILE_Q2_K: begin
        read_addr[0] = {1'b0, read_k_i[7], read_k_i[4]};
        read_addr[1] = {2'b0, read_k_i[4]};
      end
      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT:
        read_addr[0] = {2'b0, read_k_i[4]};
      default: ;
    endcase
  end

  for (genvar b = 0; b < 32; b++) begin : gen_location
    if (PredecodedWriteLocations) begin : gen_registered
      assign weight_location[b] = weight_location_i[b];
      assign activation_location[b] = activation_location_i[b];
    end else begin : gen_native
      assign weight_location[b] = qbs_weight_payload_location(weight_profile_i, unsigned'(weight_offset_i[b]));
      assign activation_location[b] = qbs_activation_payload_location(activation_profile_i, unsigned'(activation_offset_i[b]));
    end
  end

  logic [15:0] bank_grant [2][3][4];
  logic [3:0] pending_multiword [3];
  logic [31:0] weight_byte_select [16], activation_byte_select [32];
  for (genvar byte_lane = 0; byte_lane < 16; byte_lane++) begin : gen_weight_byte_decode
    for (genvar writer = 0; writer < 32; writer++) begin : gen_writer
      assign weight_byte_select[byte_lane][writer] =
          weight_location[writer].offset[3:0] == 4'(byte_lane);
    end
  end
  for (genvar byte_lane = 0; byte_lane < 32; byte_lane++) begin : gen_activation_byte_decode
    for (genvar writer = 0; writer < 32; writer++) begin : gen_writer
      assign activation_byte_select[byte_lane][writer] =
          activation_location[writer].offset[4:0] == 5'(byte_lane);
    end
  end

  function automatic logic [8:0] last_slot_byte(
      input logic [15:0] hit, input logic [127:0] data);
    logic [8:0] tree [32];
    tree[0] = '0;
    for (int b = 0; b < 16; b++) tree[16+b] = {hit[b], data[8*b +: 8]};
    for (int n = 15; n > 0; n--)
      tree[n] = tree[2*n+1][8] ? tree[2*n+1] : tree[2*n];
    return tree[1];
  endfunction

  // Output byte j is input byte (j + phase) modulo 16. Four fixed stages
  // share the rotation instead of selecting 16 sources at every SRAM byte.
  function automatic logic [127:0] rotate_beat(
      input logic [127:0] data, input logic [3:0] phase);
    logic [127:0] stage [5];
    stage[0] = data;
    for (int s = 0; s < 4; s++)
      for (int b = 0; b < 16; b++)
        stage[s+1][8*b +: 8] = phase[s]
            ? stage[s][8*((b + (1 << s)) % 16) +: 8] : stage[s][8*b +: 8];
    return stage[4];
  endfunction

  // All arguments here are elaboration constants. Only the low four source
  // address bits select data; the existing full-address masks grant writes.
  function automatic int unsigned activation_phase(
      input int unsigned scale, quants, contexts, ctx, b, input bit side);
    int unsigned source_byte;
    if (contexts == 1) source_byte = side ? b : scale + b;
    else if (!side) source_byte = contexts * scale + b * contexts + ctx;
    else if (b < scale) source_byte = ctx * scale + b;
    else source_byte = contexts * (scale + quants) +
        ((b - scale) / 2) * contexts * 2 + ctx * 2 + ((b - scale) % 2);
    return source_byte % 16;
  endfunction

  function automatic logic [7:0] activation_stream_byte(
      input logic [127:0] aligned_data, input qbs_activation_profile_e profile,
      input qbs_activation_layout_e layout, input int unsigned ctx, b, input bit side);
    case (layout)
      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED:
        return profile == QBS_ACTIVATION_PROFILE_Q8_K
            ? aligned_data[8*activation_phase(4, 256, 4, ctx, b, side) +: 8]
            : aligned_data[8*activation_phase(2, 32, 4, ctx, b, side) +: 8];
      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED:
        return profile == QBS_ACTIVATION_PROFILE_Q8_K
            ? aligned_data[8*activation_phase(4, 256, 8, ctx, b, side) +: 8]
            : aligned_data[8*activation_phase(2, 32, 8, ctx, b, side) +: 8];
      default:
        return profile == QBS_ACTIVATION_PROFILE_Q8_K
            ? aligned_data[8*activation_phase(4, 256, 1, ctx, b, side) +: 8]
            : aligned_data[8*activation_phase(2, 32, 1, ctx, b, side) +: 8];
    endcase
  endfunction

  logic [7:0] stream_data [2][3][4][16];
  logic [7:0] stream_weight_side [2][4][16];
  logic [7:0] stream_activation_side [2][4][ActivationSideBytes];
  if (StreamWriteData) begin : gen_stream_data
    wire [3:0] weight_block_phase = 4'(qbs_weight_block_bytes(weight_profile_i));
    for (genvar slot = 0; slot < 2; slot++) begin : gen_slot
      wire [127:0] activation_aligned = rotate_beat(
          activation_data_i[128*slot +: 128], 4'(-activation_source_phase_i[slot]));
      for (genvar row = 0; row < 4; row++) begin : gen_row
        wire [3:0] row_phase = 4'(row) * weight_block_phase - weight_source_phase_i[slot];
        wire [127:0] weight_aligned = rotate_beat(weight_data_i[128*slot +: 128], row_phase);
        for (genvar b = 0; b < 16; b++) begin : gen_byte
          // K formats' region offsets are multiples of 16. Q4_0/Q8_0/IQ4_NL
          // start payload at byte 2, Q5_0 at byte 6; all side phases are zero.
          always_comb begin
            case (weight_profile_i)
              QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
              QBS_WEIGHT_PROFILE_IQ4_NL:
                stream_data[slot][0][row][b] = weight_aligned[8*((b+2)%16) +: 8];
              QBS_WEIGHT_PROFILE_Q5_0:
                stream_data[slot][0][row][b] = weight_aligned[8*((b+6)%16) +: 8];
              default: stream_data[slot][0][row][b] = weight_aligned[8*b +: 8];
            endcase
          end
          assign stream_data[slot][1][row][b] = weight_aligned[8*b +: 8];
          assign stream_weight_side[slot][row][b] = weight_aligned[8*b +: 8];
          assign stream_data[slot][2][row][b] = activation_stream_byte(
              activation_aligned, activation_profile_i, activation_layout_i,
              row + ActivationContextBase, b, 1'b0);
        end
        for (genvar b = 0; b < ActivationSideBytes; b++) begin : gen_side
          assign stream_activation_side[slot][row][b] = activation_stream_byte(
              activation_aligned, activation_profile_i, activation_layout_i,
              row + ActivationContextBase, b, 1'b1);
        end
      end
    end
  end else begin : gen_generic_data
    assign stream_data = '{default:'0};
    assign stream_weight_side = '{default:'0};
    assign stream_activation_side = '{default:'0};
  end

  // Keep byte priority local to one bank. Dynamic bank updates otherwise
  // describe a mux over the entire 3072-bit write-data array at every byte.
  for (genvar slot = 0; slot < 2; slot++) begin : gen_write_merge
    for (genvar p = 0; p < 3; p++) begin : gen_bank_plane
      localparam int WordShift = p == 2 ? 5 : 4;
      localparam int WordBytes = 1 << WordShift;
      for (genvar r = 0; r < 4; r++) begin : gen_bank_row
        logic [15:0] candidate;
        logic [15:0] word_match;
        logic [7:0] offset [16];
        logic [3:0] first_word [32];
        logic [2:0] selected_word;
        wire source_valid = p == 2 ? activation_valid_i[slot] : weight_valid_i[slot];
        wire [127:0] data = p == 2 ? activation_data_i[128*slot +: 128]
                                              : weight_data_i[128*slot +: 128];
        for (genvar b = 0; b < 16; b++) begin : gen_candidate
          localparam int B = 16*slot + b;
          if (p == 2) begin
            assign offset[b] = activation_location[B].offset;
            assign candidate[b] = activation_mask_i[B] &&
                activation_location[B].plane == 0 && activation_context_i[B] == 2'(r);
          end else begin
            assign offset[b] = weight_location[B].offset;
            assign candidate[b] = weight_mask_i[B] &&
                weight_location[B].plane == 2'(p) && weight_row_i[B] == 2'(r);
          end
          assign first_word[16+b] = {candidate[b], offset[b][WordShift +: 3]};
        end
        // Select the first byte's word in four levels, then grant all bytes
        // in that word in parallel. An older slot still owns the bank first.
        assign first_word[0] = '0;
        for (genvar n = 1; n < 16; n++) begin : gen_first_word
          assign first_word[n] = first_word[2*n][3]
              ? first_word[2*n] : first_word[2*n+1];
        end
        if (slot == 0) begin
          logic [2:0] word_bit_conflict;
          for (genvar bit_index = 0; bit_index < 3; bit_index++) begin : gen_word_conflict
            logic [15:0] word_bit;
            for (genvar b = 0; b < 16; b++) begin : gen_bit
              assign word_bit[b] = offset[b][WordShift+bit_index];
            end
            // Distinct words differ in at least one address bit. This test
            // needs neither priority selection nor the consumed-byte path.
            assign word_bit_conflict[bit_index] =
                (|(candidate & word_bit)) && (|(candidate & ~word_bit));
          end
          assign pending_multiword[p][r] = |word_bit_conflict;
          assign selected_word = first_word[1][2:0];
          assign write_req[slot][p][r] = source_valid && first_word[1][3];
          assign write_addr[slot][p][r] = write_req[slot][p][r]
              ? selected_word : 3'b0;
        end else begin
          assign selected_word = write_req[0][p][r]
              ? write_addr[0][p][r] : first_word[1][2:0];
          assign write_req[slot][p][r] = write_req[0][p][r] ||
              (source_valid && first_word[1][3]);
          assign write_addr[slot][p][r] = write_req[slot][p][r]
              ? selected_word : 3'b0;
        end
        for (genvar b = 0; b < 16; b++) begin : gen_word_grant
          assign word_match[b] = candidate[b] && selected_word == offset[b][WordShift +: 3];
          assign bank_grant[slot][p][r][b] = source_valid && word_match[b];
        end
        if (p != 2) begin : gen_unused_upper
          assign write_be[slot][p][r][31:16] = '0;
          assign write_data[slot][p][r][255:128] = '0;
        end
        for (genvar byte_lane = 0; byte_lane < WordBytes; byte_lane++) begin : gen_byte_merge
          wire [15:0] hit = word_match &
              (p == 2 ? activation_byte_select[byte_lane][16*slot +: 16]
                      : weight_byte_select[byte_lane % 16][16*slot +: 16]);
          wire [8:0] selected = StreamWriteData
              ? {(|hit), stream_data[slot][p][r][byte_lane % 16]} : last_slot_byte(hit, data);
`ifdef QBS_STREAM_EQUIV
          if (StreamWriteData) begin : gen_equivalence
            assert property (@(posedge clk_i) disable iff (!rst_ni)
                (source_valid && (|hit)) |->
                ($onehot(hit) && selected == last_slot_byte(hit, data)))
              else $fatal(1, "QBS stream payload selection differs from generic routing");
          end
`endif
          wire byte_valid = source_valid && selected[8];
          if (slot == 0) begin
            assign write_be[slot][p][r][byte_lane] = byte_valid;
            assign write_data[slot][p][r][8*byte_lane +: 8] =
                byte_valid ? selected[7:0] : 8'b0;
          end else begin
            assign write_be[slot][p][r][byte_lane] =
                byte_valid || write_be[0][p][r][byte_lane];
            assign write_data[slot][p][r][8*byte_lane +: 8] = byte_valid
                ? selected[7:0] : write_data[0][p][r][8*byte_lane +: 8];
          end
        end
      end
    end
    for (genvar b = 0; b < 16; b++) begin : gen_consumed
      localparam int B = 16*slot + b;
      logic [7:0] weight_grants;
      logic [3:0] activation_grants;
      for (genvar r = 0; r < 4; r++) begin : gen_row_grant
        assign weight_grants[r] = bank_grant[slot][0][r][b];
        assign weight_grants[4+r] = bank_grant[slot][1][r][b];
        assign activation_grants[r] = bank_grant[slot][2][r][b];
      end
      assign weight_consumed_o[B] = (|weight_grants) ||
          (weight_valid_i[slot] && weight_mask_i[B] && weight_location[B].plane == 2);
      assign activation_consumed_o[B] = (|activation_grants) ||
          (activation_valid_i[slot] && activation_mask_i[B] && activation_location[B].plane == 2);
    end
  end

  assign weight_pending_multiword_o = |pending_multiword[0] || |pending_multiword[1];
  assign activation_pending_multiword_o = |pending_multiword[2];

  for (genvar p = 0; p < 3; p++) begin : gen_plane
    for (genvar r = 0; r < 4; r++) begin : gen_row
      wire rd = p == 2 ? activation_read_i : weight_read_i;
      localparam int DataWidth = p == 2 ? 256 : 128;
      qbs_payload_sram #(.NumWords(p == 1 ? 4 : 8), .DataWidth(DataWidth)) i_payload (
        .clk_i, .rst_ni, .req_i(rd || write_req[1][p][r]), .we_i(write_req[1][p][r]),
        .addr_i(write_req[1][p][r] ? write_addr[1][p][r] : read_addr[p]),
        .wdata_i(write_data[1][p][r][DataWidth-1:0]),
        .be_i(write_be[1][p][r][DataWidth/8-1:0]), .rdata_o(read_data[p][r][DataWidth-1:0])
      );
      if (p != 2) assign read_data[p][r][255:128] = '0;
`ifndef SYNTHESIS
      assert property (@(posedge clk_i) disable iff (!rst_ni)
          !(rd && write_req[1][p][r]))
        else $fatal(1, "QBS payload single-port read/write collision");
`endif
    end
  end

  logic [31:0] weight_side_row [4], activation_side_row [4];
  logic [31:0] weight_side_offset [WeightSideBytes], activation_side_offset [ActivationSideBytes];
  for (genvar n = 0; n < 32; n++) begin : gen_side_decode
    for (genvar row = 0; row < 4; row++) begin : gen_row
      // Side bytes never arbitrate for an SRAM word. Decode their enables
      // directly, without passing through the payload-consumption reduction.
      assign weight_side_row[row][n] = weight_mask_i[n] &&
          weight_location[n].plane == 2 && weight_row_i[n] == 2'(row);
      assign activation_side_row[row][n] = activation_mask_i[n] &&
          activation_location[n].plane == 2 && activation_context_i[n] == 2'(row);
    end
    for (genvar b = 0; b < WeightSideBytes; b++) begin : gen_weight
      assign weight_side_offset[b][n] = weight_location[n].offset == 8'(b);
    end
    for (genvar b = 0; b < ActivationSideBytes; b++) begin : gen_activation
      assign activation_side_offset[b][n] = activation_location[n].offset == 8'(b);
    end
  end

  for (genvar row = 0; row < 4; row++) begin : gen_side_row
    for (genvar b = 0; b < WeightSideBytes; b++) begin : gen_weight_byte
      wire [31:0] hit = weight_side_row[row] & weight_side_offset[b];
      wire [8:0] older = StreamWriteData
          ? {(|hit[15:0]), stream_weight_side[0][row][b % 16]}
          : last_slot_byte(hit[15:0], weight_data_i[127:0]);
      wire [8:0] newer = StreamWriteData
          ? {(|hit[31:16]), stream_weight_side[1][row][b % 16]}
          : last_slot_byte(hit[31:16], weight_data_i[255:128]);
`ifdef QBS_STREAM_EQUIV
      if (StreamWriteData) begin : gen_equivalence
        assert property (@(posedge clk_i) disable iff (!rst_ni)
            (weight_valid_i[0] && (|hit[15:0])) |->
            ($onehot(hit[15:0]) && older == last_slot_byte(hit[15:0], weight_data_i[127:0])))
          else $fatal(1, "QBS old weight metadata selection mismatch");
        assert property (@(posedge clk_i) disable iff (!rst_ni)
            (weight_valid_i[1] && (|hit[31:16])) |->
            ($onehot(hit[31:16]) && newer == last_slot_byte(hit[31:16], weight_data_i[255:128])))
          else $fatal(1, "QBS new weight metadata selection mismatch");
      end
`endif
      wire use_newer = weight_valid_i[1] && newer[8];
      wire enable = use_newer || (weight_valid_i[0] && older[8]);
      // Decode and select data before applying the late input handshake.
      always_ff @(posedge clk_i)
        if (enable) weight_side_q[row][b] <= use_newer ? newer[7:0] : older[7:0];
    end
    for (genvar b = 0; b < ActivationSideBytes; b++) begin : gen_activation_byte
      wire [31:0] hit = activation_side_row[row] & activation_side_offset[b];
      wire [8:0] older = StreamWriteData
          ? {(|hit[15:0]), stream_activation_side[0][row][b]}
          : last_slot_byte(hit[15:0], activation_data_i[127:0]);
      wire [8:0] newer = StreamWriteData
          ? {(|hit[31:16]), stream_activation_side[1][row][b]}
          : last_slot_byte(hit[31:16], activation_data_i[255:128]);
`ifdef QBS_STREAM_EQUIV
      if (StreamWriteData) begin : gen_equivalence
        assert property (@(posedge clk_i) disable iff (!rst_ni)
            (activation_valid_i[0] && (|hit[15:0])) |->
            ($onehot(hit[15:0]) && older == last_slot_byte(hit[15:0], activation_data_i[127:0])))
          else $fatal(1, "QBS old activation metadata selection mismatch");
        assert property (@(posedge clk_i) disable iff (!rst_ni)
            (activation_valid_i[1] && (|hit[31:16])) |->
            ($onehot(hit[31:16]) && newer == last_slot_byte(hit[31:16], activation_data_i[255:128])))
          else $fatal(1, "QBS new activation metadata selection mismatch");
      end
`endif
      wire use_newer = activation_valid_i[1] && newer[8];
      wire enable = use_newer || (activation_valid_i[0] && older[8]);
      always_ff @(posedge clk_i)
        if (enable) activation_side_q[row][b] <= use_newer ? newer[7:0] : older[7:0];
    end
  end

  assign weight_side_o = weight_side_q;
  assign activation_side_o = activation_side_q;
  for (genvar row = 0; row < 4; row++) begin : gen_window
    assign weight_window_o[row][0] = read_data[0][row][127:0];
    assign weight_window_o[row][1] = read_data[1][row][127:0];
    assign activation_window_o[row] = read_data[2][row];
  end

  if (NativeView) begin : gen_native_view
  localparam qbs_weight_profile_e WeightProfiles [9] = '{
    QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q6_K,
    QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q5_K,
    QBS_WEIGHT_PROFILE_Q3_K, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
    QBS_WEIGHT_PROFILE_Q2_K, QBS_WEIGHT_PROFILE_Q5_0,
    QBS_WEIGHT_PROFILE_IQ4_NL
  };
  localparam qbs_activation_profile_e ActivationProfiles [2] = '{
    QBS_ACTIVATION_PROFILE_Q8_K, QBS_ACTIVATION_PROFILE_Q8_0
  };
  logic [7:0] weight_view [9][4][QbsMaxWeightBlockBytes];
  logic [7:0] activation_view [2][4][QbsMaxActivationBlockBytes];

  // Each profile's native-byte mapping is wiring, not an addressable memory.
  // Resolve indices at elaboration, then select the profile's byte value.
  for (genvar f = 0; f < 9; f++) begin : gen_weight_view
    for (genvar row = 0; row < 4; row++) begin : gen_row
      for (genvar b = 0; b < QbsMaxWeightBlockBytes; b++) begin : gen_byte
        localparam qbs_payload_location_t Loc = qbs_weight_payload_location(WeightProfiles[f], b);
        if (b >= qbs_weight_block_bytes(WeightProfiles[f])) begin
          assign weight_view[f][row][b] = '0;
        end else if (Loc.plane == 2) begin
          assign weight_view[f][row][b] = weight_side_q[row][Loc.offset];
        end else begin
          assign weight_view[f][row][b] =
              read_data[Loc.plane][row][8*Loc.offset[3:0] +: 8];
        end
      end
    end
  end
  for (genvar f = 0; f < 2; f++) begin : gen_activation_view
    for (genvar row = 0; row < 4; row++) begin : gen_row
      for (genvar b = 0; b < QbsMaxActivationBlockBytes; b++) begin : gen_byte
        localparam qbs_payload_location_t Loc = qbs_activation_payload_location(ActivationProfiles[f], b);
        if (b >= qbs_activation_block_bytes(ActivationProfiles[f])) begin
          assign activation_view[f][row][b] = '0;
        end else if (Loc.plane == 2) begin
          assign activation_view[f][row][b] = activation_side_q[row][Loc.offset];
        end else begin
          assign activation_view[f][row][b] = read_data[2][row][8*Loc.offset[4:0] +: 8];
        end
      end
    end
  end
  for (genvar row = 0; row < 4; row++) begin : gen_view_select
    for (genvar b = 0; b < QbsMaxWeightBlockBytes; b++) begin : gen_weight_byte
      always_comb begin
        case (weight_profile_i)
          QBS_WEIGHT_PROFILE_Q4_K:        weight_view_o[row][b] = weight_view[0][row][b];
          QBS_WEIGHT_PROFILE_Q6_K:        weight_view_o[row][b] = weight_view[1][row][b];
          QBS_WEIGHT_PROFILE_Q4_0:        weight_view_o[row][b] = weight_view[2][row][b];
          QBS_WEIGHT_PROFILE_Q5_K:        weight_view_o[row][b] = weight_view[3][row][b];
          QBS_WEIGHT_PROFILE_Q3_K:        weight_view_o[row][b] = weight_view[4][row][b];
          QBS_WEIGHT_PROFILE_Q8_0_WEIGHT: weight_view_o[row][b] = weight_view[5][row][b];
          QBS_WEIGHT_PROFILE_Q2_K:        weight_view_o[row][b] = weight_view[6][row][b];
          QBS_WEIGHT_PROFILE_Q5_0:        weight_view_o[row][b] = weight_view[7][row][b];
          QBS_WEIGHT_PROFILE_IQ4_NL:      weight_view_o[row][b] = weight_view[8][row][b];
          default:                      weight_view_o[row][b] = '0;
        endcase
      end
    end
    for (genvar b = 0; b < QbsMaxActivationBlockBytes; b++) begin : gen_activation_byte
      always_comb begin
        case (activation_profile_i)
          QBS_ACTIVATION_PROFILE_Q8_K: activation_view_o[row][b] = activation_view[0][row][b];
          QBS_ACTIVATION_PROFILE_Q8_0: activation_view_o[row][b] = activation_view[1][row][b];
          default:                   activation_view_o[row][b] = '0;
        endcase
      end
    end
  end
  end else begin : gen_no_native_view
    for (genvar row = 0; row < 4; row++) begin : gen_row
      for (genvar b = 0; b < QbsMaxWeightBlockBytes; b++) begin : gen_weight
        assign weight_view_o[row][b] = '0;
      end
      for (genvar b = 0; b < QbsMaxActivationBlockBytes; b++) begin : gen_activation
        assign activation_view_o[row][b] = '0;
      end
    end
  end
endmodule
