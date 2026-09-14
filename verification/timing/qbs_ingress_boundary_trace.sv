// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
// Bounded comparison of command shape, tile ownership and arithmetic inputs.
module qbs_ingress_boundary_trace (
  input logic clk_i, rst_ni, command_fire, compute_start,
  input logic [127:0] descriptor,
  input logic [3:0] m,
  input logic [5:0] n,
  input logic [8:0] kb,
  input logic tile_start, tile_done, bank,
  input logic [7:0] tile_k,
  input logic [5:0] tile_row,
  input logic [2:0] tile_rows,
  input logic int_fire, first_block,
  input logic [6:0] result_index,
  input logic signed [31:0] dot, aux,
  input logic [15:0] wd, wmin,
  input logic [31:0] ad,
  input logic fp_update,
  input logic [6:0] fp_index,
  input logic [31:0] fp_data,
  input logic replay_start, replay_done, replay_valid, replay_ready, activation_needed,
  input logic [7:0] expected_k,
  input logic [10:0] replay_offset
);
  int fd, cycle, command_index;
  initial fd = $fopen("ingress_boundary.trace", "w");
  always @(posedge clk_i) if (rst_ni) begin
    cycle++;
    if (command_fire) command_index++;
    if (command_index <= 8) begin
      if (compute_start)
        $fdisplay(fd, "COMMAND %0d %0d m=%0d n=%0d kb=%0d desc=%032h",
            cycle, command_index, m, n, kb, descriptor);
      if (tile_start || tile_done)
        $fdisplay(fd, "TILE %0d %0d start=%0d done=%0d k=%0d row=%0d rows=%0d bank=%0d",
            cycle, command_index, tile_start, tile_done, tile_k, tile_row, tile_rows, bank);
      if (int_fire)
        $fdisplay(fd, "INT %0d %0d idx=%0d first=%0d dot=%0d aux=%0d wd=%04h min=%04h ad=%08h",
            cycle, command_index, result_index, first_block, dot, aux, wd, wmin, ad);
      if (fp_update)
        $fdisplay(fd, "FP %0d %0d idx=%0d data=%08h",
            cycle, command_index, fp_index, fp_data);
      if (replay_start || replay_done || (replay_valid && replay_ready))
        $fdisplay(fd, "REPLAY %0d %0d start=%0d done=%0d fire=%0d need=%0d k=%0d offset=%0d",
            cycle, command_index, replay_start, replay_done,
            replay_valid && replay_ready, activation_needed, expected_k, replay_offset);
    end
  end
  final $fclose(fd);
endmodule

bind qbs_engine qbs_ingress_boundary_trace i_ingress_boundary_trace (
  .clk_i, .rst_ni, .command_fire,
  .compute_start(compute_command_valid && compute_command_ready),
  .descriptor(descriptor_q), .m(m_q), .n(n_q), .kb(k_blocks_q),
  .tile_start(i_compute_engine.integer_start_fire), .tile_done(i_compute_engine.integer_done),
  .bank(i_compute_engine.active_weight_bank_q), .tile_k(i_compute_engine.k_block_q),
  .tile_row(i_compute_engine.row_base_q), .tile_rows(i_compute_engine.row_count),
  .int_fire(i_compute_engine.integer_result_valid && i_compute_engine.integer_result_ready),
  .first_block(i_compute_engine.integer_result_first_block),
  .result_index(i_compute_engine.fp_request_index),
  .dot(i_compute_engine.integer_result_dot), .aux(i_compute_engine.integer_result_aux),
  .wd(i_compute_engine.integer_result_weight_d), .wmin(i_compute_engine.integer_result_weight_dmin),
  .ad(i_compute_engine.integer_result_activation_d),
  .fp_update(i_compute_engine.fp_update_valid), .fp_index(i_compute_engine.fp_update_index),
  .fp_data(i_compute_engine.fp_update_data),
  .replay_start(context_replay_start_valid && context_replay_start_ready),
  .replay_done(context_replay_done), .replay_valid(context_replay_data_valid),
  .replay_ready(context_replay_data_ready), .activation_needed(compute_activation_needed),
  .expected_k(compute_expected_k), .replay_offset(context_replay_offset)
);
