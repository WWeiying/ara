// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
// Check the per-beat layout contract against the adapter's actual targets.
module qbs_stream_contract_checker import qbs_pkg::*; #(
  parameter int unsigned ActivationContextBase = 0
) (
  input logic clk_i, rst_ni,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input qbs_activation_layout_e activation_layout_i,
  input logic [1:0] weight_source_valid, activation_source_valid,
  input logic [12:0] weight_source_base [2], activation_source_base [2],
  input logic [31:0] weight_mask, activation_mask,
  input logic [1:0] weight_rows [32], activation_contexts [32],
  input logic [7:0] weight_offsets [32],
  input logic [8:0] activation_offsets [32],
  input qbs_payload_location_t weight_location [32], activation_location [32]
);
  longint unsigned weight_checks = 0, activation_checks = 0;
  int scale, quants, contexts, ctx, off, absolute_byte, phase;

  always @(posedge clk_i) if (rst_ni) begin
    scale = qbs_activation_scale_bytes(activation_profile_i);
    quants = qbs_activation_quant_bytes(activation_profile_i);
    contexts = activation_layout_i == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED ? 8 : 4;
    for (int n = 0; n < 32; n++) begin
      if (weight_source_valid[n / 16] && weight_mask[n]) begin
        absolute_byte = unsigned'(weight_rows[n]) * qbs_weight_block_bytes(weight_profile_i) +
                        unsigned'(weight_offsets[n]);
        assert (absolute_byte == unsigned'(weight_source_base[n / 16]) + n % 16)
          else $fatal(1, "weight stream source/target mismatch byte=%0d", n);
        phase = 0;
        if (weight_location[n].plane == 0) begin
          case (weight_profile_i)
            QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
            QBS_WEIGHT_PROFILE_IQ4_NL: phase = 2;
            QBS_WEIGHT_PROFILE_Q5_0: phase = 6;
            default: ;
          endcase
        end
        assert (4'(weight_location[n].offset + phase) == weight_offsets[n][3:0])
          else $fatal(1, "weight physical/native phase mismatch profile=%0d byte=%0d", weight_profile_i, n);
        weight_checks++;
      end
      if (activation_source_valid[n / 16] && activation_mask[n]) begin
        ctx = unsigned'(activation_contexts[n]) + ActivationContextBase;
        off = unsigned'(activation_offsets[n]);
        if (activation_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR)
          absolute_byte = ctx * qbs_activation_block_bytes(activation_profile_i) + off;
        else if (off < scale) absolute_byte = ctx * scale + off;
        else if (off < scale + quants)
          absolute_byte = contexts * scale + (off - scale) * contexts + ctx;
        else begin
          off -= scale + quants;
          absolute_byte = contexts * (scale + quants) + (off / 2) * contexts * 2 +
                          ctx * 2 + off % 2;
        end
        assert (absolute_byte == unsigned'(activation_source_base[n / 16]) + n % 16)
          else $fatal(1, "activation stream source/target mismatch layout=%0d ctx=%0d byte=%0d",
                      activation_layout_i, ctx, n);
        activation_checks++;
      end
      // One physical destination cannot occur twice inside a single beat.
      for (int j = n + 1; j < (n / 16 + 1) * 16; j++) begin
        if (weight_source_valid[n / 16] && weight_mask[n] && weight_mask[j])
          assert (!(weight_rows[n] == weight_rows[j] && weight_location[n] == weight_location[j]))
            else $fatal(1, "non-injective weight beat");
        if (activation_source_valid[n / 16] && activation_mask[n] && activation_mask[j])
          assert (!(activation_contexts[n] == activation_contexts[j] && activation_location[n] == activation_location[j]))
            else $fatal(1, "non-injective activation beat");
      end
    end
  end
  final $display("QBS stream contract checks base=%0d weight=%0d activation=%0d",
                 ActivationContextBase, weight_checks, activation_checks);
endmodule

bind qbs_block_adapter qbs_stream_contract_checker #(
  .ActivationContextBase(ActivationContextBase)
) i_stream_contract_check (.*);
