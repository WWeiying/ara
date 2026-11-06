// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Experimental private weight bank. Native ingress is compacted to 32 bytes;
// compute keeps its existing synchronous 16-byte windows. One epoch owns all
// rows until clear. This module is not enabled in the production engine yet.
module qbs_weight_wide_bank (
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
  input logic write_enable_i,
  input logic read_i,
  output logic read_ready_o, read_valid_o,
  input logic [7:0] read_k_i,
  output logic [127:0] window_o [4][2],
  output logic [7:0] side_o [4][20],
  output logic [3:0] row_complete_o,
  output logic all_complete_o, pending_o,
  output logic [10:0] accepted_bytes_o, committed_bytes_o
);
  import qbs_pkg::*;
  logic map_valid, map_ready, map_fire, input_ready;
  logic [255:0] map_data;
  logic [3:0][1:0][4:0] source_start;
  logic [3:0][1:0][5:0] count;
  logic [3:0][1:0][7:0] payload_offset;
  logic [3:0][1:0] payload_last;
  logic [3:0][19:0] side_mask;
  logic [3:0][19:0][4:0] side_source;
  logic [3:0][1:0] segment_ready, segment_pending, write_valid;
  logic [3:0][1:0][5:0] write_count;
  logic [3:0][4:0] side_count;
  logic [3:0][7:0] committed_q;
  logic [10:0] accepted_q, total_expected;
  logic [7:0] block_bytes;
  logic [1:0][2:0] read_addr;
  logic [1:0] read_half_q;
  logic [3:0][19:0] side_valid_q;
  logic [7:0] side_q [4][20];
  logic read_fire, accept_enable, read_valid_q, window_valid_q;

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

  assign block_bytes = 8'(qbs_weight_block_bytes(profile_i));
  always_comb begin
    case (row_count_i)
      1: total_expected = {3'b0, block_bytes};
      2: total_expected = {2'b0, block_bytes, 1'b0};
      3: total_expected = {3'b0, block_bytes} + {2'b0, block_bytes, 1'b0};
      4: total_expected = {1'b0, block_bytes, 2'b0};
      default: total_expected = '0;
    endcase
  end
  assign accept_enable = rst_ni && !clear_i && accepted_q < total_expected;
  assign ready_o = accept_enable && input_ready;
  qbs_weight_wide_mapper i_mapper (
    .clk_i, .rst_ni, .clear_i, .profile_i, .row_count_i, .group_mode_i,
    .row_i, .offset_i, .data_i, .strb_i, .valid_i(valid_i && accept_enable),
    .ready_o(input_ready), .valid_o(map_valid), .ready_i(map_ready),
    .profile_o(), .row_count_o(), .group_mode_o(), .row_o(), .offset_o(),
    .data_o(map_data), .strb_o(), .source_start_o(source_start), .count_o(count),
    .payload_offset_o(payload_offset), .payload_last_o(payload_last),
    .side_mask_o(side_mask), .side_source_index_o(side_source)
  );

  // All segments of a packet advance together, including its side metadata.
  // An assembler's ready depends on its output slot, not on its input valid.
  assign map_ready = &(segment_ready | {8{!map_valid}});
  assign map_fire = map_valid && map_ready;
  assign pending_o = rst_ni && !clear_i && (map_valid || (|segment_pending));
  assign accepted_bytes_o = accepted_q;
  assign committed_bytes_o =
      ({3'b0, committed_q[0]} + {3'b0, committed_q[1]}) +
      ({3'b0, committed_q[2]} + {3'b0, committed_q[3]});
  for (genvar r = 0; r < 4; r++) begin : gen_rows
    assign side_count[r] = 5'(popcount32({12'b0, side_mask[r]}));
    assign row_complete_o[r] = rst_ni && !clear_i && 3'(r) < row_count_i &&
        block_bytes != 0 && committed_q[r] == block_bytes && !(|segment_pending[r]);
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        committed_q[r] <= '0;
        side_valid_q[r] <= '0;
      end else if (clear_i) begin
        committed_q[r] <= '0;
        side_valid_q[r] <= '0;
      end else begin
        committed_q[r] <= committed_q[r] +
            8'(write_count[r][0]) + 8'(write_count[r][1]) +
            (map_fire ? 8'(side_count[r]) : 8'b0);
        if (map_fire) side_valid_q[r] <= side_valid_q[r] | side_mask[r];
      end
    end
    for (genvar s = 0; s < 20; s++) begin : gen_side
      always_ff @(posedge clk_i)
        if (rst_ni && !clear_i && map_fire && side_mask[r][s])
          side_q[r][s] <= map_data[8*side_source[r][s] +: 8];
      assign side_o[r][s] = rst_ni && !clear_i && side_valid_q[r][s] ? side_q[r][s] : 8'b0;
    end
    for (genvar p = 0; p < 2; p++) begin : gen_plane
      localparam int unsigned ByteAddrWidth = p == 0 ? 7 : 6;
      localparam int unsigned WordAddrWidth = ByteAddrWidth - 5;
      logic assembler_ready, assembler_pending, out_valid;
      logic [WordAddrWidth-1:0] out_addr;
      logic [255:0] out_data, read_data;
      logic [31:0] out_strb;
      wire [255:0] segment_data = map_data >> {source_start[r][p], 3'b000};
      wire [31:0] segment_strb = 32'hffffffff >> (6'd32 - count[r][p]);
      wire write_fire = out_valid && write_enable_i;
      assign segment_ready[r][p] = count[r][p] == 0 || assembler_ready;
      assign segment_pending[r][p] = assembler_pending;
      assign write_valid[r][p] = out_valid;
      assign write_count[r][p] = write_fire ? popcount32(out_strb) : 6'b0;
      qbs_weight_line_assembler #(.ByteAddrWidth(ByteAddrWidth)) i_assembler (
        .clk_i, .rst_ni, .clear_i,
        .valid_i(map_fire && count[r][p] != 0), .ready_o(assembler_ready),
        .offset_i(payload_offset[r][p][ByteAddrWidth-1:0]),
        .data_i(segment_data), .strb_i(segment_strb), .last_i(payload_last[r][p]),
        .write_valid_o(out_valid), .write_ready_i(write_enable_i),
        .write_addr_o(out_addr), .write_data_o(out_data), .write_strb_o(out_strb),
        .pending_o(assembler_pending)
      );
      qbs_payload_sram #(.NumWords(p == 0 ? 4 : 2), .DataWidth(256)) i_payload (
        .clk_i, .rst_ni, .req_i(write_fire || read_fire), .we_i(write_fire),
        .addr_i(write_fire ? 3'(out_addr) : {1'b0, read_addr[p][2:1]}),
        .wdata_i(out_data), .be_i(out_strb), .rdata_o(read_data)
      );
      // Match the original compute-side 128-bit view after the SRAM edge.
      assign window_o[r][p] = rst_ni && !clear_i && window_valid_q && 3'(r) < row_count_i
          ? (read_half_q[p] ? read_data[255:128] : read_data[127:0]) : 128'b0;
    end
  end
  assign all_complete_o = rst_ni && !clear_i && block_bytes != 0 &&
      row_count_i inside {[1:4]} && accepted_q == total_expected &&
      committed_bytes_o == total_expected && !pending_o;
  assign read_ready_o = all_complete_o;
  assign read_fire = read_i && read_ready_o;
  assign read_valid_o = rst_ni && !clear_i && read_valid_q;
  always_comb begin
    read_addr = '0;
    case (profile_i)
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
      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT: read_addr[0] = {2'b0, read_k_i[4]};
      default: ;
    endcase
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      accepted_q <= '0;
      read_valid_q <= 1'b0;
      window_valid_q <= 1'b0;
    end else if (clear_i) begin
      accepted_q <= '0;
      read_valid_q <= 1'b0;
      window_valid_q <= 1'b0;
    end else begin
      if (valid_i && ready_o) accepted_q <= accepted_q + 11'(popcount32(strb_i));
      read_valid_q <= read_fire;
      if (read_fire) window_valid_q <= 1'b1;
    end
  end
  always_ff @(posedge clk_i)
    if (read_fire) read_half_q <= {read_addr[1][0], read_addr[0][0]};

`ifndef SYNTHESIS
  logic epoch_started_q;
  qbs_weight_profile_e epoch_profile_q;
  logic [2:0] epoch_rows_q;
  logic [8:0] next_native_q [4];
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      epoch_started_q <= 1'b0;
      for (int r = 0; r < 4; r++) next_native_q[r] <= '0;
    end else if (clear_i) begin
      epoch_started_q <= 1'b0;
      for (int r = 0; r < 4; r++) next_native_q[r] <= '0;
    end else begin
      if (epoch_started_q)
        assert ({profile_i, row_count_i} === {epoch_profile_q, epoch_rows_q})
          else $fatal(1, "QBS_WIDE_BANK_CONFIG_DRIFT");
      if (valid_i && ready_o) begin
        epoch_started_q <= 1'b1;
        epoch_profile_q <= profile_i;
        epoch_rows_q <= row_count_i;
        assert (accepted_q + 11'(popcount32(strb_i)) <= total_expected)
          else $fatal(1, "QBS_WIDE_BANK_INPUT_OVERFLOW");
        for (int r = 0; r < 4; r++) begin
          int start_byte, end_byte, n;
          start_byte = group_mode_i ? int'(offset_i) - r*int'(block_bytes) : int'(offset_i);
          end_byte = start_byte + int'(popcount32(strb_i));
          n = (end_byte < int'(block_bytes) ? end_byte : int'(block_bytes)) -
              (start_byte > 0 ? start_byte : 0);
          if ((group_mode_i || row_i == 2'(r)) && n > 0 && r < int'(row_count_i)) begin
            assert (next_native_q[r] == (start_byte > 0 ? start_byte : 0))
              else $fatal(1, "QBS_WIDE_BANK_NONUNIQUE_OR_UNORDERED");
            next_native_q[r] <= next_native_q[r] + 9'(n);
          end
        end
      end
      for (int r = 0; r < 4; r++)
        assert (committed_q[r] <= block_bytes)
          else $fatal(1, "QBS_WIDE_BANK_COMMIT_OVERFLOW");
      assert (!(read_fire && (|write_valid)))
        else $fatal(1, "QBS_WIDE_BANK_SINGLE_PORT_COLLISION");
    end
  end
`endif
endmodule
