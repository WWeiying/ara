// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
// Unintegrated control-only native-byte mapper. A packet owns one shared data
// register; segment count denotes a prefix after data >> (8*source_start).
module qbs_weight_wide_mapper (
  input logic clk_i, rst_ni, clear_i,
  input qbs_pkg::qbs_weight_profile_e profile_i,
  input logic [2:0] row_count_i,
  input logic group_mode_i,
  input logic [1:0] row_i,
  input logic [9:0] offset_i,
  input logic [255:0] data_i,
  input logic [31:0] strb_i,
  input logic valid_i,
  output logic ready_o,
  output logic valid_o,
  input logic ready_i,
  output qbs_pkg::qbs_weight_profile_e profile_o,
  output logic [2:0] row_count_o,
  output logic group_mode_o,
  output logic [1:0] row_o,
  output logic [9:0] offset_o,
  output logic [255:0] data_o,
  output logic [31:0] strb_o,
  output logic [3:0][1:0][4:0] source_start_o,
  output logic [3:0][1:0][5:0] count_o,
  output logic [3:0][1:0][7:0] payload_offset_o,
  output logic [3:0][1:0] payload_last_o,
  output logic [3:0][19:0] side_mask_o,
  output logic [3:0][19:0][4:0] side_source_index_o
);
  import qbs_pkg::*;
  typedef struct packed {
    qbs_weight_profile_e profile;
    logic [2:0] row_count;
    logic group_mode;
    logic [1:0] row;
    logic [9:0] offset;
    logic [255:0] data;
    logic [31:0] strb;
    logic [3:0][1:0][4:0] source_start;
    logic [3:0][1:0][5:0] count;
    logic [3:0][1:0][7:0] payload_offset;
    logic [3:0][1:0] payload_last;
    logic [3:0][19:0] side_mask;
    logic [3:0][19:0][4:0] side_source_index;
  } packet_t;
  packet_t packet_d, packet_q;
  logic valid_q;
  logic [2:0] rejection;
  logic [7:0] block_bytes;
  logic [5:0] amount;
  logic [10:0] range_bytes;
  wire [10:0] row_begin [4], row_end [4];
  wire [3:0] byte_row_hit [32];
  wire [10:0] byte_native [32];
  qbs_payload_location_t byte_location [32], byte_following [32];
  wire [31:0] byte_last;
  wire [31:0] payload_hit [4][2];
  wire [31:0] side_hit [4][20];

  function automatic logic [5:0] popcount32(input logic [31:0] mask);
    logic [1:0] pairs [16];
    logic [2:0] quads [8];
    logic [3:0] octets [4];
    logic [4:0] halves [2];
    for (int i = 0; i < 16; i++)
      pairs[i] = {1'b0, mask[2*i]} + {1'b0, mask[2*i+1]};
    for (int i = 0; i < 8; i++)
      quads[i] = {1'b0, pairs[2*i]} + {1'b0, pairs[2*i+1]};
    for (int i = 0; i < 4; i++)
      octets[i] = {1'b0, quads[2*i]} + {1'b0, quads[2*i+1]};
    for (int i = 0; i < 2; i++)
      halves[i] = {1'b0, octets[2*i]} + {1'b0, octets[2*i+1]};
    return {1'b0, halves[0]} + {1'b0, halves[1]};
  endfunction

  function automatic logic [31:0] first_one32(input logic [31:0] mask);
    logic [15:0] any2, select2;
    logic [7:0] any4, select4;
    logic [3:0] any8, select8;
    logic [1:0] any16, select16;
    logic [31:0] first;
    for (int i = 0; i < 16; i++) any2[i] = |mask[2*i +: 2];
    for (int i = 0; i < 8; i++) any4[i] = any2[2*i] | any2[2*i+1];
    for (int i = 0; i < 4; i++) any8[i] = any4[2*i] | any4[2*i+1];
    for (int i = 0; i < 2; i++) any16[i] = any8[2*i] | any8[2*i+1];
    select16[0] = any16[0];
    select16[1] = !any16[0] && any16[1];
    for (int i = 0; i < 2; i++) begin
      select8[2*i] = select16[i] && any8[2*i];
      select8[2*i+1] = select16[i] && !any8[2*i] && any8[2*i+1];
    end
    for (int i = 0; i < 4; i++) begin
      select4[2*i] = select8[i] && any4[2*i];
      select4[2*i+1] = select8[i] && !any4[2*i] && any4[2*i+1];
    end
    for (int i = 0; i < 8; i++) begin
      select2[2*i] = select4[i] && any2[2*i];
      select2[2*i+1] = select4[i] && !any2[2*i] && any2[2*i+1];
    end
    for (int i = 0; i < 16; i++) begin
      first[2*i] = select2[i] && mask[2*i];
      first[2*i+1] = select2[i] && !mask[2*i] && mask[2*i+1];
    end
    return first;
  endfunction

  function automatic logic [4:0] encode_onehot32(input logic [31:0] onehot);
    return {(|(onehot & 32'hffff0000)), (|(onehot & 32'hff00ff00)),
            (|(onehot & 32'hf0f0f0f0)), (|(onehot & 32'hcccccccc)),
            (|(onehot & 32'haaaaaaaa))};
  endfunction

  assign block_bytes = 8'(qbs_weight_block_bytes(profile_i));
  assign amount = popcount32(strb_i);
  for (genvar r = 0; r < 4; r++) begin : gen_row_bounds
    assign row_begin[r] = 11'(r) * {3'b0, block_bytes};
    assign row_end[r] = 11'(r+1) * {3'b0, block_bytes};
  end
  always_comb begin
    range_bytes = {3'b0, block_bytes};
    if (group_mode_i) begin
      case (row_count_i)
        1: range_bytes = row_end[0];
        2: range_bytes = row_end[1];
        3: range_bytes = row_end[2];
        4: range_bytes = row_end[3];
        default: range_bytes = 0;
      endcase
    end
    rejection = 0;
    if (block_bytes == 0) rejection = 1;
    else if (row_count_i < 1 || row_count_i > 4) rejection = 2;
    else if (!group_mode_i && row_i >= row_count_i) rejection = 3;
    else if (strb_i == 0 || (strb_i & (strb_i + 32'd1)) != 0) rejection = 4;
    else if ({1'b0, offset_i} + {5'b0, amount} > range_bytes) rejection = 5;
  end

  // Each source byte is decoded independently. All row dimensions below are
  // elaboration-time constants; there is no accumulator or dynamic bank write.
  for (genvar b = 0; b < 32; b++) begin : gen_byte_decode
    wire [10:0] address = {1'b0, offset_i} + 11'(b);
    wire [10:0] local_native [4];
    for (genvar r = 0; r < 4; r++) begin : gen_row_match
      assign byte_row_hit[b][r] = strb_i[b] && 3'(r) < row_count_i &&
          (group_mode_i ? address >= row_begin[r] && address < row_end[r] : row_i == 2'(r));
      assign local_native[r] = group_mode_i ? address - row_begin[r] : address;
    end
    assign byte_native[b] =
        (({11{byte_row_hit[b][0]}} & local_native[0]) |
         ({11{byte_row_hit[b][1]}} & local_native[1])) |
        (({11{byte_row_hit[b][2]}} & local_native[2]) |
         ({11{byte_row_hit[b][3]}} & local_native[3]));
    assign byte_location[b] = qbs_weight_payload_location(profile_i, unsigned'(byte_native[b]));
    assign byte_following[b] = qbs_weight_payload_location(profile_i, unsigned'(byte_native[b] + 11'd1));
    assign byte_last[b] = byte_native[b] + 11'd1 == {3'b0, block_bytes} ||
                          byte_following[b].plane != byte_location[b].plane;
  end

  assign packet_d.profile = profile_i;
  assign packet_d.row_count = row_count_i;
  assign packet_d.group_mode = group_mode_i;
  assign packet_d.row = row_i;
  assign packet_d.offset = offset_i;
  assign packet_d.data = data_i;
  assign packet_d.strb = strb_i;
  for (genvar r = 0; r < 4; r++) begin : gen_row_controls
    for (genvar p = 0; p < 2; p++) begin : gen_payload_segment
      wire [31:0] first;
      wire [31:0] selected_offset_bits [8];
      for (genvar b = 0; b < 32; b++) begin : gen_hit
        assign payload_hit[r][p][b] = byte_row_hit[b][r] && byte_location[b].plane == 2'(p);
        for (genvar k = 0; k < 8; k++) begin : gen_offset_bit
          assign selected_offset_bits[k][b] = first[b] && byte_location[b].offset[k];
        end
      end
      assign first = first_one32(payload_hit[r][p]);
      assign packet_d.source_start[r][p] = encode_onehot32(first);
      assign packet_d.count[r][p] = popcount32(payload_hit[r][p]);
      assign packet_d.payload_last[r][p] = |(payload_hit[r][p] & byte_last);
      for (genvar k = 0; k < 8; k++) begin : gen_offset_reduce
        assign packet_d.payload_offset[r][p][k] = |selected_offset_bits[k];
      end
    end
    for (genvar s = 0; s < 20; s++) begin : gen_side_index
      for (genvar b = 0; b < 32; b++) begin : gen_hit
        assign side_hit[r][s][b] = byte_row_hit[b][r] && byte_location[b].plane == 2 &&
                                  byte_location[b].offset == 8'(s);
      end
      assign packet_d.side_mask[r][s] = |side_hit[r][s];
      assign packet_d.side_source_index[r][s] = encode_onehot32(side_hit[r][s]);
    end
  end

  assign ready_o = rst_ni && !clear_i && (!valid_q || ready_i) &&
                   (!valid_i || rejection == 0);
  assign valid_o = valid_q && rst_ni && !clear_i;
  assign profile_o = packet_q.profile;
  assign row_count_o = packet_q.row_count;
  assign group_mode_o = packet_q.group_mode;
  assign row_o = packet_q.row;
  assign offset_o = packet_q.offset;
  assign data_o = packet_q.data;
  assign strb_o = packet_q.strb;
  assign source_start_o = packet_q.source_start;
  assign count_o = packet_q.count;
  assign payload_offset_o = packet_q.payload_offset;
  assign payload_last_o = packet_q.payload_last;
  assign side_mask_o = packet_q.side_mask;
  assign side_source_index_o = packet_q.side_source_index;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      valid_q <= 0;
    end else if (clear_i) begin
      valid_q <= 0;
    end else if (!valid_q || ready_i) begin
      valid_q <= valid_i && ready_o;
    end
  end
  // Invalid packet contents are don't-care: only the valid bit has reset/clear.
  always_ff @(posedge clk_i)
    if (rst_ni && !clear_i && valid_i && ready_o) packet_q <= packet_d;

`ifndef SYNTHESIS
  wire mapping_checks_enabled = rst_ni && !clear_i && valid_i && rejection == 0 &&
      !$isunknown({profile_i, row_count_i, group_mode_i, row_i, offset_i, strb_i});
  always @(posedge clk_i) begin
    if (rst_ni && !clear_i && valid_i) begin
      assert (!$isunknown({profile_i, row_count_i, group_mode_i, row_i, offset_i, strb_i}))
        else $fatal(1, "QBS_WIDE_REJECT_UNKNOWN");
      case (rejection)
        0: ;
        1: $fatal(1, "QBS_WIDE_REJECT_PROFILE");
        2: $fatal(1, "QBS_WIDE_REJECT_ROWS");
        3: $fatal(1, "QBS_WIDE_REJECT_ROW");
        4: $fatal(1, "QBS_WIDE_REJECT_STRB");
        5: $fatal(1, "QBS_WIDE_REJECT_RANGE");
        default: $fatal(1, "QBS_WIDE_REJECT_MAPPING");
      endcase
    end
  end
  for (genvar b = 0; b < 32; b++) begin : gen_byte_assertions
    always @(posedge clk_i)
      if (mapping_checks_enabled && strb_i[b]) begin
        assert ($onehot(byte_row_hit[b]) && byte_native[b] < {3'b0, block_bytes} &&
                byte_location[b].plane <= 2 &&
                (byte_location[b].plane != 2 || byte_location[b].offset < 20))
          else $fatal(1, "QBS_WIDE_REJECT_MAPPING");
      end
  end
  for (genvar r = 0; r < 4; r++) begin : gen_control_assertions
    for (genvar p = 0; p < 2; p++) begin : gen_segment
      always @(posedge clk_i)
        if (mapping_checks_enabled && packet_d.count[r][p] != 0) begin
          assert (payload_hit[r][p] ==
                  ((32'hffffffff >> (32-int'(packet_d.count[r][p]))) << packet_d.source_start[r][p]))
            else $fatal(1, "QBS_WIDE_REJECT_MAPPING");
          for (int b = 0; b < 32; b++)
            if (payload_hit[r][p][b])
              assert (int'(byte_location[b].offset) == int'(packet_d.payload_offset[r][p]) +
                      b - int'(packet_d.source_start[r][p]))
                else $fatal(1, "QBS_WIDE_REJECT_MAPPING");
        end
    end
    for (genvar s = 0; s < 20; s++) begin : gen_side
      always @(posedge clk_i)
        if (mapping_checks_enabled)
          assert ($onehot0(side_hit[r][s])) else $fatal(1, "QBS_WIDE_REJECT_MAPPING");
    end
  end
  assert property (@(posedge clk_i) disable iff (!rst_ni || clear_i)
      valid_o && !ready_i |=> valid_o && $stable(packet_q))
    else $fatal(1, "QBS_WIDE_OUTPUT_UNSTABLE");
`endif
endmodule
