// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// This is Ara's slide unit. It is responsible for running the vector slide (up/down)
// instructions, which need access to the whole Vector Register File.

module sldu import ara_pkg::*; import rvv_pkg::*; #(
    parameter  int  unsigned NrLanes   = 0,
    parameter  int  unsigned VLEN      = 0,
    parameter  type          vaddr_t   = logic, // Type used to address vector register file elements,
    parameter  type          pe_req_t  = logic,
    parameter  type          pe_resp_t = logic,
    // Dependant parameters. DO NOT CHANGE!
    localparam int  unsigned DataWidth = $bits(elen_t), // Width of the lane datapath
    localparam int  unsigned StrbWidth = DataWidth/8,
    localparam type          strb_t    = logic [StrbWidth-1:0], // Byte-strobe type
    localparam type          vlen_t    = logic[$clog2(VLEN+1)-1:0]
  ) (
    input  logic                   clk_i,
    input  logic                   rst_ni,
    // Interface with the main sequencer
    input  pe_req_t                pe_req_i,
    input  logic                   pe_req_valid_i,
    input  logic     [NrVInsn-1:0] pe_vinsn_running_i,
    output logic                   pe_req_ready_o,
    output pe_resp_t               pe_resp_o,
    output logic                   idle_o,
    input  logic                   maintenance_drain_i,
    // Interface with the lanes
    input  elen_t    [NrLanes-1:0] sldu_operand_i,
    input  logic     [NrLanes-1:0] sldu_operand_valid_i,
    input  logic     [NrLanes-1:0] sldu_operand_reduction_i,
    output logic     [NrLanes-1:0] sldu_operand_ready_o,
    output logic     [NrLanes-1:0] sldu_result_req_o,
    output vid_t     [NrLanes-1:0] sldu_result_id_o,
    output vaddr_t   [NrLanes-1:0] sldu_result_addr_o,
    output elen_t    [NrLanes-1:0] sldu_result_wdata_o,
    output strb_t    [NrLanes-1:0] sldu_result_be_o,
    input  logic     [NrLanes-1:0] sldu_result_gnt_i,
    input  logic     [NrLanes-1:0] sldu_result_final_gnt_i,
    // Support for reductions
    output sldu_mux_e              sldu_mux_sel_o,
    output logic     [NrLanes-1:0] sldu_red_valid_o,
    // Interface with the Mask Unit
    input  strb_t    [NrLanes-1:0] mask_i,
    input  logic     [NrLanes-1:0] mask_valid_i,
    output logic                   mask_ready_o
  );

  `include "common_cells/registers.svh"

  import cf_math_pkg::idx_width;

  function automatic elen_t saturating_byte_offset(
    elen_t element_offset, rvv_pkg::vew_e eew
  );
    automatic elen_t max_offset = '1;
    if (element_offset > (max_offset >> unsigned'(eew)))
      saturating_byte_offset = max_offset;
    else
      saturating_byte_offset = element_offset << unsigned'(eew);
  endfunction : saturating_byte_offset

  ////////////////////////////////
  //  Vector instruction queue  //
  ////////////////////////////////

  // We store a certain number of in-flight vector instructions
  localparam VInsnQueueDepth = SlduInsnQueueDepth;

  struct packed {
    pe_req_t [VInsnQueueDepth-1:0] vinsn;

    // Each instruction can be in one of the three execution phases.
    // - Being accepted (i.e., it is being stored for future execution in this
    //   vector functional unit).
    // - Being issued (i.e., its micro-operations are currently being issued
    //   to the corresponding functional units).
    // - Being committed (i.e., its results are being written to the vector
    //   register file).
    // We need pointers to index which instruction is at each execution phase
    // between the VInsnQueueDepth instructions in memory.
    logic [idx_width(VInsnQueueDepth)-1:0] accept_pnt;
    logic [idx_width(VInsnQueueDepth)-1:0] issue_pnt;
    logic [idx_width(VInsnQueueDepth)-1:0] commit_pnt;

    // We also need to count how many instructions are queueing to be
    // issued/committed, to avoid accepting more instructions than
    // we can handle.
    logic [idx_width(VInsnQueueDepth):0] issue_cnt;
    logic [idx_width(VInsnQueueDepth):0] commit_cnt;
  } vinsn_queue_d, vinsn_queue_q;

  pe_req_t vinsn_issue_q;
  logic vinsn_issue_valid_q;
  // Is the vector instruction queue full?
  logic vinsn_queue_full;
  assign vinsn_queue_full = (vinsn_queue_q.commit_cnt == VInsnQueueDepth);

  // Do we have a vector instruction ready to be issued?
  `FF(vinsn_issue_q, vinsn_queue_d.vinsn[vinsn_queue_d.issue_pnt], '0)
  `FF(vinsn_issue_valid_q, vinsn_queue_d.issue_cnt != '0, 1'b0)

  // Do we have a vector instruction with results being committed?
  pe_req_t vinsn_commit;
  logic    vinsn_commit_valid;
  assign vinsn_commit       = vinsn_queue_q.vinsn[vinsn_queue_q.commit_pnt];
  assign vinsn_commit_valid = (vinsn_queue_q.commit_cnt != '0);

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      vinsn_queue_q <= '0;
    end else begin
      vinsn_queue_q <= vinsn_queue_d;
    end
  end

  /////////////////////
  //  Result queues  //
  /////////////////////

  localparam int unsigned ResultQueueDepth = 2;

  // There is a result queue per lane, holding the results that were not
  // yet accepted by the corresponding lane.
  typedef struct packed {
    vid_t id;
    vaddr_t addr;
    elen_t wdata;
    strb_t be;
  } payload_t;

  // Result queue
  payload_t [ResultQueueDepth-1:0][NrLanes-1:0] result_queue_d, result_queue_q;
  logic     [ResultQueueDepth-1:0][NrLanes-1:0] result_queue_valid_d, result_queue_valid_q;
  vlen_t    [ResultQueueDepth-1:0]               result_queue_bytes_d,
                                                       result_queue_bytes_q;
  // We need two pointers in the result queue. One pointer to
  // indicate with `payload_t` we are currently writing into (write_pnt),
  // and one pointer to indicate which `payload_t` we are currently
  // reading from and writing into the lanes (read_pnt).
  logic     [idx_width(ResultQueueDepth)-1:0]   result_queue_write_pnt_d, result_queue_write_pnt_q;
  logic     [idx_width(ResultQueueDepth)-1:0]   result_queue_read_pnt_d, result_queue_read_pnt_q;
  // We need to count how many valid elements are there in this result queue.
  logic     [idx_width(ResultQueueDepth):0]     result_queue_cnt_d, result_queue_cnt_q;
  // Vector to register the final grants from the operand requesters, which indicate
  // that the result was actually written in the VRF (while the normal grant just says
  // that the result was accepted by the operand requester stage
  logic     [NrLanes-1:0]                       result_final_gnt_d, result_final_gnt_q;

  // Is the result queue full?
  logic result_queue_full;
  assign result_queue_full = (result_queue_cnt_q == ResultQueueDepth);
  // Is the result queue empty?
  logic result_queue_empty;
  assign result_queue_empty = (result_queue_cnt_q == '0);

  always_ff @(posedge clk_i or negedge rst_ni) begin: p_result_queue_ff
    if (!rst_ni) begin
      result_queue_q           <= '0;
      result_queue_valid_q     <= '0;
      result_queue_bytes_q     <= '0;
      result_queue_write_pnt_q <= '0;
      result_queue_read_pnt_q  <= '0;
      result_queue_cnt_q       <= '0;
    end else begin
      result_queue_q           <= result_queue_d;
      result_queue_valid_q     <= result_queue_valid_d;
      result_queue_bytes_q     <= result_queue_bytes_d;
      result_queue_write_pnt_q <= result_queue_write_pnt_d;
      result_queue_read_pnt_q  <= result_queue_read_pnt_d;
      result_queue_cnt_q       <= result_queue_cnt_d;
    end
  end

  ////////////////////////////////
  //  Spill-reg from the lanes  //
  ////////////////////////////////

  typedef struct packed {
    logic  reduction;
    elen_t data;
  } sldu_operand_t;

  elen_t         [NrLanes-1:0] sldu_operand;
  sldu_operand_t [NrLanes-1:0] sldu_operand_input, sldu_operand_payload;
  logic          [NrLanes-1:0] sldu_operand_valid;
  logic          [NrLanes-1:0] sldu_operand_ready;
  logic          [NrLanes-1:0] reduction_stale_flush;
  logic                        reduction_context_start;

  // One aggregate VRF word is sufficient to preserve the only physical word
  // that can straddle the active/tail boundary of an unmasked widening result.
  elen_t [NrLanes-1:0] overlap_snapshot_d, overlap_snapshot_q;
  logic overlap_snapshot_valid_d, overlap_snapshot_valid_q;

  // Don't handshake if the operands target the addrgen.
  logic [NrLanes-1:0]  sldu_operand_ready_q;

  localparam int unsigned NP2_RESULT_PNT = 1;

  // NP2 slides decompose the offset into power-of-two permutations. Keep the
  // intermediate aggregate atomic: feeding it back through independent lane
  // spill registers can mix it with prefetched words from the external stream.
  elen_t [NrLanes-1:0] np2_data_d, np2_data_q;
  logic                np2_data_valid_d, np2_data_valid_q;

  // There are multiple transmitters (TX) (OpQueue, ALU, FPU, SLDU-NP2) and receivers (RX) (SLDU, ADDRGEN).
  // Hypotheses:
  // - When valid is asserted on the RX, data cannot change anymore until the handshake happens.
  // - When valid is received by RX, then DATA is targeting that RX only.
  // Data and handshakes signals are controlled upstream (TX side) so that this Hypotheses hold.

  for (genvar l = 0; l < NrLanes; l++) begin
    assign sldu_operand_input[l].reduction = sldu_operand_reduction_i[l];
    assign sldu_operand_input[l].data      = sldu_operand_i[l];

    spill_register_flushable #(
      .T(sldu_operand_t)
    ) i_sldu_spill_register (
      .clk_i  (clk_i                                      ),
      .rst_ni (rst_ni                                     ),
      .valid_i(sldu_operand_valid_i[l] &&
               !reduction_stale_flush[l]                 ),
      .flush_i(reduction_stale_flush[l]                  ),
      .ready_o(sldu_operand_ready_q[l]                   ),
      .data_i (sldu_operand_input[l]                     ),
      .valid_o(sldu_operand_valid[l]                     ),
      .ready_i(sldu_operand_ready[l]                     ),
      .data_o (sldu_operand_payload[l]                   )
    );

    assign sldu_operand[l] = sldu_operand_payload[l].data;
    assign sldu_operand_ready_o[l] =
        sldu_operand_ready_q[l] && !reduction_stale_flush[l];
  end

  //////////////////////////
  //  Cut from the masku  //
  //////////////////////////

  typedef struct packed {
    logic  [NrLanes-1:0] lane_valid;
    strb_t [NrLanes-1:0] data;
  } mask_operand_t;

  mask_operand_t mask_payload_d, mask_payload_q;
  strb_t [NrLanes-1:0] mask_q;
  logic  [NrLanes-1:0] mask_valid_q;
  logic                mask_ready_d;
  logic                mask_spill_valid;
  logic                mask_spill_ready;
  logic                mask_context_finishing;
  logic                mask_context_handoff;
  logic                mask_input_context_valid;
  logic [idx_width(VInsnQueueDepth)-1:0] next_issue_pnt;

  // The spill registers may accept a replacement mask in the same cycle in
  // which their current word is consumed. Preserve it when the next queued
  // instruction is another masked slide; MASKU has already advanced to that
  // context, so the replacement is its first mask word. Otherwise discard it
  // when the issuing slide leaves the queue.
  assign mask_context_finishing = vinsn_issue_valid_q &&
      (vinsn_queue_d.issue_pnt != vinsn_queue_q.issue_pnt);
  assign next_issue_pnt = vinsn_queue_q.issue_pnt == VInsnQueueDepth-1
                        ? '0 : vinsn_queue_q.issue_pnt + 1'b1;
  assign mask_context_handoff = mask_context_finishing &&
      (vinsn_queue_q.issue_cnt > 1) &&
      (vinsn_queue_q.vinsn[next_issue_pnt].vfu == VFU_SlideUnit) &&
      !vinsn_queue_q.vinsn[next_issue_pnt].vm;

  assign mask_input_context_valid = ~vinsn_issue_q.vm &&
      vinsn_issue_valid_q &&
      (vinsn_issue_q.vfu == VFU_SlideUnit) &&
      (~mask_context_finishing || mask_context_handoff);

  // Keep the lane data and its final partial-lane validity in one aggregate
  // FIFO.  Separate lane spills can acquire different depths after a partial
  // word and then combine words from adjacent slide contexts.
  assign mask_payload_d.lane_valid = mask_valid_i;
  assign mask_payload_d.data       = mask_i;

  spill_register_flushable #(
    .T(mask_operand_t)
  ) i_mask_operand_register (
    .clk_i  (clk_i                                      ),
    .rst_ni (rst_ni                                     ),
    .flush_i(mask_context_finishing && !mask_context_handoff),
    .data_o (mask_payload_q                              ),
    .valid_o(mask_spill_valid                            ),
    .ready_i(mask_ready_d                                ),
    .data_i (mask_payload_d                               ),
    .valid_i((|mask_valid_i) && mask_input_context_valid),
    .ready_o(mask_spill_ready                            )
  );

  assign mask_q       = mask_payload_q.data;
  assign mask_valid_q = mask_payload_q.lane_valid & {NrLanes{mask_spill_valid}};


  // Don't upset the masku with a spurious ready
  assign mask_ready_o = mask_spill_ready && (|mask_valid_i) &&
                        mask_input_context_valid;

  ///////////////////
  //  NP2 Support  //
  ///////////////////

  // The SLDU only supports powers of two (p2) strides
  // Decompose the non-power-of-two (np2) slide in multiple p2 slides

  // We implement the np2 support here and fully process every input packet
  // singularly to comply with the undisturbed policy. We cannot use the VRF
  // as intermediate buffer; each VRF write is a commit.

  typedef logic [idx_width(8*NrLanes)-1:0] stride_t;

  stride_t                                  p2_stride_gen_stride_d;
  logic                                     p2_stride_gen_valid_d;
  logic                                     p2_stride_gen_update_d;
  logic [idx_width(idx_width(8*NrLanes)):0] p2_stride_gen_popc_q;
  stride_t                                  p2_stride_gen_stride_q;
  logic                                     p2_stride_gen_valid_q;

  p2_stride_gen #(
    .NrLanes (NrLanes)
  ) i_p2_stride_gen (
    .clk_i       (clk_i                 ),
    .rst_ni      (rst_ni                ),
    .stride_i    (p2_stride_gen_stride_d),
    .valid_i     (p2_stride_gen_valid_d ),
    .update_i    (p2_stride_gen_update_d),
    .popc_o      (p2_stride_gen_popc_q  ),
    .stride_p2_o (p2_stride_gen_stride_q),
    .valid_o     (p2_stride_gen_valid_q )
  );

  //////////////////
  //  Reductions  //
  //////////////////

  // Inter-lane reductions are performed with a logarithmic tree, and the result is
  // accumulated in the last Lane. Then, in the end, the result is passed to the first
  // lane for SIMD reduction
  logic [idx_width(NrLanes)-1:0] red_stride_cnt_d, red_stride_cnt_q;
  logic [idx_width(NrLanes):0] red_stride_cnt_d_wide;
  logic [idx_width(NrLanes)-1:0] osum_src_lane_d, osum_src_lane_q;

  logic is_issue_reduction, is_issue_alu_reduction, is_issue_vmfpu_reduction;

  assign is_issue_alu_reduction   = vinsn_issue_valid_q & (vinsn_issue_q.vfu == VFU_Alu);
  assign is_issue_vmfpu_reduction = vinsn_issue_valid_q & (vinsn_issue_q.vfu == VFU_MFpu);
  assign is_issue_reduction       = is_issue_alu_reduction | is_issue_vmfpu_reduction;

  always_comb begin
    sldu_mux_sel_o = NO_RED;
    if ((is_issue_alu_reduction && !(vinsn_commit_valid && vinsn_commit.vfu != VFU_Alu)) || (vinsn_commit_valid && vinsn_commit.vfu == VFU_Alu)) begin
      sldu_mux_sel_o = ALU_RED;
    end else if ((is_issue_vmfpu_reduction && !(vinsn_commit_valid && vinsn_commit.vfu != VFU_MFpu)) || (vinsn_commit_valid && vinsn_commit.vfu == VFU_MFpu)) begin
      sldu_mux_sel_o = MFPU_RED;
    end
  end

  /////////////////////
  //  SLDU DataPath  //
  /////////////////////

  // Input/output non-flat operands
  elen_t [NrLanes-1:0] sld_op_src;
  elen_t [NrLanes-1:0] sld_op_dst;

  // Input and output eew for reshuffling
  rvv_pkg::vew_e sld_eew_src;
  rvv_pkg::vew_e sld_eew_dst;

  // 0: slidedown, 1: slideup
  logic sld_dir;

  // The SLDU slides by powers of two
  logic [idx_width(4*NrLanes):0] sld_slamt;
  stride_t slide_intra_word_element_offset;

  // Complete aggregate words are skipped by the lane operand requester for
  // slidedown and by the destination VRF pointer for slideup.  The datapath
  // therefore permutes only the residual element offset within one aggregate.
  assign slide_intra_word_element_offset =
      vinsn_issue_q.stride[idx_width(8*NrLanes)-1:0] >>
      unsigned'(vinsn_issue_q.vtype.vsew);

  logic slide_down_source_oor;
  int unsigned slide_source_group_bytes;

  always_comb begin : p_slide_down_source_oor
    automatic int unsigned slide_vlmax;

    slide_source_group_bytes = VLEN / 8;
    unique case (vinsn_issue_q.vtype.vlmul)
      LMUL_1  : slide_source_group_bytes <<= 0;
      LMUL_2  : slide_source_group_bytes <<= 1;
      LMUL_4  : slide_source_group_bytes <<= 2;
      LMUL_8  : slide_source_group_bytes <<= 3;
      LMUL_1_2: slide_source_group_bytes >>= 1;
      LMUL_1_4: slide_source_group_bytes >>= 2;
      LMUL_1_8: slide_source_group_bytes >>= 3;
      default:;
    endcase
    slide_vlmax = slide_source_group_bytes >> vinsn_issue_q.vtype.vsew;

    slide_down_source_oor = vinsn_issue_valid_q &&
                            vinsn_issue_q.op == VSLIDEDOWN &&
                            !vinsn_issue_q.use_scalar_op &&
                            (vinsn_issue_q.stride >> vinsn_issue_q.vtype.vsew) >=
                            slide_vlmax;
  end

  sldu_op_dp #(
    .NrLanes  (NrLanes    )
  ) i_sldu_op_dp (
    .op_i     (sld_op_src ),
    .slamt_i  (sld_slamt  ),
    .eew_src_i(sld_eew_src),
    .eew_dst_i(sld_eew_dst),
    .dir_i    (sld_dir    ),
    .op_o     (sld_op_dst )
  );

  //////////////////
  //  Slide unit  //
  //////////////////

  // Vector instructions currently running
  logic [NrVInsn-1:0] vinsn_running_d, vinsn_running_q;

  // Interface with the main sequencer
  pe_resp_t pe_resp;

  // State of the slide FSM
  typedef enum logic [3:0] {
    SLIDE_IDLE,
    SLIDE_RUN,
    SLIDE_RUN_VSLIDE1UP_FIRST_WORD,
    SLIDE_EMIT_VSLIDE1DOWN_SCALAR,
    SLIDE_RUN_OSUM,
    SLIDE_WAIT_OSUM,
    SLIDE_NP2_SETUP,
    SLIDE_NP2_RUN,
    SLIDE_NP2_COMMIT,
    SLIDE_NP2_WAIT
  } slide_state_e;
  slide_state_e state_d, state_q;

  // A source-class bit travels with each lane word. On reduction startup,
  // discard only words that are provably from the preceding non-reduction
  // stream. Backpressure the upstream stream while flushing so a legitimate
  // reduction word cannot be acknowledged and lost in the same cycle.
  assign reduction_context_start =
      (state_q == SLIDE_IDLE) && (state_d == SLIDE_RUN) &&
      vinsn_issue_valid_q &&
      (vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu});

  for (genvar l = 0; l < NrLanes; l++) begin : gen_reduction_stale_flush
    assign reduction_stale_flush[l] = reduction_context_start &&
        ((sldu_operand_valid[l] && !sldu_operand_payload[l].reduction) ||
         (sldu_operand_valid_i[l] && !sldu_operand_reduction_i[l]));
  end

  // A maintenance reshuffle can safely reuse the untagged per-lane stream
  // only after all older commands, results, and buffered operands have drained.
  assign idle_o = state_q == SLIDE_IDLE &&
                  vinsn_queue_q.issue_cnt == '0 &&
                  vinsn_queue_q.commit_cnt == '0 &&
                  result_queue_empty &&
                  !(|sldu_operand_valid) &&
                  !(|sldu_operand_valid_i);

`ifdef FOR_VERIFY
  longint unsigned debug_reshuffle_idle_cycle_q;

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      debug_reshuffle_idle_cycle_q <= '0;
    end else begin
      debug_reshuffle_idle_cycle_q <= debug_reshuffle_idle_cycle_q + 1'b1;
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_RESHUFFLE_IDLE") &&
        debug_reshuffle_idle_cycle_q > 30000 &&
        (debug_reshuffle_idle_cycle_q % 100 == 0)) begin
      $display("[ARA_SLDU_IDLE] t=%0t idle=%0b state=%0d issue=%0d commit=%0d result=%0d spill=%b input=%b ready=%b",
               $time, idle_o, state_q, vinsn_queue_q.issue_cnt,
               vinsn_queue_q.commit_cnt, result_queue_cnt_q,
               sldu_operand_valid, sldu_operand_valid_i,
               sldu_operand_ready);
    end
  end
