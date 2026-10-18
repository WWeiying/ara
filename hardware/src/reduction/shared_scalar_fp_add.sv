// SPDX-License-Identifier: SHL-0.51
// Experimental multi-format ADD. Shared alignment/add/normalization, with
// format-specific rounding. No pipeline, arbitration, or instruction state.
module shared_scalar_fp_add import fpnew_pkg::*; (
  input logic clk_i, rst_ni,
  input logic [63:0] a_i, b_i,
  input fp_format_e format_i,
  input roundmode_e rnd_mode_i,
  output logic [63:0] result_o,
  output status_t status_o
);
  logic [1:0] operand_sign, is_nan, is_snan, is_inf;
  logic [1:0][10:0] exponent;
  logic [1:0][52:0] significand;
  logic [1:0][63:0] operand;
  logic [52:0] larger_sig, smaller_sig;
  logic [11:0] larger_exp, smaller_exp, norm_exp, max_exp, distance;
  logic [56:0] larger_ext, smaller_ext, aligned, sum, normalized;
  logic sign, subtraction, lost, overflow_before;
  integer leading, left_shift;
  logic [2:0][63:0] rounded_result;
  status_t [2:0] rounded_status;
  logic [1:0] selected_format;
  logic [63:0] canonical_nan, infinity;

  assign operand = {b_i, a_i};
  always_comb begin
    exponent = '0;
    significand = '0;
    operand_sign = '0;
    is_nan = '0;
    is_snan = '0;
    is_inf = '0;
    max_exp = 12'd2047;
    selected_format = 2'd2;
    canonical_nan = 64'h7ff8_0000_0000_0000;
    for (int op = 0; op < 2; op++) begin
      case (format_i)
        FP16: begin
          operand_sign[op] = operand[op][15];
          exponent[op] = {6'b0, operand[op][14:10]};
          significand[op] = {|operand[op][14:10], operand[op][9:0], 42'b0};
          is_nan[op] = (&operand[op][14:10]) && (|operand[op][9:0]);
          is_snan[op] = is_nan[op] && !operand[op][9];
          is_inf[op] = (&operand[op][14:10]) && !(|operand[op][9:0]);
        end
        FP32: begin
          operand_sign[op] = operand[op][31];
          exponent[op] = {3'b0, operand[op][30:23]};
          significand[op] = {|operand[op][30:23], operand[op][22:0], 29'b0};
          is_nan[op] = (&operand[op][30:23]) && (|operand[op][22:0]);
          is_snan[op] = is_nan[op] && !operand[op][22];
          is_inf[op] = (&operand[op][30:23]) && !(|operand[op][22:0]);
        end
        default: begin
          operand_sign[op] = operand[op][63];
          exponent[op] = operand[op][62:52];
          significand[op] = {|operand[op][62:52], operand[op][51:0]};
          is_nan[op] = (&operand[op][62:52]) && (|operand[op][51:0]);
          is_snan[op] = is_nan[op] && !operand[op][51];
          is_inf[op] = (&operand[op][62:52]) && !(|operand[op][51:0]);
        end
      endcase
    end
    case (format_i)
      FP16: begin
        max_exp = 12'd31;
        selected_format = 2'd0;
        canonical_nan = 64'hffff_ffff_ffff_7e00;
      end
      FP32: begin
        max_exp = 12'd255;
        selected_format = 2'd1;
        canonical_nan = 64'hffff_ffff_7fc0_0000;
      end
      default: ;
    endcase
    // Native biased exponents are sufficient: only equal-format operands
    // enter a request. Left-aligned significands share the 53-bit arithmetic.
    larger_exp = {1'b0, exponent[0]};
    smaller_exp = {1'b0, exponent[1]};
    larger_sig = significand[0];
    smaller_sig = significand[1];
    sign = operand_sign[0];
    if ({exponent[0], significand[0]} < {exponent[1], significand[1]}) begin
      larger_exp = {1'b0, exponent[1]};
      smaller_exp = {1'b0, exponent[0]};
      larger_sig = significand[1];
      smaller_sig = significand[0];
      sign = operand_sign[1];
    end
    if (larger_exp == 0) larger_exp = 1;
    if (smaller_exp == 0) smaller_exp = 1;
    subtraction = operand_sign[0] ^ operand_sign[1];
    larger_ext = {1'b0, larger_sig, 3'b0};
    smaller_ext = {1'b0, smaller_sig, 3'b0};
    distance = larger_exp - smaller_exp;
    aligned = smaller_ext >> distance;
    lost = 1'b0;
    for (int bit_idx = 0; bit_idx < 57; bit_idx++)
      if (distance > bit_idx) lost |= smaller_ext[bit_idx];
    aligned[0] |= lost;
    sum = subtraction ? larger_ext - aligned : larger_ext + aligned;
    normalized = sum;
    norm_exp = larger_exp;
    leading = 0;
    left_shift = 0;
    if (sum[56]) begin
      normalized = sum >> 1;
      normalized[0] |= sum[0];
      norm_exp = larger_exp + 1'b1;
    end else begin
      leading = 56;
      for (int bit_idx = 0; bit_idx < 56; bit_idx++)
        if (sum[bit_idx]) leading = 55-bit_idx;
      left_shift = leading;
      if (left_shift > int'(larger_exp)-1) left_shift = int'(larger_exp)-1;
      normalized = sum << left_shift;
      norm_exp = larger_exp - 12'(left_shift);
    end
    if (!normalized[55]) norm_exp = '0;
    overflow_before = norm_exp >= max_exp;
    infinity = is_inf[0] ? a_i : b_i;
    case (format_i)
      FP16: infinity[63:16] = '1;
      FP32: infinity[63:32] = '1;
      default: ;
    endcase
  end

  // Round directly at the target precision; never round to FP64 first,
  // which could introduce double rounding for FP16 or FP32.
  for (genvar f = 0; f < 3; f++) begin : gen_round
    localparam fp_format_e Fmt = f == 0 ? FP16 : f == 1 ? FP32 : FP64;
    localparam int W = fp_width(Fmt), E = exp_bits(Fmt), M = man_bits(Fmt);
    localparam int Low = 55-M;
    logic [E+M-1:0] pre_round, rounded;
    logic [1:0] round_sticky;
    logic rounded_sign;
    always_comb begin
      pre_round = {norm_exp[E-1:0], normalized[54:Low]};
      round_sticky = {normalized[Low-1], |normalized[Low-2:0]};
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
      .sign_o(rounded_sign), .exact_zero_o()
    );
    assign rounded_result[f] = {{(64-W){1'b1}}, rounded_sign, rounded};
    always_comb begin
      rounded_status[f] = '0;
      rounded_status[f].OF = overflow_before || (&rounded[M+:E]);
      rounded_status[f].NX = (|round_sticky) || rounded_status[f].OF;
      rounded_status[f].UF = !(|rounded[M+:E]) && rounded_status[f].NX;
    end
  end
  always_comb begin
    result_o = rounded_result[selected_format];
    status_o = rounded_status[selected_format];
    if ((|is_nan) || ((&is_inf) && subtraction)) begin
      result_o = canonical_nan;
      status_o = '0;
      status_o.NV = (|is_snan) || ((&is_inf) && subtraction);
    end else if (|is_inf) begin
      result_o = infinity;
      status_o = '0;
    end
  end
endmodule
