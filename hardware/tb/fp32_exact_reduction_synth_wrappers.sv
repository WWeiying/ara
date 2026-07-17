// Copyright 2026
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Synthesis-only wrappers used to compare the lane-local rounded interface
// with the global exact-state export interface.  Keeping unused ports below
// the synthesis top lets constant propagation remove logic that the selected
// architecture does not observe.

module fp32_exact_reduction_local_synth_wrapper (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        start_i,
  input  logic [2:0]  rnd_mode_i,
  input  logic        seed_valid_i,
  input  logic [31:0] seed_i,
  input  logic [63:0] data_i,
  input  logic [1:0]  active_i,
  input  logic        last_i,
  input  logic        in_valid_i,
  output logic        in_ready_o,
  output logic [31:0] result_o,
  output logic [4:0]  status_o,
  output logic        out_valid_o,
  input  logic        out_ready_i,
  output logic        busy_o
);

  fp32_exact_reduction_accum #(
    .AccWidth          (288),
    .ExponentSegmented (1'b1),
    .EmitRoundedResult (1'b1)
  ) i_accumulator (
    .clk_i,
    .rst_ni,
    .start_i,
    .rnd_mode_i,
    .seed_valid_i,
    .seed_i,
    .data_i,
    .active_i,
    .last_i,
    .in_valid_i,
    .in_ready_o,
    .result_o,
    .status_o,
    .out_valid_o,
    .out_ready_i,
    .busy_o,
    .exact_value_o          (),
    .special_o              (),
    .source_seen_o          (),
    .finite_nonzero_seen_o  (),
    .pos_zero_seen_o        (),
    .neg_zero_seen_o        (),
    .seed_valid_o           (),
    .seed_o                 (),
    .rnd_mode_o             ()
  );

endmodule

module fp32_exact_reduction_export_synth_wrapper (
  input  logic         clk_i,
  input  logic         rst_ni,
  input  logic         start_i,
  input  logic [2:0]   rnd_mode_i,
  input  logic         seed_valid_i,
  input  logic [31:0]  seed_i,
  input  logic [63:0]  data_i,
  input  logic [1:0]   active_i,
  input  logic         last_i,
  input  logic         in_valid_i,
  output logic         in_ready_o,
  output logic         out_valid_o,
  input  logic         out_ready_i,
  output logic         busy_o,
  output logic [287:0] exact_value_o,
  output logic [3:0]   special_o,
  output logic         source_seen_o,
  output logic         finite_nonzero_seen_o,
  output logic         pos_zero_seen_o,
  output logic         neg_zero_seen_o,
  output logic         seed_valid_o,
  output logic [31:0]  seed_o,
  output logic [2:0]   rnd_mode_o
);

  fp32_exact_reduction_accum #(
    .AccWidth          (288),
    .ExponentSegmented (1'b1),
    .EmitRoundedResult (1'b0)
  ) i_accumulator (
    .clk_i,
    .rst_ni,
    .start_i,
    .rnd_mode_i,
    .seed_valid_i,
    .seed_i,
    .data_i,
    .active_i,
    .last_i,
    .in_valid_i,
    .in_ready_o,
    .result_o              (),
    .status_o              (),
    .out_valid_o,
    .out_ready_i,
    .busy_o,
    .exact_value_o,
    .special_o,
    .source_seen_o,
    .finite_nonzero_seen_o,
    .pos_zero_seen_o,
    .neg_zero_seen_o,
    .seed_valid_o,
    .seed_o,
    .rnd_mode_o
  );

endmodule
