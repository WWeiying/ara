// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_block_adapter import qbs_pkg::*; #(
  parameter int unsigned ActivationContextBase = 0
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
  output logic [3:0]              weight_complete_o,
  output logic [3:0]              activation_complete_o,
  output logic                    all_weight_complete_o,
  output logic                    all_activation_complete_o,
  output logic [31:0]             accepted_weight_bytes_o,
  output logic [31:0]             accepted_activation_bytes_o
);

  logic weight_byte_valid_q [4][QbsMaxWeightBlockBytes];
  logic activation_byte_valid_q [4][QbsMaxActivationBlockBytes];
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
  weight_target_t weight_target [16];
  activation_target_t activation_target [16];
  logic [15:0] new_weight_mask, new_activation_mask;
  logic [4:0] new_weight_bytes, new_activation_bytes;

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
  weight_beat_t weight_pending_q, weight_source;
  activation_beat_t activation_pending_q, activation_source;
  logic weight_pending_q_valid, activation_pending_q_valid;
  logic weight_source_valid, activation_source_valid;
  logic [15:0] weight_mask, activation_mask;
  logic [15:0] weight_consumed, activation_consumed;
  logic [15:0] weight_remaining, activation_remaining;
  logic [1:0] weight_rows [16], activation_contexts [16];
  logic [7:0] weight_offsets [16];
  logic [8:0] activation_offsets [16];

  assign weight_write_ready_o = !weight_pending_q_valid &&
      !clear_weight_i && !weight_read_i;
  assign activation_write_ready_o = !activation_pending_q_valid &&
      !clear_activation_i && !activation_read_i;
  assign weight_source = weight_pending_q_valid ? weight_pending_q :
      {weight_write_group_i, weight_write_row_i, weight_write_offset_i,
       weight_write_data_i, weight_write_strb_i};
  assign activation_source = activation_pending_q_valid ? activation_pending_q :
      {activation_write_context_i, activation_write_offset_i,
       activation_write_data_i, activation_write_strb_i};
  assign weight_source_valid = !clear_weight_i &&
      (weight_pending_q_valid || (weight_write_valid_i && weight_write_ready_o));
  assign activation_source_valid = !clear_activation_i &&
      (activation_pending_q_valid || (activation_write_valid_i && activation_write_ready_o));
  assign weight_remaining = weight_mask & ~weight_consumed;
  assign activation_remaining = activation_mask & ~activation_consumed;

  for (genvar b = 0; b < 16; b++) begin : gen_payload_targets
    assign weight_mask[b] = weight_target[b].valid;
    assign activation_mask[b] = activation_target[b].valid;
    assign weight_rows[b] = weight_target[b].row;
    assign activation_contexts[b] = activation_target[b].ctx;
    assign weight_offsets[b] = weight_target[b].offset;
    assign activation_offsets[b] = activation_target[b].offset;
  end

  qbs_payload_buffer i_payload_buffer (
    .clk_i, .rst_ni, .weight_profile_i, .activation_profile_i,
    .weight_valid_i(weight_source_valid), .activation_valid_i(activation_source_valid),
    .weight_mask_i(weight_mask), .activation_mask_i(activation_mask),
    .weight_row_i(weight_rows), .weight_offset_i(weight_offsets),
    .activation_context_i(activation_contexts), .activation_offset_i(activation_offsets),
    .weight_data_i(weight_source.data), .activation_data_i(activation_source.data),
    .weight_consumed_o(weight_consumed), .activation_consumed_o(activation_consumed),
    .weight_read_i, .activation_read_i, .read_k_i,
    .weight_view_o(weight_block_o), .activation_view_o(activation_block_o)
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      weight_pending_q_valid <= 1'b0;
      activation_pending_q_valid <= 1'b0;
      weight_pending_q <= '0;
      activation_pending_q <= '0;
    end else begin
      if (clear_weight_i) weight_pending_q_valid <= 1'b0;
      else if (weight_source_valid) begin
        weight_pending_q_valid <= |weight_remaining;
        if (|weight_remaining) begin
          weight_pending_q <= weight_source;
          weight_pending_q.strb <= weight_remaining;
        end
      end
      if (clear_activation_i) activation_pending_q_valid <= 1'b0;
      else if (activation_source_valid) begin
        activation_pending_q_valid <= |activation_remaining;
        if (|activation_remaining) begin
          activation_pending_q <= activation_source;
          activation_pending_q.strb <= activation_remaining;
        end
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
      for (int byte_index = 0; byte_index < QbsMaxWeightBlockBytes; byte_index++)
        byte_complete[byte_index] = byte_index >= weight_bytes ||
                                   weight_byte_valid_q[row][byte_index];
      weight_complete_o[row] = row < weight_row_count_i && (&byte_complete) &&
                               !weight_pending_q_valid;
      weight_missing[row] = row < weight_row_count_i && !(&byte_complete);
    end
    all_weight_complete_o = (weight_row_count_i inside {[1:4]}) &&
                            !(|weight_missing) && !weight_pending_q_valid;

    for (int ctx = 0; ctx < 4; ctx++) begin
      logic [QbsMaxActivationBlockBytes-1:0] byte_complete;
      for (int byte_index = 0; byte_index < QbsMaxActivationBlockBytes; byte_index++)
        byte_complete[byte_index] = byte_index >= activation_bytes ||
                                   activation_byte_valid_q[ctx][byte_index];
      activation_complete_o[ctx] = ctx < activation_context_count && (&byte_complete) &&
                                   !activation_pending_q_valid;
      activation_missing[ctx] = ctx < activation_context_count && !(&byte_complete);
    end
    all_activation_complete_o = (m_i inside {[1:QbsMaxM]}) &&
                                !(|activation_missing) && !activation_pending_q_valid;
  end

  // Mapping and duplicate detection precede SRAM arbitration. Counters below
  // advance only for bytes actually committed to payload or side storage.
  always_comb begin : map_weight_bytes
    new_weight_mask = '0;
    for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
      automatic int unsigned source_offset =
          unsigned'(weight_source.offset) + beat_byte;
      automatic int unsigned target_row;
      automatic int unsigned target_offset;
      automatic int unsigned block_bytes;
      automatic logic mapping_valid;

      block_bytes = qbs_weight_block_bytes(weight_profile_i);
      target_row = unsigned'(weight_source.row);
      target_offset = source_offset;

      // The native block size is profile-dependent. At most four row
      // banks are active, so range comparisons avoid a divider.
      if (weight_source.group_mode) begin
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
      weight_target[beat_byte].valid = weight_source.strb[beat_byte] &&
                                       mapping_valid;
      weight_target[beat_byte].row = 2'(target_row);
      weight_target[beat_byte].offset = WeightOffsetWidth'(target_offset);
      if (weight_target[beat_byte].valid)
        new_weight_mask[beat_byte] = !weight_byte_valid_q[target_row][target_offset];
    end
  end

  always_comb begin : map_activation_bytes
    new_activation_mask = '0;
    for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
      automatic int unsigned source_offset =
          unsigned'(activation_source.offset) + beat_byte;
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
      target_context = unsigned'(activation_source.ctx);
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
      activation_target[beat_byte].valid = activation_source.strb[beat_byte] &&
          mapping_valid && target_local_context < 4 && target_offset < block_bytes;
      activation_target[beat_byte].ctx = 2'(target_local_context);
      activation_target[beat_byte].offset = ActivationOffsetWidth'(target_offset);
      if (activation_target[beat_byte].valid)
        new_activation_mask[beat_byte] =
            !activation_byte_valid_q[target_local_context][target_offset];
    end
  end

  assign new_weight_bytes = count_beat_bytes(new_weight_mask & weight_consumed);
  assign new_activation_bytes = count_beat_bytes(new_activation_mask & activation_consumed);

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      accepted_weight_bytes_o <= '0;
      accepted_activation_bytes_o <= '0;
      for (int row = 0; row < 4; row++)
        for (int byte_index = 0; byte_index < QbsMaxWeightBlockBytes;
             byte_index++) begin
          weight_byte_valid_q[row][byte_index] <= 1'b0;
        end
      for (int ctx = 0; ctx < 4; ctx++)
        for (int byte_index = 0; byte_index < QbsMaxActivationBlockBytes;
             byte_index++) begin
          activation_byte_valid_q[ctx][byte_index] <= 1'b0;
        end
    end else begin
      if (clear_weight_i) begin
        accepted_weight_bytes_o <= '0;
        for (int row = 0; row < 4; row++)
          for (int byte_index = 0; byte_index < QbsMaxWeightBlockBytes;
               byte_index++)
            weight_byte_valid_q[row][byte_index] <= 1'b0;
      end
      if (clear_activation_i) begin
        accepted_activation_bytes_o <= '0;
        for (int ctx = 0; ctx < 4; ctx++)
          for (int byte_index = 0; byte_index < QbsMaxActivationBlockBytes;
               byte_index++)
            activation_byte_valid_q[ctx][byte_index] <= 1'b0;
      end

      if (weight_source_valid) begin
        for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
          if (weight_consumed[beat_byte]) begin
            weight_byte_valid_q[weight_target[beat_byte].row][weight_target[beat_byte].offset]
                <= 1'b1;
          end
        end
        accepted_weight_bytes_o <= accepted_weight_bytes_o + 32'(new_weight_bytes);
      end

      if (activation_source_valid) begin
        for (int beat_byte = 0; beat_byte < 16; beat_byte++) begin
          if (activation_consumed[beat_byte]) begin
            activation_byte_valid_q[activation_target[beat_byte].ctx]
                                   [activation_target[beat_byte].offset] <= 1'b1;
          end
        end
        accepted_activation_bytes_o <= accepted_activation_bytes_o + 32'(new_activation_bytes);
      end

`ifndef SYNTHESIS
      assert (!(weight_read_i && (weight_pending_q_valid || clear_weight_i)));
      assert (!(activation_read_i && (activation_pending_q_valid || clear_activation_i)));
      if (weight_pending_q_valid && !clear_weight_i)
        assert (weight_remaining == 0)
          else $fatal(1, "QBS weight beat needs more than two SRAM writes");
      if (activation_pending_q_valid && !clear_activation_i)
        assert (activation_remaining == 0)
          else $fatal(1, "QBS activation beat needs more than two SRAM writes");
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

endmodule : qbs_block_adapter
