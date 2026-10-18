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
  // Experimental 32-bit exponent windows: eight 65-bit signed bins retain
  // the same population headroom and two 128-bit normalization phases.
  parameter bit CompactSegments =
`ifdef ARA_RED_COMPACT_EXACT_SEGMENTS
    1'b1,
`else
    1'b0,
`endif
  // Four 64-bit exponent windows trade wider bin updates for fewer read/write
  // selections. Keep the existing two normalization cycles and 288-bit output.
  parameter bit WideSegments =
`ifdef ARA_RED_WIDE_EXACT_SEGMENTS
    1'b1,
`else
    1'b0,
`endif
  // Use one beat-update datapath for simultaneous start/data and later beats.
  // State initialization and seed insertion still precede the first update.
  parameter bit SharedBeatUpdate =
`ifdef ARA_RED_SHARED_EXACT_UPDATE
    1'b1,
`else
    1'b0,
`endif
  // Both normalization phases use the same two chunk composers. Select
  // their input bins before arithmetic; keep the original two-cycle schedule.
  parameter bit SharedNormalize =
`ifdef ARA_RED_SHARED_EXACT_NORMALIZE
    1'b1,
`else
    1'b0,
`endif
  // Read each selected bin from the unmodified beat state, forward only
  // same-bin collisions between elements, then perform one decoded writeback.
  parameter bit CollisionForwardUpdate =
`ifdef ARA_RED_EXACT_COLLISION_FORWARD
    1'b1,
`else
    1'b0,
`endif
  // Deferred-seed updates read registered bins directly. Initialization is
  // applied after the indexed read, avoiding a full-bin next-state mux on
  // every read port. Preserve the original update for non-deferred seeds.
  parameter bit DirectBinRead =
`ifdef ARA_RED_EXACT_DIRECT_BIN_READ
    1'b1,
`else
    1'b0,
`endif
  // A global packet merger can consume the exact state directly.  Disabling
  // the lane-local final result lets synthesis prune four redundant rounders
  // while preserving the same state-ready handshake.
  parameter bit EmitRoundedResult = 1'b1,
  // Global reductions always attach the seed at the central root, even when
  // it is already available. This keeps the special-value tree independent
  // of whether a producer is still running (late seed). Preserve seed
  // metadata for transport, but exclude it from the lane's numeric subtree.
  parameter bit DeferSeed = 1'b0,
  // With centralized rounding, ROUND_RESULT only clears an unused payload.
  // Preserve the two normalization stages; optionally publish their registered
  // exact state immediately afterwards. This does not change rounded mode.
  parameter bit SkipUnroundedRoundStage =
`ifdef ARA_RED_EXACT_NO_ROUND_BUBBLE
    1'b1
`else
    1'b0
