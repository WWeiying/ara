// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_compute_engine
  import qbs_pkg::*;
  import fpnew_pkg::*;
(
  input  logic                    clk_i,
  input  logic                    rst_ni,

  input  logic                    command_valid_i,
  output logic                    command_ready_o,
  input  qbs_weight_profile_e     command_weight_profile_i,
  input  qbs_activation_profile_e command_activation_profile_i,
  input  qbs_weight_layout_e      command_weight_layout_i,
  input  qbs_activation_layout_e  command_activation_layout_i,
  input  logic [2:0]              command_m_i,
  input  logic [5:0]              command_n_i,
  input  logic [8:0]              command_k_blocks_i,
  input  roundmode_e              command_round_mode_i,

  // A fault stops new work. Work already admitted to the integer/FP pipelines
  // drains into hidden state before the command-local state is discarded.
  input  logic                    fault_i,
  output logic                    fault_done_o,

  input  logic                    weight_write_valid_i,
  output logic                    weight_write_ready_o,
  input  logic                    weight_write_bank_i,
  input  logic [2:0]              weight_write_row_count_i,
  input  logic                    weight_write_group_i,
  input  logic [1:0]              weight_write_row_i,
  input  logic [9:0]              weight_write_offset_i,
  input  logic [127:0]            weight_write_data_i,
  input  logic [15:0]             weight_write_strb_i,
  input  logic                    activation_write_valid_i,
  output logic                    activation_write_ready_o,
  input  logic [1:0]              activation_write_context_i,
  input  logic [10:0]             activation_write_offset_i,
  input  logic [127:0]            activation_write_data_i,
  input  logic [15:0]             activation_write_strb_i,

  // Logical block requested by the fixed K-block-major scheduler. The future
  // read engine uses these indices plus the command descriptor to form ranges.
  output logic [7:0]              expected_k_block_o,
  output logic [5:0]              expected_row_base_o,
  output logic [2:0]              expected_row_count_o,
  output logic                    expected_weight_bank_o,
  output logic                    activation_block_needed_o,
  output logic                    weight_block_needed_o,

  // Results remain hidden until the complete command has drained without a
  // fault. The commit adapter reads them and acknowledges atomic consumption.
  output logic                    result_valid_o,
  input  logic                    result_consumed_i,
  input  logic [6:0]              result_read_index_i,
  output logic                    result_read_valid_o,
  output logic [31:0]             result_read_data_o,
  input  logic [3:0]              result_bank_read_row_i,
  output logic [7:0]              result_bank_read_valid_o,
  output logic [31:0]             result_bank_read_data_o [8],
  output logic [4:0]              result_fflags_o,

  output logic                    busy_o,
  output logic                    phase_activation_load_o,
  output logic                    phase_weight_load_o,
  output logic                    phase_compute_o,
  output logic                    phase_drain_o,
  output logic [31:0]             weight_prefetch_wait_cycles_o,
  output logic [31:0]             tiles_computed_o,
  output logic [31:0]             weight_bytes_o,
  output logic [31:0]             activation_bytes_o,
  output logic [31:0]             useful_pairs_o,
  output logic [31:0]             pair_capacity_o,
  output logic [31:0]             dot_active_cycles_o,
  output logic [31:0]             fp_uop_issue_o,
  output logic [31:0]             fp_table_occupancy_sum_o,
  output logic [4:0]              fp_table_occupancy_max_o,
  output logic [31:0]             fp_table_full_cycles_o,
  output logic [31:0]             accumulator_updates_o
);

  typedef enum logic [3:0] {
    QBS_IDLE,
    QBS_INIT,
    QBS_LOAD_TILE,
    QBS_COMPUTE_TILE,
    QBS_WAIT_WEIGHT,
    QBS_START_WEIGHT,
    QBS_CLEAR_BLOCK,
    QBS_FINAL_DRAIN,
    QBS_RESULT,
    QBS_FAULT_DRAIN,
    QBS_FAULT_CLEAR
  } qbs_compute_state_e;

  qbs_compute_state_e state_q, state_d;
  qbs_weight_profile_e weight_profile_q;
  qbs_activation_profile_e activation_profile_q;
  qbs_weight_layout_e weight_layout_q;
  qbs_activation_layout_e activation_layout_q;
  logic [2:0] m_q;
  logic [5:0] n_q;
  logic [8:0] k_blocks_q;
  roundmode_e round_mode_q;
  logic [7:0] k_block_q;
  logic [5:0] row_base_q;

  logic [1:0] clear_weight;
  logic clear_activation;
  logic clear_accumulator;
  logic [2:0] row_count;
  logic [2:0] load_row_count;
  logic [5:0] load_row_base;
  logic next_row_available;
  logic [2:0] next_row_count;
  logic active_weight_bank_q;
  logic write_weight_bank;
  logic weight_write_fire;
  logic current_weight_complete;
  logic load_weight_complete;
  logic integer_start_fire;
  logic advance_prefetched_tile;

  logic [7:0] weight_block [4][QbsMaxWeightBlockBytes];
  logic [7:0] weight_block_bank0 [4][QbsMaxWeightBlockBytes];
  logic [7:0] weight_block_bank1 [4][QbsMaxWeightBlockBytes];
  logic [7:0] activation_block [4][QbsMaxActivationBlockBytes];
  logic [7:0] unused_activation_block_bank1 [4][QbsMaxActivationBlockBytes];
  logic [3:0] weight_complete [2];
  logic [3:0] activation_complete;
  logic [3:0] unused_activation_complete_bank1;
  logic all_weight_complete [2];
  logic all_activation_complete;
  logic unused_all_activation_complete_bank1;
  logic [31:0] adapter_weight_bytes [2];
  logic [31:0] adapter_activation_bytes;
  logic [31:0] unused_adapter_activation_bytes_bank1;
  logic [2:0] weight_bank_row_count_q [2];
  logic [2:0] bank0_row_count;
  logic [2:0] bank1_row_count;

  logic integer_start_valid;
  logic integer_start_ready;
  logic integer_busy;
  logic integer_done;
  logic integer_result_valid;
  logic integer_result_ready;
  logic [3:0] integer_result_stream;
  logic [5:0] integer_result_row_base;
  logic [2:0] integer_result_row_count;
  logic integer_result_first_block;
  logic signed [31:0] integer_result_dot;
  logic signed [31:0] integer_result_aux;
  logic [15:0] integer_result_weight_d;
  logic [15:0] integer_result_weight_dmin;
  logic [31:0] integer_result_activation_d;
  logic [31:0] tile_useful_pairs;
  logic [31:0] tile_pair_capacity;
  logic [15:0] tile_dot_active_cycles;

  logic fp_request_ready;
  logic [6:0] fp_request_index;
  logic fp_busy;
  logic fp_update_valid;
  logic [6:0] fp_update_index;
  logic [31:0] fp_update_data;

