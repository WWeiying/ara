// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_block_adapter import qbs_pkg::*; #(
  parameter int unsigned ActivationContextBase = 0,
  parameter bit NativeView = 1'b1,
  // The integrated range reader/replay writes each block byte once between
  // clears. Generic clients may rewrite bytes and retain bitmap tracking.
  parameter bit UniqueInputBytes = 1'b0
) (
  input  logic                    clk_i,
  input  logic                    rst_ni,

  input  logic                    clear_weight_i,
  input  logic                    clear_activation_i,
  input  qbs_weight_profile_e     weight_profile_i,
  input  qbs_activation_profile_e activation_profile_i,
  input  logic [2:0]              weight_row_count_i,
  input  qbs_activation_layout_e  activation_layout_i,
  input  logic [3:0]              m_i,

  // A row-major range carries one native block. An R4 range may concatenate
  // all active row blocks; byte-level steering handles beats that cross a
  // native-block boundary without padding or a second AXI request.
  input  logic                    weight_write_valid_i,
  output logic                    weight_write_ready_o,
  input  logic                    weight_write_group_i,
  input  logic [1:0]              weight_write_row_i,
  input  logic [9:0]              weight_write_offset_i,
  input  logic [127:0]            weight_write_data_i,
  input  logic [15:0]             weight_write_strb_i,

  // Row-major ranges target one context. M4 ranges concatenate four scales,
  // byte-interleave four quant payloads, then element-interleave auxiliary
  // arrays. The profile metadata determines each region's fixed geometry.
  input  logic                    activation_write_valid_i,
  output logic                    activation_write_ready_o,
  input  logic [1:0]              activation_write_context_i,
  input  logic [11:0]             activation_write_offset_i,
  input  logic [127:0]            activation_write_data_i,
  input  logic [15:0]             activation_write_strb_i,

  input  logic                    weight_read_i,
  input  logic                    activation_read_i,
  input  logic [7:0]              read_k_i,
  // Native-index view of the synchronous payload window, not a full block.
  output logic [7:0]              weight_block_o [4][QbsMaxWeightBlockBytes],
  output logic [7:0]              activation_block_o [4][QbsMaxActivationBlockBytes],
  output logic [255:0] weight_window_o [4][2], activation_window_o [4],
  output logic [7:0] weight_side_o [4][20], activation_side_o [4][36],
  output logic [3:0]              weight_complete_o,
  output logic [3:0]              activation_complete_o,
  output logic                    all_weight_complete_o,
  output logic                    all_activation_complete_o,
  output logic [31:0]             accepted_weight_bytes_o,
  output logic [31:0]             accepted_activation_bytes_o
);

  logic weight_byte_valid_q [4][QbsMaxWeightBlockBytes];
  logic activation_byte_valid_q [4][QbsMaxActivationBlockBytes];
`ifdef SYNTHESIS
  localparam bit TrackByteValid = !UniqueInputBytes;
`else
  // Simulation keeps the exact bitmap as a contract oracle, not hardware.
  localparam bit TrackByteValid = 1'b1;
