// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Conservative VLIW Pack Unit.  The upper 32 bits of each 128-bit fetch
// packet are treated as the RISC-V hint header, and the lower 96 bits are
// six 16-bit instruction slots.  Hint immediate p-bits request parallel packing;
// dependency/resource breaks can still force a smaller execute packet.

module hdv_vliw_pack_unit import hdv_pkg::*; #(
  parameter int unsigned XLEN             = 64,
  parameter int unsigned FetchPacketWidth = 128,
  parameter int unsigned NumSlots         = 6,
  parameter int unsigned SlotWidth        = 16,
  parameter int unsigned MaxIssueSlots    = NumSlots,
  parameter type addr_t = logic [XLEN-1:0]
) (
  input  logic                                      clk_i,
  input  logic                                      rst_ni,
  input  logic                                      flush_i,

  input  logic                                      packet_valid_i,
  output logic                                      packet_ready_o,
  input  logic [FetchPacketWidth-1:0]               packet_i,
  input  addr_t                                     packet_pc_i,

  input  logic [NumSlots-2:0]                       dep_break_i,
  output logic                                      execute_valid_o,
  input  logic                                      execute_ready_i,
  output logic [NumSlots-1:0]                       execute_slot_valid_o,
  output logic [NumSlots-1:0][SlotWidth-1:0]        execute_slot_o,
  output logic [NumSlots-1:0]                       execute_slot_is_32b_o,
  output hdv_inst_class_e [NumSlots-1:0]            execute_class_o,
  output addr_t                                     execute_pc_o
);

  localparam int unsigned SlotIdxWidth = (NumSlots > 1) ? $clog2(NumSlots) : 1;
  localparam logic [SlotIdxWidth:0] MaxIssueSlotsCount = MaxIssueSlots;

  logic packet_hold_valid_d, packet_hold_valid_q;
  logic [FetchPacketWidth-1:0] packet_d, packet_q;
  addr_t packet_pc_d, packet_pc_q;
  logic [SlotIdxWidth-1:0] head_slot_d, head_slot_q;
  logic [31:0] header;
  logic [NumSlots-2:0] p_bits;
  logic [NumSlots-1:0][SlotWidth-1:0] slots;
  logic [NumSlots-1:0] raw_slot_is_32b;
  logic [NumSlots-1:0] slot_is_32b;
  logic [NumSlots-1:0] slot_is_continuation;
  logic [NumSlots-1:0] issue_mask;
  logic [NumSlots-1:0] class_system_mask;
  logic [NumSlots-1:0] class_branch_mask;
  hdv_inst_class_e [NumSlots-1:0] slot_class;
  logic [SlotIdxWidth:0] issue_count;
  logic packet_accept;
  logic execute_accept;
  logic last_slot_in_packet;
  logic stop_pack;

  assign packet_accept  = packet_valid_i & packet_ready_o;
  assign execute_accept = execute_valid_o & execute_ready_i;
  assign packet_ready_o = !packet_hold_valid_q;

  assign header = packet_q[FetchPacketWidth-1 -: 32];
  // RISC-V HINT header is encoded as addi x0, x0, imm.  The paper defines
  // p-bits in the hint immediate field, so p_bits[0] is header[20].
  assign p_bits = header[20 +: NumSlots-1];

  for (genvar i = 0; i < NumSlots; i++) begin : gen_slots
    assign slots[i] = packet_q[i*SlotWidth +: SlotWidth];
    assign raw_slot_is_32b[i] = (slots[i][1:0] == 2'b11);
    assign execute_slot_o[i] = slots[i];
    assign execute_slot_is_32b_o[i] = slot_is_32b[i];
  end

  always_comb begin : p_slot_marks
    logic skip_next;

    slot_is_32b          = '0;
    slot_is_continuation = '0;
    skip_next            = 1'b0;

    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (skip_next) begin
        slot_is_continuation[i] = 1'b1;
        skip_next = 1'b0;
      end else if (raw_slot_is_32b[i] && i < NumSlots - 1) begin
        slot_is_32b[i] = 1'b1;
        skip_next = 1'b1;
      end
    end
  end

  always_comb begin : p_classify
    class_system_mask = '0;
    class_branch_mask = '0;

    for (int unsigned i = 0; i < NumSlots; i++) begin
      slot_class[i] = HDV_INST_SCALAR;

      if ((slots[i][6:0] == 7'b1010111) ||           // V arithmetic (opcode 0x57)
          (slots[i][6:0] == 7'b0000111 &&            // V load (LOAD-FP), exclude scalar FLW/FLD
           slots[i][14:12] != 3'b010 && slots[i][14:12] != 3'b011) ||
          (slots[i][6:0] == 7'b0100111 &&            // V store (STORE-FP), exclude scalar FSW/FSD
           slots[i][14:12] != 3'b010 && slots[i][14:12] != 3'b011)) begin
        slot_class[i] = HDV_INST_VECTOR;
      end else if ((slots[i][6:0] == 7'b1110011) || (slots[i][1:0] != 2'b11 && slots[i][15:13] == 3'b111)) begin
        slot_class[i] = HDV_INST_SYSTEM;
        class_system_mask[i] = 1'b1;
      end else if ((slots[i][6:0] == 7'b1100011) || (slots[i][6:0] == 7'b1101111) ||
                   (slots[i][6:0] == 7'b1100111)) begin
        slot_class[i] = HDV_INST_BRANCH;
        class_branch_mask[i] = 1'b1;
      end

      if (slot_is_continuation[i]) begin
        if (i > 0) begin
          execute_class_o[i] = slot_class[i-1];
        end else begin
          execute_class_o[i] = slot_class[i];
        end
      end else begin
        execute_class_o[i] = slot_class[i];
      end
    end
  end

  always_comb begin : p_issue_mask
    issue_mask = '0;
    issue_count = '0;
    stop_pack = 1'b0;

    if (packet_hold_valid_q) begin
      for (int unsigned i = 0; i < NumSlots; i++) begin
        // Skip continuation slots (already force-included by their 32-bit parent)
        // and slots beyond head_slot or the packet capacity (MaxIssueSlots=NumSlots).
        if (!stop_pack && i >= head_slot_q && issue_count < MaxIssueSlotsCount
            && !slot_is_continuation[i]) begin
          issue_mask[i] = 1'b1;
          issue_count++;

          if (i == NumSlots - 1) begin
            stop_pack = 1'b1;
          end else if (slot_is_32b[i]) begin
            // Force the second half of the 32-bit instruction into the packet.
            issue_mask[i + 1] = 1'b1;
            issue_count++;
            // Decide whether to continue to the NEXT instruction after this one.
            // Stop if the 32-bit instruction itself is SYSTEM/BRANCH (checked on
            // the STARTING slot i, not the continuation slot i+1 whose raw bits
            // don't carry a valid opcode).  Also stop on dep_break or p-bit=0.
            if (i + 1 == NumSlots - 1 || issue_count >= MaxIssueSlotsCount) begin
              stop_pack = 1'b1;  // end of fetch packet, no room for more
            end else if (!p_bits[i+1] || dep_break_i[i+1] ||
                         class_system_mask[i] || class_branch_mask[i]) begin
              stop_pack = 1'b1;
            end
            // else: continue; the loop will skip i+1 (continuation) and
            // consider i+2 as the next instruction candidate.
          end else if (!p_bits[i] || dep_break_i[i] ||
                       class_system_mask[i] || class_branch_mask[i]) begin
            stop_pack = 1'b1;
          end
        end
      end
    end
  end

  assign execute_valid_o      = packet_hold_valid_q;
  assign execute_slot_valid_o = issue_mask;
  // PC of slot 0 in the fetch packet; HEU computes per-slot PC as execute_pc_i + i*2.
  assign execute_pc_o         = packet_pc_q;
  assign last_slot_in_packet  = issue_mask[NumSlots-1];

  always_comb begin : p_next
    packet_hold_valid_d = packet_hold_valid_q;
    packet_d            = packet_q;
    packet_pc_d         = packet_pc_q;
    head_slot_d         = head_slot_q;

    if (execute_accept) begin
      if (last_slot_in_packet) begin
        packet_hold_valid_d = 1'b0;
        head_slot_d = '0;
      end else begin
        for (int unsigned i = 0; i < NumSlots; i++) begin
          if (issue_mask[i]) begin
            head_slot_d = SlotIdxWidth'(i + 1);
          end
        end
      end
    end

    if (packet_accept) begin
      packet_hold_valid_d = 1'b1;
      packet_d            = packet_i;
      packet_pc_d         = packet_pc_i;
      head_slot_d         = '0;
    end

    if (flush_i) begin
      packet_hold_valid_d = 1'b0;
      head_slot_d         = '0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      packet_hold_valid_q <= 1'b0;
      packet_q            <= '0;
      packet_pc_q         <= '0;
      head_slot_q         <= '0;
    end else begin
      packet_hold_valid_q <= packet_hold_valid_d;
      packet_q            <= packet_d;
      packet_pc_q         <= packet_pc_d;
      head_slot_q         <= head_slot_d;
    end
  end

endmodule : hdv_vliw_pack_unit
