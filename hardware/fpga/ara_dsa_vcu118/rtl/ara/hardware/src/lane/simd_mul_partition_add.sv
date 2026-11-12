// SPDX-License-Identifier: SHL-0.51
// One byte-sliced adder. Carry crosses bytes, never SIMD element boundaries.
module simd_mul_partition_add (
  input logic [63:0] a_i, b_i,
  input logic [1:0] sew_i,
  input logic [7:0] carry_i,
  output logic [63:0] sum_o
);
  wire [7:0] boundary;
  wire [7:0] p [4], g [4];
  for (genvar k = 0; k < 8; k++) begin : gen_byte
    wire [8:0] base_sum = {1'b0, a_i[k*8+:8]} + {1'b0, b_i[k*8+:8]};
    assign boundary[k] = (k == 0) || ((k & ((1 << sew_i)-1)) == 0);
    assign p[0][k] = (&base_sum[7:0]) && !boundary[k];
    assign g[0][k] = base_sum[8] || ((&base_sum[7:0]) && boundary[k] && carry_i[k]);
    wire cin;
    if (k == 0) assign cin = carry_i[k];
    else assign cin = boundary[k] ? carry_i[k] : g[3][k-1];
    assign sum_o[k*8+:8] = base_sum[7:0] + cin;
  end
  for (genvar l = 0; l < 3; l++) begin : gen_level
    for (genvar k = 0; k < 8; k++) begin : gen_prefix
      if (k >= (1 << l)) begin
        assign p[l+1][k] = p[l][k] & p[l][k-(1 << l)];
        assign g[l+1][k] = g[l][k] | (p[l][k] & g[l][k-(1 << l)]);
      end else begin
        assign p[l+1][k] = p[l][k];
        assign g[l+1][k] = g[l][k];
      end
    end
  end
endmodule
