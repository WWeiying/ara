// Copyright 2026
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// One-shot binary32 finalizer for a globally merged exact reduction state.
//
// Bit zero of exact_value_i has weight 2^-149.  The finite sum is therefore
// rounded only here, after every lane-local state has been merged.  The
// metadata inputs preserve IEEE-754 special-value and signed-zero behavior.

module fp32_exact_reduction_finalize #(
  parameter integer AccWidth = 288
) (
  input  logic signed [AccWidth-1:0] exact_value_i,
  // {nan, invalid, positive infinity, negative infinity}
  input  logic [3:0]                  special_i,
  input  logic                        source_seen_i,
  input  logic                        finite_nonzero_seen_i,
  input  logic                        pos_zero_seen_i,
  input  logic                        neg_zero_seen_i,
  input  logic                        seed_valid_i,
  input  logic [31:0]                 seed_i,
  input  logic [2:0]                  rnd_mode_i,
  output logic [31:0]                 result_o,
  // RISC-V fflags order: {NV, DZ, OF, UF, NX}.
  output logic [4:0]                  status_o
);

  typedef logic signed [AccWidth-1:0] accumulator_t;

  function automatic logic [31:0] overflow_result(
    input logic sign,
    input logic [2:0] round_mode
  );
    logic round_to_infinity;
    begin
      unique case (round_mode)
        3'b001: round_to_infinity = 1'b0;  // RTZ
        3'b010: round_to_infinity = sign;  // RDN
        3'b011: round_to_infinity = !sign; // RUP
        3'b101: round_to_infinity = 1'b0;  // ROD
        default: round_to_infinity = 1'b1; // RNE/RMM
      endcase
      overflow_result = round_to_infinity
                      ? {sign, 8'hff, 23'h0}
                      : {sign, 8'hfe, 23'h7fffff};
    end
  endfunction

  function automatic logic [36:0] round_fixed(
    input accumulator_t exact_value,
    input logic [2:0] round_mode,
    input logic finite_nonzero_seen,
    input logic pos_zero_seen,
    input logic neg_zero_seen
  );
    accumulator_t magnitude;
    logic sign;
    logic zero_sign;
    logic [23:0] significand;
    logic [24:0] rounded_significand;
    logic guard_bit, sticky_bit, inexact, increment;
    logic [7:0] encoded_exponent;
    logic [31:0] result;
    logic [4:0] flags;
    int msb;
    int shift;
    int exponent;
    begin
      result = '0;
      flags  = '0;
      sign = exact_value[AccWidth-1];
      magnitude = sign ? -exact_value : exact_value;

      msb = -1;
      for (int i = 0; i < AccWidth; i++)
        if (magnitude[i])
          msb = i;

      if (msb < 0) begin
        if (!finite_nonzero_seen && neg_zero_seen && !pos_zero_seen)
          zero_sign = 1'b1;
        else if (!finite_nonzero_seen && pos_zero_seen && !neg_zero_seen)
          zero_sign = 1'b0;
        else
          zero_sign = (round_mode == 3'b010);
        result = {zero_sign, 31'b0};
      end else if (msb < 23) begin
        result = {sign, 8'h00, magnitude[22:0]};
      end else begin
        exponent = msb - 149;
        shift = msb - 23;

        if (exponent > 127) begin
          result = overflow_result(sign, round_mode);
          flags[2] = 1'b1;
          flags[0] = 1'b1;
        end else begin
          significand = magnitude >>> shift;
          guard_bit = 1'b0;
          sticky_bit = 1'b0;
          if (shift > 0)
            guard_bit = magnitude[shift-1];
          for (int i = 0; i < AccWidth; i++)
            if (i < (shift-1))
              sticky_bit |= magnitude[i];
          inexact = guard_bit | sticky_bit;

          unique case (round_mode)
            3'b000: increment = guard_bit &&
                               (sticky_bit || significand[0]);
            3'b001: increment = 1'b0;
            3'b010: increment = sign && inexact;
            3'b011: increment = !sign && inexact;
            3'b100: increment = guard_bit;
            default: increment = 1'b0;
          endcase

          rounded_significand = {1'b0, significand};
          if (round_mode == 3'b101) begin
            if (inexact)
              rounded_significand[0] = 1'b1;
          end else begin
            rounded_significand += increment;
          end

          if (rounded_significand[24]) begin
            significand = rounded_significand[24:1];
            exponent += 1;
          end else begin
            significand = rounded_significand[23:0];
          end

          if (exponent > 127) begin
            result = overflow_result(sign, round_mode);
            flags[2] = 1'b1;
            flags[0] = 1'b1;
          end else begin
            encoded_exponent = exponent + 127;
            result = {sign, encoded_exponent, significand[22:0]};
            flags[0] = inexact;
          end
        end
      end
      round_fixed = {flags, result};
    end
  endfunction

  always_comb begin
    logic [36:0] rounded;

    rounded = '0;
    result_o = '0;
    status_o = '0;

    if (!source_seen_i) begin
      // An all-inactive RVV reduction copies the scalar seed exactly and
      // raises no exception.  The no-seed case is an internal empty subtree.
      result_o = seed_valid_i ? seed_i
                              : {(rnd_mode_i != 3'b010), 31'b0};
    end else if (special_i[3]) begin
      result_o = 32'h7fc00000;
      status_o[4] = special_i[2];
    end else if (special_i[1]) begin
      result_o = 32'h7f800000;
    end else if (special_i[0]) begin
      result_o = 32'hff800000;
    end else begin
      rounded = round_fixed(exact_value_i, rnd_mode_i,
                            finite_nonzero_seen_i,
                            pos_zero_seen_i, neg_zero_seen_i);
      status_o = rounded[36:32];
      result_o = rounded[31:0];
    end
  end

`ifndef SYNTHESIS
  initial begin
    assert (AccWidth >= 288)
      else $fatal(1, "binary32 exact reduction finalizer is too narrow");
  end
`endif

endmodule