`ifndef SYNTHESIS
  // Observation-only counters. Each blocked counter requires an actual
  // valid/ready failure; occupancy counters are named separately.
  logic [31:0] probe_context_start_blocked_cycles_q;
  logic [31:0] probe_compute_without_dot_issue_cycles_q;
  logic [31:0] probe_profile_result_blocked_cycles_q;
  logic [31:0] probe_fp_slot_blocked_cycles_q;
  logic [31:0] probe_fp_accumulator_blocked_cycles_q;
  logic [31:0] probe_fp_other_blocked_cycles_q;
  logic [31:0] probe_fp_input_blocked_cycles_q;
  logic [31:0] probe_fp_no_schedulable_uop_cycles_q;
  logic [31:0] probe_fp_busy_cycles_q;
  logic [31:0] probe_profile_context_occupancy_sum_q;
  logic [31:0] probe_profile_two_context_cycles_q;
  logic [31:0] probe_profile_drain_only_cycles_q;
  logic [31:0] probe_profile_correction_pending_cycles_q;
  logic [31:0] probe_profile_result_pending_cycles_q;
  logic probe_weight_wait_active;
`endif

  function automatic logic [2:0] rows_from_base(input logic [5:0] base);
    automatic int unsigned remaining_rows;
    remaining_rows = unsigned'(n_q) - unsigned'(base);
    return remaining_rows >= 4 ? 3'd4 : 3'(remaining_rows);
  endfunction

  always_comb begin
    row_count = rows_from_base(row_base_q);
    next_row_available = unsigned'(row_base_q) + unsigned'(row_count) <
                         unsigned'(n_q);
    next_row_count = next_row_available
        ? rows_from_base(row_base_q + row_count) : '0;
    load_row_base = row_base_q;
    if (state_q inside {QBS_COMPUTE_TILE, QBS_WAIT_WEIGHT,
                        QBS_START_WEIGHT} && next_row_available)
      load_row_base = row_base_q + row_count;
    load_row_count = rows_from_base(load_row_base);

    write_weight_bank = active_weight_bank_q;
    if (state_q inside {QBS_COMPUTE_TILE, QBS_WAIT_WEIGHT,
                        QBS_START_WEIGHT})
      write_weight_bank = ~active_weight_bank_q;

    // A response carries its own tile metadata. The live input is selected
    // while a beat is presented so the first beat is mapped correctly; the
    // retained value keeps completion detection stable between beats.
    bank0_row_count = weight_bank_row_count_q[0];
    bank1_row_count = weight_bank_row_count_q[1];
    if (weight_write_valid_i && weight_write_bank_i == 1'b0)
      bank0_row_count = weight_write_row_count_i;
    if (weight_write_valid_i && weight_write_bank_i == 1'b1)
      bank1_row_count = weight_write_row_count_i;
  end

  assign command_ready_o = state_q == QBS_IDLE;
  assign busy_o = state_q != QBS_IDLE;
  assign result_valid_o = state_q == QBS_RESULT;
  assign expected_k_block_o = k_block_q;
  assign expected_row_base_o = load_row_base;
  assign expected_row_count_o = load_row_count;
  assign expected_weight_bank_o = write_weight_bank;
  assign activation_block_needed_o =
      state_q == QBS_LOAD_TILE && !fault_i && !all_activation_complete;
  assign current_weight_complete = all_weight_complete[active_weight_bank_q];
  assign load_weight_complete = all_weight_complete[write_weight_bank];
  assign weight_block_needed_o =
      !fault_i && ((state_q == QBS_LOAD_TILE && !current_weight_complete) ||
      (state_q inside {QBS_COMPUTE_TILE, QBS_WAIT_WEIGHT} &&
       next_row_available && !load_weight_complete));
  assign activation_write_ready_o = activation_block_needed_o;

  always_comb begin
    clear_weight = '0;
    if (state_q inside {QBS_INIT, QBS_CLEAR_BLOCK, QBS_FAULT_CLEAR})
      clear_weight = '1;
    else if (state_q == QBS_START_WEIGHT)
      clear_weight[~active_weight_bank_q] = 1'b1;
  end
  assign clear_activation = state_q inside {QBS_INIT, QBS_CLEAR_BLOCK,
                                            QBS_FAULT_CLEAR};
  assign clear_accumulator = state_q inside {QBS_INIT, QBS_FAULT_CLEAR};

  always_comb begin
    weight_write_ready_o = 1'b0;
    if (!fault_i && weight_write_row_count_i inside {[1:4]} &&
        !clear_weight[weight_write_bank_i]) begin
      unique case (state_q)
        QBS_LOAD_TILE: begin
          if (weight_write_bank_i == active_weight_bank_q)
            weight_write_ready_o =
                !all_weight_complete[weight_write_bank_i];
          else if (next_row_available)
            weight_write_ready_o =
                !all_weight_complete[weight_write_bank_i];
        end
        QBS_COMPUTE_TILE,
        QBS_WAIT_WEIGHT: begin
          if (weight_write_bank_i != active_weight_bank_q)
            weight_write_ready_o =
                !all_weight_complete[weight_write_bank_i];
        end
        default: ;
      endcase
    end
  end
  assign weight_write_fire = weight_write_valid_i && weight_write_ready_o;

  qbs_block_adapter i_block_adapter_bank0 (
    .clk_i,
    .rst_ni,
    .clear_weight_i               (clear_weight[0]),
    .clear_activation_i           (clear_activation),
    .weight_profile_i             (weight_profile_q),
    .activation_profile_i         (activation_profile_q),
    .weight_row_count_i           (bank0_row_count),
    .activation_layout_i          (activation_layout_q),
    .m_i                          (m_q),
    .weight_write_valid_i         (weight_write_fire &&
                                   weight_write_bank_i == 1'b0),
    .weight_write_group_i,
    .weight_write_row_i,
    .weight_write_offset_i,
    .weight_write_data_i,
    .weight_write_strb_i,
    .activation_write_valid_i     (activation_write_valid_i &&
                                   activation_write_ready_o),
    .activation_write_context_i,
    .activation_write_offset_i,
    .activation_write_data_i,
    .activation_write_strb_i,
    .weight_block_o               (weight_block_bank0),
    .activation_block_o           (activation_block),
    .weight_complete_o            (weight_complete[0]),
    .activation_complete_o        (activation_complete),
    .all_weight_complete_o        (all_weight_complete[0]),
    .all_activation_complete_o    (all_activation_complete),
    .accepted_weight_bytes_o      (adapter_weight_bytes[0]),
    .accepted_activation_bytes_o  (adapter_activation_bytes)
  );

  qbs_block_adapter i_block_adapter_bank1 (
    .clk_i,
    .rst_ni,
    .clear_weight_i               (clear_weight[1]),
    .clear_activation_i           (clear_activation),
    .weight_profile_i             (weight_profile_q),
    .activation_profile_i         (activation_profile_q),
    .weight_row_count_i           (bank1_row_count),
    .activation_layout_i          (activation_layout_q),
    .m_i                          (m_q),
    .weight_write_valid_i         (weight_write_fire &&
                                   weight_write_bank_i == 1'b1),
    .weight_write_group_i,
    .weight_write_row_i,
    .weight_write_offset_i,
    .weight_write_data_i,
    .weight_write_strb_i,
    .activation_write_valid_i     (1'b0),
    .activation_write_context_i   ('0),
    .activation_write_offset_i    ('0),
    .activation_write_data_i      ('0),
    .activation_write_strb_i      ('0),
    .weight_block_o               (weight_block_bank1),
    .activation_block_o           (unused_activation_block_bank1),
    .weight_complete_o            (weight_complete[1]),
    .activation_complete_o        (unused_activation_complete_bank1),
    .all_weight_complete_o        (all_weight_complete[1]),
    .all_activation_complete_o    (unused_all_activation_complete_bank1),
    .accepted_weight_bytes_o      (adapter_weight_bytes[1]),
    .accepted_activation_bytes_o  (unused_adapter_activation_bytes_bank1)
  );

  always_comb begin
    for (int row = 0; row < 4; row++)
      for (int byte_index = 0; byte_index < QbsMaxWeightBlockBytes;
           byte_index++)
        weight_block[row][byte_index] = active_weight_bank_q
            ? weight_block_bank1[row][byte_index]
            : weight_block_bank0[row][byte_index];
  end

  assign integer_start_valid =
      state_q inside {QBS_LOAD_TILE, QBS_START_WEIGHT} &&
      !fault_i && current_weight_complete && all_activation_complete;
  assign integer_start_fire = integer_start_valid && integer_start_ready;
  assign advance_prefetched_tile =
      (state_q == QBS_COMPUTE_TILE && integer_done &&
       next_row_available && load_weight_complete && !fault_i) ||
      (state_q == QBS_WAIT_WEIGHT && load_weight_complete && !fault_i);

  assign phase_activation_load_o =
      state_q == QBS_LOAD_TILE && !all_activation_complete;
  assign phase_weight_load_o =
      (state_q == QBS_LOAD_TILE && all_activation_complete &&
       !current_weight_complete) || state_q == QBS_WAIT_WEIGHT;
  assign phase_compute_o = state_q == QBS_COMPUTE_TILE;
  assign phase_drain_o = state_q == QBS_FINAL_DRAIN;

`ifndef SYNTHESIS
  assign probe_weight_wait_active = state_q == QBS_WAIT_WEIGHT;
`endif

  qbs_profile_engine_int i_profile_engine_int (
    .clk_i,
    .rst_ni,
    .weight_block_i                (weight_block),
    .activation_block_i            (activation_block),
    .start_valid_i                 (integer_start_valid),
    .start_ready_o                 (integer_start_ready),
    .start_profile_i               (weight_profile_q),
    .start_activation_profile_i    (activation_profile_q),
    .start_m_i                     (m_q),
    .start_row_count_i             (row_count),
    .start_row_base_i              (row_base_q),
    .start_first_block_i           (k_block_q == 0),
    .busy_o                        (integer_busy),
    .done_o                        (integer_done),
    .result_valid_o                (integer_result_valid),
    .result_ready_i                (integer_result_ready),
    .result_stream_o               (integer_result_stream),
    .result_row_base_o             (integer_result_row_base),
    .result_row_count_o            (integer_result_row_count),
    .result_first_block_o          (integer_result_first_block),
    .result_dot_o                  (integer_result_dot),
    .result_aux_o                  (integer_result_aux),
    .result_weight_d_o             (integer_result_weight_d),
    .result_weight_dmin_o          (integer_result_weight_dmin),
    .result_activation_d_o         (integer_result_activation_d),
    .decode_valid_o                (),
    .decode_k_base_o               (),
    .decode_k_per_context_o        (),
    .decode_stream_valid_o         (),
    .decode_weight_quant_o         (),
    .decode_activation_quant_o     (),
    .group_valid_o                 (),
    .group_index_o                 (),
    .group_dot_o                   (),
    .group_aux_o                   (),
    .group_scale_o                 (),
    .group_min_o                   (),
    .useful_pairs_o                (tile_useful_pairs),
    .pair_capacity_o               (tile_pair_capacity),
    .dot_active_cycles_o           (tile_dot_active_cycles)
  );

  assign fp_request_index =
      {integer_result_stream[1:0], 5'b0} +
      {1'b0, integer_result_row_base} +
      {5'b0, integer_result_stream[3:2]};
  assign integer_result_ready = fp_request_ready;

  qbs_fp_accumulator i_fp_accumulator (
    .clk_i,
    .rst_ni,
    .clear_i                       (clear_accumulator),
    .request_valid_i               (integer_result_valid),
    .request_ready_o               (fp_request_ready),
    .request_slot_i                (integer_result_stream),
    .request_profile_i             (weight_profile_q),
    .request_activation_profile_i  (activation_profile_q),
    .request_accumulator_index_i   (fp_request_index),
    .request_first_block_i         (integer_result_first_block),
    .request_dot_i                 (integer_result_dot),
    .request_aux_i                 (integer_result_aux),
    .request_weight_d_i            (integer_result_weight_d),
    .request_weight_dmin_i         (integer_result_weight_dmin),
    .request_activation_d_i        (integer_result_activation_d),
    .request_round_mode_i          (round_mode_q),
    .read_index_i                  (result_read_index_i),
    .read_valid_o                  (result_read_valid_o),
    .read_data_o                   (result_read_data_o),
    .bank_read_row_i               (result_bank_read_row_i),
    .bank_read_valid_o             (result_bank_read_valid_o),
    .bank_read_data_o              (result_bank_read_data_o),
    .update_valid_o                (fp_update_valid),
    .update_index_o                (fp_update_index),
    .update_data_o                 (fp_update_data),
    .fflags_o                      (result_fflags_o),
    .busy_o                        (fp_busy),
    .fp_uop_issue_o,
    .table_occupancy_sum_o         (fp_table_occupancy_sum_o),
    .table_occupancy_max_o         (fp_table_occupancy_max_o),
    .table_full_cycles_o           (fp_table_full_cycles_o),
    .accumulator_updates_o
  );

  always_comb begin
    state_d = state_q;
    fault_done_o = 1'b0;

    unique case (state_q)
      QBS_IDLE: begin
        if (command_valid_i)
          state_d = QBS_INIT;
      end
      QBS_INIT: state_d = QBS_LOAD_TILE;
      QBS_LOAD_TILE: begin
        if (fault_i)
          state_d = QBS_FAULT_DRAIN;
        else if (integer_start_valid && integer_start_ready)
          state_d = QBS_COMPUTE_TILE;
      end
      QBS_COMPUTE_TILE: begin
        if (fault_i)
          state_d = QBS_FAULT_DRAIN;
        else if (integer_done) begin
          if (next_row_available) begin
            if (load_weight_complete)
              state_d = QBS_START_WEIGHT;
            else
              state_d = QBS_WAIT_WEIGHT;
          end
          else if (unsigned'(k_block_q) + 1 < unsigned'(k_blocks_q))
            state_d = QBS_CLEAR_BLOCK;
          else
            state_d = QBS_FINAL_DRAIN;
        end
      end
      QBS_WAIT_WEIGHT: begin
        if (fault_i)
          state_d = QBS_FAULT_DRAIN;
        else if (load_weight_complete)
          state_d = QBS_START_WEIGHT;
      end
      QBS_START_WEIGHT: begin
        if (fault_i)
          state_d = QBS_FAULT_DRAIN;
        else if (integer_start_fire)
          state_d = QBS_COMPUTE_TILE;
      end
      QBS_CLEAR_BLOCK: state_d = QBS_LOAD_TILE;
      QBS_FINAL_DRAIN: begin
        if (fault_i)
          state_d = QBS_FAULT_DRAIN;
        else if (!integer_busy && !fp_busy)
          state_d = QBS_RESULT;
      end
      QBS_RESULT: begin
        if (result_consumed_i)
          state_d = QBS_IDLE;
      end
      QBS_FAULT_DRAIN: begin
        if (!integer_busy && !fp_busy)
          state_d = QBS_FAULT_CLEAR;
      end
      QBS_FAULT_CLEAR: begin
        fault_done_o = 1'b1;
        state_d = QBS_IDLE;
      end
      default: state_d = QBS_IDLE;
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= QBS_IDLE;
      weight_profile_q <= QBS_WEIGHT_PROFILE_INVALID;
      activation_profile_q <= QBS_ACTIVATION_PROFILE_INVALID;
      weight_layout_q <= QBS_WEIGHT_LAYOUT_INVALID;
      activation_layout_q <= QBS_ACTIVATION_LAYOUT_INVALID;
      m_q <= '0;
      n_q <= '0;
      k_blocks_q <= '0;
      round_mode_q <= RNE;
      k_block_q <= '0;
      row_base_q <= '0;
      active_weight_bank_q <= 1'b0;
      weight_bank_row_count_q[0] <= '0;
      weight_bank_row_count_q[1] <= '0;
      weight_prefetch_wait_cycles_o <= '0;
      tiles_computed_o <= '0;
      weight_bytes_o <= '0;
      activation_bytes_o <= '0;
      useful_pairs_o <= '0;
      pair_capacity_o <= '0;
      dot_active_cycles_o <= '0;
    end else begin
      state_q <= state_d;

      if (state_q == QBS_IDLE && command_valid_i) begin
        weight_profile_q <= command_weight_profile_i;
        activation_profile_q <= command_activation_profile_i;
        weight_layout_q <= command_weight_layout_i;
        activation_layout_q <= command_activation_layout_i;
        m_q <= command_m_i;
        n_q <= command_n_i;
        k_blocks_q <= command_k_blocks_i;
        round_mode_q <= command_round_mode_i;
        k_block_q <= '0;
        row_base_q <= '0;
        active_weight_bank_q <= 1'b0;
        weight_bank_row_count_q[0] <= '0;
        weight_bank_row_count_q[1] <= '0;
        weight_prefetch_wait_cycles_o <= '0;
        tiles_computed_o <= '0;
        weight_bytes_o <= '0;
        activation_bytes_o <= '0;
        useful_pairs_o <= '0;
        pair_capacity_o <= '0;
        dot_active_cycles_o <= '0;
      end

      for (int bank = 0; bank < 2; bank++) begin
        if (clear_weight[bank])
          weight_bank_row_count_q[bank] <= '0;
      end
      if (weight_write_fire)
        weight_bank_row_count_q[weight_write_bank_i] <=
            weight_write_row_count_i;

      if (integer_start_fire) begin
        weight_bytes_o <=
            weight_bytes_o + adapter_weight_bytes[active_weight_bank_q];
        if (row_base_q == 0)
          activation_bytes_o <=
              activation_bytes_o + adapter_activation_bytes;
      end

      if (state_q == QBS_COMPUTE_TILE && integer_done) begin
        tiles_computed_o <= tiles_computed_o + 1'b1;
        useful_pairs_o <= useful_pairs_o + tile_useful_pairs;
        pair_capacity_o <= pair_capacity_o + tile_pair_capacity;
        dot_active_cycles_o <=
            dot_active_cycles_o + tile_dot_active_cycles;

        if (!next_row_available &&
            unsigned'(k_block_q) + 1 < unsigned'(k_blocks_q)) begin
          row_base_q <= '0;
          k_block_q <= k_block_q + 1'b1;
          active_weight_bank_q <= 1'b0;
        end
      end

      if (advance_prefetched_tile) begin
        row_base_q <= row_base_q + row_count;
        active_weight_bank_q <= ~active_weight_bank_q;
      end

      if (state_q == QBS_WAIT_WEIGHT)
        weight_prefetch_wait_cycles_o <=
            weight_prefetch_wait_cycles_o + 1'b1;

`ifndef SYNTHESIS
      if (state_q == QBS_IDLE && command_valid_i) begin
        assert (qbs_weight_block_bytes(command_weight_profile_i) != 0);
        assert (qbs_profiles_compatible(command_weight_profile_i,
                                        command_activation_profile_i));
        assert (command_weight_layout_i inside {
            QBS_WEIGHT_LAYOUT_ROW_MAJOR,
            QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR});
        assert (command_activation_layout_i inside {
            QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED});
        assert (command_m_i inside {[1:4]});
        assert (command_n_i inside {[1:QbsMaxN]});
        assert (command_k_blocks_i inside {[1:QbsMaxKBlocks]});
        if (command_activation_layout_i ==
            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED)
          assert (command_m_i == 4);
      end
      if (integer_result_valid && fp_request_ready) begin
        assert (unsigned'(fp_request_index) < QbsMaxM * QbsMaxN);
        assert (unsigned'(integer_result_stream[3:2]) <
                unsigned'(integer_result_row_count));
        assert (unsigned'(integer_result_stream[1:0]) < unsigned'(m_q));
      end
      if (weight_write_fire) begin
        assert (weight_write_row_count_i inside {[1:4]})
          else $fatal(1, "QBS weight response has an invalid row count");
        if (weight_write_bank_i == active_weight_bank_q) begin
          assert (state_q == QBS_LOAD_TILE &&
                  weight_write_row_count_i == row_count)
            else $fatal(1, "QBS overwrote or mislabeled the active weight bank");
        end else begin
          assert (next_row_available &&
                  weight_write_row_count_i == next_row_count)
            else $fatal(1, "QBS prefetched weight response has the wrong tile shape");
        end
      end
      if (state_q == QBS_START_WEIGHT) begin
        assert (current_weight_complete && !clear_weight[active_weight_bank_q])
          else $fatal(1, "QBS started an incomplete or clearing weight bank");
      end
      if (state_q == QBS_RESULT) begin
        assert (!integer_busy && !fp_busy)
          else $fatal(1, "QBS result exposed before compute drain");
      end
      if (fault_done_o)
        assert (!result_valid_o)
          else $fatal(1, "QBS fault exposed architectural results");
`endif
    end
  end

`ifndef SYNTHESIS
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      probe_context_start_blocked_cycles_q <= '0;
      probe_compute_without_dot_issue_cycles_q <= '0;
      probe_profile_result_blocked_cycles_q <= '0;
      probe_fp_slot_blocked_cycles_q <= '0;
      probe_fp_accumulator_blocked_cycles_q <= '0;
      probe_fp_other_blocked_cycles_q <= '0;
      probe_fp_input_blocked_cycles_q <= '0;
      probe_fp_no_schedulable_uop_cycles_q <= '0;
      probe_fp_busy_cycles_q <= '0;
      probe_profile_context_occupancy_sum_q <= '0;
      probe_profile_two_context_cycles_q <= '0;
      probe_profile_drain_only_cycles_q <= '0;
      probe_profile_correction_pending_cycles_q <= '0;
      probe_profile_result_pending_cycles_q <= '0;
    end else if (state_q == QBS_IDLE && command_valid_i) begin
      probe_context_start_blocked_cycles_q <= '0;
      probe_compute_without_dot_issue_cycles_q <= '0;
      probe_profile_result_blocked_cycles_q <= '0;
      probe_fp_slot_blocked_cycles_q <= '0;
      probe_fp_accumulator_blocked_cycles_q <= '0;
      probe_fp_other_blocked_cycles_q <= '0;
      probe_fp_input_blocked_cycles_q <= '0;
      probe_fp_no_schedulable_uop_cycles_q <= '0;
      probe_fp_busy_cycles_q <= '0;
      probe_profile_context_occupancy_sum_q <= '0;
      probe_profile_two_context_cycles_q <= '0;
      probe_profile_drain_only_cycles_q <= '0;
      probe_profile_correction_pending_cycles_q <= '0;
      probe_profile_result_pending_cycles_q <= '0;
    end else begin
      if (integer_start_valid && !integer_start_ready)
        probe_context_start_blocked_cycles_q <=
            probe_context_start_blocked_cycles_q + 1'b1;
      if (state_q == QBS_COMPUTE_TILE &&
          !i_profile_engine_int.issue_active_q)
        probe_compute_without_dot_issue_cycles_q <=
            probe_compute_without_dot_issue_cycles_q + 1'b1;

      if (integer_result_valid && !fp_request_ready) begin
        probe_profile_result_blocked_cycles_q <=
            probe_profile_result_blocked_cycles_q + 1'b1;
        if (i_fp_accumulator.entry_valid_q[integer_result_stream]) begin
          probe_fp_slot_blocked_cycles_q <=
              probe_fp_slot_blocked_cycles_q + 1'b1;
        end else if (i_fp_accumulator.request_accumulator_conflict) begin
          probe_fp_accumulator_blocked_cycles_q <=
              probe_fp_accumulator_blocked_cycles_q + 1'b1;
        end else begin
          probe_fp_other_blocked_cycles_q <=
              probe_fp_other_blocked_cycles_q + 1'b1;
        end
      end

      if (i_fp_accumulator.fp_in_valid && !i_fp_accumulator.fp_in_ready)
        probe_fp_input_blocked_cycles_q <=
            probe_fp_input_blocked_cycles_q + 1'b1;
      if (i_fp_accumulator.entry_occupancy != 0 &&
          !i_fp_accumulator.fp_in_valid)
        probe_fp_no_schedulable_uop_cycles_q <=
            probe_fp_no_schedulable_uop_cycles_q + 1'b1;
      if (fp_busy)
        probe_fp_busy_cycles_q <= probe_fp_busy_cycles_q + 1'b1;

      probe_profile_context_occupancy_sum_q <=
          probe_profile_context_occupancy_sum_q +
          {31'b0, i_profile_engine_int.context_valid_q[0]} +
          {31'b0, i_profile_engine_int.context_valid_q[1]};
      if (&i_profile_engine_int.context_valid_q)
        probe_profile_two_context_cycles_q <=
            probe_profile_two_context_cycles_q + 1'b1;
      if (!i_profile_engine_int.compute_active_q &&
          |i_profile_engine_int.context_valid_q)
        probe_profile_drain_only_cycles_q <=
            probe_profile_drain_only_cycles_q + 1'b1;
      if (|i_profile_engine_int.slot_valid_q[0] ||
          |i_profile_engine_int.slot_valid_q[1])
        probe_profile_correction_pending_cycles_q <=
            probe_profile_correction_pending_cycles_q + 1'b1;
      if (|i_profile_engine_int.result_pending_q[0] ||
          |i_profile_engine_int.result_pending_q[1])
        probe_profile_result_pending_cycles_q <=
            probe_profile_result_pending_cycles_q + 1'b1;
    end
  end
`endif

  logic unused;
  assign unused = ^{weight_layout_q, weight_complete[0], weight_complete[1],
                    activation_complete, fp_update_valid, fp_update_index,
                    fp_update_data, unused_activation_complete_bank1,
                    unused_all_activation_complete_bank1,
                    unused_adapter_activation_bytes_bank1};

endmodule : qbs_compute_engine
