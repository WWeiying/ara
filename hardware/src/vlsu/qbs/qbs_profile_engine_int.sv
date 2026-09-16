// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_profile_engine_int import qbs_pkg::*; #(
  parameter bit CompactRead = 1'b0
) (
  input  logic                clk_i,
  input  logic                rst_ni,

  input  logic [7:0]          weight_block_i [4][QbsMaxWeightBlockBytes],
  input  logic [7:0]          activation_block_i [4][QbsMaxActivationBlockBytes],
  input logic [127:0] weight_window_i [4][2],
  input logic [255:0] activation_window_i [4],
  input logic [7:0] weight_side_i [4][20], activation_side_i [4][36],
  output logic                buffer_read_valid_o,
  output logic [7:0]          buffer_read_k_base_o,

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
  localparam int unsigned DotLatency = 3;

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
  logic correction_pipeline_busy;
  logic correction_drain_empty;
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
  // A stream is {weight row, local activation context}. Do not replicate
  // row-only or context-only metadata across all sixteen streams.
  logic signed [7:0] meta_row_scale_q [4];
  logic [5:0] meta_row_min_q [4];
  logic signed [15:0] meta_context_aux_q [4];
  typedef struct packed {
    logic context_id;
    logic [3:0] group_index;
    logic group_end;
    logic [3:0][7:0] row_scale;
    logic [3:0][5:0] row_min;
    logic [3:0][15:0] context_aux;
  } dot_metadata_t;
  dot_metadata_t dot_metadata_q [DotLatency];
  logic [DotLatency-1:0] dot_metadata_valid_q;
  logic [15:0] context_weight_d_q [NumContexts][4];
  logic [15:0] context_weight_dmin_q [NumContexts][4];
  logic [31:0] context_activation_d_q [NumContexts][4];

  logic dot_valid;
  logic [15:0] dot_stream_valid;
  logic signed [18:0] dot_stream_sum [16];
  // The largest unscaled group has 32 signed INT8 products (+524288).
  // Q6_K bounds a block subtotal to [-2^27, 2^27-1]. Keep guard bits in
  // the correction arithmetic and check before narrowing stored results.
  logic signed [20:0] group_partial_q [NumContexts][NumStreams];

  logic [NumStreams-1:0] slot_valid_q [NumContexts];
  logic signed [20:0] slot_dot_q [NumContexts][NumStreams];
  // All active streams in a context deposit one subgroup together. Retain
  // its shared row/context metadata until the correction operands consume it.
  logic signed [15:0] slot_aux_q [NumContexts][4];
  logic signed [7:0] slot_scale_q [NumContexts][4];
  logic [5:0] slot_min_q [NumContexts][4];
  logic slot_last_q [NumContexts];
  logic signed [27:0] subtotal_dot_q [NumContexts][NumStreams];
  // Even 16 groups of full signed-16 bsum times unsigned-6 min fit in 26 bits.
  logic signed [25:0] subtotal_aux_q [NumContexts][NumStreams];

  logic [NumStreams-1:0] result_pending_q [NumContexts];

  logic [4:0] result_rr_q;
  logic result_context;
  logic [4:0] correction_rr_q;
  logic [NumStreams-1:0] correction_consume [NumContexts];
  logic correction_consume_any;
  logic [4:0] correction_last_index;
  logic [1:0] correction_valid;
  logic correction_context [2];
  logic [3:0] correction_stream [2];
  logic signed [28:0] correction_dot_product [2];
  logic signed [29:0] correction_dot [2];
  // Preserve all sixteen encoded bsum bits, including noncanonical inputs.
  logic signed [22:0] correction_aux_product [2];
  logic signed [26:0] correction_aux [2];

  typedef struct packed {
    logic valid;
    logic context_id;
    logic [3:0] stream;
    logic last_group;
    logic affine;
    logic signed [20:0] dot;
    logic signed [15:0] aux;
    logic signed [7:0] scale;
    logic [5:0] minimum;
  } correction_operand_t;
  typedef struct packed {
    logic valid;
    logic context_id;
    logic [3:0] stream;
    logic last_group;
    logic signed [28:0] dot_product;
    logic signed [22:0] aux_product;
  } correction_product_t;
  correction_operand_t correction_operand_q [2];
  correction_product_t correction_product_q [2];

  logic [FlatEntries-1:0] correction_pending_flat;
  logic [FlatEntries-1:0] correction_first_upper_mask;
  logic [FlatEntries-1:0] correction_first_lower_mask;
  logic [4:0] correction_first_index;
  logic [4:0] correction_second_index;
  logic correction_first_found;
  logic correction_second_found;

  typedef struct packed {
    logic first_valid;
    logic [4:0] first_index;
    logic second_valid;
    logic [4:0] second_index;
  } correction_selection_t;
  correction_selection_t correction_upper, correction_lower;

  // Prefix counts saturate at two. Both grants are decoded together, so the
  // second grant does not wait for the first index and a second rotating mask.
  function automatic correction_selection_t first_two(
      input logic [FlatEntries-1:0] pending);
    logic [FlatEntries-1:0] any_prefix [$clog2(FlatEntries)+1];
    logic [FlatEntries-1:0] two_prefix [$clog2(FlatEntries)+1];
    correction_selection_t selection;
    any_prefix[0] = pending;
    two_prefix[0] = '0;
    for (int level = 0; level < $clog2(FlatEntries); level++) begin
      for (int bit_index = 0; bit_index < FlatEntries; bit_index++) begin
        any_prefix[level+1][bit_index] = any_prefix[level][bit_index];
        two_prefix[level+1][bit_index] = two_prefix[level][bit_index];
        if (bit_index >= (1 << level)) begin
          any_prefix[level+1][bit_index] |=
              any_prefix[level][bit_index-(1 << level)];
          two_prefix[level+1][bit_index] |=
              two_prefix[level][bit_index-(1 << level)] |
              (any_prefix[level][bit_index] &
               any_prefix[level][bit_index-(1 << level)]);
        end
      end
    end
    selection = '0;
    selection.first_valid = any_prefix[$clog2(FlatEntries)][FlatEntries-1];
    selection.second_valid = two_prefix[$clog2(FlatEntries)][FlatEntries-1];
    for (int bit_index = 1; bit_index < FlatEntries; bit_index++) begin
      selection.first_index |= 5'(bit_index) & {5{pending[bit_index] &
          ~any_prefix[$clog2(FlatEntries)][bit_index-1]}};
      selection.second_index |= 5'(bit_index) & {5{pending[bit_index] &
          any_prefix[$clog2(FlatEntries)][bit_index-1] &
          ~two_prefix[$clog2(FlatEntries)][bit_index-1]}};
    end
    return selection;
  endfunction : first_two

  always_comb begin
    start_context = 1'b0;
    if (context_valid_q[0]) start_context = 1'b1;
  end

  assign correction_pipeline_busy = correction_operand_q[0].valid ||
      correction_operand_q[1].valid || correction_product_q[0].valid ||
      correction_product_q[1].valid;
  assign correction_drain_empty = correction_pending_flat == '0 &&
      !correction_pipeline_busy;
  assign busy_q = compute_active_q || (|context_valid_q) || correction_pipeline_busy;
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
       correction_drain_empty);
  assign start_fire = start_valid_i && start_ready_o;
  assign compute_pipeline_empty = !issue_active_q && !s0_valid_q &&
      !(|dot_metadata_valid_q) && !dot_valid;
  // Read SRAM on the edge that registers s0_k_base_q. Its data reaches the
  // decoder with the existing s0 stage, without adding a dot-product stage.
  assign buffer_read_valid_o = compute_active_q && issue_active_q;
  assign buffer_read_k_base_o = k_cursor_q;

  qbs_profile_decoder #(.CompactRead(CompactRead)) i_profile_decoder (
    .profile_i             (profile_q),
    .activation_profile_i  (activation_profile_q),
    .m_i                   (m_q),
    .row_count_i           (row_count_q),
    .k_base_i              (s0_k_base_q),
    .weight_block_i        (weight_block_i),
    .activation_block_i    (activation_block_i),
    .weight_window_i, .activation_window_i, .weight_side_i, .activation_side_i,
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

  assign dot_context_q = dot_metadata_q[DotLatency-1].context_id;
  assign meta_group_index_q = dot_metadata_q[DotLatency-1].group_index;
  assign meta_group_end_q = dot_metadata_q[DotLatency-1].group_end;
  for (genvar index = 0; index < 4; index++) begin : gen_dot_metadata
    assign meta_row_scale_q[index] = dot_metadata_q[DotLatency-1].row_scale[index];
    assign meta_row_min_q[index] = dot_metadata_q[DotLatency-1].row_min[index];
    assign meta_context_aux_q[index] = dot_metadata_q[DotLatency-1].context_aux[index];
  end

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

  assign correction_upper = first_two(correction_first_upper_mask);
  assign correction_lower = first_two(correction_first_lower_mask);
  assign correction_first_found = correction_upper.first_valid || correction_lower.first_valid;
  assign correction_first_index = correction_upper.first_valid
      ? correction_upper.first_index : correction_lower.first_index;
  assign correction_second_found = correction_upper.second_valid ||
      (correction_upper.first_valid && correction_lower.first_valid) ||
      correction_lower.second_valid;
  assign correction_second_index = correction_upper.second_valid
      ? correction_upper.second_index : correction_upper.first_valid
      ? correction_lower.first_index : correction_lower.second_index;

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

  // Two shared lanes retain two corrections/cycle. Read the subtotal only at
  // commit, not at selection: earlier updates to the same stream must be visible.
  always_comb begin
    correction_dot_product = '{default: '0};
    correction_aux_product = '{default: '0};
    correction_dot = '{default: '0};
    correction_aux = '{default: '0};

    for (int lane = 0; lane < 2; lane++) begin
      if (correction_operand_q[lane].valid) begin
        correction_dot_product[lane] =
            correction_operand_q[lane].dot * correction_operand_q[lane].scale;
        if (correction_operand_q[lane].affine)
          correction_aux_product[lane] = correction_operand_q[lane].aux *
              $signed({1'b0, correction_operand_q[lane].minimum});
      end
      if (correction_product_q[lane].valid) begin
        correction_dot[lane] = $signed(subtotal_dot_q[
            correction_product_q[lane].context_id][correction_product_q[lane].stream]) +
            correction_product_q[lane].dot_product;
        correction_aux[lane] = $signed(subtotal_aux_q[
            correction_product_q[lane].context_id][correction_product_q[lane].stream]) +
            correction_product_q[lane].aux_product;
      end
    end
  end

  logic [FlatEntries-1:0] result_upper, result_lower;
  logic [4:0] result_upper_index, result_lower_index, result_index;
  logic result_upper_empty, result_lower_empty, result_found;
  for (genvar index = 0; index < FlatEntries; index++) begin : gen_result_mask
    wire pending_result = result_pending_q[index / NumStreams][index % NumStreams];
    assign result_upper[index] = pending_result && 5'(index) >= result_rr_q;
    assign result_lower[index] = pending_result && 5'(index) < result_rr_q;
  end
  lzc #(.WIDTH(FlatEntries), .MODE(1'b0)) i_result_upper (
    .in_i(result_upper), .cnt_o(result_upper_index), .empty_o(result_upper_empty));
  lzc #(.WIDTH(FlatEntries), .MODE(1'b0)) i_result_lower (
    .in_i(result_lower), .cnt_o(result_lower_index), .empty_o(result_lower_empty));
  assign result_found = !result_upper_empty || !result_lower_empty;
  assign result_index = !result_upper_empty ? result_upper_index : result_lower_index;

  always_comb begin
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

    begin
      automatic logic [4:0] index = result_index;
      automatic logic context_index = index[4];
      automatic logic [3:0] stream_index = index[3:0];
      if (result_found) begin
        result_valid_o = 1'b1;
        result_context = context_index;
        result_stream_o = stream_index;
        result_context_base_o = context_base_q[context_index];
        result_row_base_o = context_row_base_q[context_index];
        result_row_count_o = context_row_count_q[context_index];
        result_first_block_o = context_first_block_q[context_index];
        // A context cannot be reused until every pending result is consumed.
        // Its final subtotals already provide stable result storage.
        result_dot_o = subtotal_dot_q[context_index][stream_index];
        result_aux_o = context_affine_q[context_index]
            ? $signed(subtotal_aux_q[context_index][stream_index]) : 32'sd0;
        result_weight_d_o = context_weight_d_q[context_index][stream_index[3:2]];
        result_weight_dmin_o =
            context_weight_dmin_q[context_index][stream_index[3:2]];
        result_activation_d_o =
            context_activation_d_q[context_index][stream_index[1:0]];
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
      dot_metadata_valid_q <= '0;
      for (int stage = 0; stage < DotLatency; stage++)
        dot_metadata_q[stage] <= '0;
      for (int lane = 0; lane < 2; lane++) begin
        correction_operand_q[lane] <= '0;
        correction_product_q[lane] <= '0;
      end
      context_valid_q <= '0;
      result_rr_q <= '0;
      correction_rr_q <= '0;
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
        slot_last_q[context_index] <= 1'b0;
        result_pending_q[context_index] <= '0;
        for (int index = 0; index < 4; index++) begin
          context_weight_d_q[context_index][index] <= '0;
          context_weight_dmin_q[context_index][index] <= '0;
          context_activation_d_q[context_index][index] <= '0;
          slot_aux_q[context_index][index] <= '0;
          slot_scale_q[context_index][index] <= '0;
          slot_min_q[context_index][index] <= '0;
        end
        for (int stream = 0; stream < NumStreams; stream++) begin
          group_partial_q[context_index][stream] <= '0;
          subtotal_dot_q[context_index][stream] <= '0;
          subtotal_aux_q[context_index][stream] <= '0;
          slot_dot_q[context_index][stream] <= '0;
        end
      end

      for (int stream = 0; stream < NumStreams; stream++) begin
        group_index_o[stream] <= '0;
        group_dot_o[stream] <= '0;
        group_aux_o[stream] <= '0;
        group_scale_o[stream] <= '0;
        group_min_o[stream] <= '0;
      end
    end else begin
      done_o <= 1'b0;
      group_valid_o <= '0;
      s0_valid_q <= 1'b0;
      dot_metadata_valid_q <= {dot_metadata_valid_q[DotLatency-2:0], s0_valid_q};
      for (int stage = 1; stage < DotLatency; stage++) begin
        if (dot_metadata_valid_q[stage-1])
          dot_metadata_q[stage] <= dot_metadata_q[stage-1];
      end

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
        dot_metadata_q[0].context_id <= s0_context_q;
        dot_metadata_q[0].group_index <= decoder_group_index;
        dot_metadata_q[0].group_end <= decoder_group_end;
        for (int index = 0; index < 4; index++) begin
          dot_metadata_q[0].row_scale[index] <= decoder_scale[4 * index];
          dot_metadata_q[0].row_min[index] <= decoder_min[4 * index][5:0];
          dot_metadata_q[0].context_aux[index] <= decoder_aux[index];
          if (s0_k_base_q == 0) begin
            context_weight_d_q[s0_context_q][index] <= decoder_weight_d[index];
            context_weight_dmin_q[s0_context_q][index] <= decoder_weight_dmin[index];
            context_activation_d_q[s0_context_q][index] <= decoder_activation_d[index];
          end
        end
      end

      if (correction_consume_any)
        correction_rr_q <= correction_last_index + 1'b1;
      for (int lane = 0; lane < 2; lane++) begin
        correction_operand_q[lane].valid <= correction_valid[lane];
        correction_product_q[lane].valid <= correction_operand_q[lane].valid;
        if (correction_valid[lane]) begin
