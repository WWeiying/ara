// SPDX-License-Identifier: SHL-0.51
// Architectural ownership at the lane-local/completion boundary.
package ara_rce_pkg;
  import ara_pkg::*;
  import rvv_pkg::*;

`ifdef ARA_RED_RCE_QUEUE_LOOKAHEAD
  localparam bit RceQueueLookaheadEnable = 1'b1;
`else
  localparam bit RceQueueLookaheadEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_WORD_TURNAROUND
  localparam bit RceWordTurnaroundEnable = 1'b1;
`else
  localparam bit RceWordTurnaroundEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_EXACT_EGRESS_RELEASE
  localparam bit RceExactEgressReleaseEnable = 1'b1;
`else
  localparam bit RceExactEgressReleaseEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_RESULT_DEPTH
  localparam int unsigned RceResultQueueDepth = `ARA_RED_RCE_RESULT_DEPTH;
`else
  localparam int unsigned RceResultQueueDepth = 2;
`endif

`ifdef ARA_RED_RCE_ALU_RESULT_DEPTH
  localparam int unsigned RceAluResultQueueDepth = `ARA_RED_RCE_ALU_RESULT_DEPTH;
`else
  localparam int unsigned RceAluResultQueueDepth = RceResultQueueDepth;
`endif
`ifdef ARA_RED_RCE_FP_RESULT_DEPTH
  localparam int unsigned RceFpResultQueueDepth = `ARA_RED_RCE_FP_RESULT_DEPTH;
`else
  localparam int unsigned RceFpResultQueueDepth = RceResultQueueDepth;
`endif

`ifdef ARA_RED_RCE_COMPACT_WORD
  localparam bit RceCompactWordEnable = 1'b1;
`else
  localparam bit RceCompactWordEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_OPERAND_ISOLATION
  localparam bit RceOperandIsolationEnable = 1'b1;
`else
  localparam bit RceOperandIsolationEnable = 1'b0;
`endif

`ifdef ARA_RED_RCE_INT
  localparam bit RceIntEnable = 1'b1;
`else
  localparam bit RceIntEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_INT_LATE_SEED
  localparam bit RceIntLateSeedEnable = 1'b1;
`else
  localparam bit RceIntLateSeedEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_FP_MINMAX
  localparam bit RceFpMinMaxEnable = 1'b1;
`else
  localparam bit RceFpMinMaxEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_EXACT
  localparam bit RceExactEnable = 1'b1;
`else
  localparam bit RceExactEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_EXACT_DIRECT
  localparam bit RceExactDirectEnable = 1'b1;
`else
  localparam bit RceExactDirectEnable = 1'b0;
`endif
`ifdef ARA_RED_RCE_FP64_SUM
  localparam bit RceFp64SumEnable = 1'b1;
`else
  localparam bit RceFp64SumEnable = 1'b0;
`endif
  localparam bit RceFpCompletionEnable = RceFp64SumEnable || RceFpMinMaxEnable || RceExactDirectEnable;
  localparam bit RceEnable = RceIntEnable || RceFpMinMaxEnable || RceExactEnable || RceFp64SumEnable;

  // Exact packet transport remains ordered by its SLDU adapter. This command
  // owns one sparse frame; late-seed data is version-checked by that adapter.
  typedef struct packed {
    vid_t id;
    logic [4:0] vd;
    vreg_version_t version;
    logic late_seed;
  } rce_exact_command_t;
  typedef struct packed {
    vid_t id;
    logic [4:0] vd;
    vreg_version_t version;
    logic [7:0] be;
    logic [31:0] data;
    logic [4:0] fflags;
  } rce_exact_result_t;
  typedef struct packed {
    logic [3:0] stale_token_drop;
    logic header_wait, header_fire, seed_wait, seed_bind, limb_fire;
    logic [2:0] window_limbs, implicit_sign_lanes;
  } rce_exact_events_t;
`ifdef ARA_RED_RCE_MIXED
  localparam bit RceMixedEnable = 1'b1;
`else
  localparam bit RceMixedEnable = 1'b0;
`endif

  typedef enum logic [1:0] {
    RCE_SEED_EMBEDDED,  // Already incorporated exactly once by the lanes.
    RCE_SEED_READY,     // Source-only partials; seed supplied in the command.
    RCE_SEED_WAIT       // Source-only partials; bind the named producer later.
  } rce_seed_mode_e;

  typedef struct packed {
    vid_t id;
    ara_op_e op;
    fpnew_pkg::roundmode_e fp_rm;
    vew_e eew;         // Effective RESULT width, already widened by dispatch.
    logic [4:0] vd;
    vreg_version_t vd_version;
    logic vl_zero;     // Architectural VL=0, distinct from an empty lane.
    rce_seed_mode_e seed_mode;
    elen_t seed;       // Original bits, including sNaN payload and signed zero.
    vid_t seed_producer;
    logic [4:0] seed_register;
    vreg_version_t seed_version;
  } rce_command_t;

  typedef struct packed {
    vid_t id;
    elen_t data;
    logic source_active; // At least one REAL, unmasked source in this lane.
    logic [4:0] fflags;  // Accrued by local arithmetic, excluding deferred seed.
    logic seed_valid;   // Lane 0 can supply an eagerly read original seed.
    elen_t seed;
  } rce_partial_t;

  typedef struct packed {
    vid_t producer;
    logic [4:0] vd;
    vreg_version_t version;
    elen_t data;
  } rce_seed_t;

  typedef struct packed {
    vid_t id;
    logic [4:0] vd;
    vreg_version_t version;
    elen_t data;
    logic [7:0] be;
    logic [4:0] fflags;
    logic write_enable;
    logic is_fp;
  } rce_result_t;

  // This predicate describes the INITIAL integer/minmax backend, not all RVV
  // reductions. Exact/unordered-add backends are added behind the same owner
  // interface separately; ordered sums never enter an unordered merge tree.
  function automatic logic rce_fp64_sum(ara_op_e op, vew_e eew);
    return RceFp64SumEnable && eew == EW64 && op inside {VFREDUSUM, VFWREDUSUM};
  endfunction

  function automatic logic rce_fp_word(ara_op_e op, vew_e eew);
    return (RceFpMinMaxEnable && op inside {VFREDMIN, VFREDMAX}) || rce_fp64_sum(op, eew);
  endfunction

  function automatic logic rce_word_eligible(ara_op_e op, vew_e eew);
    return rce_fp64_sum(op, eew) || ((op inside {[VREDSUM:VWREDSUM]}) && (eew <= EW64)) ||
           ((op inside {VFREDMIN, VFREDMAX}) &&
            (eew inside {EW16, EW32, EW64}));
  endfunction

  // Source-only integer reductions start every packed element at its identity.
  function automatic elen_t rce_integer_identity(ara_op_e op, vew_e eew);
    logic low_bit, high_bit;
    low_bit = op inside {VREDAND, VREDMINU, VREDMIN};
    high_bit = op inside {VREDAND, VREDMINU, VREDMAX};
    case (eew)
      EW8: return {8{high_bit, {7{low_bit}}}};
      EW16: return {4{high_bit, {15{low_bit}}}};
      EW32: return {2{high_bit, {31{low_bit}}}};
      default: return {high_bit, {63{low_bit}}};
    endcase
  endfunction
endpackage
