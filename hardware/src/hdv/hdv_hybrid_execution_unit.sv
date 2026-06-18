// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Hybrid Execution Unit (HEU) front-end dispatcher.  This standalone block
// splits an execute packet into scalar and vector backend streams.  Backends
// report when their EP slice has been safely accepted; Ara may still complete
// vector instructions later.  A one-EP skid buffer lets VLIWPU hand off the
// next packet while the current packet waits for backend acceptance.  When the
// current packet is stalled only by scalar dependencies, the buffered packet's
// vector slice may be sent ahead to keep Ara fed; scalar slices remain in EP
// order and vector early issue never crosses an unresolved scalar branch.

module hdv_hybrid_execution_unit import hdv_pkg::*; #(
  parameter int unsigned XLEN          = 64,
  parameter int unsigned NumSlots      = 8,
  parameter int unsigned SlotWidth     = 16,
  parameter bit          EnableBufferedVectorEarlyIssue = 1'b1,
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
  input  addr_t [NumSlots-1:0]               vliwpu_heu_execute_slot_pc_i,
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
  output logic                               heu_vector_ep_id_o,

  input  logic                               scalar_heu_accepted_i,
  input  logic                               vector_heu_accepted_i,
  input  logic                               vector_heu_accepted_id_i,
  input  logic                               backend_heu_error_i,
  output logic                               heu_top_busy_o,
  output logic                               heu_top_ep_accepted_o,
  output logic                               heu_top_ep_error_o
);

  logic has_scalar;
  logic has_vector;
  logic accept_packet;
  logic accept_to_current;
  logic accept_to_buffer;
  logic current_done;
  logic outstanding_d, outstanding_q;
  logic scalar_pending_d, scalar_pending_q;
  logic vector_pending_d, vector_pending_q;
  logic buffer_valid_d, buffer_valid_q;
  logic buffer_has_scalar_d, buffer_has_scalar_q;
  logic buffer_has_vector_d, buffer_has_vector_q;
  logic buffer_has_branch_d, buffer_has_branch_q;
  logic [31:0] buffer_scalar_write_mask_d, buffer_scalar_write_mask_q;
  logic [31:0] buffer_scalar_fpr_write_mask_d, buffer_scalar_fpr_write_mask_q;
  logic [31:0] buffer_vector_write_mask_d, buffer_vector_write_mask_q;
  logic [31:0] buffer_vector_read_mask_d, buffer_vector_read_mask_q;
  logic [31:0] buffer_vector_fpr_read_mask_d, buffer_vector_fpr_read_mask_q;
  logic buffer_vector_sent_d, buffer_vector_sent_q;
  logic buffer_vector_pending_d, buffer_vector_pending_q;
  logic buffer_vector_id_d, buffer_vector_id_q;
  logic [NumSlots-1:0] buffer_scalar_insn_valid_d, buffer_scalar_insn_valid_q;
  logic [NumSlots-1:0] buffer_vector_insn_valid_d, buffer_vector_insn_valid_q;
  logic [NumSlots-1:0][31:0] buffer_dispatch_insn_d, buffer_dispatch_insn_q;
  logic [NumSlots-1:0] buffer_dispatch_insn_is_32b_d, buffer_dispatch_insn_is_32b_q;
  addr_t [NumSlots-1:0] buffer_dispatch_insn_pc_d, buffer_dispatch_insn_pc_q;
  addr_t buffer_dispatch_pc_d, buffer_dispatch_pc_q;
  logic scalar_dispatch_valid_d, scalar_dispatch_valid_q;
  logic vector_dispatch_valid_d, vector_dispatch_valid_q;
  logic [NumSlots-1:0] scalar_insn_valid_d, scalar_insn_valid_q;
  logic [NumSlots-1:0] vector_insn_valid_d, vector_insn_valid_q;
  logic vector_dispatch_from_buffer_d, vector_dispatch_from_buffer_q;
  logic vector_dispatch_id_d, vector_dispatch_id_q;
  logic [NumSlots-1:0][31:0] dispatch_insn_d, dispatch_insn_q;
  logic [NumSlots-1:0][31:0] vector_dispatch_insn_d, vector_dispatch_insn_q;
  logic [NumSlots-1:0] dispatch_insn_is_32b_d, dispatch_insn_is_32b_q;
  logic [NumSlots-1:0] vector_dispatch_insn_is_32b_d, vector_dispatch_insn_is_32b_q;
  addr_t [NumSlots-1:0] dispatch_insn_pc_d, dispatch_insn_pc_q;
  addr_t [NumSlots-1:0] vector_dispatch_insn_pc_d, vector_dispatch_insn_pc_q;
  addr_t dispatch_pc_d, dispatch_pc_q;
  addr_t vector_dispatch_pc_d, vector_dispatch_pc_q;
  logic ep_accepted_d, ep_accepted_q;
  logic error_d, error_q;
  logic current_has_branch_d, current_has_branch_q;
  logic [31:0] current_scalar_write_mask_d, current_scalar_write_mask_q;
  logic [31:0] current_scalar_fpr_write_mask_d, current_scalar_fpr_write_mask_q;
  logic [31:0] current_vector_write_mask_d, current_vector_write_mask_q;
  logic current_vector_id_d, current_vector_id_q;
  logic next_vector_id_d, next_vector_id_q;
  logic buffer_vector_can_issue;
  logic buffer_vector_issue_fire;
  logic [NumSlots-1:0] scalar_insn_valid_in;
  logic [NumSlots-1:0] vector_insn_valid_in;
  logic [NumSlots-1:0][31:0] dispatch_insn_in;
  logic [NumSlots-1:0] dispatch_insn_is_32b_in;
  addr_t [NumSlots-1:0] dispatch_insn_pc_in;
  logic [31:0] scalar_write_mask_in;
  logic [31:0] scalar_fpr_write_mask_in;
  logic [31:0] vector_write_mask_in;
  logic [31:0] vector_read_mask_in;
  logic [31:0] vector_fpr_read_mask_in;

  function automatic logic is_scalar_control_flow(input logic [31:0] insn,
                                                  input logic        is_32b);
    logic [6:0] opcode;
    logic [2:0] c_funct3;
    logic [1:0] c_opcode;
    begin
      opcode = insn[6:0];
      c_funct3 = insn[15:13];
      c_opcode = insn[1:0];
      if (is_32b) begin
        is_scalar_control_flow = (opcode == 7'b1100011) || // branch
                                 (opcode == 7'b1101111) || // jal
                                 (opcode == 7'b1100111);   // jalr/ret
      end else begin
        is_scalar_control_flow =
          ((c_opcode == 2'b01) &&
           ((c_funct3 == 3'b101) || (c_funct3 == 3'b110) || (c_funct3 == 3'b111))) ||
          ((c_opcode == 2'b10) && (c_funct3 == 3'b100) && (insn[6:2] == 5'd0));
      end
    end
  endfunction

  function automatic logic [31:0] scalar_gpr_write_mask(input logic [31:0] insn,
                                                        input logic        is_32b);
    automatic logic [31:0] mask;
    automatic logic [6:0] opcode;
    automatic logic [4:0] rd;
    begin
      mask = '0;
      opcode = insn[6:0];
      rd = insn[11:7];
      if (!is_32b) begin
        // Compressed scalar write decoding is intentionally conservative here:
        // do not early-issue a later vector slice across an unexpanded C insn.
        mask = 32'hffff_ffff;
      end else if (rd != 5'd0) begin
        unique case (opcode)
          7'b0110111, // LUI
          7'b0010111, // AUIPC
          7'b1101111, // JAL
          7'b1100111, // JALR
          7'b0000011, // LOAD
          7'b0010011, // OP-IMM
          7'b0011011, // OP-IMM-32
          7'b0110011, // OP
          7'b0111011, // OP-32
          7'b1010011, // scalar FPU may write integer rd (fcvt/fclass/fcmp)
          7'b0001111, // FENCE rd is architecturally unused, but keep conservative
          7'b1110011: // SYSTEM/CSR
            mask[rd] = 1'b1;
          default: mask = '0;
        endcase
      end
      scalar_gpr_write_mask = mask;
    end
  endfunction

  function automatic logic [31:0] scalar_fpr_write_mask(input logic [31:0] insn,
                                                        input logic        is_32b);
    automatic logic [31:0] mask;
    automatic logic [6:0] opcode;
    automatic logic [2:0] funct3;
    automatic logic [4:0] rd;
    begin
      mask = '0;
      opcode = insn[6:0];
      funct3 = insn[14:12];
      rd = insn[11:7];
      if (!is_32b) begin
        mask = 32'hffff_ffff;
      end else if (rd != 5'd0) begin
        unique case (opcode)
          7'b0000111: begin // FLW/FLD write FRF, vector loads are classified separately.
            if ((funct3 == 3'b010) || (funct3 == 3'b011)) begin
              mask[rd] = 1'b1;
            end
          end
          7'b1010011: begin // scalar FPU usually writes FRF; mark conservatively.
            mask[rd] = 1'b1;
          end
          default: mask = '0;
        endcase
      end
      scalar_fpr_write_mask = mask;
    end
  endfunction

  function automatic logic [31:0] vector_gpr_read_mask(input logic [31:0] insn,
                                                       input logic        is_32b);
    automatic logic [31:0] mask;
    automatic logic [6:0] opcode;
    automatic logic [2:0] funct3;
    begin
      mask = '0;
      opcode = insn[6:0];
      funct3 = insn[14:12];
      if (!is_32b) begin
        mask = 32'hffff_ffff;
      end else begin
        unique case (opcode)
          7'b0000111, // vector memory base address in rs1
          7'b0100111: begin
            if (insn[19:15] != 5'd0) begin
              mask[insn[19:15]] = 1'b1;
            end
            if ((insn[27:26] == 2'b10) && (insn[24:20] != 5'd0)) begin
              // RVV strided memory instructions use scalar rs2 as stride.
              // Indexed memory uses vs2 in the same field and must not be
              // treated as a scalar GPR dependency.
              mask[insn[24:20]] = 1'b1;
            end
          end

          7'b1010111: begin
            unique case (funct3)
              3'b100, // OPIVX
              3'b110: begin // OPMVX
                if (insn[19:15] != 5'd0) begin
                  mask[insn[19:15]] = 1'b1;
                end
              end
              3'b111: begin // vsetvli/vsetivli/vsetvl configuration
                if (insn[19:15] != 5'd0) begin
                  mask[insn[19:15]] = 1'b1;
                end
                if (insn[24:20] != 5'd0) begin
                  mask[insn[24:20]] = 1'b1;
                end
              end
              default: mask = '0;
            endcase
          end

          default: mask = '0;
        endcase
      end
      vector_gpr_read_mask = mask;
    end
  endfunction

  function automatic logic [31:0] vector_fpr_read_mask(input logic [31:0] insn,
                                                       input logic        is_32b);
    automatic logic [31:0] mask;
    begin
      mask = '0;
      if (is_32b &&
          (insn[6:0] == 7'b1010111) &&
          (insn[14:12] == 3'b101) &&
          (insn[19:15] != 5'd0)) begin
        // OPFVF reads scalar FP register frs1 as the .vf operand.
        mask[insn[19:15]] = 1'b1;
      end
      vector_fpr_read_mask = mask;
    end
  endfunction

  function automatic logic [31:0] vector_gpr_write_mask(input logic [31:0] insn,
                                                        input logic        is_32b);
    automatic logic [31:0] mask;
    begin
      mask = '0;
      if (is_32b &&
          (insn[6:0] == 7'b1010111) &&
          (insn[14:12] == 3'b111) &&
          (insn[11:7] != 5'd0)) begin
        // vsetvli/vsetivli/vsetvl write the new VL to integer rd.  A later
        // vector instruction may read that rd as AVL/base/vx and must not
        // snapshot the old scalar value while this EP's vector slice is still
        // pending.
        mask[insn[11:7]] = 1'b1;
      end
      vector_gpr_write_mask = mask;
    end
  endfunction

  always_comb begin : p_split
    has_scalar = 1'b0;
    has_vector = 1'b0;
    scalar_insn_valid_in = '0;
    vector_insn_valid_in = '0;
    dispatch_insn_in = '0;
    dispatch_insn_is_32b_in = '0;
    dispatch_insn_pc_in = '0;
    scalar_write_mask_in = '0;
    scalar_fpr_write_mask_in = '0;
    vector_write_mask_in = '0;
    vector_read_mask_in = '0;
    vector_fpr_read_mask_in = '0;

    for (int unsigned i = 0; i < NumSlots; i++) begin
      logic is_continuation;

      is_continuation = 1'b0;
      if (i > 0) begin
        is_continuation = vliwpu_heu_execute_slot_is_32b_i[i-1];
      end

      if (vliwpu_heu_execute_slot_valid_i[i] && !is_continuation) begin
        dispatch_insn_pc_in[i] = vliwpu_heu_execute_slot_pc_i[i];

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
          vector_write_mask_in |= vector_gpr_write_mask(dispatch_insn_in[i],
                                                        dispatch_insn_is_32b_in[i]);
          vector_read_mask_in |= vector_gpr_read_mask(dispatch_insn_in[i],
                                                      dispatch_insn_is_32b_in[i]);
          vector_fpr_read_mask_in |= vector_fpr_read_mask(dispatch_insn_in[i],
                                                          dispatch_insn_is_32b_in[i]);
        end else begin
          has_scalar = 1'b1;
          scalar_insn_valid_in[i] = 1'b1;
          scalar_write_mask_in |= scalar_gpr_write_mask(dispatch_insn_in[i],
                                                        dispatch_insn_is_32b_in[i]);
          scalar_fpr_write_mask_in |= scalar_fpr_write_mask(dispatch_insn_in[i],
                                                            dispatch_insn_is_32b_in[i]);
        end
      end
    end
  end

  assign heu_scalar_valid_o        = scalar_dispatch_valid_q;
  assign heu_vector_valid_o        = vector_dispatch_valid_q;
  assign heu_scalar_insn_valid_o   = scalar_insn_valid_q;
  assign heu_vector_insn_valid_o   = vector_insn_valid_q;
  assign heu_scalar_insn_o         = dispatch_insn_q;
  assign heu_vector_insn_o         = vector_dispatch_insn_q;
  assign heu_scalar_insn_is_32b_o  = dispatch_insn_is_32b_q;
  assign heu_vector_insn_is_32b_o  = vector_dispatch_insn_is_32b_q;
  assign heu_scalar_insn_pc_o      = dispatch_insn_pc_q;
  assign heu_vector_insn_pc_o      = vector_dispatch_insn_pc_q;
  assign heu_scalar_pc_o           = dispatch_pc_q;
  assign heu_vector_pc_o           = vector_dispatch_pc_q;
  assign heu_vector_ep_id_o        = vector_dispatch_id_q;

  assign heu_vliwpu_execute_ready_o = !buffer_valid_q;
  assign accept_packet = vliwpu_heu_execute_valid_i & heu_vliwpu_execute_ready_o;
  assign accept_to_current = accept_packet & !outstanding_q;
  assign accept_to_buffer  = accept_packet & outstanding_q;

  assign heu_top_busy_o  = outstanding_q | buffer_valid_q | accept_packet |
                           scalar_dispatch_valid_q | vector_dispatch_valid_q;
  assign heu_top_ep_accepted_o  = ep_accepted_q;
  assign heu_top_ep_error_o = error_q;

  assign buffer_vector_can_issue = EnableBufferedVectorEarlyIssue &
                                   buffer_valid_q & buffer_has_vector_q &
                                   !buffer_vector_sent_q &
                                   !vector_dispatch_valid_q &
                                   !current_has_branch_q &
                                   (!scalar_pending_q ||
                                    ((buffer_vector_read_mask_q &
                                      current_scalar_write_mask_q) == 32'b0) &&
                                    ((buffer_vector_fpr_read_mask_q &
                                      current_scalar_fpr_write_mask_q) == 32'b0)) &
                                   (!vector_pending_q ||
                                    (((buffer_vector_read_mask_q &
                                       current_vector_write_mask_q) == 32'b0) &&
                                     ((current_vector_write_mask_q == 32'b0) ||
                                      (buffer_vector_write_mask_q == 32'b0))));
  assign buffer_vector_issue_fire = buffer_vector_can_issue;

  always_comb begin : p_next
    outstanding_d = outstanding_q;
    scalar_dispatch_valid_d = scalar_dispatch_valid_q;
    vector_dispatch_valid_d = vector_dispatch_valid_q;
    scalar_insn_valid_d     = scalar_insn_valid_q;
    vector_insn_valid_d     = vector_insn_valid_q;
    vector_dispatch_from_buffer_d = vector_dispatch_from_buffer_q;
    vector_dispatch_id_d    = vector_dispatch_id_q;
    dispatch_insn_d         = dispatch_insn_q;
    vector_dispatch_insn_d  = vector_dispatch_insn_q;
    dispatch_insn_is_32b_d  = dispatch_insn_is_32b_q;
    vector_dispatch_insn_is_32b_d = vector_dispatch_insn_is_32b_q;
    dispatch_insn_pc_d      = dispatch_insn_pc_q;
    vector_dispatch_insn_pc_d = vector_dispatch_insn_pc_q;
    dispatch_pc_d           = dispatch_pc_q;
    vector_dispatch_pc_d    = vector_dispatch_pc_q;
    buffer_valid_d = buffer_valid_q;
    buffer_has_scalar_d = buffer_has_scalar_q;
    buffer_has_vector_d = buffer_has_vector_q;
    buffer_has_branch_d = buffer_has_branch_q;
    buffer_scalar_write_mask_d = buffer_scalar_write_mask_q;
    buffer_scalar_fpr_write_mask_d = buffer_scalar_fpr_write_mask_q;
    buffer_vector_write_mask_d = buffer_vector_write_mask_q;
    buffer_vector_read_mask_d = buffer_vector_read_mask_q;
    buffer_vector_fpr_read_mask_d = buffer_vector_fpr_read_mask_q;
    buffer_vector_sent_d = buffer_vector_sent_q;
    buffer_vector_pending_d = buffer_vector_pending_q;
    buffer_vector_id_d = buffer_vector_id_q;
    buffer_scalar_insn_valid_d = buffer_scalar_insn_valid_q;
    buffer_vector_insn_valid_d = buffer_vector_insn_valid_q;
    buffer_dispatch_insn_d = buffer_dispatch_insn_q;
    buffer_dispatch_insn_is_32b_d = buffer_dispatch_insn_is_32b_q;
    buffer_dispatch_insn_pc_d = buffer_dispatch_insn_pc_q;
    buffer_dispatch_pc_d = buffer_dispatch_pc_q;
    // ep_accepted_d auto-clears each cycle so heu_top_ep_accepted_o is a 1-cycle pulse.
    // Callers (mock core, TSU) must latch it themselves.
    ep_accepted_d        = 1'b0;
    error_d       = error_q;
    current_has_branch_d = current_has_branch_q;
    current_scalar_write_mask_d = current_scalar_write_mask_q;
    current_scalar_fpr_write_mask_d = current_scalar_fpr_write_mask_q;
    current_vector_write_mask_d = current_vector_write_mask_q;
    current_vector_id_d = current_vector_id_q;
    next_vector_id_d = next_vector_id_q;

    if (scalar_dispatch_valid_q && scalar_heu_ready_i) begin
      scalar_dispatch_valid_d = 1'b0;
    end
    if (vector_dispatch_valid_q && vector_heu_ready_i) begin
      vector_dispatch_valid_d = 1'b0;
      if (vector_dispatch_from_buffer_q) begin
        buffer_vector_sent_d = 1'b1;
        buffer_vector_pending_d = 1'b1;
      end
      vector_dispatch_from_buffer_d = 1'b0;
    end

    if (accept_to_current) begin
      logic new_vector_id;

      new_vector_id = next_vector_id_q;
      outstanding_d = 1'b1;
      ep_accepted_d        = 1'b0;
      error_d       = 1'b0;
      scalar_dispatch_valid_d = has_scalar;
      vector_dispatch_valid_d = has_vector;
      scalar_insn_valid_d     = scalar_insn_valid_in;
      vector_insn_valid_d     = vector_insn_valid_in;
      dispatch_insn_d         = dispatch_insn_in;
      vector_dispatch_insn_d  = dispatch_insn_in;
      dispatch_insn_is_32b_d  = dispatch_insn_is_32b_in;
      vector_dispatch_insn_is_32b_d = dispatch_insn_is_32b_in;
      dispatch_insn_pc_d      = dispatch_insn_pc_in;
      vector_dispatch_insn_pc_d = dispatch_insn_pc_in;
      dispatch_pc_d           = vliwpu_heu_execute_pc_i;
      vector_dispatch_pc_d    = vliwpu_heu_execute_pc_i;
      vector_dispatch_from_buffer_d = 1'b0;
      vector_dispatch_id_d = new_vector_id;
      current_vector_id_d = new_vector_id;
      if (has_vector) begin
        next_vector_id_d = ~next_vector_id_q;
      end
      current_has_branch_d    = 1'b0;
      current_scalar_write_mask_d = scalar_write_mask_in;
      current_scalar_fpr_write_mask_d = scalar_fpr_write_mask_in;
      current_vector_write_mask_d = vector_write_mask_in;
      for (int unsigned i = 0; i < NumSlots; i++) begin
        current_has_branch_d |= scalar_insn_valid_in[i] &&
                                is_scalar_control_flow(dispatch_insn_in[i],
                                                       dispatch_insn_is_32b_in[i]);
      end
    end

    if (accept_to_buffer) begin
      logic new_vector_id;

      new_vector_id = next_vector_id_d;
      buffer_valid_d = 1'b1;
      buffer_has_scalar_d = has_scalar;
      buffer_has_vector_d = has_vector;
      buffer_has_branch_d = 1'b0;
      buffer_scalar_write_mask_d = scalar_write_mask_in;
      buffer_scalar_fpr_write_mask_d = scalar_fpr_write_mask_in;
      buffer_vector_write_mask_d = vector_write_mask_in;
      buffer_vector_read_mask_d = vector_read_mask_in;
      buffer_vector_fpr_read_mask_d = vector_fpr_read_mask_in;
      buffer_vector_sent_d = 1'b0;
      buffer_vector_pending_d = 1'b0;
      buffer_vector_id_d = new_vector_id;
      buffer_scalar_insn_valid_d = scalar_insn_valid_in;
      buffer_vector_insn_valid_d = vector_insn_valid_in;
      buffer_dispatch_insn_d = dispatch_insn_in;
      buffer_dispatch_insn_is_32b_d = dispatch_insn_is_32b_in;
      buffer_dispatch_insn_pc_d = dispatch_insn_pc_in;
      buffer_dispatch_pc_d = vliwpu_heu_execute_pc_i;
      if (has_vector) begin
        next_vector_id_d = ~new_vector_id;
      end
      for (int unsigned i = 0; i < NumSlots; i++) begin
        buffer_has_branch_d |= scalar_insn_valid_in[i] &&
                               is_scalar_control_flow(dispatch_insn_in[i],
                                                      dispatch_insn_is_32b_in[i]);
      end
    end

    if (buffer_vector_issue_fire) begin
      vector_dispatch_valid_d = 1'b1;
      vector_insn_valid_d = buffer_vector_insn_valid_q;
      vector_dispatch_insn_d = buffer_dispatch_insn_q;
      vector_dispatch_insn_is_32b_d = buffer_dispatch_insn_is_32b_q;
      vector_dispatch_insn_pc_d = buffer_dispatch_insn_pc_q;
      vector_dispatch_pc_d = buffer_dispatch_pc_q;
      vector_dispatch_from_buffer_d = 1'b1;
      vector_dispatch_id_d = buffer_vector_id_q;
    end

    if ((outstanding_q | accept_to_current) && backend_heu_error_i) begin
      error_d = 1'b1;
    end

    scalar_pending_d = scalar_pending_q;
    vector_pending_d = vector_pending_q;

    if (scalar_pending_q && scalar_heu_accepted_i) begin
      scalar_pending_d = 1'b0;
    end
    if (vector_pending_q && vector_heu_accepted_i &&
        (vector_heu_accepted_id_i == current_vector_id_q)) begin
      vector_pending_d = 1'b0;
    end
    if (buffer_vector_pending_q && vector_heu_accepted_i &&
        (vector_heu_accepted_id_i == buffer_vector_id_q)) begin
      buffer_vector_pending_d = 1'b0;
    end

    if (accept_to_current) begin
      scalar_pending_d = has_scalar;
      vector_pending_d = has_vector;
    end

    current_done = outstanding_q && !scalar_pending_d && !vector_pending_d &&
                   !scalar_dispatch_valid_d &&
                   !(vector_dispatch_valid_d && !vector_dispatch_from_buffer_d);

    if (current_done) begin
      ep_accepted_d        = !error_d;
      if (buffer_valid_d) begin
        logic buffer_vector_inflight;

        buffer_vector_inflight = vector_dispatch_valid_d && vector_dispatch_from_buffer_d;
        outstanding_d = 1'b1;
        error_d = 1'b0;
        scalar_dispatch_valid_d = buffer_has_scalar_d;
        scalar_insn_valid_d = buffer_scalar_insn_valid_d;
        vector_insn_valid_d = buffer_vector_insn_valid_d;
        dispatch_insn_d = buffer_dispatch_insn_d;
        dispatch_insn_is_32b_d = buffer_dispatch_insn_is_32b_d;
        dispatch_insn_pc_d = buffer_dispatch_insn_pc_d;
        dispatch_pc_d = buffer_dispatch_pc_d;
        if (!buffer_vector_sent_d && !buffer_vector_inflight) begin
          vector_dispatch_valid_d = buffer_has_vector_d;
          vector_insn_valid_d = buffer_vector_insn_valid_d;
          vector_dispatch_insn_d = buffer_dispatch_insn_d;
          vector_dispatch_insn_is_32b_d = buffer_dispatch_insn_is_32b_d;
          vector_dispatch_insn_pc_d = buffer_dispatch_insn_pc_d;
          vector_dispatch_pc_d = buffer_dispatch_pc_d;
          vector_dispatch_from_buffer_d = 1'b0;
          vector_dispatch_id_d = buffer_vector_id_d;
        end else if (buffer_vector_inflight) begin
          vector_dispatch_from_buffer_d = 1'b0;
        end else begin
          vector_dispatch_valid_d = 1'b0;
          vector_dispatch_from_buffer_d = 1'b0;
        end
        scalar_pending_d = buffer_has_scalar_d;
        vector_pending_d = buffer_has_vector_d &&
                           (!buffer_vector_sent_d || buffer_vector_pending_d);
        current_vector_id_d = buffer_vector_id_d;
        current_has_branch_d = buffer_has_branch_d;
        current_scalar_write_mask_d = buffer_scalar_write_mask_d;
        current_scalar_fpr_write_mask_d = buffer_scalar_fpr_write_mask_d;
        current_vector_write_mask_d = buffer_vector_write_mask_d;
        buffer_valid_d = 1'b0;
        buffer_has_branch_d = 1'b0;
        buffer_scalar_write_mask_d = '0;
        buffer_scalar_fpr_write_mask_d = '0;
        buffer_vector_write_mask_d = '0;
        buffer_vector_read_mask_d = '0;
        buffer_vector_fpr_read_mask_d = '0;
        buffer_vector_sent_d = 1'b0;
        buffer_vector_pending_d = 1'b0;
      end else begin
        outstanding_d = 1'b0;
        current_has_branch_d = 1'b0;
        current_scalar_write_mask_d = '0;
        current_scalar_fpr_write_mask_d = '0;
        current_vector_write_mask_d = '0;
      end
    end

    if (flush_i) begin
      outstanding_d = 1'b0;
      scalar_pending_d = 1'b0;
      vector_pending_d = 1'b0;
      buffer_valid_d = 1'b0;
      buffer_scalar_write_mask_d = '0;
      buffer_scalar_fpr_write_mask_d = '0;
      buffer_vector_write_mask_d = '0;
      buffer_vector_read_mask_d = '0;
      buffer_vector_fpr_read_mask_d = '0;
      buffer_vector_sent_d = 1'b0;
      buffer_vector_pending_d = 1'b0;
      buffer_vector_id_d = 1'b0;
      scalar_dispatch_valid_d = 1'b0;
      vector_dispatch_valid_d = 1'b0;
      vector_dispatch_from_buffer_d = 1'b0;
      ep_accepted_d        = 1'b0;
      error_d       = 1'b0;
      current_has_branch_d = 1'b0;
      current_scalar_write_mask_d = '0;
      current_scalar_fpr_write_mask_d = '0;
      current_vector_write_mask_d = '0;
      current_vector_id_d = 1'b0;
      next_vector_id_d = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      outstanding_q <= 1'b0;
      scalar_pending_q <= 1'b0;
      vector_pending_q <= 1'b0;
      buffer_valid_q <= 1'b0;
      buffer_has_scalar_q <= 1'b0;
      buffer_has_vector_q <= 1'b0;
      buffer_has_branch_q <= 1'b0;
      buffer_scalar_write_mask_q <= '0;
      buffer_scalar_fpr_write_mask_q <= '0;
      buffer_vector_write_mask_q <= '0;
      buffer_vector_read_mask_q <= '0;
      buffer_vector_fpr_read_mask_q <= '0;
      buffer_vector_sent_q <= 1'b0;
      buffer_vector_pending_q <= 1'b0;
      buffer_vector_id_q <= 1'b0;
      buffer_scalar_insn_valid_q <= '0;
      buffer_vector_insn_valid_q <= '0;
      buffer_dispatch_insn_q <= '0;
      buffer_dispatch_insn_is_32b_q <= '0;
      buffer_dispatch_insn_pc_q <= '0;
      buffer_dispatch_pc_q <= '0;
      scalar_dispatch_valid_q <= 1'b0;
      vector_dispatch_valid_q <= 1'b0;
      scalar_insn_valid_q <= '0;
      vector_insn_valid_q <= '0;
      vector_dispatch_from_buffer_q <= 1'b0;
      vector_dispatch_id_q <= 1'b0;
      dispatch_insn_q <= '0;
      vector_dispatch_insn_q <= '0;
      dispatch_insn_is_32b_q <= '0;
      vector_dispatch_insn_is_32b_q <= '0;
      dispatch_insn_pc_q <= '0;
      vector_dispatch_insn_pc_q <= '0;
      dispatch_pc_q <= '0;
      vector_dispatch_pc_q <= '0;
      ep_accepted_q        <= 1'b0;
      error_q       <= 1'b0;
      current_has_branch_q <= 1'b0;
      current_scalar_write_mask_q <= '0;
      current_scalar_fpr_write_mask_q <= '0;
      current_vector_write_mask_q <= '0;
      current_vector_id_q <= 1'b0;
      next_vector_id_q <= 1'b0;
    end else begin
      outstanding_q <= outstanding_d;
      scalar_pending_q <= scalar_pending_d;
      vector_pending_q <= vector_pending_d;
      buffer_valid_q <= buffer_valid_d;
      buffer_has_scalar_q <= buffer_has_scalar_d;
      buffer_has_vector_q <= buffer_has_vector_d;
      buffer_has_branch_q <= buffer_has_branch_d;
      buffer_scalar_write_mask_q <= buffer_scalar_write_mask_d;
      buffer_scalar_fpr_write_mask_q <= buffer_scalar_fpr_write_mask_d;
      buffer_vector_write_mask_q <= buffer_vector_write_mask_d;
      buffer_vector_read_mask_q <= buffer_vector_read_mask_d;
      buffer_vector_fpr_read_mask_q <= buffer_vector_fpr_read_mask_d;
      buffer_vector_sent_q <= buffer_vector_sent_d;
      buffer_vector_pending_q <= buffer_vector_pending_d;
      buffer_vector_id_q <= buffer_vector_id_d;
      buffer_scalar_insn_valid_q <= buffer_scalar_insn_valid_d;
      buffer_vector_insn_valid_q <= buffer_vector_insn_valid_d;
      buffer_dispatch_insn_q <= buffer_dispatch_insn_d;
      buffer_dispatch_insn_is_32b_q <= buffer_dispatch_insn_is_32b_d;
      buffer_dispatch_insn_pc_q <= buffer_dispatch_insn_pc_d;
      buffer_dispatch_pc_q <= buffer_dispatch_pc_d;
      scalar_dispatch_valid_q <= scalar_dispatch_valid_d;
      vector_dispatch_valid_q <= vector_dispatch_valid_d;
      scalar_insn_valid_q <= scalar_insn_valid_d;
      vector_insn_valid_q <= vector_insn_valid_d;
      vector_dispatch_from_buffer_q <= vector_dispatch_from_buffer_d;
      vector_dispatch_id_q <= vector_dispatch_id_d;
      dispatch_insn_q <= dispatch_insn_d;
      vector_dispatch_insn_q <= vector_dispatch_insn_d;
      dispatch_insn_is_32b_q <= dispatch_insn_is_32b_d;
      vector_dispatch_insn_is_32b_q <= vector_dispatch_insn_is_32b_d;
      dispatch_insn_pc_q <= dispatch_insn_pc_d;
      vector_dispatch_insn_pc_q <= vector_dispatch_insn_pc_d;
      dispatch_pc_q <= dispatch_pc_d;
      vector_dispatch_pc_q <= vector_dispatch_pc_d;
      ep_accepted_q        <= ep_accepted_d;
      error_q       <= error_d;
      current_has_branch_q <= current_has_branch_d;
      current_scalar_write_mask_q <= current_scalar_write_mask_d;
      current_scalar_fpr_write_mask_q <= current_scalar_fpr_write_mask_d;
      current_vector_write_mask_q <= current_vector_write_mask_d;
      current_vector_id_q <= current_vector_id_d;
      next_vector_id_q <= next_vector_id_d;
    end
  end

endmodule : hdv_hybrid_execution_unit
