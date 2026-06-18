// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Vector dispatch adapter: serializes HEU's multi-slot vector execute-packet
// into single-instruction acc_req transactions for Ara.  It buffers the current
// EP internally and keeps issuing vector slots whenever Ara can accept them.
// vec_heu_accepted_o is the EP acceptance pulse back to HEU.  In vtrace mode,
// EPs without a scalar-visible vset write are accepted when enqueued because
// operands come from an immutable trace.  With the real scalar backend, accepted
// is delayed until all vector requests in the EP have consumed their scalar
// operands.  EPs with vset rd!=x0 additionally wait for that vset response
// writeback, preserving scalar reads of vl/rd.
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
`ifndef SYNTHESIS
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
  output logic                              vec_heu_ready_o,    // accept when pending skid buffer is free
  input  logic [NumSlots-1:0]               heu_vec_insn_valid_i, // which slots are vector
  input  logic [NumSlots-1:0][31:0]         heu_vec_insn_i,       // assembled 32-bit insns
  input  logic                              heu_vec_ep_id_i,

  // ── Acceptance pulse back to HEU (1-cycle) ────────────────────────────────
  output logic                              vec_heu_accepted_o,
  output logic                              vec_heu_accepted_id_o,
  output logic                              vec_heu_error_o,
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

  // ── Vector configuration writeback to scalar backend ────────────────────
  // Ara returns the new VL in the response result of vsetvli/vsetivli/vsetvl.
  output logic                              vec_scalar_vset_wb_valid_o,
  output logic [4:0]                        vec_scalar_vset_wb_rd_o,
  output logic [XLEN-1:0]                   vec_scalar_vset_wb_data_o,

  // ── In-flight vset hazard hint to scalar backend (A2 fix) ───────────────
  // Asserted from the moment an EP carrying a vset (rd!=x0) is presented until
  // its VL writeback lands, so the scalar backend can stall a dependent scalar
  // that reads that rd.  This window is already covered by the EP's vector
  // accept wait, so the interlock is performance-neutral.
  output logic                              vec_scalar_vset_inflight_o,
  output logic [4:0]                        vec_scalar_vset_inflight_rd_o,

  // ── Ara accelerator request / response (replaces CVA6→Ara path) ──────────
  output cva6_to_acc_t                      acc_req_o,
  input  acc_to_cva6_t                      acc_resp_i
);

  localparam int unsigned SlotIdxW = (NumSlots > 1) ? $clog2(NumSlots) : 1;
  localparam int unsigned VTraceIdxW = (VTraceDepth > 1) ? $clog2(VTraceDepth) : 1;
  localparam int unsigned VTraceEntryWidth = 32 + 64 + 64;
  localparam int unsigned CountW = (NumSlots > 1) ? $clog2(NumSlots + 1) : 1;
  localparam int unsigned RespMetaDepth = 16;
  localparam int unsigned RespMetaCountW = $clog2(RespMetaDepth + 1);
  localparam int unsigned RealWaitDepth = 2;

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
  logic [NumSlots-1:0]       pending_insn_valid_d, pending_insn_valid_q;
  logic [NumSlots-1:0][31:0] pending_insn_d,       pending_insn_q;
  logic                      pending_ep_id_d, pending_ep_id_q;
  logic                      pending_valid_d,      pending_valid_q;
  logic                      ep_enqueued_d,        ep_enqueued_q;
  logic                      ep_enqueued_id_d,     ep_enqueued_id_q;
  logic                      error_sticky_d,       error_sticky_q;
  logic [VTraceIdxW:0]        vtrace_idx_d, vtrace_idx_q;
  logic [VTraceEntryWidth-1:0] vtrace_mem [VTraceDepth];
  logic [VTraceEntryWidth-1:0] vtrace_entry_raw;
  logic [VTraceIdxW-1:0]       vtrace_mem_idx;
  logic [RespMetaCountW-1:0]     resp_meta_count_d, resp_meta_count_q;
  logic [RespMetaDepth-1:0]      resp_meta_is_vset_d, resp_meta_is_vset_q;
  logic [RespMetaDepth-1:0][4:0] resp_meta_rd_d, resp_meta_rd_q;
  logic [RespMetaDepth-1:0]      resp_meta_ep_id_d, resp_meta_ep_id_q;
  logic [CountW-1:0]             vset_accept_wait_d, vset_accept_wait_q;
  logic [NumSlots-1:0]           vset_accept_id_d, vset_accept_id_q;
  logic [RealWaitDepth-1:0]      real_wait_valid_d, real_wait_valid_q;
  logic [RealWaitDepth-1:0]      real_wait_id_d, real_wait_id_q;
  logic [RealWaitDepth-1:0]      real_wait_has_vset_d, real_wait_has_vset_q;
  logic [RealWaitDepth-1:0]      real_wait_drained_d, real_wait_drained_q;
  logic [RealWaitDepth-1:0]      real_wait_vset_seen_d, real_wait_vset_seen_q;
  logic                         operand_valid_d, operand_valid_q;
  logic [XLEN-1:0]              operand_rs1_d, operand_rs1_q;
  logic [XLEN-1:0]              operand_rs2_d, operand_rs2_q;
  logic                         selected_is_vset;
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
  logic                        resp_is_vset_wb;
  logic                        real_wait_full;
  logic                        real_wait_can_accept;
  logic [RealWaitDepth-1:0]    real_wait_ready;

  // Priority-encoders: find the lowest-index valid slot in the buffered EP or
  // in a freshly arriving EP.  The latter lets IDLE accept an EP and issue its
  // first vector instruction to Ara in the same cycle.
  logic                  slot_found;
  logic [SlotIdxW-1:0]   slot_idx;
  logic                  input_slot_found;
  logic [SlotIdxW-1:0]   input_slot_idx;
  logic                  selected_slot_found;
  logic [31:0]           selected_insn;
  logic                  selected_uses_frs1;

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

  logic accept_insn;      // Ara accepted the instruction this cycle
  logic resp_valid;       // Ara produced the CV-X-IF response this cycle
  logic resp_has_queued_meta;
  logic resp_meta_is_vset;
  logic [4:0] resp_meta_rd;
  logic resp_meta_ep_id;
  logic enqueue_ep;
  logic enqueue_to_pending;
  logic capture_operand;
  logic vset_accept_enqueue;
  logic vset_accept_ack;
  logic [CountW-1:0] vset_accept_count_after_pop;
  logic real_ep_drained;
  logic selected_ep_id;

  // accept_insn (the FSM "request consumed / advance" event) is driven by the
  // resolved-request buffer logic further below: a request leaves the FSM when it
  // either bypasses straight to Ara or is stored into the depth-2 buffer.
  assign resp_valid  = acc_resp_i.acc_resp.resp_valid;
  assign enqueue_ep = heu_vec_valid_i & vec_heu_ready_o;
  assign enqueue_to_pending = enqueue_ep & (state_q != IDLE);
  assign resp_meta_full = (resp_meta_count_q == RespMetaCountW'(RespMetaDepth));
  assign resp_meta_can_push = !resp_meta_full || resp_valid;
  assign capture_operand = selected_slot_found && !UseVTraceScalar &&
                           !operand_valid_q && scalar_vec_operand_req_ready_i;
  assign resp_has_queued_meta = (resp_meta_count_q != '0);
  assign resp_meta_is_vset    = resp_has_queued_meta ? resp_meta_is_vset_q[0] : selected_is_vset;
  assign resp_meta_rd         = resp_has_queued_meta ? resp_meta_rd_q[0] : selected_insn[11:7];
  assign resp_meta_ep_id      = resp_has_queued_meta ? resp_meta_ep_id_q[0] : selected_ep_id;
  assign resp_is_vset_wb      = resp_valid && resp_meta_is_vset && (resp_meta_rd != 5'd0);
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
  // RVV OPFVF uses scalar FP register rs1 as the .vf operand.  Other vector
  // encodings use integer rs1 for AVL/base/vx operands.
  assign selected_uses_frs1  = selected_insn[6:0] == 7'b1010111 &&
                               selected_insn[14:12] == 3'b101;
  // RVV configuration instructions share opcode 0x57 and funct3 OPCFG=111.
  assign selected_is_vset    = selected_insn[6:0] == 7'b1010111 &&
                               selected_insn[14:12] == 3'b111;

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

  assign vec_scalar_operand_req_valid_o = selected_slot_found && !UseVTraceScalar &&
                                          !operand_valid_q;
  assign vec_scalar_rs1_addr_o          = selected_insn[19:15];
  assign vec_scalar_rs2_addr_o          = selected_insn[24:20];
  assign vec_scalar_frs1_addr_o         = selected_insn[19:15];
  assign vec_scalar_vset_wb_valid_o     = resp_is_vset_wb;
  assign vec_scalar_vset_wb_rd_o        = resp_meta_rd;
  assign vec_scalar_vset_wb_data_o      = acc_resp_i.acc_resp.result;

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
    if (vec_scalar_vset_wb_valid_o) begin
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
  assign vec_heu_error_o     = error_sticky_q | vtrace_empty_error |
                               vtrace_mismatch | ara_exception_error;

  // ── FSM-intended vector request (before the resolved-request buffer) ───────
  // This is the single request the issue FSM wants to send to Ara this cycle,
  // with its scalar operand already snapshotted into operand_rs*_q.
  logic            fsm_req_valid;
  logic [31:0]     fsm_req_insn;
  logic [XLEN-1:0] fsm_req_rs1;
  logic [XLEN-1:0] fsm_req_rs2;

  always_comb begin
    fsm_req_valid = 1'b0;
    fsm_req_insn  = selected_insn;
    fsm_req_rs1   = '0;
    fsm_req_rs2   = '0;
    if (selected_slot_found) begin
      fsm_req_valid = !(vtrace_empty_error | vtrace_mismatch) &&
                      (UseVTraceScalar || operand_valid_q) &&
                      resp_meta_can_push;
      if (UseVTraceScalar && vtrace_available) begin
        fsm_req_rs1 = vtrace_rs1;
        fsm_req_rs2 = vtrace_rs2;
      end else begin
        fsm_req_rs1 = operand_rs1_q;
        fsm_req_rs2 = operand_rs2_q;
      end
    end
  end

  // ── Depth-2 resolved-request buffer with bypass (vector early issue) ───────
  // Decouples the FSM's "request produced" event (operand snapshotted) from
  // Ara's "request accepted" (req_ready).  When Ara back-pressures, the FSM can
  // keep snapshotting operands of the following EP's slots into this buffer, so
  // the next EP's vector requests are presented to Ara the moment it frees up.
  // Correctness relies on HEU's early-issue dependency gates: a buffered EP's
  // vector slice may arrive before the current EP retires, but only when its
  // scalar operand reads do not depend on still-pending scalar/vset writes.
  // The snapshot taken at push time is therefore the program-order value.
  logic            vq0_valid_q, vq0_valid_d;
  logic            vq1_valid_q, vq1_valid_d;
  logic [31:0]     vq0_insn_q, vq0_insn_d, vq1_insn_q, vq1_insn_d;
  logic [XLEN-1:0] vq0_rs1_q, vq0_rs1_d, vq1_rs1_q, vq1_rs1_d;
  logic [XLEN-1:0] vq0_rs2_q, vq0_rs2_d, vq1_rs2_q, vq1_rs2_d;
  logic            vq_serving, vq_full, vq_pop, vq_bypass, vq_push, ara_acc;

  assign vq_serving = vq0_valid_q;            // head present -> drain buffer first
  assign vq_full    = vq0_valid_q & vq1_valid_q;

  // Drive Ara from the buffer head, or bypass the FSM request when buffer empty.
  always_comb begin
    acc_req_o                     = '0;
    acc_req_o.acc_req.resp_ready  = 1'b1; // always ready to receive Ara's response
    acc_req_o.acc_req.inval_ready = 1'b1; // always consume cache-line invalidations
    acc_req_o.acc_req.frm         = fpnew_pkg::RNE;
    if (vq_serving) begin
      acc_req_o.acc_req.req_valid = 1'b1;
      acc_req_o.acc_req.insn      = vq0_insn_q;
      acc_req_o.acc_req.rs1       = vq0_rs1_q;
      acc_req_o.acc_req.rs2       = vq0_rs2_q;
    end else begin
      acc_req_o.acc_req.req_valid = fsm_req_valid; // bypass: empty buffer
      acc_req_o.acc_req.insn      = fsm_req_insn;
      acc_req_o.acc_req.rs1       = fsm_req_rs1;
      acc_req_o.acc_req.rs2       = fsm_req_rs2;
    end
  end

  assign ara_acc   = acc_req_o.acc_req.req_valid & acc_resp_i.acc_resp.req_ready;
  assign vq_bypass = !vq_serving & fsm_req_valid;
  assign vq_pop    = vq_serving & ara_acc;                 // Ara took buffer head
  // FSM request advances when it bypassed straight to Ara, or got stored.
  assign vq_push   = fsm_req_valid & !(vq_bypass & ara_acc) & (!vq_full | vq_pop);
  assign accept_insn = (vq_bypass & ara_acc) | vq_push;    // FSM "request consumed"

  always_comb begin : p_vq_next
    vq0_valid_d = vq0_valid_q; vq0_insn_d = vq0_insn_q;
    vq0_rs1_d   = vq0_rs1_q;   vq0_rs2_d  = vq0_rs2_q;
    vq1_valid_d = vq1_valid_q; vq1_insn_d = vq1_insn_q;
    vq1_rs1_d   = vq1_rs1_q;   vq1_rs2_d  = vq1_rs2_q;
    // Pop: shift vq1 -> vq0.
    if (vq_pop) begin
      vq0_valid_d = vq1_valid_q;
      vq0_insn_d  = vq1_insn_q; vq0_rs1_d = vq1_rs1_q; vq0_rs2_d = vq1_rs2_q;
      vq1_valid_d = 1'b0;
    end
    // Push: append FSM request at the first empty slot (after pop).
    if (vq_push) begin
      if (!vq0_valid_d) begin
        vq0_valid_d = 1'b1; vq0_insn_d = fsm_req_insn;
        vq0_rs1_d   = fsm_req_rs1; vq0_rs2_d = fsm_req_rs2;
      end else begin
        vq1_valid_d = 1'b1; vq1_insn_d = fsm_req_insn;
        vq1_rs1_d   = fsm_req_rs1; vq1_rs2_d = fsm_req_rs2;
      end
    end
    if (flush_i) begin
      vq0_valid_d = 1'b0;
      vq1_valid_d = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_vq_reg
    if (!rst_ni) begin
      vq0_valid_q <= 1'b0; vq0_insn_q <= '0; vq0_rs1_q <= '0; vq0_rs2_q <= '0;
      vq1_valid_q <= 1'b0; vq1_insn_q <= '0; vq1_rs1_q <= '0; vq1_rs2_q <= '0;
    end else begin
      vq0_valid_q <= vq0_valid_d; vq0_insn_q <= vq0_insn_d;
      vq0_rs1_q   <= vq0_rs1_d;   vq0_rs2_q  <= vq0_rs2_d;
      vq1_valid_q <= vq1_valid_d; vq1_insn_q <= vq1_insn_d;
      vq1_rs1_q   <= vq1_rs1_d;   vq1_rs2_q  <= vq1_rs2_d;
    end
  end

  always_comb begin
    for (int unsigned i = 0; i < RealWaitDepth; i++) begin
      real_wait_ready[i] = real_wait_valid_q[i] &&
                           real_wait_drained_q[i] &&
                           (!real_wait_has_vset_q[i] || real_wait_vset_seen_q[i]);
    end
  end

  assign real_wait_full = &real_wait_valid_q;
  assign real_wait_can_accept = !(&(real_wait_valid_q & ~real_wait_ready));
  assign vec_heu_ready_o = !pending_valid_q && (UseVTraceScalar || real_wait_can_accept);
  // In real-scalar mode the EP-accept pulse can be driven combinationally from
  // real_wait_ready: that signal depends only on registered wait-table state
  // (drained/valid/vset_seen), so there is no combinational loop through HEU.
  // Routing it through ep_enqueued_q added an extra register stage, delaying the
  // accept one cycle past the EP drain (vs. the baseline state==DONE accept) and
  // serializing the vsetvli->sub->bnez loop critical path by ~1 cycle/iteration.
  // vtrace mode keeps the registered ep_enqueued_q accept path unchanged.
  assign vec_heu_accepted_o    = UseVTraceScalar ? ep_enqueued_q
                                                 : (real_wait_ready[0] | real_wait_ready[1]);
  assign vec_heu_accepted_id_o = UseVTraceScalar ? ep_enqueued_id_q
                                                 : (real_wait_ready[0] ? real_wait_id_q[0]
                                                                       : real_wait_id_q[1]);
  assign vec_dispatch_busy_o = (state_q != IDLE) | pending_valid_q |
                               (resp_meta_count_q != '0) |
                               (vset_accept_wait_q != '0) |
                               (|real_wait_valid_q) |
                               operand_valid_q |
                               vq0_valid_q | vq1_valid_q;

  always_comb begin
    state_d      = state_q;
    insn_valid_d = insn_valid_q;
    insn_d       = insn_q;
    insn_ep_id_d = insn_ep_id_q;
    pending_insn_valid_d = pending_insn_valid_q;
    pending_insn_d = pending_insn_q;
    pending_ep_id_d = pending_ep_id_q;
    pending_valid_d = pending_valid_q;
    ep_enqueued_d = 1'b0;
    ep_enqueued_id_d = ep_enqueued_id_q;
    error_sticky_d = error_sticky_q;
    vtrace_idx_d = vtrace_idx_q;
    resp_meta_count_d = resp_meta_count_q;
    resp_meta_is_vset_d = resp_meta_is_vset_q;
    resp_meta_rd_d = resp_meta_rd_q;
    resp_meta_ep_id_d = resp_meta_ep_id_q;
    vset_accept_wait_d = vset_accept_wait_q;
    vset_accept_id_d = vset_accept_id_q;
    real_wait_valid_d = real_wait_valid_q;
    real_wait_id_d = real_wait_id_q;
    real_wait_has_vset_d = real_wait_has_vset_q;
    real_wait_drained_d = real_wait_drained_q;
    real_wait_vset_seen_d = real_wait_vset_seen_q;
    operand_valid_d = operand_valid_q;
    operand_rs1_d = operand_rs1_q;
    operand_rs2_d = operand_rs2_q;
    real_ep_drained = 1'b0;

    if (vtrace_empty_error | vtrace_mismatch | ara_exception_error) begin
      error_sticky_d = 1'b1;
    end

    if (!UseVTraceScalar) begin
      if (real_wait_ready[0]) begin
        ep_enqueued_d = 1'b1;
        ep_enqueued_id_d = real_wait_id_q[0];
        real_wait_valid_d[0] = 1'b0;
        real_wait_has_vset_d[0] = 1'b0;
        real_wait_drained_d[0] = 1'b0;
        real_wait_vset_seen_d[0] = 1'b0;
      end else if (real_wait_ready[1]) begin
        ep_enqueued_d = 1'b1;
        ep_enqueued_id_d = real_wait_id_q[1];
        real_wait_valid_d[1] = 1'b0;
        real_wait_has_vset_d[1] = 1'b0;
        real_wait_drained_d[1] = 1'b0;
        real_wait_vset_seen_d[1] = 1'b0;
      end
    end

    if (enqueue_ep) begin
      if (UseVTraceScalar && !input_ep_has_vset_wb) begin
        ep_enqueued_d = 1'b1;
        ep_enqueued_id_d = heu_vec_ep_id_i;
      end
      if (!UseVTraceScalar) begin
        if (!real_wait_valid_d[0]) begin
          real_wait_valid_d[0] = 1'b1;
          real_wait_id_d[0] = heu_vec_ep_id_i;
          real_wait_has_vset_d[0] = input_ep_has_vset_wb;
          real_wait_drained_d[0] = 1'b0;
          real_wait_vset_seen_d[0] = 1'b0;
        end else begin
          real_wait_valid_d[1] = 1'b1;
          real_wait_id_d[1] = heu_vec_ep_id_i;
          real_wait_has_vset_d[1] = input_ep_has_vset_wb;
          real_wait_drained_d[1] = 1'b0;
          real_wait_vset_seen_d[1] = 1'b0;
        end
      end
    end

    if (enqueue_to_pending) begin
      pending_valid_d = 1'b1;
      pending_insn_valid_d = heu_vec_insn_valid_i;
      pending_insn_d = heu_vec_insn_i;
      pending_ep_id_d = heu_vec_ep_id_i;
    end

    if (capture_operand) begin
      operand_valid_d = 1'b1;
      operand_rs1_d = selected_uses_frs1 ? scalar_vec_frs1_data_i :
                                           scalar_vec_rs1_data_i;
      operand_rs2_d = scalar_vec_rs2_data_i;
    end

    if (resp_valid) begin
      if (resp_meta_count_q != '0) begin
        resp_meta_count_d = resp_meta_count_q - RespMetaCountW'(1);
        for (int unsigned i = 0; i < RespMetaDepth - 1; i++) begin
          resp_meta_is_vset_d[i] = resp_meta_is_vset_q[i+1];
          resp_meta_rd_d[i] = resp_meta_rd_q[i+1];
          resp_meta_ep_id_d[i] = resp_meta_ep_id_q[i+1];
        end
        resp_meta_is_vset_d[RespMetaDepth-1] = 1'b0;
        resp_meta_rd_d[RespMetaDepth-1] = '0;
        resp_meta_ep_id_d[RespMetaDepth-1] = 1'b0;
      end
      if (vset_accept_ack) begin
        if (UseVTraceScalar) begin
          ep_enqueued_d = 1'b1;
          ep_enqueued_id_d = (vset_accept_wait_q != '0) ? vset_accept_id_q[0] :
                                                            heu_vec_ep_id_i;
        end
      end
      if (!UseVTraceScalar && resp_is_vset_wb) begin
        for (int unsigned i = 0; i < RealWaitDepth; i++) begin
          if (real_wait_valid_d[i] && (real_wait_id_d[i] == resp_meta_ep_id)) begin
            real_wait_vset_seen_d[i] = 1'b1;
          end
        end
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

    if (accept_insn) begin
      operand_valid_d = 1'b0;
      // If Ara responds in the same cycle and there is no older queued
      // response metadata, this response belongs to the instruction just
      // accepted and is consumed directly above.
      if (!(resp_valid && (resp_meta_count_q == '0))) begin
        resp_meta_is_vset_d[resp_meta_count_d] = selected_is_vset;
        resp_meta_rd_d[resp_meta_count_d] = selected_insn[11:7];
        resp_meta_ep_id_d[resp_meta_count_d] = selected_ep_id;
        resp_meta_count_d = resp_meta_count_d + RespMetaCountW'(1);
      end
    end

    case (state_q)
      IDLE: begin
        if (enqueue_ep) begin
          insn_valid_d = heu_vec_insn_valid_i;
          insn_d       = heu_vec_insn_i;
          insn_ep_id_d = heu_vec_ep_id_i;
          if (accept_insn) begin
            insn_valid_d[input_slot_idx] = 1'b0;
            if (UseVTraceScalar) begin
              vtrace_idx_d = vtrace_idx_q + 1'b1;
            end
          end
          state_d = (|heu_vec_insn_valid_i) ? DISPATCH : DONE;
          if (!(|insn_valid_d)) begin
            state_d = DONE;
            real_ep_drained = 1'b1;
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
          real_ep_drained = 1'b1;
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
          pending_valid_d = 1'b0;
          state_d = (|pending_insn_valid_d) ? DISPATCH : IDLE;
        end else begin
          state_d = IDLE;
        end
      end

      default: state_d = IDLE;
    endcase

    if (!UseVTraceScalar && real_ep_drained) begin
      for (int unsigned i = 0; i < RealWaitDepth; i++) begin
        if (real_wait_valid_d[i] && (real_wait_id_d[i] == insn_ep_id_d)) begin
          real_wait_drained_d[i] = 1'b1;
        end
      end
    end

    if (flush_i) begin
      state_d      = IDLE;
      insn_valid_d = '0;
      insn_ep_id_d = 1'b0;
      pending_insn_valid_d = '0;
      pending_ep_id_d = 1'b0;
      pending_valid_d = 1'b0;
      ep_enqueued_d = 1'b0;
      ep_enqueued_id_d = 1'b0;
      error_sticky_d = 1'b0;
      vtrace_idx_d = '0;
      resp_meta_count_d = '0;
      resp_meta_is_vset_d = '0;
      resp_meta_rd_d = '0;
      resp_meta_ep_id_d = '0;
      vset_accept_wait_d = '0;
      vset_accept_id_d = '0;
      real_wait_valid_d = '0;
      real_wait_id_d = '0;
      real_wait_has_vset_d = '0;
      real_wait_drained_d = '0;
      real_wait_vset_seen_d = '0;
      operand_valid_d = 1'b0;
      operand_rs1_d = '0;
      operand_rs2_d = '0;
    end
  end

`ifndef SYNTHESIS
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

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q      <= IDLE;
      insn_valid_q <= '0;
      insn_q       <= '0;
      insn_ep_id_q <= 1'b0;
      pending_insn_valid_q <= '0;
      pending_insn_q <= '0;
      pending_ep_id_q <= 1'b0;
      pending_valid_q <= 1'b0;
      ep_enqueued_q <= 1'b0;
      ep_enqueued_id_q <= 1'b0;
      error_sticky_q <= 1'b0;
      vtrace_idx_q <= '0;
      resp_meta_count_q <= '0;
      resp_meta_is_vset_q <= '0;
      resp_meta_rd_q <= '0;
      resp_meta_ep_id_q <= '0;
      vset_accept_wait_q <= '0;
      vset_accept_id_q <= '0;
      real_wait_valid_q <= '0;
      real_wait_id_q <= '0;
      real_wait_has_vset_q <= '0;
      real_wait_drained_q <= '0;
      real_wait_vset_seen_q <= '0;
      operand_valid_q <= 1'b0;
      operand_rs1_q <= '0;
      operand_rs2_q <= '0;
    end else begin
      state_q      <= state_d;
      insn_valid_q <= insn_valid_d;
      insn_q       <= insn_d;
      insn_ep_id_q <= insn_ep_id_d;
      pending_insn_valid_q <= pending_insn_valid_d;
      pending_insn_q <= pending_insn_d;
      pending_ep_id_q <= pending_ep_id_d;
      pending_valid_q <= pending_valid_d;
      ep_enqueued_q <= ep_enqueued_d;
      ep_enqueued_id_q <= ep_enqueued_id_d;
      error_sticky_q <= error_sticky_d;
      vtrace_idx_q <= vtrace_idx_d;
      resp_meta_count_q <= resp_meta_count_d;
      resp_meta_is_vset_q <= resp_meta_is_vset_d;
      resp_meta_rd_q <= resp_meta_rd_d;
      resp_meta_ep_id_q <= resp_meta_ep_id_d;
      vset_accept_wait_q <= vset_accept_wait_d;
      vset_accept_id_q <= vset_accept_id_d;
      real_wait_valid_q <= real_wait_valid_d;
      real_wait_id_q <= real_wait_id_d;
      real_wait_has_vset_q <= real_wait_has_vset_d;
      real_wait_drained_q <= real_wait_drained_d;
      real_wait_vset_seen_q <= real_wait_vset_seen_d;
      operand_valid_q <= operand_valid_d;
      operand_rs1_q <= operand_rs1_d;
      operand_rs2_q <= operand_rs2_d;
    end
  end

endmodule : hdv_vec_dispatch_unit