`endif
  logic [$clog2(QbsMaxWeightBlockBytes+1)-1:0] weight_committed_q [4];
  logic [$clog2(QbsMaxActivationBlockBytes+1)-1:0] activation_committed_q [4];
  logic [2:0] activation_context_count;

  localparam int unsigned WeightOffsetWidth = $clog2(QbsMaxWeightBlockBytes);
  localparam int unsigned ActivationOffsetWidth = $clog2(QbsMaxActivationBlockBytes);

  typedef struct packed {
    logic valid;
    logic [1:0] row;
    logic [WeightOffsetWidth-1:0] offset;
  } weight_target_t;
  typedef struct packed {
    logic valid;
    logic [1:0] ctx;
    logic [ActivationOffsetWidth-1:0] offset;
  } activation_target_t;
  weight_target_t weight_target [32];
  activation_target_t activation_target [32];
  logic [31:0] new_weight_mask, new_activation_mask;
  logic [5:0] new_weight_bytes, new_activation_bytes;

  typedef struct packed {
    logic group_mode;
    logic [1:0] row;
    logic [9:0] offset;
    logic [127:0] data;
    logic [15:0] strb;
  } weight_beat_t;
  typedef struct packed {
    logic [1:0] ctx;
    logic [11:0] offset;
    logic [127:0] data;
    logic [15:0] strb;
  } activation_beat_t;
  weight_beat_t weight_pending_q, weight_source [2];
  activation_beat_t activation_pending_q, activation_source [2];
  weight_beat_t weight_input, weight_ingress_q [2];
  activation_beat_t activation_input, activation_ingress_q [2];
  weight_target_t weight_input_target [16], weight_ingress_target_q [2][16];
  activation_target_t activation_input_target [16], activation_ingress_target_q [2][16];
  weight_target_t weight_pending_target_q [16];
  activation_target_t activation_pending_target_q [16];
  qbs_payload_location_t weight_input_location [16], activation_input_location [16];
  qbs_payload_location_t weight_ingress_location_q [2][16], activation_ingress_location_q [2][16];
  qbs_payload_location_t weight_pending_location_q [16], activation_pending_location_q [16];
  qbs_payload_location_t weight_location [32], activation_location [32];
  logic weight_ingress_rd_q, weight_ingress_wr_q, activation_ingress_rd_q, activation_ingress_wr_q;
  logic [1:0] weight_ingress_count_q, activation_ingress_count_q;
  logic weight_ingress_push, activation_ingress_push;
  logic weight_write_pending, activation_write_pending;
  logic weight_pending_q_valid, activation_pending_q_valid;
  logic [1:0] weight_source_valid, activation_source_valid;
  logic [31:0] weight_mask, activation_mask;
  logic [31:0] weight_consumed, activation_consumed;
  logic [31:0] weight_remaining, activation_remaining;
  logic weight_pending_multiword, activation_pending_multiword;
  logic [1:0] weight_rows [32], activation_contexts [32];
  logic [7:0] weight_offsets [32];
  logic [8:0] activation_offsets [32];
  logic [12:0] weight_source_base [2], activation_source_base [2];
  logic [3:0] weight_source_phase [2], activation_source_phase [2];
  logic [15:0] weight_duplicate_mask, activation_duplicate_mask;

  // Decode once at acceptance. Two entries separate upstream ready from SRAM
  // arbitration and sustain one beat/cycle with simultaneous push and pop.
  assign weight_write_ready_o = weight_ingress_count_q < 2 &&
      !clear_weight_i && !weight_read_i;
  assign activation_write_ready_o = activation_ingress_count_q < 2 &&
      !clear_activation_i && !activation_read_i;
  assign weight_ingress_push = weight_write_valid_i && weight_write_ready_o;
  assign activation_ingress_push = activation_write_valid_i && activation_write_ready_o;
  assign weight_write_pending = weight_pending_q_valid || weight_ingress_count_q != 0;
  assign activation_write_pending = activation_pending_q_valid || activation_ingress_count_q != 0;
  assign weight_source[0] = weight_pending_q;
  assign activation_source[0] = activation_pending_q;
  assign weight_input =
      {weight_write_group_i, weight_write_row_i, weight_write_offset_i,
       weight_write_data_i, weight_write_strb_i};
  assign activation_input =
      {activation_write_context_i, activation_write_offset_i,
       activation_write_data_i, activation_write_strb_i};
  assign weight_source[1] = weight_ingress_q[weight_ingress_rd_q];
  assign activation_source[1] = activation_ingress_q[activation_ingress_rd_q];
  assign weight_source_valid[0] = weight_pending_q_valid && !clear_weight_i;
  assign activation_source_valid[0] = activation_pending_q_valid && !clear_activation_i;
  assign weight_source_valid[1] = weight_ingress_count_q != 0 &&
      (!weight_pending_q_valid || !weight_pending_multiword) &&
      !clear_weight_i && !weight_read_i;
  assign activation_source_valid[1] = activation_ingress_count_q != 0 &&
      (!activation_pending_q_valid || !activation_pending_multiword) &&
      !clear_activation_i && !activation_read_i;
  assign weight_remaining = weight_mask & ~weight_consumed;
  assign activation_remaining = activation_mask & ~activation_consumed;

  for (genvar b = 0; b < 32; b++) begin : gen_payload_targets
    assign weight_mask[b] = weight_target[b].valid;
    assign activation_mask[b] = activation_target[b].valid;
    assign weight_rows[b] = weight_target[b].row;
    assign activation_contexts[b] = activation_target[b].ctx;
    assign weight_offsets[b] = weight_target[b].offset;
    assign activation_offsets[b] = activation_target[b].offset;
  end

  for (genvar slot = 0; slot < 2; slot++) begin : gen_stream_phase
    assign weight_source_phase[slot] = weight_source_base[slot][3:0];
    // Row-major activation ranges already carry an explicit context. Packed
    // M4/M8 ranges carry the global interleaved offset in this same field.
    assign activation_source_phase[slot] = activation_source[slot].offset[3:0];
  end

  qbs_payload_buffer #(.NativeView(NativeView), .PredecodedWriteLocations(1'b1),
      .StreamWriteData(1'b1), .ActivationContextBase(ActivationContextBase)) i_payload_buffer (
    .clk_i, .rst_ni, .weight_profile_i, .activation_profile_i,
    .weight_valid_i(weight_source_valid), .activation_valid_i(activation_source_valid),
    .weight_mask_i(weight_mask), .activation_mask_i(activation_mask),
    .weight_row_i(weight_rows), .weight_offset_i(weight_offsets),
    .activation_context_i(activation_contexts), .activation_offset_i(activation_offsets),
    .weight_location_i(weight_location), .activation_location_i(activation_location),
    .weight_data_i({weight_source[1].data, weight_source[0].data}),
    .activation_data_i({activation_source[1].data, activation_source[0].data}),
    .weight_source_phase_i(weight_source_phase), .activation_source_phase_i(activation_source_phase),
    .activation_layout_i,
    .weight_consumed_o(weight_consumed), .activation_consumed_o(activation_consumed),
    .weight_pending_multiword_o(weight_pending_multiword),
    .activation_pending_multiword_o(activation_pending_multiword),
    .weight_read_i, .activation_read_i, .read_k_i,
    .weight_view_o(weight_block_o), .activation_view_o(activation_block_o),
    .weight_window_o, .activation_window_o, .weight_side_o, .activation_side_o
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      weight_ingress_count_q <= '0;
      activation_ingress_count_q <= '0;
      weight_ingress_rd_q <= 1'b0;
      weight_ingress_wr_q <= 1'b0;
      activation_ingress_rd_q <= 1'b0;
      activation_ingress_wr_q <= 1'b0;
    end else begin
      if (clear_weight_i) begin
        weight_ingress_count_q <= '0;
        weight_ingress_rd_q <= 1'b0;
        weight_ingress_wr_q <= 1'b0;
      end else begin
        case ({weight_ingress_push, weight_source_valid[1]})
          2'b10: weight_ingress_count_q <= weight_ingress_count_q + 1'b1;
          2'b01: weight_ingress_count_q <= weight_ingress_count_q - 1'b1;
          default: ;
        endcase
        if (weight_ingress_push) weight_ingress_wr_q <= ~weight_ingress_wr_q;
        if (weight_source_valid[1]) weight_ingress_rd_q <= ~weight_ingress_rd_q;
      end
      if (clear_activation_i) begin
        activation_ingress_count_q <= '0;
        activation_ingress_rd_q <= 1'b0;
        activation_ingress_wr_q <= 1'b0;
      end else begin
        case ({activation_ingress_push, activation_source_valid[1]})
          2'b10: activation_ingress_count_q <= activation_ingress_count_q + 1'b1;
          2'b01: activation_ingress_count_q <= activation_ingress_count_q - 1'b1;
          default: ;
        endcase
        if (activation_ingress_push) activation_ingress_wr_q <= ~activation_ingress_wr_q;
        if (activation_source_valid[1]) activation_ingress_rd_q <= ~activation_ingress_rd_q;
      end
    end
  end

  for (genvar entry = 0; entry < 2; entry++) begin : gen_ingress_storage
    always_ff @(posedge clk_i) begin
      if (weight_ingress_push && weight_ingress_wr_q == 1'(entry)) begin
        weight_ingress_q[entry] <= weight_input;
        for (int b = 0; b < 16; b++) begin
          weight_ingress_target_q[entry][b] <= weight_input_target[b];
          weight_ingress_location_q[entry][b] <= weight_input_location[b];
        end
      end
      if (activation_ingress_push && activation_ingress_wr_q == 1'(entry)) begin
        activation_ingress_q[entry] <= activation_input;
        for (int b = 0; b < 16; b++) begin
          activation_ingress_target_q[entry][b] <= activation_input_target[b];
          activation_ingress_location_q[entry][b] <= activation_input_location[b];
        end
      end
    end
  end

  for (genvar b = 0; b < 16; b++) begin : gen_registered_targets
    assign weight_input_location[b] = qbs_weight_payload_location(
        weight_profile_i, unsigned'(weight_input_target[b].offset));
    assign activation_input_location[b] = qbs_activation_payload_location(
        activation_profile_i, unsigned'(activation_input_target[b].offset));
    assign weight_target[b] = {
        weight_pending_target_q[b].valid && weight_pending_q.strb[b],
        weight_pending_target_q[b].row, weight_pending_target_q[b].offset};
    assign activation_target[b] = {
        activation_pending_target_q[b].valid && activation_pending_q.strb[b],
        activation_pending_target_q[b].ctx, activation_pending_target_q[b].offset};
    assign weight_target[16+b] = weight_ingress_target_q[weight_ingress_rd_q][b];
    assign activation_target[16+b] = activation_ingress_target_q[activation_ingress_rd_q][b];
    assign weight_location[b] = weight_pending_location_q[b];
    assign activation_location[b] = activation_pending_location_q[b];
    assign weight_location[16+b] = weight_ingress_location_q[weight_ingress_rd_q][b];
    assign activation_location[16+b] = activation_ingress_location_q[activation_ingress_rd_q][b];
    always_ff @(posedge clk_i) begin
      if (weight_source_valid[1] && (|weight_remaining[31:16])) begin
        weight_pending_target_q[b] <= weight_target[16+b];
        weight_pending_location_q[b] <= weight_location[16+b];
      end
      if (activation_source_valid[1] && (|activation_remaining[31:16])) begin
        activation_pending_target_q[b] <= activation_target[16+b];
        activation_pending_location_q[b] <= activation_location[16+b];
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      weight_pending_q_valid <= 1'b0;
      activation_pending_q_valid <= 1'b0;
      weight_pending_q <= '0;
      activation_pending_q <= '0;
    end else begin
      if (clear_weight_i) weight_pending_q_valid <= 1'b0;
      else if (weight_source_valid[1]) begin
        weight_pending_q_valid <= |weight_remaining[31:16];
        if (|weight_remaining[31:16]) begin
          weight_pending_q <= weight_source[1];
          weight_pending_q.strb <= weight_remaining[31:16];
        end
      end else if (weight_source_valid[0]) begin
        weight_pending_q_valid <= |weight_remaining[15:0];
        weight_pending_q.strb <= weight_remaining[15:0];
      end
      if (clear_activation_i) activation_pending_q_valid <= 1'b0;
      else if (activation_source_valid[1]) begin
        activation_pending_q_valid <= |activation_remaining[31:16];
        if (|activation_remaining[31:16]) begin
          activation_pending_q <= activation_source[1];
          activation_pending_q.strb <= activation_remaining[31:16];
        end
      end else if (activation_source_valid[0]) begin
        activation_pending_q_valid <= |activation_remaining[15:0];
        activation_pending_q.strb <= activation_remaining[15:0];
      end
    end
  end

  function automatic logic [4:0] count_beat_bytes(input logic [15:0] mask);
    logic [1:0] pairs [8];
    logic [2:0] quads [4];
    logic [3:0] octets [2];
    for (int i = 0; i < 8; i++)
      pairs[i] = {1'b0, mask[2*i]} + {1'b0, mask[2*i+1]};
    for (int i = 0; i < 4; i++)
      quads[i] = {1'b0, pairs[2*i]} + {1'b0, pairs[2*i+1]};
    for (int i = 0; i < 2; i++)
      octets[i] = {1'b0, quads[2*i]} + {1'b0, quads[2*i+1]};
    return {1'b0, octets[0]} + {1'b0, octets[1]};
  endfunction

  // Align older committed strobes with the input beat's source byte indices.
  // This avoids counting a byte twice when the newer beat overwrites an older
  // pending byte in the same physical SRAM write.
  function automatic logic [15:0] overlapping_bytes(
      input logic [15:0] older_mask,
      input logic [12:0] older_base, newer_base);
    logic [12:0] distance;
    if (newer_base >= older_base) begin
      distance = newer_base - older_base;
      return distance < 16 ? older_mask >> distance[3:0] : 16'b0;
    end
    distance = older_base - newer_base;
    return distance < 16 ? older_mask << distance[3:0] : 16'b0;
  endfunction

  for (genvar slot = 0; slot < 2; slot++) begin : gen_source_base
    assign weight_source_base[slot] = 13'(weight_source[slot].offset) +
        (weight_source[slot].group_mode ? 13'b0 :
         13'(unsigned'(weight_source[slot].row) * qbs_weight_block_bytes(weight_profile_i)));
    assign activation_source_base[slot] = 13'(activation_source[slot].offset) +
        (activation_layout_i != QBS_ACTIVATION_LAYOUT_ROW_MAJOR ? 13'b0 :
         13'(unsigned'(activation_source[slot].ctx) * qbs_activation_block_bytes(activation_profile_i)));
  end
  assign weight_duplicate_mask = overlapping_bytes(weight_consumed[15:0],
      weight_source_base[0], weight_source_base[1]);
  assign activation_duplicate_mask = overlapping_bytes(activation_consumed[15:0],
      activation_source_base[0], activation_source_base[1]);

  // Constant mapping helper stays at module scope for VCS/DC elaboration.
  function automatic int activation_valid_index(
      input int index, block_bytes, scale_bytes, quant_bytes, contexts);
    int ctx, offset, relative;
    if (contexts == 1) begin
      ctx = index / block_bytes;
      offset = index % block_bytes;
    end else if (index >= contexts * block_bytes) begin
      return -1;
    end else if (index < contexts * scale_bytes) begin
      ctx = index / scale_bytes;
      offset = index % scale_bytes;
    end else if (index < contexts * (scale_bytes + quant_bytes)) begin
      relative = index - contexts * scale_bytes;
      ctx = relative % contexts;
      offset = scale_bytes + relative / contexts;
    end else begin
      relative = index - contexts * (scale_bytes + quant_bytes);
      ctx = (relative / 2) % contexts;
      offset = scale_bytes + quant_bytes + (relative / (2 * contexts)) * 2 + relative % 2;
    end
    if ((contexts == 1 && ctx >= 4) || ctx < ActivationContextBase ||
        ctx >= ActivationContextBase + 4) return -1;
    return (ctx - ActivationContextBase) * QbsMaxActivationBlockBytes + offset;
  endfunction

  // These views only permute existing valid bits into source byte order.
  // Two 16-bit windows replace 32 independent full-block bit lookups.
  if (!UniqueInputBytes) begin : gen_byte_history
  localparam int WeightLinearBits = 4 * QbsMaxWeightBlockBytes;
  localparam int ActivationLinearBits = QbsMaxM * QbsMaxActivationBlockBytes;
  localparam int WeightWindowCount = (WeightLinearBits + 15) / 16;
  localparam int ActivationWindowCount = (ActivationLinearBits + 15) / 16;
  logic [WeightLinearBits-1:0] weight_valid_view [9];
  logic [ActivationLinearBits-1:0] activation_valid_view [6];
  logic [16*WeightWindowCount+15:0] weight_linear_valid;
  logic [16*ActivationWindowCount+15:0] activation_linear_valid;
  wire [31:0] weight_valid_window [WeightWindowCount];
  wire [31:0] activation_valid_window [ActivationWindowCount];
  logic [15:0] weight_seen [2], activation_seen [2];

  for (genvar profile = 0; profile < 9; profile++) begin : gen_weight_valid_view
    localparam int Bytes = qbs_weight_block_bytes(qbs_weight_profile_e'(profile + 1));
    for (genvar index = 0; index < WeightLinearBits; index++) begin : gen_bit
      if (index < 4 * Bytes) begin : gen_native
        assign weight_valid_view[profile][index] = weight_byte_valid_q[index/Bytes][index%Bytes];
      end else begin : gen_padding
        assign weight_valid_view[profile][index] = 1'b0;
      end
    end
  end

  for (genvar profile = 0; profile < 2; profile++) begin : gen_activation_valid_view
    localparam qbs_activation_profile_e Profile = qbs_activation_profile_e'(profile + 1);
    for (genvar layout_index = 0; layout_index < 3; layout_index++) begin : gen_layout
      localparam int Contexts = layout_index == 0 ? 1 : layout_index == 1 ? 4 : QbsMaxM;
      for (genvar index = 0; index < ActivationLinearBits; index++) begin : gen_bit
        localparam int NativeIndex = activation_valid_index(index,
            qbs_activation_block_bytes(Profile), qbs_activation_scale_bytes(Profile),
            qbs_activation_quant_bytes(Profile), Contexts);
        if (NativeIndex >= 0) begin : gen_native
          assign activation_valid_view[3*profile+layout_index][index] =
              activation_byte_valid_q[NativeIndex/QbsMaxActivationBlockBytes]
                                     [NativeIndex%QbsMaxActivationBlockBytes];
        end else begin : gen_padding
          assign activation_valid_view[3*profile+layout_index][index] = 1'b0;
        end
      end
    end
  end

  always_comb begin
    weight_linear_valid = '0;
    case (weight_profile_i)
      QBS_WEIGHT_PROFILE_Q4_K: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[0];
      QBS_WEIGHT_PROFILE_Q6_K: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[1];
      QBS_WEIGHT_PROFILE_Q4_0: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[2];
      QBS_WEIGHT_PROFILE_Q5_K: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[3];
      QBS_WEIGHT_PROFILE_Q3_K: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[4];
      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[5];
      QBS_WEIGHT_PROFILE_Q2_K: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[6];
      QBS_WEIGHT_PROFILE_Q5_0: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[7];
      QBS_WEIGHT_PROFILE_IQ4_NL: weight_linear_valid[WeightLinearBits-1:0] = weight_valid_view[8];
      default: ;
    endcase
    activation_linear_valid = '0;
    case (activation_profile_i)
      QBS_ACTIVATION_PROFILE_Q8_K:
        case (activation_layout_i)
          QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED:
            activation_linear_valid[ActivationLinearBits-1:0] = activation_valid_view[1];
          QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED:
            activation_linear_valid[ActivationLinearBits-1:0] = activation_valid_view[2];
          default: activation_linear_valid[ActivationLinearBits-1:0] = activation_valid_view[0];
        endcase
      QBS_ACTIVATION_PROFILE_Q8_0:
        case (activation_layout_i)
          QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED:
            activation_linear_valid[ActivationLinearBits-1:0] = activation_valid_view[4];
          QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED:
            activation_linear_valid[ActivationLinearBits-1:0] = activation_valid_view[5];
          default: activation_linear_valid[ActivationLinearBits-1:0] = activation_valid_view[3];
        endcase
      default: ;
    endcase
  end

  for (genvar group_index = 0; group_index < WeightWindowCount; group_index++) begin : gen_weight_window
    assign weight_valid_window[group_index] = weight_linear_valid[16*group_index +: 32];
  end
  for (genvar group_index = 0; group_index < ActivationWindowCount; group_index++) begin : gen_activation_window
    assign activation_valid_window[group_index] = activation_linear_valid[16*group_index +: 32];
  end
  for (genvar slot = 0; slot < 2; slot++) begin : gen_seen_window
    logic [12:0] activation_base;
    // The mapping's default layout is row-major; preserve it for idle inputs.
    assign activation_base = activation_source[slot].offset +
        ((activation_layout_i inside {QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
                                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED}) ? 13'b0 :
         13'(unsigned'(activation_source[slot].ctx) * qbs_activation_block_bytes(activation_profile_i)));
    always_comb begin
      weight_seen[slot] = '0;
      activation_seen[slot] = '0;
      if (weight_source_base[slot] < WeightLinearBits)
        weight_seen[slot] = 16'(weight_valid_window[
            weight_source_base[slot][4 +: $clog2(WeightWindowCount)]] >> weight_source_base[slot][3:0]);
      if (activation_base < ActivationLinearBits)
        activation_seen[slot] = 16'(activation_valid_window[
            activation_base[4 +: $clog2(ActivationWindowCount)]] >> activation_base[3:0]);
    end
    for (genvar b = 0; b < 16; b++) begin : gen_new_byte
      assign new_weight_mask[16*slot+b] = weight_target[16*slot+b].valid &&
          !weight_seen[slot][b] && (slot == 0 || !weight_duplicate_mask[b]);
      assign new_activation_mask[16*slot+b] = activation_target[16*slot+b].valid &&
          !activation_seen[slot][b] && (slot == 0 || !activation_duplicate_mask[b]);
    end
  end
  end else begin : gen_unique_bytes
    assign new_weight_mask = weight_mask;
    assign new_activation_mask = activation_mask;
  end

  // Complete each byte reduction before applying the live row/context count.
  // A response's row count can arrive through a late valid-qualified mux.
  always_comb begin : check_completion
    int unsigned weight_bytes;
    int unsigned activation_bytes;
    logic [3:0] weight_missing, activation_missing;
    weight_bytes = qbs_weight_block_bytes(weight_profile_i);
    activation_bytes = qbs_activation_block_bytes(activation_profile_i);
    weight_missing = '0;
    activation_missing = '0;
    weight_complete_o = '0;
    activation_complete_o = '0;

    activation_context_count = '0;
    if (activation_layout_i == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED)
      activation_context_count = 3'd4;
    else if (ActivationContextBase == 0 && unsigned'(m_i) <= 4)
      activation_context_count = 3'(m_i);

    for (int row = 0; row < 4; row++) begin
      logic [QbsMaxWeightBlockBytes-1:0] byte_complete;
      logic row_complete;
      for (int byte_index = 0; byte_index < QbsMaxWeightBlockBytes; byte_index++)
        byte_complete[byte_index] = byte_index >= weight_bytes ||
                                   weight_byte_valid_q[row][byte_index];
      row_complete = UniqueInputBytes ? unsigned'(weight_committed_q[row]) == weight_bytes
                                      : (&byte_complete);
      weight_complete_o[row] = row < weight_row_count_i && row_complete &&
                               !weight_write_pending;
      weight_missing[row] = row < weight_row_count_i && !row_complete;
    end
    all_weight_complete_o = (weight_row_count_i inside {[1:4]}) &&
                            !(|weight_missing) && !weight_write_pending;

    for (int ctx = 0; ctx < 4; ctx++) begin
      logic [QbsMaxActivationBlockBytes-1:0] byte_complete;
      logic row_complete;
      for (int byte_index = 0; byte_index < QbsMaxActivationBlockBytes; byte_index++)
        byte_complete[byte_index] = byte_index >= activation_bytes ||
                                   activation_byte_valid_q[ctx][byte_index];
      row_complete = UniqueInputBytes ? unsigned'(activation_committed_q[ctx]) == activation_bytes
                                      : (&byte_complete);
      activation_complete_o[ctx] = ctx < activation_context_count && row_complete &&
                                   !activation_write_pending;
      activation_missing[ctx] = ctx < activation_context_count && !row_complete;
    end
    all_activation_complete_o = (m_i inside {[1:QbsMaxM]}) &&
                                !(|activation_missing) && !activation_write_pending;
  end

  // The first stage maps the incoming beat; stored targets drive SRAM
  // arbitration in the next stage. Counters advance only on actual commits.
  always_comb begin : map_weight_bytes
    for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
      automatic int unsigned source_offset =
          unsigned'(weight_input.offset) + beat_byte;
      automatic int unsigned target_row;
      automatic int unsigned target_offset;
      automatic int unsigned block_bytes;
      automatic logic mapping_valid;

      block_bytes = qbs_weight_block_bytes(weight_profile_i);
      target_row = unsigned'(weight_input.row);
      target_offset = source_offset;

      // The native block size is profile-dependent. At most four row
      // banks are active, so range comparisons avoid a divider.
      if (weight_input.group_mode) begin
        if (source_offset >= 3 * block_bytes) begin
          target_row = 3;
          target_offset = source_offset - 3 * block_bytes;
        end else if (source_offset >= 2 * block_bytes) begin
          target_row = 2;
          target_offset = source_offset - 2 * block_bytes;
        end else if (source_offset >= block_bytes) begin
          target_row = 1;
          target_offset = source_offset - block_bytes;
        end else begin
          target_row = 0;
        end
      end

      mapping_valid = target_row < unsigned'(weight_row_count_i) &&
                      target_offset < block_bytes;
      weight_input_target[beat_byte].valid = weight_input.strb[beat_byte] &&
                                       mapping_valid;
      weight_input_target[beat_byte].row = 2'(target_row);
      weight_input_target[beat_byte].offset = WeightOffsetWidth'(target_offset);
    end
  end

  always_comb begin : map_activation_bytes
    for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
      automatic int unsigned source_offset =
          unsigned'(activation_input.offset) + beat_byte;
      automatic int unsigned target_context;
      automatic int unsigned target_local_context;
      automatic int unsigned target_offset;
      automatic int unsigned block_bytes;
      automatic int unsigned scale_bytes;
      automatic int unsigned quant_bytes;
      automatic int unsigned aux_count;
      automatic int unsigned aux_element_bytes;
      automatic logic mapping_valid;

      block_bytes = qbs_activation_block_bytes(activation_profile_i);
      scale_bytes = qbs_activation_scale_bytes(activation_profile_i);
      quant_bytes = qbs_activation_quant_bytes(activation_profile_i);
      aux_count = qbs_activation_aux_count(activation_profile_i);
      aux_element_bytes =
          qbs_activation_aux_element_bytes(activation_profile_i);
      target_context = unsigned'(activation_input.ctx);
      target_offset = source_offset;
      mapping_valid = source_offset < block_bytes;

      if (activation_layout_i ==
          QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED) begin
        automatic int unsigned scale_region_bytes = 4 * scale_bytes;
        automatic int unsigned quant_region_end =
            scale_region_bytes + 4 * quant_bytes;
        mapping_valid = source_offset < 4 * block_bytes;
        if (source_offset < scale_region_bytes) begin
          // Supported activation scales are two or four bytes. Keeping
          // both mappings explicit avoids a variable divider in RTL.
          if (scale_bytes == 2) begin
            target_context = source_offset >> 1;
            target_offset = source_offset & 1;
          end else begin
            target_context = source_offset >> 2;
            target_offset = source_offset & 3;
          end
        end else if (source_offset < quant_region_end) begin
          automatic int unsigned packed_qs =
              source_offset - scale_region_bytes;
          target_context = packed_qs & 3;
          target_offset = scale_bytes + (packed_qs >> 2);
        end else begin
          automatic int unsigned packed_aux_byte =
              source_offset - quant_region_end;
          automatic int unsigned packed_aux;
          if (aux_element_bytes == 2) begin
            packed_aux = packed_aux_byte >> 1;
            target_context = packed_aux & 3;
            target_offset = scale_bytes + quant_bytes +
                (packed_aux >> 2) * 2 + (packed_aux_byte & 1);
          end else begin
            mapping_valid = 1'b0;
          end
          mapping_valid &= packed_aux_byte <
              4 * aux_count * aux_element_bytes;
        end
      end else if (activation_layout_i ==
                   QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED) begin
        automatic int unsigned scale_region_bytes =
            QbsMaxM * scale_bytes;
        automatic int unsigned quant_region_end =
            scale_region_bytes + QbsMaxM * quant_bytes;
        mapping_valid = source_offset < QbsMaxM * block_bytes;
        if (source_offset < scale_region_bytes) begin
          if (scale_bytes == 2) begin
            target_context = source_offset >> 1;
            target_offset = source_offset & 1;
          end else begin
            target_context = source_offset >> 2;
            target_offset = source_offset & 3;
          end
        end else if (source_offset < quant_region_end) begin
          automatic int unsigned packed_qs =
              source_offset - scale_region_bytes;
          target_context = packed_qs & (QbsMaxM - 1);
          target_offset = scale_bytes + (packed_qs >> 3);
        end else begin
          automatic int unsigned packed_aux_byte =
              source_offset - quant_region_end;
          automatic int unsigned packed_aux;
          if (aux_element_bytes == 2) begin
            packed_aux = packed_aux_byte >> 1;
            target_context = packed_aux & (QbsMaxM - 1);
            target_offset = scale_bytes + quant_bytes +
                (packed_aux >> 3) * 2 + (packed_aux_byte & 1);
          end else begin
            mapping_valid = 1'b0;
          end
          mapping_valid &= packed_aux_byte <
              QbsMaxM * aux_count * aux_element_bytes;
        end
      end

      target_local_context = target_context - ActivationContextBase;
      mapping_valid &= target_context >= ActivationContextBase &&
                       target_context < ActivationContextBase + 4;
      activation_input_target[beat_byte].valid = activation_input.strb[beat_byte] &&
          mapping_valid && target_local_context < 4 && target_offset < block_bytes;
      activation_input_target[beat_byte].ctx = 2'(target_local_context);
      activation_input_target[beat_byte].offset = ActivationOffsetWidth'(target_offset);
    end
  end

  assign new_weight_bytes =
      {1'b0, count_beat_bytes(new_weight_mask[15:0] & weight_consumed[15:0])} +
      {1'b0, count_beat_bytes(new_weight_mask[31:16] & weight_consumed[31:16])};
  assign new_activation_bytes =
      {1'b0, count_beat_bytes(new_activation_mask[15:0] & activation_consumed[15:0])} +
      {1'b0, count_beat_bytes(new_activation_mask[31:16] & activation_consumed[31:16])};

  localparam int unsigned WeightValidGroups = (QbsMaxWeightBlockBytes + 15) / 16;
  localparam int unsigned ActivationValidGroups = (QbsMaxActivationBlockBytes + 15) / 16;
  logic [31:0] weight_valid_row [4], activation_valid_row [4];
  logic [31:0] weight_valid_group [WeightValidGroups];
  logic [31:0] activation_valid_group [ActivationValidGroups];
  logic [31:0] weight_valid_byte [16], activation_valid_byte [16];

  // Decode each writer once, then share row/group/byte selects. Repeating
  // the full target comparison at every valid bit creates a large network.
  for (genvar b = 0; b < 32; b++) begin : gen_valid_decode
    wire weight_commit = (|weight_source_valid) && weight_consumed[b];
    wire activation_commit = (|activation_source_valid) && activation_consumed[b];
    for (genvar row = 0; row < 4; row++) begin : gen_row
      assign weight_valid_row[row][b] = weight_commit && weight_target[b].row == 2'(row);
      assign activation_valid_row[row][b] = activation_commit && activation_target[b].ctx == 2'(row);
    end
    for (genvar group_index = 0; group_index < WeightValidGroups; group_index++) begin : gen_weight_group
      assign weight_valid_group[group_index][b] =
          weight_target[b].offset[WeightOffsetWidth-1:4] == (WeightOffsetWidth-4)'(group_index);
    end
    for (genvar group_index = 0; group_index < ActivationValidGroups; group_index++) begin : gen_activation_group
      assign activation_valid_group[group_index][b] =
          activation_target[b].offset[ActivationOffsetWidth-1:4] == (ActivationOffsetWidth-4)'(group_index);
    end
    for (genvar byte_index = 0; byte_index < 16; byte_index++) begin : gen_byte
      assign weight_valid_byte[byte_index][b] = weight_target[b].offset[3:0] == 4'(byte_index);
      assign activation_valid_byte[byte_index][b] = activation_target[b].offset[3:0] == 4'(byte_index);
    end
  end

  // All writers set 1, so their order is immaterial. Keep reset > set > clear.
  if (TrackByteValid) begin : gen_bitmap_storage
  for (genvar row = 0; row < 4; row++) begin : gen_byte_valid
    for (genvar group_index = 0; group_index < WeightValidGroups; group_index++) begin : gen_weight
      wire [31:0] group_hit = weight_valid_row[row] & weight_valid_group[group_index];
      for (genvar byte_index = 0; byte_index < 16; byte_index++) begin : gen_byte
        localparam int Index = 16*group_index + byte_index;
        if (Index < QbsMaxWeightBlockBytes) begin : gen_valid
          wire set_hit = |(group_hit & weight_valid_byte[byte_index]);
          always_ff @(posedge clk_i or negedge rst_ni) begin
            if (!rst_ni) weight_byte_valid_q[row][Index] <= 1'b0;
            else if (set_hit) weight_byte_valid_q[row][Index] <= 1'b1;
            else if (clear_weight_i) weight_byte_valid_q[row][Index] <= 1'b0;
          end
        end
      end
    end
    for (genvar group_index = 0; group_index < ActivationValidGroups; group_index++) begin : gen_activation
      wire [31:0] group_hit = activation_valid_row[row] & activation_valid_group[group_index];
      for (genvar byte_index = 0; byte_index < 16; byte_index++) begin : gen_byte
        localparam int Index = 16*group_index + byte_index;
        if (Index < QbsMaxActivationBlockBytes) begin : gen_valid
          wire set_hit = |(group_hit & activation_valid_byte[byte_index]);
          always_ff @(posedge clk_i or negedge rst_ni) begin
            if (!rst_ni) activation_byte_valid_q[row][Index] <= 1'b0;
            else if (set_hit) activation_byte_valid_q[row][Index] <= 1'b1;
            else if (clear_activation_i) activation_byte_valid_q[row][Index] <= 1'b0;
          end
        end
      end
    end
  end
  end

  if (UniqueInputBytes) begin : gen_commit_counts
    for (genvar row = 0; row < 4; row++) begin : gen_row
      wire [5:0] weight_count =
          {1'b0, count_beat_bytes(weight_valid_row[row][15:0])} +
          {1'b0, count_beat_bytes(weight_valid_row[row][31:16])};
      wire [5:0] activation_count =
          {1'b0, count_beat_bytes(activation_valid_row[row][15:0])} +
          {1'b0, count_beat_bytes(activation_valid_row[row][31:16])};
      always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
          weight_committed_q[row] <= '0;
          activation_committed_q[row] <= '0;
        end else begin
          if (clear_weight_i) weight_committed_q[row] <= '0;
          else if (|weight_count)
            weight_committed_q[row] <= weight_committed_q[row] + weight_count;
          if (clear_activation_i) activation_committed_q[row] <= '0;
          else if (|activation_count)
            activation_committed_q[row] <= activation_committed_q[row] + activation_count;
        end
      end
`ifndef SYNTHESIS
      always @(posedge clk_i) if (rst_ni) begin
        if (|weight_count)
          assert (unsigned'(weight_committed_q[row]) + unsigned'(weight_count) <=
                  qbs_weight_block_bytes(weight_profile_i))
            else $fatal(1, "QBS weight completion counter overflow");
        if (|activation_count)
          assert (unsigned'(activation_committed_q[row]) + unsigned'(activation_count) <=
                  qbs_activation_block_bytes(activation_profile_i))
            else $fatal(1, "QBS activation completion counter overflow");
      end