`endif
) (
  input  logic                  clk_i,
  input  logic                  rst_ni,

  input  logic                  start_i,
  input  logic [2:0]            rnd_mode_i,
  // Binary16 inputs are embedded in the same 2^-149 fixed-point domain.
  // This mode is used only with the global finalizer; binary32 remains the
  // lane-local rounded-interface format.
  input  logic                  format_fp16_i,
  input  logic                  seed_valid_i,
  input  logic [31:0]           seed_i,

  input  logic [63:0]           data_i,
  input  logic [3:0]            active_i,
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
  output logic [2:0]            rnd_mode_o,
  output logic                  format_fp16_o
);

  typedef logic signed [AccWidth-1:0] accumulator_t;
  localparam integer SegmentBits     = WideSegments ? 64 : CompactSegments ? 32 : 16;
  localparam integer SegmentCount    = 256 / SegmentBits;
  localparam integer SegmentBinWidth = SegmentBits + 33;
  localparam integer DigitsPerChunk  = 64 / SegmentBits;
  localparam integer HalfSegments    = 128 / SegmentBits;
  localparam integer ChunkWidth      = 98;
  typedef logic signed [SegmentBinWidth-1:0] segment_bin_t;
  typedef segment_bin_t [SegmentCount-1:0] segment_bins_t;
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
  logic       format_fp16_d, format_fp16_q;
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

  function automatic logic fp16_is_nan(input logic [15:0] value);
    fp16_is_nan = (&value[14:10]) && (|value[9:0]);
  endfunction

  function automatic logic fp16_is_snan(input logic [15:0] value);
    fp16_is_snan = fp16_is_nan(value) && !value[9];
  endfunction

  function automatic logic fp16_is_inf(input logic [15:0] value);
    fp16_is_inf = (&value[14:10]) && !(|value[9:0]);
  endfunction

  function automatic logic fp16_is_zero(input logic [15:0] value);
    fp16_is_zero = !(|value[14:0]);
  endfunction

  function automatic logic fp16_is_finite_nonzero(input logic [15:0] value);
    fp16_is_finite_nonzero = !(&value[14:10]) && (|value[14:0]);
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

  function automatic special_t fp16_special(input logic [15:0] value);
    special_t decoded;
    begin
      decoded = '0;
      if (fp16_is_nan(value)) begin
        decoded.nan = 1'b1;
        decoded.invalid = fp16_is_snan(value);
      end else if (fp16_is_inf(value)) begin
        decoded.pos_inf = !value[15];
        decoded.neg_inf = value[15];
      end
      fp16_special = decoded;
    end
  endfunction

  function automatic logic value_is_nan(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_nan = format_fp16 ? fp16_is_nan(value[15:0])
                               : fp32_is_nan(value);
  endfunction

  function automatic logic value_is_inf(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_inf = format_fp16 ? fp16_is_inf(value[15:0])
                               : fp32_is_inf(value);
  endfunction

  function automatic logic value_is_zero(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_zero = format_fp16 ? fp16_is_zero(value[15:0])
                                : fp32_is_zero(value);
  endfunction

  function automatic logic value_is_finite_nonzero(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_is_finite_nonzero =
      format_fp16 ? fp16_is_finite_nonzero(value[15:0])
                  : fp32_is_finite_nonzero(value);
  endfunction

  function automatic logic value_sign(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_sign = format_fp16 ? value[15] : value[31];
  endfunction

  function automatic special_t value_special(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_special = format_fp16 ? fp16_special(value[15:0])
                                : fp32_special(value);
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

  // Binary16's minimum subnormal is 2^-24, which is bit 125 of the
  // binary32-oriented 2^-149 accumulator.  Mapping both formats into one
  // coordinate system lets them reuse the packet merger unchanged.
  function automatic accumulator_t fp16_to_fixed(input logic [15:0] value);
    accumulator_t magnitude;
    logic [10:0] significand;
    int unsigned shift;
    begin
      magnitude = '0;
      if (value[14:10] == 5'h00) begin
        magnitude = value[9:0];
        magnitude = magnitude <<< 125;
      end else if (value[14:10] != 5'h1f) begin
        significand = {1'b1, value[9:0]};
        shift = value[14:10] + 124;
        magnitude = significand;
        magnitude = magnitude <<< shift;
      end
      fp16_to_fixed = value[15] ? -magnitude : magnitude;
    end
  endfunction

  function automatic accumulator_t value_to_fixed(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_to_fixed = format_fp16 ? fp16_to_fixed(value[15:0])
                                 : fp32_to_fixed(value);
  endfunction

  // Divide the binary32 exponent range into 16-bit or 32-bit fixed-point
  // windows. Segment zero also contains subnormals, whose significand is
  // already expressed in units of 2^-149.
  function automatic logic [3:0] fp32_segment_index(
    input logic [31:0] value
  );
    logic [7:0] unbiased_shift;
    begin
      unbiased_shift = (value[30:23] == 8'h00)
                     ? 8'h00 : value[30:23] - 1'b1;
      fp32_segment_index = (unbiased_shift >> $clog2(SegmentBits));
    end
  endfunction

  function automatic logic [3:0] fp16_segment_index(
    input logic [15:0] value
  );
    logic [7:0] absolute_shift;
    begin
      absolute_shift = (value[14:10] == 5'h00)
                     ? 8'd125 : value[14:10] + 8'd124;
      fp16_segment_index = (absolute_shift >> $clog2(SegmentBits));
    end
  endfunction

  function automatic logic [3:0] value_segment_index(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_segment_index =
      format_fp16 ? fp16_segment_index(value[15:0])
                  : fp32_segment_index(value);
  endfunction

  // Convert one finite binary32 value into the coordinate system of its
  // exponent segment.  At most 257 inputs can contribute to a reduction in
  // the supported configuration. SegmentBits+33 signed bits cover a 24-bit
  // significand, up to SegmentBits-1 local shift, nine population bits and sign.
  function automatic segment_bin_t fp32_to_segment(
    input logic [31:0] value
  );
    segment_bin_t magnitude;
    logic [23:0] significand;
    logic [$clog2(SegmentBits)-1:0] local_shift;
    begin
      magnitude = '0;
      if (value[30:23] == 8'h00) begin
        magnitude[22:0] = value[22:0];
      end else if (value[30:23] != 8'hff) begin
        significand = {1'b1, value[22:0]};
        local_shift = (value[30:23] - 1'b1) & (SegmentBits-1);
        magnitude = significand;
        magnitude = magnitude <<< local_shift;
      end
      fp32_to_segment = value[31] ? -magnitude : magnitude;
    end
  endfunction

  function automatic segment_bin_t fp16_to_segment(
    input logic [15:0] value
  );
    segment_bin_t magnitude;
    logic [10:0] significand;
    logic [7:0] absolute_shift;
    logic [$clog2(SegmentBits)-1:0] local_shift;
    begin
      magnitude = '0;
      absolute_shift = (value[14:10] == 5'h00)
                     ? 8'd125 : value[14:10] + 8'd124;
      local_shift = absolute_shift[$clog2(SegmentBits)-1:0];
      if (value[14:10] == 5'h00) begin
        magnitude = value[9:0];
        magnitude = magnitude <<< local_shift;
      end else if (value[14:10] != 5'h1f) begin
        significand = {1'b1, value[9:0]};
        magnitude = significand;
        magnitude = magnitude <<< local_shift;
      end
      fp16_to_segment = value[15] ? -magnitude : magnitude;
    end
  endfunction

  function automatic segment_bin_t value_to_segment(
    input logic [31:0] value,
    input logic format_fp16
  );
    value_to_segment = format_fp16 ? fp16_to_segment(value[15:0])
                                   : fp32_to_segment(value);
  endfunction

  function automatic logic [31:0] input_element(
    input logic [63:0] word,
    input int unsigned index,
    input logic format_fp16
  );
    logic [31:0] selected;
    begin
      selected = '0;
      if (format_fp16) begin
        unique case (index)
          0: selected[15:0] = word[15:0];
          1: selected[15:0] = word[31:16];
          2: selected[15:0] = word[47:32];
          default: selected[15:0] = word[63:48];
        endcase
      end else begin
        unique case (index)
          0: selected = word[31:0];
          1: selected = word[63:32];
          default: selected = '0;
        endcase
      end
      input_element = selected;
    end
  endfunction

  function automatic segment_bins_t collision_forward_update(
    input segment_bins_t original_bins,
    input logic [63:0] word,
    input logic [3:0] active,
    input logic fp16,
    input logic initialize_bins
  );
    logic [3:0][3:0] index;
    logic [3:0] finite;
    segment_bin_t [3:0] updated;
    segment_bin_t previous;
    logic [31:0] value;
    segment_bins_t result_bins;
    index = '0;
    finite = '0;
    updated = '0;
    previous = '0;
    value = '0;
    result_bins = initialize_bins ? '0 : original_bins;
    for (int e = 0; e < 4; e++) begin
      value = input_element(word, e, fp16);
      index[e] = value_segment_index(value, fp16);
      finite[e] = active[e] && !value_is_nan(value, fp16) && !value_is_inf(value, fp16);
      previous = initialize_bins ? '0 : original_bins[index[e]];
      // The latest earlier active element wins on an exponent-bin collision.
      for (int prior = 0; prior < e; prior++)
        if (finite[prior] && index[prior] == index[e]) previous = updated[prior];
      updated[e] = previous + value_to_segment(value, fp16);
    end
    for (int bin = 0; bin < SegmentCount; bin++)
      for (int e = 0; e < 4; e++)
        if (finite[e] && index[e] == 4'(bin)) result_bins[bin] = updated[e];
    return result_bins;
  endfunction

  // Compose two/four adjacent exponent bins into one 64-bit normalization
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
      pair_hi = CompactSegments ? '0 :
        (bin2_ext <<< (2*SegmentBits)) + (bin3_ext <<< (3*SegmentBits));
      carry_ext = carry;
      compose_segment_chunk = pair_lo + pair_hi + carry_ext;
    end
  endfunction

  // Each chunk covers 64 fixed-point bits in either representation.
  function automatic normalization_chunk_t compose_bins_chunk(
    input segment_bins_t chunk_bins,
    input int base,
    input segment_bin_t carry
  );
    if (WideSegments)
      return normalization_chunk_t'(chunk_bins[base]) + normalization_chunk_t'(carry);
    if (CompactSegments)
      return compose_segment_chunk(chunk_bins[base], chunk_bins[base+1], '0, '0, carry);
    return compose_segment_chunk(chunk_bins[base], chunk_bins[base+1],
                                 chunk_bins[base+2], chunk_bins[base+3], carry);
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
    format_fp16_d         = format_fp16_q;
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

    // Reconstruct normalized digits for the exact transport/rounding output.
    // Payload is defined at out_valid; during accumulation bins are not digits.
    // The upper 32 bits share the last bin's otherwise unused high storage,
    // so either segmented mode needs no separate 288-bit root register.
    exact_root = bank_q[0];
    if (ExponentSegmented) begin
      exact_root = '0;
      for (int segment = 0; segment < SegmentCount; segment++)
        exact_root[SegmentBits*segment +: SegmentBits] =
          segment_bin_q[segment][SegmentBits-1:0];
      exact_root[AccWidth-1:256] =
        {(AccWidth-256){segment_bin_q[SegmentCount-1][SegmentBits+31]}};
      exact_root[287:256] = segment_bin_q[SegmentCount-1][SegmentBits+31:SegmentBits];
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
    format_fp16_o          = format_fp16_q;

    if (SharedNormalize && ExponentSegmented &&
        (state_q inside {MERGE_PAIRS, MERGE_ROOT})) begin
      chunk_carry = '0;
      if (state_q == MERGE_ROOT)
        chunk_carry = $signed(segment_bin_q[0][SegmentBinWidth-1:SegmentBits]);
      chunk0 = compose_bins_chunk(segment_bin_q,
        state_q == MERGE_ROOT ? HalfSegments : 0, chunk_carry);
      chunk_carry = chunk0 >>> 64;
      chunk1 = compose_bins_chunk(segment_bin_q,
        (state_q == MERGE_ROOT ? HalfSegments : 0) + DigitsPerChunk, chunk_carry);
    end

    unique case (state_q)
      IDLE: begin
        if (start_i) begin
          state_d               = ACCUMULATE;
          bank_d                = '0;
          segment_bin_d         = '0;
          bank_special_d        = '0;
          bank_index_d          = '0;
          rnd_mode_d            = rnd_mode_i;
          format_fp16_d         = format_fp16_i;
          seed_valid_d          = seed_valid_i;
          seed_raw_d            = seed_i;
          source_seen_d         = 1'b0;
          finite_nonzero_seen_d = seed_valid_i && !DeferSeed &&
            value_is_finite_nonzero(seed_i, format_fp16_i);
          pos_zero_seen_d       = seed_valid_i && !DeferSeed &&
            value_is_zero(seed_i, format_fp16_i) &&
            !value_sign(seed_i, format_fp16_i);
          neg_zero_seen_d       = seed_valid_i && !DeferSeed &&
            value_is_zero(seed_i, format_fp16_i) &&
            value_sign(seed_i, format_fp16_i);
          result_d              = '0;
          status_d              = '0;

          if (seed_valid_i && !DeferSeed)
            bank_special_d[0] = value_special(seed_i, format_fp16_i);
          if (seed_valid_i && !DeferSeed && !value_is_nan(seed_i, format_fp16_i) &&
              !value_is_inf(seed_i, format_fp16_i)) begin
            if (ExponentSegmented)
              segment_bin_d[value_segment_index(seed_i, format_fp16_i)] =
                value_to_segment(seed_i, format_fp16_i);
            else
              bank_d[0] = value_to_fixed(seed_i, format_fp16_i);
          end

          // Start and the first source beat may handshake together.  This
          // avoids a setup bubble at the VMFPU instruction boundary.
          if (in_valid_i) begin
            if (!SharedBeatUpdate) for (int e = 0; e < 4; e++) begin
              element = input_element(data_i, e, format_fp16_i);
              if (active_i[e]) begin
                source_seen_d = 1'b1;
                bank_special_d[0] =
                  merge_special(bank_special_d[0],
                                value_special(element, format_fp16_i));
                finite_nonzero_seen_d |=
                  value_is_finite_nonzero(element, format_fp16_i);
                pos_zero_seen_d |= value_is_zero(element, format_fp16_i) &&
                                   !value_sign(element, format_fp16_i);
                neg_zero_seen_d |= value_is_zero(element, format_fp16_i) &&
                                   value_sign(element, format_fp16_i);
                if (!value_is_nan(element, format_fp16_i) &&
                    !value_is_inf(element, format_fp16_i)) begin
                  if (ExponentSegmented) begin
                    element_segment =
                      value_segment_index(element, format_fp16_i);
                    if (!CollisionForwardUpdate)
                      segment_bin_d[element_segment] +=
                        value_to_segment(element, format_fp16_i);
                  end else begin
                    bank_d[0] += value_to_fixed(element, format_fp16_i);
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
          if (!SharedBeatUpdate) for (int e = 0; e < 4; e++) begin
            element = input_element(data_i, e, format_fp16_q);
            if (active_i[e]) begin
              source_seen_d = 1'b1;
              bank_special_d[bank_index_q] =
                merge_special(bank_special_d[bank_index_q],
                              value_special(element, format_fp16_q));
              finite_nonzero_seen_d |=
                value_is_finite_nonzero(element, format_fp16_q);
              pos_zero_seen_d |= value_is_zero(element, format_fp16_q) &&
                                 !value_sign(element, format_fp16_q);
              neg_zero_seen_d |= value_is_zero(element, format_fp16_q) &&
                                 value_sign(element, format_fp16_q);
              if (!value_is_nan(element, format_fp16_q) &&
                  !value_is_inf(element, format_fp16_q)) begin
                if (ExponentSegmented) begin
                  element_segment =
                    value_segment_index(element, format_fp16_q);
                  if (!CollisionForwardUpdate)
                    segment_bin_d[element_segment] +=
                      value_to_segment(element, format_fp16_q);
                end else begin
                  bank_d[bank_index_q] +=
                    value_to_fixed(element, format_fp16_q);
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
          // Normalize the lower 128 bits into base-2^SegmentBits digits.
          // Overwrite consumed bins in place; bin zero's high bits retain
          // the signed carry into the upper half.
          if (!SharedNormalize) begin
            chunk0 = compose_bins_chunk(segment_bin_q, 0, '0);
            chunk_carry = chunk0 >>> 64;
            chunk1 = compose_bins_chunk(segment_bin_q, DigitsPerChunk, chunk_carry);
          end
          for (int digit = 0; digit < DigitsPerChunk; digit++) begin
            segment_bin_d[digit] = '0;
            segment_bin_d[digit][SegmentBits-1:0] =
              chunk0[SegmentBits*digit +: SegmentBits];
            segment_bin_d[digit+DigitsPerChunk] = '0;
            segment_bin_d[digit+DigitsPerChunk][SegmentBits-1:0] =
              chunk1[SegmentBits*digit +: SegmentBits];
          end
          segment_bin_d[0][SegmentBinWidth-1:SegmentBits] = chunk1[96:64];
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
          // Finish the upper 128 bits. The last bin's high bits hold the
          // final signed carry, which becomes exact_root[287:256].
          if (!SharedNormalize) begin
            chunk_carry = $signed(segment_bin_q[0][SegmentBinWidth-1:SegmentBits]);
            chunk0 = compose_bins_chunk(segment_bin_q, HalfSegments, chunk_carry);
            chunk_carry = chunk0 >>> 64;
            chunk1 = compose_bins_chunk(segment_bin_q,
              HalfSegments + DigitsPerChunk, chunk_carry);
          end
          for (int digit = 0; digit < DigitsPerChunk; digit++) begin
            segment_bin_d[digit+HalfSegments] = '0;
            segment_bin_d[digit+HalfSegments][SegmentBits-1:0] =
              chunk0[SegmentBits*digit +: SegmentBits];
            segment_bin_d[digit+HalfSegments+DigitsPerChunk] = '0;
            segment_bin_d[digit+HalfSegments+DigitsPerChunk][SegmentBits-1:0] =
              chunk1[SegmentBits*digit +: SegmentBits];
          end
          segment_bin_d[SegmentCount-1][SegmentBinWidth-1:SegmentBits] = chunk1[96:64];
        end else begin
          bank_d[0] = bank_q[0] + bank_q[1];
        end
        bank_special_d[0] =
          merge_special(bank_special_q[0], bank_special_q[1]);
        if (SkipUnroundedRoundStage && !EmitRoundedResult) begin
          result_d = '0;
          status_d = '0;
          state_d = HOLD_RESULT;
        end else begin
          state_d = ROUND_RESULT;
        end
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

    // The first beat sees the initialized state (including a non-deferred
    // seed); subsequent beats see the registered state. Preserve the exact
    // per-bank special-value fold order, including qNaN/Inf interactions.
    if (SharedBeatUpdate && in_valid_i &&
        ((state_q == IDLE && start_i) || state_q == ACCUMULATE)) begin
      for (int e = 0; e < 4; e++) begin
        element = input_element(data_i, e, format_fp16_d);
        if (active_i[e]) begin
          source_seen_d = 1'b1;
          bank_special_d[state_q == IDLE ? 2'd0 : bank_index_q] =
            merge_special(bank_special_d[state_q == IDLE ? 2'd0 : bank_index_q],
                          value_special(element, format_fp16_d));
          finite_nonzero_seen_d |= value_is_finite_nonzero(element, format_fp16_d);
          pos_zero_seen_d |= value_is_zero(element, format_fp16_d) &&
                             !value_sign(element, format_fp16_d);
          neg_zero_seen_d |= value_is_zero(element, format_fp16_d) &&
                             value_sign(element, format_fp16_d);
          if (!value_is_nan(element, format_fp16_d) &&
              !value_is_inf(element, format_fp16_d)) begin
            if (ExponentSegmented) begin
              element_segment = value_segment_index(element, format_fp16_d);
              if (!CollisionForwardUpdate)
                segment_bin_d[element_segment] += value_to_segment(element, format_fp16_d);
            end else begin
              bank_d[state_q == IDLE ? 2'd0 : bank_index_q] +=
                value_to_fixed(element, format_fp16_d);
            end
          end
        end
      end
    end
    // Initialization and seed insertion have already populated segment_bin_d.
    // Special-value folding stays in the original order above; this function
    // only replaces the finite integer updates and adds no pipeline stage.
    if (CollisionForwardUpdate && ExponentSegmented && in_valid_i &&
        ((state_q == IDLE && start_i) || state_q == ACCUMULATE))
      if (DirectBinRead && DeferSeed)
        segment_bin_d = collision_forward_update(segment_bin_q, data_i, active_i,
                                                format_fp16_d, state_q == IDLE);
      else
        segment_bin_d = collision_forward_update(segment_bin_d, data_i, active_i,
                                                format_fp16_d, 1'b0);
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q               <= IDLE;
      bank_q                <= '0;
      segment_bin_q         <= '0;
      bank_special_q        <= '0;
      bank_index_q          <= '0;
      rnd_mode_q            <= '0;
      format_fp16_q         <= 1'b0;
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
      format_fp16_q         <= format_fp16_d;
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
    assert (!DeferSeed || !EmitRoundedResult)
      else $fatal(1, "deferred seed requires a global finalizer");
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

  a_fp16_requires_global_finalizer: assert property (
    @(posedge clk_i) disable iff (!rst_ni)
      (start_i && format_fp16_i) |-> !EmitRoundedResult
  ) else $error("binary16 exact reduction requires the global finalizer");

  a_format_is_owned_for_whole_reduction: assert property (
    @(posedge clk_i) disable iff (!rst_ni)
      (state_q != IDLE && !start_i) |=> $stable(format_fp16_q)
  ) else $error("exact reduction format changed while state was live");

  a_fp16_uses_shared_exact_quantum: assert property (
    @(posedge clk_i) disable iff (!rst_ni)
      (out_valid_o && format_fp16_o) |->
        (exact_value_o[124:0] == '0)
  ) else $error("binary16 exact state is not aligned to accumulator bit 125");
`endif

endmodule