`ifndef SYNTHESIS
          assert (!result_pending_q[correction_context[lane]][correction_stream[lane]])
            else $fatal(1, "QBS correction overwrote an unconsumed result");
`endif
          slot_valid_q[correction_context[lane]][correction_stream[lane]] <= 1'b0;
          correction_operand_q[lane].context_id <= correction_context[lane];
          correction_operand_q[lane].stream <= correction_stream[lane];
          correction_operand_q[lane].last_group <=
              slot_last_q[correction_context[lane]];
          correction_operand_q[lane].affine <= context_affine_q[correction_context[lane]];
          correction_operand_q[lane].dot <=
              slot_dot_q[correction_context[lane]][correction_stream[lane]];
          correction_operand_q[lane].aux <=
              slot_aux_q[correction_context[lane]][correction_stream[lane][1:0]];
          correction_operand_q[lane].scale <=
              slot_scale_q[correction_context[lane]][correction_stream[lane][3:2]];
          correction_operand_q[lane].minimum <=
              slot_min_q[correction_context[lane]][correction_stream[lane][3:2]];
        end
        if (correction_operand_q[lane].valid) begin
          correction_product_q[lane].context_id <= correction_operand_q[lane].context_id;
          correction_product_q[lane].stream <= correction_operand_q[lane].stream;
          correction_product_q[lane].last_group <= correction_operand_q[lane].last_group;
          correction_product_q[lane].dot_product <= correction_dot_product[lane];
          correction_product_q[lane].aux_product <= correction_aux_product[lane];
        end
        if (correction_product_q[lane].valid) begin
          subtotal_dot_q[correction_product_q[lane].context_id]
              [correction_product_q[lane].stream] <=
              correction_dot[lane][27:0];
          subtotal_aux_q[correction_product_q[lane].context_id]
              [correction_product_q[lane].stream] <=
              correction_aux[lane][25:0];
          if (correction_product_q[lane].last_group) begin
            result_pending_q[correction_product_q[lane].context_id]
                [correction_product_q[lane].stream] <=
                1'b1;
          end
        end
      end

      if (dot_valid) begin
        if (meta_group_end_q && |dot_stream_valid) begin
          for (int index = 0; index < 4; index++) begin
            slot_aux_q[dot_context_q][index] <= meta_context_aux_q[index];
            slot_scale_q[dot_context_q][index] <= meta_row_scale_q[index];
            slot_min_q[dot_context_q][index] <= meta_row_min_q[index];
          end
          slot_last_q[dot_context_q] <= unsigned'(meta_group_index_q) + 1 ==
              context_subgroup_count_q[dot_context_q];
