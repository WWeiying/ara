// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// Ara's sequencer controls the ordering and the dependencies between the
// parallel vector instructions in execution.

module ara_sequencer import ara_pkg::*; import rvv_pkg::*; import cf_math_pkg::idx_width; #(
    // RVV Parameters
    parameter  int unsigned NrLanes     = 1,          // Number of parallel vector lanes
    parameter  int unsigned VLEN        = 0,
    parameter  type         ara_req_t   = logic,
    parameter  type         ara_resp_t  = logic,
    parameter  type         pe_req_t    = logic,
    parameter  type         pe_resp_t   = logic,
    parameter  type         exception_t = logic,
    // Dependant parameters. DO NOT CHANGE!
    // Ara has NrLanes + 3 processing elements: each one of the lanes, the vector load unit, the
    // vector store unit, the slide unit, and the mask unit.
    localparam int unsigned NrPEs   = NrLanes + 4,
    localparam type         vlen_t  = logic[$clog2(VLEN+1)-1:0]
  ) (
    input  logic                            clk_i,
    input  logic                            rst_ni,
    // Interface with Ara's dispatcher
    input  ara_req_t                        ara_req_i,
    input  logic                            ara_req_valid_i,
    output logic                            ara_req_ready_o,
    output ara_resp_t                       ara_resp_o,
    output logic                            ara_resp_valid_o,
    output logic                            ara_idle_o,
    // Interface with the processing elements
    output pe_req_t                         pe_req_o,
    output logic                            pe_req_valid_o,
    output logic              [NrVInsn-1:0] pe_vinsn_running_o,
    input  logic                [NrPEs-1:0] pe_req_ready_i,
    input  pe_resp_t            [NrPEs-1:0] pe_resp_i,
    input  logic                            alu_vinsn_done_i,
    input  logic                            mfpu_vinsn_done_i,
    // Interface with the operand requesters
    output logic [NrVInsn-1:0][NrVInsn-1:0] global_hazard_table_o,
    // Only the slide unit can answer with a scalar response
    input  elen_t                           pe_scalar_resp_i,
    input  logic                            pe_scalar_resp_valid_i,
    output logic                            pe_scalar_resp_ready_o,
    // Interface with the Address Generation
    input  logic                            addrgen_ack_i,
    input  exception_t                      addrgen_exception_i,
    input  vlen_t                           addrgen_exception_vstart_i,
    input  logic                            addrgen_fof_exception_i,
    // Interface with the store unit
    input  logic                            lsu_current_burst_exception_i,
    // Terminal status from a blocking QBS command
    input  logic                      [4:0] qbs_fflags_i,
    input  logic                            qbs_fflags_valid_i
  );

  `include "common_cells/registers.svh"

  `ifdef FOR_VERIFY
  logic raw_hazard, war_hazard, waw_hazard, false_hazard, sequencer_block;
  logic verify_vinsn_alloc;
  logic [NrVInsn-1:0] verify_vinsn_done;
  `endif
  ///////////////////////////////////
  //  Running vector instructions  //
  ///////////////////////////////////

  // A set bit indicates that the corresponding vector instruction is running at that PE.
  logic [NrPEs-1:0][NrVInsn-1:0] pe_vinsn_running_d, pe_vinsn_running_q;

  // A set bit indicates that the corresponding vector instruction in running somewhere in Ara.
  logic [NrVInsn-1:0] vinsn_running_d, vinsn_running_q;
  logic [NrVInsn-1:0] vinsn_running_prev_q, vinsn_retired_q;
  vid_t               vinsn_id_n;
  logic               vinsn_running_full;

  // NrLanes bits that indicate if the sequencer must stall because of a lane desynchronization.
  logic [NrVInsn-1:0] stall_lanes_desynch_vec;
  logic               stall_lanes_desynch;
  // Transpose the matrix, as vertical slices are not allowed in System Verilog
  logic [NrVInsn-1:0][NrPEs-1:0] pe_vinsn_running_q_trns;

  // Ara is idle if no instruction is currently running on it.
  assign ara_idle_o = !(|vinsn_running_q);

  lzc #(.WIDTH(NrVInsn)) i_next_id (
    .in_i   (~(vinsn_running_q | vinsn_running_prev_q)),
    .cnt_o  (vinsn_id_n        ),
    .empty_o(vinsn_running_full)
  );

  always_comb begin: p_vinsn_running
    vinsn_running_d = '0;
    for (int unsigned pe = 0; pe < NrPEs; pe++) vinsn_running_d |= pe_vinsn_running_d[pe];
  end: p_vinsn_running

  always_ff @(posedge clk_i or negedge rst_ni) begin: p_vinsn_running_ff
    if (!rst_ni) begin
      vinsn_running_q    <= '0;
      vinsn_running_prev_q <= '0;
      vinsn_retired_q    <= '0;
      pe_vinsn_running_q <= '0;
    end else begin
      vinsn_running_prev_q <= vinsn_running_q;
      vinsn_retired_q    <= vinsn_running_q & ~vinsn_running_d;
      vinsn_running_q    <= vinsn_running_d;
      pe_vinsn_running_q <= pe_vinsn_running_d;
    end
  end

  assign pe_vinsn_running_o = vinsn_running_q;

  `ifdef FOR_VERIFY
  // Report completion of the old vid independently of same-cycle vid reuse.
  // This is verification-only metadata consumed by ara_commit_monitor.
  for (genvar id = 0; id < NrVInsn; id++) begin : gen_verify_vinsn_done
    always_comb begin
      verify_vinsn_done[id] = vinsn_running_q[id];
      for (int unsigned pe = 0; pe < NrPEs; pe++) begin
        verify_vinsn_done[id] &=
            ~(pe_vinsn_running_q[pe][id] & ~pe_resp_i[pe].vinsn_done[id]);
      end
    end
  end
  `endif

  // Transpose the matrix
  for (genvar r = 0; r < NrVInsn; r++) begin : gen_trans_mtx_r
    for (genvar c = 0; c < NrPEs; c++) begin : gen_trans_mtx_c
      assign pe_vinsn_running_q_trns[r][c] = pe_vinsn_running_q[c][r];
    end
  end

  // Stall the sequencer if the lanes get de-synchronized
  // and lane 0 is no more the last lane to finish the operation.
  // This is because the instruction counters for ALU and MFPU refers
  // to lane 0. If lane 0 finishes before the other lanes, the counter
  // is not reflecting the real lane situations anymore.
  for (genvar i = 0; i < NrVInsn; i++) begin : gen_stall_lane_desynch
    assign stall_lanes_desynch_vec[i] = ~pe_vinsn_running_q[0][i] & |pe_vinsn_running_q_trns[i][NrLanes-1:1];
  end
  assign stall_lanes_desynch = |stall_lanes_desynch_vec;

  /////////////////////////
  // Global Hazard table //
  /////////////////////////

  // Global table of the dependencies between instructions
  //
  // The row at index N is the hazard vector belonging to instruction N
  // It indicates all the instruction on which instruction N depends
  //
  // For example, with the following table, instruction 3 depends on
  // instruction 0 and instruction 2
  //
  // +--------+--------+--------+--------+--------+
  // |   -    | Insn 0 | Insn 1 | Insn 2 | Insn 3 |
  // +--------+--------+--------+--------+--------+
  // | Insn 0 |      0 |      0 |      0 |      0 |
  // | Insn 1 |      1 |      0 |      0 |      0 |
  // | Insn 2 |      0 |      0 |      0 |      0 |
  // | Insn 3 |      1 |      0 |      1 |      0 |
  // +--------+--------+--------+--------+--------+
  //
  // This information is forwarded to the operand requesters of each lane

  logic [NrVInsn-1:0][NrVInsn-1:0] global_hazard_table_d;

  ////////////////////////
  // Start and End lane //
  ////////////////////////

  pe_req_t pe_req_d;
  logic    pe_req_valid_d;

  // Some units outside the lanes, e.g., the store unit, always need
  // to receive operands from all the lanes. For this reason,
  // we need to know if each lane will need to fetch one operand
  // more (mock operand) to balance the other lane true operands.
  // With vstart != 0 and EW != 64bit, this operation is a harder to be done
  // within the lanes without further help.
  // Therefore, we calculate here the start and end lanes, i.e., the lanes
  // that respectively will provide the first and last true element of
  // the computation.
  logic [$clog2(NrLanes)-1:0] start_lane, end_lane;
  // Buffers to simplify the code reading
  logic [$clog2(8*NrLanes)-1:0] buf8;
  logic [$clog2(4*NrLanes)-1:0] buf16;
  logic [$clog2(2*NrLanes)-1:0] buf32;

  always_comb begin
    // start_lane and end_lane has default values in the unique case statement already
    buf8       = '0;
    buf16      = '0;
    buf32      = '0;

    // Start lane
    // Number of elements in a single L*64-bit fetch: (NrLanes << (64 - pe_req_d.vtype.vsew)).
    // vstart / (NrLanes << (64 - pe_req_d.vtype.vsew)) -> don't care.
    // vstart % NrLanes -> our starting lane if:
    // (vstart % (NrLanes << (64 - pe_req_d.vtype.vsew))) / NrLanes.
    // Otherwise, the starting lane continues to be the 0th.

    // End lane
    // Number of elements in a single L*64-bit fetch: (NrLanes << (64 - pe_req_d.vtype.vsew)).
    // vl / (NrLanes << (64 - pe_req_d.vtype.vsew)) -> don't care.
    // (vl % NrLanes) - 1 -> our end lane if:
    // (vl % (NrLanes << (64 - pe_req_d.vtype.vsew)) - 1) / NrLanes.
    // With the end lane we should subtract 1 since vl represents a number of
    // elements and NOT an index.
    unique case (pe_req_d.vtype.vsew)
      EW8: begin
        start_lane = &pe_req_d.vstart[$clog2(8*NrLanes)-1:$clog2(NrLanes)]
                   ? pe_req_d.vstart[$clog2(NrLanes)-1:0]
                   : '0;
        buf8       = pe_req_d.vl[$clog2(8*NrLanes)-1:0] - 1;
        end_lane   = !(|buf8[$clog2(8*NrLanes)-1:$clog2(NrLanes)])
                   ? pe_req_d.vl[$clog2(NrLanes)-1:0] - 1
                   : '1;
      end
      EW16: begin
        start_lane = &pe_req_d.vstart[$clog2(4*NrLanes)-1:$clog2(NrLanes)]
                   ? pe_req_d.vstart[$clog2(NrLanes)-1:0]
                   : '0;
        buf16      = pe_req_d.vl[$clog2(4*NrLanes)-1:0] - 1;
        end_lane   = !(|buf16[$clog2(4*NrLanes)-1:$clog2(NrLanes)])
                   ? pe_req_d.vl[$clog2(NrLanes)-1:0] - 1
                   : '1;
      end
      EW32: begin
        start_lane = &pe_req_d.vstart[$clog2(2*NrLanes)-1:$clog2(NrLanes)]
                   ? pe_req_d.vstart[$clog2(NrLanes)-1:0]
                   : '0;
        buf32      = pe_req_d.vl[$clog2(2*NrLanes)-1:0] - 1;
        end_lane   = !(|buf32[$clog2(2*NrLanes)-1:$clog2(NrLanes)])
                   ? pe_req_d.vl[$clog2(NrLanes)-1:0] - 1
                   : '1;
      end
      // EW64, default
      default: begin
        start_lane = pe_req_d.vstart[$clog2(NrLanes)-1:0];
        end_lane   = pe_req_d.vl[$clog2(NrLanes)-1:0] - 1;
      end
    endcase
  end

  /////////////////
  //  Sequencer  //
  /////////////////

  // If the instruction requires an answer to Ariane, the sequencer needs to wait.
  enum logic { IDLE, WAIT } state_d, state_q;
  logic addrgen_acked_d, addrgen_acked_q;
  exception_t addrgen_exception_d, addrgen_exception_q;
  vlen_t addrgen_exception_vstart_d, addrgen_exception_vstart_q;
  logic addrgen_fof_exception_d, addrgen_fof_exception_q;
  logic [NrLanes-1:0] memory_lane_accepted_d, memory_lane_accepted_q;
  logic memory_mask_accepted_d, memory_mask_accepted_q;

  // For hazard detection, we need to know which vector instruction is reading/writing to each
  // vector register
  typedef struct packed {
    vid_t vid;
    logic [2:0] group_offset;
    // The normal chaining scheme assumes that source reads and destination
    // writes advance through the VRF in the same physical-word order.  Keep
    // hazards against reordered accesses until the whole instruction retires.
    logic wait_complete;
    logic valid;
  } vreg_access_t;
  vreg_access_t [31:0] read_list_d, read_list_q;
  vreg_access_t [31:0] write_list_d, write_list_q;
  // A register can have several concurrent readers. read_list keeps the
  // newest reader's chaining metadata, while this bitmap preserves every
  // in-flight reader that a younger writer must observe.
  logic [31:0][NrVInsn-1:0] read_mask_d, read_mask_q;
  logic multi_reader_war;

  // This function determines the VFU responsible for handling this operation.
  function automatic vfu_e vfu(ara_op_e op`ifndef SYNTHESIS = VADD `endif);
    unique case (op) inside
      [VADD:VWREDSUM]      : vfu = VFU_Alu;
      [VMUL:VFWREDOSUM]    : vfu = VFU_MFpu;
      [VMFEQ:VCOMPRESS]    : vfu = VFU_MaskUnit;
      [VLE:VLXE], VQBEXEC, VAKVFILL, VAKVLOAD, VAKVRELEASE:
          vfu = VFU_LoadUnit;
      [VSE:VSXE]           : vfu = VFU_StoreUnit;
      [VSLIDEUP:VSLIDEDOWN]: vfu = VFU_SlideUnit;
      [VMVXS:VFMVFS]       : vfu = VFU_None;
      default              : vfu = VFU_None;
    endcase
  endfunction : vfu

  // This function determines all the targets VFUs of this operation and returns
  // a vector. Asserted bits correspond to target VFUs. Unluckily, Verilator does
  // not support assignment patterns with enum types on the indices
  function automatic logic [NrVFUs-1:0] target_vfus(ara_op_e op);
    target_vfus = '0;
    unique case (op) inside
      [VADD:VFMVSF]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_Alu) target_vfus[i] = 1'b1;
      [VREDSUM:VWREDSUM]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_Alu || i == VFU_SlideUnit) target_vfus[i] = 1'b1;
      [VFREDUSUM:VFWREDOSUM]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_MFpu || i == VFU_SlideUnit) target_vfus[i] = 1'b1;
      [VMUL:VFCVTFF]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_MFpu) target_vfus[i] = 1'b1;
      [VMSEQ:VMXNOR]:
        for (int i = 0; i < NrVFUs; i++)
          // VID is generated entirely inside MASKU. Unlike the other mask
          // operations in this range, it has no lane-ALU preprocessing phase.
          if (i == VFU_MaskUnit || (i == VFU_Alu && op != VID))
            target_vfus[i] = 1'b1;
      [VRGATHER:VCOMPRESS]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_Alu || i == VFU_MaskUnit) target_vfus[i] = 1'b1;
      [VMFEQ:VMFGE]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_MFpu || i == VFU_MaskUnit) target_vfus[i] = 1'b1;
      [VLE:VLXE], VQBEXEC, VAKVFILL, VAKVLOAD, VAKVRELEASE:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_LoadUnit) target_vfus[i] = 1'b1;
      [VSE:VSXE]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_StoreUnit) target_vfus[i] = 1'b1;
      [VSLIDEUP:VSLIDEDOWN]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_SlideUnit) target_vfus[i] = 1'b1;
      [VMVXS:VFMVFS]:
        for (int i = 0; i < NrVFUs; i++)
          if (i == VFU_None) target_vfus[i] = 1'b1;
    endcase
  endfunction : target_vfus

  // Determine if the request does not need source operands from the VRF
  function automatic logic no_src_vrf(pe_req_t pe_req);
    no_src_vrf = (((pe_req.op == VLE || pe_req.op == VLSE) && pe_req.vm) ||
                  pe_req.op inside {
                    VQBEXEC, VAKVFILL, VAKVLOAD, VAKVRELEASE
                  });
  endfunction

  function automatic logic mask_result(ara_op_e op);
    mask_result = op inside {
      [VMFEQ:VMFGE], [VMSEQ:VMSGT], [VMADC:VMSBC], [VMSBF:VMSIF],
      [VMANDNOT:VMXNOR]
    };
  endfunction

  function automatic logic reduction_result(ara_op_e op);
    reduction_result = op inside {
      [VREDSUM:VWREDSUM], [VFREDUSUM:VFWREDOSUM]
    };
  endfunction

  function automatic int unsigned lmul_register_count(vlmul_e lmul);
    unique case (lmul)
      LMUL_2: lmul_register_count = 2;
      LMUL_4: lmul_register_count = 4;
      LMUL_8: lmul_register_count = 8;
      default: lmul_register_count = 1;
    endcase
  endfunction

  function automatic int unsigned destination_register_count(ara_req_t req);
    destination_register_count =
        (mask_result(req.op) || reduction_result(req.op))
        ? 1 : lmul_register_count(req.emul);
  endfunction

  function automatic int unsigned source_register_count(
      ara_req_t req, vew_e source_eew, logic first_source
  );
    automatic int unsigned count;

    // Indexed memory operands use EMUL = LMUL * EEW_index / SEW even
    // though the load destination or store data group keeps data LMUL.
    if (!first_source && req.op inside {VLXE, VSXE}) begin
      automatic vlmul_e index_lmul = vlmul_e'(
          req.vtype.vlmul + (source_eew - req.vtype.vsew));
      source_register_count = lmul_register_count(index_lmul);
      return source_register_count;
    end

    // A reduction's destination EMUL is one register, but its vector data
    // source still spans the current data LMUL.  Keep the scalar seed at one
    // register and do not apply widening-result scaling to the data source.
    if (reduction_result(req.op)) begin
      source_register_count = first_source
          ? 1 : lmul_register_count(req.vtype.vlmul);
      return source_register_count;
    end

    // Mask-producing instructions also have a one-register destination while
    // comparisons and carry operations consume full data-LMUL source groups.
    count = lmul_register_count(mask_result(req.op) ? req.vtype.vlmul : req.emul);

    // Architectural mask operands occupy one register independently of the
    // data LMUL used by the other operands.
    if (req.op inside {[VMANDNOT:VMXNOR], [VMSBF:VMSIF], VCPOP, VFIRST, VIOTA} ||
        (first_source && req.op == VCOMPRESS)) begin
      count = 1;
    end else if (!is_store(req.op)) begin
      // Widening requests encode the wider destination EMUL, while narrowing
      // requests encode the narrower destination EMUL. Adjust only operands
      // whose EEW differs from the destination EEW; .W forms retain EMUL.
      if ((req.cvt_resize == CVT_WIDE) &&
          (unsigned'(source_eew) < unsigned'(req.vtype.vsew))) begin
        count = count > 1 ? count >> 1 : 1;
      end else if (((req.cvt_resize == CVT_NARROW) ||
                    req.op inside {VNSRL, VNSRA, VNCLIP, VNCLIPU}) &&
                   (unsigned'(source_eew) > unsigned'(req.vtype.vsew))) begin
        count = count < 8 ? count << 1 : 8;
      end
    end

    source_register_count = count;
  endfunction

  localparam int unsigned InsnQueueDepth [NrVFUs] = '{
    ValuInsnQueueDepth,
    MfpuInsnQueueDepth,
    SlduInsnQueueDepth,
    MaskuInsnQueueDepth,
    VlduInsnQueueDepth,
    VstuInsnQueueDepth,
    NoneInsnQueueDepth
  };

  logic ara_req_token_d, ara_req_token_q;

  // Counters keep track of how many instructions each unit is running.
  // They have the same size only to keep the code easy.
  logic [NrVFUs-1:0] [idx_width(MaxVInsnQueueDepth + 1)-1:0] insn_queue_cnt_q;
  logic [NrVFUs-1:0] insn_queue_done;
  logic [NrVFUs-1:0] insn_queue_cnt_en, insn_queue_cnt_down, insn_queue_cnt_up;
  // Each FU has its own ready signal
  logic [NrVFUs-1:0] vinsn_queue_ready;
  // Bit [i] is 1'b1 if the respective PE is ready for the issue of this insn
  logic [NrVFUs-1:0] vinsn_queue_issue;
  logic              accepted_insn, accepted_insn_stalled;
  logic [NrVFUs-1:0] target_vfus_vec;
  // Gold tickets and passes
  // Normally, instructions can be issued to the lane sequencer only if
  // the counters have not reached their maximum capacity.
  // When an instruction enters the main sequencer, it can happen that the
  // counter is already at maximum capacity The instruction is
  // registered anyway taking the counter beyond the maximum capacity.
  // In this case, the instruction will get a gold ticket, to witness that
  // it was already registered with the counter, so that the instruction can
  // pass the checks when the counter returns within its limits, even if
  // it is at its maximum capacity (the instruction was already counted!)
  logic [NrVFUs-1:0] gold_ticket_d, gold_ticket_q;
  logic [NrVFUs-1:0] priority_pass;

  // Signal to know if there is a mask instruction being executed by the MASKU
  // that can use the MaskB operand queue. If there is a running MASKU instruction,
  // we cannot sample the scalar operand.
  // Since the scalar move uses the MaskB opqueue, we need to wait to finish
  // the MASKU insn to be sure that the forwarded value is the scalar one
  logic pending_mask_insn_d, pending_mask_insn_q;
  logic running_mask_insn_d, running_mask_insn_q;

  logic lsu_current_burst_exception_q;
  `FF(lsu_current_burst_exception_q, lsu_current_burst_exception_i, 1'b0, clk_i, rst_ni);

  // pe_req_ready_i comes from all the lanes
  // It is deasserted if the current request is stuck
  // because the target operand requesters are not ready in that lane
  logic [NrLanes-1:0] operand_requester_ready;
  assign operand_requester_ready = pe_req_ready_i[NrLanes-1:0];

  logic mask_requester_ready;
  assign mask_requester_ready =
      (pe_req_o.vm && pe_req_o.vfu != VFU_MaskUnit) ||
      pe_req_ready_i[NrLanes+OffsetMask];

  logic slide_requester_ready;
  assign slide_requester_ready =
      !((pe_req_o.vfu == VFU_SlideUnit) ||
        (pe_req_o.op inside {[VREDSUM:VWREDSUM], [VFREDUSUM:VFWREDOSUM]})) ||
      pe_req_ready_i[NrLanes+OffsetSlide];

  logic pe_req_broadcast_valid;
  assign pe_req_broadcast_valid = pe_req_valid_o &&
      ((pe_req_o.vm && pe_req_o.vfu != VFU_MaskUnit) ||
       (((&operand_requester_ready) || no_src_vrf(pe_req_o)) &&
        pe_req_ready_i[NrLanes+OffsetMask]));

  // Update the token only upon new instructions
  assign ara_req_token_d = (ara_req_valid_i) ? ara_req_i.token : ara_req_token_q;

  always_comb begin: p_sequencer
    // Default assignments
    state_d               = state_q;
    addrgen_acked_d       = addrgen_acked_q;
    addrgen_exception_d   = addrgen_exception_q;
    addrgen_exception_vstart_d = addrgen_exception_vstart_q;
    addrgen_fof_exception_d = addrgen_fof_exception_q;
    memory_lane_accepted_d = memory_lane_accepted_q;
    memory_mask_accepted_d = memory_mask_accepted_q;
    pe_vinsn_running_d    = pe_vinsn_running_q;
    read_list_d           = read_list_q;
    read_mask_d           = read_mask_q;
    write_list_d          = write_list_q;
    global_hazard_table_d = global_hazard_table_o;
    multi_reader_war      = 1'b0;

    // Maintain request
    pe_req_d       = '0;
    pe_req_valid_d = 1'b0;

    // No response
    ara_resp_o       = '0;
    ara_resp_valid_o = 1'b0;

    // Always ready to receive a new request
    ara_req_ready_o = 1'b1;

    // Not ready by default
    pe_scalar_resp_ready_o = 1'b0;

    // Retire access-list entries in the same cycle in which the corresponding
    // running bit becomes clear, without placing the full running-state fanout
    // directly on the request-ready hazard path.
    for (int unsigned v = 0; v < 32; v++) begin
      read_list_d[v].valid &= ~vinsn_retired_q[read_list_q[v].vid];
      read_mask_d[v]       &= ~vinsn_retired_q;
      write_list_d[v].valid &= ~vinsn_retired_q[write_list_q[v].vid];
    end

    // Update the running vector instructions
    for (int pe = 0; pe < NrPEs; pe++) pe_vinsn_running_d[pe] &= ~pe_resp_i[pe].vinsn_done;
    `ifdef FOR_VERIFY
    raw_hazard = '0;
    war_hazard = '0;
    waw_hazard = '0;
    false_hazard = '0;
    sequencer_block = '0;
    verify_vinsn_alloc = 1'b0;
    `endif

    case (state_q)
      IDLE: begin
        // Sent a request, but the operand requesters are not ready
        // Do not trap here the instructions that do not need any operands at all
        if (pe_req_valid_o &&
            (!(&operand_requester_ready || no_src_vrf(pe_req_o)) ||
             !mask_requester_ready || !slide_requester_ready)) begin
          // Maintain output
          pe_req_d               = pe_req_o;
          pe_req_valid_d         = pe_req_valid_o;

          // If we are here after a faulty lsu op with VRF sources,
          // wait until the lsu signals the exception on the current burst before aborting the request.
          if (lsu_current_burst_exception_q)
            pe_req_valid_d = 1'b0;

          // We are not ready
          ara_req_ready_o = 1'b0;
        // Received a new request
        end else if (ara_req_valid_i) begin
          // The target PE is ready, and we can handle another running vector instruction
          // Let instructions with priority pass be issued
          // MaskB has no ownership tag on its lane-to-MASKU interface. Keep a
          // scalar extract behind every older vector instruction so lane 0
          // cannot route an older MaskB operand into the scalar return path.
          if (&vinsn_queue_issue && !stall_lanes_desynch && !vinsn_running_full &&
              !((ara_req_i.op inside {[VMVXS:VFMVFS]}) &&
                ((|vinsn_running_q) || pending_mask_insn_q || running_mask_insn_q))) begin
            ///////////////
            //  Hazards  //
            ///////////////

            begin : group_hazard_check
              automatic int unsigned vd_regs = destination_register_count(ara_req_i);
              automatic int unsigned vs1_regs =
                  source_register_count(ara_req_i, ara_req_i.eew_vs1, 1'b1);
              automatic int unsigned vs2_regs =
                  source_register_count(ara_req_i, ara_req_i.eew_vs2, 1'b0);
              logic [NrVInsn-1:0] raw_hazard_vec;
              logic [NrVInsn-1:0] war_hazard_vec;
              logic [NrVInsn-1:0] waw_hazard_vec;
              logic [NrVInsn-1:0] wait_complete_vec;

              raw_hazard_vec = '0;
              war_hazard_vec = '0;
              waw_hazard_vec = '0;
              wait_complete_vec = '0;

              // RAW. Register groups are tracked at physical-register
              // granularity so an access to v11 cannot bypass an older m4
              // write whose architectural base is v8.
              for (int unsigned i = 0; i < 8; i++) begin
                if (ara_req_i.use_vs1 && i < vs1_regs &&
                    (unsigned'(ara_req_i.vs1) + i) < 32) begin
                  pe_req_d.hazard_vs1[
                      write_list_d[ara_req_i.vs1 + i].vid] |=
                      write_list_d[ara_req_i.vs1 + i].valid;
                  raw_hazard_vec[
                      write_list_d[ara_req_i.vs1 + i].vid] |=
                      write_list_d[ara_req_i.vs1 + i].valid;
                  if (write_list_d[ara_req_i.vs1 + i].valid &&
                      (write_list_d[ara_req_i.vs1 + i].wait_complete ||
                       write_list_d[ara_req_i.vs1 + i].group_offset != i[2:0])) begin
                    wait_complete_vec[
                        write_list_d[ara_req_i.vs1 + i].vid] = 1'b1;
                  end
                end
                if (ara_req_i.use_vs2 && i < vs2_regs &&
                    (unsigned'(ara_req_i.vs2) + i) < 32) begin
                  pe_req_d.hazard_vs2[
                      write_list_d[ara_req_i.vs2 + i].vid] |=
                      write_list_d[ara_req_i.vs2 + i].valid;
                  raw_hazard_vec[
                      write_list_d[ara_req_i.vs2 + i].vid] |=
                      write_list_d[ara_req_i.vs2 + i].valid;
                  if (write_list_d[ara_req_i.vs2 + i].valid &&
                      (ara_req_i.op inside {VRGATHER, VRGATHEREI16, VCOMPRESS} ||
                       write_list_d[ara_req_i.vs2 + i].wait_complete ||
                       write_list_d[ara_req_i.vs2 + i].group_offset != i[2:0])) begin
                    wait_complete_vec[
                        write_list_d[ara_req_i.vs2 + i].vid] = 1'b1;
                  end
                end
              end
              if (!ara_req_i.vm) begin
                pe_req_d.hazard_vm[write_list_d[VMASK].vid] |=
                    write_list_d[VMASK].valid;
                raw_hazard_vec[write_list_d[VMASK].vid] |=
                    write_list_d[VMASK].valid;
                if (write_list_d[VMASK].valid &&
                    (write_list_d[VMASK].wait_complete ||
                     write_list_d[VMASK].group_offset != '0)) begin
                  wait_complete_vec[write_list_d[VMASK].vid] = 1'b1;
                end
              end

              // WAR and WAW cover every register written by the destination
              // group. use_vd_op reads the same footprint; the WAW dependency
              // also keeps that old-vd fetch behind an older group writer.
              for (int unsigned i = 0; i < 8; i++) begin
                if (ara_req_i.use_vd && i < vd_regs &&
                    (unsigned'(ara_req_i.vd) + i) < 32) begin
                  automatic logic [NrVInsn-1:0] readers;
                  readers = read_mask_d[ara_req_i.vd + i];
                  pe_req_d.hazard_vs1 |= readers;
                  pe_req_d.hazard_vs2 |= readers;
                  pe_req_d.hazard_vm  |= readers;
                  war_hazard_vec      |= readers;

                  if ((|readers) && ((readers & (readers - 1'b1)) == '0)) begin
                    if (read_list_d[ara_req_i.vd + i].valid &&
                        readers[read_list_d[ara_req_i.vd + i].vid]) begin
                      if (read_list_d[ara_req_i.vd + i].wait_complete ||
                          read_list_d[ara_req_i.vd + i].group_offset != i[2:0]) begin
                        wait_complete_vec[read_list_d[ara_req_i.vd + i].vid] = 1'b1;
                      end
                    end else begin
                      // The newest-reader metadata was overwritten before an
                      // older sole reader finished. Its access progress is no
                      // longer reconstructible, so wait for that reader to retire.
                      wait_complete_vec |= readers;
                    end
                  end
                  pe_req_d.hazard_vd[
                      write_list_d[ara_req_i.vd + i].vid] |=
                      write_list_d[ara_req_i.vd + i].valid;
                  waw_hazard_vec[
                      write_list_d[ara_req_i.vd + i].vid] |=
                      write_list_d[ara_req_i.vd + i].valid;
                  if (write_list_d[ara_req_i.vd + i].valid &&
                      (ara_req_i.op == VCOMPRESS ||
                       write_list_d[ara_req_i.vd + i].wait_complete ||
                       write_list_d[ara_req_i.vd + i].group_offset != i[2:0])) begin
                    wait_complete_vec[
                        write_list_d[ara_req_i.vd + i].vid] = 1'b1;
                  end
                end
              end

              // A result pulse identifies a vid, not an individual source
              // stream. Requiring several independent readers to advance in
              // the same cycle can deadlock after the younger writer has
              // reserved operand queues. Keep that writer at the Ara request
              // boundary until no more than one reader remains; the normal
              // single-reader chaining path then applies.
              multi_reader_war =
                  |(war_hazard_vec & (war_hazard_vec - 1'b1));

              // Result writeback is not a valid proxy for source lifetime:
              // a younger writer can otherwise overwrite a later source word
              // while the older reader is backpressured. Only pure, ordered
              // WAR dependencies use lane-local source-capture release.
              pe_req_d.hazard_source_lifetime =
                  war_hazard_vec & ~raw_hazard_vec & ~waw_hazard_vec &
                  ~wait_complete_vec;
              pe_req_d.hazard_wait_complete = wait_complete_vec;

            `ifdef FOR_VERIFY
            raw_hazard = |raw_hazard_vec;
            war_hazard = |war_hazard_vec;
              waw_hazard = |waw_hazard_vec;
              false_hazard = war_hazard || waw_hazard;
              sequencer_block = (!(|{ara_req_i.use_vs1, ara_req_i.use_vs2, ara_req_i.use_vd_op, !ara_req_i.vm}) &&
                |{pe_req_d.hazard_vs1, pe_req_d.hazard_vs2, pe_req_d.hazard_vm, pe_req_d.hazard_vd} ||
                (pe_req_d.op == VSLIDEUP && |{pe_req_d.hazard_vd, pe_req_d.hazard_vs1, pe_req_d.hazard_vs2}) ||
                (pe_req_d.op == VSLIDEDOWN &&
                 |{pe_req_d.hazard_vd, pe_req_d.hazard_vs1, pe_req_d.hazard_vs2}));
              if ($test$plusargs("ARA_DEBUG_GROUP_HAZARD") &&
                  ara_req_i.verify_arch_insn inside {
                    32'h228de457, 32'h51b0a5d7, 32'h4e0e0c57,
                    32'h6f88aa57, 32'h1f440457, 32'h96834057,
                    32'hb2040a57, 32'haf4ece57, 32'hbc86b257
                  }) begin
                $display("[ARA_GROUP_HAZARD] t=%0t insn=%h op=%0d id=%0d vd=v%0d emul=%0d regs=%0d use_vd=%0b use_vd_op=%0b wait=%b write_v8_11=%0b:%0d_%0b:%0d_%0b:%0d_%0b:%0d raw=%b war=%b waw=%b hazards=%b/%b/%b/%b",
                         $time, ara_req_i.verify_arch_insn, ara_req_i.op,
                         vinsn_id_n, ara_req_i.vd, ara_req_i.emul, vd_regs,
                         ara_req_i.use_vd, ara_req_i.use_vd_op,
                         wait_complete_vec,
                         write_list_d[8].valid, write_list_d[8].vid,
                         write_list_d[9].valid, write_list_d[9].vid,
                         write_list_d[10].valid, write_list_d[10].vid,
                         write_list_d[11].valid, write_list_d[11].vid,
                         raw_hazard_vec, war_hazard_vec, waw_hazard_vec,
                         pe_req_d.hazard_vs1, pe_req_d.hazard_vs2,
                         pe_req_d.hazard_vm, pe_req_d.hazard_vd);
              end
            `endif

            end : group_hazard_check

            /////////////
            //  Issue  //
            /////////////

            // Populate the PE request
            pe_req_d = '{
              id            : vinsn_id_n,
              op            : ara_req_i.op,
              vm            : ara_req_i.vm,
              eew_vmask     : ara_req_i.eew_vmask,
              vfu           : vfu(ara_req_i.op),
              vs1           : ara_req_i.vs1,
              use_vs1       : ara_req_i.use_vs1,
              conversion_vs1: ara_req_i.conversion_vs1,
              eew_vs1       : ara_req_i.eew_vs1,
              old_eew_vs1   : ara_req_i.old_eew_vs1,
              vs2           : ara_req_i.vs2,
              use_vs2       : ara_req_i.use_vs2,
              conversion_vs2: ara_req_i.conversion_vs2,
              eew_vs2       : ara_req_i.eew_vs2,
              old_eew_vs2   : ara_req_i.old_eew_vs2,
              use_vd_op     : ara_req_i.use_vd_op,
              eew_vd_op     : ara_req_i.eew_vd_op,
              scalar_op     : ara_req_i.scalar_op,
              use_scalar_op : ara_req_i.use_scalar_op,
              swap_vs2_vd_op: ara_req_i.swap_vs2_vd_op,
              stride        : ara_req_i.stride,
              is_stride_np2 : ara_req_i.is_stride_np2,
              vd            : ara_req_i.vd,
              use_vd        : ara_req_i.use_vd,
              emul          : ara_req_i.emul,
              fp_rm         : ara_req_i.fp_rm,
              wide_fp_imm   : ara_req_i.wide_fp_imm,
              cvt_resize    : ara_req_i.cvt_resize,
              overlap_capture: ara_req_i.overlap_capture,
              overlap_use_snapshot: ara_req_i.overlap_use_snapshot,
              overlap_snapshot_word: ara_req_i.overlap_snapshot_word,
              source_snapshot_capture: ara_req_i.source_snapshot_capture,
              source_snapshot_replay_vs1: ara_req_i.source_snapshot_replay_vs1,
              source_snapshot_replay_vs2: ara_req_i.source_snapshot_replay_vs2,
              scale_vl      : ara_req_i.scale_vl,
              start_lane    : start_lane,
              end_lane      : end_lane,
              vl            : ara_req_i.vl,
              vstart        : ara_req_i.vstart,
              vtype         : ara_req_i.vtype,
              akv_refill    : ara_req_i.akv_refill,
              hazard_vd     : pe_req_d.hazard_vd,
              hazard_vm     : pe_req_d.hazard_vm,
              hazard_vs1    : pe_req_d.hazard_vs1,
              hazard_vs2    : pe_req_d.hazard_vs2,
              hazard_source_lifetime: pe_req_d.hazard_source_lifetime,
              hazard_wait_complete: pe_req_d.hazard_wait_complete,
              default       : '0
            };

            // Populate the global hazard table
            global_hazard_table_d[vinsn_id_n] = pe_req_d.hazard_vd  | pe_req_d.hazard_vm |
                                                pe_req_d.hazard_vs1 | pe_req_d.hazard_vs2;

            // We only issue instructions that take no operands if they have no hazards.
            // Moreover, SLIDE instructions cannot be always chained
            // ToDo: optimize the case for vslide1down, vslide1up (wait 2 cycles, then chain)
            if (multi_reader_war ||
                (!(|{ara_req_i.use_vs1, ara_req_i.use_vs2, ara_req_i.use_vd_op, !ara_req_i.vm}) &&
                 |{pe_req_d.hazard_vs1, pe_req_d.hazard_vs2,
                   pe_req_d.hazard_vm, pe_req_d.hazard_vd}) ||
                (pe_req_d.op == VSLIDEUP && |{pe_req_d.hazard_vd, pe_req_d.hazard_vs1, pe_req_d.hazard_vs2}) ||
                (pe_req_d.op == VSLIDEDOWN &&
                 |{pe_req_d.hazard_vd, pe_req_d.hazard_vs1, pe_req_d.hazard_vs2}))
            begin
              ara_req_ready_o = 1'b0;
              pe_req_valid_d  = 1'b0;
            end else begin
              // Acknowledge instruction
              ara_req_ready_o = 1'b1;

              // Remember that the vector instruction is running
              unique case (vfu(ara_req_i.op))
                VFU_LoadUnit : pe_vinsn_running_d[NrLanes + OffsetLoad][vinsn_id_n]  = 1'b1;
                VFU_StoreUnit: pe_vinsn_running_d[NrLanes + OffsetStore][vinsn_id_n] = 1'b1;
                VFU_SlideUnit: pe_vinsn_running_d[NrLanes + OffsetSlide][vinsn_id_n] = 1'b1;
                VFU_MaskUnit : pe_vinsn_running_d[NrLanes + OffsetMask][vinsn_id_n]  = 1'b1;
                VFU_None     : ;
                default: for (int l = 0; l < NrLanes; l++)
                    // Instruction is running on the lanes
                    pe_vinsn_running_d[l][vinsn_id_n] = 1'b1;
              endcase

              // Reductions execute their lane-local ALU/MFPU phase and their
              // cross-lane phase in SLDU under the same vid. Keep the vid live
              // until both sides have acknowledged completion.
              if (reduction_result(ara_req_i.op))
                pe_vinsn_running_d[NrLanes + OffsetSlide][vinsn_id_n] = 1'b1;

              // Masked vector instructions also run on the mask unit
              pe_vinsn_running_d[NrLanes + OffsetMask][vinsn_id_n] |= !ara_req_i.vm;

              // Some instructions need to wait for an acknowledgment
              // before being committed with Ariane
              if (is_load(ara_req_i.op) || is_store(ara_req_i.op) ||
                  (!ara_req_i.use_vd && !ara_req_i.overlap_capture)) begin
                ara_req_ready_o = 1'b0;
                state_d         = WAIT;
                if (is_load(ara_req_i.op) || is_store(ara_req_i.op))
                  addrgen_acked_d = 1'b0;
                if (is_load(ara_req_i.op) || is_store(ara_req_i.op)) begin
                  addrgen_exception_d = '0;
                  addrgen_exception_vstart_d = '0;
                  addrgen_fof_exception_d = 1'b0;
                  memory_lane_accepted_d = no_src_vrf(pe_req_d) ? '1 : '0;
                  memory_mask_accepted_d = pe_req_d.vm;
                end
              end

              // Issue the instruction
              pe_req_valid_d = 1'b1;
              `ifdef FOR_VERIFY
              // Scalar-return operations use VFU_None and do not allocate a
              // backend vid. A masked request additionally occupies MASKU and
              // therefore does have a normal vid lifecycle.
              verify_vinsn_alloc = (vfu(ara_req_i.op) != VFU_None) || !ara_req_i.vm;
              `endif

              begin : group_access_update
                automatic int unsigned vd_regs = destination_register_count(ara_req_i);
                automatic int unsigned vs1_regs =
                    source_register_count(ara_req_i, ara_req_i.eew_vs1, 1'b1);
                automatic int unsigned vs2_regs =
                    source_register_count(ara_req_i, ara_req_i.eew_vs2, 1'b0);
                automatic logic ordered_access_wait_complete =
                    ara_req_i.op inside {VSLIDEUP, VSLIDEDOWN};
                // VCOMPRESS emits a data-dependent number of destination
                // words. It cannot participate in result-paced WAW chaining
                // with either an older or a younger writer.
                automatic logic destination_wait_complete =
                    ordered_access_wait_complete ||
                    ara_req_i.op inside {VCOMPRESS, VQBEXEC};
                // Gather can reread the same vs2 element, while compress consumes
                // selected vs2 elements at a rate unrelated to destination writes.
                // Their source lifetime therefore ends at instruction completion,
                // not at the normal result-paced chaining point.
                automatic logic vs2_access_wait_complete =
                    ordered_access_wait_complete ||
                    ara_req_i.op inside {VRGATHER, VRGATHEREI16, VCOMPRESS};

                // Unmasked scalar-return requests use VFU_None and hold the
                // sequencer in WAIT until their source has been consumed. They
                // do not allocate a vid, so recording them in the access tables
                // would create an entry that has no retirement event.
                if (vfu(ara_req_i.op) != VFU_None || !ara_req_i.vm) begin
                  for (int unsigned i = 0; i < 8; i++) begin
                    if (ara_req_i.use_vd && i < vd_regs &&
                        (unsigned'(ara_req_i.vd) + i) < 32) begin
                      write_list_d[ara_req_i.vd + i] =
                          '{vid: vinsn_id_n, group_offset: i[2:0],
                            wait_complete: destination_wait_complete, valid: 1'b1};
                    end
                    if (ara_req_i.use_vs1 && i < vs1_regs &&
                        (unsigned'(ara_req_i.vs1) + i) < 32) begin
                      read_list_d[ara_req_i.vs1 + i] =
                          '{vid: vinsn_id_n, group_offset: i[2:0],
                            wait_complete: ordered_access_wait_complete, valid: 1'b1};
                      read_mask_d[ara_req_i.vs1 + i][vinsn_id_n] = 1'b1;
                    end
                    if (ara_req_i.use_vs2 && i < vs2_regs &&
                        (unsigned'(ara_req_i.vs2) + i) < 32) begin
                      read_list_d[ara_req_i.vs2 + i] =
                          '{vid: vinsn_id_n, group_offset: i[2:0],
                            wait_complete: vs2_access_wait_complete, valid: 1'b1};
                      read_mask_d[ara_req_i.vs2 + i][vinsn_id_n] = 1'b1;
                    end
                    if (ara_req_i.use_vd_op && i < vd_regs &&
                        (unsigned'(ara_req_i.vd) + i) < 32) begin
                      read_list_d[ara_req_i.vd + i] =
                          '{vid: vinsn_id_n, group_offset: i[2:0],
                            wait_complete: ordered_access_wait_complete, valid: 1'b1};
                      read_mask_d[ara_req_i.vd + i][vinsn_id_n] = 1'b1;
                    end
                  end
                  if (!ara_req_i.vm) begin
                    read_list_d[VMASK] =
                        '{vid: vinsn_id_n, group_offset: '0,
                          wait_complete: ara_req_i.op inside {VSLIDEUP, VSLIDEDOWN},
                          valid: 1'b1};
                    read_mask_d[VMASK][vinsn_id_n] = 1'b1;
                  end
                end
              end : group_access_update
            end
          end else ara_req_ready_o = 1'b0; // Wait until the PEs are ready
        end
      end

      WAIT: begin
        // Wait until we got an answer from lane 0
        ara_req_ready_o = 1'b0;

        // Maintain output
        pe_req_d       = pe_req_o;
        pe_req_valid_d = pe_req_valid_o;

        // The request is broadcast to AddrGen, the lane operand requesters,
        // and MASKU, which may accept it in different cycles. Remember each
        // operand-side handshake instead of treating a later ready level as
        // evidence that the request was accepted in that cycle.
        if (is_load(pe_req_o.op) || is_store(pe_req_o.op)) begin
          for (int unsigned lane = 0; lane < NrLanes; lane++) begin
            memory_lane_accepted_d[lane] |=
                pe_req_broadcast_valid && pe_req_ready_i[lane];
          end
          memory_mask_accepted_d |= pe_req_o.vm ||
              (pe_req_broadcast_valid && pe_req_ready_i[NrLanes+OffsetMask]);
        end

        if (addrgen_ack_i) begin
          addrgen_acked_d = 1'b1;
          addrgen_exception_d = addrgen_exception_i;
          addrgen_exception_vstart_d = addrgen_exception_vstart_i;
          addrgen_fof_exception_d = addrgen_fof_exception_i;
        end

        // Stop requesting if the operations have been completely acknowledged:
        // 1) Scalar moves / vcpop / vfirst only need acknowledgement from
        //    their operand suppliers.  MASKU requests are broadcast atomically
        //    with the lanes, so raw lane readiness alone is not an acceptance
        //    when MASKU is still draining an older context.
        if (pe_req_o.op inside {VMVXS, VFMVFS, VCPOP, VFIRST} &&
            &operand_requester_ready && mask_requester_ready)
          pe_req_valid_d = 1'b0;
        // 2) Unmasked non-indexed loads only need ack from the addrgen
        if (no_src_vrf(pe_req_o) && addrgen_ack_i)
          pe_req_valid_d = 1'b0;
        // 3) In case of an exception on this burst, kill the request.
        //    Exceptions on this burst mean that all the valid sources have been fetched from VRF already.
        //    Don't immediately kill when detecting the exception in the addrgen, as previous valid bursts
        //    can still need operands to be fetched from the VRF.
        if (lsu_current_burst_exception_q) begin
          pe_req_valid_d = 1'b0;
          memory_lane_accepted_d = '1;
          memory_mask_accepted_d = 1'b1;
        end
        // 4) In the other cases, we need an ack from both addrgen and lanes, so keep up the req

        // Wait for the address translation
        if ((is_load(pe_req_o.op) || is_store(pe_req_o.op)) &&
            (addrgen_acked_q || addrgen_ack_i) &&
            (&memory_lane_accepted_d) && memory_mask_accepted_d) begin
          // The address generator acknowledges indexed operations only after
          // consuming their lane operands.  Withdraw the broadcast request in
          // the same cycle so it cannot be accepted again after AddrGen
          // returns to IDLE.
          pe_req_valid_d       = 1'b0;
          state_d             = IDLE;
          ara_req_ready_o     = 1'b1;
          ara_resp_valid_o    = 1'b1;
          ara_resp_o.exception = addrgen_ack_i
                               ? addrgen_exception_i : addrgen_exception_q;
          ara_resp_o.exception_vstart = addrgen_ack_i
                                      ? addrgen_exception_vstart_i
                                      : addrgen_exception_vstart_q;
          ara_resp_o.fof_exception = addrgen_ack_i
                                   ? addrgen_fof_exception_i
                                   : addrgen_fof_exception_q;
          if (pe_req_o.op == VQBEXEC) begin
            ara_resp_o.fflags = qbs_fflags_i;
            ara_resp_o.fflags_valid = qbs_fflags_valid_i;
          end
          addrgen_acked_d = 1'b0;
          memory_lane_accepted_d = '0;
          memory_mask_accepted_d = 1'b0;
        end

        // Wait for the scalar result
        if (pe_req_o.op inside {VMVXS, VFMVFS, VCPOP, VFIRST} &&
            pe_scalar_resp_valid_i) begin
          // Acknowledge the request
          state_d                = IDLE;
          ara_req_ready_o        = 1'b1;
          ara_resp_valid_o       = 1'b1;
          ara_resp_o.resp        = pe_scalar_resp_i;
          pe_scalar_resp_ready_o = pe_scalar_resp_valid_i &
                                   ~(pending_mask_insn_q || running_mask_insn_q);
          addrgen_acked_d = 1'b0;
        end
      end
    endcase

    // Update the global hazard table
    for (int id = 0; id < NrVInsn; id++) global_hazard_table_d[id] &= vinsn_running_d;
  end : p_sequencer

  always_ff @(posedge clk_i or negedge rst_ni) begin: p_sequencer_ff
    if (!rst_ni) begin
      state_q <= IDLE;
      addrgen_acked_q <= 1'b0;
      addrgen_exception_q <= '0;
      addrgen_exception_vstart_q <= '0;
      addrgen_fof_exception_q <= 1'b0;
      memory_lane_accepted_q <= '0;
      memory_mask_accepted_q <= 1'b0;

      read_list_q  <= '0;
      read_mask_q  <= '0;
      write_list_q <= '0;

      pe_req_o       <= '0;
      pe_req_valid_o <= 1'b0;

      ara_req_token_q <= 1'b1;
      gold_ticket_q   <= 1'b0;

      global_hazard_table_o <= '0;

      pending_mask_insn_q <= 1'b0;
      running_mask_insn_q <= 1'b0;
    end else begin
      state_q <= state_d;
      addrgen_acked_q <= addrgen_acked_d;
      addrgen_exception_q <= addrgen_exception_d;
      addrgen_exception_vstart_q <= addrgen_exception_vstart_d;
      addrgen_fof_exception_q <= addrgen_fof_exception_d;
      memory_lane_accepted_q <= memory_lane_accepted_d;
      memory_mask_accepted_q <= memory_mask_accepted_d;

      read_list_q  <= read_list_d;
      read_mask_q  <= read_mask_d;
      write_list_q <= write_list_d;

      pe_req_o       <= pe_req_d;
      pe_req_valid_o <= pe_req_valid_d;

      ara_req_token_q <= ara_req_token_d;
      gold_ticket_q   <= gold_ticket_d;

      global_hazard_table_o <= global_hazard_table_d;

      pending_mask_insn_q <= pending_mask_insn_d;
      running_mask_insn_q <= running_mask_insn_d;
    end
  end

`ifdef FOR_VERIFY
  longint unsigned verify_stall_cycle_q;

`ifndef SYNTHESIS
  always_ff @(posedge clk_i) begin
    if (rst_ni) begin
      assert (vinsn_retired_q == (vinsn_running_prev_q & ~vinsn_running_q))
        else $fatal(1, "Vector-instruction retirement pulse is cycle-misaligned");
      for (int unsigned v = 0; v < 32; v++) begin
        assert (!(read_list_q[v].valid &&
                  !vinsn_running_q[read_list_q[v].vid] &&
                  !vinsn_retired_q[read_list_q[v].vid]))
          else $fatal(1, "Stale vector read-list entry missed its retirement pulse");
        assert (!(write_list_q[v].valid &&
                  !vinsn_running_q[write_list_q[v].vid] &&
                  !vinsn_retired_q[write_list_q[v].vid]))
          else $fatal(1, "Stale vector write-list entry missed its retirement pulse");
        assert ((read_mask_q[v] & ~(vinsn_running_q | vinsn_retired_q)) == '0)
          else $fatal(1, "Stale vector read-mask entry missed its retirement pulse");
      end
    end
  end
`endif

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      verify_stall_cycle_q <= '0;
    end else begin
      verify_stall_cycle_q <= verify_stall_cycle_q + 1'b1;
      if ($test$plusargs("ARA_DEBUG_SEQ_STALL") &&
          verify_stall_cycle_q != 0 && verify_stall_cycle_q % 1000 == 0) begin
        $display("[ARA_SEQ_STALL] t=%0t cyc=%0d state=%0d ara=%0b/%0b op=%0d insn=%h pe=%0b op=%0d id=%0d ready=%b lane_ready=%b running=%b pe_running=%h desync=%0b:%b full=%0b issue=%b",
                 $time, verify_stall_cycle_q, state_q,
                 ara_req_valid_i, ara_req_ready_o, ara_req_i.op,
                 ara_req_i.verify_arch_insn, pe_req_valid_o, pe_req_o.op,
                 pe_req_o.id, pe_req_ready_i, operand_requester_ready,
                 vinsn_running_q, pe_vinsn_running_q, stall_lanes_desynch,
                 stall_lanes_desynch_vec, vinsn_running_full,
                 vinsn_queue_issue);
      end
      if ($test$plusargs("ARA_DEBUG_MULTI_READER_WAR") &&
          verify_stall_cycle_q > 65000 && verify_stall_cycle_q % 50 == 0) begin
        $display("[ARA_MULTI_READER_SEQ] t=%0t cyc=%0d running=%b pe_running=%h global4=%b global5=%b global6=%b read_v0=%b read_v8=%b read_v16=%b",
                 $time, verify_stall_cycle_q, vinsn_running_q,
                 pe_vinsn_running_q, global_hazard_table_o[4],
                 global_hazard_table_o[5], global_hazard_table_o[6],
                 read_mask_q[0], read_mask_q[8], read_mask_q[16]);
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VMUL402")) begin
      if (accepted_insn && ara_req_i.verify_arch_insn == 32'h96c6e457)
        $display("[ARA_VMUL402_SEQ_ACCEPT] t=%0t state=%0d ready=%0b op=%0d use_scalar=%0b scalar=%h token=%0b",
                 $time, state_q, ara_req_ready_o, ara_req_i.op,
                 ara_req_i.use_scalar_op, ara_req_i.scalar_op,
                 ara_req_i.token);
      if (pe_req_valid_o && pe_req_o.op == VMUL && pe_req_o.vd == 5'd8 &&
          pe_req_o.vs2 == 5'd12 && pe_req_o.vl == 11 &&
          pe_req_o.vtype.vsew == EW64)
        $display("[ARA_VMUL402_SEQ_ISSUE] t=%0t ready=%b id=%0d use_scalar=%0b scalar=%h hazards=%b/%b/%b/%b",
                 $time, pe_req_ready_i, pe_req_o.id,
                 pe_req_o.use_scalar_op, pe_req_o.scalar_op,
                 pe_req_o.hazard_vs1, pe_req_o.hazard_vs2,
                 pe_req_o.hazard_vm, pe_req_o.hazard_vd);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VFMVFS416") &&
        ((ara_req_valid_i && ara_req_i.op == VFMVFS) ||
         (pe_req_valid_o && pe_req_o.op == VFMVFS) ||
         pe_scalar_resp_valid_i || pe_scalar_resp_ready_o ||
         ara_resp_valid_o)) begin
      $display("[ARA_VFMVFS416_SEQ] t=%0t state=%0d ara=%0b/%0b op=%0d insn=%h pe=%0b op=%0d id=%0d vs2=%0d scalar=%0b/%0b val=%h resp=%0b val=%h pending=%0b running=%0b mask_done=%b",
               $time, state_q, ara_req_valid_i, ara_req_ready_o, ara_req_i.op,
               ara_req_i.verify_arch_insn, pe_req_valid_o, pe_req_o.op,
               pe_req_o.id, pe_req_o.vs2, pe_scalar_resp_valid_i,
               pe_scalar_resp_ready_o, pe_scalar_resp_i, ara_resp_valid_o,
               ara_resp_o.resp, pending_mask_insn_q, running_mask_insn_q,
               pe_resp_i[NrLanes+OffsetMask].vinsn_done);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_SCALAR_MASK") &&
        ((ara_req_valid_i && ara_req_i.op inside {VCPOP, VFIRST}) ||
         pe_scalar_resp_valid_i || pe_scalar_resp_ready_o ||
         ara_resp_valid_o)) begin
      $display("[ARA_SEQ_SCALAR] t=%0t state=%0d req=%0b/%0b op=%0d pe_op=%0d pe_valid=%0b scalar=%0b/%0b val=%h resp=%0b pending=%0b running=%0b mask_done=%b",
               $time, state_q, ara_req_valid_i, ara_req_ready_o, ara_req_i.op,
               pe_req_o.op, pe_req_valid_o, pe_scalar_resp_valid_i,
               pe_scalar_resp_ready_o, pe_scalar_resp_i, ara_resp_valid_o,
               pending_mask_insn_q, running_mask_insn_q,
               pe_resp_i[NrLanes+OffsetMask].vinsn_done);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VMSOF_STALL") &&
        ((ara_req_valid_i && ara_req_i.verify_arch_insn == 32'h50712b57) ||
         (pe_req_valid_o && pe_req_o.op == VMSOF &&
          pe_req_o.vd == 5'd22 && pe_req_o.vs2 == 5'd7))) begin
      $display("[ARA_VMSOF_STALL] t=%0t state=%0d ara=%0b/%0b accepted=%0b op=%0d pe=%0b ready=%b lane_ready=%b pending=%0b running=%0b id=%0d hazards=%b/%b/%b/%b wait=%b global=%b",
               $time, state_q, ara_req_valid_i, ara_req_ready_o, accepted_insn,
               ara_req_i.op, pe_req_valid_o, pe_req_ready_i,
               operand_requester_ready, pending_mask_insn_q,
               running_mask_insn_q, pe_req_o.id, pe_req_o.hazard_vs1,
               pe_req_o.hazard_vs2, pe_req_o.hazard_vm,
               pe_req_o.hazard_vd, pe_req_o.hazard_wait_complete,
               global_hazard_table_o);
    end
  end

`endif

  /////////////////
  // Scalar Move //
  /////////////////

  // This signal detects only instructions that produce
  // a mask vector, to reduce latency of scalar moves
  // if a masked vector instruction is ongoing

  // This works only if MASKU insn queue has width == 1
  always_comb begin
    pending_mask_insn_d = pending_mask_insn_q;
    running_mask_insn_d = running_mask_insn_q;

    if (|pe_resp_i[NrLanes+OffsetMask].vinsn_done)
      running_mask_insn_d = 1'b0;

    if (pe_req_valid_o && &operand_requester_ready && pe_req_o.vfu == VFU_MaskUnit) begin
      pending_mask_insn_d = 1'b0;
      running_mask_insn_d = 1'b1;
    end

    // Reserve the untagged MaskB lane-to-MASKU path as soon as a mask-result
    // instruction enters the sequencer.  Waiting until lane issue leaves a
    // window in which a younger scalar extract can consume lane 0's old-vd
    // operand while the mask instruction is still queued.
    if (accepted_insn && vfu(ara_req_i.op) == VFU_MaskUnit)
      pending_mask_insn_d = 1'b1;
  end

  //////////////
  // Counters //
  //////////////

  // Instructions are registered upon entry by the FUs insn queue counters.

  // ALU and MFPU has different signal sources
  assign insn_queue_done[VFU_Alu]       = alu_vinsn_done_i;
  assign insn_queue_done[VFU_MFpu]      = mfpu_vinsn_done_i;
  assign insn_queue_done[VFU_LoadUnit]  = |pe_resp_i[NrLanes+OffsetLoad].vinsn_done;
  assign insn_queue_done[VFU_StoreUnit] = |pe_resp_i[NrLanes+OffsetStore].vinsn_done;
  assign insn_queue_done[VFU_MaskUnit]  = |pe_resp_i[NrLanes+OffsetMask].vinsn_done;
  assign insn_queue_done[VFU_SlideUnit] = |pe_resp_i[NrLanes+OffsetSlide].vinsn_done;
  // Dummy counter, just for compatibility
  assign insn_queue_done[VFU_None]      = insn_queue_cnt_up[VFU_None];

  // Register the incoming instruction if it is valid
  assign accepted_insn = ara_req_valid_i & (ara_req_token_q != ara_req_i.token);

  // The new accepted instruction will not be immediately issued
  assign accepted_insn_stalled = accepted_insn & ~ara_req_ready_o;

  // Masked instructions do use the mask unit as well
  always_comb begin
    target_vfus_vec                = target_vfus(ara_req_i.op);
    target_vfus_vec[VFU_MaskUnit] |= ~ara_req_i.vm;
  end

  // One counter per VFU
  for (genvar i = 0; i < NrVFUs; i++) begin : gen_seq_fu_cnt
    // The width can be optimized for each counter
    localparam CNT_WIDTH = idx_width(MaxVInsnQueueDepth + 1);

    counter #(
        .WIDTH           (CNT_WIDTH),
        .STICKY_OVERFLOW (0)
    ) i_insn_queue_cnt (
        .clk_i           (clk_i                 ),
        .rst_ni          (rst_ni                ),
        .clear_i         (1'b0                  ),
        .en_i            (insn_queue_cnt_en[i]  ),
        .load_i          (1'b0                  ),
        .down_i          (insn_queue_cnt_down[i]),
        .d_i             ('0                    ),
        .q_o             (insn_queue_cnt_q[i]   ),
        .overflow_o      (/* Unconnected */     )
    );

    // Each PE is ready only if it can accept a new instruction in the queue
    assign vinsn_queue_ready[i] = insn_queue_cnt_q[i] < InsnQueueDepth[i];
    // Count up on the right counter
    assign insn_queue_cnt_up[i] = accepted_insn & target_vfus_vec[i];
    // Count down if an instruction was consumed by the PE
    assign insn_queue_cnt_down[i] = insn_queue_done[i];
    // Don't count if one instruction is issued and one is consumed
    assign insn_queue_cnt_en[i] = insn_queue_cnt_up[i] ^ insn_queue_cnt_down[i];
    // Assign the gold ticket when:
    //   1) The new instruction finds the target cnt already full
    //   2) The new instruction is stalled and the target cnt is pre-filled
    // In both cases the instruction is stalled, and it should pass as soon as
    // insn_queue_cnt_q[i] == InsnQueueDepth[i] since it was already counted
    assign gold_ticket_d[i] = accepted_insn_stalled
                            ? (insn_queue_cnt_q[i] >= (InsnQueueDepth[i] - 1)) & target_vfus_vec[i]
                            : gold_ticket_q[i];
    // The instructions with a gold ticket can pass the checks even if the cnt is full,
    // but not when (insn_queue_cnt_q[i] == InsnQueueDepth[i] + 1)
	// Moreover, just arrived instructions cannot use the golden ticket of a previous instruction
    assign priority_pass[i] = gold_ticket_q[i] & (insn_queue_cnt_q[i] == InsnQueueDepth[i]) &
      (ara_req_token_q == ara_req_i.token);
    // The instruction queue [i] allows us to issue the instruction
    // If the insn is not targeting the PE [i], PE [i] cannot stall the instruction issue.
    // Each targeted PE must be ready (either with cnt < MAX or with a priority pass)
    assign vinsn_queue_issue[i] = ~target_vfus_vec[i] | (vinsn_queue_ready[i] | priority_pass[i]);
  end

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_SEGMENT") &&
        ara_req_i.nf != 3'b000 && ara_req_valid_i) begin
      $display("[ARA_SEGMENT_ACCEPT] t=%0t valid=%0b ready=%0b accepted=%0b arch=%0d insn=%h vd=v%0d emul=%0d vl=%0d vstart=%0d token=%0b/%0b",
               $time, ara_req_valid_i, ara_req_ready_o, accepted_insn,
               ara_req_i.verify_arch_seq, ara_req_i.verify_arch_insn,
               ara_req_i.vd, ara_req_i.emul, ara_req_i.vl,
               ara_req_i.vstart, ara_req_token_q, ara_req_i.token);
    end
  end
`endif

endmodule : ara_sequencer
