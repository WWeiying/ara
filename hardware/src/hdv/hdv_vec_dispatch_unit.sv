// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Vector dispatch adapter: serializes HEU's multi-slot vector execute-packet
// into single-instruction acc_req transactions for Ara.  It buffers the current
// EP internally and keeps issuing vector slots whenever Ara can accept them.
// vec_heu_accepted_o means all vector instructions in this EP were accepted by Ara;
// it does not mean that the vector instructions have retired.
//
// In simulation, a vtrace file can provide the scalar context that a real scalar
// core would normally send with each vector instruction.  Each vtrace entry is:
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
  parameter int unsigned NumSlots        = 6,
  parameter bit          UseVTraceScalar = 1'b1,
  parameter int unsigned VTraceDepth     = `HDV_N_VINSN,
  parameter string       VTraceFile      = `HDV_STRINGIFY(`HDV_VTRACE),
  parameter type cva6_to_acc_t           = logic,
  parameter type acc_to_cva6_t           = logic
) (
  input  logic                              clk_i,
  input  logic                              rst_ni,
  input  logic                              flush_i,

  // ── From HEU vector dispatch output ──────────────────────────────────────
  // HEU asserts heu_vec_valid_i when has_vector=1 and dispatch_valid is set.
  input  logic                              heu_vec_valid_i,
  output logic                              vec_heu_ready_o,    // accept when IDLE
  input  logic [NumSlots-1:0]               heu_vec_insn_valid_i, // which slots are vector
  input  logic [NumSlots-1:0][31:0]         heu_vec_insn_i,       // assembled 32-bit insns

  // ── Acceptance pulse back to HEU (1-cycle) ────────────────────────────────
  output logic                              vec_heu_accepted_o,
  output logic                              vec_heu_error_o,

  // ── Ara accelerator request / response (replaces CVA6→Ara path) ──────────
  output cva6_to_acc_t                      acc_req_o,
  input  acc_to_cva6_t                      acc_resp_i
);

  localparam int unsigned SlotIdxW = (NumSlots > 1) ? $clog2(NumSlots) : 1;
  localparam int unsigned VTraceIdxW = (VTraceDepth > 1) ? $clog2(VTraceDepth) : 1;
  localparam int unsigned VTraceEntryWidth = 32 + 64 + 64;

  typedef enum logic [1:0] {
    IDLE     = 2'd0,
    DISPATCH = 2'd1,
    WAIT     = 2'd2,
    DONE     = 2'd3
  } state_e;

  state_e                    state_d,      state_q;
  logic [NumSlots-1:0]       insn_valid_d, insn_valid_q;
  logic [NumSlots-1:0][31:0] insn_d,       insn_q;
  logic [VTraceIdxW:0]        vtrace_idx_d, vtrace_idx_q;
  logic [VTraceEntryWidth-1:0] vtrace_mem [VTraceDepth];
  logic [VTraceEntryWidth-1:0] vtrace_entry_raw;
  logic [VTraceIdxW-1:0]       vtrace_mem_idx;
  logic                        vtrace_available;
  logic [31:0]                 vtrace_insn;
  logic [63:0]                 vtrace_rs1;
  logic [63:0]                 vtrace_rs2;
  logic                        vtrace_mismatch;
  logic                        vtrace_empty_error;
  logic                        ara_exception_error;

  // Priority-encoders: find the lowest-index valid slot in the buffered EP or
  // in a freshly arriving EP.  The latter lets IDLE accept an EP and issue its
  // first vector instruction to Ara in the same cycle.
  logic                  slot_found;
  logic [SlotIdxW-1:0]   slot_idx;
  logic                  input_slot_found;
  logic [SlotIdxW-1:0]   input_slot_idx;
  logic                  selected_slot_found;
  logic [31:0]           selected_insn;

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

  assign accept_insn = acc_resp_i.acc_resp.req_ready & acc_req_o.acc_req.req_valid;
  assign resp_valid  = acc_resp_i.acc_resp.resp_valid;

  assign vtrace_available = (vtrace_idx_q < (VTraceIdxW+1)'(VTraceDepth));
  assign vtrace_mem_idx   = vtrace_available ? vtrace_idx_q[VTraceIdxW-1:0] : '0;
  assign vtrace_entry_raw = vtrace_mem[vtrace_mem_idx];
  assign vtrace_insn      = vtrace_entry_raw[159:128];
  assign vtrace_rs1       = vtrace_entry_raw[127:64];
  assign vtrace_rs2       = vtrace_entry_raw[63:0];

  assign selected_slot_found = ((state_q == DISPATCH) && slot_found) ||
                               ((state_q == IDLE) && heu_vec_valid_i && input_slot_found);
  assign selected_insn       = (state_q == DISPATCH) ? insn_q[slot_idx]
                                                     : heu_vec_insn_i[input_slot_idx];

  assign vtrace_empty_error = UseVTraceScalar &&
                              selected_slot_found &&
                              !vtrace_available;
  assign vtrace_mismatch    = UseVTraceScalar &&
                              selected_slot_found &&
                              vtrace_available &&
                              (vtrace_insn != selected_insn);
  assign ara_exception_error = resp_valid && acc_resp_i.acc_resp.exception.valid;
  assign vec_heu_error_o     = vtrace_empty_error | vtrace_mismatch | ara_exception_error;

  // Drive Ara's acc_req from either a buffered EP or a newly accepted EP.
  always_comb begin
    acc_req_o                       = '0;
    acc_req_o.acc_req.resp_ready    = 1'b1; // always ready to receive Ara's response
    acc_req_o.acc_req.inval_ready   = 1'b1; // always consume cache-line invalidations

    if (selected_slot_found) begin
      acc_req_o.acc_req.req_valid = !(vtrace_empty_error | vtrace_mismatch);
      acc_req_o.acc_req.insn      = selected_insn;
      acc_req_o.acc_req.frm       = fpnew_pkg::RNE; // vtrace carries rs1/rs2, not frm.
      if (UseVTraceScalar && vtrace_available) begin
        acc_req_o.acc_req.rs1 = vtrace_rs1;
        acc_req_o.acc_req.rs2 = vtrace_rs2;
      end
    end
  end

  assign vec_heu_ready_o = (state_q == IDLE);
  assign vec_heu_accepted_o  = (state_q == DONE);

  always_comb begin
    state_d      = state_q;
    insn_valid_d = insn_valid_q;
    insn_d       = insn_q;
    vtrace_idx_d = vtrace_idx_q;

    case (state_q)
      IDLE: begin
        if (heu_vec_valid_i) begin
          insn_valid_d = heu_vec_insn_valid_i;
          insn_d       = heu_vec_insn_i;
          if (accept_insn) begin
            insn_valid_d[input_slot_idx] = 1'b0;
            if (UseVTraceScalar) begin
              vtrace_idx_d = vtrace_idx_q + 1'b1;
            end
          end
          state_d      = (|heu_vec_insn_valid_i) ? DISPATCH : DONE;
          if (!(|insn_valid_d)) begin
            state_d = DONE;
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
        state_d = (|insn_valid_d) ? DISPATCH : DONE;
      end

      WAIT: begin
        state_d = DONE;
      end

      DONE: begin
        // vec_heu_accepted_o is high for this one cycle after Ara accepts this EP.
        state_d = IDLE;
      end

      default: state_d = IDLE;
    endcase

    if (flush_i) begin
      state_d      = IDLE;
      insn_valid_d = '0;
      vtrace_idx_d = '0;
    end
  end

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
      vtrace_idx_q <= '0;
    end else begin
      state_q      <= state_d;
      insn_valid_q <= insn_valid_d;
      insn_q       <= insn_d;
      vtrace_idx_q <= vtrace_idx_d;
    end
  end

endmodule : hdv_vec_dispatch_unit
