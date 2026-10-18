// SPDX-License-Identifier: SHL-0.51
// Dedicated reduction completion datapath. No requests to lane ALU/FPU.
//
// Reserve a context with cmd_valid/ready before sending per-lane partials.
// Each lane may hand off independently, but exactly once for that instruction.
// Input partials are 64-bit SIMD words in the lane's existing physical layout;
// neutral padding and local seed insertion (if requested) are the producer's
// responsibility. Horizontal folding does not depend on logical element order
// for the integer and min/max operations supported here.
//
// One combinational merge datapath is time-shared across lane merges, horizontal
// folds and seed insertion. Two contexts decouple receiving from completion.
// Result acceptance transfers ownership to the writeback adapter; it is NOT an
// architectural instruction-done event. The adapter must await actual VRF grant.
module reduction_completion_engine import ara_pkg::*; import rvv_pkg::*;
    import ara_rce_pkg::*; #(
  parameter int unsigned NrLanes = 4,
  parameter int unsigned ContextDepth = 2,
  parameter bit EnableExact = RceExactEnable,
  parameter bit UseSharedFp64Add = 1'b0,
  localparam int unsigned PtrWidth = (ContextDepth > 1) ? $clog2(ContextDepth) : 1,
  localparam int unsigned LaneWidth = (NrLanes > 1) ? $clog2(NrLanes) : 1
) (
  input logic clk_i,
  input logic rst_ni,
`ifdef ARA_RED_SHARED_RCE_ADD
  output ordered_add_request_t shared_add_request_o,
  output logic shared_add_valid_o,
  input logic shared_add_ready_i,
  input ordered_add_response_t shared_add_response_i,
  input logic shared_add_response_valid_i,
  output logic shared_add_response_ready_o,
`endif
  input rce_command_t cmd_i,
  input logic cmd_valid_i,
  output logic cmd_ready_o,
  input rce_partial_t [NrLanes-1:0] partial_i,
  input logic [NrLanes-1:0] partial_valid_i,
  output logic [NrLanes-1:0] partial_ready_o,
  input logic [NrVInsn-1:0] seed_lifetime_i,
  input rce_seed_write_t [1:0] external_seed_i,
  input logic [1:0] external_seed_valid_i,
  input rce_seed_write_t [1:0] ordinary_seed_i,
  input logic [1:0] ordinary_seed_valid_i,
  input rce_seed_t seed_i,
  input logic seed_valid_i,
  output logic seed_ready_o,
  output rce_result_t result_o,
  output logic result_valid_o,
  input logic result_ready_i,
  output logic [$clog2(ContextDepth+1)-1:0] occupancy_o,
  input rce_exact_command_t exact_cmd_i,
  input logic exact_cmd_valid_i,
  output logic exact_cmd_ready_o,
  input elen_t [NrLanes-1:0] exact_operand_i,
  input logic [NrLanes-1:0] exact_operand_valid_i,
  output logic [NrLanes-1:0] exact_operand_ready_o,
  input logic exact_seed_ready_i,
  input logic [31:0] exact_seed_data_i,
  output logic exact_local_complete_o,
  output logic [NrLanes-1:0] exact_lane_consumed_o,
  output rce_exact_result_t exact_result_o,
  output logic exact_result_valid_o,
  input logic exact_result_ready_i,
  output rce_exact_events_t exact_events_o
);
  typedef enum logic [2:0] {IDLE, MERGE, FOLD, SEED, HOLD, FP_WAIT} state_e;
  state_e state_q;
  rce_command_t [ContextDepth-1:0] command_q;
  logic [ContextDepth-1:0] valid_q, seed_ready_q;
  logic [ContextDepth-1:0][NrLanes-1:0] received_q, active_q;
  elen_t [ContextDepth-1:0][NrLanes-1:0] partial_q;
  logic [ContextDepth-1:0][NrLanes-1:0][4:0] flags_q;
  logic [PtrWidth-1:0] read_q, write_q, work_ptr;
  // The retirement pointer never changes during speculative completion work.
  // One checkpoint and one completed-result slot share the existing datapath.
  logic background_q, prepared_valid_q;
  elen_t paused_accum_q;
  logic [4:0] paused_flags_q;
  logic paused_fp_seed_done_q;
  rce_result_t prepared_result_q;
  assign work_ptr = background_q ? next_ptr(read_q) : read_q;
  logic [$clog2(ContextDepth+1)-1:0] count_q;
  // Initialization may consume the final accepted partial on this edge.
  // No arithmetic bypass: the initialized accumulator remains registered.
  logic [ContextDepth-1:0][NrLanes-1:0] received_now, active_now;
  elen_t [ContextDepth-1:0] first_partial_now;
  logic [ContextDepth-1:0][NrLanes-1:0][4:0] flags_now;
  logic [LaneWidth-1:0] lane_q;
  logic [1:0] fold_q;
  elen_t accum_q;
  logic [4:0] accrued_q;
  rce_result_t result_q;
  elen_t merge_a, merge_b, merge_result;
  logic [4:0] merge_flags;
  logic command_fire, result_fire;
`ifndef SYNTHESIS
`ifndef ARA_RED_SHARED_RCE_ADD
  initial assert (!UseSharedFp64Add)
    else $fatal(1, "shared FP64 completion requires ARA_RED_SHARED_RCE_ADD ports");