`ifndef SYNTHESIS
          assert ((slot_valid_q[dot_context_q] &
                   ~correction_consume[dot_context_q]) == '0)
            else $fatal(1, "QBS shared subgroup metadata overwritten before consumption");
`endif
        end
        for (int stream = 0; stream < NumStreams; stream++) begin
          if (dot_stream_valid[stream]) begin
            automatic logic signed [21:0] group_total;
            group_total = group_partial_q[dot_context_q][stream] +
                dot_stream_sum[stream];
            if (meta_group_end_q) begin
              group_partial_q[dot_context_q][stream] <= '0;
              slot_valid_q[dot_context_q][stream] <= 1'b1;
              slot_dot_q[dot_context_q][stream] <= group_total[20:0];
              group_valid_o[stream] <= 1'b1;
              group_index_o[stream] <= meta_group_index_q;
              group_dot_o[stream] <= group_total;
              group_aux_o[stream] <= meta_context_aux_q[stream % 4];
              group_scale_o[stream] <= meta_row_scale_q[stream / 4];
              group_min_o[stream] <= {2'b0, meta_row_min_q[stream / 4]};
            end else begin
              group_partial_q[dot_context_q][stream] <= group_total[20:0];
            end
`ifndef SYNTHESIS
            assert (group_total[21] == group_total[20])
              else $fatal(1, "QBS unscaled group overflow");
`endif
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
          assert (correction_drain_empty)
            else $fatal(1, "QBS started a short tail wave before correction drain");
        assert (start_row_count_i inside {[1:4]});
        assert (!context_valid_q[start_context])
          else $fatal(1, "QBS reused a live integer tile context");
      end
      for (int lane = 0; lane < 2; lane++) begin
        if (correction_product_q[lane].valid) begin
          assert (context_valid_q[correction_product_q[lane].context_id] &&
              !result_pending_q[correction_product_q[lane].context_id]
                  [correction_product_q[lane].stream])
            else $fatal(1, "QBS correction committed to a released/completed stream");
          assert (correction_dot[lane] <= 30'sd134217727 &&
                  correction_dot[lane] >= -30'sd134217728)
            else $fatal(1,
                "QBS dot subtotal overflow: context=%0d stream=%0d",
                correction_product_q[lane].context_id, correction_product_q[lane].stream);
          assert (correction_aux[lane][26] == correction_aux[lane][25])
            else $fatal(1,
                "QBS aux subtotal overflow: context=%0d stream=%0d",
                correction_product_q[lane].context_id, correction_product_q[lane].stream);
        end
      end
      assert (dot_valid == dot_metadata_valid_q[DotLatency-1])
        else $fatal(1, "QBS dot data and metadata pipeline lost alignment");
      if (correction_product_q[0].valid && correction_product_q[1].valid)
        assert ({correction_product_q[0].context_id, correction_product_q[0].stream} !=
                {correction_product_q[1].context_id, correction_product_q[1].stream})
          else $fatal(1, "QBS correction lanes committed the same stream twice");
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
      if (s0_valid_q) begin
        if (s0_k_base_q == 0)
          assert (result_pending_q[s0_context_q] == '0)
            else $fatal(1, "QBS metadata overwritten before result drain");
        for (int stream = 0; stream < NumStreams; stream++) begin
          if (decoder_stream_valid[stream]) begin
            assert (decoder_scale[stream] == decoder_scale[4 * (stream / 4)] &&
                    decoder_min[stream] == decoder_min[4 * (stream / 4)] &&
                    decoder_aux[stream] == decoder_aux[stream % 4] &&
                    decoder_min[stream] <= 8'd63)
              else $fatal(1, "QBS row/context metadata factoring violated");
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