`endif

  logic  [8*NrLanes-1:0] out_en_flat, out_en_seq;
  strb_t [NrLanes-1:0]   out_en;

  // Pointers in the input operand and the output result
  logic   [idx_width(NrLanes*StrbWidth):0] in_pnt_d, in_pnt_q;
  logic   [idx_width(NrLanes*StrbWidth):0] out_pnt_d, out_pnt_q;
  vaddr_t                                  vrf_pnt_d, vrf_pnt_q;

  // Remaining bytes of the current instruction in the issue phase
  vlen_t issue_cnt_d, issue_cnt_q;
  // Respected by default: input_limit_d  = 8*NrLanes + out_pnt_d - in_pnt_d;
  // To enforce: output_limit_d = out_pnt_d + issue_cnt_d;
  // MAXVL == VLEN (when LMUL == 8, i.e., the maximum possible)
  logic [idx_width(VLEN+1):0] output_limit_d, output_limit_q;

  // Remaining bytes of the current instruction in the commit phase
  vlen_t commit_cnt_d, commit_cnt_q;

  always_comb begin: p_sldu
    // Maintain state
    vinsn_queue_d = vinsn_queue_q;
    issue_cnt_d   = issue_cnt_q;
    commit_cnt_d  = commit_cnt_q;
    in_pnt_d      = in_pnt_q;
    out_pnt_d     = out_pnt_q;
    vrf_pnt_d     = vrf_pnt_q;
    state_d       = state_q;

    result_queue_d           = result_queue_q;
    result_queue_valid_d     = result_queue_valid_q;
    result_queue_bytes_d     = result_queue_bytes_q;
    result_queue_read_pnt_d  = result_queue_read_pnt_q;
    result_queue_write_pnt_d = result_queue_write_pnt_q;
    result_queue_cnt_d       = result_queue_cnt_q;

    result_final_gnt_d = result_final_gnt_q;

    // Vector instructions currently running
    vinsn_running_d = vinsn_running_q & pe_vinsn_running_i;

    out_en_flat    = '0;
    out_en_seq     = '0;
    out_en         = '0;
    output_limit_d = output_limit_q;

    // We are not ready, by default
    pe_resp            = '0;
    mask_ready_d       = 1'b0;
    sldu_operand_ready = '0;

    // Lane selectors and operand queues can finish a reduction stream a few
    // cycles after its SLDU command has retired.  With no command left, those
    // words have no legal consumer and must not become the prefix of the next
    // untagged slide stream.  Drain them before advertising maintenance idle.
    if (maintenance_drain_i && state_q == SLIDE_IDLE &&
        vinsn_queue_q.issue_cnt == '0 &&
        vinsn_queue_q.commit_cnt == '0 && result_queue_empty)
      sldu_operand_ready = '1;

    red_stride_cnt_d = red_stride_cnt_q;
    osum_src_lane_d  = osum_src_lane_q;

    p2_stride_gen_stride_d = '0;
    p2_stride_gen_valid_d  = 1'b0;
    p2_stride_gen_update_d = 1'b0;

    np2_data_d       = np2_data_q;
    np2_data_valid_d = np2_data_valid_q;
    overlap_snapshot_d = overlap_snapshot_q;
    overlap_snapshot_valid_d = overlap_snapshot_valid_q;

    red_stride_cnt_d_wide = {red_stride_cnt_q, red_stride_cnt_q[idx_width(NrLanes)-1]};

    // Inform the main sequencer if we are idle
    pe_req_ready_o = !vinsn_queue_full;

    // Slide Unit DP
    sld_op_src  = state_q inside {SLIDE_NP2_RUN, SLIDE_NP2_COMMIT} &&
                  np2_data_valid_q
                ? np2_data_q
                : slide_down_source_oor
                ? '0
                : vinsn_issue_q.overlap_use_snapshot && overlap_snapshot_valid_q &&
                  vrf_pnt_q == vinsn_issue_q.overlap_snapshot_word
                ? overlap_snapshot_q : sldu_operand;
    sld_eew_src = (vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu}) ||
                  (vinsn_issue_q.overlap_use_snapshot && overlap_snapshot_valid_q &&
                   vrf_pnt_q == vinsn_issue_q.overlap_snapshot_word)
                ? vinsn_issue_q.vtype.vsew
                : vinsn_issue_q.eew_vs2;
    sld_eew_dst = vinsn_issue_q.vtype.vsew;
    sld_dir     = (vinsn_issue_q.op == VSLIDEUP) || (vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu});
    sld_slamt   = (vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu})
                ? red_stride_cnt_q
                : slide_intra_word_element_offset;

    /////////////////
    //  Slide FSM  //
    /////////////////

    unique case (state_q)
      SLIDE_IDLE: begin
        // Result entries do not carry their producer class; output routing is
        // selected from the commit-head instruction.  Slides may pipeline with
        // other slides, but a reduction must not overlap an older instruction
        // (and a younger slide must not overlap a committing reduction).
        if (vinsn_issue_valid_q &&
            ((vinsn_queue_q.commit_cnt == vinsn_queue_q.issue_cnt) ||
             (vinsn_issue_q.vfu == VFU_SlideUnit &&
              vinsn_commit.vfu == VFU_SlideUnit))) begin
          state_d   = vinsn_issue_q.is_stride_np2 && !slide_down_source_oor
                    ? SLIDE_NP2_SETUP : SLIDE_RUN;
          vrf_pnt_d = '0;

          unique case (vinsn_issue_q.op)
            VSLIDEUP: begin
              // vslideup starts reading the source operand from its beginning
              in_pnt_d  = '0;
              // vslideup starts writing the destination vector at the slide offset
              out_pnt_d = vinsn_issue_q.stride[idx_width(8*NrLanes)-1:0];

              // Initialize counters
              issue_cnt_d = vinsn_issue_q.vl << int'(vinsn_issue_q.vtype.vsew);

              // Initialize be-enable-generation ancillary signals
              output_limit_d = vinsn_issue_q.use_scalar_op ? out_pnt_d + issue_cnt_d : issue_cnt_d;

              // Trim vector elements which are not touched by the slide unit
              issue_cnt_d -= vinsn_issue_q.stride[$bits(issue_cnt_d)-1:0];

              // Start writing at the middle of the destination vector
              vrf_pnt_d = vinsn_issue_q.stride >> $clog2(8*NrLanes);

              // Go to SLIDE_RUN_VSLIDE1UP_FIRST_WORD if this is a vslide1up instruction
              if (vinsn_issue_q.use_scalar_op)
                state_d = SLIDE_RUN_VSLIDE1UP_FIRST_WORD;
            end
            VSLIDEDOWN: begin
              // vslidedown starts reading the source operand from the slide offset
              in_pnt_d  = slide_down_source_oor
                        ? '0
                        : vinsn_issue_q.stride[idx_width(8*NrLanes)-1:0];
              // vslidedown starts writing the destination vector at its beginning
              out_pnt_d = '0;

              // Initialize counters
              issue_cnt_d = vinsn_issue_q.vl << int'(vinsn_issue_q.vtype.vsew);

              // Initialize be-enable-generation ancillary signals
              output_limit_d = vinsn_issue_q.use_scalar_op
                             ? issue_cnt_d - (1 << int'(vinsn_issue_q.vtype.vsew))
                             : issue_cnt_d;

              // Trim the last element of vslide1down, which does not come from the VRF
              if (vinsn_issue_q.use_scalar_op) begin
                issue_cnt_d -= 1 << int'(vinsn_issue_q.vtype.vsew);
                if (issue_cnt_d == '0)
                  state_d = SLIDE_EMIT_VSLIDE1DOWN_SCALAR;
              end
            end
            // Ordered sum reductions
            VFREDOSUM, VFWREDOSUM: begin
              // Ordered redsum instructions doesn't need in/out_pnt
              in_pnt_d  = '0;
              out_pnt_d = '0;

              // The total number of transactions is vl - 1, but the last data is sent
              // to lane 0
              issue_cnt_d     = vinsn_issue_q.vl;
              osum_src_lane_d = '0;

              state_d = SLIDE_RUN_OSUM;
            end
            // Unordered reductions
            default: begin
              // Unordered redsum instructions doesn't need in/out_pnt
              in_pnt_d  = '0;
              out_pnt_d = '0;

              // Initialize issue cnt. Pretend to move NrLanes 64-bit elements for (clog2(NrLanes) + 1) times.
              issue_cnt_d  = (NrLanes * ($clog2(NrLanes) + 1)) << EW64;
            end
          endcase
        end
      end

      SLIDE_RUN, SLIDE_RUN_VSLIDE1UP_FIRST_WORD, SLIDE_NP2_COMMIT: begin
        // Are we ready?
        // During a reduction (vinsn_issue_q.vfu == VFU_Alu/VFU_MFPU) don't wait for mask bits
        if (((state_q == SLIDE_NP2_COMMIT
              ? np2_data_valid_q : &sldu_operand_valid) ||
             slide_down_source_oor ||
           (((vinsn_issue_q.stride[$bits(vinsn_issue_q.vl)-1:0] >> vinsn_issue_q.vtype.vsew) >= vinsn_issue_q.vl) &&
           (state_q == SLIDE_RUN_VSLIDE1UP_FIRST_WORD))) &&
           !result_queue_full && (vinsn_issue_q.vm || vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu} || (|mask_valid_q)))
        begin

          // How many bytes are we copying from the operand to the destination, in this cycle?
          automatic int in_byte_count = NrLanes * 8 - in_pnt_q;
          automatic int out_byte_count = NrLanes * 8 - out_pnt_q;
          automatic int byte_count = in_byte_count < out_byte_count ? in_byte_count : out_byte_count;
          automatic int remaining_byte_count = issue_cnt_q < byte_count
                                             ? issue_cnt_q : byte_count;
          automatic int current_output_end = out_pnt_q + remaining_byte_count;
          automatic int unsigned output_word_base =
              unsigned'(vrf_pnt_q) * NrLanes * 8;
          automatic int unsigned preserved_prefix_bytes =
              unsigned'(vinsn_issue_q.vstart) << unsigned'(vinsn_issue_q.vtype.vsew);
          automatic logic partial_reshuffle = vinsn_issue_q.scale_vl &&
              vinsn_issue_q.op == VSLIDEDOWN && vinsn_issue_q.stride == '0 &&
              vinsn_issue_q.vstart != '0;
          automatic int unsigned scalar_seq_byte =
              (unsigned'(vinsn_issue_q.vl) - 1) << unsigned'(vinsn_issue_q.vtype.vsew);
          automatic int unsigned scalar_word_offset = scalar_seq_byte % (NrLanes * 8);
          automatic int unsigned vslideup_first_word =
              unsigned'(vinsn_issue_q.stride) / (NrLanes * 8);
          automatic int unsigned vslideup_prefix_bytes =
              unsigned'(vinsn_issue_q.stride) % (NrLanes * 8);

          if (vinsn_issue_q.overlap_capture &&
              vrf_pnt_q == vinsn_issue_q.overlap_snapshot_word) begin
            overlap_snapshot_d = sld_op_dst;
            overlap_snapshot_valid_d = 1'b1;
          end

          // Build the sequential byte-output-enable
          for (int unsigned b = 0; b < 8*NrLanes; b++)
            if (((b >= out_pnt_q && b < output_limit_q &&
                  b < current_output_end) &&
                 (!partial_reshuffle ||
                  (output_word_base + b >= preserved_prefix_bytes))) ||
                vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu})
              out_en_seq[b] = 1'b1;

          // Shuffle the output enable
          for (int unsigned b = 0; b < 8*NrLanes; b++)
            out_en_flat[shuffle_index(b, NrLanes, vinsn_issue_q.vtype.vsew)] = out_en_seq[b];

          // Mask the output enable with the mask vector
          out_en = out_en_flat & ({8*NrLanes{vinsn_issue_q.vm | (vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu})}} | mask_q);

          // A capture has no result payload.  In particular, do not leave byte
          // enables in an invalid queue slot that a later partial fixup reuses.
          if (!vinsn_issue_q.overlap_capture) begin
            // Write in the correct bytes
            for (int lane = 0; lane < NrLanes; lane++)
              for (int b = 0; b < 8; b++)
                if (out_en[lane][b]) begin
                  result_queue_d[result_queue_write_pnt_q][lane].wdata[8*b +: 8] =
                    sld_op_dst[lane][8*b +: 8];
                  result_queue_d[result_queue_write_pnt_q][lane].be[b] = 1'b1;
                end

            // vslidedown reads up to VLMAX, not merely VL.  Operand requests
            // can span the end of the source group, so replace bytes beyond
            // that architectural boundary with zero before writeback.
            if (vinsn_issue_q.op == VSLIDEDOWN &&
                !vinsn_issue_q.use_scalar_op &&
                vinsn_issue_q.stride != '0) begin
              for (int unsigned b = 0; b < 8*NrLanes; b++) begin
                automatic int unsigned shuffled_byte;
                shuffled_byte = shuffle_index(
                    b, NrLanes, vinsn_issue_q.vtype.vsew);
                if (out_en_seq[b] &&
                    output_word_base + b + unsigned'(vinsn_issue_q.stride) >=
                        slide_source_group_bytes)
                  result_queue_d[result_queue_write_pnt_q]
                      [shuffled_byte / 8].wdata[8*(shuffled_byte % 8) +: 8] = '0;
              end
            end

            // Initialize id and addr fields of the result queue requests
            for (int lane = 0; lane < NrLanes; lane++) begin
              result_queue_d[result_queue_write_pnt_q][lane].id = vinsn_issue_q.id;
              result_queue_d[result_queue_write_pnt_q][lane].addr =
                vaddr(vinsn_issue_q.vd, NrLanes, VLEN) + vrf_pnt_q;
            end
          end

          // Bump pointers (reductions always finish in one shot)
          in_pnt_d    = vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu} ? NrLanes * 8                  : in_pnt_q  + byte_count;
          out_pnt_d   = vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu} ? NrLanes * 8                  : out_pnt_q + byte_count;
          if (vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu})
            issue_cnt_d = issue_cnt_q <= (NrLanes * 8)
                        ? '0 : issue_cnt_q - (NrLanes * 8);
          else
            issue_cnt_d = issue_cnt_q <= byte_count
                        ? '0 : issue_cnt_q - byte_count;

          // In Jump to SLIDE_RUN if stride is P2
          if (state_q != SLIDE_NP2_COMMIT)
            state_d = SLIDE_RUN;

          // If this is a vslide1up instruction, copy the scalar operand to the first word
          if (state_q == SLIDE_RUN_VSLIDE1UP_FIRST_WORD)
            unique case (vinsn_issue_q.vtype.vsew)
              EW8: begin
                result_queue_d[result_queue_write_pnt_q][0].wdata[7:0] =
                  vinsn_issue_q.scalar_op[7:0];
                result_queue_d[result_queue_write_pnt_q][0].be[0:0] =
                  vinsn_issue_q.vm || mask_q[0][0];
              end
              EW16: begin
                result_queue_d[result_queue_write_pnt_q][0].wdata[15:0] =
                  vinsn_issue_q.scalar_op[15:0];
                result_queue_d[result_queue_write_pnt_q][0].be[1:0] =
                  {2{vinsn_issue_q.vm || mask_q[0][0]}};
              end
              EW32: begin
                result_queue_d[result_queue_write_pnt_q][0].wdata[31:0] =
                  vinsn_issue_q.scalar_op[31:0];
                result_queue_d[result_queue_write_pnt_q][0].be[3:0] =
                  {4{vinsn_issue_q.vm || mask_q[0][0]}};
              end
              EW64: begin
                result_queue_d[result_queue_write_pnt_q][0].wdata[63:0] =
                  vinsn_issue_q.scalar_op[63:0];
                result_queue_d[result_queue_write_pnt_q][0].be[7:0] =
                  {8{vinsn_issue_q.vm || mask_q[0][0]}};
              end
            endcase

          // Read a full word from the VRF or finished the instruction
          if (in_pnt_d == NrLanes * 8 || issue_cnt_q <= byte_count) begin
            // Reset the pointer and ask for a new operand
            in_pnt_d           = '0;
            if (state_q == SLIDE_NP2_COMMIT)
              np2_data_valid_d = 1'b0;
            else if (!slide_down_source_oor)
              sldu_operand_ready = '1;
            // Left-rotate the logarithmic counter. Hacky way to write it, but it's to
            // deal with the 2-lanes design without complaints from Verilator...
            // wide signal to please the tool
            red_stride_cnt_d_wide = {red_stride_cnt_q, red_stride_cnt_q[idx_width(NrLanes)-1]};
            red_stride_cnt_d      = red_stride_cnt_d_wide[idx_width(NrLanes)-1:0];

            if (state_q == SLIDE_NP2_COMMIT) begin
              // Jump to NP2 setup again
              state_d = SLIDE_NP2_SETUP;
            end
          end

          // Filled up a word to the VRF or finished the instruction
          if (out_pnt_d == NrLanes * 8 || issue_cnt_q <= byte_count) begin
            // Reset the pointer
            out_pnt_d = vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu} ? {'0, red_stride_cnt_d, 3'b0} : '0;
            // We used all the bits of the mask
            if (vinsn_issue_q.op inside {VSLIDEUP, VSLIDEDOWN}) begin
              // If the vslide1down scalar shares this aggregate word, retain
              // its mask until the scalar-only write is emitted.  At a word
              // boundary the scalar belongs to the next mask word instead.
              mask_ready_d = !vinsn_issue_q.vm &&
                  !(vinsn_issue_q.op == VSLIDEDOWN &&
                    vinsn_issue_q.use_scalar_op &&
                    issue_cnt_q <= byte_count && scalar_word_offset != 0);
            end

            // Increment VRF address
            vrf_pnt_d = vrf_pnt_q + 1;

            // A capture uop only consumes the VRF operand stream.  All normal
            // slides and overlap fixups continue through the result queue.
            if (!vinsn_issue_q.overlap_capture) begin
              result_queue_cnt_d += 1;
              result_queue_valid_d[result_queue_write_pnt_q] = '1;
              // Record the complete logical interval accumulated in this
              // entry, independently of byte enables.  An entry can be filled
              // over multiple input beats, so the final beat size alone is not
              // sufficient.  A reduction always represents one aggregate
              // step.  For an ordinary vslideup, the first destination word
              // also covers an untouched prefix that is not logical progress;
              // vslide1up does write that prefix with its scalar operand.
              // Masked elements still count as completed architectural bytes.
              result_queue_bytes_d[result_queue_write_pnt_q] =
                  vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu}
                  ? vlen_t'(NrLanes * 8)
                  : vinsn_issue_q.op == VSLIDEUP &&
                    !vinsn_issue_q.use_scalar_op &&
                    unsigned'(vrf_pnt_q) == vslideup_first_word
                  ? vlen_t'(current_output_end - vslideup_prefix_bytes)
                  : vlen_t'(current_output_end);
              result_queue_write_pnt_d                       = result_queue_write_pnt_q + 1;
              if (result_queue_write_pnt_q == ResultQueueDepth-1)
                result_queue_write_pnt_d = '0;
            end

            if (state_q == SLIDE_NP2_COMMIT) state_d = SLIDE_NP2_WAIT;
          end

          // Finished the operation
          if (issue_cnt_q <= byte_count || (vinsn_issue_q.vfu inside {VFU_Alu, VFU_MFpu} && issue_cnt_q <= 8 * NrLanes)) begin
            // Reset the logarighmic counter
            red_stride_cnt_d = 1;

            // A vslide1down scalar is emitted as a separate result entry.  It
            // may share the source's last aggregate VRF word or occupy the
            // first element of the next one; keeping it separate handles both
            // cases, including VL=1, without requiring two queue allocations
            // in a single cycle.
            if (vinsn_issue_q.op == VSLIDEDOWN && vinsn_issue_q.use_scalar_op) begin
              state_d = SLIDE_EMIT_VSLIDE1DOWN_SCALAR;
            end else begin
              state_d = SLIDE_IDLE;
              // Increment vector instruction queue pointers and counters
              vinsn_queue_d.issue_pnt += 1;
              vinsn_queue_d.issue_cnt -= 1;
            end

            // Capture uops have no architectural result to commit.  A fixup
            // that consumes the saved word owns it until its final issue beat.
            if (vinsn_issue_q.overlap_capture)
              commit_cnt_d = '0;
            if (vinsn_issue_q.overlap_use_snapshot)
              overlap_snapshot_valid_d = 1'b0;
          end
        end
      end
      SLIDE_EMIT_VSLIDE1DOWN_SCALAR: begin
        // The scalar is destination element vl-1.  Emit one sparse aggregate
        // result entry so commit accounting sees exactly one additional
        // element, even when it starts a new aggregate VRF word.
        if (!result_queue_full && (vinsn_issue_q.vm || (|mask_valid_q))) begin
          automatic int unsigned scalar_seq_byte =
              (unsigned'(vinsn_issue_q.vl) - 1) << unsigned'(vinsn_issue_q.vtype.vsew);
          automatic int unsigned scalar_word = scalar_seq_byte / (NrLanes * 8);
          automatic int unsigned scalar_word_offset = scalar_seq_byte % (NrLanes * 8);
          automatic int unsigned shuffled_byte = shuffle_index(
              scalar_word_offset, NrLanes, vinsn_issue_q.vtype.vsew);
          automatic int unsigned tgt_lane = shuffled_byte / 8;
          automatic int unsigned tgt_lane_offset = shuffled_byte % 8;
          automatic logic scalar_mask_bit =
              vinsn_issue_q.vm || mask_q[tgt_lane][tgt_lane_offset];

          for (int lane = 0; lane < NrLanes; lane++) begin
            result_queue_d[result_queue_write_pnt_q][lane] = '0;
            result_queue_d[result_queue_write_pnt_q][lane].id = vinsn_issue_q.id;
            result_queue_d[result_queue_write_pnt_q][lane].addr =
              vaddr(vinsn_issue_q.vd, NrLanes, VLEN) + vaddr_t'(scalar_word);
          end

          unique case (vinsn_issue_q.vtype.vsew)
            EW8: begin
              result_queue_d[result_queue_write_pnt_q][tgt_lane]
                  .wdata[8*tgt_lane_offset +: 8] = vinsn_issue_q.scalar_op[7:0];
              result_queue_d[result_queue_write_pnt_q][tgt_lane]
                  .be[tgt_lane_offset +: 1] = scalar_mask_bit;
            end
            EW16: begin
              result_queue_d[result_queue_write_pnt_q][tgt_lane]
                  .wdata[8*tgt_lane_offset +: 16] = vinsn_issue_q.scalar_op[15:0];
              result_queue_d[result_queue_write_pnt_q][tgt_lane]
                  .be[tgt_lane_offset +: 2] = {2{scalar_mask_bit}};
            end
            EW32: begin
              result_queue_d[result_queue_write_pnt_q][tgt_lane]
                  .wdata[8*tgt_lane_offset +: 32] = vinsn_issue_q.scalar_op[31:0];
              result_queue_d[result_queue_write_pnt_q][tgt_lane]
                  .be[tgt_lane_offset +: 4] = {4{scalar_mask_bit}};
            end
            EW64: begin
              result_queue_d[result_queue_write_pnt_q][tgt_lane]
                  .wdata[8*tgt_lane_offset +: 64] = vinsn_issue_q.scalar_op[63:0];
              result_queue_d[result_queue_write_pnt_q][tgt_lane]
                  .be[tgt_lane_offset +: 8] = {8{scalar_mask_bit}};
            end
          endcase

          result_queue_cnt_d += 1;
          result_queue_valid_d[result_queue_write_pnt_q] = '1;
          result_queue_bytes_d[result_queue_write_pnt_q] =
              vlen_t'(1) << unsigned'(vinsn_issue_q.vtype.vsew);
          if (result_queue_write_pnt_q == ResultQueueDepth-1)
            result_queue_write_pnt_d = '0;
          else
            result_queue_write_pnt_d = result_queue_write_pnt_q + 1'b1;

          mask_ready_d = !vinsn_issue_q.vm;
          state_d = SLIDE_IDLE;
          vinsn_queue_d.issue_pnt += 1;
          vinsn_queue_d.issue_cnt -= 1;
        end
      end
      SLIDE_RUN_OSUM: begin
        // Ordered reductions form one token chain across the lanes. A lane that
        // has completed locally may expose younger traffic on the shared bus,
        // so only the owner of the next element may advance the chain.
        // Don't wait for mask bits
        if (!result_queue_full && sldu_operand_valid[osum_src_lane_q]) begin
          automatic int tgt_lane = (osum_src_lane_q == NrLanes - 1) ? 0
                                                                    : osum_src_lane_q + 1;
          // The final accumulated value always returns to lane 0 for writeback.
          if (issue_cnt_q == 1) tgt_lane = 0;

          sldu_operand_ready[osum_src_lane_q] = 1'b1;
          result_queue_d[result_queue_write_pnt_q][tgt_lane].wdata =
            sldu_operand[osum_src_lane_q];
          result_queue_d[result_queue_write_pnt_q][tgt_lane].be =
            {8{vinsn_issue_q.vm}} | mask_q[tgt_lane];
          result_queue_valid_d[result_queue_write_pnt_q][tgt_lane] = '1;

          issue_cnt_d = issue_cnt_q - 1;
          if (osum_src_lane_q == NrLanes - 1)
            osum_src_lane_d = '0;
          else
            osum_src_lane_d = osum_src_lane_q + 1'b1;
        end

        // Finish the operation
        if (issue_cnt_d == '0) begin
          state_d      = SLIDE_WAIT_OSUM;
          // Increment vector instruction queue pointers and counters
          vinsn_queue_d.issue_pnt += 1;
          vinsn_queue_d.issue_cnt -= 1;
        end
      end
      SLIDE_WAIT_OSUM: begin
        // Wait one cycle for the last result processing
        commit_cnt_d = 1'b0;
        state_d      = SLIDE_IDLE;
      end
      SLIDE_NP2_SETUP: begin
        // Setup the p2-stride generator
        p2_stride_gen_stride_d = slide_intra_word_element_offset;
        p2_stride_gen_valid_d  = 1'b1;
        // Start an aggregate only when all lanes expose the same stream beat.
        // The following power-of-two steps operate exclusively on np2_data_q.
        if (&sldu_operand_valid && result_queue_empty) begin
          result_queue_read_pnt_d  = NP2_RESULT_PNT;
          result_queue_write_pnt_d = NP2_RESULT_PNT;
          state_d = SLIDE_NP2_RUN;
        end
      end
      SLIDE_NP2_RUN: begin
        // Setup the current p2 stride
        sld_slamt = p2_stride_gen_stride_q;
        // Consume one external aggregate for the first step, then iterate on
        // the dedicated atomic feedback register without touching lane spills.
        if (np2_data_valid_q || &sldu_operand_valid) begin
          np2_data_d       = sld_op_dst;
          np2_data_valid_d = 1'b1;
          if (!np2_data_valid_q)
            sldu_operand_ready = '1;
          // Update the p2 stride
          p2_stride_gen_update_d = 1'b1;
          // Commit the final result
          if (p2_stride_gen_popc_q == {'0, 1'b1} && result_queue_empty) begin
            state_d = SLIDE_NP2_COMMIT;
            // Prepare the write pointer
            result_queue_write_pnt_d = NP2_RESULT_PNT;
          end
        end
      end
      SLIDE_NP2_WAIT: begin
        if (result_queue_empty) begin
          result_queue_read_pnt_d  = NP2_RESULT_PNT;
          result_queue_write_pnt_d = NP2_RESULT_PNT;
          // A misaligned input aggregate can still contain bytes for the next
          // output word. If it was fully consumed together with the queued
          // result, start a new external aggregate instead of waiting for a
          // feedback value that no longer exists.
          state_d = np2_data_valid_q ? SLIDE_NP2_COMMIT : SLIDE_NP2_SETUP;
        end
      end
      default:;
    endcase

    //////////////////////////////////
    //  Write results into the VRF  //
    //////////////////////////////////

    for (int lane = 0; lane < NrLanes; lane++) begin: result_write
      sldu_result_req_o[lane]   = result_queue_valid_q[result_queue_read_pnt_q][lane] & (~(vinsn_commit.vfu inside {VFU_Alu, VFU_MFpu}));
      sldu_red_valid_o[lane]    = result_queue_valid_q[result_queue_read_pnt_q][lane] & (vinsn_commit.vfu inside {VFU_Alu, VFU_MFpu});
      sldu_result_addr_o[lane]  = result_queue_q[result_queue_read_pnt_q][lane].addr;
      sldu_result_id_o[lane]    = result_queue_q[result_queue_read_pnt_q][lane].id;
      sldu_result_wdata_o[lane] = result_queue_q[result_queue_read_pnt_q][lane].wdata;
      sldu_result_be_o[lane]    = result_queue_q[result_queue_read_pnt_q][lane].be;

      // Update the final gnt vector
      result_final_gnt_d[lane] |= sldu_result_final_gnt_i[lane];

      // Received a grant from the VRF (slide) or from the FUs (reduction).
      // Deactivate the request, but do not bump the pointers for now.
      if (((vinsn_commit.vfu inside {VFU_Alu, VFU_MFpu} && sldu_red_valid_o[lane]) || sldu_result_req_o[lane]) && sldu_result_gnt_i[lane]) begin
        result_queue_valid_d[result_queue_read_pnt_q][lane] = 1'b0;
        result_queue_d[result_queue_read_pnt_q][lane]       = '0;
        // Reset the final gnt vector since we are now waiting for another final gnt
        result_final_gnt_d[lane] = 1'b0;
      end
    end: result_write

    // Advance a slide result only after every lane has observed the final VRF
    // grant.  A normal grant merely transfers the beat into the operand
    // requester's stream register; reusing a delayed final grant from an older
    // beat can otherwise retire the instruction before its last write lands.
    // Reductions are consumed directly by the functional units and need no
    // final VRF grant.
    if (!(|result_queue_valid_d[result_queue_read_pnt_q]) &&
      (vinsn_commit.vfu inside {VFU_Alu, VFU_MFpu} || &result_final_gnt_d))
      // There is something waiting to be written
      if (!result_queue_empty) begin
        if (state_q != SLIDE_NP2_SETUP)
          // Increment the read pointer
          if (result_queue_read_pnt_q == ResultQueueDepth-1)
            result_queue_read_pnt_d = 0;
          else
            result_queue_read_pnt_d = result_queue_read_pnt_q + 1;

        // Decrement the counter of results waiting to be written
        result_queue_cnt_d -= 1;

        // A partial aggregate and a scalar-only tail do not represent a full
        // lane word. Retire exactly the logical bytes carried by this entry.
        commit_cnt_d = commit_cnt_q - result_queue_bytes_q[result_queue_read_pnt_q];
        if (commit_cnt_q <= result_queue_bytes_q[result_queue_read_pnt_q])
          commit_cnt_d = '0;
        result_queue_bytes_d[result_queue_read_pnt_q] = '0;
      end

    // Finished committing the results of a vector instruction
    if (vinsn_commit_valid && commit_cnt_d == '0) begin
      // Mark the vector instruction as being done
      pe_resp.vinsn_done[vinsn_commit.id] = 1'b1;

      // Update the commit counters and pointers
      vinsn_queue_d.commit_cnt -= 1;
      if (vinsn_queue_d.commit_pnt == VInsnQueueDepth-1)
        vinsn_queue_d.commit_pnt = '0;
      else
        vinsn_queue_d.commit_pnt += 1;

      // Update the commit counter for the next instruction
      if (vinsn_queue_d.commit_cnt != '0) begin
        commit_cnt_d = vinsn_queue_q.vinsn[vinsn_queue_d.commit_pnt].op inside {VSLIDEUP, VSLIDEDOWN}
                     ? vinsn_queue_q.vinsn[vinsn_queue_d.commit_pnt].vl << int'(vinsn_queue_q.vinsn[vinsn_queue_d.commit_pnt].vtype.vsew)
                     : (NrLanes * ($clog2(NrLanes) + 1)) << EW64;

        // Trim vector elements which are not written by the slide unit
        if (vinsn_queue_q.vinsn[vinsn_queue_d.commit_pnt].op == VSLIDEUP &&
            !vinsn_queue_q.vinsn[vinsn_queue_d.commit_pnt].use_scalar_op)
          commit_cnt_d -= vinsn_queue_q.vinsn[vinsn_queue_d.commit_pnt].stride[$bits(commit_cnt_d)-1:0];
      end
    end

    //////////////////////////////
    //  Accept new instruction  //
    //////////////////////////////

    if (!vinsn_queue_full && pe_req_valid_i && !vinsn_running_d[pe_req_i.id] &&
      (pe_req_i.vfu == VFU_SlideUnit || pe_req_i.op inside {[VREDSUM:VWREDSUM], [VFREDUSUM:VFWREDOSUM]})) begin
      vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt] = pe_req_i;
      vinsn_running_d[pe_req_i.id]                  = 1'b1;

      // Calculate the slide offset inside the vector register
      if (pe_req_i.op inside {VSLIDEUP, VSLIDEDOWN})
        vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt].stride =
            saturating_byte_offset(pe_req_i.stride, pe_req_i.vtype.vsew);
      // Always move 64-bit packs of data from one lane to the other
      if (pe_req_i.vfu inside {VFU_Alu, VFU_MFpu})
        vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt].vtype.vsew = EW64;

      if (vinsn_queue_d.commit_cnt == '0) begin
        commit_cnt_d = pe_req_i.op inside {VSLIDEUP, VSLIDEDOWN}
                     ? pe_req_i.vl << int'(pe_req_i.vtype.vsew)
                     : (NrLanes * ($clog2(NrLanes) + 1)) << EW64;
        // Trim vector elements which are not written by the slide unit
        // VSLIDE1UP always writes at least 1 element
        if (pe_req_i.op == VSLIDEUP && !pe_req_i.use_scalar_op) begin
          commit_cnt_d -= vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt].stride[$bits(commit_cnt_d)-1:0];
        end
      end

      // Bump pointers and counters of the vector instruction queue
      vinsn_queue_d.accept_pnt += 1;
      vinsn_queue_d.issue_cnt += 1;
      vinsn_queue_d.commit_cnt += 1;
    end
  end: p_sldu

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      vinsn_running_q       <= '0;
      issue_cnt_q           <= '0;
      commit_cnt_q          <= '0;
      in_pnt_q              <= '0;
      out_pnt_q             <= '0;
      vrf_pnt_q             <= '0;
      output_limit_q        <= '0;
      state_q               <= SLIDE_IDLE;
      pe_resp_o             <= '0;
      result_final_gnt_q    <= '0;
      red_stride_cnt_q      <= 1;
      osum_src_lane_q       <= '0;
      np2_data_q            <= '0;
      np2_data_valid_q      <= 1'b0;
      overlap_snapshot_q       <= '0;
      overlap_snapshot_valid_q <= 1'b0;
    end else begin
      vinsn_running_q       <= vinsn_running_d;
      issue_cnt_q           <= issue_cnt_d;
      commit_cnt_q          <= commit_cnt_d;
      in_pnt_q              <= in_pnt_d;
      out_pnt_q             <= out_pnt_d;
      vrf_pnt_q             <= vrf_pnt_d;
      output_limit_q        <= output_limit_d;
      state_q               <= state_d;
      pe_resp_o             <= pe_resp;
      result_final_gnt_q    <= result_final_gnt_d;
      red_stride_cnt_q      <= red_stride_cnt_d;
      osum_src_lane_q       <= osum_src_lane_d;
      np2_data_q            <= np2_data_d;
      np2_data_valid_q      <= np2_data_valid_d;
      overlap_snapshot_q       <= overlap_snapshot_d;
      overlap_snapshot_valid_q <= overlap_snapshot_valid_d;
    end
  end

`ifdef FOR_VERIFY
  logic [9:0] slide_debug_quiet_q;

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_SLIDE398")) begin
      if (pe_req_valid_i && pe_req_ready_o && pe_req_i.op == VSLIDEDOWN &&
          pe_req_i.vd == 5'd6 && pe_req_i.vs2 == 5'd20 &&
          pe_req_i.vl == 11 && pe_req_i.vtype.vsew == EW64)
        $display("[ARA_SLIDE398_ACCEPT] t=%0t id=%0d stride=%0d vm=%0b vstart=%0d",
                 $time, pe_req_i.id, pe_req_i.stride, pe_req_i.vm,
                 pe_req_i.vstart);

      if (vinsn_issue_valid_q && vinsn_issue_q.op == VSLIDEDOWN &&
          vinsn_issue_q.vd == 5'd6 && vinsn_issue_q.vs2 == 5'd20 &&
          vinsn_issue_q.vl == 11 && vinsn_issue_q.vtype.vsew == EW64 &&
          ((state_q != state_d) || (issue_cnt_q != issue_cnt_d) ||
           (|sldu_operand_ready) || (|sldu_result_req_o)))
        $display("[ARA_SLIDE398] t=%0t id=%0d state=%0d->%0d issue=%0d->%0d in=%0d->%0d out=%0d->%0d vrf=%0d oor=%0b op_v=%b op_r=%b mask_v=%b mask=%h src=%h dst=%h out_en=%h req=%b",
                 $time, vinsn_issue_q.id, state_q, state_d,
                 issue_cnt_q, issue_cnt_d, in_pnt_q, in_pnt_d,
                 out_pnt_q, out_pnt_d, vrf_pnt_q, slide_down_source_oor,
                 sldu_operand_valid, sldu_operand_ready, mask_valid_q,
                 mask_q, sldu_operand, sld_op_dst, out_en,
                 sldu_result_req_o);
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      slide_debug_quiet_q <= '0;
    end else if ($test$plusargs("ARA_DEBUG_SLIDE_MASK")) begin
      if (pe_req_valid_i && pe_req_ready_o &&
          pe_req_i.op inside {VSLIDEUP, VSLIDEDOWN}) begin
        $display("[ARA_SLDU_ACCEPT] t=%0t id=%0d op=%0d vl=%0d stride_elm=%0d vm=%0b vsew=%0d scalar=%0b",
                 $time, pe_req_i.id, pe_req_i.op, pe_req_i.vl,
                 pe_req_i.stride, pe_req_i.vm, pe_req_i.vtype.vsew,
                 pe_req_i.use_scalar_op);
      end

      if ((vinsn_issue_valid_q &&
           vinsn_issue_q.op inside {VSLIDEUP, VSLIDEDOWN}) ||
          (vinsn_commit_valid &&
           vinsn_commit.op inside {VSLIDEUP, VSLIDEDOWN})) begin
        automatic logic slide_event;
        slide_event = (state_q != state_d) || (issue_cnt_q != issue_cnt_d) ||
                      (commit_cnt_q != commit_cnt_d) || (|sldu_operand_ready) ||
                      mask_ready_d || (|sldu_result_req_o) ||
                      (|sldu_result_gnt_i) || (|sldu_result_final_gnt_i);
        if (slide_event || (&slide_debug_quiet_q)) begin
          $display("[ARA_SLDU_STATE] t=%0t issue_id=%0d issue_op=%0d commit_id=%0d commit_op=%0d q=%0d/%0d state=%0d->%0d issue=%0d->%0d commit=%0d->%0d in=%0d->%0d out=%0d->%0d vrf=%0d rq_cnt=%0d rp=%0d wp=%0d rq_valid=%b rq_bytes=%0d rq_id=%0d operand_v=%b operand_r=%b mask_v=%b mask_r=%0b mask=%h req=%b gnt=%b final=%b final_seen=%b",
                   $time, vinsn_issue_q.id, vinsn_issue_q.op,
                   vinsn_commit.id, vinsn_commit.op,
                   vinsn_queue_q.issue_cnt, vinsn_queue_q.commit_cnt,
                   state_q, state_d,
                   issue_cnt_q, issue_cnt_d, commit_cnt_q, commit_cnt_d,
                   in_pnt_q, in_pnt_d, out_pnt_q, out_pnt_d, vrf_pnt_q,
                   result_queue_cnt_q,
                   result_queue_read_pnt_q, result_queue_write_pnt_q,
                   result_queue_valid_q[result_queue_read_pnt_q],
                   result_queue_bytes_q[result_queue_read_pnt_q],
                   result_queue_q[result_queue_read_pnt_q][0].id,
                   sldu_operand_valid, sldu_operand_ready, mask_valid_q,
                   mask_ready_d, mask_q, sldu_result_req_o,
                   sldu_result_gnt_i, sldu_result_final_gnt_i,
                   result_final_gnt_q);
          slide_debug_quiet_q <= '0;
        end else begin
          slide_debug_quiet_q <= slide_debug_quiet_q + 1'b1;
        end
      end else begin
        slide_debug_quiet_q <= '0;
      end

      if (|pe_resp.vinsn_done)
        $display("[ARA_SLDU_DONE] t=%0t done=%b commit_cnt=%0d queue_commit=%0d",
                 $time, pe_resp.vinsn_done, commit_cnt_d,
                 vinsn_queue_d.commit_cnt);
    end else if ($test$plusargs("ARA_DEBUG_REDUCTION")) begin
      if (pe_req_valid_i && pe_req_ready_o &&
          pe_req_i.op inside {[VREDSUM:VWREDSUM], [VFREDUSUM:VFWREDOSUM]}) begin
        $display("[ARA_SLDU_RED_ACCEPT] t=%0t id=%0d op=%0d vfu=%0d vl=%0d q=%0d/%0d running=%b",
                 $time, pe_req_i.id, pe_req_i.op, pe_req_i.vfu, pe_req_i.vl,
                 vinsn_queue_q.issue_cnt, vinsn_queue_q.commit_cnt,
                 vinsn_running_q);
      end

      if ((vinsn_issue_valid_q &&
           vinsn_issue_q.op inside {[VREDSUM:VWREDSUM], [VFREDUSUM:VFWREDOSUM]}) ||
          (vinsn_queue_q.issue_cnt != '0 && state_q == SLIDE_IDLE)) begin
        $display("[ARA_SLDU_RED_STATE] t=%0t id=%0d op=%0d vfu=%0d valid=%0b state=%0d->%0d q=%0d/%0d oor=%0b operand=%b/%b rq=%0d",
                 $time, vinsn_issue_q.id, vinsn_issue_q.op, vinsn_issue_q.vfu,
                 vinsn_issue_valid_q, state_q, state_d,
                 vinsn_queue_q.issue_cnt, vinsn_queue_q.commit_cnt,
                 slide_down_source_oor, sldu_operand_valid,
                 sldu_operand_ready, result_queue_cnt_q);
      end
    end else begin
      slide_debug_quiet_q <= '0;
    end

    if (rst_ni && $test$plusargs("ARA_DEBUG_VFREDOSUM_SLDU")) begin
      if (pe_req_valid_i && pe_req_i.op == VFREDOSUM) begin
        $display("[ARA_VFREDOSUM_SLDU_INPUT] %m t=%0t id=%0d ready=%0b full=%0b local_q=%0b local_d=%0b global=%0b q=%0d/%0d",
                 $time, pe_req_i.id, pe_req_ready_o, vinsn_queue_full,
                 vinsn_running_q[pe_req_i.id], vinsn_running_d[pe_req_i.id],
                 pe_vinsn_running_i[pe_req_i.id],
                 vinsn_queue_q.issue_cnt, vinsn_queue_q.commit_cnt);
      end
      if (pe_req_valid_i && pe_req_ready_o && pe_req_i.op == VFREDOSUM) begin
        $display("[ARA_VFREDOSUM_SLDU_ACCEPT] %m t=%0t id=%0d vl=%0d vstart=%0d q=%0d/%0d",
                 $time, pe_req_i.id, pe_req_i.vl, pe_req_i.vstart,
                 vinsn_queue_q.issue_cnt, vinsn_queue_q.commit_cnt);
      end
      if (vinsn_issue_valid_q && vinsn_issue_q.op == VFREDOSUM &&
          ((state_q != state_d) || (issue_cnt_q != issue_cnt_d) ||
           (|sldu_operand_ready) || (|sldu_red_valid_o) ||
           (|sldu_result_gnt_i))) begin
        $display("[ARA_VFREDOSUM_SLDU] %m t=%0t id=%0d vl=%0d state=%0d->%0d issue=%0d->%0d operand=%b/%b rq=%0d:%b red=%b gnt=%b",
                 $time, vinsn_issue_q.id, vinsn_issue_q.vl, state_q, state_d,
                 issue_cnt_q, issue_cnt_d, sldu_operand_valid,
                 sldu_operand_ready, result_queue_cnt_q,
                 result_queue_valid_q[result_queue_read_pnt_q],
                 sldu_red_valid_o, sldu_result_gnt_i);
      end
    end

    if (rst_ni && $test$plusargs("ARA_DEBUG_LAYOUT428_DATA")) begin
      if (pe_req_valid_i && pe_req_ready_o && pe_req_i.vd == 5'd4 &&
          pe_req_i.vs2 == 5'd4 && pe_req_i.vl == 128) begin
        $display("[ARA_LAYOUT428_SLDU_ACCEPT] %m t=%0t id=%0d op=%0d vfu=%0d vsew=%0d stride=%0d",
                 $time, pe_req_i.id, pe_req_i.op, pe_req_i.vfu,
                 pe_req_i.vtype.vsew, pe_req_i.stride);
      end
      if (vinsn_issue_valid_q && vinsn_issue_q.vd == 5'd4 &&
          vinsn_issue_q.vs2 == 5'd4 && vinsn_issue_q.vl == 128 &&
          ((|sldu_operand_ready) || (|sldu_result_req_o))) begin
        $display("[ARA_LAYOUT428_SLDU_DATA] %m t=%0t id=%0d state=%0d op_v=%b op_r=%b in=%h out=%h req=%b",
                 $time, vinsn_issue_q.id, state_q, sldu_operand_valid,
                 sldu_operand_ready, sldu_operand, sld_op_dst,
                 sldu_result_req_o);
      end
    end

  end

`endif

endmodule: sldu