`endif
    end
`ifndef SYNTHESIS
    always @(posedge clk_i) if (rst_ni) begin
      for (int b = 0; b < 32; b++) begin
        if (weight_consumed[b])
          assert (!weight_byte_valid_q[weight_rows[b]][weight_offsets[b]])
            else $fatal(1, "QBS unique-input adapter received a duplicate weight byte");
        if (activation_consumed[b])
          assert (!activation_byte_valid_q[activation_contexts[b]][activation_offsets[b]])
            else $fatal(1, "QBS unique-input adapter received a duplicate activation byte");
      end
    end
`endif
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      accepted_weight_bytes_o <= '0;
      accepted_activation_bytes_o <= '0;
    end else begin
      if (clear_weight_i) begin
        accepted_weight_bytes_o <= '0;
      end
      if (clear_activation_i) begin
        accepted_activation_bytes_o <= '0;
      end

      if (|weight_source_valid) begin
        accepted_weight_bytes_o <= accepted_weight_bytes_o + 32'(new_weight_bytes);
      end

      if (|activation_source_valid) begin
        accepted_activation_bytes_o <= accepted_activation_bytes_o + 32'(new_activation_bytes);
      end

`ifndef SYNTHESIS
      assert (!(weight_read_i && (weight_write_pending || clear_weight_i)))
        else $fatal(1, "QBS weight read before ingress drained");
      assert (!(activation_read_i && (activation_write_pending || clear_activation_i)))
        else $fatal(1, "QBS activation read before ingress drained");
      if (weight_source_valid[1] && weight_pending_q_valid)
        assert (weight_remaining[15:0] == 0)
          else $fatal(1, "QBS input overwrote uncommitted weight bytes");
      if (activation_source_valid[1] && activation_pending_q_valid)
        assert (activation_remaining[15:0] == 0)
          else $fatal(1, "QBS input overwrote uncommitted activation bytes");
      if (weight_write_valid_i) begin
        assert (weight_write_group_i ||
                weight_write_row_i < weight_row_count_i)
          else $fatal(1, "QBS weight beat targets an inactive row");
        for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
          if (weight_write_strb_i[beat_byte]) begin
            automatic int unsigned block_bytes =
                qbs_weight_block_bytes(weight_profile_i);
            if (weight_write_group_i)
              assert (unsigned'(weight_write_offset_i) + beat_byte <
                      unsigned'(weight_row_count_i) * block_bytes)
                else $fatal(1, "QBS weight beat exceeds active R4 group");
            else
              assert (unsigned'(weight_write_offset_i) + beat_byte <
                      block_bytes)
                else $fatal(1, "QBS weight beat exceeds native block");
          end
        end
      end
      if (activation_write_valid_i) begin
        assert (activation_layout_i inside {
            QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
            QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED});
        if (activation_layout_i ==
            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED)
          assert (m_i == 4)
            else $fatal(1, "QBS M4 activation layout requires M=4");
        else if (activation_layout_i ==
                 QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED)
          assert (m_i inside {[QbsWideMMin:QbsMaxM]})
            else $fatal(1, "QBS M8 activation layout requires M=5..8");
        else if (ActivationContextBase == 0)
          assert (activation_write_context_i < m_i)
            else $fatal(1, "QBS activation beat targets inactive context");
      end
`endif
    end
  end

`ifndef SYNTHESIS
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      weight_source_valid[1] ==
      ((weight_ingress_count_q != 0) &&
       (!weight_pending_q_valid || !(|weight_remaining[15:0])) &&
       !clear_weight_i && !weight_read_i))
    else $fatal(1, "QBS weight conflict detector changed ingress pop");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      activation_source_valid[1] ==
      ((activation_ingress_count_q != 0) &&
       (!activation_pending_q_valid || !(|activation_remaining[15:0])) &&
       !clear_activation_i && !activation_read_i))
    else $fatal(1, "QBS activation conflict detector changed ingress pop");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      weight_ingress_count_q <= 2 && activation_ingress_count_q <= 2)
    else $fatal(1, "QBS ingress FIFO overflow/underflow");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      clear_weight_i |=> !weight_write_pending)
    else $fatal(1, "QBS weight clear did not flush ingress");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      clear_activation_i |=> !activation_write_pending)
    else $fatal(1, "QBS activation clear did not flush ingress");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      weight_write_pending && !clear_weight_i |=>
      clear_weight_i || $stable(weight_profile_i))
    else $fatal(1, "QBS weight profile changed with uncommitted ingress");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      activation_write_pending && !clear_activation_i |=>
      clear_activation_i || $stable({activation_profile_i, activation_layout_i}))
    else $fatal(1, "QBS activation profile/layout changed with uncommitted ingress");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      weight_source_valid[0] && (|weight_remaining[15:0]) |=>
      clear_weight_i || !(|weight_remaining[15:0]))
    else $fatal(1, "QBS pending weight needs more than two SRAM writes");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      activation_source_valid[0] && (|activation_remaining[15:0]) |=>
      clear_activation_i || !(|activation_remaining[15:0]))
    else $fatal(1, "QBS pending activation needs more than two SRAM writes");
`endif

endmodule : qbs_block_adapter
