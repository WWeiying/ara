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
  input  logic                        format_fp16_i,
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

  function automatic logic [15:0] overflow_result_fp16(
    input logic sign,
    input logic [2:0] round_mode
  );
    logic round_to_infinity;
    begin
      unique case (round_mode)
        3'b001: round_to_infinity = 1'b0;
        3'b010: round_to_infinity = sign;
        3'b011: round_to_infinity = !sign;
        3'b101: round_to_infinity = 1'b0;
        default: round_to_infinity = 1'b1;
      endcase
      overflow_result_fp16 = round_to_infinity
                           ? {sign, 5'h1f, 10'h000}
                           : {sign, 5'h1e, 10'h3ff};
    end
  endfunction

  // A two-level leading-one search avoids synthesizing the 288-entry linear
  // priority chain produced by a monolithic ascending for-loop.  Sixteen-bit
  // groups first locate the highest occupied window; a second short search
  // resolves the bit within that window.  FP16 and FP32 share this decode.
  function automatic integer exact_msb(input accumulator_t magnitude);
    logic [17:0] group_nonzero;
    int highest_group;
    begin
      group_nonzero = '0;
      for (int group = 0; group < 18; group++)
        group_nonzero[group] = |magnitude[group*16 +: 16];

      highest_group = -1;
      for (int group = 0; group < 18; group++)
        if (group_nonzero[group])
          highest_group = group;

      exact_msb = -1;
      if (highest_group >= 0)
        for (int bit_index = 0; bit_index < 16; bit_index++)
          if (magnitude[highest_group*16 + bit_index])
            exact_msb = highest_group*16 + bit_index;
    end
  endfunction

  function automatic logic [36:0] round_fixed(
    input accumulator_t magnitude,
    input logic sign,
    input integer msb,
    input logic [2:0] round_mode,
    input logic finite_nonzero_seen,
    input logic pos_zero_seen,
    input logic neg_zero_seen
  );
    logic zero_sign;
    logic [23:0] significand;
    logic [24:0] rounded_significand;
    logic guard_bit, sticky_bit, inexact, increment;
    logic [7:0] encoded_exponent;
    logic [31:0] result;
    logic [4:0] flags;
    int shift;
    int exponent;
    begin
      result = '0;
      flags  = '0;

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

  // Round the shared 2^-149 exact state to binary16.  Binary16's minimum
  // subnormal has weight 2^-24 and therefore occupies accumulator bit 125.
  // Sums of binary16 inputs remain multiples of that quantum, so subnormal
  // results are exact and cannot raise UF/NX.
  function automatic logic [20:0] round_fixed_fp16(
    input accumulator_t magnitude,
    input logic sign,
    input integer msb,
    input logic [2:0] round_mode,
    input logic finite_nonzero_seen,
    input logic pos_zero_seen,
    input logic neg_zero_seen
  );
    logic zero_sign;
    logic [10:0] significand;
    logic [11:0] rounded_significand;
    logic guard_bit, sticky_bit, inexact, increment;
    logic [4:0] encoded_exponent;
    logic [15:0] result;
    logic [4:0] flags;
    int shift;
    int exponent;
    begin
      result = '0;
      flags = '0;

      if (msb < 0) begin
        if (!finite_nonzero_seen && neg_zero_seen && !pos_zero_seen)
          zero_sign = 1'b1;
        else if (!finite_nonzero_seen && pos_zero_seen && !neg_zero_seen)
          zero_sign = 1'b0;
        else
          zero_sign = (round_mode == 3'b010);
        result = {zero_sign, 15'b0};
      end else if (msb < 135) begin
        result = {sign, 5'h00, magnitude[134:125]};
      end else begin
        exponent = msb - 149;
        shift = msb - 10;

        if (exponent > 15) begin
          result = overflow_result_fp16(sign, round_mode);
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

          if (rounded_significand[11]) begin
            significand = rounded_significand[11:1];
            exponent += 1;
          end else begin
            significand = rounded_significand[10:0];
          end

          if (exponent > 15) begin
            result = overflow_result_fp16(sign, round_mode);
            flags[2] = 1'b1;
            flags[0] = 1'b1;
          end else begin
            encoded_exponent = exponent + 15;
            result = {sign, encoded_exponent, significand[9:0]};
            flags[0] = inexact;
          end
        end
      end
      round_fixed_fp16 = {flags, result};
    end
  endfunction

  always_comb begin
    logic [36:0] rounded;
    logic [20:0] rounded_fp16;
    accumulator_t magnitude;
    logic sign;
    int msb;

    rounded = '0;
    rounded_fp16 = '0;
    sign = exact_value_i[AccWidth-1];
    magnitude = sign ? -exact_value_i : exact_value_i;
    msb = exact_msb(magnitude);
    result_o = '0;
    status_o = '0;

    if (!source_seen_i) begin
      // An all-inactive RVV reduction copies the scalar seed exactly and
      // raises no exception.  The no-seed case is an internal empty subtree.
      if (format_fp16_i)
        result_o = seed_valid_i ? {16'b0, seed_i[15:0]}
                                : {16'b0, (rnd_mode_i != 3'b010), 15'b0};
      else
        result_o = seed_valid_i ? seed_i
                                : {(rnd_mode_i != 3'b010), 31'b0};
    end else if (special_i[3]) begin
      result_o = format_fp16_i ? 32'h00007e00 : 32'h7fc00000;
      status_o[4] = special_i[2];
    end else if (special_i[1]) begin
      result_o = format_fp16_i ? 32'h00007c00 : 32'h7f800000;
    end else if (special_i[0]) begin
      result_o = format_fp16_i ? 32'h0000fc00 : 32'hff800000;
    end else if (format_fp16_i) begin
      rounded_fp16 = round_fixed_fp16(magnitude, sign, msb, rnd_mode_i,
                                      finite_nonzero_seen_i,
                                      pos_zero_seen_i, neg_zero_seen_i);
      status_o = rounded_fp16[20:16];
      result_o = {16'b0, rounded_fp16[15:0]};
    end else begin
      rounded = round_fixed(magnitude, sign, msb, rnd_mode_i,
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
