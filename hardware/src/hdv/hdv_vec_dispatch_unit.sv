// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Vector dispatch adapter: serializes HEU's multi-slot vector execute-packet
// into single-instruction acc_req transactions for Ara.  It buffers the current
// EP internally and keeps issuing vector slots whenever Ara can accept them.
//
// ── Key semantic levels (ordered by completion progress) ───────────────────
//  Level 1 — Ara req handshake (acc_req.req_valid & req_ready):
//           Ara has received one vector instruction.  No operand guarantee.
//  Level 2 — Operand captured (operand_valid_q / vq_push):
//           Scalar rs1/rs2/frs1 values have been read from the scalar backend
//           and snapshotted into the request or command-window entry.  A later
//           scalar EP that overwrites those registers will not affect this
//           vector instruction.  This is the precondition for acknowledging
//           the EP back to HEU so the frontend can advance.
//  Level 3 — vec_ep_acknowledged_o (EP acknowledged):
//           Every vector slot in this EP has reached Level 2 AND any
//           scalar-visible vset (rd!=x0) writeback has been received.
//           HEU uses this to advance to the next EP.  THIS DOES NOT IMPLY
//           THAT ANY VECTOR INSTRUCTION HAS COMPLETED EXECUTION.
//  Level 4 — Ara response (acc_resp.resp_valid):
//           Ara has finished executing one vector instruction.  For vset,
//           the granted VL is written back to the scalar backend.  Vector
//           memory instruction responses may arrive long after Level 3.
//
// vec_store_inflight_o guards memory ordering: it is asserted while any
// vector store request has been sent to Ara but its response has not yet
// returned.  The scalar backend stalls scalar memory operations until this
// signal is deasserted, providing conservative store→load ordering.
//
// A real scalar backend supplies rs1/rs2/frs1 values through the operand service
// ports below.  In simulation, a vtrace file can alternatively provide the
// scalar context for bring-up.  Each vtrace entry is:
//   {insn[31:0], rs1[63:0], rs2[63:0]}
// The entry is consumed only when Ara accepts the request.

`ifndef HDV_STRINGIFY
`define HDV_STRINGIFY(x) `"x`"
`endif

`ifndef HDV_VTRACE
`ifdef VTRACE
`define HDV_VTRACE `VTRACE
`else
`define HDV_VTRACE ../../apps/ideal_dispatcher/vtrace/vsaxpy.vtrace
`endif
`endif

`ifndef HDV_N_VINSN
`ifdef N_VINSN
`define HDV_N_VINSN `N_VINSN
`else
`define HDV_N_VINSN 160
`endif
`endif

module hdv_vec_dispatch_unit import hdv_pkg::*; #(
  parameter int unsigned XLEN            = 64,
  parameter int unsigned NumSlots        = 8,
  parameter bit          UseVTraceScalar = 1'b1,
  parameter int unsigned VTraceDepth     = `HDV_N_VINSN,
  // [item2] Small resolved command window between HDV and Ara.  Entries already
  // captured scalar operands, so HDV can absorb short Ara req_ready bubbles
  // without building a large timing/area-heavy queue by default.
  parameter int unsigned CmdWindowDepth  = 4,
