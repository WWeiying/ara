// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Conservative VLIW Pack Unit.  IPU still supplies 128-bit fetch beats.  The
// first 32-bit word of the first beat is a RISC-V LUI x0, imm20 hint header:
//   imm20[12:0]  : p-bits between 16-bit slots in the logical packet
//   imm20[13]    : logical packet is 256-bit and consumes the next 128-bit beat
//   imm20[14]    : the tail EP may cross into the next logical packet
//   imm20[15]    : loop-start marker, decoded here for software-visible format
//   imm20[16]    : loop-end marker, decoded here for software-visible format
//
// The HEU interface remains NumSlots wide.  A 256-bit logical packet therefore
// only enlarges the VLIWPU packing window; it does not widen a single EP beyond
// MaxIssueSlots/NumSlots.

module hdv_vliw_pack_unit import hdv_pkg::*; #(
  parameter int unsigned XLEN             = 64,
  parameter int unsigned FetchPacketWidth = 128,
  parameter int unsigned NumSlots         = 8,
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
  output addr_t                                     vliwpu_heu_execute_pc_o,
  // Prefetch mode from HINT header imm20[18:17]: 00=off,01=1X,10=2X,11=4X
  output logic [1:0]                                vliwpu_prefetch_mode_o
);

  localparam int unsigned HeaderBytes       = 4;
  localparam int unsigned SlotBytes         = SlotWidth / 8;
  localparam int unsigned Packet128Slots    = (FetchPacketWidth - 32) / SlotWidth;
  localparam int unsigned Packet256Slots    = ((2 * FetchPacketWidth) - 32) / SlotWidth;
  localparam int unsigned PacketSlotIdxW    = (Packet256Slots > 1) ? $clog2(Packet256Slots + 1) : 1;
  localparam logic [PacketSlotIdxW:0] MaxIssueSlotsCount = MaxIssueSlots;

  typedef logic [2*FetchPacketWidth-1:0] logical_packet_t;
  typedef logic [PacketSlotIdxW-1:0]     packet_slot_idx_t;
  typedef logic [PacketSlotIdxW:0]       packet_slot_count_t;

  logic packet_hold_valid_d, packet_hold_valid_q;
  logical_packet_t packet_d, packet_q;
  addr_t packet_pc_d, packet_pc_q;
  logic packet_is_256_d, packet_is_256_q;
  packet_slot_idx_t head_slot_d, head_slot_q;

  logic pending_256_d, pending_256_q;
  logic [FetchPacketWidth-1:0] pending_first_beat_d, pending_first_beat_q;
  addr_t pending_first_pc_d, pending_first_pc_q;

  logic carry_valid_d, carry_valid_q;
  logic [NumSlots-1:0] carry_slot_valid_d, carry_slot_valid_q;
  logic [NumSlots-1:0][SlotWidth-1:0] carry_slot_d, carry_slot_q;
  logic [NumSlots-1:0] carry_slot_is_32b_d, carry_slot_is_32b_q;
  addr_t [NumSlots-1:0] carry_slot_pc_d, carry_slot_pc_q;
  hdv_inst_class_e [NumSlots-1:0] carry_class_d, carry_class_q;
  packet_slot_count_t carry_count_d, carry_count_q;
  addr_t carry_pc_d, carry_pc_q;

  logic [31:0] header;
  logic [31:0] incoming_header;
  logic [19:0] header_imm20;
  logic [Packet256Slots-2:0] p_bits;
  logic header_is_lui_hint;
  logic incoming_header_is_lui_hint;
  logic incoming_packet_256;
  logic header_packet_256;
  logic header_cross_next;
  logic header_loop_start;
  logic header_loop_end;
  logic [1:0] header_prefetch_mode;

  logic [Packet256Slots-1:0][SlotWidth-1:0] slots;
  logic [Packet256Slots-1:0] raw_slot_is_32b;
  logic [Packet256Slots-1:0] slot_is_32b;
  logic [Packet256Slots-1:0] slot_is_continuation;
  logic [Packet256Slots-1:0] issue_mask;
  logic [Packet256Slots-1:0] class_system_mask;
  logic [Packet256Slots-1:0] class_branch_mask;
  hdv_inst_class_e [Packet256Slots-1:0] slot_class;

  packet_slot_count_t active_slot_count;
  packet_slot_count_t issue_count;
  packet_slot_idx_t issue_next_head_slot;
  logic issue_packet_drained;
  logic issue_has_control;
  logic prior_has_control;

  logic packet_accept;
  logic execute_accept;
  logic packet_hold_can_accept;
  logic normal_execute_valid;
  logic cross_execute_valid;
  logic tail_cross_candidate;

  logic [NumSlots-1:0] execute_slot_valid;
  logic [NumSlots-1:0][SlotWidth-1:0] execute_slot;
  logic [NumSlots-1:0] execute_slot_is_32b;
  addr_t [NumSlots-1:0] execute_slot_pc;
  hdv_inst_class_e [NumSlots-1:0] execute_class;
  packet_slot_idx_t cross_next_head_slot;
  logic cross_next_drained;

  function automatic logic dep_break_at(input int unsigned boundary);
    if (boundary < NumSlots - 1) begin
      dep_break_at = ctrl_vliwpu_dep_break_i[boundary];
    end else begin
      dep_break_at = 1'b0;
    end
  endfunction

  function automatic logic p_bit_at(input int unsigned boundary);
    if (boundary < Packet256Slots - 1) begin
      p_bit_at = p_bits[boundary];
    end else begin
      p_bit_at = 1'b0;
    end
  endfunction

  function automatic hdv_inst_class_e classify_slot(input logic [SlotWidth-1:0] slot);
    classify_slot = HDV_INST_SCALAR;
    if ((slot[6:0] == 7'b1010111) ||
        (slot[6:0] == 7'b0000111 && slot[14:12] != 3'b010 && slot[14:12] != 3'b011) ||
        (slot[6:0] == 7'b0100111 && slot[14:12] != 3'b010 && slot[14:12] != 3'b011)) begin
      classify_slot = HDV_INST_VECTOR;
    // FENCE / FENCE.I (opcode 0x0F) is a memory-ordering barrier; classify it
    // as SYSTEM so it becomes a hard EP boundary and cannot be packed with
    // vector instructions that it must not cross.
    end else if ((slot[6:0] == 7'b0001111) ||
                 (slot[6:0] == 7'b1110011) ||
                 (slot[1:0] != 2'b11 && slot[15:13] == 3'b111)) begin
      classify_slot = HDV_INST_SYSTEM;
    end else if ((slot[6:0] == 7'b1100011) || (slot[6:0] == 7'b1101111) ||
                 (slot[6:0] == 7'b1100111)) begin
      classify_slot = HDV_INST_BRANCH;
    end
  endfunction

  assign packet_accept  = ipu_vliwpu_packet_valid_i & vliwpu_ipu_packet_ready_o;
  assign execute_accept = vliwpu_heu_execute_valid_o & heu_vliwpu_execute_ready_i;

  assign incoming_header = ipu_vliwpu_packet_i[31:0];
  assign incoming_header_is_lui_hint = (incoming_header[6:0] == 7'b0110111) &&
                                       (incoming_header[11:7] == 5'd0);
  assign incoming_packet_256 = incoming_header_is_lui_hint & incoming_header[25];

  assign header = packet_q[31:0];
  assign header_imm20 = header[31:12];
  assign header_is_lui_hint = (header[6:0] == 7'b0110111) && (header[11:7] == 5'd0);
  assign p_bits = header_is_lui_hint ? header_imm20[0 +: Packet256Slots-1] : '0;
  assign header_packet_256 = header_is_lui_hint & header_imm20[13];
  assign header_cross_next = header_is_lui_hint & header_imm20[14];
  assign header_loop_start = header_is_lui_hint & header_imm20[15];
  assign header_loop_end   = header_is_lui_hint & header_imm20[16];
  // Prefetch mode: imm20[18:17] — 00=off, 01=1X, 10=2X, 11=4X
  assign header_prefetch_mode = header_is_lui_hint ? header_imm20[18:17] : 2'b00;

  assign active_slot_count = packet_is_256_q ? packet_slot_count_t'(Packet256Slots) :
                                               packet_slot_count_t'(Packet128Slots);

  // The cross-packet path intentionally clears packet_hold_q and keeps a carry
  // fragment while waiting for the next logical packet.  Do not block input
  // ready on carry_valid_q in that state, otherwise cross-packet EP formation
  // cannot receive the packet it needs to complete the EP.
  assign packet_hold_can_accept = !packet_hold_valid_q ||
                                  tail_cross_candidate ||
                                  (execute_accept &&
                                   ((normal_execute_valid && issue_packet_drained) ||
                                    (cross_execute_valid && cross_next_drained)));
  assign vliwpu_ipu_packet_ready_o = packet_hold_can_accept;

  for (genvar i = 0; i < Packet256Slots; i++) begin : gen_slots
    assign slots[i] = packet_q[32 + i*SlotWidth +: SlotWidth];
    assign raw_slot_is_32b[i] = (i < active_slot_count) && (slots[i][1:0] == 2'b11);
  end

  for (genvar i = 0; i < NumSlots; i++) begin : gen_outputs
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

    for (int unsigned i = 0; i < Packet256Slots; i++) begin
      if (i >= active_slot_count) begin
        skip_next = 1'b0;
      end else if (skip_next) begin
        slot_is_continuation[i] = 1'b1;
        skip_next = 1'b0;
      end else if (raw_slot_is_32b[i] && i + 1 < active_slot_count) begin
        slot_is_32b[i] = 1'b1;
        skip_next = 1'b1;
      end
    end
  end

  always_comb begin : p_classify
    class_system_mask = '0;
    class_branch_mask = '0;

    for (int unsigned i = 0; i < Packet256Slots; i++) begin
      slot_class[i] = classify_slot(slots[i]);
      if (i >= active_slot_count) begin
        slot_class[i] = HDV_INST_SCALAR;
      end
      class_system_mask[i] = (slot_class[i] == HDV_INST_SYSTEM);
      class_branch_mask[i] = (slot_class[i] == HDV_INST_BRANCH);
    end
  end

  always_comb begin : p_issue_mask
    logic stop_pack;
    packet_slot_idx_t boundary;

    issue_mask = '0;
    issue_count = '0;
    issue_next_head_slot = head_slot_q;
    issue_packet_drained = 1'b0;
    stop_pack = 1'b0;
    boundary = '0;

    if (packet_hold_valid_q) begin
      for (int unsigned i = 0; i < Packet256Slots; i++) begin
        if (!stop_pack && (i >= head_slot_q) && (i < active_slot_count) &&
            !slot_is_continuation[i] && (issue_count < MaxIssueSlotsCount)) begin
          issue_mask[i] = 1'b1;
          issue_count++;
          issue_next_head_slot = packet_slot_idx_t'(i + 1);
          boundary = packet_slot_idx_t'(i);

          if (slot_is_32b[i] && (i + 1 < active_slot_count) &&
              (issue_count < MaxIssueSlotsCount)) begin
            issue_mask[i + 1] = 1'b1;
            issue_count++;
            issue_next_head_slot = packet_slot_idx_t'(i + 2);
            boundary = packet_slot_idx_t'(i + 1);
          end

          if (issue_next_head_slot >= active_slot_count ||
              issue_count >= MaxIssueSlotsCount ||
              !p_bit_at(boundary) || dep_break_at(boundary) ||
              class_system_mask[i] || class_branch_mask[i]) begin
            stop_pack = 1'b1;
          end
        end
      end
    end

    issue_packet_drained = packet_hold_valid_q && (issue_next_head_slot >= active_slot_count);
  end

  always_comb begin : p_tail_info
    issue_has_control = 1'b0;
    prior_has_control = 1'b0;

    for (int unsigned i = 0; i < Packet256Slots; i++) begin
      if (issue_mask[i] && !slot_is_continuation[i]) begin
        issue_has_control |= class_system_mask[i] | class_branch_mask[i];
      end
      if ((i < head_slot_q) && !slot_is_continuation[i]) begin
        prior_has_control |= class_system_mask[i] | class_branch_mask[i];
      end
    end
  end

  assign tail_cross_candidate = packet_hold_valid_q && !carry_valid_q &&
                                header_cross_next &&
                                issue_packet_drained &&
                                (issue_count < MaxIssueSlotsCount) &&
                                !issue_has_control && !prior_has_control;
  assign normal_execute_valid = packet_hold_valid_q && !tail_cross_candidate &&
                                !carry_valid_q;
  assign cross_execute_valid = carry_valid_q && packet_hold_valid_q;
  assign vliwpu_heu_execute_valid_o = normal_execute_valid | cross_execute_valid;
  assign vliwpu_heu_execute_slot_valid_o = execute_slot_valid;
  assign vliwpu_heu_execute_pc_o = cross_execute_valid ? carry_pc_q : packet_pc_q;
  // The EP-bundled copy of this (routed through the HEU register stage so it stays
  // aligned with the EP) is what the addrgen actually uses; this stays the live
  // value for the ara fallback path.
  assign vliwpu_prefetch_mode_o = packet_hold_valid_q ? header_prefetch_mode : 2'b00;

  always_comb begin : p_execute_pack
    int unsigned out_idx;
    logic stop_cross;
    packet_slot_idx_t boundary;

    cross_next_head_slot = '0;
    cross_next_drained = 1'b1;
    execute_slot_valid = '0;
    execute_slot = '0;
    execute_slot_is_32b = '0;
    execute_slot_pc = '0;
    boundary = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      execute_class[i] = HDV_INST_SCALAR;
    end

    out_idx = 0;
    if (cross_execute_valid) begin
      for (int unsigned i = 0; i < NumSlots; i++) begin
        if (carry_slot_valid_q[i] && out_idx < NumSlots) begin
          execute_slot_valid[out_idx] = 1'b1;
          execute_slot[out_idx] = carry_slot_q[i];
          execute_slot_is_32b[out_idx] = carry_slot_is_32b_q[i];
          execute_slot_pc[out_idx] = carry_slot_pc_q[i];
          execute_class[out_idx] = carry_class_q[i];
          out_idx++;
        end
      end

      stop_cross = 1'b0;
      for (int unsigned i = 0; i < Packet256Slots; i++) begin
        if (!stop_cross && (i < active_slot_count) && (out_idx < MaxIssueSlotsCount) &&
            !slot_is_continuation[i]) begin
          execute_slot_valid[out_idx] = 1'b1;
          execute_slot[out_idx] = slots[i];
          execute_slot_is_32b[out_idx] = slot_is_32b[i];
          execute_slot_pc[out_idx] = packet_pc_q + addr_t'(HeaderBytes + i * SlotBytes);
          execute_class[out_idx] = slot_class[i];
          out_idx++;
          cross_next_head_slot = packet_slot_idx_t'(i + 1);
          boundary = packet_slot_idx_t'(i);

          if (slot_is_32b[i] && (i + 1 < active_slot_count) &&
              (out_idx < MaxIssueSlotsCount)) begin
            execute_slot_valid[out_idx] = 1'b1;
            execute_slot[out_idx] = slots[i + 1];
            execute_slot_is_32b[out_idx] = 1'b0;
            execute_slot_pc[out_idx] = packet_pc_q + addr_t'(HeaderBytes + (i + 1) * SlotBytes);
            execute_class[out_idx] = slot_class[i];
            out_idx++;
            cross_next_head_slot = packet_slot_idx_t'(i + 2);
            boundary = packet_slot_idx_t'(i + 1);
          end

          if (cross_next_head_slot >= active_slot_count ||
              out_idx >= MaxIssueSlotsCount ||
              !p_bit_at(boundary) || dep_break_at(boundary) ||
              class_system_mask[i] || class_branch_mask[i]) begin
            stop_cross = 1'b1;
          end
        end
      end
      cross_next_drained = (cross_next_head_slot >= active_slot_count);
    end else begin
      for (int unsigned i = 0; i < Packet256Slots; i++) begin
        if (issue_mask[i] && out_idx < NumSlots) begin
          execute_slot_valid[out_idx] = 1'b1;
          execute_slot[out_idx] = slots[i];
          execute_slot_is_32b[out_idx] = slot_is_32b[i];
          execute_slot_pc[out_idx] = packet_pc_q + addr_t'(HeaderBytes + i * SlotBytes);
          execute_class[out_idx] = slot_is_continuation[i] && (i > 0) ?
                                   slot_class[i - 1] : slot_class[i];
          out_idx++;
        end
      end
    end
  end

  always_comb begin : p_next
    packet_hold_valid_d = packet_hold_valid_q;
    packet_d            = packet_q;
    packet_pc_d         = packet_pc_q;
    packet_is_256_d     = packet_is_256_q;
    head_slot_d         = head_slot_q;
    pending_256_d       = pending_256_q;
    pending_first_beat_d = pending_first_beat_q;
    pending_first_pc_d   = pending_first_pc_q;
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
      carry_pc_d = packet_pc_q + addr_t'(HeaderBytes + head_slot_q * SlotBytes);

      for (int unsigned i = 0; i < Packet256Slots; i++) begin
        if (issue_mask[i] && out_idx < NumSlots) begin
          carry_slot_valid_d[out_idx] = 1'b1;
          carry_slot_d[out_idx] = slots[i];
          carry_slot_is_32b_d[out_idx] = slot_is_32b[i];
          carry_slot_pc_d[out_idx] = packet_pc_q + addr_t'(HeaderBytes + i * SlotBytes);
          carry_class_d[out_idx] = slot_is_continuation[i] && (i > 0) ?
                                   slot_class[i - 1] : slot_class[i];
          out_idx++;
        end
      end
      carry_count_d = packet_slot_count_t'(out_idx);
      packet_hold_valid_d = 1'b0;
      packet_is_256_d = 1'b0;
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
          packet_is_256_d = 1'b0;
          head_slot_d = '0;
        end else begin
          head_slot_d = cross_next_head_slot;
        end
      end else begin
        if (issue_packet_drained) begin
          packet_hold_valid_d = 1'b0;
          packet_is_256_d = 1'b0;
          head_slot_d = '0;
        end else begin
          head_slot_d = issue_next_head_slot;
        end
      end
    end

    if (packet_accept) begin
      if (pending_256_q) begin
        packet_hold_valid_d = 1'b1;
        packet_d = {ipu_vliwpu_packet_i, pending_first_beat_q};
        packet_pc_d = pending_first_pc_q;
        packet_is_256_d = 1'b1;
        head_slot_d = '0;
        pending_256_d = 1'b0;
        pending_first_beat_d = '0;
        pending_first_pc_d = '0;
      end else if (incoming_packet_256) begin
        pending_256_d = 1'b1;
        pending_first_beat_d = ipu_vliwpu_packet_i;
        pending_first_pc_d = ipu_vliwpu_packet_pc_i;
      end else begin
        packet_hold_valid_d = 1'b1;
        packet_d = {{FetchPacketWidth{1'b0}}, ipu_vliwpu_packet_i};
        packet_pc_d = ipu_vliwpu_packet_pc_i;
        packet_is_256_d = 1'b0;
        head_slot_d = '0;
      end
    end

    if (flush_i) begin
      packet_hold_valid_d = 1'b0;
      packet_d            = '0;
      packet_pc_d         = '0;
      packet_is_256_d     = 1'b0;
      head_slot_d         = '0;
      pending_256_d       = 1'b0;
      pending_first_beat_d = '0;
      pending_first_pc_d   = '0;
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
      packet_is_256_q     <= 1'b0;
      head_slot_q         <= '0;
      pending_256_q       <= 1'b0;
      pending_first_beat_q <= '0;
      pending_first_pc_q   <= '0;
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
      packet_is_256_q     <= packet_is_256_d;
      head_slot_q         <= head_slot_d;
      pending_256_q       <= pending_256_d;
      pending_first_beat_q <= pending_first_beat_d;
      pending_first_pc_q   <= pending_first_pc_d;
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

  `ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin
    if (rst_ni && packet_hold_valid_q && header_is_lui_hint) begin
      if (header_packet_256 != packet_is_256_q) begin
        $warning("[HDV] VLIWPU header packet_256 bit and assembled packet width disagree at pc=0x%0h",
                 packet_pc_q);
      end
      if (header_loop_start || header_loop_end) begin
        // Loop markers are part of the software-visible header format.  The
        // current loop-lock implementation is still driven by branch redirect.
      end
    end
  end

  always_ff @(posedge clk_i) begin : p_pf_probe_pack
    if (rst_ni && $test$plusargs("HDV_PF_PROBE") && execute_accept &&
        (vliwpu_heu_execute_pc_o >= addr_t'(64'h8000_1000)) &&
        (vliwpu_heu_execute_pc_o <= addr_t'(64'h8000_1200))) begin
      $display("[PFPROBE-PACK] ev=execute pc=0x%0h packet_pc=0x%0h head=%0d is256=%0d cross=%0d tail_cross=%0d pbits=0x%0h dep=0x%0h issue=0x%0h issue_next=%0d drained=%0d slot32=0x%0h cont=0x%0h active=%0d raw0=0x%032h raw1=0x%032h",
               vliwpu_heu_execute_pc_o, packet_pc_q, head_slot_q, packet_is_256_q,
               cross_execute_valid, tail_cross_candidate, p_bits, ctrl_vliwpu_dep_break_i,
               issue_mask, issue_next_head_slot, issue_packet_drained, slot_is_32b,
               slot_is_continuation, active_slot_count, packet_q[127:0], packet_q[255:128]);
      $display("[PFPROBE-PACK] slots pc=0x%0h s0=0x%04h s1=0x%04h s2=0x%04h s3=0x%04h s4=0x%04h s5=0x%04h s6=0x%04h s7=0x%04h",
               packet_pc_q, slots[0], slots[1], slots[2], slots[3],
               slots[4], slots[5], slots[6], slots[7]);
      $display("[PFPROBE-PACK] exec valid=%b is32=%b pc0=0x%0h e0=0x%04h pc1=0x%0h e1=0x%04h pc2=0x%0h e2=0x%04h pc3=0x%0h e3=0x%04h pc4=0x%0h e4=0x%04h pc5=0x%0h e5=0x%04h pc6=0x%0h e6=0x%04h pc7=0x%0h e7=0x%04h",
               execute_slot_valid, execute_slot_is_32b,
               execute_slot_pc[0], execute_slot[0], execute_slot_pc[1], execute_slot[1],
               execute_slot_pc[2], execute_slot[2], execute_slot_pc[3], execute_slot[3],
               execute_slot_pc[4], execute_slot[4], execute_slot_pc[5], execute_slot[5],
               execute_slot_pc[6], execute_slot[6], execute_slot_pc[7], execute_slot[7]);
    end
  end
  `endif

endmodule : hdv_vliw_pack_unit
