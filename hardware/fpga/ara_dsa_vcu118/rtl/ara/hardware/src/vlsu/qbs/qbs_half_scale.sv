// Exact finite binary16 multiplication into binary32. No rounding or flags.
// An input sampled at edge N appears after edge N+1 (two register stages).
// There is no backpressure; busy_o includes both registered valid stages.
module qbs_half_scale #(
  parameter int TagWidth = 4
) (
  input  logic                clk_i,
  input  logic                rst_ni,
  input  logic                valid_i,
  input  logic [15:0]         a_i,
  input  logic [15:0]         b_i,
  input  logic [TagWidth-1:0] tag_i,
  output logic                valid_o,
  output logic [31:0]         result_o,
  output logic [TagWidth-1:0] tag_o,
  output logic                busy_o
);
  logic [10:0] mantissa_a, mantissa_b;
  logic [4:0] exponent_a, exponent_b;
  logic [21:0] product_q;
  logic [5:0] exponent_sum_q;
  logic sign_q, product_valid_q;
  logic [TagWidth-1:0] tag_q;
  logic [4:0] leading_zeroes, leading_bit;
  logic product_zero;
  logic [23:0] normalized_product;
  logic [7:0] result_exponent;
  logic [31:0] result_d;

  assign mantissa_a = {(|a_i[14:10]), a_i[9:0]};
  assign mantissa_b = {(|b_i[14:10]), b_i[9:0]};
  assign exponent_a = (a_i[14:10] == '0) ? 5'd1 : a_i[14:10];
  assign exponent_b = (b_i[14:10] == '0) ? 5'd1 : b_i[14:10];

  lzc #(.WIDTH(22), .MODE(1'b1)) i_product_lzc (
    .in_i(product_q), .cnt_o(leading_zeroes), .empty_o(product_zero)
  );

  // half = (-1)^sign * mantissa * 2^(effective_exponent - 25).
  // For leading bit p, the binary32 exponent is p + ea + eb + 77.
  // All nonzero results are normal binary32, with at most 22 significant bits.
  assign leading_bit = 5'd21 - leading_zeroes;
  assign result_exponent = 8'd77 + {3'b0, leading_bit} + {2'b0, exponent_sum_q};
  assign normalized_product = {product_q, 2'b00} << leading_zeroes;
  assign result_d = product_zero ? {sign_q, 31'b0}
                                : {sign_q, result_exponent, normalized_product[22:0]};
  assign busy_o = product_valid_q | valid_o;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      product_valid_q <= 1'b0;
      valid_o <= 1'b0;
    end else begin
      product_valid_q <= valid_i;
      valid_o <= product_valid_q;
    end
  end

  // Data registers deliberately have no reset; validity owns their lifetime.
  always_ff @(posedge clk_i) begin
    if (rst_ni && valid_i) begin
      product_q <= mantissa_a * mantissa_b;
      exponent_sum_q <= {1'b0, exponent_a} + {1'b0, exponent_b};
      sign_q <= a_i[15] ^ b_i[15];
      tag_q <= tag_i;
    end
    if (rst_ni && product_valid_q) begin
      result_o <= result_d;
      tag_o <= tag_q;
    end
  end

  // synthesis translate_off
  initial begin
    assert (TagWidth > 0) else $fatal(1, "qbs_half_scale requires TagWidth > 0");
  end
  always @(posedge clk_i) begin
    if (rst_ni && valid_i) begin
      assert (!$isunknown({a_i, b_i}) && a_i[14:10] != 5'h1f && b_i[14:10] != 5'h1f)
        else $fatal(1, "qbs_half_scale requires finite operands: a=%h b=%h", a_i, b_i);
    end
  end
  // synthesis translate_on
endmodule