`ifdef FOR_VERIFY
  // Simulation-only vtrace context file path.  `string` is not synthesizable, so
  // the parameter (and the $readmemh/$fopen init block that uses it) is excluded
  // under SYNTHESIS; real-scalar mode (UseVTraceScalar=0) never needs it.
  parameter string       VTraceFile      = `HDV_STRINGIFY(`HDV_VTRACE),
`endif
  parameter type cva6_to_acc_t           = logic,
  parameter type acc_to_cva6_t           = logic
) (
  input  logic                              clk_i,
  input  logic                              rst_ni,
  input  logic                              flush_i,

  // ── From HEU vector dispatch output ──────────────────────────────────────
  // HEU asserts heu_vec_valid_i when has_vector=1 and dispatch_valid is set.
  input  logic                              heu_vec_valid_i,
  output logic                              vec_ep_ready_o,         // ready when pending skid buffer is free
  input  logic [NumSlots-1:0]               heu_vec_insn_valid_i,   // which slots are vector
  input  logic [NumSlots-1:0][31:0]         heu_vec_insn_i,         // assembled 32-bit insns
  input  logic                              heu_vec_ep_id_i,
  input  logic                              heu_vec_prefetch_hint_valid_i,
  input  logic                              heu_vec_prefetch_disable_i,
  input  logic [1:0]                        heu_vec_prefetch_mode_i, // EP-bundled prefetch mode (aligned w/ EP)

  // ── EP acknowledged pulse back to HEU (1-cycle) ───────────────────────────
  // vec_ep_acknowledged_o fires when all vector slots in this EP have reached
  // operand-safety (Level 2) and any vset rd!=x0 writeback has been received.
  // THIS DOES NOT MEAN VECTOR EXECUTION IS COMPLETE — see module header.
  output logic                              vec_ep_acknowledged_o,
  output logic                              vec_ep_acknowledged_id_o,
  output logic                              vec_ep_error_o,
  output logic                              vec_dispatch_busy_o,

  // ── Scalar operand service ───────────────────────────────────────────────
  output logic                              vec_scalar_operand_req_valid_o,
  input  logic                              scalar_vec_operand_req_ready_i,
  output logic [4:0]                        vec_scalar_rs1_addr_o,
  output logic [4:0]                        vec_scalar_rs2_addr_o,
  output logic [4:0]                        vec_scalar_frs1_addr_o,
  input  logic [XLEN-1:0]                   scalar_vec_rs1_data_i,
  input  logic [XLEN-1:0]                   scalar_vec_rs2_data_i,
  input  logic [XLEN-1:0]                   scalar_vec_frs1_data_i,

  // ── Vector-to-scalar writeback to scalar backend ────────────────────────
  output logic                              vec_scalar_wb_valid_o,
  output logic [4:0]                        vec_scalar_wb_rd_o,
  output logic [XLEN-1:0]                   vec_scalar_wb_data_o,
  output logic                              vec_scalar_wb_is_fpr_o,
  output logic                              vec_scalar_wb_is_vset_o,

  // ── In-flight vset hazard hint to scalar backend (A2 fix) ───────────────
  // Asserted from the moment an EP carrying a vset (rd!=x0) is presented until
  // its VL writeback lands, so the scalar backend can stall a dependent scalar
  // that reads that rd.  This window is already covered by the EP's vector
  // acknowledge wait, so the interlock is performance-neutral.
  output logic                              vec_scalar_vset_inflight_o,
  output logic [4:0]                        vec_scalar_vset_inflight_rd_o,
  // Asserted while any vector store request is in flight (sent to Ara but
  // response not yet received).  The scalar backend uses this to stall scalar
  // memory operations until the vector store is complete, providing
  // conservative store→load ordering.
  output logic                              vec_store_inflight_o,

  // ── Ara accelerator request / response (replaces CVA6→Ara path) ──────────
  output cva6_to_acc_t                      acc_req_o,
  input  acc_to_cva6_t                      acc_resp_i,
  output ara_pkg::hdv_meta_t                acc_req_hdv_meta_o

  // ── Performance-counter readout (FOR_VERIFY only) ─────────────────────────
  // A simple muxed readout port so the testbench / waveform / control- status
  // interface can sample any counter without hierarchical paths.
  `ifdef FOR_VERIFY
  ,
  input  logic [3:0]                        perf_ctr_sel_i,
  output logic [63:0]                       perf_ctr_data_o
  `endif
);

  localparam int unsigned SlotIdxW = (NumSlots > 1) ? $clog2(NumSlots) : 1;
  localparam int unsigned VTraceIdxW = (VTraceDepth > 1) ? $clog2(VTraceDepth) : 1;
  localparam int unsigned VTraceEntryWidth = 32 + 64 + 64;
  localparam int unsigned CountW = (NumSlots > 1) ? $clog2(NumSlots + 1) : 1;

  // ── Outstanding-model parameters ──────────────────────────────────────────
  //
  //  At most MaxOutstandingVecEPs vector EP slices can be alive in this module
  //  simultaneously.  Each occupies one entry in the real_wait_* table and is
  //  identified by an EpIdWidth-bit tag sourced from HEU's heu_vector_ep_id_o.
  //
  //  HEU currently drives exactly 2 EP ids (current + buffered), so
  //  MaxOutstandingVecEPs = 2 and EpIdWidth = 1.  To scale beyond 2 EPs:
  //    · widen HEU's vector_ep_id output to EpIdWidth bits
  //    · widen every ep_id / id storage in this module to EpIdWidth bits
  //    · increase RealWaitDepth accordingly
  //
  //  CmdWindowDepth is independent of the EP count — it absorbs short Ara
  //  back-pressure bubbles and can hold entries from any EP.  A single EP
  //  with > CmdWindowDepth vector slots will stall the FSM naturally.
  //
  //  RespMetaDepth must be large enough to cover every vector request that
  //  has passed through accept_insn (i.e. is either parked in the command
  //  window or has been sent to Ara) but has not yet received a response.
  //  Worst case: all slots of all outstanding EPs are in flight:
  //    RespMetaDepth >= MaxOutstandingVecEPs * NumSlots
  //  The floor of 16 is a safety margin for Ara's internal pipeline depth.
  localparam int unsigned MaxOutstandingVecEPs = 2;
  localparam int unsigned EpIdWidth = (MaxOutstandingVecEPs > 1) ?
                                       $clog2(MaxOutstandingVecEPs) : 1;
  localparam int unsigned RealWaitDepth = MaxOutstandingVecEPs;
  localparam int unsigned RespMetaMinDepth = MaxOutstandingVecEPs * NumSlots;
  localparam int unsigned RespMetaDepth = (RespMetaMinDepth > 16) ?
                                           RespMetaMinDepth : 16;
  localparam int unsigned RespMetaCountW = $clog2(RespMetaDepth + 1);
  localparam int unsigned CmdWindowCountW = (CmdWindowDepth > 1) ? $clog2(CmdWindowDepth + 1) : 1;

  // Compile-time invariant: the HEU→vec_dispatch EP-id wire must be at least
  // EpIdWidth bits wide.  If this fires, widen heu_vec_ep_id_i and the
  // HEU-side heu_vector_ep_id_o to EpIdWidth bits.
  // verilator lint_off WIDTH
  generate
    if (1 != EpIdWidth) begin : gen_ep_id_width_check
      initial begin
        $fatal(1, "[HDV] heu_vec_ep_id_i is 1 bit but MaxOutstandingVecEPs=%0d"
                 , " requires EpIdWidth=%0d.  Widen the EP-id port.",
                 MaxOutstandingVecEPs, EpIdWidth);
      end
    end
  endgenerate
  // verilator lint_on  WIDTH

  // ── Command window entry: carries a resolved vector request plus HDV-level
  // semantic tags so the window is self-describing — every entry records what
  // kind of command it is, which EP it came from, and what side-effects
  // (scalar writeback, memory ordering) it may produce.
  typedef enum logic [1:0] {
    VQ_CMD_ARITH  = 2'b00,  // vector arithmetic — no memory, no ordering concern
    VQ_CMD_LOAD   = 2'b01,  // vector load
    VQ_CMD_STORE  = 2'b10,  // vector store — memory-ordering relevance
    VQ_CMD_CONFIG = 2'b11   // vsetvli / vsetivli / vsetvl — changes VL/VTYPE
  } vq_cmd_class_e;

  typedef struct packed {
    logic [31:0]     insn;          // 32-bit vector instruction
    logic [XLEN-1:0] rs1;           // snapshotted scalar operand (rs1 / base / frs1)
    logic [XLEN-1:0] rs2;           // snapshotted scalar operand (rs2 / stride)
    ara_pkg::hdv_meta_t hdv_meta;   // HDV metadata snapped with this vector command
    vq_cmd_class_e    cmd_class;    // command category
    logic             has_scalar_wb; // instruction produces scalar-visible writeback
    logic             wb_is_fpr;    // writeback targets FRF (vfmv.f.s) rather than XRF
    logic             is_last_in_ep; // this is the last vector slot of its EP
  } vq_entry_t;

  typedef enum logic [1:0] {
    IDLE     = 2'd0,
    DISPATCH = 2'd1,
    WAIT     = 2'd2,
    DONE     = 2'd3
  } state_e;

  state_e                    state_d,      state_q;
  logic [NumSlots-1:0]       insn_valid_d, insn_valid_q;
  logic [NumSlots-1:0][31:0] insn_d,       insn_q;
  logic                      insn_ep_id_d, insn_ep_id_q;
  // Per-buffered-packet prefetch hint, latched WITH the packet (like insn_ep_id_q)
  // so a vle reaches the addrgen with its own EP's hint even when the front-end has
  // advanced through dense packet256+cross traffic.
  logic                      insn_prefetch_hint_valid_d, insn_prefetch_hint_valid_q;
  logic                      insn_prefetch_disable_d,    insn_prefetch_disable_q;
  logic [1:0]                insn_prefetch_mode_d,       insn_prefetch_mode_q;
  logic [NumSlots-1:0]       pending_insn_valid_d, pending_insn_valid_q;
  logic [NumSlots-1:0][31:0] pending_insn_d,       pending_insn_q;
  logic                      pending_ep_id_d, pending_ep_id_q;
  logic                      pending_prefetch_hint_valid_d, pending_prefetch_hint_valid_q;
  logic                      pending_prefetch_disable_d,    pending_prefetch_disable_q;
  logic [1:0]                pending_prefetch_mode_d, pending_prefetch_mode_q;
  logic                      pending_valid_d,      pending_valid_q;
  logic                      ep_acknowledged_d,        ep_acknowledged_q;
  logic                      ep_acknowledged_id_d,     ep_acknowledged_id_q;
  logic                      error_sticky_d,       error_sticky_q;
  logic [VTraceIdxW:0]        vtrace_idx_d, vtrace_idx_q;
  logic [VTraceEntryWidth-1:0] vtrace_mem [VTraceDepth];
  logic [VTraceEntryWidth-1:0] vtrace_entry_raw;
  logic [VTraceIdxW-1:0]       vtrace_mem_idx;
  logic [RespMetaCountW-1:0]     resp_meta_count_d, resp_meta_count_q;
  logic [RespMetaDepth-1:0]      resp_meta_wb_valid_d, resp_meta_wb_valid_q;
  logic [RespMetaDepth-1:0]      resp_meta_is_fpr_d, resp_meta_is_fpr_q;
  logic [RespMetaDepth-1:0]      resp_meta_is_vset_d, resp_meta_is_vset_q;
  logic [RespMetaDepth-1:0]      resp_meta_is_store_d, resp_meta_is_store_q;
  logic [RespMetaDepth-1:0][4:0] resp_meta_rd_d, resp_meta_rd_q;
  logic [RespMetaDepth-1:0]      resp_meta_ep_id_d, resp_meta_ep_id_q;
  logic [CountW-1:0]             vset_accept_wait_d, vset_accept_wait_q;
  logic [NumSlots-1:0]           vset_accept_id_d, vset_accept_id_q;
  logic [RealWaitDepth-1:0]      real_wait_valid_d, real_wait_valid_q;
  logic [RealWaitDepth-1:0]      real_wait_id_d, real_wait_id_q;
  logic [RealWaitDepth-1:0]      real_wait_has_vset_d, real_wait_has_vset_q;
  logic [RealWaitDepth-1:0]      real_ep_operands_captured_d, real_ep_operands_captured_q;
  logic [RealWaitDepth-1:0]      real_ep_vset_wb_done_d, real_ep_vset_wb_done_q;
  // Per-ep_id latch for a vsetvli writeback that arrives (immediate Ara response)
  // BEFORE its owning EP is enqueued into real_wait; consumed at enqueue.
  logic [1:0]                   vset_wb_pending_d, vset_wb_pending_q;
  logic                         operand_valid_d, operand_valid_q;
  logic [XLEN-1:0]              operand_rs1_d, operand_rs1_q;
  logic [XLEN-1:0]              operand_rs2_d, operand_rs2_q;
  logic                         selected_is_vset;
  logic                         selected_scalar_wb_valid;
  logic                         selected_scalar_wb_is_fpr;
  logic                         selected_is_vstore;
  logic                        vtrace_available;
  logic [31:0]                 vtrace_insn;
  logic [63:0]                 vtrace_rs1;
  logic [63:0]                 vtrace_rs2;
  logic                        vtrace_mismatch;
  logic                        vtrace_empty_error;
  logic                        ara_exception_error;
  logic                        resp_meta_full;
  logic                        resp_meta_can_push;
  logic                        input_ep_has_vset_wb;
  logic [4:0]                  input_vset_rd;
  logic                        resp_is_scalar_wb;
  logic                        real_wait_full;
  logic                        real_ep_can_acknowledge;
  logic [RealWaitDepth-1:0]    real_ep_safe;

  // Priority-encoders: find the lowest-index valid slot in the buffered EP or
  // in a freshly arriving EP.  The latter lets IDLE accept an EP and issue its
  // first vector instruction to Ara in the same cycle.
  logic                  slot_found;
  logic [SlotIdxW-1:0]   slot_idx;
  logic                  input_slot_found;
  logic [SlotIdxW-1:0]   input_slot_idx;
  // Pre-fetch: secondary priority encoder for the next slot after slot_idx
  logic                  next_slot_found;
  logic [SlotIdxW-1:0]   next_slot_idx;
  logic                  next_operand_valid_d, next_operand_valid_q;
  logic [XLEN-1:0]       next_operand_rs1_d, next_operand_rs1_q;
  logic [XLEN-1:0]       next_operand_rs2_d, next_operand_rs2_q;
  logic [SlotIdxW-1:0]   next_operand_slot_idx_d, next_operand_slot_idx_q;
  logic                  prefetch_operand_req;
  logic                  selected_has_next_operand;
  logic                  selected_slot_found;
  logic [31:0]           selected_insn;
  logic                  selected_uses_frs1;
  logic                  selected_uses_rs1;
  logic                  selected_uses_rs2;
  logic                  selected_needs_operand;
  logic                  selected_operand_port_busy;
  logic                  selected_operand_bypass;
  logic                  next_needs_operand;

  always_comb begin
    slot_found = 1'b0;
    slot_idx   = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (insn_valid_q[i] && !slot_found) begin
        slot_found = 1'b1;
        slot_idx   = SlotIdxW'(i);
      end
    end
  end

  always_comb begin
    input_slot_found = 1'b0;
    input_slot_idx   = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (heu_vec_insn_valid_i[i] && !input_slot_found) begin
        input_slot_found = 1'b1;
        input_slot_idx   = SlotIdxW'(i);
      end
    end
  end

  // Secondary priority encoder: find the second-lowest valid slot
  // (used to pre-fetch the next operand while the current slot dispatches).
  always_comb begin
    next_slot_found = 1'b0;
    next_slot_idx   = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (insn_valid_q[i] && (i > slot_idx) && !next_slot_found && slot_found) begin
        next_slot_found = 1'b1;
        next_slot_idx   = SlotIdxW'(i);
      end
    end
  end

  logic accept_insn;      // Ara accepted the instruction this cycle
  logic resp_valid;       // Ara produced the CV-X-IF response this cycle
  logic resp_has_queued_meta;
  logic resp_meta_wb_valid;
  logic resp_meta_is_fpr;
  logic resp_meta_is_vset;
  logic resp_meta_is_store;
  logic [4:0] resp_meta_rd;
  logic resp_meta_ep_id;
  logic resp_is_vset_wb;
  // Ara echoes acc_req.trans_id into acc_resp.trans_id; trans_id[0] carries the
  // owning ep_id of the responding instruction.
  logic resp_ep_id_from_trans;
  logic resp_vset_wb_from_trans;
  logic ara_meta_wb_valid;
  logic ara_meta_is_fpr;
  logic ara_meta_is_vset;
  logic ara_meta_is_store;
  logic [4:0] ara_meta_rd;
  logic ara_meta_ep_id;
  logic enqueue_ep;
  logic enqueue_to_pending;
  logic capture_operand;
  logic vset_accept_enqueue;
  logic vset_accept_ack;
  logic [CountW-1:0] vset_accept_count_after_pop;
  logic real_ep_operands_done;
  logic selected_ep_id;
  logic selected_prefetch_hint_valid;
  logic selected_prefetch_disable;
  logic [1:0] selected_prefetch_mode;
  ara_pkg::hdv_meta_t selected_hdv_meta;

  function automatic logic is_vector_scalar_wb(input logic [31:0] insn);
    logic is_vset;
    logic is_int_scalar;
    logic is_fp_scalar;
    begin
      is_vset = (insn[6:0] == 7'b1010111) &&
                (insn[14:12] == 3'b111);
      is_int_scalar = (insn[6:0] == 7'b1010111) &&
                      (insn[14:12] == 3'b010) &&
                      (insn[31:26] == 6'b010000) &&
                      ((insn[19:15] == 5'b00000) ||
                       (insn[19:15] == 5'b10000) ||
                       (insn[19:15] == 5'b10001));
      is_fp_scalar = (insn[6:0] == 7'b1010111) &&
                     (insn[14:12] == 3'b001) &&
                     (insn[31:26] == 6'b010000) &&
                     (insn[19:15] == 5'b00000);
      return is_vset || is_int_scalar || is_fp_scalar;
    end
  endfunction

  function automatic logic is_vector_fp_scalar_wb(input logic [31:0] insn);
    return (insn[6:0] == 7'b1010111) &&
           (insn[14:12] == 3'b001) &&
           (insn[31:26] == 6'b010000) &&
           (insn[19:15] == 5'b00000);
  endfunction

  function automatic logic vector_uses_scalar_rs1(input logic [31:0] insn);
    automatic logic uses;
    begin
      uses = 1'b0;
      unique case (insn[6:0])
        7'b0000111, // vector load
        7'b0100111: begin // vector store
          uses = (insn[19:15] != 5'd0);
        end
        7'b0101111: begin // vector AMO
          uses = (insn[19:15] != 5'd0);
        end
        7'b1010111: begin
          unique case (insn[14:12])
            3'b100, // OPIVX
            3'b110: uses = (insn[19:15] != 5'd0); // OPMVX
            3'b111: begin // vsetvli / vsetivli / vsetvl
              if (insn[31:30] == 2'b11) begin
                uses = 1'b0; // vsetivli: AVL is immediate
              end else if (insn[31:25] == 7'b1000000) begin
                uses = (insn[19:15] != 5'd0);
              end else begin
                uses = (insn[19:15] != 5'd0);
              end
            end
            default: uses = 1'b0; // OPIVV/OPFVV/OPMVV/OPIVI use no scalar register
          endcase
        end
        default: uses = 1'b0;
      endcase
      vector_uses_scalar_rs1 = uses;
    end
  endfunction

  function automatic logic vector_uses_scalar_rs2(input logic [31:0] insn);
    automatic logic uses;
    begin
      uses = 1'b0;
      unique case (insn[6:0])
        7'b0000111, // vector load
        7'b0100111: begin // vector store
          uses = (insn[27:26] == 2'b10) && (insn[24:20] != 5'd0); // strided rs2
        end
        7'b1010111: begin
          if ((insn[14:12] == 3'b111) && (insn[31:25] == 7'b1000000)) begin
            uses = (insn[24:20] != 5'd0); // vsetvl vtype comes from rs2
          end
        end
        default: uses = 1'b0;
      endcase
      vector_uses_scalar_rs2 = uses;
    end
  endfunction

  function automatic logic vector_uses_scalar_frs1(input logic [31:0] insn);
    return (insn[6:0] == 7'b1010111) && (insn[14:12] == 3'b101); // OPFVF
  endfunction

  function automatic logic vector_needs_scalar_operand(input logic [31:0] insn);
    begin
      vector_needs_scalar_operand = vector_uses_scalar_rs1(insn) ||
                                    vector_uses_scalar_rs2(insn) ||
                                    vector_uses_scalar_frs1(insn);
    end
  endfunction

  // accept_insn (the FSM "request consumed / advance" event) is driven by the
  // resolved-request buffer logic further below: a request leaves the FSM when it
  // either bypasses straight to Ara or is stored into the depth-2 buffer.
  assign resp_valid  = acc_resp_i.acc_resp.resp_valid;
  assign enqueue_ep = heu_vec_valid_i & vec_ep_ready_o;
  assign enqueue_to_pending = enqueue_ep & (state_q != IDLE);
  assign resp_meta_full = (resp_meta_count_q == RespMetaCountW'(RespMetaDepth));
  assign resp_meta_can_push = !resp_meta_full || resp_valid;
  assign capture_operand = selected_slot_found && !UseVTraceScalar &&
                           selected_needs_operand &&
                           !operand_valid_q && !selected_has_next_operand &&
                           scalar_vec_operand_req_ready_i;
  assign resp_has_queued_meta = (resp_meta_count_q != '0);
  assign resp_meta_wb_valid   = resp_has_queued_meta ? resp_meta_wb_valid_q[0] :
                                                       ara_meta_wb_valid;
  assign resp_meta_is_fpr     = resp_has_queued_meta ? resp_meta_is_fpr_q[0] :
                                                       ara_meta_is_fpr;
  assign resp_meta_is_vset    = resp_has_queued_meta ? resp_meta_is_vset_q[0] :
                                                       ara_meta_is_vset;
  assign resp_meta_is_store   = resp_has_queued_meta ? resp_meta_is_store_q[0] :
                                                       ara_meta_is_store;
  assign resp_meta_rd         = resp_has_queued_meta ? resp_meta_rd_q[0] : ara_meta_rd;
  assign resp_meta_ep_id      = resp_has_queued_meta ? resp_meta_ep_id_q[0] : ara_meta_ep_id;
  assign resp_is_vset_wb      = resp_valid && resp_meta_is_vset && (resp_meta_rd != 5'd0);
  // True owning ep_id of the responding instruction (echoed by Ara, reorder-proof).
  assign resp_ep_id_from_trans = acc_resp_i.acc_resp.trans_id[0];
  assign resp_vset_wb_from_trans = acc_resp_i.acc_resp.trans_id[1];
  assign resp_is_scalar_wb    = resp_valid && resp_meta_wb_valid && (resp_meta_rd != 5'd0);
  assign vset_accept_enqueue  = enqueue_ep && input_ep_has_vset_wb;
  assign vset_accept_ack      = resp_is_vset_wb &&
                                ((vset_accept_wait_q != '0) || vset_accept_enqueue);
  assign vset_accept_count_after_pop = vset_accept_wait_q -
                                       CountW'(vset_accept_ack &&
                                               (vset_accept_wait_q != '0));

  assign vtrace_available = (vtrace_idx_q < (VTraceIdxW+1)'(VTraceDepth));
  assign vtrace_mem_idx   = vtrace_available ? vtrace_idx_q[VTraceIdxW-1:0] : '0;
  assign vtrace_entry_raw = vtrace_mem[vtrace_mem_idx];
  assign vtrace_insn      = vtrace_entry_raw[159:128];
  assign vtrace_rs1       = vtrace_entry_raw[127:64];
  assign vtrace_rs2       = vtrace_entry_raw[63:0];

  assign selected_slot_found = ((state_q == DISPATCH) && slot_found) ||
                               ((state_q == IDLE) && enqueue_ep && input_slot_found);
  assign selected_insn       = (state_q == DISPATCH) ? insn_q[slot_idx]
                                                     : heu_vec_insn_i[input_slot_idx];
  assign selected_ep_id      = (state_q == DISPATCH) ? insn_ep_id_q : heu_vec_ep_id_i;
  // Mode travels with the instruction: buffered packet's latched mode in DISPATCH,
  // else the live header (bypass path dispatches the currently-presented packet).
  assign selected_prefetch_hint_valid = (state_q == DISPATCH) ? insn_prefetch_hint_valid_q
                                                              : heu_vec_prefetch_hint_valid_i;
  assign selected_prefetch_disable = (state_q == DISPATCH) ? insn_prefetch_disable_q
                                                           : heu_vec_prefetch_disable_i;
  assign selected_prefetch_mode = (state_q == DISPATCH) ? insn_prefetch_mode_q
                                                        : heu_vec_prefetch_mode_i;
  assign selected_hdv_meta = '{
    hdv_valid           : 1'b1,
    ep_id                : selected_ep_id,
    prefetch_hint_valid  : selected_prefetch_hint_valid,
    prefetch_disable     : selected_prefetch_disable,
    prefetch_mode        : selected_prefetch_mode
  };
  // RVV OPFVF uses scalar FP register rs1 as the .vf operand.  Other vector
  // encodings use integer rs1 for AVL/base/vx operands.
  assign selected_uses_frs1  = vector_uses_scalar_frs1(selected_insn);
  assign selected_uses_rs1   = vector_uses_scalar_rs1(selected_insn);
  assign selected_uses_rs2   = vector_uses_scalar_rs2(selected_insn);
  assign selected_needs_operand = vector_needs_scalar_operand(selected_insn);
  assign selected_operand_port_busy = selected_slot_found && !UseVTraceScalar &&
                                      selected_needs_operand && !operand_valid_q &&
                                      !selected_has_next_operand;
  // Do not bypass on the same cycle an EP is first presented.  Keeping one
  // cycle between EP enqueue and scalar-operand snapshot preserves the existing
  // cross-EP scalar write/read timing; within DISPATCH, the scalar backend's
  // combinational operand port can still feed the Ara request/window directly.
  assign selected_operand_bypass = (state_q == DISPATCH) &&
                                   selected_operand_port_busy &&
                                   scalar_vec_operand_req_ready_i;
  assign next_needs_operand = next_slot_found &&
                              vector_needs_scalar_operand(insn_q[next_slot_idx]);
  // RVV configuration instructions share opcode 0x57 and funct3 OPCFG=111.
  assign selected_is_vset    = selected_insn[6:0] == 7'b1010111 &&
                               selected_insn[14:12] == 3'b111;
  assign selected_is_vstore  = selected_insn[6:0] == 7'b0100111;
  assign selected_scalar_wb_is_fpr = is_vector_fp_scalar_wb(selected_insn);
  assign selected_scalar_wb_valid  = is_vector_scalar_wb(selected_insn);

  always_comb begin
    input_ep_has_vset_wb = 1'b0;
    input_vset_rd        = 5'd0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (heu_vec_insn_valid_i[i] &&
          (heu_vec_insn_i[i][6:0] == 7'b1010111) &&
          (heu_vec_insn_i[i][14:12] == 3'b111) &&
          (heu_vec_insn_i[i][11:7] != 5'd0)) begin
        input_ep_has_vset_wb = 1'b1;
        input_vset_rd        = heu_vec_insn_i[i][11:7];
      end
    end
  end

  // operand request: either the primary slot needs capture, or we are
  // pre-fetching the next slot while the current one dispatches.
  assign selected_has_next_operand = (state_q == DISPATCH) && next_operand_valid_q &&
                                     (next_operand_slot_idx_q == slot_idx);
  assign prefetch_operand_req = (state_q == DISPATCH) && accept_insn && next_slot_found &&
                                next_needs_operand && !UseVTraceScalar &&
                                !next_operand_valid_q && !selected_operand_port_busy;

  assign vec_scalar_operand_req_valid_o = selected_operand_port_busy ||
                                          prefetch_operand_req;
  // Addresses: use pre-fetch target during pre-fetch, else primary slot.
  assign vec_scalar_rs1_addr_o  = prefetch_operand_req ?
                                  (vector_uses_scalar_rs1(insn_q[next_slot_idx]) ?
                                   insn_q[next_slot_idx][19:15] : 5'd0) :
                                  (selected_uses_rs1 ? selected_insn[19:15] : 5'd0);
  assign vec_scalar_rs2_addr_o  = prefetch_operand_req ?
                                  (vector_uses_scalar_rs2(insn_q[next_slot_idx]) ?
                                   insn_q[next_slot_idx][24:20] : 5'd0) :
                                  (selected_uses_rs2 ? selected_insn[24:20] : 5'd0);
  assign vec_scalar_frs1_addr_o = prefetch_operand_req ?
                                  (vector_uses_scalar_frs1(insn_q[next_slot_idx]) ?
                                   insn_q[next_slot_idx][19:15] : 5'd0) :
                                  (selected_uses_frs1 ? selected_insn[19:15] : 5'd0);
  assign vec_scalar_wb_valid_o          = resp_is_scalar_wb;
  assign vec_scalar_wb_rd_o             = resp_meta_rd;
  assign vec_scalar_wb_data_o           = acc_resp_i.acc_resp.result;
  assign vec_scalar_wb_is_fpr_o         = resp_meta_is_fpr;
  assign vec_scalar_wb_is_vset_o        = resp_meta_is_vset;
  // Forward declaration: driven by p_vq_store_scan after vq_* declarations.
  logic vq_has_store;

  // vec_store_inflight_o covers both the response-metadata FIFO (stores that
  // have been sent to Ara) and the command window (stores parked in vq_*).
  // The command-window check (p_vq_store_scan, defined after the vq_*
  // declarations) closes a 1-cycle gap for stores that just entered the
  // window: vq_push and resp_meta write happen in the same cycle, but the
  // registered resp_meta_is_store_q won't reflect the new entry yet.
  assign vec_store_inflight_o = ((resp_meta_count_q != '0) && (|resp_meta_is_store_q)) ||
                                 vq_has_store;


  // ── In-flight vset tracking (A2 RAW interlock hint) ───────────────────────
  // Level signal covering the whole window from "vset EP presented" to "VL
  // writeback".  The combinational `heu_vec_valid_i & input_ep_has_vset_wb`
  // term covers the presentation cycle even before vec_dispatch latches the EP,
  // so a fast scalar backend cannot read the rd before the hint is visible.
  logic       vset_inflight_valid_d, vset_inflight_valid_q;
  logic [4:0] vset_inflight_rd_d,    vset_inflight_rd_q;

  always_comb begin
    vset_inflight_valid_d = vset_inflight_valid_q;
    vset_inflight_rd_d    = vset_inflight_rd_q;
    if (heu_vec_valid_i && input_ep_has_vset_wb) begin
      vset_inflight_valid_d = 1'b1;
      vset_inflight_rd_d    = input_vset_rd;
    end
    if (resp_valid && resp_vset_wb_from_trans) begin
      vset_inflight_valid_d = 1'b0;
    end
    if (flush_i) begin
      vset_inflight_valid_d = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      vset_inflight_valid_q <= 1'b0;
      vset_inflight_rd_q    <= 5'd0;
    end else begin
      vset_inflight_valid_q <= vset_inflight_valid_d;
      vset_inflight_rd_q    <= vset_inflight_rd_d;
    end
  end

  assign vec_scalar_vset_inflight_o    = vset_inflight_valid_q ||
                                         (heu_vec_valid_i && input_ep_has_vset_wb);
  assign vec_scalar_vset_inflight_rd_o = vset_inflight_valid_q ? vset_inflight_rd_q
                                                               : input_vset_rd;

  assign vtrace_empty_error = UseVTraceScalar &&
                              selected_slot_found &&
                              !vtrace_available;
  assign vtrace_mismatch    = UseVTraceScalar &&
                              selected_slot_found &&
                              vtrace_available &&
                              (vtrace_insn != selected_insn);
  assign ara_exception_error = resp_valid && acc_resp_i.acc_resp.exception.valid;
  assign vec_ep_error_o      = error_sticky_q | vtrace_empty_error |
                               vtrace_mismatch | ara_exception_error;

  // ── FSM-intended vector request (before the resolved-request buffer) ───────
  // This is the single request the issue FSM wants to send to Ara this cycle,
  // with its scalar operand already snapshotted into operand_rs*_q.
  logic            fsm_req_valid;
  logic [31:0]     fsm_req_insn;
  logic [XLEN-1:0] fsm_req_rs1;
  logic [XLEN-1:0] fsm_req_rs2;
  logic            fsm_req_is_last; // this is the last vector slot of its EP

  always_comb begin
    automatic logic [NumSlots-1:0] remaining_after_this;
    fsm_req_valid   = 1'b0;
    fsm_req_insn    = selected_insn;
    fsm_req_rs1     = '0;
    fsm_req_rs2     = '0;
    fsm_req_is_last = 1'b0;
    if (selected_slot_found) begin
      fsm_req_valid = !(vtrace_empty_error | vtrace_mismatch) &&
                      (UseVTraceScalar || !selected_needs_operand ||
                       operand_valid_q || selected_has_next_operand ||
                       selected_operand_bypass) &&
                      resp_meta_can_push;
      if (UseVTraceScalar && vtrace_available) begin
        fsm_req_rs1 = vtrace_rs1;
        fsm_req_rs2 = vtrace_rs2;
      end else if (selected_has_next_operand) begin
        fsm_req_rs1 = next_operand_rs1_q;
        fsm_req_rs2 = next_operand_rs2_q;
      end else if (selected_operand_bypass) begin
        fsm_req_rs1 = selected_uses_frs1 ? scalar_vec_frs1_data_i :
                      selected_uses_rs1  ? scalar_vec_rs1_data_i  : '0;
        fsm_req_rs2 = selected_uses_rs2  ? scalar_vec_rs2_data_i  : '0;
      end else begin
        fsm_req_rs1 = operand_rs1_q;
        fsm_req_rs2 = operand_rs2_q;
      end
      // Determine whether this is the last vector slot of its EP.
      // IDLE+enqueue: check against HEU input valid mask.
      // DISPATCH:     check against internal insn_valid_q.
      if (state_q == IDLE) begin
        remaining_after_this = heu_vec_insn_valid_i &
                               ~(NumSlots'(1) << input_slot_idx);
        fsm_req_is_last = !(|remaining_after_this);
      end else begin
        remaining_after_this = insn_valid_q &
                               ~(NumSlots'(1) << slot_idx);
        fsm_req_is_last = !(|remaining_after_this);
      end
    end
  end

  // ── Resolved command window with bypass (vector early issue) ───────────────
  // Decouples the FSM's "request produced" event (operand snapshotted) from
  // Ara's "request accepted" (req_ready).  When Ara back-pressures, the FSM can
  // keep snapshotting operands of following EP slots into this window, so
  // the next EP's vector requests are presented to Ara the moment it frees up.
  // Correctness relies on HEU's early-issue dependency gates: a buffered EP's
  // vector slice may arrive before the current EP retires, but only when its
  // scalar operand reads do not depend on still-pending scalar/vset writes.
  // The snapshot taken at push time is therefore the program-order value.
  //
  // Each vq_entry_t carries the full HDV semantic context of one vector request:
  // insn + operands for Ara, plus ep_id / cmd_class / side-effect flags so the
  // window is self-describing without consulting the resp_meta FIFO.

  // ── Performance-counter declarations (simulation only) ──────────────────
  // Counters are 64-bit; the always_ff body lives after the vq_* / fsm_req_*
  // declarations so it can reference those signals.
  `ifdef FOR_VERIFY
  logic [63:0] cnt_dispatch_slot;         // total vector slots consumed
  logic [63:0] cnt_vq_push;               // requests that entered the window
  logic [63:0] cnt_vq_bypass;             // requests that bypassed straight to Ara
  logic [63:0] cnt_vq_full_stall;         // fsm_req_valid but vq_full blocked push
  logic [63:0] cnt_ara_backpressure;      // vq_serving & !ara_acc : Ara not ready
  logic [63:0] cnt_vq_pop;                // requests popped from window (Ara took)
  logic [63:0] cnt_fsm_idle_could_dispatch; // fsm_req_valid but window empty: bypass possible
  logic [63:0] cnt_ep_acknowledged;       // EPs acknowledged back to HEU
  logic [63:0] cnt_ep_vset_acknowledged;  // EPs acknowledged only after vset wb
  logic [63:0] cnt_operand_wait;          // cycles stuck waiting for scalar operand
	  logic [63:0] cnt_resp_meta_full_stall;  // fsm_req_valid but resp_meta_full blocked
	  logic [63:0] cnt_real_wait_full_stall;  // EP enqueue blocked: real_wait table full
	  logic [63:0] cnt_vq_max_occupancy;      // peak command-window occupancy (1-cycle)
	  logic [63:0] cnt_resp_meta_max;         // peak resp_meta FIFO occupancy (1-cycle)
	  logic [63:0] cnt_dispatch_total_cycles; // total cycles spent in DISPATCH state
	  logic [31:0] pf_probe_stall_cycles_q;
	  `endif

  logic [CmdWindowCountW-1:0] vq_count_q, vq_count_d;
  vq_entry_t [CmdWindowDepth-1:0] vq_q, vq_d;
  logic            vq_serving, vq_full, vq_pop, vq_bypass, vq_push, ara_acc;

  assign vq_serving = (vq_count_q != '0);     // head present -> drain window first
  assign vq_full    = (vq_count_q == CmdWindowCountW'(CmdWindowDepth));

  // Drive Ara from the window head, or bypass the FSM request when window empty.
  // ── HDV → Ara metadata ─────────────────────────────────────────────────
  //  trans_id[0] = response-routing ep_id. trans_id[1] = scalar-visible vset
  //  marker (vset* with rd!=x0). Ara echoes these bits back, so vset writeback
  //  acknowledgement is precise even when normal response metadata is reordered.
  //  Prefetch metadata travels on HDV-only sideband signals aligned with acc_req.
  //
  //  store_pending is intentionally left at 0: Ara's dispatcher forwards it
  //  via core_st_pending_o → core_st_pending_i (internal loopback to VLSU).
  //  HDV does not own the CVA6 store-buffer semantics that this signal
  //  encodes, so setting it would disrupt Ara's internal store tracking.
  always_comb begin
    automatic logic [1:0] req_cmd_class;
    req_cmd_class = selected_is_vset  ? 2'b11 :
                    selected_is_vstore ? 2'b10 :
                    (selected_insn[6:0] == 7'b0000111) ? 2'b01 : 2'b00;

    acc_req_o                     = '0;
    acc_req_hdv_meta_o            = '0;
    acc_req_o.acc_req.resp_ready  = 1'b1; // always ready to receive Ara's response
    acc_req_o.acc_req.inval_ready = 1'b1; // always consume cache-line invalidations
    acc_req_o.acc_req.frm         = fpnew_pkg::RNE;
    if (vq_serving) begin
      acc_req_o.acc_req.req_valid     = resp_meta_can_push;
      acc_req_o.acc_req.insn          = vq_q[0].insn;
      acc_req_o.acc_req.rs1           = vq_q[0].rs1;
      acc_req_o.acc_req.rs2           = vq_q[0].rs2;
      acc_req_o.acc_req.trans_id      = '0;
      acc_req_o.acc_req.trans_id[0]   = vq_q[0].hdv_meta.ep_id;
      acc_req_o.acc_req.trans_id[1]   = (vq_q[0].cmd_class == VQ_CMD_CONFIG) &&
                                        (vq_q[0].insn[11:7] != 5'd0);
      acc_req_hdv_meta_o              = vq_q[0].hdv_meta;
    end else begin
      acc_req_o.acc_req.req_valid     = fsm_req_valid && resp_meta_can_push; // bypass: empty buffer
      acc_req_o.acc_req.insn          = fsm_req_insn;
      acc_req_o.acc_req.rs1           = fsm_req_rs1;
      acc_req_o.acc_req.rs2           = fsm_req_rs2;
      acc_req_o.acc_req.trans_id      = '0;
      acc_req_o.acc_req.trans_id[0]   = selected_ep_id;
      acc_req_o.acc_req.trans_id[1]   = selected_is_vset && (selected_insn[11:7] != 5'd0);
      acc_req_hdv_meta_o              = selected_hdv_meta;
    end
  end

  assign ara_acc   = acc_req_o.acc_req.req_valid & acc_resp_i.acc_resp.req_ready;
  assign vq_bypass = !vq_serving & fsm_req_valid;
  assign vq_pop    = vq_serving & ara_acc;                 // Ara took window head
  // FSM request advances when it bypassed straight to Ara, or got stored.
  assign vq_push   = fsm_req_valid & !(vq_bypass & ara_acc) & (!vq_full | vq_pop);
  assign accept_insn = (vq_bypass & ara_acc) | vq_push;    // FSM "request consumed"

`ifdef FOR_VERIFY
  logic acc_req_stalled_q;
  logic acc_req_vset_wb_marker_expected;
  logic resp_vset_has_wait_target;

  assign acc_req_vset_wb_marker_expected =
      vq_serving ? ((vq_q[0].cmd_class == VQ_CMD_CONFIG) && (vq_q[0].insn[11:7] != 5'd0)) :
                   (selected_is_vset && (selected_insn[11:7] != 5'd0));

  always_comb begin : p_verify_vset_resp_target
    resp_vset_has_wait_target = 1'b0;
    for (int unsigned i = 0; i < RealWaitDepth; i++) begin
      if (real_wait_valid_d[i] && real_wait_has_vset_d[i] &&
          !real_ep_vset_wb_done_q[i] &&
          (real_wait_id_d[i] == resp_ep_id_from_trans)) begin
        resp_vset_has_wait_target = 1'b1;
      end
    end
    if (vset_accept_enqueue && input_ep_has_vset_wb &&
        (heu_vec_ep_id_i == resp_ep_id_from_trans)) begin
      resp_vset_has_wait_target = 1'b1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      acc_req_stalled_q <= 1'b0;
    end else begin
      if (acc_req_stalled_q) begin
        assert ($stable(acc_req_o.acc_req.insn));
        assert ($stable(acc_req_o.acc_req.rs1));
        assert ($stable(acc_req_o.acc_req.rs2));
        assert ($stable(acc_req_o.acc_req.trans_id));
        assert ($stable(acc_req_hdv_meta_o));
      end
      if (acc_req_o.acc_req.req_valid) begin
        assert (acc_req_o.acc_req.trans_id[0] == acc_req_hdv_meta_o.ep_id)
          else $fatal(1, "[HDV_VDU] trans_id[0] ep marker mismatch: trans=%0d meta_ep=%0d",
                      acc_req_o.acc_req.trans_id[0], acc_req_hdv_meta_o.ep_id);
        assert (acc_req_o.acc_req.trans_id[1] == acc_req_vset_wb_marker_expected)
          else $fatal(1, "[HDV_VDU] trans_id[1] vset marker mismatch: trans=%0d expected=%0d insn=0x%08h vq=%0d",
                      acc_req_o.acc_req.trans_id[1], acc_req_vset_wb_marker_expected,
                      acc_req_o.acc_req.insn, vq_serving);
      end
      acc_req_stalled_q <= acc_req_o.acc_req.req_valid && !acc_resp_i.acc_resp.req_ready;
    end
  end
`endif

  assign ara_meta_wb_valid = vq_serving ? vq_q[0].has_scalar_wb : selected_scalar_wb_valid;
  assign ara_meta_is_fpr   = vq_serving ? vq_q[0].wb_is_fpr     : selected_scalar_wb_is_fpr;
  assign ara_meta_is_vset  = vq_serving ? (vq_q[0].cmd_class == VQ_CMD_CONFIG) : selected_is_vset;
  assign ara_meta_is_store = vq_serving ? (vq_q[0].cmd_class == VQ_CMD_STORE)  : selected_is_vstore;
  assign ara_meta_rd       = vq_serving ? vq_q[0].insn[11:7] : selected_insn[11:7];
  assign ara_meta_ep_id    = vq_serving ? vq_q[0].hdv_meta.ep_id : selected_ep_id;

  always_comb begin : p_vq_next
    vq_count_d = vq_count_q;
    vq_d       = vq_q;
    // Pop: shift entries toward the head.
    if (vq_pop) begin
      for (int unsigned i = 0; i < CmdWindowDepth - 1; i++) begin
        vq_d[i] = vq_q[i+1];
      end
      vq_d[CmdWindowDepth-1] = '0;
      vq_count_d = vq_count_q - CmdWindowCountW'(1);
    end
    // Push: append FSM request with full HDV semantic context.
    if (vq_push) begin
      vq_d[vq_count_d].insn          = fsm_req_insn;
      vq_d[vq_count_d].rs1           = fsm_req_rs1;
      vq_d[vq_count_d].rs2           = fsm_req_rs2;
      vq_d[vq_count_d].hdv_meta      = selected_hdv_meta;
      vq_d[vq_count_d].cmd_class     = selected_is_vset  ? VQ_CMD_CONFIG :
                                       selected_is_vstore ? VQ_CMD_STORE  :
                                       (selected_insn[6:0] == 7'b0000111) ? VQ_CMD_LOAD :
                                                                           VQ_CMD_ARITH;
      vq_d[vq_count_d].has_scalar_wb = selected_scalar_wb_valid;
      vq_d[vq_count_d].wb_is_fpr     = selected_scalar_wb_is_fpr;
      vq_d[vq_count_d].is_last_in_ep = fsm_req_is_last;
      vq_count_d = vq_count_d + CmdWindowCountW'(1);
    end
    if (flush_i) begin
      vq_count_d = '0;
      vq_d       = '0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_vq_reg
    if (!rst_ni) begin
      vq_count_q <= '0;
      vq_q       <= '0;
    end else begin
      vq_count_q <= vq_count_d;
      vq_q       <= vq_d;
    end
  end

  // ── Performance-counter update (simulation only) ─────────────────────────
  // Defined here so it can reference vq_*, fsm_req_*, ara_acc, etc., which
  // are all declared above.
  `ifdef FOR_VERIFY
  always_ff @(posedge clk_i or negedge rst_ni) begin : p_perf_counters
    if (!rst_ni) begin
      cnt_dispatch_slot        <= '0;
      cnt_vq_push              <= '0;
      cnt_vq_bypass            <= '0;
      cnt_vq_full_stall        <= '0;
      cnt_ara_backpressure     <= '0;
      cnt_vq_pop               <= '0;
      cnt_fsm_idle_could_dispatch <= '0;
      cnt_ep_acknowledged      <= '0;
      cnt_ep_vset_acknowledged <= '0;
      cnt_operand_wait         <= '0;
      cnt_resp_meta_full_stall <= '0;
      cnt_real_wait_full_stall <= '0;
      cnt_vq_max_occupancy     <= '0;
      cnt_resp_meta_max        <= '0;
      cnt_dispatch_total_cycles <= '0;
    end else begin
      // ── Slot throughput ──────────────────────────────────────────────
      if (accept_insn) begin
        cnt_dispatch_slot <= cnt_dispatch_slot + 64'd1;
      end

      // ── Command-window push / bypass breakdown ───────────────────────
      if (vq_push) begin
        cnt_vq_push <= cnt_vq_push + 64'd1;
      end
      if (vq_bypass && ara_acc) begin
        cnt_vq_bypass <= cnt_vq_bypass + 64'd1;
      end
      if (vq_pop) begin
        cnt_vq_pop <= cnt_vq_pop + 64'd1;
      end

      // ── Stall events ─────────────────────────────────────────────────
      // fsm_req_valid means the FSM has a slot ready; vq_full means the
      // window can't accept it.  vq_pop can make room in the same cycle,
      // so full-stall is !(vq_full | vq_pop).
      if (fsm_req_valid && (vq_full && !vq_pop)) begin
        cnt_vq_full_stall <= cnt_vq_full_stall + 64'd1;
      end
      // Ara backpressure: window has entries but Ara isn't taking them.
      if (vq_serving && !ara_acc) begin
        cnt_ara_backpressure <= cnt_ara_backpressure + 64'd1;
      end
      // FSM has a request and window is empty — bypass is possible.
      if (fsm_req_valid && !vq_serving) begin
        cnt_fsm_idle_could_dispatch <= cnt_fsm_idle_could_dispatch + 64'd1;
      end
      // Operand-wait stall: slot selected but no snapshot yet (real-scalar).
      if (selected_slot_found && !UseVTraceScalar && selected_needs_operand &&
          !operand_valid_q) begin
        cnt_operand_wait <= cnt_operand_wait + 64'd1;
      end
      // resp_meta backpressure: FSM ready but metadata FIFO full.
      if (fsm_req_valid && resp_meta_full && !resp_valid) begin
        cnt_resp_meta_full_stall <= cnt_resp_meta_full_stall + 64'd1;
      end
      // real_wait table backpressure: new EP can't be accepted.
      if (heu_vec_valid_i && !vec_ep_ready_o) begin
        cnt_real_wait_full_stall <= cnt_real_wait_full_stall + 64'd1;
      end

      // ── EP acknowledged (frontend-advance events) ────────────────────
      if (vec_ep_acknowledged_o) begin
        cnt_ep_acknowledged <= cnt_ep_acknowledged + 64'd1;
        // Count vset-wb-delayed acknowledgements: in real-scalar mode the
        // acknowledged EP's real_wait_has_vset tells us whether it waited
        // for vset wb; in vtrace mode the vset_accept_wait_q is still
        // non-zero when the ep_acknowledged_q pulse fires.
        if (!UseVTraceScalar) begin
          if ((real_ep_safe[0] && real_wait_has_vset_q[0]) ||
              (real_ep_safe[1] && real_wait_has_vset_q[1])) begin
            cnt_ep_vset_acknowledged <= cnt_ep_vset_acknowledged + 64'd1;
          end
        end else begin
          if (vset_accept_enqueue || (vset_accept_wait_q != '0)) begin
            cnt_ep_vset_acknowledged <= cnt_ep_vset_acknowledged + 64'd1;
          end
        end
      end

      // ── Peak-occupancy trackers (1-cycle snapshot max) ───────────────
      if (vq_count_q > cnt_vq_max_occupancy[0 +: CmdWindowCountW])
        cnt_vq_max_occupancy <= 64'(vq_count_q);
      if (resp_meta_count_q > cnt_resp_meta_max[0 +: RespMetaCountW])
        cnt_resp_meta_max <= 64'(resp_meta_count_q);

      // ── DISPATCH-state residency ─────────────────────────────────────
      if (state_q == DISPATCH) begin
        cnt_dispatch_total_cycles <= cnt_dispatch_total_cycles + 64'd1;
      end
    end
  end
  `endif

  // Scan the command window for store entries — used by vec_store_inflight_o
  // to close the 1-cycle gap between vq_push and resp_meta registration.
  always_comb begin : p_vq_store_scan
    vq_has_store = 1'b0;
    for (int unsigned i = 0; i < CmdWindowDepth; i++) begin
      if (i < vq_count_q && vq_q[i].cmd_class == VQ_CMD_STORE) begin
        vq_has_store = 1'b1;
      end
    end
  end

  // ── Simulation-time invariants ────────────────────────────────────────────
  `ifdef FOR_VERIFY
  // The wait-table occupancy must never exceed MaxOutstandingVecEPs (the
  // table depth).  real_wait_full should gate vec_ep_ready_o before that
  // happens; this assertion catches any bug that defeats that gate.
  always_ff @(posedge clk_i) begin : p_assert_wait_table_overflow
    if (rst_ni && $past(rst_ni)) begin
      assert ($countones(real_wait_valid_q) <= RealWaitDepth)
        else $fatal(1, "[HDV] real_wait table overflow: %0d entries valid, depth=%0d",
                    $countones(real_wait_valid_q), RealWaitDepth);
    end
  end

  // The response-metadata FIFO must never overflow.  fsm_req_valid already
  // checks resp_meta_can_push; this assertion is a backstop.
  always_ff @(posedge clk_i) begin : p_assert_resp_meta_overflow
    if (rst_ni && $past(rst_ni)) begin
      assert (resp_meta_count_q <= RespMetaDepth)
        else $fatal(1, "[HDV] resp_meta FIFO overflow: count=%0d, depth=%0d",
                    resp_meta_count_q, RespMetaDepth);
    end
  end
  `endif

  // ── Performance-counter readout mux (FOR_VERIFY only) ──────────────────
  // Simple 16-entry mux so testbench / waveform / CSR-interface can sample
  // any counter with a 4-bit selector.  Undefined selects return 0.
  `ifdef FOR_VERIFY
  always_comb begin : p_perf_ctr_readout
    perf_ctr_data_o = '0;
    unique case (perf_ctr_sel_i)
      4'd0:  perf_ctr_data_o = cnt_dispatch_slot;
      4'd1:  perf_ctr_data_o = cnt_vq_push;
      4'd2:  perf_ctr_data_o = cnt_vq_bypass;
      4'd3:  perf_ctr_data_o = cnt_vq_full_stall;
      4'd4:  perf_ctr_data_o = cnt_ara_backpressure;
      4'd5:  perf_ctr_data_o = cnt_vq_pop;
      4'd6:  perf_ctr_data_o = cnt_fsm_idle_could_dispatch;
      4'd7:  perf_ctr_data_o = cnt_ep_acknowledged;
      4'd8:  perf_ctr_data_o = cnt_ep_vset_acknowledged;
      4'd9:  perf_ctr_data_o = cnt_operand_wait;
      4'd10: perf_ctr_data_o = cnt_resp_meta_full_stall;
      4'd11: perf_ctr_data_o = cnt_real_wait_full_stall;
      4'd12: perf_ctr_data_o = cnt_vq_max_occupancy;
      4'd13: perf_ctr_data_o = cnt_resp_meta_max;
      4'd14: perf_ctr_data_o = cnt_dispatch_total_cycles;
      default: perf_ctr_data_o = '0;
    endcase
  end
  `endif

  always_comb begin
    for (int unsigned i = 0; i < RealWaitDepth; i++) begin
      real_ep_safe[i] = real_wait_valid_q[i] &&
                           real_ep_operands_captured_q[i] &&
                           (!real_wait_has_vset_q[i] || real_ep_vset_wb_done_q[i]);
    end
  end

  assign real_wait_full = &real_wait_valid_q;
  assign real_ep_can_acknowledge = !(&(real_wait_valid_q & ~real_ep_safe));
  assign vec_ep_ready_o = !pending_valid_q && (UseVTraceScalar || real_ep_can_acknowledge);
  // In real-scalar mode the EP-acknowledge pulse is driven combinationally from
  // real_ep_safe: that signal depends only on registered wait-table state
  // (operands_captured / valid / vset_wb_done), so there is no combinational
  // loop through HEU.  Routing it through ep_acknowledged_q added an extra
  // register stage, delaying the acknowledge one cycle past the EP operand-capture
  // (vs. the baseline state==DONE acknowledge) and serializing the vsetvli→sub→bnez
  // loop critical path by ~1 cycle/iteration.
  // vtrace mode keeps the registered ep_acknowledged_q acknowledge path unchanged.
  assign vec_ep_acknowledged_o    = UseVTraceScalar ? ep_acknowledged_q
                                                    : (real_ep_safe[0] | real_ep_safe[1]);
  assign vec_ep_acknowledged_id_o = UseVTraceScalar ? ep_acknowledged_id_q
                                                    : (real_ep_safe[0] ? real_wait_id_q[0]
                                                                       : real_wait_id_q[1]);
  assign vec_dispatch_busy_o = (state_q != IDLE) | pending_valid_q |
                               (resp_meta_count_q != '0) |
                               (vset_accept_wait_q != '0) |
                               (|real_wait_valid_q) |
                               operand_valid_q |
                               next_operand_valid_q |
                               (vq_count_q != '0);

  always_comb begin
    state_d      = state_q;
    insn_valid_d = insn_valid_q;
    insn_d       = insn_q;
    insn_ep_id_d = insn_ep_id_q;
    insn_prefetch_hint_valid_d = insn_prefetch_hint_valid_q;
    insn_prefetch_disable_d = insn_prefetch_disable_q;
    insn_prefetch_mode_d = insn_prefetch_mode_q;
    pending_insn_valid_d = pending_insn_valid_q;
    pending_insn_d = pending_insn_q;
    pending_ep_id_d = pending_ep_id_q;
    pending_prefetch_hint_valid_d = pending_prefetch_hint_valid_q;
    pending_prefetch_disable_d = pending_prefetch_disable_q;
    pending_prefetch_mode_d = pending_prefetch_mode_q;
    pending_valid_d = pending_valid_q;
    ep_acknowledged_d = 1'b0;
    ep_acknowledged_id_d = ep_acknowledged_id_q;
    error_sticky_d = error_sticky_q;
    vtrace_idx_d = vtrace_idx_q;
    resp_meta_count_d = resp_meta_count_q;
    resp_meta_wb_valid_d = resp_meta_wb_valid_q;
    resp_meta_is_fpr_d = resp_meta_is_fpr_q;
    resp_meta_is_vset_d = resp_meta_is_vset_q;
    resp_meta_is_store_d = resp_meta_is_store_q;
    resp_meta_rd_d = resp_meta_rd_q;
    resp_meta_ep_id_d = resp_meta_ep_id_q;
    vset_wb_pending_d = vset_wb_pending_q;
    vset_accept_wait_d = vset_accept_wait_q;
    vset_accept_id_d = vset_accept_id_q;
    real_wait_valid_d = real_wait_valid_q;
    real_wait_id_d = real_wait_id_q;
    real_wait_has_vset_d = real_wait_has_vset_q;
    real_ep_operands_captured_d = real_ep_operands_captured_q;
    real_ep_vset_wb_done_d = real_ep_vset_wb_done_q;
    operand_valid_d = operand_valid_q;
    operand_rs1_d = operand_rs1_q;
    operand_rs2_d = operand_rs2_q;
    real_ep_operands_done = 1'b0;
    next_operand_valid_d = next_operand_valid_q;
    next_operand_rs1_d = next_operand_rs1_q;
    next_operand_rs2_d = next_operand_rs2_q;
    next_operand_slot_idx_d = next_operand_slot_idx_q;

    if (vtrace_empty_error | vtrace_mismatch | ara_exception_error) begin
      error_sticky_d = 1'b1;
    end

    if (!UseVTraceScalar) begin
      if (real_ep_safe[0]) begin
        ep_acknowledged_d = 1'b1;
        ep_acknowledged_id_d = real_wait_id_q[0];
        real_wait_valid_d[0] = 1'b0;
        real_wait_has_vset_d[0] = 1'b0;
        real_ep_operands_captured_d[0] = 1'b0;
        real_ep_vset_wb_done_d[0] = 1'b0;
      end else if (real_ep_safe[1]) begin
        ep_acknowledged_d = 1'b1;
        ep_acknowledged_id_d = real_wait_id_q[1];
        real_wait_valid_d[1] = 1'b0;
        real_wait_has_vset_d[1] = 1'b0;
        real_ep_operands_captured_d[1] = 1'b0;
        real_ep_vset_wb_done_d[1] = 1'b0;
      end
    end

    if (enqueue_ep) begin
      if (UseVTraceScalar && !input_ep_has_vset_wb) begin
        ep_acknowledged_d = 1'b1;
        ep_acknowledged_id_d = heu_vec_ep_id_i;
      end
      if (!UseVTraceScalar) begin
        if (!real_wait_valid_d[0]) begin
          real_wait_valid_d[0] = 1'b1;
          real_wait_id_d[0] = heu_vec_ep_id_i;
          real_wait_has_vset_d[0] = input_ep_has_vset_wb;
          real_ep_operands_captured_d[0] = 1'b0;
          // Consume an early-arrived vset writeback latched for this ep_id.
          real_ep_vset_wb_done_d[0] = input_ep_has_vset_wb && vset_wb_pending_q[heu_vec_ep_id_i];
        end else begin
          real_wait_valid_d[1] = 1'b1;
          real_wait_id_d[1] = heu_vec_ep_id_i;
          real_wait_has_vset_d[1] = input_ep_has_vset_wb;
          real_ep_operands_captured_d[1] = 1'b0;
          real_ep_vset_wb_done_d[1] = input_ep_has_vset_wb && vset_wb_pending_q[heu_vec_ep_id_i];
        end
        if (input_ep_has_vset_wb)
          vset_wb_pending_d[heu_vec_ep_id_i] = 1'b0;
      end
    end

    if (enqueue_to_pending) begin
      pending_valid_d = 1'b1;
      pending_insn_valid_d = heu_vec_insn_valid_i;
      pending_insn_d = heu_vec_insn_i;
      pending_ep_id_d = heu_vec_ep_id_i;
      pending_prefetch_hint_valid_d = heu_vec_prefetch_hint_valid_i;
      pending_prefetch_disable_d = heu_vec_prefetch_disable_i;
      pending_prefetch_mode_d = heu_vec_prefetch_mode_i;
    end

    if (capture_operand) begin
      operand_valid_d = 1'b1;
      operand_rs1_d = selected_uses_frs1 ? scalar_vec_frs1_data_i :
                      selected_uses_rs1  ? scalar_vec_rs1_data_i  : '0;
      operand_rs2_d = selected_uses_rs2  ? scalar_vec_rs2_data_i  : '0;
    end

    // Pre-fetch: capture the next slot's operand while the current one
    // is being dispatched.  This hides the 1-cycle operand-read latency
    // for all slots after the first.
    if (prefetch_operand_req && scalar_vec_operand_req_ready_i) begin
      next_operand_valid_d = 1'b1;
      next_operand_rs1_d = vector_uses_scalar_frs1(insn_q[next_slot_idx]) ?
                           scalar_vec_frs1_data_i :
                           vector_uses_scalar_rs1(insn_q[next_slot_idx]) ?
                           scalar_vec_rs1_data_i : '0;
      next_operand_rs2_d = vector_uses_scalar_rs2(insn_q[next_slot_idx]) ?
                           scalar_vec_rs2_data_i : '0;
      next_operand_slot_idx_d = next_slot_idx;
    end
    // Consume the pre-fetched operand when it is used for dispatch.
    if (accept_insn && selected_has_next_operand) begin
      next_operand_valid_d = 1'b0;
      next_operand_slot_idx_d = '0;
    end

    if (resp_valid) begin
      if (resp_meta_count_q != '0) begin
        resp_meta_count_d = resp_meta_count_q - RespMetaCountW'(1);
        for (int unsigned i = 0; i < RespMetaDepth - 1; i++) begin
          resp_meta_wb_valid_d[i] = resp_meta_wb_valid_q[i+1];
          resp_meta_is_fpr_d[i] = resp_meta_is_fpr_q[i+1];
          resp_meta_is_vset_d[i] = resp_meta_is_vset_q[i+1];
          resp_meta_is_store_d[i] = resp_meta_is_store_q[i+1];
          resp_meta_rd_d[i] = resp_meta_rd_q[i+1];
          resp_meta_ep_id_d[i] = resp_meta_ep_id_q[i+1];
        end
        resp_meta_wb_valid_d[RespMetaDepth-1] = 1'b0;
        resp_meta_is_fpr_d[RespMetaDepth-1] = 1'b0;
        resp_meta_is_vset_d[RespMetaDepth-1] = 1'b0;
        resp_meta_is_store_d[RespMetaDepth-1] = 1'b0;
        resp_meta_rd_d[RespMetaDepth-1] = '0;
        resp_meta_ep_id_d[RespMetaDepth-1] = 1'b0;
      end
      if (vset_accept_ack) begin
        if (UseVTraceScalar) begin
          ep_acknowledged_d = 1'b1;
          ep_acknowledged_id_d = (vset_accept_wait_q != '0) ? vset_accept_id_q[0] :
                                                            heu_vec_ep_id_i;
        end
      end
      // Rollback step: mark the waiting EP by the response ep_id.  This matches
      // the older live behavior while the surrounding metadata changes are kept.
      // Use _d for valid/has_vset/id so an EP enqueued THIS cycle (whose vsetvli
      // responds same-cycle in Ara) is not missed; _q for the done bit avoids a
      // combinational loop (done_d depends on this block).
      if (!UseVTraceScalar && resp_valid) begin
        logic vwb_matched;
        vwb_matched = 1'b0;
        for (int unsigned i = 0; i < RealWaitDepth; i++) begin
          if (real_wait_valid_d[i] && real_wait_has_vset_d[i] &&
              !real_ep_vset_wb_done_q[i] &&
              (real_wait_id_d[i] == resp_ep_id_from_trans)) begin
            real_ep_vset_wb_done_d[i] = 1'b1;
            vwb_matched = 1'b1;
          end
        end
        // Early-arrival: the vsetvli writeback (immediate Ara response) landed before
        // its owning EP was enqueued into real_wait. Latch it per ep_id; the
        // enqueue consumes it.
        if (!vwb_matched && resp_is_vset_wb)
          vset_wb_pending_d[resp_ep_id_from_trans] = 1'b1;
      end
    end

    if (vset_accept_ack && (vset_accept_wait_q != '0)) begin
      for (int unsigned i = 0; i < NumSlots - 1; i++) begin
        vset_accept_id_d[i] = vset_accept_id_q[i+1];
      end
      vset_accept_id_d[NumSlots-1] = 1'b0;
    end
    if (vset_accept_enqueue) begin
      vset_accept_id_d[vset_accept_count_after_pop] = heu_vec_ep_id_i;
    end
    if (vset_accept_enqueue || vset_accept_ack) begin
      vset_accept_wait_d = vset_accept_count_after_pop + CountW'(vset_accept_enqueue);
    end

    if (ara_acc) begin
      // Track the request that actually entered Ara.  Requests parked in the
      // command window do not consume response metadata until they later pop.
      if (!(resp_valid && (resp_meta_count_q == '0))) begin
        resp_meta_wb_valid_d[resp_meta_count_d] = ara_meta_wb_valid;
        resp_meta_is_fpr_d[resp_meta_count_d] = ara_meta_is_fpr;
        resp_meta_is_vset_d[resp_meta_count_d] = ara_meta_is_vset;
        resp_meta_is_store_d[resp_meta_count_d] = ara_meta_is_store;
        resp_meta_rd_d[resp_meta_count_d] = ara_meta_rd;
        resp_meta_ep_id_d[resp_meta_count_d] = ara_meta_ep_id;
        resp_meta_count_d = resp_meta_count_d + RespMetaCountW'(1);
      end
    end

    if (accept_insn) begin
      operand_valid_d = 1'b0;
    end

    case (state_q)
      IDLE: begin
        if (enqueue_ep) begin
          insn_valid_d = heu_vec_insn_valid_i;
          insn_d       = heu_vec_insn_i;
          insn_ep_id_d = heu_vec_ep_id_i;
          insn_prefetch_hint_valid_d = heu_vec_prefetch_hint_valid_i;
          insn_prefetch_disable_d = heu_vec_prefetch_disable_i;
          insn_prefetch_mode_d = heu_vec_prefetch_mode_i;
          if (accept_insn) begin
            insn_valid_d[input_slot_idx] = 1'b0;
            if (UseVTraceScalar) begin
              vtrace_idx_d = vtrace_idx_q + 1'b1;
            end
          end
          state_d = (|heu_vec_insn_valid_i) ? DISPATCH : DONE;
          if (!(|insn_valid_d)) begin
            state_d = DONE;
            real_ep_operands_done = 1'b1;
          end
        end
      end

      DISPATCH: begin
        if (accept_insn) begin
          insn_valid_d[slot_idx] = 1'b0; // mark slot as issued
          if (UseVTraceScalar) begin
            vtrace_idx_d = vtrace_idx_q + 1'b1;
          end
        end
        if (|insn_valid_d) begin
          state_d = DISPATCH;
        end else begin
          state_d = DONE;
          real_ep_operands_done = 1'b1;
        end
      end

      WAIT: begin
        state_d = DONE;
      end

      DONE: begin
        if (pending_valid_d) begin
          insn_valid_d = pending_insn_valid_d;
          insn_d = pending_insn_d;
          insn_ep_id_d = pending_ep_id_d;
          insn_prefetch_hint_valid_d = pending_prefetch_hint_valid_d;
          insn_prefetch_disable_d = pending_prefetch_disable_d;
          insn_prefetch_mode_d = pending_prefetch_mode_d;
          pending_valid_d = 1'b0;
          state_d = (|pending_insn_valid_d) ? DISPATCH : IDLE;
        end else begin
          state_d = IDLE;
        end
      end

      default: state_d = IDLE;
    endcase

    if (!UseVTraceScalar && real_ep_operands_done) begin
      for (int unsigned i = 0; i < RealWaitDepth; i++) begin
        if (real_wait_valid_d[i] && (real_wait_id_d[i] == insn_ep_id_d)) begin
          real_ep_operands_captured_d[i] = 1'b1;
        end
      end
    end

    if (flush_i) begin
      state_d      = IDLE;
      insn_valid_d = '0;
      insn_ep_id_d = 1'b0;
      insn_prefetch_hint_valid_d = 1'b0;
      insn_prefetch_disable_d = 1'b0;
      insn_prefetch_mode_d = 2'b0;
      pending_insn_valid_d = '0;
      pending_ep_id_d = 1'b0;
      pending_prefetch_hint_valid_d = 1'b0;
      pending_prefetch_disable_d = 1'b0;
      pending_prefetch_mode_d = 2'b0;
      pending_valid_d = 1'b0;
      ep_acknowledged_d = 1'b0;
      ep_acknowledged_id_d = 1'b0;
      error_sticky_d = 1'b0;
      vtrace_idx_d = '0;
      resp_meta_count_d = '0;
      resp_meta_wb_valid_d = '0;
      resp_meta_is_fpr_d = '0;
      resp_meta_is_vset_d = '0;
      resp_meta_is_store_d = '0;
      resp_meta_rd_d = '0;
      resp_meta_ep_id_d = '0;
      vset_accept_wait_d = '0;
      vset_accept_id_d = '0;
      real_wait_valid_d = '0;
      real_wait_id_d = '0;
      real_wait_has_vset_d = '0;
      real_ep_operands_captured_d = '0;
      real_ep_vset_wb_done_d = '0;
      vset_wb_pending_d = '0;   // drop early-arrival latches so a stale bit can't satisfy a post-flush EP
      operand_valid_d = 1'b0;
      operand_rs1_d = '0;
      operand_rs2_d = '0;
      next_operand_valid_d = 1'b0;
      next_operand_rs1_d = '0;
      next_operand_rs2_d = '0;
      next_operand_slot_idx_d = '0;
    end
  end

`ifdef FOR_VERIFY
  initial begin : init_vtrace_scalar_context
    if (UseVTraceScalar) begin
      automatic int vtrace_fd;
      vtrace_fd = $fopen(VTraceFile, "r");
      if (vtrace_fd == 0) begin
        $fatal(1, "[HDV] failed to open vtrace scalar context: %s", VTraceFile);
      end
      $fclose(vtrace_fd);
      $readmemh(VTraceFile, vtrace_mem);
    end
  end
`endif

`ifdef FOR_VERIFY
  // Runtime (clocked) sim-only assertions: exclude from synthesis.
  always_ff @(posedge clk_i) begin : p_error_report
    if (rst_ni) begin
      if (vtrace_empty_error) begin
        $error("[HDV] vtrace exhausted before vector instruction 0x%08h", selected_insn);
      end
      if (vtrace_mismatch) begin
        $error("[HDV] vtrace mismatch at index %0d: trace=0x%08h heu=0x%08h",
               vtrace_idx_q, vtrace_insn, selected_insn);
      end
      if (ara_exception_error) begin
        $error("[HDV] Ara reported exception for vector dispatch");
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_pf_probe_vec_dispatch
    if (!rst_ni) begin
      pf_probe_stall_cycles_q <= '0;
    end else if ($test$plusargs("HDV_PF_PROBE")) begin
      if (enqueue_ep) begin
        $display("[PFPROBE-VEC] ev=enqueue_ep state=%0d ep=%0d valid=%b insn0=0x%08h insn1=0x%08h insn2=0x%08h insn3=0x%08h pfmode=%0d real_wait=%b safe=%b",
                 state_q, heu_vec_ep_id_i, heu_vec_insn_valid_i, heu_vec_insn_i[0],
                 heu_vec_insn_i[1], heu_vec_insn_i[2], heu_vec_insn_i[3],
                 heu_vec_prefetch_mode_i, real_wait_valid_q, real_ep_safe);
      end

      if (capture_operand) begin
        $display("[PFPROBE-VEC] ev=capture_operand state=%0d ep=%0d slot=%0d insn=0x%08h rs1=x%0d data=0x%0h rs2=x%0d data=0x%0h frs1=%0d selected_next=%0d",
                 state_q, selected_ep_id, (state_q == DISPATCH) ? slot_idx : input_slot_idx,
                 selected_insn, selected_insn[19:15],
                 selected_uses_frs1 ? scalar_vec_frs1_data_i : scalar_vec_rs1_data_i,
                 selected_insn[24:20], scalar_vec_rs2_data_i, selected_uses_frs1,
                 selected_has_next_operand);
      end

      if (prefetch_operand_req && scalar_vec_operand_req_ready_i) begin
        $display("[PFPROBE-VEC] ev=prefetch_operand state=%0d ep=%0d next_slot=%0d insn=0x%08h rs1=x%0d data=0x%0h rs2=x%0d data=0x%0h",
                 state_q, insn_ep_id_q, next_slot_idx, insn_q[next_slot_idx],
                 insn_q[next_slot_idx][19:15],
                 ((insn_q[next_slot_idx][6:0] == 7'b1010111) &&
                  (insn_q[next_slot_idx][14:12] == 3'b101)) ?
                     scalar_vec_frs1_data_i : scalar_vec_rs1_data_i,
                 insn_q[next_slot_idx][24:20], scalar_vec_rs2_data_i);
      end

      if (accept_insn) begin
        $display("[PFPROBE-VEC] ev=accept_insn state=%0d ep=%0d slot=%0d insn=0x%08h rs1=0x%0h rs2=0x%0h bypass=%0d push=%0d pop=%0d vq_count=%0d next_operand=%0d",
                 state_q, selected_ep_id, (state_q == DISPATCH) ? slot_idx : input_slot_idx,
                 fsm_req_insn, fsm_req_rs1, fsm_req_rs2, vq_bypass, vq_push, vq_pop,
                 vq_count_q, selected_has_next_operand);
      end

      if (ara_acc) begin
        $display("[PFPROBE-VEC] ev=ara_acc serving=%0d insn=0x%08h rs1=0x%0h rs2=0x%0h trans_id=0x%0h meta_rd=x%0d meta_vset=%0d meta_store=%0d",
                 vq_serving, acc_req_o.acc_req.insn, acc_req_o.acc_req.rs1,
                 acc_req_o.acc_req.rs2, acc_req_o.acc_req.trans_id,
                 ara_meta_rd, ara_meta_is_vset, ara_meta_is_store);
      end

      if (vec_ep_acknowledged_o) begin
        $display("[PFPROBE-VEC] ev=vec_ack id=%0d real_wait=%b safe=%b operands_captured=%b vset_done=%b",
                 vec_ep_acknowledged_id_o, real_wait_valid_q, real_ep_safe,
                 real_ep_operands_captured_q, real_ep_vset_wb_done_q);
      end

      if ((acc_req_o.acc_req.req_valid && !acc_resp_i.acc_resp.req_ready) ||
          (vq_serving && !ara_acc) || resp_meta_full || real_wait_full) begin
        pf_probe_stall_cycles_q <= pf_probe_stall_cycles_q + 32'd1;
        if ((pf_probe_stall_cycles_q <= 32'd8) ||
            ((pf_probe_stall_cycles_q[9:0] == 10'h0) &&
             (pf_probe_stall_cycles_q != 32'd0))) begin
          $display("[PFPROBE-VEC] ev=stall cyc=%0d state=%0d state_d=%0d acc_v=%0d acc_r=%0d ara_acc=%0d vq_serving=%0d vq_count=%0d vq_full=%0d vq_head=0x%08h head_ep=%0d head_cls=%0d resp_meta=%0d resp_full=%0d real_wait=%b safe=%b operands=%b vset_done=%b pending=%0d insn_valid=%b selected_found=%0d fsm_req=%0d selected=0x%08h",
                   pf_probe_stall_cycles_q, state_q, state_d, acc_req_o.acc_req.req_valid,
                   acc_resp_i.acc_resp.req_ready, ara_acc, vq_serving, vq_count_q,
                   vq_full, vq_q[0].insn, vq_q[0].hdv_meta.ep_id, vq_q[0].cmd_class,
                   resp_meta_count_q, resp_meta_full, real_wait_valid_q, real_ep_safe,
                   real_ep_operands_captured_q, real_ep_vset_wb_done_q, pending_valid_q,
                   insn_valid_q, selected_slot_found, fsm_req_valid, selected_insn);
        end
      end else begin
        pf_probe_stall_cycles_q <= '0;
      end
    end else begin
      pf_probe_stall_cycles_q <= '0;
    end
  end
`endif

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q      <= IDLE;
      insn_valid_q <= '0;
      insn_q       <= '0;
      insn_ep_id_q <= 1'b0;
      insn_prefetch_hint_valid_q <= 1'b0;
      insn_prefetch_disable_q <= 1'b0;
      insn_prefetch_mode_q <= 2'b0;
      pending_insn_valid_q <= '0;
      pending_insn_q <= '0;
      pending_ep_id_q <= 1'b0;
      pending_prefetch_hint_valid_q <= 1'b0;
      pending_prefetch_disable_q <= 1'b0;
      pending_prefetch_mode_q <= 2'b0;
      pending_valid_q <= 1'b0;
      ep_acknowledged_q <= 1'b0;
      ep_acknowledged_id_q <= 1'b0;
      error_sticky_q <= 1'b0;
      vtrace_idx_q <= '0;
      resp_meta_count_q <= '0;
      resp_meta_wb_valid_q <= '0;
      resp_meta_is_fpr_q <= '0;
      resp_meta_is_vset_q <= '0;
      resp_meta_is_store_q <= '0;
      resp_meta_rd_q <= '0;
      resp_meta_ep_id_q <= '0;
      vset_accept_wait_q <= '0;
      vset_accept_id_q <= '0;
      real_wait_valid_q <= '0;
      real_wait_id_q <= '0;
      real_wait_has_vset_q <= '0;
      real_ep_operands_captured_q <= '0;
      real_ep_vset_wb_done_q <= '0;
      vset_wb_pending_q <= '0;
      operand_valid_q <= 1'b0;
      operand_rs1_q <= '0;
      operand_rs2_q <= '0;
      next_operand_valid_q <= 1'b0;
      next_operand_rs1_q  <= '0;
      next_operand_rs2_q  <= '0;
      next_operand_slot_idx_q <= '0;
    end else begin
      state_q      <= state_d;
      insn_valid_q <= insn_valid_d;
      insn_q       <= insn_d;
      insn_ep_id_q <= insn_ep_id_d;
      insn_prefetch_hint_valid_q <= insn_prefetch_hint_valid_d;
      insn_prefetch_disable_q <= insn_prefetch_disable_d;
      insn_prefetch_mode_q <= insn_prefetch_mode_d;
      pending_insn_valid_q <= pending_insn_valid_d;
      pending_insn_q <= pending_insn_d;
      pending_ep_id_q <= pending_ep_id_d;
      pending_prefetch_hint_valid_q <= pending_prefetch_hint_valid_d;
      pending_prefetch_disable_q <= pending_prefetch_disable_d;
      pending_prefetch_mode_q <= pending_prefetch_mode_d;
      pending_valid_q <= pending_valid_d;
      ep_acknowledged_q <= ep_acknowledged_d;
      ep_acknowledged_id_q <= ep_acknowledged_id_d;
      error_sticky_q <= error_sticky_d;
      vtrace_idx_q <= vtrace_idx_d;
      resp_meta_count_q <= resp_meta_count_d;
      resp_meta_wb_valid_q <= resp_meta_wb_valid_d;
      resp_meta_is_fpr_q <= resp_meta_is_fpr_d;
      resp_meta_is_vset_q <= resp_meta_is_vset_d;
      resp_meta_is_store_q <= resp_meta_is_store_d;
      resp_meta_rd_q <= resp_meta_rd_d;
      resp_meta_ep_id_q <= resp_meta_ep_id_d;
      vset_accept_wait_q <= vset_accept_wait_d;
      vset_accept_id_q <= vset_accept_id_d;
      real_wait_valid_q <= real_wait_valid_d;
      real_wait_id_q <= real_wait_id_d;
      real_wait_has_vset_q <= real_wait_has_vset_d;
      real_ep_operands_captured_q <= real_ep_operands_captured_d;
      real_ep_vset_wb_done_q <= real_ep_vset_wb_done_d;
      vset_wb_pending_q <= vset_wb_pending_d;
      operand_valid_q <= operand_valid_d;
      operand_rs1_q <= operand_rs1_d;
      operand_rs2_q <= operand_rs2_d;
      next_operand_valid_q <= next_operand_valid_d;
      next_operand_rs1_q  <= next_operand_rs1_d;
      next_operand_rs2_q  <= next_operand_rs2_d;
      next_operand_slot_idx_q <= next_operand_slot_idx_d;
    end
  end

endmodule : hdv_vec_dispatch_unit