`endif
`endif
  logic [ContextDepth-1:0] cached_seed_ready;
  elen_t [ContextDepth-1:0] cached_seed_data;
  logic fp_sum, fp_seed_q, fp_seed_done_q;
  logic fp_feedback_request, fp_seed_feedback_request;
  logic fp_in_valid, fp_in_ready, fp_out_valid;
  elen_t fp_result;
  fpnew_pkg::status_t fp_status;
  vid_t fp_tag;
  logic word_compute;
  logic sparse_integer, sparse_fp, merge_lane_found;
  logic fp_next_found;
  logic [LaneWidth-1:0] fp_next_lane;
  logic [LaneWidth-1:0] merge_lane;
  // Lane 0 is always retained in the initial accumulator, including any
  // embedded seed. Empty source lanes 1..N-1 contain only neutral padding.
  // Select the next active lane without adding another arithmetic unit.
  always_comb begin
    sparse_integer = RceWordSparseEnable &&
      (command_q[work_ptr].op inside {VREDSUM, VWREDSUM, VWREDSUMU,
        VREDAND, VREDOR, VREDXOR, VREDMIN, VREDMAX, VREDMINU, VREDMAXU});
    sparse_fp = RceFp64SparseEnable && fp_sum;
    merge_lane = lane_q;
    merge_lane_found = !(sparse_integer || sparse_fp);
    for (int lane = 1; lane < NrLanes; lane++)
      if ((sparse_integer || sparse_fp) && !merge_lane_found && lane >= int'(lane_q) &&
          active_q[work_ptr][lane]) begin
        merge_lane = LaneWidth'(lane);
        merge_lane_found = 1'b1;
      end
  end
  // Search strictly above the in-flight lane. The first active lane keeps
  // the original rounded addition order; no inactive value enters the FPU.
  always_comb begin
    fp_next_lane = lane_q + 1'b1;
    fp_next_found = lane_q < NrLanes-1;
    if (RceFp64SparseEnable) begin
      fp_next_found = 1'b0;
      for (int lane = 1; lane < NrLanes; lane++)
        if (!fp_next_found && lane > int'(lane_q) && active_q[work_ptr][lane]) begin
          fp_next_lane = LaneWidth'(lane);
          fp_next_found = 1'b1;
        end
    end
  end
  rce_seed_write_t [3:0] captured_seed;
  logic [3:0] captured_seed_valid;
  assign captured_seed = {external_seed_i, ordinary_seed_i};
  assign captured_seed_valid = {external_seed_valid_i & {2{RceExternalSeedEnable}},
                                ordinary_seed_valid_i & {2{RceOrdinarySeedEnable}}};
  logic committed_seed_valid, command_seed_valid;
  rce_seed_t committed_seed;
  elen_t command_seed_data;

  function automatic logic seed_matches(rce_command_t cmd, rce_seed_t seed);
    return cmd.seed_mode == RCE_SEED_WAIT && cmd.seed_producer == seed.producer &&
           cmd.seed_register == seed.vd && cmd.seed_version == seed.version;
  endfunction

  // Only actual result acceptance (the top-level VRF grant) can publish a seed.
  // The small per-ID cache bridges retirement before a consumer command arrives.
  // A new command invalidates the previous lifetime of that ID before reuse.
  assign committed_seed_valid = result_fire && result_q.write_enable &&
    ((RceIntLateSeedEnable && !result_q.is_fp) || RceFpLateSeedEnable);
  assign committed_seed = '{producer: result_q.id, vd: result_q.vd,
                            version: result_q.version, data: result_q.data};
  if (RceIntLateSeedEnable || RceFpLateSeedEnable || RceOrdinarySeedEnable) begin : gen_word_seed_cache
    logic [NrVInsn-1:0] valid_q;
    logic [NrVInsn-1:0][4:0] vd_q;
    vreg_version_t [NrVInsn-1:0] version_q;
    elen_t [NrVInsn-1:0] data_q;
    logic [NrVInsn-1:0][7:0] bytes_q;
    logic [NrVInsn-1:0] live_q;
    function automatic logic covers(logic [7:0] bytes, vew_e eew);
      logic [7:0] needed;
      needed = 8'((9'd1 << (1 << int'(eew))) - 1);
      return (bytes & needed) == needed;
    endfunction
    always_comb begin
      command_seed_valid = valid_q[cmd_i.seed_producer] &&
        vd_q[cmd_i.seed_producer] == cmd_i.seed_register &&
        version_q[cmd_i.seed_producer] == cmd_i.seed_version &&
        covers(bytes_q[cmd_i.seed_producer],cmd_i.eew);
      command_seed_data = data_q[cmd_i.seed_producer];
      for (int slot=0; slot<ContextDepth; slot++) begin
        cached_seed_ready[slot] = valid_q[command_q[slot].seed_producer] &&
          vd_q[command_q[slot].seed_producer] == command_q[slot].seed_register &&
          version_q[command_q[slot].seed_producer] == command_q[slot].seed_version &&
          covers(bytes_q[command_q[slot].seed_producer], command_q[slot].eew);
        cached_seed_data[slot] = data_q[command_q[slot].seed_producer];
      end
      if (committed_seed_valid && seed_matches(cmd_i, committed_seed) &&
          covers(result_q.be,cmd_i.eew)) begin
        command_seed_valid = 1'b1;
        command_seed_data = committed_seed.data;
      end
    end
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        valid_q <= '0; vd_q <= '0; version_q <= '0; data_q <= '0; bytes_q <= '0; live_q <= '0;
      end else begin
        live_q <= seed_lifetime_i;
        for (int id=0; id<NrVInsn; id++)
          if (RceOrdinarySeedEnable && seed_lifetime_i[id] && !live_q[id])
            valid_q[id] <= 1'b0;
        if (command_fire) valid_q[cmd_i.id] <= 1'b0;
        if (committed_seed_valid) begin
          valid_q[committed_seed.producer] <= 1'b1;
          vd_q[committed_seed.producer] <= committed_seed.vd;
          version_q[committed_seed.producer] <= committed_seed.version;
          data_q[committed_seed.producer] <= committed_seed.data;
          bytes_q[committed_seed.producer] <= result_q.be;
        end
        // Both write ports capture independently; a simultaneous ALU/FPU
        // completion must not be lost behind a single-broadcast arbiter.
        for (int port=0; port<4; port++) if (captured_seed_valid[port]) begin
          valid_q[captured_seed[port].seed.producer] <= 1'b1;
          vd_q[captured_seed[port].seed.producer] <= captured_seed[port].seed.vd;
          version_q[captured_seed[port].seed.producer] <= captured_seed[port].seed.version;
          data_q[captured_seed[port].seed.producer] <= captured_seed[port].seed.data;
          bytes_q[captured_seed[port].seed.producer] <= captured_seed[port].be;
        end
      end
    end
  end else begin : gen_no_integer_seed_cache
    assign command_seed_valid = 1'b0;
    assign command_seed_data = '0;
    assign cached_seed_ready = '0;
    assign cached_seed_data = '0;
  end

  assign fp_sum = rce_fp64_sum(command_q[work_ptr].op, command_q[work_ptr].eew);
  assign word_compute = !fp_sum &&
    ((state_q inside {MERGE, FOLD}) ||
     (state_q == SEED && seed_ready_q[work_ptr] && (|active_q[work_ptr])));
  // Return-to-input forwarding preserves the fixed ascending lane order.
  // The returning operation is consumed even if the next input is stalled;
  // in that case its result is saved and normal MERGE retries the next lane.
  assign fp_feedback_request = RceFp64FeedbackEnable && fp_sum &&
    state_q == FP_WAIT && fp_out_valid && !fp_seed_q &&
    fp_next_found && active_q[work_ptr][fp_next_lane];
  // Feed the final lane sum directly into the seed add when its version is
  // already bound. A blocked input falls back to SEED with the saved result.
  assign fp_seed_feedback_request = RceFp64SeedFeedbackEnable && fp_sum &&
    state_q == FP_WAIT && fp_out_valid && !fp_seed_q &&
    !fp_next_found && seed_ready_q[work_ptr] &&
    command_q[work_ptr].seed_mode != RCE_SEED_EMBEDDED && !fp_seed_done_q;
  assign fp_in_valid = fp_feedback_request || fp_seed_feedback_request || (fp_sum &&
    ((state_q == MERGE && merge_lane_found && active_q[work_ptr][merge_lane]) ||
     (state_q == SEED && seed_ready_q[work_ptr] && (|active_q[work_ptr]) &&
      command_q[work_ptr].seed_mode != RCE_SEED_EMBEDDED && !fp_seed_done_q)));

`ifdef ARA_RED_SHARED_RCE_ADD
  if (!RceFp64SumEnable || !UseSharedFp64Add) begin : gen_shared_unused
    assign shared_add_request_o = '0;
    assign shared_add_valid_o = 1'b0;
    assign shared_add_response_ready_o = 1'b0;
  end
`endif
  if (RceFp64SumEnable) begin : gen_fp64_add
    elen_t operand_a, operand_b;
    fpnew_pkg::roundmode_e rounding_mode;
    // Isolate by operation class. Clearing on every invalid feedback cycle
    // adds zero/data transitions between dependent FP64 adds; keeping the
    // active FP64 context connected avoids that cost without holding registers.
    assign operand_a = (fp_feedback_request || fp_seed_feedback_request) ? fp_result :
      (!RceOperandIsolationEnable || fp_sum ? merge_a : '0);
    assign operand_b = fp_seed_feedback_request ? command_q[work_ptr].seed :
      fp_feedback_request ? partial_q[work_ptr][fp_next_lane] :
      (!RceOperandIsolationEnable || fp_sum ? merge_b : '0);
    assign rounding_mode = !RceOperandIsolationEnable || fp_sum ?
      command_q[work_ptr].fp_rm : fpnew_pkg::RNE;
    // Fixed ADD and a constant multiplicand specialize the existing arithmetic
    // core to addition. No lane FPU, multiplier operation, divider or SIMD wrapper.
    // AFTER keeps op_i constant through the arithmetic cone; two output stages
    // isolate the result handshake. Physical pruning/timing still need synthesis.
`ifdef ARA_RED_SHARED_RCE_ADD
    if (UseSharedFp64Add) begin : gen_shared
      assign shared_add_request_o = '{
        operands: {operand_b, operand_a, 64'h3ff0000000000000},
        rm: rounding_mode, src_fmt: fpnew_pkg::FP64, dst_fmt: fpnew_pkg::FP64,
        int_fmt: fpnew_pkg::INT64, tag: 9'(command_q[work_ptr].id), mask: 1'b1};
      assign shared_add_valid_o = fp_in_valid;
      assign fp_in_ready = shared_add_ready_i;
      assign fp_result = shared_add_response_i.result;
      assign fp_status = shared_add_response_i.status;
      assign fp_tag = vid_t'(shared_add_response_i.tag);
      assign fp_out_valid = shared_add_response_valid_i;
      assign shared_add_response_ready_o = state_q == FP_WAIT;
`ifndef SYNTHESIS
      a_shared_completion_tag: assert property (@(posedge clk_i) disable iff (!rst_ni)
        fp_out_valid |-> shared_add_response_i.tag == 9'(command_q[work_ptr].id))
        else $error("shared RCE result has incorrect instruction owner");
`endif
    end else begin : gen_private
`endif
    fpnew_fma #(.FpFormat(fpnew_pkg::FP64), .NumPipeRegs(2),
      .PipeConfig(fpnew_pkg::AFTER), .TagType(vid_t), .AuxType(logic)) i_add (
      .clk_i, .rst_ni, .operands_i({operand_b, operand_a, 64'h3ff0000000000000}),
      .is_boxed_i(3'b111), .rnd_mode_i(rounding_mode),
      .op_i(fpnew_pkg::ADD), .op_mod_i(1'b0), .tag_i(command_q[work_ptr].id),
      .mask_i(1'b1), .aux_i(1'b0), .in_valid_i(fp_in_valid), .in_ready_o(fp_in_ready),
      .flush_i(1'b0), .result_o(fp_result), .status_o(fp_status), .extension_bit_o(),
      .tag_o(fp_tag), .mask_o(), .aux_o(), .out_valid_o(fp_out_valid),
      .out_ready_i(state_q == FP_WAIT), .busy_o()
    );
`ifdef ARA_RED_SHARED_RCE_ADD
    end
`endif
  end else begin : gen_no_fp64_add
    assign fp_in_ready = 1'b0;
    assign fp_out_valid = 1'b0;
    assign fp_result = '0;
    assign fp_status = '0;
    assign fp_tag = '0;
  end

  function automatic logic [PtrWidth-1:0] next_ptr(logic [PtrWidth-1:0] p);
    return p == ContextDepth-1 ? '0 : p + 1'b1;
  endfunction

  // A scalar minNum/maxNum operation. Integer bit comparison of magnitudes
  // implements finite/inf ordering; NaNs and the signed-zero tie are explicit.
  // Arguments occupy the low 'width' bits, with all other bits zero.
  function automatic logic [64:0] fp_extreme(
    logic maximum, int width, elen_t a, elen_t b,
    logic unsigned_less, logic bits_equal
  );
    logic na, nb, sa, sb, za, zb, invalid, a_less;
    elen_t exponent, fraction, quiet, canonical, magnitude_mask;
    exponent = '0; fraction = '0; quiet = '0;
    case (width)
      16: begin exponent = 64'h7c00; fraction = 64'h3ff; quiet = 64'h200; end
      32: begin exponent = 64'h7f800000; fraction = 64'h7fffff; quiet = 64'h400000; end
      64: begin exponent = 64'h7ff0000000000000;
                fraction = 64'hfffffffffffff; quiet = 64'h8000000000000; end
      default: ;
    endcase
    magnitude_mask = exponent | fraction;
    canonical = exponent | quiet;
    na = ((a & exponent) == exponent) && ((a & fraction) != 0);
    nb = ((b & exponent) == exponent) && ((b & fraction) != 0);
    invalid = (na && !(|(a & quiet))) || (nb && !(|(b & quiet)));
    sa = a[width-1]; sb = b[width-1];
    za = (a & magnitude_mask) == 0; zb = (b & magnitude_mask) == 0;
    a_less = (sa != sb) ? sa : (sa ? !unsigned_less && !bits_equal : unsigned_less);
    if (na && nb) return {invalid, canonical};
    if (na) return {invalid, b};
    if (nb) return {invalid, a};
    if (za && zb)
      return {invalid, (elen_t'(maximum ? sa & sb : sa | sb) << (width-1))};
    return {invalid, ((maximum ? !a_less : a_less) ? a : b)};
  endfunction

  function automatic elen_t integer_merge(
    ara_op_e op, int width, elen_t a, elen_t b
  );
    logic signed_compare, a_less;
    signed_compare = op inside {VREDMIN, VREDMAX};
    a_less = signed_compare && (a[width-1] != b[width-1]) ?
             a[width-1] : a < b;
    case (op)
      VREDSUM, VWREDSUM, VWREDSUMU: return a + b;
      VREDAND: return a & b;
      VREDOR: return a | b;
      VREDXOR: return a ^ b;
      VREDMIN, VREDMINU: return a_less ? a : b;
      VREDMAX, VREDMAXU: return a_less ? b : a;
      default: return '0;
    endcase
  endfunction

  // Retained organization for an independent, cycle-identical structural ablation.
  `define RCE_MERGE_WIDTH(W) \
    for (int e = 0; e < 64/W; e++) begin \
      if (command_q[work_ptr].op inside {VFREDMIN, VFREDMAX}) begin \
        automatic logic [64:0] fp; \
        fp = fp_extreme(command_q[work_ptr].op == VFREDMAX, W, \
          elen_t'(merge_a[W*e +: W]), elen_t'(merge_b[W*e +: W]), \
          merge_a[W*e +: W] < merge_b[W*e +: W], \
          merge_a[W*e +: W] == merge_b[W*e +: W]); \
        merge_result[W*e +: W] = fp[W-1:0]; \
        merge_flags[4] |= fp[64]; \
      end else merge_result[W*e +: W] = W'(integer_merge(command_q[work_ptr].op, W, \
          elen_t'(merge_a[W*e +: W]), elen_t'(merge_b[W*e +: W]))); \
    end

  always_comb begin
    merge_a = accum_q;
    merge_b = partial_q[work_ptr][merge_lane];
    if (state_q == FOLD) begin
      case (fold_q)
        0: merge_b = accum_q >> 32;
        1: merge_b = accum_q >> 16;
        default: merge_b = accum_q >> 8;
      endcase
    end else if (state_q == SEED) begin
      automatic elen_t mask;
      mask = 64'hffffffffffffffff >> (64 - (8 << int'(command_q[work_ptr].eew)));
      merge_a = accum_q & mask;
      merge_b = command_q[work_ptr].seed & mask;
    end
    if (RceOperandIsolationEnable && !word_compute && !fp_sum) begin
      merge_a = '0;
      merge_b = '0;
    end
  end

  if (!RceCompactWordEnable) begin : gen_legacy_word
  always_comb begin
    merge_result = '0;
    merge_flags = '0;
    case (command_q[work_ptr].eew)
      EW8:  begin `RCE_MERGE_WIDTH(8) end
      EW16: begin `RCE_MERGE_WIDTH(16) end
      EW32: begin `RCE_MERGE_WIDTH(32) end
      EW64: begin `RCE_MERGE_WIDTH(64) end
      default: ;
    endcase
  end
  end else begin : gen_compact_word
    // One adder for every SEW. A zero guard bit absorbs carry at an element
    // boundary; a one guard propagates carry between bytes of the same element.
    // Guard positions are discarded from the 72-bit sum, leaving packed 64 bits.
    logic [7:0] guard_bits;
    logic [71:0] sum_a, sum_b, sum_extended;
    elen_t add_a, add_b, packed_sum, compare_a, compare_b;
    logic [3:0][7:0] less, equal;
    logic add_enabled, compare_enabled;
    assign add_enabled = command_q[work_ptr].op inside {VREDSUM, VWREDSUM, VWREDSUMU};
    assign compare_enabled = command_q[work_ptr].op inside
      {VREDMIN, VREDMINU, VREDMAX, VREDMAXU, VFREDMIN, VFREDMAX};
    assign add_a = !RceOperandIsolationEnable || (word_compute && add_enabled) ? merge_a : '0;
    assign add_b = !RceOperandIsolationEnable || (word_compute && add_enabled) ? merge_b : '0;
    assign compare_a = !RceOperandIsolationEnable || (word_compute && compare_enabled) ? merge_a : '0;
    assign compare_b = !RceOperandIsolationEnable || (word_compute && compare_enabled) ? merge_b : '0;
    always_comb begin
      case (command_q[work_ptr].eew)
        EW8: guard_bits = 8'h00;
        EW16: guard_bits = 8'h55;
        EW32: guard_bits = 8'h77;
        default: guard_bits = 8'h7f;
      endcase
      if (RceOperandIsolationEnable && !(word_compute && add_enabled)) guard_bits = '0;
    end
    assign sum_extended = sum_a + sum_b;
    for (genvar b = 0; b < 8; b++) begin : gen_byte
      assign sum_a[9*b +: 9] = {guard_bits[b], add_a[8*b +: 8]};
      assign sum_b[9*b +: 9] = {1'b0, add_b[8*b +: 8]};
      assign packed_sum[8*b +: 8] = sum_extended[9*b +: 8];
      assign less[0][b] = compare_a[8*b +: 8] < compare_b[8*b +: 8];
      assign equal[0][b] = compare_a[8*b +: 8] == compare_b[8*b +: 8];
    end
    // Balanced comparison tree shares byte comparisons across all formats,
    // integer signed/unsigned extremes and floating-point min/max ordering.
    for (genvar level = 1; level < 4; level++) begin : gen_compare_level
      for (genvar b = 0; b < 8; b++) begin : gen_group
        if ((b % (1 << level)) == 0) begin : gen_head
          localparam int High = b + (1 << (level-1));
          assign less[level][b] = less[level-1][High] ||
            (equal[level-1][High] && less[level-1][b]);
          assign equal[level][b] = equal[level-1][High] && equal[level-1][b];
        end else begin : gen_unused
          assign less[level][b] = 1'b0;
          assign equal[level][b] = 1'b0;
        end
      end
    end
    `define RCE_EXTREME_WIDTH(W, L) \
      for (int e = 0; e < 64/W; e++) begin \
        if (command_q[work_ptr].op inside {VFREDMIN, VFREDMAX}) begin \
          automatic logic [64:0] fp; \
          fp = fp_extreme(command_q[work_ptr].op == VFREDMAX, W, \
            elen_t'(merge_a[W*e +: W]), elen_t'(merge_b[W*e +: W]), \
            less[L][W/8*e], equal[L][W/8*e]); \
          merge_result[W*e +: W] = fp[W-1:0]; \
          merge_flags[4] |= fp[64]; \
        end else begin \
          automatic logic a_less, select_a; \
          a_less = (command_q[work_ptr].op inside {VREDMIN, VREDMAX}) && \
            (merge_a[W*e+W-1] != merge_b[W*e+W-1]) ? \
            merge_a[W*e+W-1] : less[L][W/8*e]; \
          select_a = command_q[work_ptr].op inside {VREDMAX, VREDMAXU} ? !a_less : a_less; \
          merge_result[W*e +: W] = select_a ? merge_a[W*e +: W] : merge_b[W*e +: W]; \
        end \
      end
    always_comb begin
      merge_result = '0;
      merge_flags = '0;
      case (command_q[work_ptr].op)
        VREDSUM, VWREDSUM, VWREDSUMU: merge_result = packed_sum;
        VREDAND: merge_result = merge_a & merge_b;
        VREDOR: merge_result = merge_a | merge_b;
        VREDXOR: merge_result = merge_a ^ merge_b;
        VREDMIN, VREDMINU, VREDMAX, VREDMAXU, VFREDMIN, VFREDMAX:
          case (command_q[work_ptr].eew)
            EW8: begin `RCE_EXTREME_WIDTH(8, 0) end
            EW16: begin `RCE_EXTREME_WIDTH(16, 1) end
            EW32: begin `RCE_EXTREME_WIDTH(32, 2) end
            EW64: begin `RCE_EXTREME_WIDTH(64, 3) end
            default: ;
          endcase
        default: ;
      endcase
    end
    `undef RCE_EXTREME_WIDTH
  end
  `undef RCE_MERGE_WIDTH

  assign occupancy_o = count_q;
  assign cmd_ready_o = ((count_q < ContextDepth) ||
    (RceWordTurnaroundEnable && result_fire)) && rce_word_eligible(cmd_i.op, cmd_i.eew);
  assign command_fire = cmd_valid_i && cmd_ready_o;
  assign result_valid_o = state_q == HOLD && !background_q;
  assign result_o = result_q;
  assign result_fire = result_valid_o && result_ready_i;

  always_comb begin
    partial_ready_o = '0;
    seed_ready_o = 1'b0;
    for (int slot = 0; slot < ContextDepth; slot++) begin
      for (int lane = 0; lane < NrLanes; lane++)
        if (valid_q[slot] && !command_q[slot].vl_zero &&
            command_q[slot].id == partial_i[lane].id && !received_q[slot][lane])
          partial_ready_o[lane] = 1'b1;
      if (valid_q[slot] && !seed_ready_q[slot] &&
          command_q[slot].seed_producer == seed_i.producer &&
          command_q[slot].seed_register == seed_i.vd &&
          command_q[slot].seed_version == seed_i.version)
        seed_ready_o = 1'b1;
    end
  end

  always_comb begin
    received_now = received_q;
    active_now = active_q;
    flags_now = flags_q;
    for (int slot = 0; slot < ContextDepth; slot++) begin
      first_partial_now[slot] = partial_q[slot][0];
      if (RceWordTurnaroundEnable)
        for (int lane = 0; lane < NrLanes; lane++) begin
          if (valid_q[slot] && command_q[slot].id == partial_i[lane].id &&
              partial_valid_i[lane] && partial_ready_o[lane]) begin
            received_now[slot][lane] = 1'b1;
            active_now[slot][lane] = partial_i[lane].source_active;
            flags_now[slot][lane] = partial_i[lane].fflags;
            if (lane == 0) first_partial_now[slot] = partial_i[lane].data;
          end
        end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= IDLE;
      command_q <= '0; valid_q <= '0; seed_ready_q <= '0;
      received_q <= '0; active_q <= '0; partial_q <= '0; flags_q <= '0;
      read_q <= '0; write_q <= '0; count_q <= '0;
      lane_q <= '0; fold_q <= '0; accum_q <= '0; accrued_q <= '0;
      result_q <= '0;
      background_q <= 1'b0; prepared_valid_q <= 1'b0;
      paused_accum_q <= '0; paused_flags_q <= '0;
      paused_fp_seed_done_q <= 1'b0; prepared_result_q <= '0;
      fp_seed_q <= 1'b0;
      fp_seed_done_q <= 1'b0;
    end else begin
      case ({command_fire, result_fire})
        2'b10: count_q <= count_q + 1'b1;
        2'b01: count_q <= count_q - 1'b1;
        default: ;
      endcase
      if (result_fire) begin
        valid_q[read_q] <= 1'b0;
        received_q[read_q] <= '0;
      end
      if (command_fire) begin
        command_q[write_q] <= cmd_i;
        valid_q[write_q] <= 1'b1;
        received_q[write_q] <= '0;
        active_q[write_q] <= '0;
        flags_q[write_q] <= '0;
        seed_ready_q[write_q] <= cmd_i.seed_mode != RCE_SEED_WAIT;
        if (cmd_i.seed_mode == RCE_SEED_WAIT && command_seed_valid) begin
          command_q[write_q].seed <= command_seed_data;
          seed_ready_q[write_q] <= 1'b1;
        end
        write_q <= next_ptr(write_q);
      end
      for (int slot = 0; slot < ContextDepth; slot++) begin
        for (int lane = 0; lane < NrLanes; lane++) begin
          if (valid_q[slot] && command_q[slot].id == partial_i[lane].id &&
              partial_valid_i[lane] && partial_ready_o[lane]) begin
            partial_q[slot][lane] <= partial_i[lane].data;
            received_q[slot][lane] <= 1'b1;
            active_q[slot][lane] <= partial_i[lane].source_active;
            flags_q[slot][lane] <= partial_i[lane].fflags;
            if (partial_i[lane].seed_valid &&
                command_q[slot].seed_mode != RCE_SEED_WAIT) begin
              command_q[slot].seed <= partial_i[lane].seed;
            end
          end
        end
        if (valid_q[slot] && !seed_ready_q[slot] && seed_valid_i &&
            command_q[slot].seed_producer == seed_i.producer &&
            command_q[slot].seed_register == seed_i.vd &&
            command_q[slot].seed_version == seed_i.version) begin
          command_q[slot].seed <= seed_i.data;
          seed_ready_q[slot] <= 1'b1;
        end
        if (valid_q[slot] && !seed_ready_q[slot] && cached_seed_ready[slot]) begin
          command_q[slot].seed <= cached_seed_data[slot];
          seed_ready_q[slot] <= 1'b1;
        end
        if (valid_q[slot] && !seed_ready_q[slot] && committed_seed_valid &&
            seed_matches(command_q[slot], committed_seed) &&
            (result_q.be & 8'((9'd1 << (1 << int'(command_q[slot].eew))) - 1)) ==
              8'((9'd1 << (1 << int'(command_q[slot].eew))) - 1)) begin
          command_q[slot].seed <= committed_seed.data;
          seed_ready_q[slot] <= 1'b1;
        end
      end
      case (state_q)
        IDLE: if (valid_q[read_q]) begin
          if (command_q[work_ptr].vl_zero) begin
            result_q <= '{id: command_q[work_ptr].id, vd: command_q[work_ptr].vd,
              version: command_q[work_ptr].vd_version,
              is_fp: (command_q[work_ptr].op inside {VFREDMIN, VFREDMAX}) || fp_sum, default: '0};
            state_q <= HOLD;
          end else if (&received_now[read_q]) begin
            automatic logic [4:0] flags;
            flags = '0;
            for (int lane = 0; lane < NrLanes; lane++) flags |= flags_now[work_ptr][lane];
            accrued_q <= flags;
            accum_q <= first_partial_now[work_ptr];
            lane_q <= LaneWidth'(1);
            fold_q <= '0;
            fp_seed_done_q <= 1'b0;
            if ((fp_sum || RceEmptyBypassEnable) && !(|active_now[work_ptr]))
              state_q <= SEED;
            else if (NrLanes > 1) state_q <= MERGE;
            else state_q <= command_q[work_ptr].eew == EW64 ? SEED : FOLD;
          end
        end
        MERGE: begin
          if (fp_sum) begin
            if (sparse_fp && !merge_lane_found) begin
              state_q <= SEED;
            end else if (!active_q[work_ptr][merge_lane]) begin
              // Inactive subtrees may copy the other operand without adding zero.
              if (lane_q == NrLanes-1) state_q <= SEED;
              else lane_q <= lane_q + 1'b1;
            end else if (fp_in_valid && fp_in_ready) begin
              lane_q <= merge_lane;
              fp_seed_q <= 1'b0;
              state_q <= FP_WAIT;
            end
          end else begin
          if (merge_lane_found) begin
            accum_q <= merge_result;
            accrued_q <= accrued_q | merge_flags;
          end
          if (!merge_lane_found || merge_lane == NrLanes-1) begin
            fold_q <= '0;
            state_q <= command_q[work_ptr].eew == EW64 ? SEED : FOLD;
          end else lane_q <= merge_lane + 1'b1;
          end
        end
        FP_WAIT: if (fp_out_valid) begin
          accum_q <= fp_result;
          accrued_q <= accrued_q | fp_status;
          if (fp_seed_q) begin
            fp_seed_done_q <= 1'b1;
            state_q <= SEED;
          end else if (!fp_next_found) begin
            if (fp_seed_feedback_request && fp_in_ready) begin
              fp_seed_q <= 1'b1;
              state_q <= FP_WAIT;
            end else state_q <= SEED;
          end
          else begin
            lane_q <= fp_next_lane;
            state_q <= fp_feedback_request && fp_in_ready ? FP_WAIT : MERGE;
          end
        end
        FOLD: begin
          accum_q <= merge_result;
          accrued_q <= accrued_q | merge_flags;
          fold_q <= fold_q + 1'b1;
          if (fold_q == (2 - int'(command_q[work_ptr].eew))) state_q <= SEED;
        end
        SEED: if (seed_ready_q[work_ptr]) begin
          automatic logic empty_source, embedded;
          automatic elen_t scalar_mask;
          empty_source = !(|active_q[work_ptr]);
          embedded = command_q[work_ptr].seed_mode == RCE_SEED_EMBEDDED;
          scalar_mask = 64'hffffffffffffffff >> (64 - (8 << int'(command_q[work_ptr].eew)));
          if (fp_sum && !empty_source && !embedded && !fp_seed_done_q) begin
            if (fp_in_valid && fp_in_ready) begin
              fp_seed_q <= 1'b1;
              state_q <= FP_WAIT;
            end
          end else begin
          result_q <= '{id: command_q[work_ptr].id, vd: command_q[work_ptr].vd,
            version: command_q[work_ptr].vd_version,
            data: (empty_source ? command_q[work_ptr].seed :
                    ((embedded || fp_sum) ? accum_q : merge_result)) & scalar_mask,
            be: 8'((9'd1 << (1 << int'(command_q[work_ptr].eew))) - 1'b1),
            // In embedded min/max mode the lane may have quieted the seed
            // before knowing GLOBAL source activity. Its sNaN NV is deferred
            // here, and must survive even if only another lane was active.
            fflags: empty_source ? 5'b0 : accrued_q | merge_flags,
            write_enable: 1'b1,
            is_fp: (command_q[work_ptr].op inside {VFREDMIN, VFREDMAX}) || fp_sum};
          state_q <= HOLD;
          end
        end else if (RceSeedLookaheadEnable && !background_q && !prepared_valid_q &&
                     count_q > 1 && valid_q[next_ptr(read_q)] &&
                     (&received_q[next_ptr(read_q)]) && seed_ready_q[next_ptr(read_q)] &&
                     !command_q[next_ptr(read_q)].vl_zero) begin
          automatic logic [PtrWidth-1:0] slot = next_ptr(read_q);
          automatic logic [4:0] flags = '0;
          for (int lane = 0; lane < NrLanes; lane++) flags |= flags_q[slot][lane];
          paused_accum_q <= accum_q;
          paused_flags_q <= accrued_q;
          paused_fp_seed_done_q <= fp_seed_done_q;
          background_q <= 1'b1;
          accum_q <= first_partial_now[slot];
          accrued_q <= flags;
          lane_q <= LaneWidth'(1);
          fold_q <= '0;
          fp_seed_done_q <= 1'b0;
          if ((RceEmptyBypassEnable || rce_fp64_sum(command_q[slot].op, command_q[slot].eew)) &&
              !(|active_q[slot])) state_q <= SEED;
          else if (NrLanes > 1) state_q <= MERGE;
          else state_q <= command_q[slot].eew == EW64 ? SEED : FOLD;
        end
        HOLD: if (background_q) begin
          prepared_result_q <= result_q;
          prepared_valid_q <= 1'b1;
          background_q <= 1'b0;
          accum_q <= paused_accum_q;
          accrued_q <= paused_flags_q;
          fp_seed_done_q <= paused_fp_seed_done_q;
          state_q <= SEED;
        end else if (result_fire) begin
          read_q <= next_ptr(read_q);
          state_q <= IDLE;
          // Only an already resident successor can bypass initialization.
          // A same-slot refill has no received partials yet and must use IDLE.
          if (prepared_valid_q) begin
            result_q <= prepared_result_q;
            prepared_valid_q <= 1'b0;
            state_q <= HOLD;
          end else if (RceWordTurnaroundEnable && count_q > 1 &&
              valid_q[next_ptr(read_q)] && (&received_now[next_ptr(read_q)]) &&
              !command_q[next_ptr(read_q)].vl_zero) begin
            automatic logic [PtrWidth-1:0] next_slot = next_ptr(read_q);
            automatic logic [4:0] flags = '0;
            for (int lane = 0; lane < NrLanes; lane++) flags |= flags_now[next_slot][lane];
            accrued_q <= flags;
            accum_q <= first_partial_now[next_slot];
            lane_q <= LaneWidth'(1);
            fold_q <= '0;
            fp_seed_done_q <= 1'b0;
            if ((RceEmptyBypassEnable ||
                 rce_fp64_sum(command_q[next_slot].op, command_q[next_slot].eew)) &&
                !(|active_now[next_slot])) state_q <= SEED;
            else if (NrLanes > 1) state_q <= MERGE;
            else state_q <= command_q[next_slot].eew == EW64 ? SEED : FOLD;
          end
        end
        default: state_q <= IDLE;
      endcase
    end
  end

`ifndef SYNTHESIS
  initial begin
    assert (NrLanes >= 1 && ContextDepth >= 1 && ContextDepth <= NrVInsn)
      else $fatal(1, "Invalid RCE configuration");
  end
  a_stable_result: assert property (@(posedge clk_i) disable iff (!rst_ni)
    result_valid_o && !result_ready_i |=> result_valid_o && $stable(result_o));
  a_bounded_contexts: assert property (@(posedge clk_i) disable iff (!rst_ni)
    count_q <= ContextDepth);
  a_background_owner: assert property (@(posedge clk_i) disable iff (!rst_ni)
    background_q |-> count_q > 1 && !result_valid_o && !prepared_valid_q);
  a_prepared_owner: assert property (@(posedge clk_i) disable iff (!rst_ni)
    prepared_valid_q |-> count_q > 1 &&
      prepared_result_q.id == command_q[next_ptr(read_q)].id);
  a_fp_response_owner: assert property (@(posedge clk_i) disable iff (!rst_ni)
    fp_out_valid |-> state_q == FP_WAIT && fp_sum && fp_tag == command_q[work_ptr].id);
  for (genvar slot = 0; slot < ContextDepth; slot++) begin
    a_unique_owner: assert property (@(posedge clk_i) disable iff (!rst_ni)
      command_fire |-> !(valid_q[slot] && command_q[slot].id == cmd_i.id));
  end
  for (genvar lane = 1; lane < NrLanes; lane++) begin
    a_seed_only_from_lane_zero: assert property (@(posedge clk_i) disable iff (!rst_ni)
      partial_valid_i[lane] && partial_ready_o[lane] |-> !partial_i[lane].seed_valid);
  end
`endif

  // Sparse exact backend. One context matches the existing serialized SLDU
  // transport; it does not consume or duplicate the packed-word contexts.
  // Local state, carry propagation and rounding now belong to this RCE.
  if (EnableExact) begin : gen_exact
    typedef enum logic [2:0] {EXACT_IDLE, EXACT_RECEIVE, EXACT_RESULT, EXACT_SEED_WAIT, EXACT_SEED_ADD} exact_state_e;
    exact_state_e state_q, state_d;
    rce_exact_command_t owner_q;
    rce_exact_result_t completed_q, raw_result;
    logic completed_valid_q, completed_space, completed_push;
    assign completed_space = !completed_valid_q || exact_result_ready_i;
    // Use the existing completion slot as a timing boundary. A finalized
    // result is always captured before it reaches VRF / forwarding consumers.
    // Simultaneous pop/push replaces an old result without losing ownership.
    assign completed_push = RceExactDecoupleEnable && state_q == EXACT_RESULT &&
      completed_space;
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        completed_q <= '0;
        completed_valid_q <= 1'b0;
      end else if (RceExactDecoupleEnable) begin
        if (exact_result_valid_o && exact_result_ready_i) completed_valid_q <= 1'b0;
        if (completed_push) begin
          completed_q <= raw_result;
          completed_valid_q <= 1'b1;
        end
      end
    end
    logic exact_late_seed_ready;
  logic [2:0]   exact_packet_beat_d, exact_packet_beat_q;
  logic [2:0]   exact_limb_count_d, exact_limb_count_q;
  logic [NrLanes-1:0][2:0] exact_lane_limb_count_d, exact_lane_limb_count_q;
  logic [NrLanes-1:0][2:0] exact_lane_start_d, exact_lane_start_q;
  logic [NrLanes-1:0]      exact_lane_sign_d, exact_lane_sign_q;
  logic [287:0] exact_root_d, exact_root_q;
  logic [2:0]   exact_carry_d, exact_carry_q;
  logic         exact_seed_folded_d, exact_seed_folded_q;
  logic [3:0]   exact_special_d, exact_special_q;
  logic         exact_source_seen_d, exact_source_seen_q;
  logic         exact_finite_nonzero_seen_d, exact_finite_nonzero_seen_q;
  logic         exact_pos_zero_seen_d, exact_pos_zero_seen_q;
  logic         exact_neg_zero_seen_d, exact_neg_zero_seen_q;
  logic         exact_seed_valid_d, exact_seed_valid_q;
  logic [31:0]  exact_seed_d, exact_seed_q;
  logic [2:0]   exact_rnd_mode_d, exact_rnd_mode_q;
  logic         exact_format_fp16_d, exact_format_fp16_q;
  logic [31:0]  exact_final_result;
  logic [4:0]   exact_final_status;
  logic [NrLanes-1:0] exact_stale_token_drop;
  logic               exact_header_rendezvous_wait;
  logic               exact_header_merge_fire;
  logic               exact_late_seed_wait;
  logic               exact_late_seed_bind;
  logic [2:0]         exact_header_global_limb_count;
  logic               exact_limb_merge_fire;
  logic [2:0]         exact_implicit_sign_lane_count;

  function automatic logic [3:0] exact_merge_special(
    input logic [3:0] left,
    input logic [3:0] right
  );
    logic [3:0] merged;
    begin
      merged = '0;
      merged[2] = left[2] | right[2];
      if (left[3] || right[3]) begin
        merged[3] = 1'b1;
      end else if ((left[1] && right[0]) ||
                   (left[0] && right[1])) begin
        merged[3] = 1'b1;
        merged[2] = 1'b1;
      end else begin
        merged[1] = left[1] | right[1];
        merged[0] = left[0] | right[0];
      end
      exact_merge_special = merged;
    end
  endfunction

  logic [287:0] seeded_root;
  logic [287:0] header_fixed_seed;
  logic [3:0] seeded_special;
  logic seeded_finite_nonzero, seeded_pos_zero, seeded_neg_zero;
  logic seed_header_phase;
  logic [3:0] header_source_special;
  logic header_finite_nonzero, header_pos_zero, header_neg_zero;
  assign seed_header_phase = state_q == EXACT_RECEIVE && exact_packet_beat_q == 0;
  assign header_source_special = exact_merge_special(
    exact_merge_special(exact_operand_i[0][25:22], exact_operand_i[1][25:22]),
    exact_merge_special(exact_operand_i[2][25:22], exact_operand_i[3][25:22]));
  assign header_finite_nonzero = exact_operand_i[0][20] | exact_operand_i[1][20] |
                                exact_operand_i[2][20] | exact_operand_i[3][20];
  assign header_pos_zero = exact_operand_i[0][19] | exact_operand_i[1][19] |
                          exact_operand_i[2][19] | exact_operand_i[3][19];
  assign header_neg_zero = exact_operand_i[0][18] | exact_operand_i[1][18] |
                          exact_operand_i[2][18] | exact_operand_i[3][18];
  fp32_exact_reduction_seed i_exact_seed (
    // Command acceptance has already cleared root during the header phase.
    // Reuse the same converter/adder for optional preload and late binding.
    .exact_value_i(exact_root_q),
    .special_i(seed_header_phase ? header_source_special : exact_special_q),
    .finite_nonzero_seen_i(seed_header_phase ? header_finite_nonzero : exact_finite_nonzero_seen_q),
    .pos_zero_seen_i(seed_header_phase ? header_pos_zero : exact_pos_zero_seen_q),
    .neg_zero_seen_i(seed_header_phase ? header_neg_zero : exact_neg_zero_seen_q),
    .seed_valid_i(seed_header_phase ? (owner_q.late_seed ? exact_late_seed_ready :
                                  exact_operand_i[0][17]) : exact_seed_valid_q),
    .seed_in_exact_i(1'b0),
    .seed_i(seed_header_phase ? (owner_q.late_seed ? exact_seed_data_i :
                              exact_operand_i[0][63:32]) : exact_seed_q),
    .format_fp16_i(seed_header_phase ? exact_operand_i[0][10] : exact_format_fp16_q),
    .exact_value_o(seeded_root), .seed_fixed_o(header_fixed_seed), .special_o(seeded_special),
    .finite_nonzero_seen_o(seeded_finite_nonzero),
    .pos_zero_seen_o(seeded_pos_zero), .neg_zero_seen_o(seeded_neg_zero)
  );

  fp32_exact_reduction_finalize i_fp32_exact_reduction_finalize (
    .exact_value_i         (exact_root_q),
    .special_i             (exact_special_q),
    .source_seen_i         (exact_source_seen_q),
    .finite_nonzero_seen_i (exact_finite_nonzero_seen_q),
    .pos_zero_seen_i       (exact_pos_zero_seen_q),
    .neg_zero_seen_i       (exact_neg_zero_seen_q),
    .seed_valid_i          (exact_seed_valid_q),
    .seed_i                (exact_seed_q),
    // The receive merger or EXACT_SEED_ADD has bound the seed in the root.
    // A constant here removes seed addition from the rounding timing cone.
    .seed_in_exact_i       (1'b1),
    .rnd_mode_i            (exact_rnd_mode_q),
    .format_fp16_i         (exact_format_fp16_q),
    .result_o              (exact_final_result),
    .status_o              (exact_final_status)
  );

    assign exact_late_seed_ready = !owner_q.late_seed || exact_seed_ready_i ||
      (RceExactSeedReceiveEnable && exact_seed_valid_q);
    // Per-lane ownership of the current sparse frame, independent of result
    // retirement. The transport may already buffer a following instruction.
    for (genvar lane = 0; lane < NrLanes; lane++) begin : gen_exact_lane_consumed
      assign exact_lane_consumed_o[lane] = state_q == EXACT_RESULT || state_q == EXACT_SEED_ADD || state_q == EXACT_SEED_WAIT ||
        (state_q == EXACT_RECEIVE && exact_packet_beat_q != 0 &&
         (exact_packet_beat_q > exact_lane_limb_count_q[lane] ||
          exact_lane_start_q[lane] > exact_lane_limb_count_q[lane]));
    end
    // Capturing the old finalized result transfers its complete ownership to
    // the completion slot. The root/context registers may accept a new owner
    // at the same edge; an intervening IDLE cycle serves no purpose.
    assign exact_cmd_ready_o = state_q == EXACT_IDLE ||
      (RceExactDecoupleEnable && state_q == EXACT_RESULT && completed_space);
    assign exact_result_valid_o = RceExactDecoupleEnable ? completed_valid_q :
      state_q == EXACT_RESULT;
    assign exact_result_o = RceExactDecoupleEnable ? completed_q : raw_result;
    assign raw_result = '{id: owner_q.id, vd: owner_q.vd, version: owner_q.version,
      be: exact_format_fp16_q ? 8'h03 : 8'h0f,
      data: exact_final_result, fflags: exact_final_status};
    assign exact_events_o = '{stale_token_drop: exact_stale_token_drop, header_wait: exact_header_rendezvous_wait, header_fire: exact_header_merge_fire, seed_wait: exact_late_seed_wait, seed_bind: exact_late_seed_bind, limb_fire: exact_limb_merge_fire, window_limbs: exact_header_global_limb_count, implicit_sign_lanes: exact_implicit_sign_lane_count};

    always_comb begin
      state_d = state_q;
      exact_packet_beat_d = exact_packet_beat_q;
      exact_limb_count_d = exact_limb_count_q;
      exact_lane_limb_count_d = exact_lane_limb_count_q;
      exact_lane_start_d = exact_lane_start_q;
      exact_lane_sign_d = exact_lane_sign_q;
      exact_root_d = exact_root_q;
      exact_carry_d = exact_carry_q;
      exact_seed_folded_d = exact_seed_folded_q;
      exact_special_d = exact_special_q;
      exact_source_seen_d = exact_source_seen_q;
      exact_finite_nonzero_seen_d = exact_finite_nonzero_seen_q;
      exact_pos_zero_seen_d = exact_pos_zero_seen_q;
      exact_neg_zero_seen_d = exact_neg_zero_seen_q;
      exact_seed_valid_d = exact_seed_valid_q;
      exact_seed_d = exact_seed_q;
      exact_rnd_mode_d = exact_rnd_mode_q;
      exact_format_fp16_d = exact_format_fp16_q;
      exact_operand_ready_o = '0;
      exact_local_complete_o = 1'b0;
      exact_stale_token_drop = '0;
      exact_header_rendezvous_wait = '0;
      exact_header_merge_fire = '0;
      exact_late_seed_wait = '0;
      exact_late_seed_bind = '0;
      exact_limb_merge_fire = '0;
      exact_header_global_limb_count = '0;
      exact_implicit_sign_lane_count = '0;
      // The adapter retains the issuing descriptor until local_complete.
      // Snapshot a matching seed once; later bus changes cannot replace it.
      if (RceExactSeedReceiveEnable && owner_q.late_seed && !exact_seed_valid_q &&
          exact_seed_ready_i && ((state_q == EXACT_RECEIVE && exact_packet_beat_q != 0) ||
                                state_q == EXACT_SEED_WAIT)) begin
        exact_seed_valid_d = 1'b1;
        exact_seed_d = exact_seed_data_i;
        exact_late_seed_bind = 1'b1;
      end
      case (state_q)
        EXACT_IDLE: if (exact_cmd_valid_i) begin
          state_d = EXACT_RECEIVE;
          exact_packet_beat_d = '0;
          exact_seed_valid_d = 1'b0;
          exact_limb_count_d = 3'd5;
          exact_root_d = '0;
          exact_carry_d = '0;
          exact_seed_folded_d = 1'b0;
        end
      EXACT_RECEIVE: begin
        logic [66:0] chunk_sum;
        logic [63:0] seed_limb;
        logic [66:0] csa_a, csa_b, csa_c, csa_d, csa_e;
        logic [66:0] csa_s1, csa_c1, csa_s2, csa_c2, csa_s3, csa_c3;
        logic seed_low_fits, seed_high_fits, seed_fold;
        logic [2:0] negative_lane_count;
        logic signed [3:0] upper_correction;
        logic signed [3:0] header_upper_correction;
        logic [3:0] special_pair_lo, special_pair_hi;
        logic [NrLanes-1:0] header_match;
        logic [NrLanes-1:0] limb_available;
        logic [NrLanes-1:0][63:0] limb_operand;
        logic [2:0] header_limb_count, header_start;

        chunk_sum = '0;
        seed_limb = '0;
        csa_a = '0; csa_b = '0; csa_c = '0; csa_d = '0; csa_e = '0;
        csa_s1 = '0; csa_c1 = '0; csa_s2 = '0; csa_c2 = '0;
        csa_s3 = '0; csa_c3 = '0;
        seed_low_fits = 1'b0;
        seed_high_fits = 1'b0;
        seed_fold = 1'b0;
        negative_lane_count = {2'b0, exact_lane_sign_q[0]} +
                              {2'b0, exact_lane_sign_q[1]} +
                              {2'b0, exact_lane_sign_q[2]} +
                              {2'b0, exact_lane_sign_q[3]};
        upper_correction = '0;
        header_upper_correction = -($signed({3'b0, exact_operand_i[0][8]}) +
                                     $signed({3'b0, exact_operand_i[1][8]}) +
                                     $signed({3'b0, exact_operand_i[2][8]}) +
                                     $signed({3'b0, exact_operand_i[3][8]}));
        special_pair_lo = '0;
        special_pair_hi = '0;
        header_match = '0;
        limb_available = '0;
        limb_operand = '0;
        header_limb_count = 3'd1;
        header_start = 3'd6;

        if (exact_packet_beat_q == 3'd0) begin
          // A previous reduction may leave an inactive-lane dummy token in
          // one input spill while other lanes have already presented the new
          // exact header.  Consume only mismatching tokens; matching headers
          // remain buffered until the whole tagged context is aligned.
          for (int lane = 0; lane < NrLanes; lane++) begin
            header_match[lane] = exact_operand_valid_i[lane] &&
              (exact_operand_i[lane][31:28] == 4'he) &&
              (exact_operand_i[lane][27:26] == lane[1:0]) &&
              (exact_operand_i[lane][4:0] == 5'(owner_q.id));
            if (exact_operand_valid_i[lane] && !header_match[lane])
              exact_operand_ready_o[lane] = 1'b1;
            exact_stale_token_drop[lane] =
              exact_operand_valid_i[lane] && !header_match[lane];
            if (header_match[lane] &&
                exact_operand_i[lane][13:11] > header_limb_count)
              header_limb_count = exact_operand_i[lane][13:11];
            if (header_match[lane] &&
                {1'b0, exact_operand_i[lane][7:5]} + 4'd1 < {1'b0, header_start})
              header_start = exact_operand_i[lane][7:5] + 3'd1;
          end
          exact_header_rendezvous_wait = !(&header_match)
                                         || (!RceExactSeedReceiveEnable && !exact_late_seed_ready)
          ;
          exact_late_seed_wait =
            owner_q.late_seed && !exact_late_seed_ready && !RceExactSeedReceiveEnable
                                         ;

          if (&header_match
              && (RceExactSeedReceiveEnable || exact_late_seed_ready)
             ) begin
            // Fold a ready seed into the already-required receive window.
            // Never extend the window or wait for a missing seed just to fold.
            unique case (header_start)
              3'd1: seed_low_fits = 1'b1;
              3'd2: seed_low_fits = header_fixed_seed[63:0] == '0;
              3'd3: seed_low_fits = header_fixed_seed[127:0] == '0;
              3'd4: seed_low_fits = header_fixed_seed[191:0] == '0;
              3'd5: seed_low_fits = header_fixed_seed[255:0] == '0;
              default: seed_low_fits = header_fixed_seed == '0;
            endcase
            unique case (header_limb_count)
              3'd1: seed_high_fits = header_fixed_seed[287:64] == {224{header_fixed_seed[287]}};
              3'd2: seed_high_fits = header_fixed_seed[287:128] == {160{header_fixed_seed[287]}};
              3'd3: seed_high_fits = header_fixed_seed[287:192] == {96{header_fixed_seed[287]}};
              3'd4: seed_high_fits = header_fixed_seed[287:256] == {32{header_fixed_seed[287]}};
              default: seed_high_fits = 1'b1;
            endcase
            seed_fold = exact_late_seed_ready && seed_low_fits && seed_high_fits &&
                        header_start <= header_limb_count;
            exact_seed_folded_d = seed_fold;
            exact_header_merge_fire = 1'b1;
            exact_late_seed_bind = owner_q.late_seed && exact_late_seed_ready;
            exact_header_global_limb_count = header_limb_count;
            exact_operand_ready_o = '1;
            special_pair_lo = exact_merge_special(
              exact_operand_i[0][25:22], exact_operand_i[1][25:22]);
            special_pair_hi = exact_merge_special(
              exact_operand_i[2][25:22], exact_operand_i[3][25:22]);
            exact_special_d = exact_merge_special(
              special_pair_lo, special_pair_hi);
            exact_source_seen_d =
              exact_operand_i[0][21] | exact_operand_i[1][21] |
              exact_operand_i[2][21] | exact_operand_i[3][21];
            exact_finite_nonzero_seen_d =
              exact_operand_i[0][20] | exact_operand_i[1][20] |
              exact_operand_i[2][20] | exact_operand_i[3][20];
            exact_pos_zero_seen_d =
              exact_operand_i[0][19] | exact_operand_i[1][19] |
              exact_operand_i[2][19] | exact_operand_i[3][19];
            exact_neg_zero_seen_d =
              exact_operand_i[0][18] | exact_operand_i[1][18] |
              exact_operand_i[2][18] | exact_operand_i[3][18];
            if (owner_q.late_seed) begin
              exact_seed_valid_d = exact_late_seed_ready;
              exact_seed_d =
                exact_seed_data_i;
            end else begin
              exact_seed_valid_d = exact_operand_i[0][17];
              exact_seed_d       = exact_operand_i[0][63:32];
            end
            exact_rnd_mode_d   = exact_operand_i[0][16:14];
            exact_format_fp16_d = exact_operand_i[0][10];
            exact_limb_count_d = header_limb_count;
            for (int lane = 0; lane < NrLanes; lane++) begin
              exact_lane_limb_count_d[lane] = exact_operand_i[lane][13:11];
              exact_lane_start_d[lane] = exact_operand_i[lane][7:5] + 3'd1;
              exact_lane_sign_d[lane] = exact_operand_i[lane][8];
            end
            exact_root_d       = '0;
            exact_carry_d      = '0;
            exact_packet_beat_d = header_start;
            state_d = EXACT_RECEIVE;
            if (seed_fold) begin
              exact_root_d = header_fixed_seed;
              exact_special_d = seeded_special;
              exact_finite_nonzero_seen_d = seeded_finite_nonzero;
              exact_pos_zero_seen_d = seeded_pos_zero;
              exact_neg_zero_seen_d = seeded_neg_zero;
            end
            // A payload-free frame contains its full numeric state in the
            // header: zero low limbs and the advertised upper sign extension.
            // This also covers -2**(64*end), whose only nonzero bits are the
            // omitted high ones. With start>end all negative lanes necessarily
            // begin their sign extension at this same global end.
            // Keep both timing boundaries; reclaim omitted transport cycles.
            if (header_start > header_limb_count) begin
              unique case (header_limb_count)
                3'd1: exact_root_d[287:64] =
                  {{220{header_upper_correction[3]}}, header_upper_correction};
                3'd2: exact_root_d[287:128] =
                  {{156{header_upper_correction[3]}}, header_upper_correction};
                3'd3: exact_root_d[287:192] =
                  {{92{header_upper_correction[3]}}, header_upper_correction};
                3'd4: exact_root_d[287:256] =
                  {{28{header_upper_correction[3]}}, header_upper_correction};
                default: ; // No bits above the fifth (32-bit) data limb.
              endcase
              if (RceExactSeedReceiveEnable && owner_q.late_seed && !exact_seed_valid_d)
                state_d = EXACT_SEED_WAIT;
              else begin
                state_d = EXACT_SEED_ADD;
                exact_local_complete_o = 1'b1;
              end
            end

`ifndef SYNTHESIS
            for (int lane = 0; lane < NrLanes; lane++) begin
              assert (exact_operand_i[lane][16:14] ==
                      exact_operand_i[0][16:14])
                else $error("exact reduction packet disagrees on rounding mode");
              assert (exact_operand_i[lane][10] == exact_operand_i[0][10])
                else $error("exact reduction packet disagrees on FP format");
              assert (exact_operand_i[lane][7:5] <= 3'd5)
                else $error("exact reduction packet has an invalid low-zero prefix");
              assert (exact_operand_i[lane][13:11] inside {[3'd1:3'd5]})
                else $error("exact reduction packet advertises an invalid active window");
            end
            if (owner_q.late_seed) begin
              assert (!(exact_operand_i[0][17] |
                        exact_operand_i[1][17] |
                        exact_operand_i[2][17] |
                        exact_operand_i[3][17]))
                else $error("late exact seed was also inserted by a lane");
            end else begin
              assert (exact_operand_i[0][17] &&
                      !(exact_operand_i[1][17] |
                        exact_operand_i[2][17] |
                        exact_operand_i[3][17]))
                else $error("exact reduction seed ownership invalid: %016x %016x %016x %016x",
                            exact_operand_i[0], exact_operand_i[1],
                            exact_operand_i[2], exact_operand_i[3]);
            end
`endif
          end
        end else begin
          // Lane windows may end at different limbs.  A finished lane has no
          // physical token to wait for; its omitted high limbs are the sign
          // extension advertised in the header.  Required lane tokens retain
          // normal ready/valid backpressure.
          for (int lane = 0; lane < NrLanes; lane++) begin
            if (exact_packet_beat_q < exact_lane_start_q[lane]) begin
              limb_available[lane] = 1'b1;
              limb_operand[lane] = '0;
            end else if (exact_packet_beat_q <= exact_lane_limb_count_q[lane]) begin
              limb_available[lane] = exact_operand_valid_i[lane];
              limb_operand[lane] = exact_operand_i[lane];
            end else begin
              limb_available[lane] = 1'b1;
              limb_operand[lane] = {64{exact_lane_sign_q[lane]}};
              exact_implicit_sign_lane_count += 1'b1;
            end
          end
          if (&limb_available) begin
            exact_limb_merge_fire = 1'b1;
            // Root limbs have an implicit beat number once the tagged header
            // rendezvous has completed.
            for (int lane = 0; lane < NrLanes; lane++)
              exact_operand_ready_o[lane] =
                exact_packet_beat_q >= exact_lane_start_q[lane] &&
                exact_packet_beat_q <= exact_lane_limb_count_q[lane];
            // Unprocessed root limbs still contain the preloaded seed. Once
            // processed they contain the final sum and are never read again.
            if (exact_seed_folded_q) begin
              unique case (exact_packet_beat_q)
                3'd1: seed_limb = exact_root_q[63:0];
                3'd2: seed_limb = exact_root_q[127:64];
                3'd3: seed_limb = exact_root_q[191:128];
                3'd4: seed_limb = exact_root_q[255:192];
                default: seed_limb = {{32{exact_root_q[287]}}, exact_root_q[287:256]};
              endcase
            end
            // Compress the five operands and carry before a single final CPA.
            // No additional wide arithmetic unit or root register is needed.
            csa_a = {3'b0, limb_operand[0]};
            csa_b = {3'b0, limb_operand[1]};
            csa_c = {3'b0, limb_operand[2]};
            csa_d = {3'b0, limb_operand[3]};
            csa_e = {3'b0, seed_limb};
            csa_s1 = csa_a ^ csa_b ^ csa_c;
            csa_c1 = ((csa_a & csa_b) | (csa_a & csa_c) | (csa_b & csa_c)) << 1;
            csa_s2 = csa_d ^ csa_e ^ {64'b0, exact_carry_q};
            csa_c2 = ((csa_d & csa_e) | (csa_d & {64'b0, exact_carry_q}) |
                      (csa_e & {64'b0, exact_carry_q})) << 1;
            csa_s3 = csa_s1 ^ csa_c1 ^ csa_s2;
            csa_c3 = ((csa_s1 & csa_c1) | (csa_s1 & csa_s2) | (csa_c1 & csa_s2)) << 1;
            csa_a = csa_s3 ^ csa_c3 ^ csa_c2;
            csa_b = ((csa_s3 & csa_c3) | (csa_s3 & csa_c2) | (csa_c3 & csa_c2)) << 1;
            chunk_sum = csa_a + csa_b;
            exact_carry_d = chunk_sum[66:64];
            // Above the last transmitted limb each source is all zeros or
            // all ones. In unbounded signed arithmetic their sum is therefore
            // carry_out - number_of_negative_operands (-5..4 with seed). This resolves the
            // upper root without transmitting a guard limb or adding a wide
            // carry-propagation stage. Also valid for legacy guarded packets.
            upper_correction = $signed({1'b0, chunk_sum[66:64]}) -
                               $signed({1'b0, negative_lane_count}) -
                               $signed({3'b0, (exact_seed_folded_q && exact_root_q[287])});

            unique case (exact_packet_beat_q)
              3'd1: begin
                exact_root_d[63:0] = chunk_sum[63:0];
                if (exact_limb_count_q == 3'd1)
                  exact_root_d[287:64] = {{220{upper_correction[3]}}, upper_correction};
              end
              3'd2: begin
                exact_root_d[127:64] = chunk_sum[63:0];
                if (exact_limb_count_q == 3'd2)
                  exact_root_d[287:128] = {{156{upper_correction[3]}}, upper_correction};
              end
              3'd3: begin
                exact_root_d[191:128] = chunk_sum[63:0];
                if (exact_limb_count_q == 3'd3)
                  exact_root_d[287:192] = {{92{upper_correction[3]}}, upper_correction};
              end
              3'd4: begin
                exact_root_d[255:192] = chunk_sum[63:0];
                if (exact_limb_count_q == 3'd4)
                  exact_root_d[287:256] = {{28{upper_correction[3]}}, upper_correction};
              end
              default: exact_root_d[287:256] = chunk_sum[31:0];
            endcase

            if (exact_packet_beat_q == exact_limb_count_q) begin
              if (RceExactSeedReceiveEnable && owner_q.late_seed && !exact_seed_valid_d)
                state_d = EXACT_SEED_WAIT;
              else begin
                state_d = exact_seed_folded_q ? EXACT_RESULT : EXACT_SEED_ADD;
                exact_local_complete_o = 1'b1;
              end
            end else begin
              exact_packet_beat_d = exact_packet_beat_q + 1'b1;
            end
          end
        end
      end


        EXACT_SEED_WAIT: begin
          exact_late_seed_wait = !exact_seed_valid_d;
          // Do not advance the SLDU descriptor while its seed lookup is needed.
          if (exact_seed_valid_d) begin
            state_d = EXACT_SEED_ADD;
            exact_local_complete_o = 1'b1;
          end
        end
        EXACT_SEED_ADD: begin
          // Reuse the root and special-state registers: no second 288-bit bank.
          // This state executes once per context, after all limbs and seed arrive.
          exact_root_d = seeded_root;
          exact_special_d = seeded_special;
          exact_finite_nonzero_seen_d = seeded_finite_nonzero;
          exact_pos_zero_seen_d = seeded_pos_zero;
          exact_neg_zero_seen_d = seeded_neg_zero;
          state_d = EXACT_RESULT;
        end
        EXACT_RESULT: if (RceExactDecoupleEnable ? completed_space : exact_result_ready_i) begin
          state_d = EXACT_IDLE;
          if (RceExactDecoupleEnable && exact_cmd_valid_i) begin
            state_d = EXACT_RECEIVE;
            exact_packet_beat_d = '0;
            exact_seed_valid_d = 1'b0;
            exact_limb_count_d = 3'd5;
            exact_root_d = '0;
            exact_carry_d = '0;
            exact_seed_folded_d = 1'b0;
          end
        end
        default: state_d = EXACT_IDLE;
      endcase
    end
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        state_q <= EXACT_IDLE;
        owner_q <= '0;
        exact_packet_beat_q <= '0;
        exact_limb_count_q <= '0;
        exact_lane_limb_count_q <= '0;
        exact_lane_start_q <= '0;
        exact_lane_sign_q <= '0;
        exact_root_q <= '0;
        exact_carry_q <= '0;
        exact_seed_folded_q <= 1'b0;
        exact_special_q <= '0;
        exact_source_seen_q <= '0;
        exact_finite_nonzero_seen_q <= '0;
        exact_pos_zero_seen_q <= '0;
        exact_neg_zero_seen_q <= '0;
        exact_seed_valid_q <= '0;
        exact_seed_q <= '0;
        exact_rnd_mode_q <= '0;
        exact_format_fp16_q <= '0;
      end else begin
        state_q <= state_d;
        if (exact_cmd_valid_i && exact_cmd_ready_o) owner_q <= exact_cmd_i;
        exact_packet_beat_q <= exact_packet_beat_d;
        exact_limb_count_q <= exact_limb_count_d;
        exact_lane_limb_count_q <= exact_lane_limb_count_d;
        exact_lane_start_q <= exact_lane_start_d;
        exact_lane_sign_q <= exact_lane_sign_d;
        exact_root_q <= exact_root_d;
        exact_carry_q <= exact_carry_d;
        exact_seed_folded_q <= exact_seed_folded_d;
        exact_special_q <= exact_special_d;
        exact_source_seen_q <= exact_source_seen_d;
        exact_finite_nonzero_seen_q <= exact_finite_nonzero_seen_d;
        exact_pos_zero_seen_q <= exact_pos_zero_seen_d;
        exact_neg_zero_seen_q <= exact_neg_zero_seen_d;
        exact_seed_valid_q <= exact_seed_valid_d;
        exact_seed_q <= exact_seed_d;
        exact_rnd_mode_q <= exact_rnd_mode_d;
        exact_format_fp16_q <= exact_format_fp16_d;
      end
    end
`ifndef SYNTHESIS
    initial begin
      assert (NrLanes == 4) else $fatal(1, "exact RCE requires four lanes");
      assert ($bits(vid_t) <= 5) else $fatal(1, "exact header ID field is too narrow");
    end
    a_exact_command_reserved: assert property (@(posedge clk_i) disable iff (!rst_ni)
      exact_cmd_valid_i |-> exact_cmd_ready_o);
    a_exact_header_starts_from_empty_root: assert property (
      @(posedge clk_i) disable iff (!rst_ni)
        seed_header_phase |-> exact_root_q == '0
    ) else $error("exact seed preload reused a nonempty root");
    a_exact_folded_seed_is_not_added_twice: assert property (
      @(posedge clk_i) disable iff (!rst_ni)
        exact_seed_folded_q |-> state_q != EXACT_SEED_ADD && state_q != EXACT_SEED_WAIT
    ) else $error("exact folded seed entered the late seed adder");
    a_exact_folded_seed_has_owner: assert property (
      @(posedge clk_i) disable iff (!rst_ni)
        exact_seed_folded_q |-> exact_seed_valid_q
    ) else $error("exact folded seed has no bound version");
    a_exact_result_stable: assert property (@(posedge clk_i) disable iff (!rst_ni)
      exact_result_valid_o && !exact_result_ready_i |=>
      exact_result_valid_o && $stable(exact_result_o));
  a_exact_fp16_root_has_shared_quantum: assert property (
    @(posedge clk_i) disable iff (!rst_ni)
      (state_q == EXACT_RESULT && exact_format_fp16_q) |->
        (exact_root_q[124:0] == '0)
  ) else $error("RCE binary16 exact root is not aligned to bit 125");

  a_exact_limb_schedule_is_bounded: assert property (
    @(posedge clk_i) disable iff (!rst_ni)
      (state_q == EXACT_RECEIVE && exact_packet_beat_q != 0) |->
        (exact_limb_count_q inside {[3'd1:3'd5]} &&
         exact_packet_beat_q <= exact_limb_count_q)
  ) else $error("RCE exact reduction limb schedule is malformed");

  for (genvar lane = 0; lane < NrLanes; lane++) begin : gen_exact_sparse_assertions
    a_finished_lane_sends_no_high_limb: assert property (
      @(posedge clk_i) disable iff (!rst_ni)
        (state_q == EXACT_RECEIVE && exact_packet_beat_q != 0 &&
         exact_packet_beat_q > exact_lane_limb_count_q[lane]) |->
          !exact_operand_valid_i[lane]
    ) else $error("finished exact lane sent a redundant high limb");

    // A data limb below bit 256 may have either MSB: the header separately
    // specifies its omitted upper extension. Only the full-width top word
    // itself contains the architectural sign bit (bit 31 of this word).
    a_full_width_sparse_limb_matches_header_sign: assert property (
      @(posedge clk_i) disable iff (!rst_ni)
        (state_q == EXACT_RECEIVE &&
         exact_packet_beat_q == 3'd5 &&
         exact_lane_limb_count_q[lane] == 3'd5 &&
         exact_operand_valid_i[lane]) |->
          (exact_operand_i[lane][63:31] == {33{exact_lane_sign_q[lane]}})
    ) else $error("exact lane header sign disagrees with its full-width limb");
  end

`endif
  end else begin : gen_no_exact
    assign exact_cmd_ready_o = 1'b0;
    assign exact_operand_ready_o = '0;
    assign exact_local_complete_o = 1'b0;
    assign exact_lane_consumed_o = '0;
    assign exact_result_o = '0;
    assign exact_result_valid_o = 1'b0;
    assign exact_events_o = '0;
  end

endmodule
