// Copyright 2026
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Exact, throughput-oriented backend for unordered binary32 reductions.
//
// Every finite binary32 input is an integer multiple of 2^-149.  The four
// banks below therefore accumulate signed fixed-point integers without any
// intermediate rounding.  Consecutive 64-bit source beats use different
// banks, removing the floating-point recurrence while retaining one-beat-per-
// cycle input throughput.  The banks are merged exactly and rounded once.

module fp32_exact_reduction_accum #(
  // 288 bits cover 256 binary32 vector elements plus the scalar seed.  The
  // sign bit and three spare magnitude bits also cover worst-case carry-out.
  parameter integer AccWidth = 288,
  // Replace the four full-width temporal banks with sixteen exponent-local
  // bins.  The bins are normalized in place during the existing 4->2->1
  // merge slots, so this mode preserves latency while reducing finite-state
  // storage from 4*288 to 16*49 bits and narrowing the active feedback adder.
  parameter bit ExponentSegmented = 1'b0,
  // A global packet merger can consume the exact state directly.  Disabling
  // the lane-local final result lets synthesis prune four redundant rounders
  // while preserving the same state-ready handshake.
  parameter bit EmitRoundedResult = 1'b1
) (
  input  logic                  clk_i,
  input  logic                  rst_ni,

  input  logic                  start_i,
  input  logic [2:0]            rnd_mode_i,
  input  logic                  seed_valid_i,
  input  logic [31:0]           seed_i,

  input  logic [63:0]           data_i,
  input  logic [1:0]            active_i,
  input  logic                  last_i,
  input  logic                  in_valid_i,
  output logic                  in_ready_o,

  output logic [31:0]           result_o,
  // RISC-V fflags order: {NV, DZ, OF, UF, NX}.
  output logic [4:0]            status_o,
  output logic                  out_valid_o,
  input  logic                  out_ready_i,
  output logic                  busy_o,

  // Stable while out_valid_o is asserted.  These ports are the serialization
  // boundary used by the 64-bit tagged cross-lane exact protocol.
  output logic [AccWidth-1:0]   exact_value_o,
  output logic [3:0]            special_o,
  output logic                  source_seen_o,
  output logic                  finite_nonzero_seen_o,
  output logic                  pos_zero_seen_o,
  output logic                  neg_zero_seen_o,
  output logic                  seed_valid_o,
  output logic [31:0]           seed_o,
  output logic [2:0]            rnd_mode_o
);

  typedef logic signed [AccWidth-1:0] accumulator_t;
  localparam integer SegmentCount    = 16;
  localparam integer SegmentBits     = 16;
  localparam integer SegmentBinWidth = 49;
  localparam integer ChunkWidth      = 98;
  typedef logic signed [SegmentBinWidth-1:0] segment_bin_t;
  typedef logic signed [ChunkWidth-1:0] normalization_chunk_t;
  typedef struct packed {
    logic nan;
    logic invalid;
    logic pos_inf;
    logic neg_inf;
  } special_t;

  typedef enum logic [2:0] {
    IDLE,
    ACCUMULATE,
    MERGE_PAIRS,
    MERGE_ROOT,
    ROUND_RESULT,
    HOLD_RESULT
  } state_e;

  state_e state_d, state_q;

  accumulator_t [3:0] bank_d, bank_q;
  segment_bin_t [SegmentCount-1:0] segment_bin_d, segment_bin_q;
  special_t [3:0] bank_special_d, bank_special_q;
  logic [1:0] bank_index_d, bank_index_q;

  logic [2:0] rnd_mode_d, rnd_mode_q;
  logic       seed_valid_d, seed_valid_q;
  logic [31:0] seed_raw_d, seed_raw_q;
  logic       source_seen_d, source_seen_q;
  logic       finite_nonzero_seen_d, finite_nonzero_seen_q;
  logic       pos_zero_seen_d, pos_zero_seen_q;
  logic       neg_zero_seen_d, neg_zero_seen_q;

  logic [31:0] result_d, result_q;
  logic [4:0]  status_d, status_q;

  function automatic logic fp32_is_nan(input logic [31:0] value);
    fp32_is_nan = (&value[30:23]) && (|value[22:0]);
  endfunction

  function automatic logic fp32_is_snan(input logic [31:0] value);
    fp32_is_snan = fp32_is_nan(value) && !value[22];
  endfunction

  function automatic logic fp32_is_inf(input logic [31:0] value);
    fp32_is_inf = (&value[30:23]) && !(|value[22:0]);
  endfunction

  function automatic logic fp32_is_zero(input logic [31:0] value);
    fp32_is_zero = !(|value[30:0]);
  endfunction

  function automatic logic fp32_is_finite_nonzero(input logic [31:0] value);
    fp32_is_finite_nonzero = !(&value[30:23]) && (|value[30:0]);
  endfunction

  function automatic special_t fp32_special(input logic [31:0] value);
    special_t decoded;
    begin
      decoded = '0;
      if (fp32_is_nan(value)) begin
        decoded.nan = 1'b1;
        decoded.invalid = fp32_is_snan(value);
      end else if (fp32_is_inf(value)) begin
        decoded.pos_inf = !value[31];
        decoded.neg_inf = value[31];
      end
      fp32_special = decoded;
    end
  endfunction

  // This is the special-value behavior of one exact IEEE addition node.
  // Keeping it per bank (and merging banks in a fixed 4->2->1 tree) is
  // important: a pre-existing qNaN suppresses a later infinity conflict,
  // whereas an sNaN always contributes NV.
  function automatic special_t merge_special(
    input special_t left,
    input special_t right
  );
    special_t merged;
    begin
      merged = '0;
      merged.invalid = left.invalid | right.invalid;
      if (left.nan || right.nan) begin
        merged.nan = 1'b1;
      end else if ((left.pos_inf && right.neg_inf) ||
                   (left.neg_inf && right.pos_inf)) begin
        merged.nan = 1'b1;
        merged.invalid = 1'b1;
      end else begin
        merged.pos_inf = left.pos_inf | right.pos_inf;
        merged.neg_inf = left.neg_inf | right.neg_inf;
      end
      merge_special = merged;
    end
  endfunction

  // Convert a finite binary32 number into a signed integer whose bit zero has
  // weight 2^-149.  For normals, the required shift is simply exp_field-1:
  //   (1.fraction) * 2^(exp-127) / 2^23 * 2^149.
  function automatic accumulator_t fp32_to_fixed(input logic [31:0] value);
    accumulator_t magnitude;
    logic [23:0] significand;
    int unsigned shift;
    begin
      magnitude = '0;
      if (value[30:23] == 8'h00) begin
        magnitude[22:0] = value[22:0];
      end else if (value[30:23] != 8'hff) begin
        significand = {1'b1, value[22:0]};
        shift = value[30:23] - 1'b1;
        magnitude = significand;
        magnitude = magnitude <<< shift;
      end
      fp32_to_fixed = value[31] ? -magnitude : magnitude;
    end
  endfunction

  // Divide the binary32 exponent range into sixteen 16-bit fixed-point
  // windows.  Segment zero also contains subnormals, whose significand is
  // already expressed in units of 2^-149.
  function automatic logic [3:0] fp32_segment_index(
    input logic [31:0] value
  );
    logic [7:0] unbiased_shift;
    begin
      unbiased_shift = (value[30:23] == 8'h00)
                     ? 8'h00 : value[30:23] - 1'b1;
      fp32_segment_index = unbiased_shift[7:4];
    end
  endfunction

  // Convert one finite binary32 value into the coordinate system of its
  // exponent segment.  At most 257 inputs can contribute to a reduction in
  // the supported configuration, so 49 signed bits cover a 24-bit
  // significand, a 15-bit local shift and all population carry bits.
  function automatic segment_bin_t fp32_to_segment(
    input logic [31:0] value
  );
    segment_bin_t magnitude;
    logic [23:0] significand;
    logic [3:0] local_shift;
    begin
      magnitude = '0;
      if (value[30:23] == 8'h00) begin
        magnitude[22:0] = value[22:0];
      end else if (value[30:23] != 8'hff) begin
        significand = {1'b1, value[22:0]};
        local_shift = (value[30:23] - 1'b1) & 8'h0f;
        magnitude = significand;
        magnitude = magnitude <<< local_shift;
      end
      fp32_to_segment = value[31] ? -magnitude : magnitude;
    end
  endfunction

  // Compose four adjacent exponent bins into one base-2^16 normalization
  // chunk.  A carry from the lower 64-bit chunk is expressed in the current
  // chunk's units.  Balanced pair sums keep the widest combinational adders
  // below one hundred bits.
  function automatic normalization_chunk_t compose_segment_chunk(
    input segment_bin_t bin0,
    input segment_bin_t bin1,
    input segment_bin_t bin2,
    input segment_bin_t bin3,
    input segment_bin_t carry
  );
    normalization_chunk_t pair_lo, pair_hi, carry_ext;
    normalization_chunk_t bin0_ext, bin1_ext, bin2_ext, bin3_ext;
    begin
      bin0_ext = bin0;
      bin1_ext = bin1;
      bin2_ext = bin2;
      bin3_ext = bin3;
      pair_lo = bin0_ext + (bin1_ext <<< SegmentBits);
      pair_hi = (bin2_ext <<< (2*SegmentBits)) +
                (bin3_ext <<< (3*SegmentBits));
      carry_ext = carry;
      compose_segment_chunk = pair_lo + pair_hi + carry_ext;
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

  // Round an exact signed fixed-point sum to binary32.  A subnormal result is
  // always exact because the accumulator quantum equals the binary32 minimum
  // subnormal; only normal significand truncation can set NX.
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
        // Same-sign signed zeros retain their sign.  An exact cancellation or
        // mixed-sign zero sum follows IEEE-754's rounding-direction rule.
        if (!finite_nonzero_seen && neg_zero_seen && !pos_zero_seen)
          zero_sign = 1'b1;
        else if (!finite_nonzero_seen && pos_zero_seen && !neg_zero_seen)
          zero_sign = 1'b0;
        else
          zero_sign = (round_mode == 3'b010);
        result = {zero_sign, 31'b0};
      end else if (msb < 23) begin
        // Exact subnormal: accumulator bit 0 is binary32's 2^-149 bit.
        result = {sign, 8'h00, magnitude[22:0]};
      end else begin
        exponent = msb - 149;
        shift = msb - 23;

        if (exponent > 127) begin
          result = overflow_result(sign, round_mode);
          flags[2] = 1'b1; // OF
          flags[0] = 1'b1; // NX
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
                               (sticky_bit || significand[0]); // RNE
            3'b001: increment = 1'b0;                         // RTZ
            3'b010: increment = sign && inexact;              // RDN
            3'b011: increment = !sign && inexact;             // RUP
            3'b100: increment = guard_bit;                    // RMM
            default: increment = 1'b0;
          endcase

          rounded_significand = {1'b0, significand};
          if (round_mode == 3'b101) begin
            // fpnew's non-standard round-to-odd mode is useful for widening
            // experiments even though this first integration targets only
            // non-widening RVV sums.
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
            flags[2] = 1'b1; // OF
            flags[0] = 1'b1; // NX
          end else begin
            encoded_exponent = exponent + 127;
            result = {sign, encoded_exponent, significand[22:0]};
            flags[0] = inexact; // NX
          end
        end
      end
      round_fixed = {flags, result};
    end
  endfunction

  always_comb begin : p_next
    logic [36:0] rounded;
    logic [31:0] element;
    logic [3:0] element_segment;
    accumulator_t exact_root;
    normalization_chunk_t chunk0, chunk1;
    segment_bin_t chunk_carry;
    special_t root_special;

    state_d               = state_q;
    bank_d                = bank_q;
    segment_bin_d         = segment_bin_q;
    bank_special_d        = bank_special_q;
    bank_index_d          = bank_index_q;
    rnd_mode_d            = rnd_mode_q;
    seed_valid_d          = seed_valid_q;
    seed_raw_d            = seed_raw_q;
    source_seen_d         = source_seen_q;
    finite_nonzero_seen_d = finite_nonzero_seen_q;
    pos_zero_seen_d       = pos_zero_seen_q;
    neg_zero_seen_d       = neg_zero_seen_q;
    result_d              = result_q;
    status_d              = status_q;
    rounded               = '0;
    element               = '0;
    element_segment       = '0;
    chunk0                = '0;
    chunk1                = '0;
    chunk_carry           = '0;
    root_special          = bank_special_q[0];

    in_ready_o  = (state_q == ACCUMULATE) ||
                  ((state_q == IDLE) && start_i);
    out_valid_o = (state_q == HOLD_RESULT);
    result_o    = result_q;
    status_o    = status_q;
    busy_o      = (state_q != IDLE);

    // Reconstruct the normalized base-2^16 digits only for the final rounding
    // cycle.  The upper 32 bits share segment 15's otherwise unused high
    // storage, so segmented mode needs no 288-bit root register.
    exact_root = bank_q[0];
    if (ExponentSegmented) begin
      exact_root = '0;
      for (int segment = 0; segment < SegmentCount; segment++)
        exact_root[SegmentBits*segment +: SegmentBits] =
          segment_bin_q[segment][SegmentBits-1:0];
      exact_root[AccWidth-1:256] =
        {(AccWidth-256){segment_bin_q[15][47]}};
      exact_root[287:256] = segment_bin_q[15][47:16];
    end

    exact_value_o          = exact_root;
    special_o              = root_special;
    source_seen_o          = source_seen_q;
    finite_nonzero_seen_o  = finite_nonzero_seen_q;
    pos_zero_seen_o        = pos_zero_seen_q;
    neg_zero_seen_o        = neg_zero_seen_q;
    seed_valid_o           = seed_valid_q;
    seed_o                 = seed_raw_q;
    rnd_mode_o             = rnd_mode_q;

    unique case (state_q)
      IDLE: begin
        if (start_i) begin
          state_d               = ACCUMULATE;
          bank_d                = '0;
          segment_bin_d         = '0;
          bank_special_d        = '0;
          bank_index_d          = '0;
          rnd_mode_d            = rnd_mode_i;
          seed_valid_d          = seed_valid_i;
          seed_raw_d            = seed_i;
          source_seen_d         = 1'b0;
          finite_nonzero_seen_d = seed_valid_i &&
                                  fp32_is_finite_nonzero(seed_i);
          pos_zero_seen_d       = seed_valid_i && fp32_is_zero(seed_i) &&
                                  !seed_i[31];
          neg_zero_seen_d       = seed_valid_i && fp32_is_zero(seed_i) &&
                                  seed_i[31];
          result_d              = '0;
          status_d              = '0;

          if (seed_valid_i)
            bank_special_d[0] = fp32_special(seed_i);
          if (seed_valid_i && !fp32_is_nan(seed_i) &&
              !fp32_is_inf(seed_i)) begin
            if (ExponentSegmented)
              segment_bin_d[fp32_segment_index(seed_i)] =
                fp32_to_segment(seed_i);
            else
              bank_d[0] = fp32_to_fixed(seed_i);
          end

          // Start and the first source beat may handshake together.  This
          // avoids a setup bubble at the VMFPU instruction boundary.
          if (in_valid_i) begin
            for (int e = 0; e < 2; e++) begin
              element = data_i[32*e +: 32];
              if (active_i[e]) begin
                source_seen_d = 1'b1;
                bank_special_d[0] =
                  merge_special(bank_special_d[0], fp32_special(element));
                finite_nonzero_seen_d |= fp32_is_finite_nonzero(element);
                pos_zero_seen_d |= fp32_is_zero(element) && !element[31];
                neg_zero_seen_d |= fp32_is_zero(element) && element[31];
                if (!fp32_is_nan(element) && !fp32_is_inf(element)) begin
                  if (ExponentSegmented) begin
                    element_segment = fp32_segment_index(element);
                    segment_bin_d[element_segment] +=
                      fp32_to_segment(element);
                  end else begin
                    bank_d[0] += fp32_to_fixed(element);
                  end
                end
              end
            end
            bank_index_d = 2'd1;
            if (last_i)
              state_d = MERGE_PAIRS;
          end
        end
      end

      ACCUMULATE: begin
        if (in_valid_i) begin
          for (int e = 0; e < 2; e++) begin
            element = data_i[32*e +: 32];
            if (active_i[e]) begin
              source_seen_d = 1'b1;
              bank_special_d[bank_index_q] =
                merge_special(bank_special_d[bank_index_q],
                              fp32_special(element));
              finite_nonzero_seen_d |= fp32_is_finite_nonzero(element);
              pos_zero_seen_d |= fp32_is_zero(element) && !element[31];
              neg_zero_seen_d |= fp32_is_zero(element) && element[31];
              if (!fp32_is_nan(element) && !fp32_is_inf(element)) begin
                if (ExponentSegmented) begin
                  element_segment = fp32_segment_index(element);
                  segment_bin_d[element_segment] +=
                    fp32_to_segment(element);
                end else begin
                  bank_d[bank_index_q] += fp32_to_fixed(element);
                end
              end
            end
          end
          bank_index_d = bank_index_q + 1'b1;
          if (last_i)
            state_d = MERGE_PAIRS;
        end
      end

      MERGE_PAIRS: begin
        if (ExponentSegmented) begin
          // Normalize the lower eight exponent windows into eight base-2^16
          // digits.  Consumed bins are overwritten in place; bin zero's high
          // bits temporarily carry the signed value entering segment eight.
          chunk0 = compose_segment_chunk(
            segment_bin_q[0], segment_bin_q[1],
            segment_bin_q[2], segment_bin_q[3], '0);
          chunk_carry = chunk0 >>> 64;
          chunk1 = compose_segment_chunk(
            segment_bin_q[4], segment_bin_q[5],
            segment_bin_q[6], segment_bin_q[7], chunk_carry);
          for (int digit = 0; digit < 4; digit++) begin
            segment_bin_d[digit] = '0;
            segment_bin_d[digit][15:0] =
              chunk0[SegmentBits*digit +: SegmentBits];
            segment_bin_d[digit+4] = '0;
            segment_bin_d[digit+4][15:0] =
              chunk1[SegmentBits*digit +: SegmentBits];
          end
          segment_bin_d[0][48:16] = chunk1[96:64];
        end else begin
          bank_d[0] = bank_q[0] + bank_q[1];
          bank_d[1] = bank_q[2] + bank_q[3];
        end
        bank_special_d[0] =
          merge_special(bank_special_q[0], bank_special_q[1]);
        bank_special_d[1] =
          merge_special(bank_special_q[2], bank_special_q[3]);
        state_d = MERGE_ROOT;
      end

      MERGE_ROOT: begin
        if (ExponentSegmented) begin
          // Finish the upper eight windows.  The final signed carry occupies
          // segment 15's high bits and becomes exact_root[287:256].
          chunk_carry = $signed(segment_bin_q[0][48:16]);
          chunk0 = compose_segment_chunk(
            segment_bin_q[8], segment_bin_q[9],
            segment_bin_q[10], segment_bin_q[11], chunk_carry);
          chunk_carry = chunk0 >>> 64;
          chunk1 = compose_segment_chunk(
            segment_bin_q[12], segment_bin_q[13],
            segment_bin_q[14], segment_bin_q[15], chunk_carry);
          for (int digit = 0; digit < 4; digit++) begin
            segment_bin_d[digit+8] = '0;
            segment_bin_d[digit+8][15:0] =
              chunk0[SegmentBits*digit +: SegmentBits];
            segment_bin_d[digit+12] = '0;
            segment_bin_d[digit+12][15:0] =
              chunk1[SegmentBits*digit +: SegmentBits];
          end
          segment_bin_d[15][48:16] = chunk1[96:64];
        end else begin
          bank_d[0] = bank_q[0] + bank_q[1];
        end
        bank_special_d[0] =
          merge_special(bank_special_q[0], bank_special_q[1]);
        state_d = ROUND_RESULT;
      end

      ROUND_RESULT: begin
        status_d = '0;
        if (!EmitRoundedResult) begin
          // The exact state is consumed by the global packet merger.  Keep a
          // deterministic local payload, but do not build a second rounder.
          result_d = '0;
        end else if (!source_seen_q) begin
          // RVV requires an all-inactive reduction to copy the scalar seed
          // without raising exceptions.  An empty non-seed subtree uses the
          // additive identity selected by the rounding direction.
          result_d = seed_valid_q ? seed_raw_q
                                  : {(rnd_mode_q != 3'b010), 31'b0};
        end else if (root_special.nan) begin
          result_d = 32'h7fc00000;
          status_d[4] = root_special.invalid;
        end else if (root_special.pos_inf) begin
          result_d = 32'h7f800000;
        end else if (root_special.neg_inf) begin
          result_d = 32'hff800000;
        end else begin
          rounded = round_fixed(exact_root, rnd_mode_q,
                                finite_nonzero_seen_q,
                                pos_zero_seen_q, neg_zero_seen_q);
          status_d = rounded[36:32];
          result_d = rounded[31:0];
        end
        state_d = HOLD_RESULT;
      end

      HOLD_RESULT: begin
        if (out_ready_i)
          state_d = IDLE;
      end

      default: state_d = IDLE;
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q               <= IDLE;
      bank_q                <= '0;
      segment_bin_q         <= '0;
      bank_special_q        <= '0;
      bank_index_q          <= '0;
      rnd_mode_q            <= '0;
      seed_valid_q          <= 1'b0;
      seed_raw_q            <= '0;
      source_seen_q         <= 1'b0;
      finite_nonzero_seen_q <= 1'b0;
      pos_zero_seen_q       <= 1'b0;
      neg_zero_seen_q       <= 1'b0;
      result_q              <= '0;
      status_q              <= '0;
    end else begin
      state_q               <= state_d;
      bank_q                <= bank_d;
      segment_bin_q         <= segment_bin_d;
      bank_special_q        <= bank_special_d;
      bank_index_q          <= bank_index_d;
      rnd_mode_q            <= rnd_mode_d;
      seed_valid_q          <= seed_valid_d;
      seed_raw_q            <= seed_raw_d;
      source_seen_q         <= source_seen_d;
      finite_nonzero_seen_q <= finite_nonzero_seen_d;
      pos_zero_seen_q       <= pos_zero_seen_d;
      neg_zero_seen_q       <= neg_zero_seen_d;
      result_q              <= result_d;
      status_q              <= status_d;
    end
  end

`ifndef SYNTHESIS
  initial begin
    assert (AccWidth >= 288)
      else $fatal(1, "binary32 exact reduction accumulator is too narrow");
  end

  a_result_stable_under_backpressure: assert property (
    @(posedge clk_i) disable iff (!rst_ni)
      (out_valid_o && !out_ready_i) |=>
        $stable({result_o, status_o})
  ) else $error("exact reduction result changed under backpressure");

  a_input_only_while_accumulating: assert property (
    @(posedge clk_i) disable iff (!rst_ni)
      (in_valid_i && in_ready_o) |->
        (state_q == ACCUMULATE || (state_q == IDLE && start_i))
  ) else $error("exact reduction input accepted outside accumulation");
`endif

endmodule
