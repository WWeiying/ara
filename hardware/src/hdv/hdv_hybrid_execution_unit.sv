// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Hybrid Execution Unit (HEU) front-end dispatcher.  This standalone block
// splits an execute packet into scalar and vector backend streams while
// keeping one-cycle packet acceptance atomic across both streams.

module hdv_hybrid_execution_unit import hdv_pkg::*; #(
  parameter int unsigned XLEN          = 64,
  parameter int unsigned NumSlots      = 6,
  parameter int unsigned SlotWidth     = 16,
  parameter type addr_t = logic [XLEN-1:0]
) (
  input  logic                               clk_i,
  input  logic                               rst_ni,
  input  logic                               flush_i,

  input  logic                               vliwpu_heu_execute_valid_i,
  output logic                               heu_vliwpu_execute_ready_o,
  input  logic [NumSlots-1:0]                vliwpu_heu_execute_slot_valid_i,
  input  logic [NumSlots-1:0][SlotWidth-1:0] vliwpu_heu_execute_slot_i,
  input  logic [NumSlots-1:0]                vliwpu_heu_execute_slot_is_32b_i,
  input  hdv_inst_class_e [NumSlots-1:0]     vliwpu_heu_execute_class_i,
  input  addr_t                              vliwpu_heu_execute_pc_i,

  output logic                               heu_scalar_valid_o,
  input  logic                               scalar_heu_ready_i,
  output logic [NumSlots-1:0]                heu_scalar_insn_valid_o,
  output logic [NumSlots-1:0][31:0]          heu_scalar_insn_o,
  output logic [NumSlots-1:0]                heu_scalar_insn_is_32b_o,
  output addr_t [NumSlots-1:0]               heu_scalar_insn_pc_o,
  output addr_t                              heu_scalar_pc_o,

  output logic                               heu_vector_valid_o,
  input  logic                               vector_heu_ready_i,
  output logic [NumSlots-1:0]                heu_vector_insn_valid_o,
  output logic [NumSlots-1:0][31:0]          heu_vector_insn_o,
  output logic [NumSlots-1:0]                heu_vector_insn_is_32b_o,
  output addr_t [NumSlots-1:0]               heu_vector_insn_pc_o,
  output addr_t                              heu_vector_pc_o,

  input  logic                               scalar_heu_accepted_i,
  input  logic                               vector_heu_accepted_i,
  input  logic                               backend_heu_error_i,
  output logic                               heu_top_busy_o,
  output logic                               heu_top_ep_accepted_o,
  output logic                               heu_top_ep_error_o
);

  logic has_scalar;
  logic has_vector;
  logic accept_packet;
  logic outstanding_d, outstanding_q;
  logic scalar_pending_d, scalar_pending_q;
  logic vector_pending_d, vector_pending_q;
  logic scalar_dispatch_valid_d, scalar_dispatch_valid_q;
  logic vector_dispatch_valid_d, vector_dispatch_valid_q;
  logic [NumSlots-1:0] scalar_insn_valid_d, scalar_insn_valid_q;
  logic [NumSlots-1:0] vector_insn_valid_d, vector_insn_valid_q;
  logic [NumSlots-1:0][31:0] dispatch_insn_d, dispatch_insn_q;
  logic [NumSlots-1:0] dispatch_insn_is_32b_d, dispatch_insn_is_32b_q;
  addr_t [NumSlots-1:0] dispatch_insn_pc_d, dispatch_insn_pc_q;
  addr_t dispatch_pc_d, dispatch_pc_q;
  logic ep_accepted_d, ep_accepted_q;
  logic error_d, error_q;
  logic [NumSlots-1:0] scalar_insn_valid_in;
  logic [NumSlots-1:0] vector_insn_valid_in;
  logic [NumSlots-1:0][31:0] dispatch_insn_in;
  logic [NumSlots-1:0] dispatch_insn_is_32b_in;
  addr_t [NumSlots-1:0] dispatch_insn_pc_in;

  always_comb begin : p_split
    has_scalar = 1'b0;
    has_vector = 1'b0;
    scalar_insn_valid_in = '0;
    vector_insn_valid_in = '0;
    dispatch_insn_in = '0;
    dispatch_insn_is_32b_in = '0;
    dispatch_insn_pc_in = '0;

    for (int unsigned i = 0; i < NumSlots; i++) begin
      logic is_continuation;

      is_continuation = 1'b0;
      if (i > 0) begin
        is_continuation = vliwpu_heu_execute_slot_is_32b_i[i-1];
      end

      if (vliwpu_heu_execute_slot_valid_i[i] && !is_continuation) begin
        dispatch_insn_pc_in[i] = vliwpu_heu_execute_pc_i + addr_t'(i * (SlotWidth / 8));

        if (vliwpu_heu_execute_slot_is_32b_i[i] && i < NumSlots - 1) begin
          dispatch_insn_in[i] = {vliwpu_heu_execute_slot_i[i+1], vliwpu_heu_execute_slot_i[i]};
          dispatch_insn_is_32b_in[i] = 1'b1;
        end else begin
          dispatch_insn_in[i] = {16'b0, vliwpu_heu_execute_slot_i[i]};
          dispatch_insn_is_32b_in[i] = 1'b0;
        end

        if (vliwpu_heu_execute_class_i[i] == HDV_INST_VECTOR) begin
          has_vector = 1'b1;
          vector_insn_valid_in[i] = 1'b1;
        end else begin
          has_scalar = 1'b1;
          scalar_insn_valid_in[i] = 1'b1;
        end
      end
    end
  end

  assign heu_scalar_valid_o        = scalar_dispatch_valid_q;
  assign heu_vector_valid_o        = vector_dispatch_valid_q;
  assign heu_scalar_insn_valid_o   = scalar_insn_valid_q;
  assign heu_vector_insn_valid_o   = vector_insn_valid_q;
  assign heu_scalar_insn_o         = dispatch_insn_q;
  assign heu_vector_insn_o         = dispatch_insn_q;
  assign heu_scalar_insn_is_32b_o  = dispatch_insn_is_32b_q;
  assign heu_vector_insn_is_32b_o  = dispatch_insn_is_32b_q;
  assign heu_scalar_insn_pc_o      = dispatch_insn_pc_q;
  assign heu_vector_insn_pc_o      = dispatch_insn_pc_q;
  assign heu_scalar_pc_o           = dispatch_pc_q;
  assign heu_vector_pc_o           = dispatch_pc_q;

  assign heu_vliwpu_execute_ready_o = !outstanding_q;
  assign accept_packet = vliwpu_heu_execute_valid_i & heu_vliwpu_execute_ready_o;

  assign heu_top_busy_o  = outstanding_q | accept_packet | scalar_dispatch_valid_q | vector_dispatch_valid_q;
  assign heu_top_ep_accepted_o  = ep_accepted_q;
  assign heu_top_ep_error_o = error_q;

  always_comb begin : p_next
    outstanding_d = outstanding_q;
    scalar_dispatch_valid_d = scalar_dispatch_valid_q;
    vector_dispatch_valid_d = vector_dispatch_valid_q;
    scalar_insn_valid_d     = scalar_insn_valid_q;
    vector_insn_valid_d     = vector_insn_valid_q;
    dispatch_insn_d         = dispatch_insn_q;
    dispatch_insn_is_32b_d  = dispatch_insn_is_32b_q;
    dispatch_insn_pc_d      = dispatch_insn_pc_q;
    dispatch_pc_d           = dispatch_pc_q;
    // ep_accepted_d auto-clears each cycle so heu_top_ep_accepted_o is a 1-cycle pulse.
    // Callers (mock core, TSU) must latch it themselves.
    ep_accepted_d        = 1'b0;
    error_d       = error_q;

    if (scalar_dispatch_valid_q && scalar_heu_ready_i) begin
      scalar_dispatch_valid_d = 1'b0;
    end
    if (vector_dispatch_valid_q && vector_heu_ready_i) begin
      vector_dispatch_valid_d = 1'b0;
    end

    if (accept_packet) begin
      outstanding_d = 1'b1;
      ep_accepted_d        = 1'b0;
      error_d       = 1'b0;
      scalar_dispatch_valid_d = has_scalar;
      vector_dispatch_valid_d = has_vector;
      scalar_insn_valid_d     = scalar_insn_valid_in;
      vector_insn_valid_d     = vector_insn_valid_in;
      dispatch_insn_d         = dispatch_insn_in;
      dispatch_insn_is_32b_d  = dispatch_insn_is_32b_in;
      dispatch_insn_pc_d      = dispatch_insn_pc_in;
      dispatch_pc_d           = vliwpu_heu_execute_pc_i;
    end

    if ((outstanding_q | accept_packet) && backend_heu_error_i) begin
      error_d = 1'b1;
    end

    scalar_pending_d = scalar_pending_q;
    vector_pending_d = vector_pending_q;

    if (scalar_pending_q && scalar_heu_accepted_i) begin
      scalar_pending_d = 1'b0;
    end
    if (vector_pending_q && vector_heu_accepted_i) begin
      vector_pending_d = 1'b0;
    end

    if (accept_packet) begin
      scalar_pending_d = has_scalar;
      vector_pending_d = has_vector;
    end

    if (outstanding_q && !scalar_pending_d && !vector_pending_d &&
        !scalar_dispatch_valid_d && !vector_dispatch_valid_d) begin
      outstanding_d = 1'b0;
      ep_accepted_d        = !error_d;
    end

    if (flush_i) begin
      outstanding_d = 1'b0;
      scalar_pending_d = 1'b0;
      vector_pending_d = 1'b0;
      scalar_dispatch_valid_d = 1'b0;
      vector_dispatch_valid_d = 1'b0;
      ep_accepted_d        = 1'b0;
      error_d       = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      outstanding_q <= 1'b0;
      scalar_pending_q <= 1'b0;
      vector_pending_q <= 1'b0;
      scalar_dispatch_valid_q <= 1'b0;
      vector_dispatch_valid_q <= 1'b0;
      scalar_insn_valid_q <= '0;
      vector_insn_valid_q <= '0;
      dispatch_insn_q <= '0;
      dispatch_insn_is_32b_q <= '0;
      dispatch_insn_pc_q <= '0;
      dispatch_pc_q <= '0;
      ep_accepted_q        <= 1'b0;
      error_q       <= 1'b0;
    end else begin
      outstanding_q <= outstanding_d;
      scalar_pending_q <= scalar_pending_d;
      vector_pending_q <= vector_pending_d;
      scalar_dispatch_valid_q <= scalar_dispatch_valid_d;
      vector_dispatch_valid_q <= vector_dispatch_valid_d;
      scalar_insn_valid_q <= scalar_insn_valid_d;
      vector_insn_valid_q <= vector_insn_valid_d;
      dispatch_insn_q <= dispatch_insn_d;
      dispatch_insn_is_32b_q <= dispatch_insn_is_32b_d;
      dispatch_insn_pc_q <= dispatch_insn_pc_d;
      dispatch_pc_q <= dispatch_pc_d;
      ep_accepted_q        <= ep_accepted_d;
      error_q       <= error_d;
    end
  end

endmodule : hdv_hybrid_execution_unit
