// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_adapter_equivalence import qbs_pkg::*; #(
  parameter int unsigned ActivationContextBase = 0
) (
  input logic clk_i, rst_ni, clear_weight_i, clear_activation_i,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input logic [2:0] weight_row_count_i,
  input qbs_activation_layout_e activation_layout_i,
  input logic [3:0] m_i,
  input logic weight_write_valid_i, weight_write_group_i,
  input logic [1:0] weight_write_row_i,
  input logic [9:0] weight_write_offset_i,
  input logic [127:0] weight_write_data_i,
  input logic [15:0] weight_write_strb_i,
  input logic activation_write_valid_i,
  input logic [1:0] activation_write_context_i,
  input logic [11:0] activation_write_offset_i,
  input logic [127:0] activation_write_data_i,
  input logic [15:0] activation_write_strb_i,
  input logic [7:0] weight_block_o [4][QbsMaxWeightBlockBytes],
  input logic [7:0] activation_block_o [4][QbsMaxActivationBlockBytes],
  input logic weight_byte_valid_q [4][QbsMaxWeightBlockBytes],
  input logic activation_byte_valid_q [4][QbsMaxActivationBlockBytes],
  input logic [3:0] weight_complete_o, activation_complete_o,
  input logic all_weight_complete_o, all_activation_complete_o,
  input logic [31:0] accepted_weight_bytes_o, accepted_activation_bytes_o
);
  logic [7:0] ref_weight [4][QbsMaxWeightBlockBytes];
  logic [7:0] ref_activation [4][QbsMaxActivationBlockBytes];
  logic [3:0] ref_weight_complete, ref_activation_complete;
  logic ref_all_weight, ref_all_activation;
  logic [31:0] ref_weight_bytes, ref_activation_bytes;

  qbs_block_adapter_reference #(.ActivationContextBase(ActivationContextBase))
      i_reference (
    .weight_block_o(ref_weight), .activation_block_o(ref_activation),
    .weight_complete_o(ref_weight_complete),
    .activation_complete_o(ref_activation_complete),
    .all_weight_complete_o(ref_all_weight),
    .all_activation_complete_o(ref_all_activation),
    .accepted_weight_bytes_o(ref_weight_bytes),
    .accepted_activation_bytes_o(ref_activation_bytes), .*
  );

  always @(negedge clk_i) begin
    #1ps;
    if (rst_ni) begin
      assert ({weight_complete_o, activation_complete_o, all_weight_complete_o,
          all_activation_complete_o, accepted_weight_bytes_o,
          accepted_activation_bytes_o} ===
          {ref_weight_complete, ref_activation_complete, ref_all_weight,
          ref_all_activation, ref_weight_bytes, ref_activation_bytes})
        else $fatal(1, "QBS adapter control/counter mismatch: base=%0d t=%0t",
                    ActivationContextBase, $time);
      assert (weight_block_o === ref_weight && activation_block_o === ref_activation)
        else $fatal(1, "QBS adapter payload mismatch: base=%0d t=%0t",
                    ActivationContextBase, $time);
      assert (weight_byte_valid_q === i_reference.weight_byte_valid_q &&
          activation_byte_valid_q === i_reference.activation_byte_valid_q)
        else $fatal(1, "QBS adapter byte-valid mismatch: base=%0d t=%0t",
                    ActivationContextBase, $time);
    end
  end
endmodule

bind qbs_block_adapter qbs_adapter_equivalence #(
    .ActivationContextBase(ActivationContextBase)) i_adapter_equivalence (.*);
