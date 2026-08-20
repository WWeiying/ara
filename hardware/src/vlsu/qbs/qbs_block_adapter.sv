// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_block_adapter import qbs_pkg::*; (
  input  logic                    clk_i,
  input  logic                    rst_ni,

  input  logic                    clear_weight_i,
  input  logic                    clear_activation_i,
  input  qbs_weight_profile_e     weight_profile_i,
  input  logic [2:0]              weight_row_count_i,
  input  qbs_activation_layout_e  activation_layout_i,
  input  logic [2:0]              m_i,

  // A row-major range carries one native block. An R4 range may concatenate
  // all active row blocks; byte-level steering handles beats that cross a
  // native-block boundary without padding or a second AXI request.
  input  logic                    weight_write_valid_i,
  input  logic                    weight_write_group_i,
  input  logic [1:0]              weight_write_row_i,
  input  logic [9:0]              weight_write_offset_i,
  input  logic [127:0]            weight_write_data_i,
  input  logic [15:0]             weight_write_strb_i,

  // Row-major ranges target one context. M4 ranges target the complete
  // 1168-byte block_q8_Kx4 object and are deinterleaved here.
  input  logic                    activation_write_valid_i,
  input  logic [1:0]              activation_write_context_i,
  input  logic [10:0]             activation_write_offset_i,
  input  logic [127:0]            activation_write_data_i,
  input  logic [15:0]             activation_write_strb_i,

  output logic [7:0]              weight_block_o [4][QbsQ6KBlockBytes],
  output logic [7:0]              activation_block_o [4][QbsQ8KBlockBytes],
  output logic [3:0]              weight_complete_o,
  output logic [3:0]              activation_complete_o,
  output logic                    all_weight_complete_o,
  output logic                    all_activation_complete_o,
  output logic [31:0]             accepted_weight_bytes_o,
  output logic [31:0]             accepted_activation_bytes_o
);

  localparam int unsigned QbsQ8Kx4BlockBytes = 4 * QbsQ8KBlockBytes;
  localparam int unsigned QbsQ8Kx4DBytes = 16;
  localparam int unsigned QbsQ8Kx4QsBytes = 4 * QbsBlockElements;
  localparam int unsigned QbsQ8Kx4BsumsOffset =
      QbsQ8Kx4DBytes + QbsQ8Kx4QsBytes;

  logic weight_byte_valid_q [4][QbsQ6KBlockBytes];
  logic activation_byte_valid_q [4][QbsQ8KBlockBytes];

  always_comb begin
    int unsigned weight_bytes;
    weight_bytes = weight_profile_i == QBS_WEIGHT_PROFILE_Q4_K
        ? QbsQ4KBlockBytes : QbsQ6KBlockBytes;

    weight_complete_o = '0;
    activation_complete_o = '0;
    all_weight_complete_o = weight_row_count_i inside {[1:4]};
    all_activation_complete_o = m_i inside {[1:4]};

    for (int row = 0; row < 4; row++) begin
      logic complete;
      complete = row < weight_row_count_i;
      for (int byte_index = 0; byte_index < QbsQ6KBlockBytes;
           byte_index++) begin
        if (byte_index < weight_bytes)
          complete &= weight_byte_valid_q[row][byte_index];
      end
      weight_complete_o[row] = complete;
      if (row < weight_row_count_i)
        all_weight_complete_o &= complete;
    end

    for (int ctx = 0; ctx < 4; ctx++) begin
      logic complete;
      complete = ctx < m_i;
      for (int byte_index = 0; byte_index < QbsQ8KBlockBytes;
           byte_index++)
        complete &= activation_byte_valid_q[ctx][byte_index];
      activation_complete_o[ctx] = complete;
      if (ctx < m_i)
        all_activation_complete_o &= complete;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      accepted_weight_bytes_o <= '0;
      accepted_activation_bytes_o <= '0;
      for (int row = 0; row < 4; row++)
        for (int byte_index = 0; byte_index < QbsQ6KBlockBytes;
             byte_index++) begin
          weight_byte_valid_q[row][byte_index] <= 1'b0;
          weight_block_o[row][byte_index] <= '0;
        end
      for (int ctx = 0; ctx < 4; ctx++)
        for (int byte_index = 0; byte_index < QbsQ8KBlockBytes;
             byte_index++) begin
          activation_byte_valid_q[ctx][byte_index] <= 1'b0;
          activation_block_o[ctx][byte_index] <= '0;
        end
    end else begin
      if (clear_weight_i) begin
        accepted_weight_bytes_o <= '0;
        for (int row = 0; row < 4; row++)
          for (int byte_index = 0; byte_index < QbsQ6KBlockBytes;
               byte_index++)
            weight_byte_valid_q[row][byte_index] <= 1'b0;
      end
      if (clear_activation_i) begin
        accepted_activation_bytes_o <= '0;
        for (int ctx = 0; ctx < 4; ctx++)
          for (int byte_index = 0; byte_index < QbsQ8KBlockBytes;
               byte_index++)
            activation_byte_valid_q[ctx][byte_index] <= 1'b0;
      end

      if (weight_write_valid_i && !clear_weight_i) begin
        automatic int unsigned new_weight_bytes = 0;
        for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
          automatic int unsigned source_offset =
              unsigned'(weight_write_offset_i) + beat_byte;
          automatic int unsigned target_row;
          automatic int unsigned target_offset;
          automatic int unsigned block_bytes;
          automatic logic mapping_valid;

          block_bytes = weight_profile_i == QBS_WEIGHT_PROFILE_Q4_K
              ? QbsQ4KBlockBytes : QbsQ6KBlockBytes;
          target_row = unsigned'(weight_write_row_i);
          target_offset = source_offset;

          // Avoid a synthesized divider: both supported native block sizes
          // are command constants, and at most four row banks are active.
          if (weight_write_group_i) begin
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
          if (weight_write_strb_i[beat_byte] &&
              mapping_valid) begin
            weight_block_o[target_row][target_offset] <=
                weight_write_data_i[beat_byte * 8 +: 8];
            if (!weight_byte_valid_q[target_row][target_offset])
              new_weight_bytes++;
            weight_byte_valid_q[target_row][target_offset] <= 1'b1;
          end
        end
        accepted_weight_bytes_o <=
            accepted_weight_bytes_o + new_weight_bytes;
      end

      if (activation_write_valid_i && !clear_activation_i) begin
        automatic int unsigned new_activation_bytes = 0;
        for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
          automatic int unsigned source_offset =
              unsigned'(activation_write_offset_i) + beat_byte;
          automatic int unsigned target_context;
          automatic int unsigned target_offset;
          automatic logic mapping_valid;

          target_context = unsigned'(activation_write_context_i);
          target_offset = source_offset;
          mapping_valid = source_offset < QbsQ8KBlockBytes;

          if (activation_layout_i ==
              QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED) begin
            mapping_valid = source_offset < QbsQ8Kx4BlockBytes;
            if (source_offset < QbsQ8Kx4DBytes) begin
              target_context = source_offset / 4;
              target_offset = source_offset % 4;
            end else if (source_offset < QbsQ8Kx4BsumsOffset) begin
              automatic int unsigned packed_qs =
                  source_offset - QbsQ8Kx4DBytes;
              target_context = packed_qs % 4;
              target_offset = 4 + packed_qs / 4;
            end else begin
              automatic int unsigned packed_bsum_byte =
                  source_offset - QbsQ8Kx4BsumsOffset;
              automatic int unsigned packed_bsum = packed_bsum_byte / 2;
              target_context = packed_bsum % 4;
              target_offset = 260 + (packed_bsum / 4) * 2 +
                              packed_bsum_byte % 2;
            end
          end

          if (activation_write_strb_i[beat_byte] && mapping_valid &&
              target_context < 4 && target_offset < QbsQ8KBlockBytes) begin
            activation_block_o[target_context][target_offset] <=
                activation_write_data_i[beat_byte * 8 +: 8];
            if (!activation_byte_valid_q[target_context][target_offset])
              new_activation_bytes++;
            activation_byte_valid_q[target_context][target_offset] <= 1'b1;
          end
        end
        accepted_activation_bytes_o <=
            accepted_activation_bytes_o + new_activation_bytes;
      end

`ifndef SYNTHESIS
      if (weight_write_valid_i) begin
        assert (weight_write_group_i ||
                weight_write_row_i < weight_row_count_i)
          else $fatal(1, "QBS weight beat targets an inactive row");
        for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
          if (weight_write_strb_i[beat_byte]) begin
            automatic int unsigned block_bytes =
                weight_profile_i == QBS_WEIGHT_PROFILE_Q4_K
                    ? QbsQ4KBlockBytes : QbsQ6KBlockBytes;
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
            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED});
        if (activation_layout_i ==
            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED)
          assert (m_i == 4)
            else $fatal(1, "QBS M4 activation layout requires M=4");
        else
          assert (activation_write_context_i < m_i)
            else $fatal(1, "QBS activation beat targets inactive context");
      end
`endif
    end
  end

endmodule : qbs_block_adapter
