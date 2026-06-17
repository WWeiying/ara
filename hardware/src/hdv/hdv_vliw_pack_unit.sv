// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Conservative VLIW Pack Unit.  The upper 32 bits of each 128-bit fetch
// packet are treated as the RISC-V hint header, and the lower 96 bits are
// six 16-bit instruction slots.  Hint immediate p-bits request parallel packing;
// dependency/resource breaks can still force a smaller execute packet.  If a
// non-control EP reaches the end of a fetch packet with free issue slots, the
// tail is carried over and packed with the start of the next fetch packet.

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

  input  logic                                      ipu_vliwpu_packet_valid_i,
  output logic                                      vliwpu_ipu_packet_ready_o,
  input  logic [FetchPacketWidth-1:0]               ipu_vliwpu_packet_i,
  input  addr_t                                     ipu_vliwpu_packet_pc_i,

  input  logic [NumSlots-2:0]                       ctrl_vliwpu_dep_break_i,
  output logic                                      vliwpu_heu_execute_valid_o,
  input  logic                                      heu_vliwpu_execute_ready_i,
  output logic [NumSlots-1:0]                       vliwpu_heu_execute_slot_valid_o,
  output logic [NumSlots-1:0][SlotWidth-1:0]        vliwpu_heu_execute_slot_o,
  output logic [NumSlots-1:0]                       vliwpu_heu_execute_slot_is_32b_o,
  output addr_t [NumSlots-1:0]                      vliwpu_heu_execute_slot_pc_o,
  output hdv_inst_class_e [NumSlots-1:0]            vliwpu_heu_execute_class_o,
  output addr_t                                     vliwpu_heu_execute_pc_o
);

  localparam int unsigned SlotIdxWidth = (NumSlots > 1) ? $clog2(NumSlots) : 1;
  localparam logic [SlotIdxWidth:0] MaxIssueSlotsCount = MaxIssueSlots;

  logic packet_hold_valid_d, packet_hold_valid_q;
  logic [FetchPacketWidth-1:0] packet_d, packet_q;
  addr_t packet_pc_d, packet_pc_q;
  logic [SlotIdxWidth-1:0] head_slot_d, head_slot_q;
  logic carry_valid_d, carry_valid_q;
  logic [NumSlots-1:0] carry_slot_valid_d, carry_slot_valid_q;
  logic [NumSlots-1:0][SlotWidth-1:0] carry_slot_d, carry_slot_q;
  logic [NumSlots-1:0] carry_slot_is_32b_d, carry_slot_is_32b_q;
  addr_t [NumSlots-1:0] carry_slot_pc_d, carry_slot_pc_q;
  hdv_inst_class_e [NumSlots-1:0] carry_class_d, carry_class_q;
  logic [SlotIdxWidth:0] carry_count_d, carry_count_q;
  addr_t carry_pc_d, carry_pc_q;
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
  logic current_packet_drained;
  logic last_slot_in_packet;
  logic stop_pack;
  logic normal_execute_valid;
  logic cross_execute_valid;
  logic tail_cross_candidate;
  logic tail_has_control;
  logic prior_has_control;
  logic [NumSlots-1:0] execute_slot_valid;
  logic [NumSlots-1:0][SlotWidth-1:0] execute_slot;
  logic [NumSlots-1:0] execute_slot_is_32b;
  addr_t [NumSlots-1:0] execute_slot_pc;
  hdv_inst_class_e [NumSlots-1:0] execute_class;
  logic [SlotIdxWidth-1:0] cross_next_head_slot;
  logic cross_next_drained;

  assign packet_accept  = ipu_vliwpu_packet_valid_i & vliwpu_ipu_packet_ready_o;
  assign execute_accept = vliwpu_heu_execute_valid_o & heu_vliwpu_execute_ready_i;
  assign current_packet_drained = packet_hold_valid_q & heu_vliwpu_execute_ready_i &
                                  last_slot_in_packet & !cross_execute_valid;
  assign vliwpu_ipu_packet_ready_o = carry_valid_q ? !packet_hold_valid_q :
                                     (!packet_hold_valid_q | current_packet_drained |
                                      tail_cross_candidate);

  assign header = packet_q[FetchPacketWidth-1 -: 32];
  // RISC-V HINT header is encoded as addi x0, x0, imm.  The paper defines
  // p-bits in the hint immediate field, so p_bits[0] is header[20].
  assign p_bits = header[20 +: NumSlots-1];

  for (genvar i = 0; i < NumSlots; i++) begin : gen_slots
    assign slots[i] = packet_q[i*SlotWidth +: SlotWidth];
    assign raw_slot_is_32b[i] = (slots[i][1:0] == 2'b11);
    assign vliwpu_heu_execute_slot_o[i] = execute_slot[i];
    assign vliwpu_heu_execute_slot_is_32b_o[i] = execute_slot_is_32b[i];
    assign vliwpu_heu_execute_slot_pc_o[i] = execute_slot_pc[i];
    assign vliwpu_heu_execute_class_o[i] = execute_class[i];
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

      // Output classes are assigned from execute_class after optional
      // cross-packet compaction.  slot_class only describes the raw packet.
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
            end else if (!p_bits[i+1] || ctrl_vliwpu_dep_break_i[i+1] ||
                         class_system_mask[i] || class_branch_mask[i]) begin
              stop_pack = 1'b1;
            end
            // else: continue; the loop will skip i+1 (continuation) and
            // consider i+2 as the next instruction candidate.
          end else if (!p_bits[i] || ctrl_vliwpu_dep_break_i[i] ||
                       class_system_mask[i] || class_branch_mask[i]) begin
            stop_pack = 1'b1;
          end
        end
      end
    end
  end

  always_comb begin : p_tail_cross
    tail_has_control = 1'b0;
    prior_has_control = 1'b0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (issue_mask[i] && !slot_is_continuation[i]) begin
        tail_has_control |= class_system_mask[i] | class_branch_mask[i];
      end
      if ((i < head_slot_q) && !slot_is_continuation[i]) begin
        prior_has_control |= class_system_mask[i] | class_branch_mask[i];
      end
    end
  end

  assign last_slot_in_packet = issue_mask[NumSlots-1];
  assign tail_cross_candidate = packet_hold_valid_q && !carry_valid_q &&
                                last_slot_in_packet &&
                                (issue_count < MaxIssueSlotsCount) &&
                                !tail_has_control && !prior_has_control;
  assign normal_execute_valid = packet_hold_valid_q && !tail_cross_candidate &&
                                !carry_valid_q;
  assign cross_execute_valid = carry_valid_q && packet_hold_valid_q;
  assign vliwpu_heu_execute_valid_o = normal_execute_valid | cross_execute_valid;
  assign vliwpu_heu_execute_slot_valid_o = execute_slot_valid;
  // Normal EPs use the fetch-packet base PC.  Cross-packet EPs are compacted
  // into slot 0..N, so the base PC becomes the carried tail instruction PC.
  assign vliwpu_heu_execute_pc_o = cross_execute_valid ? carry_pc_q : packet_pc_q;

  always_comb begin : p_cross_pack
    int unsigned out_idx;
    logic stop_cross;

    cross_next_head_slot = '0;
    cross_next_drained = 1'b1;
    execute_slot_valid = '0;
    execute_slot = '0;
    execute_slot_is_32b = '0;
    execute_slot_pc = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      execute_class[i] = HDV_INST_SCALAR;
    end

    if (cross_execute_valid) begin
      out_idx = 0;
      stop_cross = 1'b0;

      for (int unsigned i = 0; i < NumSlots; i++) begin
        if (carry_slot_valid_q[i]) begin
          execute_slot_valid[out_idx] = 1'b1;
          execute_slot[out_idx] = carry_slot_q[i];
          execute_slot_is_32b[out_idx] = carry_slot_is_32b_q[i];
          execute_slot_pc[out_idx] = carry_slot_pc_q[i];
          execute_class[out_idx] = carry_class_q[i];
          out_idx++;
        end
      end

      for (int unsigned i = 0; i < NumSlots; i++) begin
        if (!stop_cross && out_idx < MaxIssueSlotsCount && !slot_is_continuation[i]) begin
          execute_slot_valid[out_idx] = 1'b1;
          execute_slot[out_idx] = slots[i];
          execute_slot_is_32b[out_idx] = slot_is_32b[i];
          execute_slot_pc[out_idx] = packet_pc_q + addr_t'(i * (SlotWidth / 8));
          execute_class[out_idx] = slot_class[i];
          out_idx++;
          cross_next_head_slot = SlotIdxWidth'(i + 1);

          if (slot_is_32b[i] && i < NumSlots - 1 && out_idx < MaxIssueSlotsCount) begin
            execute_slot_valid[out_idx] = 1'b1;
            execute_slot[out_idx] = slots[i + 1];
            execute_slot_is_32b[out_idx] = 1'b0;
            execute_slot_pc[out_idx] = packet_pc_q + addr_t'((i + 1) * (SlotWidth / 8));
            execute_class[out_idx] = slot_class[i];
            out_idx++;
            cross_next_head_slot = SlotIdxWidth'(i + 2);

            if (i + 1 == NumSlots - 1 || out_idx >= MaxIssueSlotsCount) begin
              stop_cross = 1'b1;
            end else if (!p_bits[i+1] || ctrl_vliwpu_dep_break_i[i+1] ||
                         class_system_mask[i] || class_branch_mask[i]) begin
              stop_cross = 1'b1;
            end
          end else if (i == NumSlots - 1 || out_idx >= MaxIssueSlotsCount) begin
            stop_cross = 1'b1;
          end else if (!p_bits[i] || ctrl_vliwpu_dep_break_i[i] ||
                       class_system_mask[i] || class_branch_mask[i]) begin
            stop_cross = 1'b1;
          end
        end
      end

      cross_next_drained = (cross_next_head_slot == NumSlots[SlotIdxWidth-1:0]);
    end else begin
      execute_slot_valid = issue_mask;
      execute_slot = slots;
      execute_slot_is_32b = slot_is_32b;
      execute_class = slot_class;
      for (int unsigned i = 0; i < NumSlots; i++) begin
        execute_slot_pc[i] = packet_pc_q + addr_t'(i * (SlotWidth / 8));
      end
    end
  end

  always_comb begin : p_next
    packet_hold_valid_d = packet_hold_valid_q;
    packet_d            = packet_q;
    packet_pc_d         = packet_pc_q;
    head_slot_d         = head_slot_q;
    carry_valid_d       = carry_valid_q;
    carry_slot_valid_d  = carry_slot_valid_q;
    carry_slot_d        = carry_slot_q;
    carry_slot_is_32b_d = carry_slot_is_32b_q;
    carry_slot_pc_d     = carry_slot_pc_q;
    carry_class_d       = carry_class_q;
    carry_count_d       = carry_count_q;
    carry_pc_d          = carry_pc_q;

    if (tail_cross_candidate) begin
      int unsigned out_idx;

      out_idx = 0;
      carry_valid_d = 1'b1;
      carry_slot_valid_d = '0;
      carry_slot_d = '0;
      carry_slot_is_32b_d = '0;
      carry_slot_pc_d = '0;
      for (int unsigned i = 0; i < NumSlots; i++) begin
        carry_class_d[i] = HDV_INST_SCALAR;
      end
      carry_pc_d = packet_pc_q + addr_t'(head_slot_q * (SlotWidth / 8));

      for (int unsigned i = 0; i < NumSlots; i++) begin
        if (issue_mask[i]) begin
          carry_slot_valid_d[out_idx] = 1'b1;
          carry_slot_d[out_idx] = slots[i];
          carry_slot_is_32b_d[out_idx] = slot_is_32b[i];
          carry_slot_pc_d[out_idx] = packet_pc_q + addr_t'(i * (SlotWidth / 8));
          carry_class_d[out_idx] = slot_is_continuation[i] && (i > 0) ?
                                   slot_class[i-1] : slot_class[i];
          out_idx++;
        end
      end
      carry_count_d = out_idx[SlotIdxWidth:0];
      packet_hold_valid_d = 1'b0;
      head_slot_d = '0;
    end

    if (execute_accept) begin
      if (cross_execute_valid) begin
        carry_valid_d = 1'b0;
        carry_slot_valid_d = '0;
        carry_slot_d = '0;
        carry_slot_is_32b_d = '0;
        carry_slot_pc_d = '0;
        for (int unsigned i = 0; i < NumSlots; i++) begin
          carry_class_d[i] = HDV_INST_SCALAR;
        end
        carry_count_d = '0;
        carry_pc_d = '0;
        if (cross_next_drained) begin
          packet_hold_valid_d = 1'b0;
          head_slot_d = '0;
        end else begin
          head_slot_d = cross_next_head_slot;
        end
      end else begin
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
    end

    if (packet_accept) begin
      packet_hold_valid_d = 1'b1;
      packet_d            = ipu_vliwpu_packet_i;
      packet_pc_d         = ipu_vliwpu_packet_pc_i;
      head_slot_d         = '0;
    end

    if (flush_i) begin
      packet_hold_valid_d = 1'b0;
      head_slot_d         = '0;
      carry_valid_d       = 1'b0;
      carry_slot_valid_d  = '0;
      carry_slot_d        = '0;
      carry_slot_is_32b_d = '0;
      carry_slot_pc_d     = '0;
      carry_count_d       = '0;
      carry_pc_d          = '0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      packet_hold_valid_q <= 1'b0;
      packet_q            <= '0;
      packet_pc_q         <= '0;
      head_slot_q         <= '0;
      carry_valid_q       <= 1'b0;
      carry_slot_valid_q  <= '0;
      carry_slot_q        <= '0;
      carry_slot_is_32b_q <= '0;
      carry_slot_pc_q     <= '0;
      for (int unsigned i = 0; i < NumSlots; i++) begin
        carry_class_q[i]  <= HDV_INST_SCALAR;
      end
      carry_count_q       <= '0;
      carry_pc_q          <= '0;
    end else begin
      packet_hold_valid_q <= packet_hold_valid_d;
      packet_q            <= packet_d;
      packet_pc_q         <= packet_pc_d;
      head_slot_q         <= head_slot_d;
      carry_valid_q       <= carry_valid_d;
      carry_slot_valid_q  <= carry_slot_valid_d;
      carry_slot_q        <= carry_slot_d;
      carry_slot_is_32b_q <= carry_slot_is_32b_d;
      carry_slot_pc_q     <= carry_slot_pc_d;
      carry_class_q       <= carry_class_d;
      carry_count_q       <= carry_count_d;
      carry_pc_q          <= carry_pc_d;
    end
  end

endmodule : hdv_vliw_pack_unit
