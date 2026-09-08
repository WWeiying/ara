// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Compare observable behavior every cycle against the pre-port RTL. Invalid
// payload bits are deliberately excluded; their values are not an interface.
module qbs_fp_equivalence import qbs_pkg::*; #(
  parameter int unsigned NumAccumulators = QbsMaxResults,
  parameter int unsigned AccIndexWidth = $clog2(NumAccumulators)
) (
  input logic clk_i, rst_ni, clear_i, request_valid_i, request_ready_o,
  input logic [3:0] request_slot_i,
  input qbs_weight_profile_e request_profile_i,
  input qbs_activation_profile_e request_activation_profile_i,
  input logic [AccIndexWidth-1:0] request_accumulator_index_i,
  input logic request_first_block_i,
  input logic signed [31:0] request_dot_i, request_aux_i,
  input logic [15:0] request_weight_d_i, request_weight_dmin_i,
  input logic [31:0] request_activation_d_i,
  input logic [AccIndexWidth-1:0] read_index_i,
  input logic read_valid_o,
  input logic [31:0] read_data_o,
  input logic [3:0] bank_read_row_i,
  input logic [7:0] bank_read_valid_o,
  input logic [31:0] bank_read_data_o [8],
  input logic update_valid_o,
  input logic [AccIndexWidth-1:0] update_index_o,
  input logic [31:0] update_data_o,
  input logic [4:0] fflags_o,
  input logic busy_o,
  input logic [31:0] fp_uop_issue_o, table_occupancy_sum_o,
  input logic [4:0] table_occupancy_max_o,
  input logic [31:0] table_full_cycles_o, accumulator_updates_o
);
  logic ref_ready, ref_read_valid, ref_update_valid, ref_busy;
  logic [31:0] ref_read_data, ref_update_data;
  logic [AccIndexWidth-1:0] ref_update_index;
  logic [7:0] ref_bank_valid;
  logic [31:0] ref_bank_data [8];
  logic [4:0] ref_flags, ref_occ_max;
  logic [31:0] ref_uops, ref_occ_sum, ref_full, ref_updates;
  qbs_fp_accumulator_reference #(.NumAccumulators(NumAccumulators),
      .AccIndexWidth(AccIndexWidth)) i_reference (
    .request_ready_o(ref_ready), .read_valid_o(ref_read_valid),
    .read_data_o(ref_read_data), .bank_read_valid_o(ref_bank_valid),
    .bank_read_data_o(ref_bank_data), .update_valid_o(ref_update_valid),
    .update_index_o(ref_update_index), .update_data_o(ref_update_data),
    .fflags_o(ref_flags), .busy_o(ref_busy), .fp_uop_issue_o(ref_uops),
    .table_occupancy_sum_o(ref_occ_sum), .table_occupancy_max_o(ref_occ_max),
    .table_full_cycles_o(ref_full), .accumulator_updates_o(ref_updates), .*
  );
  always @(negedge clk_i) if (rst_ni) begin
    assert ({request_ready_o, read_valid_o, bank_read_valid_o, update_valid_o,
        fflags_o, busy_o, fp_uop_issue_o, table_occupancy_sum_o,
        table_occupancy_max_o, table_full_cycles_o, accumulator_updates_o} ===
        {ref_ready, ref_read_valid, ref_bank_valid, ref_update_valid,
        ref_flags, ref_busy, ref_uops, ref_occ_sum, ref_occ_max, ref_full,
        ref_updates}) else $fatal(1, "QBS FP control/cycle mismatch");
    if (update_valid_o)
      assert ({update_index_o, update_data_o} === {ref_update_index, ref_update_data})
        else $fatal(1, "QBS FP update mismatch");
    if (read_valid_o)
      assert (read_data_o === ref_read_data) else $fatal(1, "QBS FP read mismatch");
    for (int bank = 0; bank < 8; bank++) if (bank_read_valid_o[bank])
      assert (bank_read_data_o[bank] === ref_bank_data[bank])
        else $fatal(1, "QBS FP bank %0d mismatch", bank);
  end
endmodule

bind qbs_fp_accumulator qbs_fp_equivalence #(
    .NumAccumulators(NumAccumulators), .AccIndexWidth(AccIndexWidth))
    i_timing_equivalence (.*);

