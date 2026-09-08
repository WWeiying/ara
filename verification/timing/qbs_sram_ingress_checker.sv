// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Observe valid before compute-engine fire gating. Adapter input valid is
// already qualified by ready and cannot measure upstream backpressure.
module qbs_sram_ingress_checker (
  input logic clk_i, rst_ni,
  input logic weight_write_valid_i, weight_write_ready_o, weight_write_bank_i,
  input logic activation_write_valid_i, activation_write_ready_o,
  input logic [1:0] adapter_weight_ready, adapter_activation_ready
);
  int wfire, afire, wblocked, ablocked, wbuffer_blocked, abuffer_blocked;
  always @(posedge clk_i) if (rst_ni) begin
    if (weight_write_valid_i) begin
      if (weight_write_ready_o) wfire++;
      else begin
        wblocked++;
        if (!adapter_weight_ready[weight_write_bank_i]) wbuffer_blocked++;
      end
    end
    if (activation_write_valid_i) begin
      if (activation_write_ready_o) afire++;
      else begin
        ablocked++;
        if (!(&adapter_activation_ready)) abuffer_blocked++;
      end
    end
  end
  final $display("QBS SRAM ingress wfire=%0d afire=%0d wblocked=%0d ablocked=%0d wbuffer_blocked=%0d abuffer_blocked=%0d",
      wfire, afire, wblocked, ablocked, wbuffer_blocked, abuffer_blocked);
endmodule

bind qbs_compute_engine qbs_sram_ingress_checker i_sram_ingress_checker (.*);
