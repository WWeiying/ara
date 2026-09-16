// SPDX-License-Identifier: SHL-0.51
// Untimed, byte-addressed oracle. Deliberately use sequential byte priority,
// not the DUT's bank-local priority trees or stream-data rotation.
module qbs_payload_buffer_reference import qbs_pkg::*; (
  input logic clk_i, rst_ni,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input logic [1:0] weight_valid_i, activation_valid_i,
  input logic [31:0] weight_mask_i, activation_mask_i,
  input logic [1:0] weight_row_i [32], activation_context_i [32],
  input logic [7:0] weight_offset_i [32],
  input logic [8:0] activation_offset_i [32],
  input logic [255:0] weight_data_i, activation_data_i,
  output logic [31:0] weight_consumed_o, activation_consumed_o,
  input logic weight_read_i, activation_read_i,
  input logic [7:0] read_k_i,
  output logic [7:0] weight_view_o [4][QbsMaxWeightBlockBytes],
  output logic [7:0] activation_view_o [4][QbsMaxActivationBlockBytes]
);
  logic write_req [2][3][4];
  logic [2:0] write_addr [2][3][4];
  logic [255:0] write_data [2][3][4];
  logic [31:0] write_be [2][3][4];
  logic [7:0] memory [3][4][256];
  logic [7:0] weight_side [4][20], activation_side [4][36];
  int read_word [3];
  logic [7:0] read_bytes [3][4][32];

  always_comb begin
    weight_consumed_o = '0;
    activation_consumed_o = '0;
    for (int slot = 0; slot < 2; slot++) begin
      for (int p = 0; p < 3; p++)
        for (int r = 0; r < 4; r++) begin
          write_req[slot][p][r] = slot == 0 ? 0 : write_req[0][p][r];
          write_addr[slot][p][r] = slot == 0 ? 0 : write_addr[0][p][r];
          write_be[slot][p][r] = slot == 0 ? 0 : write_be[0][p][r];
          write_data[slot][p][r] = slot == 0 ? 0 : write_data[0][p][r];
        end
      for (int b = 16*slot; b < 16*(slot+1); b++) begin
        automatic qbs_payload_location_t w = qbs_weight_payload_location(weight_profile_i, weight_offset_i[b]);
        automatic qbs_payload_location_t a = qbs_activation_payload_location(activation_profile_i, activation_offset_i[b]);
        automatic int wr = int'(weight_row_i[b]);
        automatic int ar = int'(activation_context_i[b]);
        if (weight_valid_i[slot] && weight_mask_i[b]) begin
          if (w.plane == 2) weight_consumed_o[b] = 1;
          else if (!write_req[slot][w.plane][wr] || write_addr[slot][w.plane][wr] == w.offset / 16) begin
            write_req[slot][w.plane][wr] = 1;
            write_addr[slot][w.plane][wr] = 3'(w.offset / 16);
            write_be[slot][w.plane][wr][w.offset % 16] = 1;
            write_data[slot][w.plane][wr][8*(w.offset % 16) +: 8] = weight_data_i[8*b +: 8];
            weight_consumed_o[b] = 1;
          end
        end
        if (activation_valid_i[slot] && activation_mask_i[b]) begin
          if (a.plane == 2) activation_consumed_o[b] = 1;
          else if (!write_req[slot][2][ar] || write_addr[slot][2][ar] == a.offset / 32) begin
            write_req[slot][2][ar] = 1;
            write_addr[slot][2][ar] = 3'(a.offset / 32);
            write_be[slot][2][ar][a.offset % 32] = 1;
            write_data[slot][2][ar][8*(a.offset % 32) +: 8] = activation_data_i[8*b +: 8];
            activation_consumed_o[b] = 1;
          end
        end
      end
    end
  end

  always_comb begin
    read_word[0] = 0;
    read_word[1] = 0;
    read_word[2] = activation_profile_i == QBS_ACTIVATION_PROFILE_Q8_K ? read_k_i / 32 : 0;
    case (weight_profile_i)
      QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q5_K: begin
        read_word[0] = (read_k_i / 64 * 32 + read_k_i % 32) / 16;
        read_word[1] = read_k_i % 32 / 16;
      end
      QBS_WEIGHT_PROFILE_Q6_K: begin
        read_word[0] = (read_k_i / 128 * 64 + read_k_i % 64) / 16;
        read_word[1] = (read_k_i / 128 * 32 + read_k_i % 32) / 16;
      end
      QBS_WEIGHT_PROFILE_Q3_K, QBS_WEIGHT_PROFILE_Q2_K: begin
        read_word[0] = (read_k_i / 128 * 32 + read_k_i % 32) / 16;
        read_word[1] = read_k_i % 32 / 16;
      end
      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT: read_word[0] = read_k_i / 16;
      default: ;
    endcase
  end

  always @(posedge clk_i) begin
    for (int p = 0; p < 3; p++)
      for (int r = 0; r < 4; r++) begin
        if (write_req[1][p][r])
          for (int b = 0; b < (p == 2 ? 32 : 16); b++)
            if (write_be[1][p][r][b])
              memory[p][r][int'(write_addr[1][p][r])*(p == 2 ? 32 : 16)+b] <= write_data[1][p][r][8*b +: 8];
        if (p == 2 ? activation_read_i : weight_read_i)
          for (int b = 0; b < (p == 2 ? 32 : 16); b++)
            read_bytes[p][r][b] <= memory[p][r][read_word[p]*(p == 2 ? 32 : 16)+b];
      end
    for (int b = 0; b < 32; b++) begin
      automatic qbs_payload_location_t w = qbs_weight_payload_location(weight_profile_i, weight_offset_i[b]);
      automatic qbs_payload_location_t a = qbs_activation_payload_location(activation_profile_i, activation_offset_i[b]);
      if (weight_consumed_o[b] && w.plane == 2)
        weight_side[weight_row_i[b]][w.offset] <= weight_data_i[8*b +: 8];
      if (activation_consumed_o[b] && a.plane == 2)
        activation_side[activation_context_i[b]][a.offset] <= activation_data_i[8*b +: 8];
    end
  end

  always_comb begin
    for (int r = 0; r < 4; r++) begin
      for (int b = 0; b < QbsMaxWeightBlockBytes; b++) begin
        automatic qbs_payload_location_t w = qbs_weight_payload_location(weight_profile_i, b);
        weight_view_o[r][b] = b >= qbs_weight_block_bytes(weight_profile_i) ? 0 :
            w.plane == 2 ? weight_side[r][w.offset] : read_bytes[w.plane][r][w.offset % 16];
      end
      for (int b = 0; b < QbsMaxActivationBlockBytes; b++) begin
        automatic qbs_payload_location_t a = qbs_activation_payload_location(activation_profile_i, b);
        activation_view_o[r][b] = b >= qbs_activation_block_bytes(activation_profile_i) ? 0 :
            a.plane == 2 ? activation_side[r][a.offset] : read_bytes[2][r][a.offset % 32];
      end
    end
  end
endmodule
