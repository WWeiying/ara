// SPDX-License-Identifier: SHL-0.51

// Transport and pair reduction only. Multiplication is performed by the
// existing lane EW8 multiplier, connected through the mul_* interface.
module qbs_lane_mul_borrow (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic lease_i,
  input  logic native_quiescent_i,
  output logic owned_o,
  input  logic valid_i,
  output logic ready_o,
  input  logic [15:0] weight_i,
  input  logic [63:0] activation_i,
  output logic mul_valid_o,
  output logic [63:0] mul_a_o,
  output logic [63:0] mul_b_o,
  input  logic mul_ready_i,
  input  logic mul_valid_i,
  input  logic [127:0] mul_product_i,
  output logic mul_ready_o,
  output logic result_valid_o,
  output logic signed [16:0] result_pair_o [4]
);

  logic owned_q;
  logic input_valid_q, product_valid_q, result_valid_q;
  logic [15:0] weight_q;
  logic [63:0] activation_q;
  logic [127:0] product_q;
  logic pipeline_empty;

  assign pipeline_empty = !(input_valid_q || product_valid_q || result_valid_q);
  assign owned_o = owned_q;
  assign ready_o = rst_ni && owned_q && lease_i;
  assign mul_valid_o = owned_q && input_valid_q;
  assign mul_a_o = {4{weight_q}};
  assign mul_b_o = activation_q;
  assign mul_ready_o = owned_q;
  assign result_valid_o = result_valid_q;

  // The existing EW8 path has zero internal latency. Registered ingress,
  // full products, and pair reduction match the QBS dot array's three stages.
  // Results are consumed unconditionally by the private integer accumulators;
  // upstream issue throttling must occur before accepting an input beat.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      owned_q <= 1'b0;
      input_valid_q <= 1'b0;
      product_valid_q <= 1'b0;
      result_valid_q <= 1'b0;
      weight_q <= '0;
      activation_q <= '0;
      product_q <= '0;
      result_pair_o <= '{default:'0};
    end else begin
      if (!owned_q && lease_i && native_quiescent_i)
        owned_q <= 1'b1;
      else if (owned_q && !lease_i && pipeline_empty)
        owned_q <= 1'b0;

      input_valid_q <= valid_i && ready_o;
      product_valid_q <= owned_q && mul_valid_i;
      result_valid_q <= product_valid_q;
      if (valid_i && ready_o) begin
        weight_q <= weight_i;
        activation_q <= activation_i;
      end
      if (owned_q && mul_valid_i)
        product_q <= mul_product_i;
      if (product_valid_q) begin
        for (int context_index = 0; context_index < 4; context_index++) begin
          result_pair_o[context_index] <=
              $signed({product_q[32*context_index+15],
                       product_q[32*context_index +: 16]}) +
              $signed({product_q[32*context_index+31],
                       product_q[32*context_index+16 +: 16]});
        end
      end
    end
  end

`ifndef SYNTHESIS
  always_ff @(posedge clk_i) if (rst_ni && owned_q) begin
    assert (!input_valid_q || mul_ready_i)
      else $fatal(1, "QBS borrowed multiplier violated its unstalled EW8 contract");
    assert (mul_valid_i === input_valid_q)
      else $fatal(1, "QBS borrowed multiplier lost its zero-latency response");
  end
`endif
endmodule
