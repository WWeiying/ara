// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_profile_engine_int import qbs_pkg::*; (
  input  logic                clk_i,
  input  logic                rst_ni,

  input  logic [7:0]          weight_block_i [4][QbsQ6KBlockBytes],
  input  logic [7:0]          activation_block_i [4][QbsQ8KBlockBytes],

  input  logic                start_valid_i,
  output logic                start_ready_o,
  input  qbs_weight_profile_e start_profile_i,
  input  logic [2:0]          start_m_i,
  input  logic [2:0]          start_row_count_i,

  output logic                busy_o,
  output logic                done_o,
  output logic                result_valid_o,
  input  logic                result_ready_i,
  output logic [3:0]          result_stream_o,
  output logic signed [31:0] result_dot_o,
  output logic signed [31:0] result_aux_o,
  output logic [15:0]         result_weight_d_o,
  output logic [15:0]         result_weight_dmin_o,
  output logic [31:0]         result_activation_d_o,

  output logic                decode_valid_o,
  output logic [7:0]          decode_k_base_o,
  output logic [3:0]          decode_k_per_context_o,
  output logic [15:0]         decode_stream_valid_o,
  output logic signed [7:0]  decode_weight_quant_o [4][8],
  output logic signed [7:0]  decode_activation_quant_o [4][8],

  output logic [15:0]         group_valid_o,
  output logic [3:0]          group_index_o [16],
  output logic signed [31:0] group_dot_o [16],
  output logic signed [15:0] group_aux_o [16],
  output logic signed [7:0]  group_scale_o [16],
  output logic [7:0]          group_min_o [16],

  output logic [31:0]         useful_pairs_o,
  output logic [31:0]         pair_capacity_o,
  output logic [15:0]         dot_active_cycles_o
);

  qbs_weight_profile_e profile_q;
  logic [2:0] m_q;
  logic [2:0] row_count_q;
  logic [4:0] active_stream_count_q;
  logic [4:0] emitted_count_q;
  logic busy_q;
  logic issue_active_q;
  logic [7:0] k_cursor_q;
  logic s0_valid_q;
  logic [7:0] s0_k_base_q;

  logic [3:0] decoder_k_per;
  logic [3:0] decoder_group_index;
  logic decoder_group_end;
  logic [15:0] decoder_stream_valid;
  logic signed [7:0] decoder_weight_quant [4][8];
  logic signed [7:0] decoder_activation_quant [4][8];
  logic signed [7:0] decoder_scale [16];
  logic [7:0] decoder_min [16];
  logic signed [15:0] decoder_aux [16];
  logic [15:0] decoder_weight_d [4];
  logic [15:0] decoder_weight_dmin [4];
  logic [31:0] decoder_activation_d [4];

  logic [3:0] meta_group_index_q;
  logic meta_group_end_q;
  logic signed [7:0] meta_scale_q [16];
  logic [7:0] meta_min_q [16];
  logic signed [15:0] meta_aux_q [16];
  logic [15:0] meta_weight_d_q [4];
  logic [15:0] meta_weight_dmin_q [4];
  logic [31:0] meta_activation_d_q [4];

  logic dot_valid;
  logic [15:0] dot_stream_valid;
  logic signed [17:0] dot_stream_sum [16];
  logic signed [31:0] group_partial_q [16];

  logic [15:0] slot_valid_q;
  logic signed [31:0] slot_dot_q [16];
  logic signed [15:0] slot_aux_q [16];
  logic signed [7:0] slot_scale_q [16];
  logic [7:0] slot_min_q [16];
  logic slot_last_q [16];
  logic [15:0] slot_weight_d_q [16];
  logic [15:0] slot_weight_dmin_q [16];
  logic [31:0] slot_activation_d_q [16];
  logic signed [31:0] subtotal_dot_q [16];
  logic signed [31:0] subtotal_aux_q [16];

  logic [15:0] result_pending_q;
  logic signed [31:0] result_dot_q [16];
  logic signed [31:0] result_aux_q [16];
  logic [15:0] result_weight_d_q [16];
  logic [15:0] result_weight_dmin_q [16];
  logic [31:0] result_activation_d_q [16];
  logic [3:0] result_rr_q;
  logic [3:0] correction_rr_q;

  logic [15:0] correction_consume;
  logic correction_consume_any;
  logic [3:0] correction_last_index;
  logic signed [47:0] corrected_dot [16];
  logic signed [47:0] corrected_aux [16];

  assign start_ready_o = !busy_q;
  assign busy_o = busy_q;

  qbs_profile_decoder i_profile_decoder (
    .profile_i             (profile_q),
    .m_i                   (m_q),
    .row_count_i           (row_count_q),
    .k_base_i              (s0_k_base_q),
    .weight_block_i        (weight_block_i),
    .activation_block_i    (activation_block_i),
    .k_per_context_o       (decoder_k_per),
    .group_index_o         (decoder_group_index),
    .group_end_o           (decoder_group_end),
    .stream_valid_o        (decoder_stream_valid),
    .weight_quant_o        (decoder_weight_quant),
    .activation_quant_o    (decoder_activation_quant),
    .group_scale_o         (decoder_scale),
    .group_min_o           (decoder_min),
    .group_aux_o           (decoder_aux),
    .weight_d_o            (decoder_weight_d),
    .weight_dmin_o         (decoder_weight_dmin),
    .activation_d_o        (decoder_activation_d)
  );

  qbs_dot_array i_dot_array (
    .clk_i                 (clk_i),
    .rst_ni                (rst_ni),
    .valid_i               (s0_valid_q),
    .m_i                   (m_q),
    .row_count_i           (row_count_q),
    .stream_valid_i        (decoder_stream_valid),
    .weight_quant_i        (decoder_weight_quant),
    .activation_quant_i    (decoder_activation_quant),
    .valid_o               (dot_valid),
    .stream_valid_o        (dot_stream_valid),
    .stream_sum_o          (dot_stream_sum)
  );

  assign decode_valid_o = s0_valid_q;
  assign decode_k_base_o = s0_k_base_q;
  assign decode_k_per_context_o = decoder_k_per;
  assign decode_stream_valid_o = decoder_stream_valid;
  assign decode_weight_quant_o = decoder_weight_quant;
  assign decode_activation_quant_o = decoder_activation_quant;

  always_comb begin
    logic found_first;
    logic found_second;
    correction_consume = '0;
    correction_consume_any = 1'b0;
    correction_last_index = correction_rr_q;
    found_first = 1'b0;
    found_second = 1'b0;
    for (int offset = 0; offset < 16; offset++) begin
      automatic logic [3:0] index = correction_rr_q + 4'(offset);
      if (slot_valid_q[index] && !found_first) begin
        correction_consume[index] = 1'b1;
        correction_consume_any = 1'b1;
        correction_last_index = index;
        found_first = 1'b1;
      end else if (profile_q == QBS_WEIGHT_PROFILE_Q6_K &&
                   slot_valid_q[index] && !found_second) begin
        correction_consume[index] = 1'b1;
        correction_last_index = index;
        found_second = 1'b1;
      end
    end

    for (int stream = 0; stream < 16; stream++) begin
      corrected_dot[stream] = $signed(subtotal_dot_q[stream]) +
          $signed(slot_dot_q[stream]) * $signed(slot_scale_q[stream]);
      corrected_aux[stream] = $signed(subtotal_aux_q[stream]) +
          $signed(slot_aux_q[stream]) * $signed({1'b0, slot_min_q[stream]});
    end
  end

  always_comb begin
    logic found;
    found = 1'b0;
    result_valid_o = 1'b0;
    result_stream_o = result_rr_q;
    result_dot_o = '0;
    result_aux_o = '0;
    result_weight_d_o = '0;
    result_weight_dmin_o = '0;
    result_activation_d_o = '0;
    for (int offset = 0; offset < 16; offset++) begin
      automatic logic [3:0] index = result_rr_q + 4'(offset);
      if (result_pending_q[index] && !found) begin
        found = 1'b1;
        result_valid_o = 1'b1;
        result_stream_o = index;
        result_dot_o = result_dot_q[index];
        result_aux_o = result_aux_q[index];
        result_weight_d_o = result_weight_d_q[index];
        result_weight_dmin_o = result_weight_dmin_q[index];
        result_activation_d_o = result_activation_d_q[index];
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      profile_q <= QBS_WEIGHT_PROFILE_INVALID;
      m_q <= '0;
      row_count_q <= '0;
      active_stream_count_q <= '0;
      emitted_count_q <= '0;
      busy_q <= 1'b0;
      issue_active_q <= 1'b0;
      k_cursor_q <= '0;
      s0_valid_q <= 1'b0;
      s0_k_base_q <= '0;
      meta_group_index_q <= '0;
      meta_group_end_q <= 1'b0;
      slot_valid_q <= '0;
      result_pending_q <= '0;
      result_rr_q <= '0;
      correction_rr_q <= '0;
      done_o <= 1'b0;
      group_valid_o <= '0;
      useful_pairs_o <= '0;
      pair_capacity_o <= '0;
      dot_active_cycles_o <= '0;
      for (int stream = 0; stream < 16; stream++) begin
        group_partial_q[stream] <= '0;
        subtotal_dot_q[stream] <= '0;
        subtotal_aux_q[stream] <= '0;
        slot_dot_q[stream] <= '0;
        slot_aux_q[stream] <= '0;
        slot_scale_q[stream] <= '0;
        slot_min_q[stream] <= '0;
        slot_last_q[stream] <= 1'b0;
        slot_weight_d_q[stream] <= '0;
        slot_weight_dmin_q[stream] <= '0;
        slot_activation_d_q[stream] <= '0;
        result_dot_q[stream] <= '0;
        result_aux_q[stream] <= '0;
        result_weight_d_q[stream] <= '0;
        result_weight_dmin_q[stream] <= '0;
        result_activation_d_q[stream] <= '0;
        group_index_o[stream] <= '0;
        group_dot_o[stream] <= '0;
        group_aux_o[stream] <= '0;
        group_scale_o[stream] <= '0;
        group_min_o[stream] <= '0;
        meta_scale_q[stream] <= '0;
        meta_min_q[stream] <= '0;
        meta_aux_q[stream] <= '0;
      end
      for (int row = 0; row < 4; row++) begin
        meta_weight_d_q[row] <= '0;
        meta_weight_dmin_q[row] <= '0;
      end
      for (int ctx = 0; ctx < 4; ctx++)
        meta_activation_d_q[ctx] <= '0;
    end else begin
      done_o <= 1'b0;
      group_valid_o <= '0;
      s0_valid_q <= 1'b0;

      if (start_valid_i && start_ready_o) begin
        profile_q <= start_profile_i;
        m_q <= start_m_i;
        row_count_q <= start_row_count_i;
        active_stream_count_q <= start_m_i * start_row_count_i;
        emitted_count_q <= '0;
        busy_q <= 1'b1;
        issue_active_q <= 1'b1;
        k_cursor_q <= '0;
        result_rr_q <= '0;
        correction_rr_q <= '0;
        useful_pairs_o <= '0;
        pair_capacity_o <= '0;
        dot_active_cycles_o <= '0;
        slot_valid_q <= '0;
        result_pending_q <= '0;
        for (int stream = 0; stream < 16; stream++) begin
          group_partial_q[stream] <= '0;
          subtotal_dot_q[stream] <= '0;
          subtotal_aux_q[stream] <= '0;
        end
      end else begin
        if (busy_q && issue_active_q) begin
          automatic int unsigned k_per;
          k_per = m_q == 1 ? 8 : (m_q == 2 ? 4 : 2);
          s0_valid_q <= 1'b1;
          s0_k_base_q <= k_cursor_q;
          useful_pairs_o <= useful_pairs_o + row_count_q * m_q * k_per;
          pair_capacity_o <= pair_capacity_o + row_count_q * 8;
          dot_active_cycles_o <= dot_active_cycles_o + 1'b1;
          if (unsigned'(k_cursor_q) + k_per == QbsBlockElements) begin
            issue_active_q <= 1'b0;
          end else begin
            k_cursor_q <= k_cursor_q + 8'(k_per);
          end
        end

        if (s0_valid_q) begin
          meta_group_index_q <= decoder_group_index;
          meta_group_end_q <= decoder_group_end;
          for (int stream = 0; stream < 16; stream++) begin
            meta_scale_q[stream] <= decoder_scale[stream];
            meta_min_q[stream] <= decoder_min[stream];
            meta_aux_q[stream] <= decoder_aux[stream];
          end
          for (int row = 0; row < 4; row++) begin
            meta_weight_d_q[row] <= decoder_weight_d[row];
            meta_weight_dmin_q[row] <= decoder_weight_dmin[row];
          end
          for (int ctx = 0; ctx < 4; ctx++)
            meta_activation_d_q[ctx] <= decoder_activation_d[ctx];
        end

        if (correction_consume_any)
          correction_rr_q <= correction_last_index + 1'b1;
        for (int stream = 0; stream < 16; stream++) begin
          if (correction_consume[stream]) begin
            slot_valid_q[stream] <= 1'b0;
            subtotal_dot_q[stream] <= corrected_dot[stream][31:0];
            subtotal_aux_q[stream] <= corrected_aux[stream][31:0];
            if (slot_last_q[stream]) begin
              result_pending_q[stream] <= 1'b1;
              result_dot_q[stream] <= corrected_dot[stream][31:0];
              result_aux_q[stream] <= profile_q == QBS_WEIGHT_PROFILE_Q4_K
                  ? corrected_aux[stream][31:0] : '0;
              result_weight_d_q[stream] <= slot_weight_d_q[stream];
              result_weight_dmin_q[stream] <= slot_weight_dmin_q[stream];
              result_activation_d_q[stream] <= slot_activation_d_q[stream];
            end
          end
        end

        if (dot_valid) begin
          for (int stream = 0; stream < 16; stream++) begin
            if (dot_stream_valid[stream]) begin
              automatic logic signed [31:0] group_total;
              group_total = group_partial_q[stream] + dot_stream_sum[stream];
              if (meta_group_end_q) begin
                group_partial_q[stream] <= '0;
                slot_valid_q[stream] <= 1'b1;
                slot_dot_q[stream] <= group_total;
                slot_aux_q[stream] <= meta_aux_q[stream];
                slot_scale_q[stream] <= meta_scale_q[stream];
                slot_min_q[stream] <= meta_min_q[stream];
                slot_last_q[stream] <= profile_q == QBS_WEIGHT_PROFILE_Q4_K
                    ? meta_group_index_q == QbsQ4KSubgroupCount - 1
                    : meta_group_index_q == QbsQ6KSubgroupCount - 1;
                slot_weight_d_q[stream] <= meta_weight_d_q[stream / 4];
                slot_weight_dmin_q[stream] <= meta_weight_dmin_q[stream / 4];
                slot_activation_d_q[stream] <= meta_activation_d_q[stream % 4];
                group_valid_o[stream] <= 1'b1;
                group_index_o[stream] <= meta_group_index_q;
                group_dot_o[stream] <= group_total;
                group_aux_o[stream] <= meta_aux_q[stream];
                group_scale_o[stream] <= meta_scale_q[stream];
                group_min_o[stream] <= meta_min_q[stream];
`ifndef SYNTHESIS
                assert (!slot_valid_q[stream] || correction_consume[stream])
                  else $fatal(1, "QBS correction slot overflow: stream=%0d", stream);
`endif
              end else begin
                group_partial_q[stream] <= group_total;
              end
            end
          end
        end

        if (result_valid_o && result_ready_i) begin
          result_pending_q[result_stream_o] <= 1'b0;
          result_rr_q <= result_stream_o + 1'b1;
          emitted_count_q <= emitted_count_q + 1'b1;
          if (emitted_count_q + 1'b1 == active_stream_count_q) begin
            busy_q <= 1'b0;
            done_o <= 1'b1;
          end
        end
      end

`ifndef SYNTHESIS
      if (start_valid_i && start_ready_o) begin
        assert (start_profile_i inside {
            QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q6_K});
        assert (start_m_i inside {[1:4]});
        assert (start_row_count_i inside {[1:4]});
      end
      for (int stream = 0; stream < 16; stream++) begin
        if (correction_consume[stream]) begin
          assert (corrected_dot[stream] <= 48'sh0000_7fff_ffff &&
                  corrected_dot[stream] >= -48'sh0000_8000_0000)
            else $fatal(1, "QBS dot subtotal overflow: stream=%0d", stream);
          assert (corrected_aux[stream] <= 48'sh0000_7fff_ffff &&
                  corrected_aux[stream] >= -48'sh0000_8000_0000)
            else $fatal(1, "QBS aux subtotal overflow: stream=%0d", stream);
        end
      end
`endif
    end
  end

endmodule : qbs_profile_engine_int