module qbs_int_equivalence import qbs_pkg::*; (
  input logic clk_i, rst_ni,
  input logic [7:0] weight_block_i [4][QbsMaxWeightBlockBytes],
  input logic [7:0] activation_block_i [4][QbsMaxActivationBlockBytes],
  input logic start_valid_i, start_ready_o,
  input qbs_weight_profile_e start_profile_i,
  input qbs_activation_profile_e start_activation_profile_i,
  input logic [2:0] start_m_i, start_context_base_i, start_row_count_i,
  input logic [5:0] start_row_base_i,
  input logic start_first_block_i, busy_o, done_o, result_valid_o, result_ready_i,
  input logic [3:0] result_stream_o,
  input logic [2:0] result_context_base_o,
  input logic [5:0] result_row_base_o,
  input logic [2:0] result_row_count_o,
  input logic result_first_block_o,
  input logic signed [31:0] result_dot_o, result_aux_o,
  input logic [15:0] result_weight_d_o, result_weight_dmin_o,
  input logic [31:0] result_activation_d_o,
  input logic decode_valid_o,
  input logic [7:0] decode_k_base_o,
  input logic [3:0] decode_k_per_context_o,
  input logic [15:0] decode_stream_valid_o,
  input logic signed [7:0] decode_weight_quant_o [4][8],
  input logic signed [7:0] decode_activation_quant_o [4][8],
  input logic [15:0] group_valid_o,
  input logic [3:0] group_index_o [16],
  input logic signed [31:0] group_dot_o [16],
  input logic signed [15:0] group_aux_o [16],
  input logic signed [7:0] group_scale_o [16],
  input logic [7:0] group_min_o [16],
  input logic [31:0] useful_pairs_o, pair_capacity_o,
  input logic [15:0] dot_active_cycles_o
);
  logic ref_start_ready, ref_busy, ref_done, ref_result_valid;
  logic [3:0] ref_stream;
  logic [2:0] ref_context_base, ref_row_count;
  logic [5:0] ref_row_base;
  logic ref_first;
  logic signed [31:0] ref_dot, ref_aux;
  logic [15:0] ref_weight_d, ref_weight_dmin;
  logic [31:0] ref_activation_d;
  logic ref_decode_valid;
  logic [7:0] ref_k_base;
  logic [3:0] ref_k_per;
  logic [15:0] ref_stream_valid, ref_group_valid;
  logic signed [7:0] ref_weight_quant [4][8], ref_activation_quant [4][8];
  logic [3:0] ref_group_index [16];
  logic signed [31:0] ref_group_dot [16];
  logic signed [15:0] ref_group_aux [16];
  logic signed [7:0] ref_group_scale [16];
  logic [7:0] ref_group_min [16];
  logic [31:0] ref_pairs, ref_capacity;
  logic [15:0] ref_active;
  qbs_profile_engine_int_reference i_reference (
    .start_ready_o(ref_start_ready), .busy_o(ref_busy), .done_o(ref_done),
    .result_valid_o(ref_result_valid), .result_stream_o(ref_stream),
    .result_context_base_o(ref_context_base), .result_row_base_o(ref_row_base),
    .result_row_count_o(ref_row_count), .result_first_block_o(ref_first),
    .result_dot_o(ref_dot), .result_aux_o(ref_aux),
    .result_weight_d_o(ref_weight_d), .result_weight_dmin_o(ref_weight_dmin),
    .result_activation_d_o(ref_activation_d), .decode_valid_o(ref_decode_valid),
    .decode_k_base_o(ref_k_base), .decode_k_per_context_o(ref_k_per),
    .decode_stream_valid_o(ref_stream_valid), .decode_weight_quant_o(ref_weight_quant),
    .decode_activation_quant_o(ref_activation_quant), .group_valid_o(ref_group_valid),
    .group_index_o(ref_group_index), .group_dot_o(ref_group_dot),
    .group_aux_o(ref_group_aux), .group_scale_o(ref_group_scale),
    .group_min_o(ref_group_min), .useful_pairs_o(ref_pairs),
    .pair_capacity_o(ref_capacity), .dot_active_cycles_o(ref_active), .*
  );
  always @(negedge clk_i) if (rst_ni) begin
    assert ({start_ready_o, busy_o, done_o, result_valid_o, decode_valid_o,
        group_valid_o, useful_pairs_o, pair_capacity_o, dot_active_cycles_o} ===
        {ref_start_ready, ref_busy, ref_done, ref_result_valid, ref_decode_valid,
        ref_group_valid, ref_pairs, ref_capacity, ref_active})
      else $fatal(1, "QBS integer control/cycle mismatch");
    if (result_valid_o)
      assert ({result_stream_o, result_context_base_o, result_row_base_o,
          result_row_count_o, result_first_block_o, result_dot_o, result_aux_o,
          result_weight_d_o, result_weight_dmin_o, result_activation_d_o} ===
          {ref_stream, ref_context_base, ref_row_base, ref_row_count, ref_first,
          ref_dot, ref_aux, ref_weight_d, ref_weight_dmin, ref_activation_d})
        else $fatal(1, "QBS integer result mismatch");
    if (decode_valid_o) begin
      assert ({decode_k_base_o, decode_k_per_context_o, decode_stream_valid_o} ===
          {ref_k_base, ref_k_per, ref_stream_valid})
        else $fatal(1, "QBS decode control mismatch");
      assert (decode_weight_quant_o === ref_weight_quant &&
          decode_activation_quant_o === ref_activation_quant)
        else $fatal(1, "QBS decoded operand mismatch");
    end
    for (int stream = 0; stream < 16; stream++) if (group_valid_o[stream])
      assert ({group_index_o[stream], group_dot_o[stream], group_aux_o[stream],
          group_scale_o[stream], group_min_o[stream]} ===
          {ref_group_index[stream], ref_group_dot[stream], ref_group_aux[stream],
          ref_group_scale[stream], ref_group_min[stream]})
        else $fatal(1, "QBS group %0d mismatch", stream);
  end
endmodule

bind qbs_profile_engine_int qbs_int_equivalence i_timing_equivalence (.*);
