// SPDX-License-Identifier: SHL-0.51
// The production reader/replay path delivers each block byte exactly once.
// Observe physical commits, not ingress acceptance: pending bytes may drain
// later and in a different order from the incoming AXI beat.
module qbs_unique_commit_checker import qbs_pkg::*; (
  input logic clk_i, rst_ni, clear_weight_i, clear_activation_i,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input logic [31:0] weight_consumed, activation_consumed,
  input logic [31:0] weight_mask, activation_mask,
  input logic [1:0] weight_rows [32], activation_contexts [32],
  input logic [7:0] weight_offsets [32],
  input logic [8:0] activation_offsets [32]
);
  bit weight_seen [4][QbsMaxWeightBlockBytes];
  bit activation_seen [4][QbsMaxActivationBlockBytes];
  longint unsigned weight_checks = 0, activation_checks = 0;

  always @(posedge clk_i) begin
    if (!rst_ni || clear_weight_i)
      foreach (weight_seen[row, b]) weight_seen[row][b] = 0;
    if (!rst_ni || clear_activation_i)
      foreach (activation_seen[ctx, b]) activation_seen[ctx][b] = 0;
    if (rst_ni) begin
      for (int b = 0; b < 32; b++) begin
        if (weight_consumed[b]) begin
          assert (!clear_weight_i && weight_mask[b] &&
                  unsigned'(weight_offsets[b]) < qbs_weight_block_bytes(weight_profile_i))
            else $fatal(1, "QBS invalid weight commit");
          assert (!weight_seen[weight_rows[b]][weight_offsets[b]])
            else $fatal(1, "QBS duplicate weight commit row=%0d byte=%0d",
                        weight_rows[b], weight_offsets[b]);
          weight_seen[weight_rows[b]][weight_offsets[b]] = 1;
          weight_checks++;
        end
        if (activation_consumed[b]) begin
          assert (!clear_activation_i && activation_mask[b] &&
                  unsigned'(activation_offsets[b]) < qbs_activation_block_bytes(activation_profile_i))
            else $fatal(1, "QBS invalid activation commit");
          assert (!activation_seen[activation_contexts[b]][activation_offsets[b]])
            else $fatal(1, "QBS duplicate activation commit ctx=%0d byte=%0d",
                        activation_contexts[b], activation_offsets[b]);
          activation_seen[activation_contexts[b]][activation_offsets[b]] = 1;
          activation_checks++;
        end
      end
    end
  end

  final $display("QBS unique commit checks weight=%0d activation=%0d",
                 weight_checks, activation_checks);
endmodule

bind qbs_block_adapter qbs_unique_commit_checker i_unique_commit_check (.*);
