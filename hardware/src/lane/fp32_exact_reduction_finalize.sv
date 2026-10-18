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
  parameter integer AccWidth = 288,
  // Share format-dependent extraction without adding a pipeline stage.
  parameter bit SharedExtract =
`ifdef ARA_RED_SHARED_FINALIZE_EXTRACT
    1'b1
`else
    1'b0
`endif
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
  // Deasserted when seed insertion is deferred to this finalizer. The global
  // subtree intentionally excludes the seed and this finalizer inserts the
  // producer's already-rounded architectural value exactly once.
  input  logic                        seed_in_exact_i,
  input  logic [2:0]                  rnd_mode_i,
  input  logic                        format_fp16_i,
  output logic [31:0]                 result_o,
  // RISC-V fflags order: {NV, DZ, OF, UF, NX}.
  output logic [4:0]                  status_o
);

  typedef logic signed [AccWidth-1:0] accumulator_t;

  function automatic logic value_is_nan(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_nan = format_fp16
                 ? ((&value[14:10]) && (|value[9:0]))
                 : ((&value[30:23]) && (|value[22:0]));
  endfunction

  function automatic logic value_is_snan(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_snan = value_is_nan(value, format_fp16) &&
                    (format_fp16 ? !value[9] : !value[22]);
  endfunction

  function automatic logic value_is_inf(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_inf = format_fp16
                 ? ((&value[14:10]) && !(|value[9:0]))
                 : ((&value[30:23]) && !(|value[22:0]));
  endfunction

  function automatic logic value_is_zero(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_zero = format_fp16 ? !(|value[14:0])
                                : !(|value[30:0]);
  endfunction

  function automatic logic value_sign(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_sign = format_fp16 ? value[15] : value[31];
  endfunction

  function automatic accumulator_t value_to_fixed(
    input logic [31:0] value,
    input logic format_fp16
  );
    // Negate at native significand width, before sign extension and alignment.
    // -(m << s) == sign_extend(-m) << s in the exact accumulator domain.
    logic signed [24:0] significand;
    int unsigned shift;
    begin
      significand = '0;
      shift = 0;
      if (format_fp16) begin
        if (value[14:10] == 0) begin
          significand = $signed({15'b0, value[9:0]});
          shift = 125;
        end else if (value[14:10] != 5'h1f) begin
          significand = $signed({14'b0, 1'b1, value[9:0]});
          shift = int'(value[14:10]) + 124;
        end
      end else begin
        if (value[30:23] == 0) begin
          significand = $signed({2'b0, value[22:0]});
        end else if (value[30:23] != 8'hff) begin
          significand = $signed({1'b0, 1'b1, value[22:0]});
          shift = int'(value[30:23]) - 1;
        end
      end
      if (value_sign(value, format_fp16)) significand = -significand;
      value_to_fixed = accumulator_t'(significand) <<< shift;
    end
  endfunction

  function automatic logic [3:0] value_special(
    input logic [31:0] value,
    input logic format_fp16
  );
    logic sign;
    begin
      value_special = '0;
      sign = value_sign(value, format_fp16);
      if (value_is_nan(value, format_fp16)) begin
        value_special[3] = 1'b1;
        value_special[2] = value_is_snan(value, format_fp16);
      end else if (value_is_inf(value, format_fp16)) begin
        value_special[1] = !sign;
        value_special[0] = sign;
      end
    end
  endfunction

  function automatic logic [3:0] merge_special(
    input logic [3:0] left,
    input logic [3:0] right
  );
    begin
      merge_special = '0;
      merge_special[2] = left[2] | right[2];
      if (left[3] || right[3]) begin
        merge_special[3] = 1'b1;
      end else if ((left[1] && right[0]) ||
                   (left[0] && right[1])) begin
        merge_special[3] = 1'b1;
        merge_special[2] = 1'b1;
      end else begin
        merge_special[1] = left[1] | right[1];
        merge_special[0] = left[0] | right[0];
      end
    end
  endfunction

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
    input logic neg_zero_seen,
    input logic [23:0] extracted_significand,
    input logic extracted_guard,
    input logic extracted_sticky
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
          if (SharedExtract) begin
            significand = extracted_significand;
            guard_bit = extracted_guard;
            sticky_bit = extracted_sticky;
          end else begin
            significand = magnitude >>> shift;
            guard_bit = 1'b0;
            sticky_bit = 1'b0;
            if (shift > 0)
              guard_bit = magnitude[shift-1];
            for (int i = 0; i < AccWidth; i++)
              if (i < (shift-1))
                sticky_bit |= magnitude[i];
          end
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
    input logic neg_zero_seen,
    input logic [23:0] extracted_significand,
    input logic extracted_guard,
    input logic extracted_sticky
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
          if (SharedExtract) begin
            significand = extracted_significand;
            guard_bit = extracted_guard;
            sticky_bit = extracted_sticky;
          end else begin
            significand = magnitude >>> shift;
            guard_bit = 1'b0;
            sticky_bit = 1'b0;
            if (shift > 0)
              guard_bit = magnitude[shift-1];
            for (int i = 0; i < AccWidth; i++)
              if (i < (shift-1))
                sticky_bit |= magnitude[i];
          end
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
    accumulator_t effective_exact;
    accumulator_t magnitude;
    logic [3:0] effective_special;
    logic effective_finite_nonzero_seen;
    logic effective_pos_zero_seen;
    logic effective_neg_zero_seen;
    logic insert_seed;
    logic sign;
    int msb;
    int extract_shift;
    logic [23:0] extracted_significand;
    logic extracted_guard, extracted_sticky;

    rounded = '0;
    rounded_fp16 = '0;
    insert_seed = seed_valid_i && !seed_in_exact_i;
    effective_exact = exact_value_i;
    effective_special = special_i;
    effective_finite_nonzero_seen = finite_nonzero_seen_i;
    effective_pos_zero_seen = pos_zero_seen_i;
    effective_neg_zero_seen = neg_zero_seen_i;

    if (insert_seed) begin
      effective_special =
        merge_special(effective_special,
                      value_special(seed_i, format_fp16_i));
      effective_finite_nonzero_seen |=
        !value_is_nan(seed_i, format_fp16_i) &&
        !value_is_inf(seed_i, format_fp16_i) &&
        !value_is_zero(seed_i, format_fp16_i);
      effective_pos_zero_seen |=
        value_is_zero(seed_i, format_fp16_i) &&
        !value_sign(seed_i, format_fp16_i);
      effective_neg_zero_seen |=
        value_is_zero(seed_i, format_fp16_i) &&
        value_sign(seed_i, format_fp16_i);
      if (!value_is_nan(seed_i, format_fp16_i) &&
          !value_is_inf(seed_i, format_fp16_i))
        effective_exact += value_to_fixed(seed_i, format_fp16_i);
    end

    sign = effective_exact[AccWidth-1];
    magnitude = sign ? -effective_exact : effective_exact;
    msb = exact_msb(magnitude);
    // A single 24-bit window also supplies the low 11 bits for binary16.
    // Subnormal and special results bypass this window in the rounders.
    extract_shift = 0;
    extracted_significand = '0;
    extracted_guard = 1'b0;
    extracted_sticky = 1'b0;
    if (SharedExtract) begin
      if (format_fp16_i && msb >= 135) extract_shift = msb - 10;
      else if (!format_fp16_i && msb >= 23) extract_shift = msb - 23;
      extracted_significand = magnitude >>> extract_shift;
      if (extract_shift > 0) extracted_guard = magnitude[extract_shift-1];
      for (int i = 0; i < AccWidth; i++)
        if (i < extract_shift-1) extracted_sticky |= magnitude[i];
    end
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
    end else if (effective_special[3]) begin
      result_o = format_fp16_i ? 32'h00007e00 : 32'h7fc00000;
      status_o[4] = effective_special[2];
    end else if (effective_special[1]) begin
      result_o = format_fp16_i ? 32'h00007c00 : 32'h7f800000;
    end else if (effective_special[0]) begin
      result_o = format_fp16_i ? 32'h0000fc00 : 32'hff800000;
    end else if (format_fp16_i) begin
      rounded_fp16 = round_fixed_fp16(magnitude, sign, msb, rnd_mode_i,
                                      effective_finite_nonzero_seen,
                                      effective_pos_zero_seen,
                                      effective_neg_zero_seen,
                                      extracted_significand, extracted_guard,
                                      extracted_sticky);
      status_o = rounded_fp16[20:16];
      result_o = {16'b0, rounded_fp16[15:0]};
    end else begin
      rounded = round_fixed(magnitude, sign, msb, rnd_mode_i,
                            effective_finite_nonzero_seen,
                            effective_pos_zero_seen,
                            effective_neg_zero_seen,
                            extracted_significand, extracted_guard,
                            extracted_sticky);
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

// Exact seed binding stage for the central RCE. Its outputs are captured in
// the existing root/metadata registers before final normalization and rounding.
// The original finalizer remains usable as a combinational standalone block.
module fp32_exact_reduction_seed #(parameter integer AccWidth = 288) (
  input logic signed [AccWidth-1:0] exact_value_i,
  input logic [3:0] special_i,
  input logic finite_nonzero_seen_i, pos_zero_seen_i, neg_zero_seen_i,
  input logic seed_valid_i, seed_in_exact_i,
  input logic [31:0] seed_i,
  input logic format_fp16_i,
  output logic signed [AccWidth-1:0] exact_value_o,
  // Conversion alone, shared with the RCE header preload. It bypasses the
  // wide root adder; checking window fit must not follow that carry chain.
  output logic signed [AccWidth-1:0] seed_fixed_o,
  output logic [3:0] special_o,
  output logic finite_nonzero_seen_o, pos_zero_seen_o, neg_zero_seen_o
);
  typedef logic signed [AccWidth-1:0] accumulator_t;
  function automatic logic value_is_nan(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_nan = format_fp16
                 ? ((&value[14:10]) && (|value[9:0]))
                 : ((&value[30:23]) && (|value[22:0]));
  endfunction

  function automatic logic value_is_snan(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_snan = value_is_nan(value, format_fp16) &&
                    (format_fp16 ? !value[9] : !value[22]);
  endfunction

  function automatic logic value_is_inf(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_inf = format_fp16
                 ? ((&value[14:10]) && !(|value[9:0]))
                 : ((&value[30:23]) && !(|value[22:0]));
  endfunction

  function automatic logic value_is_zero(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_zero = format_fp16 ? !(|value[14:0])
                                : !(|value[30:0]);
  endfunction

  function automatic logic value_sign(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_sign = format_fp16 ? value[15] : value[31];
  endfunction

  function automatic accumulator_t value_to_fixed(
    input logic [31:0] value,
    input logic format_fp16
  );
    // Negate at native significand width, before sign extension and alignment.
    // -(m << s) == sign_extend(-m) << s in the exact accumulator domain.
    logic signed [24:0] significand;
    int unsigned shift;
    begin
      significand = '0;
      shift = 0;
      if (format_fp16) begin
        if (value[14:10] == 0) begin
          significand = $signed({15'b0, value[9:0]});
          shift = 125;
        end else if (value[14:10] != 5'h1f) begin
          significand = $signed({14'b0, 1'b1, value[9:0]});
          shift = int'(value[14:10]) + 124;
        end
      end else begin
        if (value[30:23] == 0) begin
          significand = $signed({2'b0, value[22:0]});
        end else if (value[30:23] != 8'hff) begin
          significand = $signed({1'b0, 1'b1, value[22:0]});
          shift = int'(value[30:23]) - 1;
        end
      end
      if (value_sign(value, format_fp16)) significand = -significand;
      value_to_fixed = accumulator_t'(significand) <<< shift;
    end
  endfunction

  function automatic logic [3:0] value_special(
    input logic [31:0] value,
    input logic format_fp16
  );
    logic sign;
    begin
      value_special = '0;
      sign = value_sign(value, format_fp16);
      if (value_is_nan(value, format_fp16)) begin
        value_special[3] = 1'b1;
        value_special[2] = value_is_snan(value, format_fp16);
      end else if (value_is_inf(value, format_fp16)) begin
        value_special[1] = !sign;
        value_special[0] = sign;
      end
    end
  endfunction

  function automatic logic [3:0] merge_special(
    input logic [3:0] left,
    input logic [3:0] right
  );
    begin
      merge_special = '0;
      merge_special[2] = left[2] | right[2];
      if (left[3] || right[3]) begin
        merge_special[3] = 1'b1;
      end else if ((left[1] && right[0]) ||
                   (left[0] && right[1])) begin
        merge_special[3] = 1'b1;
        merge_special[2] = 1'b1;
      end else begin
        merge_special[1] = left[1] | right[1];
        merge_special[0] = left[0] | right[0];
      end
    end
  endfunction


  always_comb begin
    seed_fixed_o = '0;
    if (seed_valid_i && !seed_in_exact_i &&
        !value_is_nan(seed_i, format_fp16_i) && !value_is_inf(seed_i, format_fp16_i))
      seed_fixed_o = value_to_fixed(seed_i, format_fp16_i);
    exact_value_o = exact_value_i;
    special_o = special_i;
    finite_nonzero_seen_o = finite_nonzero_seen_i;
    pos_zero_seen_o = pos_zero_seen_i;
    neg_zero_seen_o = neg_zero_seen_i;
    if (seed_valid_i && !seed_in_exact_i) begin
      special_o = merge_special(special_i, value_special(seed_i, format_fp16_i));
      finite_nonzero_seen_o |= !value_is_nan(seed_i, format_fp16_i) &&
        !value_is_inf(seed_i, format_fp16_i) && !value_is_zero(seed_i, format_fp16_i);
      pos_zero_seen_o |= value_is_zero(seed_i, format_fp16_i) && !value_sign(seed_i, format_fp16_i);
      neg_zero_seen_o |= value_is_zero(seed_i, format_fp16_i) && value_sign(seed_i, format_fp16_i);
      if (!value_is_nan(seed_i, format_fp16_i) && !value_is_inf(seed_i, format_fp16_i))
        exact_value_o = exact_value_i + seed_fixed_o;
    end
  end
endmodule
