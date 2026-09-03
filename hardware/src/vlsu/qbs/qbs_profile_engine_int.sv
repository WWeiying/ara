// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_profile_engine_int import qbs_pkg::*; (
  input  logic                clk_i,
  input  logic                rst_ni,

  input  logic [7:0]          weight_block_i [4][QbsMaxWeightBlockBytes],
  input  logic [7:0]          activation_block_i [4][QbsMaxActivationBlockBytes],

  input  logic                start_valid_i,
  output logic                start_ready_o,
  input  qbs_weight_profile_e start_profile_i,
  input  qbs_activation_profile_e start_activation_profile_i,
  input  logic [2:0]          start_m_i,
  input  logic [2:0]          start_context_base_i,
  input  logic [2:0]          start_row_count_i,
  input  logic [5:0]          start_row_base_i,
  input  logic                start_first_block_i,

  output logic                busy_o,
  output logic                done_o,
  output logic                result_valid_o,
  input  logic                result_ready_i,
  output logic [3:0]          result_stream_o,
  output logic [2:0]          result_context_base_o,
  output logic [5:0]          result_row_base_o,
  output logic [2:0]          result_row_count_o,
  output logic                result_first_block_o,
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

  localparam int unsigned NumContexts = 2;
  localparam int unsigned NumStreams = 16;
  localparam int unsigned FlatEntries = NumContexts * NumStreams;

  qbs_weight_profile_e profile_q;
  qbs_activation_profile_e activation_profile_q;
  logic [8:0] block_elements_q;
  logic [2:0] m_q;
  logic [2:0] row_count_q;
  logic compute_context_q;
  logic compute_active_q;
  logic issue_active_q;
  logic [7:0] k_cursor_q;
  logic s0_valid_q;
  logic s0_context_q;
  logic [7:0] s0_k_base_q;
  logic dot_context_q;

  logic [NumContexts-1:0] context_valid_q;
  qbs_weight_profile_e context_profile_q [NumContexts];
  logic context_affine_q [NumContexts];
  logic [4:0] context_subgroup_count_q [NumContexts];
  logic [4:0] context_active_stream_count_q [NumContexts];
  logic [4:0] context_emitted_count_q [NumContexts];
  logic [5:0] context_row_base_q [NumContexts];
  logic [2:0] context_base_q [NumContexts];
  logic [2:0] context_row_count_q [NumContexts];
  logic context_first_block_q [NumContexts];

  logic start_context;
  logic start_fire;
  logic tail_wave_requires_correction_drain;
  logic compute_pipeline_empty;
  logic busy_q;

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
  logic signed [31:0] group_partial_q [NumContexts][NumStreams];

  logic [NumStreams-1:0] slot_valid_q [NumContexts];
  logic signed [31:0] slot_dot_q [NumContexts][NumStreams];
  logic signed [15:0] slot_aux_q [NumContexts][NumStreams];
  logic signed [7:0] slot_scale_q [NumContexts][NumStreams];
  logic [7:0] slot_min_q [NumContexts][NumStreams];
  logic slot_last_q [NumContexts][NumStreams];
  logic [15:0] slot_weight_d_q [NumContexts][NumStreams];
  logic [15:0] slot_weight_dmin_q [NumContexts][NumStreams];
  logic [31:0] slot_activation_d_q [NumContexts][NumStreams];
  logic signed [31:0] subtotal_dot_q [NumContexts][NumStreams];
  logic signed [31:0] subtotal_aux_q [NumContexts][NumStreams];

  logic [NumStreams-1:0] result_pending_q [NumContexts];
  logic signed [31:0] result_dot_q [NumContexts][NumStreams];
  logic signed [31:0] result_aux_q [NumContexts][NumStreams];
  logic [15:0] result_weight_d_q [NumContexts][NumStreams];
  logic [15:0] result_weight_dmin_q [NumContexts][NumStreams];
  logic [31:0] result_activation_d_q [NumContexts][NumStreams];

  logic [4:0] result_rr_q;
  logic result_context;
  logic [4:0] correction_rr_q;
  logic [NumStreams-1:0] correction_consume [NumContexts];
  logic correction_consume_any;
  logic [4:0] correction_last_index;
  logic [1:0] correction_valid;
  logic correction_context [2];
  logic [3:0] correction_stream [2];
  logic signed [47:0] correction_dot [2];
  logic signed [47:0] correction_aux [2];

  logic [FlatEntries-1:0] correction_pending_flat;
  logic [FlatEntries-1:0] correction_first_upper_mask;
  logic [FlatEntries-1:0] correction_first_lower_mask;
  logic [FlatEntries-1:0] correction_second_pending;
  logic [FlatEntries-1:0] correction_second_upper_mask;
  logic [FlatEntries-1:0] correction_second_lower_mask;
  logic [4:0] correction_first_upper_index;
  logic [4:0] correction_first_lower_index;
  logic [4:0] correction_first_index;
  logic [4:0] correction_second_start;
  logic [4:0] correction_second_upper_index;
  logic [4:0] correction_second_lower_index;
  logic [4:0] correction_second_index;
  logic correction_first_upper_empty;
  logic correction_first_lower_empty;
  logic correction_second_upper_empty;
  logic correction_second_lower_empty;
  logic correction_first_found;
  logic correction_second_found;

  always_comb begin
    start_context = 1'b0;
    if (context_valid_q[0]) start_context = 1'b1;
  end

  assign busy_q = compute_active_q || (|context_valid_q);
  assign busy_o = busy_q;
  // A 16-element subgroup reaches its first group boundary after only two or
  // four cycles for an M1/M2 tail wave. The preceding M4 wave can still have
  // up to 16 correction slots in flight, so starting that tail immediately
  // would exceed the two-lane correction drain rate. Wider/subgroup-32 waves
  // provide enough lead time or service slack and keep the existing overlap.
  assign tail_wave_requires_correction_drain =
      start_context_base_i == 3'd4 && start_m_i inside {[1:2]} &&
      qbs_weight_subgroup_elements(start_profile_i) == 16;
  assign start_ready_o = !compute_active_q && !context_valid_q[start_context] &&
      (!tail_wave_requires_correction_drain ||
       correction_pending_flat == '0);
  assign start_fire = start_valid_i && start_ready_o;
  assign compute_pipeline_empty = !issue_active_q && !s0_valid_q && !dot_valid;

  qbs_profile_decoder i_profile_decoder (
    .profile_i             (profile_q),
    .activation_profile_i  (activation_profile_q),
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

  for (genvar context_index = 0; context_index < NumContexts;
       context_index++) begin : gen_correction_pending_flat
    for (genvar stream = 0; stream < NumStreams; stream++) begin : gen_stream
      localparam int unsigned FlatIndex = context_index * NumStreams + stream;
      assign correction_pending_flat[FlatIndex] =
          slot_valid_q[context_index][stream];
    end
  end

  always_comb begin
    correction_first_upper_mask = '0;
    correction_first_lower_mask = '0;
    for (int index = 0; index < FlatEntries; index++) begin
      if (5'(index) >= correction_rr_q)
        correction_first_upper_mask[index] = correction_pending_flat[index];
      else
        correction_first_lower_mask[index] = correction_pending_flat[index];
    end
  end

  lzc #(
    .WIDTH ( FlatEntries ),
    .MODE  ( 1'b0       )
  ) i_correction_first_upper_lzc (
    .in_i    ( correction_first_upper_mask  ),
    .cnt_o   ( correction_first_upper_index ),
    .empty_o ( correction_first_upper_empty )
  );

  lzc #(
    .WIDTH ( FlatEntries ),
    .MODE  ( 1'b0       )
  ) i_correction_first_lower_lzc (
    .in_i    ( correction_first_lower_mask  ),
    .cnt_o   ( correction_first_lower_index ),
    .empty_o ( correction_first_lower_empty )
  );

  assign correction_first_found =
      !correction_first_upper_empty || !correction_first_lower_empty;
  assign correction_first_index = !correction_first_upper_empty
      ? correction_first_upper_index : correction_first_lower_index;
  assign correction_second_start = correction_first_index + 1'b1;

  always_comb begin
    correction_second_pending = correction_pending_flat;
    if (correction_first_found)
      correction_second_pending[correction_first_index] = 1'b0;

    correction_second_upper_mask = '0;
    correction_second_lower_mask = '0;
    for (int index = 0; index < FlatEntries; index++) begin
      if (5'(index) >= correction_second_start)
        correction_second_upper_mask[index] = correction_second_pending[index];
      else
        correction_second_lower_mask[index] = correction_second_pending[index];
    end
  end

  lzc #(
    .WIDTH ( FlatEntries ),
    .MODE  ( 1'b0       )
  ) i_correction_second_upper_lzc (
    .in_i    ( correction_second_upper_mask  ),
    .cnt_o   ( correction_second_upper_index ),
    .empty_o ( correction_second_upper_empty )
  );

  lzc #(
    .WIDTH ( FlatEntries ),
    .MODE  ( 1'b0       )
  ) i_correction_second_lower_lzc (
    .in_i    ( correction_second_lower_mask  ),
    .cnt_o   ( correction_second_lower_index ),
    .empty_o ( correction_second_lower_empty )
  );

  assign correction_second_found = correction_first_found &&
      (!correction_second_upper_empty || !correction_second_lower_empty);
  assign correction_second_index = !correction_second_upper_empty
      ? correction_second_upper_index : correction_second_lower_index;

  always_comb begin
    correction_consume = '{default: '0};
    correction_consume_any = 1'b0;
    correction_last_index = correction_rr_q;
    correction_valid = '0;
    correction_context = '{default: '0};
    correction_stream = '{default: '0};

    if (correction_first_found) begin
      correction_consume_any = 1'b1;
      correction_valid[0] = 1'b1;
      correction_context[0] = correction_first_index[4];
      correction_stream[0] = correction_first_index[3:0];
      correction_consume[correction_first_index[4]]
          [correction_first_index[3:0]] = 1'b1;
      correction_last_index = correction_first_index;
    end

    if (correction_second_found) begin
      correction_valid[1] = 1'b1;
      correction_context[1] = correction_second_index[4];
      correction_stream[1] = correction_second_index[3:0];
      correction_consume[correction_second_index[4]]
          [correction_second_index[3:0]] = 1'b1;
      correction_last_index = correction_second_index;
    end
  end

  // Arbitration precedes arithmetic so two shared correction lanes cover the
  // worst-case rate of two 16-element groups per cycle. Both lanes implement
  // affine correction because Q2_K can sustain that rate.
  always_comb begin
    correction_dot = '{default: '0};
    correction_aux = '{default: '0};

    if (correction_valid[0]) begin
      correction_dot[0] =
          $signed(subtotal_dot_q[correction_context[0]][correction_stream[0]]) +
          $signed(slot_dot_q[correction_context[0]][correction_stream[0]]) *
          $signed(slot_scale_q[correction_context[0]][correction_stream[0]]);
      correction_aux[0] =
          $signed(subtotal_aux_q[correction_context[0]][correction_stream[0]]);
      if (context_affine_q[correction_context[0]])
        correction_aux[0] = correction_aux[0] +
            $signed(slot_aux_q[correction_context[0]][correction_stream[0]]) *
            $signed({1'b0,
                slot_min_q[correction_context[0]][correction_stream[0]]});
    end

    if (correction_valid[1]) begin
      correction_dot[1] =
          $signed(subtotal_dot_q[correction_context[1]][correction_stream[1]]) +
          $signed(slot_dot_q[correction_context[1]][correction_stream[1]]) *
          $signed(slot_scale_q[correction_context[1]][correction_stream[1]]);
      correction_aux[1] =
          $signed(subtotal_aux_q[correction_context[1]][correction_stream[1]]);
      if (context_affine_q[correction_context[1]])
        correction_aux[1] = correction_aux[1] +
            $signed(slot_aux_q[correction_context[1]][correction_stream[1]]) *
            $signed({1'b0,
                slot_min_q[correction_context[1]][correction_stream[1]]});
    end
  end

  always_comb begin
    logic found;
    found = 1'b0;
    result_valid_o = 1'b0;
    result_context = result_rr_q[4];
    result_stream_o = result_rr_q[3:0];
    result_context_base_o = '0;
    result_row_base_o = '0;
    result_row_count_o = '0;
    result_first_block_o = 1'b0;
    result_dot_o = '0;
    result_aux_o = '0;
    result_weight_d_o = '0;
    result_weight_dmin_o = '0;
    result_activation_d_o = '0;

    for (int offset = 0; offset < FlatEntries; offset++) begin
      automatic logic [4:0] index = result_rr_q + 5'(offset);
      automatic logic context_index = index[4];
      automatic logic [3:0] stream_index = index[3:0];
      if (result_pending_q[context_index][stream_index] && !found) begin
        found = 1'b1;
        result_valid_o = 1'b1;
        result_context = context_index;
        result_stream_o = stream_index;
        result_context_base_o = context_base_q[context_index];
        result_row_base_o = context_row_base_q[context_index];
        result_row_count_o = context_row_count_q[context_index];
        result_first_block_o = context_first_block_q[context_index];
        result_dot_o = result_dot_q[context_index][stream_index];
        result_aux_o = result_aux_q[context_index][stream_index];
        result_weight_d_o = result_weight_d_q[context_index][stream_index];
        result_weight_dmin_o =
            result_weight_dmin_q[context_index][stream_index];
        result_activation_d_o =
            result_activation_d_q[context_index][stream_index];
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      profile_q <= QBS_WEIGHT_PROFILE_INVALID;
      activation_profile_q <= QBS_ACTIVATION_PROFILE_INVALID;
      block_elements_q <= '0;
      m_q <= '0;
      row_count_q <= '0;
      compute_context_q <= 1'b0;
      compute_active_q <= 1'b0;
      issue_active_q <= 1'b0;
      k_cursor_q <= '0;
      s0_valid_q <= 1'b0;
      s0_context_q <= 1'b0;
      s0_k_base_q <= '0;
      dot_context_q <= 1'b0;
      context_valid_q <= '0;
      result_rr_q <= '0;
      correction_rr_q <= '0;
      meta_group_index_q <= '0;
      meta_group_end_q <= 1'b0;
      done_o <= 1'b0;
      group_valid_o <= '0;
      useful_pairs_o <= '0;
      pair_capacity_o <= '0;
      dot_active_cycles_o <= '0;

      for (int context_index = 0; context_index < NumContexts;
           context_index++) begin
        context_profile_q[context_index] <= QBS_WEIGHT_PROFILE_INVALID;
        context_affine_q[context_index] <= 1'b0;
        context_subgroup_count_q[context_index] <= '0;
        context_active_stream_count_q[context_index] <= '0;
        context_emitted_count_q[context_index] <= '0;
        context_row_base_q[context_index] <= '0;
        context_base_q[context_index] <= '0;
        context_row_count_q[context_index] <= '0;
        context_first_block_q[context_index] <= 1'b0;
        slot_valid_q[context_index] <= '0;
        result_pending_q[context_index] <= '0;
        for (int stream = 0; stream < NumStreams; stream++) begin
          group_partial_q[context_index][stream] <= '0;
          subtotal_dot_q[context_index][stream] <= '0;
          subtotal_aux_q[context_index][stream] <= '0;
          slot_dot_q[context_index][stream] <= '0;
          slot_aux_q[context_index][stream] <= '0;
          slot_scale_q[context_index][stream] <= '0;
          slot_min_q[context_index][stream] <= '0;
          slot_last_q[context_index][stream] <= 1'b0;
          slot_weight_d_q[context_index][stream] <= '0;
          slot_weight_dmin_q[context_index][stream] <= '0;
          slot_activation_d_q[context_index][stream] <= '0;
          result_dot_q[context_index][stream] <= '0;
          result_aux_q[context_index][stream] <= '0;
          result_weight_d_q[context_index][stream] <= '0;
          result_weight_dmin_q[context_index][stream] <= '0;
          result_activation_d_q[context_index][stream] <= '0;
        end
      end

      for (int stream = 0; stream < NumStreams; stream++) begin
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
      for (int context_index = 0; context_index < 4; context_index++)
        meta_activation_d_q[context_index] <= '0;
    end else begin
      done_o <= 1'b0;
      group_valid_o <= '0;
      s0_valid_q <= 1'b0;

      if (start_fire) begin
        profile_q <= start_profile_i;
        activation_profile_q <= start_activation_profile_i;
        block_elements_q <= 9'(qbs_weight_block_elements(start_profile_i));
        m_q <= start_m_i;
        row_count_q <= start_row_count_i;
        compute_context_q <= start_context;
        compute_active_q <= 1'b1;
        issue_active_q <= 1'b1;
        k_cursor_q <= '0;
        context_valid_q[start_context] <= 1'b1;
        context_profile_q[start_context] <= start_profile_i;
        context_affine_q[start_context] <=
            qbs_weight_correction_mode(start_profile_i) ==
                QBS_CORRECTION_AFFINE_MIN;
        context_subgroup_count_q[start_context] <=
            5'(qbs_weight_subgroup_count(start_profile_i));
        context_active_stream_count_q[start_context] <=
            start_m_i * start_row_count_i;
        context_emitted_count_q[start_context] <= '0;
        context_row_base_q[start_context] <= start_row_base_i;
        context_base_q[start_context] <= start_context_base_i;
        context_row_count_q[start_context] <= start_row_count_i;
        context_first_block_q[start_context] <= start_first_block_i;
        slot_valid_q[start_context] <= '0;
        result_pending_q[start_context] <= '0;
        useful_pairs_o <= '0;
        pair_capacity_o <= '0;
        dot_active_cycles_o <= '0;
        for (int stream = 0; stream < NumStreams; stream++) begin
          group_partial_q[start_context][stream] <= '0;
          subtotal_dot_q[start_context][stream] <= '0;
          subtotal_aux_q[start_context][stream] <= '0;
        end
      end

      if (compute_active_q && issue_active_q) begin
        automatic int unsigned k_per;
        k_per = m_q == 1 ? 8 : (m_q == 2 ? 4 : 2);
        s0_valid_q <= 1'b1;
        s0_context_q <= compute_context_q;
        s0_k_base_q <= k_cursor_q;
        useful_pairs_o <= useful_pairs_o + row_count_q * m_q * k_per;
        pair_capacity_o <= pair_capacity_o + row_count_q * 8;
        dot_active_cycles_o <= dot_active_cycles_o + 1'b1;
        if (unsigned'(k_cursor_q) + k_per == block_elements_q)
          issue_active_q <= 1'b0;
        else
          k_cursor_q <= k_cursor_q + 8'(k_per);
      end

      if (s0_valid_q) begin
        dot_context_q <= s0_context_q;
        meta_group_index_q <= decoder_group_index;
        meta_group_end_q <= decoder_group_end;
        for (int stream = 0; stream < NumStreams; stream++) begin
          meta_scale_q[stream] <= decoder_scale[stream];
          meta_min_q[stream] <= decoder_min[stream];
          meta_aux_q[stream] <= decoder_aux[stream];
        end
        for (int row = 0; row < 4; row++) begin
          meta_weight_d_q[row] <= decoder_weight_d[row];
          meta_weight_dmin_q[row] <= decoder_weight_dmin[row];
        end
        for (int context_index = 0; context_index < 4; context_index++)
          meta_activation_d_q[context_index] <=
              decoder_activation_d[context_index];
      end

      if (correction_consume_any)
        correction_rr_q <= correction_last_index + 1'b1;
      for (int lane = 0; lane < 2; lane++) begin
        if (correction_valid[lane]) begin
          slot_valid_q[correction_context[lane]][correction_stream[lane]] <= 1'b0;
          subtotal_dot_q[correction_context[lane]][correction_stream[lane]] <=
              correction_dot[lane][31:0];
          subtotal_aux_q[correction_context[lane]][correction_stream[lane]] <=
              correction_aux[lane][31:0];
          if (slot_last_q[correction_context[lane]][correction_stream[lane]]) begin
            result_pending_q[correction_context[lane]][correction_stream[lane]] <=
                1'b1;
            result_dot_q[correction_context[lane]][correction_stream[lane]] <=
                correction_dot[lane][31:0];
            result_aux_q[correction_context[lane]][correction_stream[lane]] <=
                context_affine_q[correction_context[lane]]
                ? correction_aux[lane][31:0] : '0;
            result_weight_d_q[correction_context[lane]][correction_stream[lane]] <=
                slot_weight_d_q[correction_context[lane]][correction_stream[lane]];
            result_weight_dmin_q[correction_context[lane]][correction_stream[lane]] <=
                slot_weight_dmin_q[correction_context[lane]][correction_stream[lane]];
            result_activation_d_q[correction_context[lane]][correction_stream[lane]] <=
                slot_activation_d_q[correction_context[lane]][correction_stream[lane]];
          end
        end
      end

      if (dot_valid) begin
        for (int stream = 0; stream < NumStreams; stream++) begin
          if (dot_stream_valid[stream]) begin
            automatic logic signed [31:0] group_total;
            group_total = group_partial_q[dot_context_q][stream] +
                dot_stream_sum[stream];
            if (meta_group_end_q) begin
              group_partial_q[dot_context_q][stream] <= '0;
              slot_valid_q[dot_context_q][stream] <= 1'b1;
              slot_dot_q[dot_context_q][stream] <= group_total;
              slot_aux_q[dot_context_q][stream] <= meta_aux_q[stream];
              slot_scale_q[dot_context_q][stream] <= meta_scale_q[stream];
              slot_min_q[dot_context_q][stream] <= meta_min_q[stream];
              slot_last_q[dot_context_q][stream] <=
                  unsigned'(meta_group_index_q) + 1 ==
                      context_subgroup_count_q[dot_context_q];
              slot_weight_d_q[dot_context_q][stream] <=
                  meta_weight_d_q[stream / 4];
              slot_weight_dmin_q[dot_context_q][stream] <=
                  meta_weight_dmin_q[stream / 4];
              slot_activation_d_q[dot_context_q][stream] <=
                  meta_activation_d_q[stream % 4];
              group_valid_o[stream] <= 1'b1;
              group_index_o[stream] <= meta_group_index_q;
              group_dot_o[stream] <= group_total;
              group_aux_o[stream] <= meta_aux_q[stream];
              group_scale_o[stream] <= meta_scale_q[stream];
              group_min_o[stream] <= meta_min_q[stream];
            end else begin
              group_partial_q[dot_context_q][stream] <= group_total;
            end
          end
        end
      end

      if (result_valid_o && result_ready_i) begin
        result_pending_q[result_context][result_stream_o] <= 1'b0;
        result_rr_q <= {result_context, result_stream_o} + 1'b1;
        context_emitted_count_q[result_context] <=
            context_emitted_count_q[result_context] + 1'b1;
        if (context_emitted_count_q[result_context] + 1'b1 ==
            context_active_stream_count_q[result_context])
          context_valid_q[result_context] <= 1'b0;
      end

      if (compute_active_q && compute_pipeline_empty) begin
        compute_active_q <= 1'b0;
        done_o <= 1'b1;
      end

`ifndef SYNTHESIS
      if (start_fire) begin
        assert (qbs_weight_block_bytes(start_profile_i) != 0);
        assert (qbs_profiles_compatible(start_profile_i,
                                        start_activation_profile_i));
        assert (start_m_i inside {[1:4]});
        assert (start_context_base_i inside {3'd0, 3'd4});
        assert (unsigned'(start_context_base_i) + unsigned'(start_m_i) <=
                QbsMaxM);
        if (tail_wave_requires_correction_drain)
          assert (correction_pending_flat == '0)
            else $fatal(1, "QBS started a short tail wave before correction drain");
        assert (start_row_count_i inside {[1:4]});
        assert (!context_valid_q[start_context])
          else $fatal(1, "QBS reused a live integer tile context");
      end
      for (int lane = 0; lane < 2; lane++) begin
        if (correction_valid[lane]) begin
          assert (correction_dot[lane] <= 48'sh0000_7fff_ffff &&
                  correction_dot[lane] >= -48'sh0000_8000_0000)
            else $fatal(1,
                "QBS dot subtotal overflow: context=%0d stream=%0d",
                correction_context[lane], correction_stream[lane]);
          assert (correction_aux[lane] <= 48'sh0000_7fff_ffff &&
                  correction_aux[lane] >= -48'sh0000_8000_0000)
            else $fatal(1,
                "QBS aux subtotal overflow: context=%0d stream=%0d",
                correction_context[lane], correction_stream[lane]);
        end
      end
      for (int context_index = 0; context_index < NumContexts;
           context_index++) begin
        for (int stream = 0; stream < NumStreams; stream++) begin
          if (dot_valid && dot_stream_valid[stream] && meta_group_end_q &&
              dot_context_q == context_index) begin
            assert (!slot_valid_q[context_index][stream] ||
                    correction_consume[context_index][stream])
              else $fatal(1,
                  "QBS correction slot overflow: context=%0d stream=%0d",
                  context_index, stream);
          end
        end
      end
      assert (!(context_valid_q[0] && context_valid_q[1] && start_ready_o))
        else $fatal(1, "QBS advertised a full tile-context queue as ready");
      if (done_o) begin
        assert (busy_q && context_valid_q[compute_context_q])
          else $fatal(1,
              "QBS compute completion lost its draining tile context");
      end
`endif
    end
  end

endmodule : qbs_profile_engine_int
