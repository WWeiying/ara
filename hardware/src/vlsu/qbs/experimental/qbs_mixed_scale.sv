// Optional normal FP16 x normal FP32 scale path; not a general FP32 MUL.
// Non-admitted inputs must retain the existing full-FPU path at the caller.
module qbs_mixed_scale #(
  parameter int unsigned TagWidth = 4
) (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic clear_i,
  input  logic valid_i,
  input  logic [31:0] activation_i,
  input  logic [31:0] weight_i,
  input  logic [TagWidth-1:0] tag_i,
  output logic eligible_o,
  output logic valid_o,
  output logic [31:0] result_o,
  output logic [4:0] fflags_o,
  output logic [TagWidth-1:0] tag_o,
  output logic busy_o
);
  logic [8:0] base_exponent;
  logic product_valid_q, rounded_valid_q;
  logic [34:0] product_q;
  logic [7:0] base_exponent_q, normalized_exponent_q;
  logic product_sign_q, rounded_sign_q, inexact_q;
  logic [TagWidth-1:0] product_tag_q, rounded_tag_q;
  logic [23:0] mantissa;
  logic guard_bit, sticky_bit, round_up;
  logic [24:0] rounded_q;

  // weight_i is the unchanged FP32 expansion of an original normal binary16.
  // This conservative range guarantees normal finite results, including carry
  // from RNE rounding. Other numerical classes are not approximated here.
  assign base_exponent = {1'b0, activation_i[30:23]} +
                         {1'b0, weight_i[30:23]} - 9'd127;
  assign eligible_o = activation_i[30:23] != 8'd0 &&
                      activation_i[30:23] != 8'hff &&
                      weight_i[30:23] >= 8'd113 && weight_i[30:23] <= 8'd142 &&
                      weight_i[12:0] == 13'b0 &&
                      base_exponent >= 9'd1 && base_exponent <= 9'd252;

  assign mantissa = product_q[34] ? product_q[34:11] : product_q[33:10];
  assign guard_bit = product_q[34] ? product_q[10] : product_q[9];
  assign sticky_bit = product_q[34] ? |product_q[9:0] : |product_q[8:0];
  assign round_up = guard_bit && (sticky_bit || mantissa[0]);
  assign busy_o = product_valid_q || rounded_valid_q || valid_o;

  // Three register stages, initiation interval one. Invalid payload registers
  // need no reset; validity and clear own their lifetime.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      product_valid_q <= 1'b0;
      rounded_valid_q <= 1'b0;
      valid_o <= 1'b0;
    end else if (clear_i) begin
      product_valid_q <= 1'b0;
      rounded_valid_q <= 1'b0;
      valid_o <= 1'b0;
    end else begin
      product_valid_q <= valid_i;
      rounded_valid_q <= product_valid_q;
      valid_o <= rounded_valid_q;
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && !clear_i) begin
      if (valid_i) begin
        product_q <= {1'b1, activation_i[22:0]} * {1'b1, weight_i[22:13]};
        base_exponent_q <= base_exponent[7:0];
        product_sign_q <= activation_i[31] ^ weight_i[31];
        product_tag_q <= tag_i;
      end
      if (product_valid_q) begin
        rounded_q <= {1'b0, mantissa} + 25'(round_up);
        normalized_exponent_q <= base_exponent_q + 8'(product_q[34]);
        inexact_q <= guard_bit || sticky_bit;
        rounded_sign_q <= product_sign_q;
        rounded_tag_q <= product_tag_q;
      end
      if (rounded_valid_q) begin
        result_o <= {rounded_sign_q,
                     8'(normalized_exponent_q + 8'(rounded_q[24])),
                     rounded_q[24] ? rounded_q[23:1] : rounded_q[22:0]};
        fflags_o <= {4'b0, inexact_q};
        tag_o <= rounded_tag_q;
      end
    end
  end

  // synthesis translate_off
  initial assert (TagWidth > 0) else $fatal(1, "Mixed scale tag width must be positive");
  always @(posedge clk_i)
    if (rst_ni && !clear_i && valid_i)
      assert (!$isunknown({activation_i,weight_i,tag_i}) && eligible_o)
        else $fatal(1, "Mixed scale non-admitted request a=%h w=%h", activation_i, weight_i);
  // synthesis translate_on
endmodule
