// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps

// The ordered dynamic-write rule from 1b0aec5f is the reference. Compare
// every valid bit, including partially filled blocks and pending drains.
module qbs_valid_equivalence import qbs_pkg::*; #(
  parameter int unsigned ActivationContextBase = 0
) (
  input logic clk_i, rst_ni, clear_weight_i, clear_activation_i,
  input logic [1:0] weight_source_valid, activation_source_valid,
  input logic [31:0] weight_consumed, activation_consumed,
  input logic [1:0] weight_rows [32], activation_contexts [32],
  input logic [7:0] weight_offsets [32],
  input logic [8:0] activation_offsets [32],
  input logic [31:0] weight_mask, activation_mask,
  input logic [31:0] new_weight_mask, new_activation_mask,
  input logic [15:0] weight_duplicate_mask, activation_duplicate_mask,
  input logic weight_byte_valid_q [4][QbsMaxWeightBlockBytes],
  input logic activation_byte_valid_q [4][QbsMaxActivationBlockBytes]
);
  logic ref_weight [4][QbsMaxWeightBlockBytes];
  logic ref_activation [4][QbsMaxActivationBlockBytes];
  longint unsigned checked_cycles = 0;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      foreach (ref_weight[r,b]) ref_weight[r][b] <= 1'b0;
      foreach (ref_activation[r,b]) ref_activation[r][b] <= 1'b0;
    end else begin
      if (clear_weight_i)
        foreach (ref_weight[r,b]) ref_weight[r][b] <= 1'b0;
      if (clear_activation_i)
        foreach (ref_activation[r,b]) ref_activation[r][b] <= 1'b0;
      if (|weight_source_valid)
        for (int b = 0; b < 32; b++)
          if (weight_consumed[b])
            ref_weight[weight_rows[b]][weight_offsets[b]] <= 1'b1;
      if (|activation_source_valid)
        for (int b = 0; b < 32; b++)
          if (activation_consumed[b])
            ref_activation[activation_contexts[b]][activation_offsets[b]] <= 1'b1;
    end
  end

  always @(negedge clk_i) begin
    #1ps;
    if (rst_ni) begin
      for (int b = 0; b < 32; b++) begin
        logic expected_weight, expected_activation;
        expected_weight = 1'b0;
        expected_activation = 1'b0;
        if (weight_mask[b])
          expected_weight = !ref_weight[weight_rows[b]][weight_offsets[b]] &&
              (b < 16 || !weight_duplicate_mask[b%16]);
        if (activation_mask[b])
          expected_activation = !ref_activation[activation_contexts[b]][activation_offsets[b]] &&
              (b < 16 || !activation_duplicate_mask[b%16]);
        assert (new_weight_mask[b] === expected_weight)
          else $fatal(1, "weight lookup mismatch base=%0d byte=%0d cycle=%0d",
                      ActivationContextBase, b, checked_cycles);
        assert (new_activation_mask[b] === expected_activation)
          else $fatal(1, "activation lookup mismatch base=%0d byte=%0d cycle=%0d",
                      ActivationContextBase, b, checked_cycles);
      end
      foreach (ref_weight[r,b])
        assert (weight_byte_valid_q[r][b] === ref_weight[r][b])
          else $fatal(1, "weight valid mismatch base=%0d row=%0d byte=%0d cycle=%0d",
                      ActivationContextBase, r, b, checked_cycles);
      foreach (ref_activation[r,b])
        assert (activation_byte_valid_q[r][b] === ref_activation[r][b])
          else $fatal(1, "activation valid mismatch base=%0d row=%0d byte=%0d cycle=%0d",
                      ActivationContextBase, r, b, checked_cycles);
      checked_cycles++;
    end
  end
  final $display("QBS valid equivalence base=%0d checked_cycles=%0d",
                 ActivationContextBase, checked_cycles);
endmodule

bind qbs_block_adapter qbs_valid_equivalence #(
  .ActivationContextBase(ActivationContextBase)
) i_valid_equivalence (.*);
