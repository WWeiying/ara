// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Four rows/contexts, three independent single-port SRAM planes per row.
// Native block offsets are translated without expanding quantized values.
module qbs_payload_buffer import qbs_pkg::*; (
  input logic clk_i, rst_ni,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input logic weight_valid_i, activation_valid_i,
  input logic [15:0] weight_mask_i, activation_mask_i,
  input logic [1:0] weight_row_i [16], activation_context_i [16],
  input logic [7:0] weight_offset_i [16],
  input logic [8:0] activation_offset_i [16],
  input logic [127:0] weight_data_i, activation_data_i,
  output logic [15:0] weight_consumed_o, activation_consumed_o,
  input logic weight_read_i, activation_read_i,
  input logic [7:0] read_k_i,
  // Only the payload window addressed by read_k_i is meaningful. Side
  // metadata retains its native indices; repeated payload wires are a view,
  // not a full-block register copy. The profile decoder reads this window.
  output logic [7:0] weight_view_o [4][QbsMaxWeightBlockBytes],
  output logic [7:0] activation_view_o [4][QbsMaxActivationBlockBytes]
);
  localparam int unsigned WeightSideBytes = 20;
  localparam int unsigned ActivationSideBytes = 36;
  typedef struct packed {
    logic [1:0] plane; // 0: low, 1: high, 2: side metadata
    logic [7:0] offset;
  } location_t;
  logic [7:0] weight_side_q [4][WeightSideBytes];
  logic [7:0] activation_side_q [4][ActivationSideBytes];
  location_t weight_location [16], activation_location [16];
  logic write_req [3][4];
  logic [2:0] write_addr [3][4];
  logic [255:0] write_data [3][4], read_data [3][4];
  logic [31:0] write_be [3][4];
  logic [2:0] read_addr [3];

  function automatic location_t weight_location_of(input int unsigned offset);
    location_t loc;
    loc = '{plane: 2'd2, offset: 8'(offset)};
    case (weight_profile_i)
      QBS_WEIGHT_PROFILE_Q4_K:
        if (offset >= 16) loc = '{2'd0, 8'(offset - 16)};
      QBS_WEIGHT_PROFILE_Q5_K:
        if (offset >= 48) loc = '{2'd0, 8'(offset - 48)};
        else if (offset >= 16) loc = '{2'd1, 8'(offset - 16)};
      QBS_WEIGHT_PROFILE_Q6_K:
        if (offset < 128) loc = '{2'd0, 8'(offset)};
        else if (offset < 192) loc = '{2'd1, 8'(offset - 128)};
        else loc.offset = 8'(offset - 192);
      QBS_WEIGHT_PROFILE_Q3_K:
        if (offset < 32) loc = '{2'd1, 8'(offset)};
        else if (offset < 96) loc = '{2'd0, 8'(offset - 32)};
        else loc.offset = 8'(offset - 96);
      QBS_WEIGHT_PROFILE_Q2_K:
        if (offset >= 80) loc.offset = 8'(offset - 64);
        else if (offset >= 16) loc = '{2'd0, 8'(offset - 16)};
      QBS_WEIGHT_PROFILE_Q5_0:
        if (offset >= 6) loc = '{2'd0, 8'(offset - 6)};
      QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
      QBS_WEIGHT_PROFILE_IQ4_NL:
        if (offset >= 2) loc = '{2'd0, 8'(offset - 2)};
      default: ;
    endcase
    return loc;
  endfunction

  function automatic location_t activation_location_of(input int unsigned offset);
    int unsigned scale, quants;
    location_t loc;
    scale = qbs_activation_scale_bytes(activation_profile_i);
    quants = qbs_activation_quant_bytes(activation_profile_i);
    loc = '{plane: 2'd2, offset: 8'(offset)};
    if (offset >= scale + quants) loc.offset = 8'(offset - quants);
    else if (offset >= scale) loc = '{2'd0, 8'(offset - scale)};
    return loc;
  endfunction

  always_comb begin
    read_addr[0] = '0;
    read_addr[1] = '0;
    read_addr[2] = activation_profile_i == QBS_ACTIVATION_PROFILE_Q8_K
        ? read_k_i[7:5] : 3'b0;
    case (weight_profile_i)
      QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q5_K:
        read_addr[0] = {1'b0, read_k_i[7:6]};
      QBS_WEIGHT_PROFILE_Q6_K: begin
        read_addr[0] = {1'b0, read_k_i[7], read_k_i[5]};
        read_addr[1] = {2'b0, read_k_i[7]};
      end
      QBS_WEIGHT_PROFILE_Q3_K, QBS_WEIGHT_PROFILE_Q2_K:
        read_addr[0] = {2'b0, read_k_i[7]};
      default: ;
    endcase
  end

  // Select one word per physical bank. Unconsumed bytes are replayed by the
  // adapter on the next cycle; weight and activation never share that queue.
  always_comb begin
    weight_consumed_o = '0;
    activation_consumed_o = '0;
    for (int plane = 0; plane < 3; plane++)
      for (int row = 0; row < 4; row++) begin
        write_req[plane][row] = 1'b0;
        write_addr[plane][row] = '0;
        write_data[plane][row] = '0;
        write_be[plane][row] = '0;
      end
    for (int b = 0; b < 16; b++) begin
      weight_location[b] = weight_location_of(unsigned'(weight_offset_i[b]));
      activation_location[b] = activation_location_of(unsigned'(activation_offset_i[b]));
      if (weight_valid_i && weight_mask_i[b]) begin
        if (weight_location[b].plane == 2) weight_consumed_o[b] = 1'b1;
        else begin
          automatic int unsigned p = unsigned'(weight_location[b].plane);
          automatic int unsigned r = unsigned'(weight_row_i[b]);
          automatic logic [2:0] word_addr = weight_location[b].offset[7:5];
          if (!write_req[p][r] || write_addr[p][r] == word_addr) begin
            write_req[p][r] = 1'b1;
            write_addr[p][r] = word_addr;
            write_data[p][r][8*weight_location[b].offset[4:0] +: 8] = weight_data_i[8*b +: 8];
            write_be[p][r][weight_location[b].offset[4:0]] = 1'b1;
            weight_consumed_o[b] = 1'b1;
          end
        end
      end
      if (activation_valid_i && activation_mask_i[b]) begin
        if (activation_location[b].plane == 2) activation_consumed_o[b] = 1'b1;
        else begin
          automatic int unsigned r = unsigned'(activation_context_i[b]);
          automatic logic [2:0] word_addr = activation_location[b].offset[7:5];
          if (!write_req[2][r] || write_addr[2][r] == word_addr) begin
            write_req[2][r] = 1'b1;
            write_addr[2][r] = word_addr;
            write_data[2][r][8*activation_location[b].offset[4:0] +: 8] = activation_data_i[8*b +: 8];
            write_be[2][r][activation_location[b].offset[4:0]] = 1'b1;
            activation_consumed_o[b] = 1'b1;
          end
        end
      end
    end
  end

  for (genvar p = 0; p < 3; p++) begin : gen_plane
    for (genvar r = 0; r < 4; r++) begin : gen_row
      wire rd = p == 2 ? activation_read_i : weight_read_i;
      qbs_payload_sram #(.NumWords(p == 0 ? 4 : p == 1 ? 2 : 8)) i_payload (
        .clk_i, .rst_ni, .req_i(rd || write_req[p][r]), .we_i(write_req[p][r]),
        .addr_i(write_req[p][r] ? write_addr[p][r] : read_addr[p]),
        .wdata_i(write_data[p][r]), .be_i(write_be[p][r]), .rdata_o(read_data[p][r])
      );
`ifndef SYNTHESIS
      assert property (@(posedge clk_i) disable iff (!rst_ni)
          !(rd && write_req[p][r]))
        else $fatal(1, "QBS payload single-port read/write collision");
`endif
    end
  end

  always_ff @(posedge clk_i) begin
    for (int b = 0; b < 16; b++) begin
      if (weight_consumed_o[b] && weight_location[b].plane == 2)
        weight_side_q[weight_row_i[b]][weight_location[b].offset] <= weight_data_i[8*b +: 8];
      if (activation_consumed_o[b] && activation_location[b].plane == 2)
        activation_side_q[activation_context_i[b]][activation_location[b].offset] <= activation_data_i[8*b +: 8];
    end
  end

  always_comb begin
    for (int row = 0; row < 4; row++) begin
      for (int b = 0; b < QbsMaxWeightBlockBytes; b++) begin
        automatic location_t loc = weight_location_of(b);
        weight_view_o[row][b] = '0;
        if (b < qbs_weight_block_bytes(weight_profile_i)) begin
          if (loc.plane == 2) weight_view_o[row][b] = weight_side_q[row][loc.offset];
          else weight_view_o[row][b] = read_data[loc.plane][row][8*loc.offset[4:0] +: 8];
        end
      end
      for (int b = 0; b < QbsMaxActivationBlockBytes; b++) begin
        automatic location_t loc = activation_location_of(b);
        activation_view_o[row][b] = '0;
        if (b < qbs_activation_block_bytes(activation_profile_i)) begin
          if (loc.plane == 2) activation_view_o[row][b] = activation_side_q[row][loc.offset];
          else activation_view_o[row][b] = read_data[2][row][8*loc.offset[4:0] +: 8];
        end
      end
    end
  end
endmodule
