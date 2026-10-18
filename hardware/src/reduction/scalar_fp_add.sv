// SPDX-License-Identifier: SHL-0.51
// Experimental scalar ADD datapath. No pipeline or architectural ownership.
// Keep this isolated until differential arithmetic and PPA checks complete.
module scalar_fp_add import fpnew_pkg::*; #(
  parameter fp_format_e FpFormat = FP64,
  localparam int W = fp_width(FpFormat),
  localparam int E = exp_bits(FpFormat),
  localparam int M = man_bits(FpFormat),
  localparam int P = M + 1,
  localparam int X = P + 4
) (
  input logic clk_i, rst_ni,
  input logic [W-1:0] a_i, b_i,
  input roundmode_e rnd_mode_i,
  output logic [W-1:0] result_o,
  output status_t status_o
);
  logic [W-1:0] larger_operand, smaller_operand;
  logic [E:0] large_exp, small_exp, norm_exp;
  logic [P-1:0] large_sig, small_sig;
  logic [X-1:0] large_ext, small_ext, aligned, sum, normalized;
  logic sign, subtraction, a_nan, b_nan, a_inf, b_inf;
  logic overflow_before, overflow_after, exact_zero, rounded_sign;
  logic [E+M-1:0] pre_round, rounded;
  logic [1:0] round_sticky;
  logic [E:0] distance;
  logic lost;
  integer leading, left_shift;

  // Magnitude ordering makes the subtraction unsigned and fixes the result
  // sign before normalization. Subnormal exponents use the minimum normal
  // exponent, but retain a zero hidden significand bit.
  always_comb begin
    larger_operand = a_i;
    smaller_operand = b_i;
    if (a_i[W-2:0] < b_i[W-2:0]) begin
      larger_operand = b_i;
      smaller_operand = a_i;
    end
    sign = larger_operand[W-1];
    subtraction = a_i[W-1] ^ b_i[W-1];
    large_exp = {1'b0, larger_operand[M+:E]};
    small_exp = {1'b0, smaller_operand[M+:E]};
    if (large_exp == 0) large_exp = 1;
    if (small_exp == 0) small_exp = 1;
    large_sig = {|larger_operand[M+:E], larger_operand[M-1:0]};
    small_sig = {|smaller_operand[M+:E], smaller_operand[M-1:0]};
    large_ext = {1'b0, large_sig, 3'b000};
    small_ext = {1'b0, small_sig, 3'b000};
    distance = large_exp - small_exp;
    // Right shift with jamming. Three trailing bits preserve guard, round
    // and sticky through the one-bit normalization of a far subtraction.
    aligned = small_ext >> distance;
    lost = 1'b0;
    for (int bit_idx = 0; bit_idx < X; bit_idx++)
      if (distance > bit_idx) lost |= small_ext[bit_idx];
    aligned[0] |= lost;
    sum = subtraction ? large_ext - aligned : large_ext + aligned;
    normalized = sum;
    norm_exp = large_exp;
    leading = 0;
    left_shift = 0;
    if (sum[X-1]) begin
      normalized = sum >> 1;
      normalized[0] |= sum[0];
      norm_exp = large_exp + 1'b1;
    end else begin
      // Priority leading-zero count; cap normalization at exponent one so
      // gradual underflow remains represented in the minimum quantum.
      leading = X-1;
      for (int bit_idx = 0; bit_idx < X-1; bit_idx++)
        if (sum[bit_idx]) leading = X-2-bit_idx;
      left_shift = leading;
      if (left_shift > int'(large_exp)-1) left_shift = int'(large_exp)-1;
      normalized = sum << left_shift;
      norm_exp = large_exp - (E+1)'(left_shift);
    end
    if (!normalized[X-2]) norm_exp = '0;
    overflow_before = norm_exp >= ((1 << E)-1);
    pre_round = {norm_exp[E-1:0], normalized[M+2:3]};
    round_sticky = {normalized[2], |normalized[1:0]};
    if (overflow_before) begin
      pre_round = {E'((1 << E)-2), {M{1'b1}}};
      round_sticky = 2'b11;
    end
  end

  fpnew_rounding #(.AbsWidth(E+M), .EnableRSR(0)) i_round (
    .clk_i, .rst_ni, .id_i('0), .en_rsr_i(1'b0),
    .abs_value_i(pre_round), .sign_i(sign), .round_sticky_bits_i(round_sticky),
    .stochastic_rounding_bits_i('0), .rnd_mode_i,
    .effective_subtraction_i(subtraction), .abs_rounded_o(rounded),
    .sign_o(rounded_sign), .exact_zero_o(exact_zero)
  );
  assign overflow_after = &rounded[M+:E];
  assign a_nan = (&a_i[M+:E]) && (|a_i[M-1:0]);
  assign b_nan = (&b_i[M+:E]) && (|b_i[M-1:0]);
  assign a_inf = (&a_i[M+:E]) && !(|a_i[M-1:0]);
  assign b_inf = (&b_i[M+:E]) && !(|b_i[M-1:0]);
  always_comb begin
    result_o = {rounded_sign, rounded};
    status_o = '0;
    status_o.OF = overflow_before || overflow_after;
    status_o.NX = (|round_sticky) || status_o.OF;
    status_o.UF = !(|rounded[M+:E]) && status_o.NX;
    if (a_nan || b_nan || (a_inf && b_inf && subtraction)) begin
      result_o = {1'b0, {E{1'b1}}, 1'b1, {(M-1){1'b0}}};
      status_o = '0;
      status_o.NV = (a_nan && !a_i[M-1]) || (b_nan && !b_i[M-1]) ||
                    (a_inf && b_inf && subtraction);
    end else if (a_inf || b_inf) begin
      result_o = a_inf ? a_i : b_i;
      status_o = '0;
    end
  end
endmodule
