// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// This unit generates transactions on the AR/AW buses, upon receiving vector
// memory operations.

module addrgen import ara_pkg::*; import rvv_pkg::*; #(
    parameter int  unsigned NrLanes      = 0,
    parameter int  unsigned VLEN         = 0,
    // AXI Interface parameters
    parameter int  unsigned AxiDataWidth = 0,
    parameter int  unsigned AxiAddrWidth = 0,
    parameter type          axi_ar_t     = logic,
    parameter type          axi_aw_t     = logic,
    parameter  type         pe_req_t     = logic,
    parameter  type         pe_resp_t    = logic,
    // CVA6 configuration
    parameter  config_pkg::cva6_cfg_t CVA6Cfg = cva6_config_pkg::cva6_cfg,
    parameter  type         exception_t  = logic,
    // Dependant parameters. DO NOT CHANGE!
    localparam type         axi_addr_t   = logic [AxiAddrWidth-1:0],
    localparam type         vlen_t       = logic[$clog2(VLEN+1)-1:0]
  ) (
    input  logic                           clk_i,
    input  logic                           rst_ni,
    // Memory interface
    output axi_ar_t                        axi_ar_o,
    output logic                           axi_ar_valid_o,
    input  logic                           axi_ar_ready_i,
    output axi_aw_t                        axi_aw_o,
    output logic                           axi_aw_valid_o,
    input  logic                           axi_aw_ready_i,
    input  logic                           axi_w_valid_i,
    // CSR input
    input  logic                           en_ld_st_translation_i,
    // Interface with CVA6's sv39 MMU
    // This is everything the MMU can provide, it might be overcomplete for Ara and some signals be useless
    output logic                           mmu_misaligned_ex_o,
    output logic                           mmu_req_o,        // request address translation
    output logic [CVA6Cfg.VLEN-1:0]        mmu_vaddr_o,      // virtual address out
    output logic                           mmu_is_store_o,   // the translation is requested by a store
    // if we need to walk the page table we can't grant in the same cycle
    // Cycle 0
    input logic                            mmu_dtlb_hit_i,   // sent in the same cycle as the request if translation hits in the DTLB
    input logic [CVA6Cfg.PPNW-1:0]         mmu_dtlb_ppn_i,   // ppn (send same cycle as hit)
    // Cycle 1
    input  logic                           mmu_valid_i,      // translation is valid
    input  logic [CVA6Cfg.PLEN-1:0]        mmu_paddr_i,      // translated address
    input  exception_t                     mmu_exception_i,  // address translation threw an exception
    // Interace with the dispatcher
    input  logic                           core_st_pending_i,
    // Interface with the main sequencer
    input  pe_req_t                        pe_req_i,
    input  logic                           pe_req_valid_i,
    input  logic     [NrVInsn-1:0]         pe_vinsn_running_i,
    output exception_t                     addrgen_exception_o,
    output logic                           addrgen_ack_o,
    output vlen_t                          addrgen_exception_vstart_o,
    output logic                           addrgen_fof_exception_o, // fault-only-first
    output logic                           addrgen_illegal_load_o,
    output logic                           addrgen_illegal_store_o,
    // Interface with the load/store units
    output addrgen_axi_req_t               ldu_axi_addrgen_req_o,
    output logic                           ldu_axi_addrgen_req_valid_o,
    input  logic                           ldu_axi_addrgen_req_ready_i,
    output addrgen_axi_req_t               stu_axi_addrgen_req_o,
    output logic                           stu_axi_addrgen_req_valid_o,
    input  logic                           stu_axi_addrgen_req_ready_i,
    //prefetch
    output logic                           prefetch_axi_ar_hit_o,
    // Stream-break recovery: pulse to flush the vldu prefetch R buffer in lockstep
    // with this addrgen's lookup FIFO when the demand stream resets (re-stream) and
    // the buffered prefetches become stale.  Only pulsed when no prefetch is in
    // flight (ROB empty + 0 in-flight beats), so it never races landing R beats.
    output logic                           prefetch_buf_flush_o,
    output axi_ar_t                        axi_addrgen_prefetch_req_o,
    output vlen_t                          prefetch_logical_bytes_o,
    output logic                           axi_addrgen_prefetch_req_valid_o,
    input  logic                           axi_addrgen_prefetch_req_ready_i,
    // Resident occupancy of the vldu prefetch R buffer, in 256-bit words.
    // Feeds the prefetch credit flow control (see PrefetchBufBeats).
    input  logic [7:0]                     prefetch_buf_occupancy_i,
    // Same-id order tag (is_prefetch per accepted AR) -> vldu R-beat demux.
    output logic                           prefetch_tag_head_o,
    output logic                           prefetch_tag_empty_o,
    input  logic                           prefetch_tag_pop_i,
    input  logic                           prefetch_buf_busy_i,
    // High while the store unit has a vector store instruction in flight. Used to
    // gate the prefetch's inter-iteration drain ONLY when a store is actually stuck.
    input  logic                           store_pending_i,
    input  logic                           block_load_addr_i,
    input  logic                           hdv_loop_active_i,
    input  logic                           hdv_task_end_i,
    output logic                           prefetch_task_clean_o,
    // Interface with the lanes (for scatter/gather operations)
    input  elen_t            [NrLanes-1:0] addrgen_operand_i,
    input  logic             [NrLanes-1:0] addrgen_operand_valid_i,
    output logic                           addrgen_operand_ready_o,
    // Indexed LSU exception support
    input  logic                           lsu_ex_flush_i
  );

  typedef enum logic [2:0] {
  PF_EN_1X = 3'b000,
  PF_EN_2X = 3'b001,
  PF_EN_4X = 3'b010,
  PF_EN_8X = 3'b011,
  PF_DEN   = 3'b100
  } pf_info;

  pf_info     prefetch_info;
  logic [1:0] prefetch_mul;
  logic       prefetch_en;

  // HDV prefetch hint from the request metadata. A loop-active falling edge
  // suppresses new generation for that cycle; task-end performs the precise
  // queue/ROB/buffer cleanup after accepted memory traffic has drained.
  logic loop_active_q;
  wire  loop_active_fall = loop_active_q && !hdv_loop_active_i;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) loop_active_q <= 1'b0;
    else         loop_active_q <= hdv_loop_active_i;
  end

  // ── Stream-break prefetch recovery ──────────────────────────────────────────
  // A demand load whose address does not match the lookup-FIFO head (FIFO non-
  // empty) means the demand stream diverged from the prefetch order — e.g. a GEMM
  // that re-streams the same B rows each row-block leaves an over-prefetched tail
  // (B[N], one past the stream) stuck at the head, which never matches again and
  // clogs the FIFO (every later demand misses).  On such a break, stop issuing new
  // prefetch, wait until everything in flight has landed (ROB empty + 0 in-flight
  // beats), then flush the lookup FIFO AND the vldu buffer in the same cycle (both
  // hold only COMPLETED data at that point, so the flush is race-free).
  logic stream_break;        // demand diverged from the prefetch FIFO order
  logic flush_pending_q;     // a break was seen; draining before the flush
  logic prefetch_flush_now;  // do the flush this cycle (drain complete)
  logic prefetch_demand_path_idle;
  logic task_end_cleaned_q;
  assign prefetch_buf_flush_o = prefetch_flush_now;
  // prefetch_flush_now / flush_pending_q logic is below, after the in-flight and
  // ROB-empty signals it depends on are declared.

  always_comb begin
    // A valid hint with disable=0 enables prefetch.  mode 00/01/10/11 maps to
    // 1X/2X/4X/8X; no hint and explicit disable both leave prefetch off, but the
    // two cases remain distinguishable in pe_req for debug/accounting.
    unique case (pe_req_d.hdv_meta.prefetch_mode)
      2'b00:   prefetch_info = PF_EN_1X;
      2'b01:   prefetch_info = PF_EN_2X;
      2'b10:   prefetch_info = PF_EN_4X;
      2'b11:   prefetch_info = PF_EN_8X;
      default: prefetch_info = PF_DEN;
    endcase
    if (!pe_req_d.hdv_meta.prefetch_hint_valid || pe_req_d.hdv_meta.prefetch_disable)
      prefetch_info = PF_DEN;
    // Do not create speculative work while a loop edge or task end is observed.
    if (loop_active_fall || hdv_task_end_i) prefetch_info = PF_DEN;
`ifdef HDV_ABLATION_NO_PREFETCH
    prefetch_info = PF_DEN;
`endif
    case (prefetch_info)
      PF_EN_1X: {prefetch_en, prefetch_mul} = {1'b1, 2'd0};
      PF_EN_2X: {prefetch_en, prefetch_mul} = {1'b1, 2'd1};
      PF_EN_4X: {prefetch_en, prefetch_mul} = {1'b1, 2'd2};
      PF_EN_8X: {prefetch_en, prefetch_mul} = {1'b1, 2'd3};
      default:  {prefetch_en, prefetch_mul} = {1'b0, 2'd0};
    endcase
  end

  localparam unsigned DataWidth = $bits(elen_t);
  localparam unsigned DataWidthB = DataWidth / 8;

  // Prefetch-buffer credit flow control (replaces the old static LMUL guard).
  // Capacity = vldu PrefetchQueueDepth(64 256-bit words) x 2 AXI beats/word =
  // 128 beats. Keep in sync with vldu.sv PrefetchQueueDepth. A prefetch AR is
  // only issued when (already-buffered beats + in-flight beats + this burst)
  // stays within this budget, so every prefetch R beat is guaranteed buffer
  // room when it lands and can never back-pressure a demand beat on the shared
  // R channel into deadlock -- for ANY LMUL and ANY number of load streams K.
  // Over-budget bursts simply wait (or the loop runs demand-only), never wedge.
  localparam int unsigned PrefetchBufBeats = 128;
  // Store-aware BOUNDED-LEAD prefetch budget. A fixed 32-beat allowance covers
  // two e32/m1 streams but can collapse a 3+ stream distance-1 pipeline before
  // every stream has one future request resident. Track a small set of static
  // load stream IDs and grant 16 beats per active stream, with the established
  // 32-beat floor for one/two-stream loops and a 96-beat ceiling that always
  // leaves part of the 128-beat buffer budget for demand/store progress.
  localparam int unsigned PrefetchBaseLeadBeats = 32;
  localparam int unsigned PrefetchLeadPerStream = 16;
  localparam int unsigned PrefetchMaxLeadBeats  = 96;
  localparam int unsigned PrefetchTrackedStreams = 8;
  localparam int unsigned PrefetchBadThresh = 4;
  // Keep a few completed/in-flight prefetch address slots free.  The data-buffer
  // credit below bounds beats, but dense multi-stream kernels can fill the
  // lookup FIFO with many small bursts before the beat budget is exhausted.
  // Once lookup is full, completed prefetches cannot retire from the ROB, so a
  // stream-break flush can wait forever for "in-flight" work that already landed.
  localparam int unsigned PrefetchLookupEntryReserve = 1;
  localparam int unsigned PrefetchBeatCountWidth =
      $clog2(PrefetchBufBeats + 1);
  localparam int unsigned PrefetchLeadCalcWidth =
      $clog2((PrefetchTrackedStreams * PrefetchLeadPerStream) + 1);


  // In-flight prefetch beats: issued (ROB-pushed) but not yet landed in the
  // buffer (ROB-popped on the burst's last R beat). Added to the vldu's
  // resident occupancy to get the total beats committed to the buffer.
  logic [PrefetchBeatCountWidth-1:0]
      prefetch_inflight_beats_d, prefetch_inflight_beats_q;
  logic [3:0] prefetch_bad_cnt_d, prefetch_bad_cnt_q;
  logic       prefetch_adaptive_throttle;
  logic [$clog2((2 * VaddrgenInsnQueueDepth) + 1)-1:0] prefetch_lookup_entry_use;
  logic [$clog2(VaddrgenInsnQueueDepth + 1)-1:0] prefetch_lookup_valid_use;
  logic       prefetch_lookup_entry_credit;
  assign prefetch_adaptive_throttle = (prefetch_bad_cnt_q >= PrefetchBadThresh[3:0]);

  localparam unsigned Log2NrLanes = $clog2(NrLanes);
  localparam unsigned Log2LaneWordWidthB = $clog2(DataWidthB/1);
  localparam unsigned Log2LaneWordWidthH = $clog2(DataWidthB/2);
  localparam unsigned Log2LaneWordWidthS = $clog2(DataWidthB/4);
  localparam unsigned Log2LaneWordWidthD = $clog2(DataWidthB/8);
  localparam unsigned Log2VRFWordWidthB = Log2NrLanes + Log2LaneWordWidthB;
  localparam unsigned Log2VRFWordWidthH = Log2NrLanes + Log2LaneWordWidthH;
  localparam unsigned Log2VRFWordWidthS = Log2NrLanes + Log2LaneWordWidthS;
  localparam unsigned Log2VRFWordWidthD = Log2NrLanes + Log2LaneWordWidthD;

  // Ara reports misaligned exceptions on its own
  assign mmu_misaligned_ex_o  = '0;

  import cf_math_pkg::idx_width;
  import axi_pkg::aligned_addr;
  import axi_pkg::BURST_INCR;
  import axi_pkg::CACHE_MODIFIABLE;

  // Check if the address is aligned to a particular width
  // Max element width: 8 bytes
  function automatic logic is_addr_error(axi_addr_t addr, logic [1:0] vew);
    // log2(MAX_ELEMENT_WIDTH_BYTE)
    localparam LOG2_MAX_SEW_BYTE = 3;
    typedef logic [LOG2_MAX_SEW_BYTE:0] max_sew_byte_t;

    is_addr_error = |(max_sew_byte_t'(addr[LOG2_MAX_SEW_BYTE-1:0]) & (max_sew_byte_t'(1 << vew) - 1));
  endfunction // is_addr_error

  ////////////////////////////
  //  Register the request  //
  ////////////////////////////

  `include "common_cells/registers.svh"
  // STU exception support
  logic lsu_ex_flush_d;
  `FF(lsu_ex_flush_d, lsu_ex_flush_i, 1'b0, clk_i, rst_ni);


  // Don't accept the same request more than once!
  // The main sequencer keeps the valid high and broadcast
  // a certain instruction with ID == X to all the lanes
  // until every lane has sampled it.

  // Every time a lane handshakes the main sequencer, it also
  // saves the insn ID, not to re-sample the same instruction.
  vid_t last_id_d, last_id_q;
  logic pe_req_valid_i_msk;
  logic en_sync_mask_d, en_sync_mask_q;

  pe_req_t pe_req, pe_req_fifo_data;
  pe_req_t pe_req_stage_d, pe_req_stage_q;
  pe_req_t pe_req_d, pe_req_q;
  axi_addr_t pe_req_unit_stride_addr_stage_d;
  axi_addr_t pe_req_unit_stride_addr_stage_q;
  logic    pe_req_valid;
  logic    pe_req_stage_valid_d, pe_req_stage_valid_q;
  logic    pe_req_stage_consume;
  logic    addrgen_ack;
  logic    pe_req_fifo_full;
  logic    pe_req_fifo_empty;
  logic    pe_req_fifo_push;
  logic    pe_req_fifo_pop;

  assign pe_req_fifo_push = pe_req_valid_i_msk && !pe_req_fifo_full;
  assign pe_req_fifo_pop  = (!pe_req_stage_valid_q || pe_req_stage_consume) &&
                            !pe_req_fifo_empty;
  assign addrgen_ack_o    = !pe_req_fifo_full;
  assign pe_req_valid     = pe_req_stage_valid_q;
  assign pe_req           = pe_req_stage_q;

  fifo_v3 #(
    .dtype(pe_req_t),
    .DEPTH(VaddrgenInsnQueueDepth)
  ) i_pe_req_register (
    .clk_i     (clk_i             ),
    .rst_ni    (rst_ni            ),
    .flush_i   (lsu_ex_flush_d    ),
    .testmode_i(1'b0              ),
    .data_i    (pe_req_i          ),
    .push_i    (pe_req_fifo_push  ),
    .full_o    (pe_req_fifo_full  ),
    .data_o    (pe_req_fifo_data  ),
    .pop_i     (pe_req_fifo_pop   ),
    .empty_o   (pe_req_fifo_empty ),
    .usage_o   (/* Unused */      )
  );

  // Register the FIFO head before address and prefetch generation.  The fifo_v3
  // head is selected by its read pointer; using it directly made that pointer
  // feed the stride, page-cross and burst-length cones in the same cycle.  This
  // elastic stage can consume and refill on one edge, so queued requests retain
  // one-request-per-cycle handoff while the FIFO pointer is removed from those
  // arithmetic paths.
  always_comb begin : p_pe_req_stage
    pe_req_stage_d                  = pe_req_stage_q;
    pe_req_unit_stride_addr_stage_d = pe_req_unit_stride_addr_stage_q;
    pe_req_stage_valid_d            = pe_req_stage_valid_q;

    if (pe_req_stage_consume) begin
      pe_req_stage_valid_d = 1'b0;
    end
    if (pe_req_fifo_pop) begin
      pe_req_stage_d = pe_req_fifo_data;
      pe_req_unit_stride_addr_stage_d =
          pe_req_fifo_data.scalar_op +
          (pe_req_fifo_data.vstart <<
           unsigned'(pe_req_fifo_data.vtype.vsew));
      pe_req_stage_valid_d = 1'b1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_pe_req_stage_regs
    if (!rst_ni) begin
      pe_req_stage_q                  <= '0;
      pe_req_unit_stride_addr_stage_q <= '0;
      pe_req_stage_valid_q            <= 1'b0;
    end else if (lsu_ex_flush_d) begin
      pe_req_stage_q                  <= '0;
      pe_req_unit_stride_addr_stage_q <= '0;
      pe_req_stage_valid_q            <= 1'b0;
    end else begin
      pe_req_stage_q                  <= pe_req_stage_d;
      pe_req_unit_stride_addr_stage_q <= pe_req_unit_stride_addr_stage_d;
      pe_req_stage_valid_q            <= pe_req_stage_valid_d;
    end
  end

  `ifdef FOR_VERIFY
  riscv::instruction_t vlsu_addrgen_instr;
  assign vlsu_addrgen_instr = riscv::instruction_t'(pe_req.instr) & {$bits(pe_req.instr){pe_req_valid}};
  `endif

  always_comb begin
    // Default assignment
    last_id_d      = last_id_q;
    en_sync_mask_d = en_sync_mask_q;

    // If the sync mask is enabled and the ID is the same
    // as before, avoid to re-sample the same instruction
    // more than once.
    if ((en_sync_mask_q && (pe_req_i.id == last_id_q)) || !(pe_req_i.op inside {VLE, VSE, VLSE, VSSE, VLXE, VSXE}))
      pe_req_valid_i_msk = 1'b0;
    else
      pe_req_valid_i_msk = pe_req_valid_i;

    // Enable the sync mask when a handshake happens,
    // and save the insn ID
    if (pe_req_valid_i_msk && addrgen_ack_o) begin
      last_id_d      = pe_req_i.id;
      en_sync_mask_d = 1'b1;
    end

    // Disable the block if the sequencer valid goes down
    if (!pe_req_valid_i && en_sync_mask_q)
      en_sync_mask_d = 1'b0;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      last_id_q      <= '0;
      en_sync_mask_q <= 1'b0;
    end else begin
      last_id_q      <= last_id_d;
      en_sync_mask_q <= en_sync_mask_d;
    end
  end

  /////////////////////
  //  Address Queue  //
  /////////////////////
  // Address queues for the vector load/store units
  addrgen_axi_req_t axi_addrgen_queue;
  logic             axi_addrgen_queue_push;
  logic             axi_addrgen_queue_full;

  addrgen_axi_req_t ldu_axi_addrgen_queue_data;
  logic             ldu_axi_addrgen_queue_push;
  logic             ldu_axi_addrgen_queue_full;

  addrgen_axi_req_t stu_axi_addrgen_queue_data;
  logic             stu_axi_addrgen_queue_push;
  logic             stu_axi_addrgen_queue_full;
  logic             stu_axi_addrgen_queue_valid;


  logic             ldu_axi_addrgen_queue_empty;
  logic             stu_axi_addrgen_queue_empty;

  fifo_v3 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(addrgen_axi_req_t     )
  ) i_ldu_addrgen_req_queue (
    .clk_i     (clk_i                                                    ),
    .rst_ni    (rst_ni                                                   ),
    .flush_i   (lsu_ex_flush_d                                           ),
    .testmode_i(1'b0                                                     ),
    .data_i    (ldu_axi_addrgen_queue_data                               ),
    .push_i    (ldu_axi_addrgen_queue_push                               ),
    .full_o    (ldu_axi_addrgen_queue_full                               ),
    .data_o    (ldu_axi_addrgen_req_o                                    ),
    .pop_i     (ldu_axi_addrgen_req_ready_i && !ldu_axi_addrgen_queue_empty),
    .empty_o   (ldu_axi_addrgen_queue_empty                              ),
    .usage_o   (/* Unused */                                             )
  );

  fifo_v3 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(addrgen_axi_req_t     )
  ) i_stu_addrgen_req_queue (
    .clk_i     (clk_i                                                    ),
    .rst_ni    (rst_ni                                                   ),
    .flush_i   (lsu_ex_flush_d                                           ),
    .testmode_i(1'b0                                                     ),
    .data_i    (stu_axi_addrgen_queue_data                               ),
    .push_i    (stu_axi_addrgen_queue_push                               ),
    .full_o    (stu_axi_addrgen_queue_full                               ),
    .data_o    (stu_axi_addrgen_req_o                                    ),
    .pop_i     (stu_axi_addrgen_req_ready_i && !stu_axi_addrgen_queue_empty),
    .empty_o   (stu_axi_addrgen_queue_empty                              ),
    .usage_o   (/* Unused */                                             )
  );

  assign ldu_axi_addrgen_req_valid_o = !ldu_axi_addrgen_queue_empty;
  assign stu_axi_addrgen_req_valid_o = !stu_axi_addrgen_queue_empty;

  assign ldu_axi_addrgen_queue_data = axi_addrgen_queue;
  assign stu_axi_addrgen_queue_data = axi_addrgen_queue;

  /////////////////////////////
  //  Prefetch AXI AR Queue  //
  /////////////////////////////
  logic    prefetch_axi_ar_hit;
  logic    prefetch_pending_d;
  axi_ar_t prefetch_axi_ar_queue_datain, prefetch_axi_ar_data;
  logic    prefetch_axi_ar_queue_push, prefetch_axi_ar_queue_pop;
  logic    prefetch_axi_ar_queue_cancel;
  logic    prefetch_axi_ar_queue_valid;
  logic    prefetch_axi_ar_queue_not_full;
  logic    prefetch_axi_ar_queue_full;
  logic    prefetch_axi_ar_queue_empty;
  logic    prefetch_axi_ar_queue_push_safe;
  logic    prefetch_axi_ar_queue_pop_safe;
  hdv_pf_stream_id_t prefetch_stream_queue_datain, prefetch_stream_at_issue;
  logic              prefetch_stream_queue_full, prefetch_stream_queue_empty;
  vlen_t              prefetch_bytes_queue_datain, prefetch_bytes_at_issue;
  logic               prefetch_bytes_queue_full, prefetch_bytes_queue_empty;
  hdv_pf_stream_id_t prefetch_active_stream_id_q[PrefetchTrackedStreams];
  logic [PrefetchTrackedStreams-1:0] prefetch_active_stream_vld_q;
  logic [$clog2(PrefetchTrackedStreams + 1)-1:0] prefetch_active_stream_count_q;
  logic prefetch_stream_track_seen, prefetch_stream_track_free;
  logic [$clog2(PrefetchTrackedStreams)-1:0] prefetch_stream_track_free_idx;
  logic [PrefetchLeadCalcWidth-1:0] prefetch_lead_beats;

  typedef struct packed {
    axi_addr_t         addr;
    vlen_t             logical_bytes;
    hdv_pf_stream_id_t stream_id;
  } prefetch_lookup_t;

  assign prefetch_axi_ar_queue_push_safe = prefetch_axi_ar_queue_push &&
                                           !prefetch_axi_ar_queue_full;
  assign prefetch_axi_ar_queue_pop_safe  =
      (prefetch_axi_ar_queue_pop || prefetch_axi_ar_queue_cancel) &&
      !prefetch_axi_ar_queue_empty;
  assign prefetch_axi_ar_queue_not_full  = !prefetch_axi_ar_queue_full;
  assign prefetch_axi_ar_queue_valid     = !prefetch_axi_ar_queue_empty;

  always_comb begin
    prefetch_stream_track_seen     = 1'b0;
    prefetch_stream_track_free     = 1'b0;
    prefetch_stream_track_free_idx = '0;
    for (int unsigned i = 0; i < PrefetchTrackedStreams; i++) begin
      if (prefetch_active_stream_vld_q[i] &&
          (prefetch_active_stream_id_q[i] == prefetch_stream_queue_datain)) begin
        prefetch_stream_track_seen = 1'b1;
      end
      if (!prefetch_active_stream_vld_q[i] && !prefetch_stream_track_free) begin
        prefetch_stream_track_free     = 1'b1;
        prefetch_stream_track_free_idx = i;
      end
    end

    prefetch_lead_beats = PrefetchBaseLeadBeats;
    if (prefetch_active_stream_count_q > 2) begin
      prefetch_lead_beats =
          PrefetchLeadCalcWidth'(prefetch_active_stream_count_q) *
          PrefetchLeadPerStream;
      if (prefetch_lead_beats > PrefetchMaxLeadBeats)
        prefetch_lead_beats = PrefetchMaxLeadBeats;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni || lsu_ex_flush_d || prefetch_flush_now || hdv_task_end_i) begin
      prefetch_active_stream_vld_q   <= '0;
      prefetch_active_stream_count_q <= '0;
      for (int unsigned i = 0; i < PrefetchTrackedStreams; i++) begin
        prefetch_active_stream_id_q[i] <= '0;
      end
    end else if (prefetch_axi_ar_queue_push_safe &&
                 !prefetch_stream_track_seen &&
                 prefetch_stream_track_free) begin
      prefetch_active_stream_vld_q[prefetch_stream_track_free_idx] <= 1'b1;
      prefetch_active_stream_id_q[prefetch_stream_track_free_idx]  <=
          prefetch_stream_queue_datain;
      prefetch_active_stream_count_q <= prefetch_active_stream_count_q + 1'b1;
    end
  end

  fifo_v3 #(
    .dtype(axi_ar_t),
    .DEPTH(VaddrgenInsnQueueDepth)
  ) i_prefetch_axi_ar_queue (
    .clk_i     (clk_i                         ),
    .rst_ni    (rst_ni                        ),
    .flush_i   (lsu_ex_flush_d | prefetch_flush_now),
    .testmode_i(1'b0                          ),
    .data_i    (prefetch_axi_ar_queue_datain  ),
    .push_i    (prefetch_axi_ar_queue_push_safe),
    .full_o    (prefetch_axi_ar_queue_full    ),
    .data_o    (prefetch_axi_ar_data          ),
    .pop_i     (prefetch_axi_ar_queue_pop_safe),
    .empty_o   (prefetch_axi_ar_queue_empty   ),
    .usage_o   (/* Unused */                  )
  );

  fifo_v3 #(
    .dtype(hdv_pf_stream_id_t),
    .DEPTH(VaddrgenInsnQueueDepth)
  ) i_prefetch_stream_queue (
    .clk_i     (clk_i                           ),
    .rst_ni    (rst_ni                          ),
    .flush_i   (lsu_ex_flush_d | prefetch_flush_now),
    .testmode_i(1'b0                            ),
    .data_i    (prefetch_stream_queue_datain    ),
    .push_i    (prefetch_axi_ar_queue_push_safe ),
    .full_o    (prefetch_stream_queue_full      ),
    .data_o    (prefetch_stream_at_issue        ),
    .pop_i     (prefetch_axi_ar_queue_pop_safe  ),
    .empty_o   (prefetch_stream_queue_empty     ),
    .usage_o   (/* Unused */                    )
  );

  fifo_v3 #(
    .dtype(vlen_t),
    .DEPTH(VaddrgenInsnQueueDepth)
  ) i_prefetch_bytes_queue (
    .clk_i     (clk_i                           ),
    .rst_ni    (rst_ni                          ),
    .flush_i   (lsu_ex_flush_d | prefetch_flush_now),
    .testmode_i(1'b0                            ),
    .data_i    (prefetch_bytes_queue_datain     ),
    .push_i    (prefetch_axi_ar_queue_push_safe ),
    .full_o    (prefetch_bytes_queue_full       ),
    .data_o    (prefetch_bytes_at_issue         ),
    .pop_i     (prefetch_axi_ar_queue_pop_safe  ),
    .empty_o   (prefetch_bytes_queue_empty      ),
    .usage_o   (/* Unused */                    )
  );

  assign prefetch_axi_ar_hit_o = prefetch_axi_ar_hit;

  ///////////////////////////
  //  Prefetch AXI AR ROB  //
  ///////////////////////////
  axi_ar_t prefetch_axi_ar_rob_datain, prefetch_axi_ar_rob_data;
  logic    prefetch_axi_ar_rob_push;
  logic    prefetch_axi_ar_rob_pop;
  logic    prefetch_axi_ar_rob_full;
  logic    prefetch_axi_ar_rob_empty;
  // Recovery flush: wait until demand-side vector memory work, every prefetch
  // return, and any VLDu hit consumption have drained. Then clear queued,
  // lookup, and buffered prefetch state together.
  assign prefetch_flush_now =
      (flush_pending_q || (hdv_task_end_i && !task_end_cleaned_q))
                           && (prefetch_inflight_beats_q == '0)
                           && prefetch_axi_ar_rob_empty
                           && prefetch_tag_empty_o
                           && !prefetch_buf_busy_i
                           && prefetch_demand_path_idle;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni)                 flush_pending_q <= 1'b0;
    else if (prefetch_flush_now) flush_pending_q <= 1'b0;
    else if (stream_break || lsu_ex_flush_d ||
             (hdv_task_end_i && !task_end_cleaned_q))
                                    flush_pending_q <= 1'b1;
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni)                    task_end_cleaned_q <= 1'b0;
    else if (!hdv_task_end_i)       task_end_cleaned_q <= 1'b0;
    else if (prefetch_flush_now)    task_end_cleaned_q <= 1'b1;
  end
  prefetch_lookup_t prefetch_axi_addr_lookup_fifo_datain, prefetch_axi_addr_lookup_fifo_data;
  logic      prefetch_axi_addr_lookup_fifo_push;
  logic      prefetch_axi_addr_lookup_fifo_pop;
  logic      prefetch_axi_addr_lookup_fifo_full;
  logic      prefetch_axi_addr_lookup_fifo_empty;
  prefetch_lookup_t prefetch_axi_addr_lookup_fifo_mem[VaddrgenInsnQueueDepth];
  localparam int unsigned PrefetchLookupPtrWidth =
      (VaddrgenInsnQueueDepth > 1) ? $clog2(VaddrgenInsnQueueDepth) : 1;
  logic [VaddrgenInsnQueueDepth-1:0] prefetch_lookup_slot_valid_q;
  logic [PrefetchLookupPtrWidth-1:0] prefetch_lookup_wr_ptr_q;
  logic [PrefetchLookupPtrWidth-1:0] prefetch_lookup_rd_ptr_q;
  
  axi_ar_t   prefetch_axi_ar_rob_mem[VaddrgenInsnQueueDepth];
  logic      prefetch_axi_ar_rob_vld[VaddrgenInsnQueueDepth];
  logic      prefetch_axi_ar_rob_match;
  logic      prefetch_axi_ar_queue_match;
  logic      prefetch_queue_hard_resources_ready;
  logic      prefetch_queue_speculative_issue_allowed;
  logic      prefetch_queue_issue_resources_ready;
  logic      prefetch_queue_promote;
  logic      prefetch_wait_match;
  logic      prefetch_lookup_match;
  logic      prefetch_lookup_head_match;
  logic      prefetch_lookup_head_future_near;
  axi_addr_t prefetch_lookup_head_delta;
  logic      prefetch_lookup_head_same_stream;

  // Static load-PC provenance and the logical byte footprint follow every
  // prefetch AR in lockstep. Exact address + footprint is the data-hit key, so
  // unrolled copies of one logical stream may consume each other's prefetches.
  // Stream identity remains a recovery key for detecting divergence within one
  // static load without flushing useful entries owned by other loads.
  hdv_pf_stream_id_t prefetch_stream_rob_data;
  vlen_t              prefetch_bytes_rob_data;
  vlen_t              prefetch_bytes_rob_mem[VaddrgenInsnQueueDepth];

  fifo_v5 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(axi_ar_t              )
  ) i_prefetch_axi_ar_rob (
    .clk_i     (clk_i                    ),
    .rst_ni    (rst_ni                   ),
    .flush_i   (1'b0                     ),
    .testmode_i(1'b0                     ),
    .data_i    (prefetch_axi_ar_rob_datain ),
    .push_i    (prefetch_axi_ar_rob_push ),
    .full_o    (prefetch_axi_ar_rob_full ),
    .data_o    (prefetch_axi_ar_rob_data ),
    .pop_i     (prefetch_axi_ar_rob_pop  ),
    .empty_o   (prefetch_axi_ar_rob_empty),
    .mem_o     (prefetch_axi_ar_rob_mem  ),
    .vld_o     (prefetch_axi_ar_rob_vld  ),
    .usage_o   (/* Unused */             )
  );

  fifo_v5 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(vlen_t                 )
  ) i_prefetch_bytes_rob (
    .clk_i     (clk_i                       ),
    .rst_ni    (rst_ni                      ),
    .flush_i   (1'b0                        ),
    .testmode_i(1'b0                        ),
    .data_i    (prefetch_bytes_at_issue     ),
    .push_i    (prefetch_axi_ar_rob_push    ),
    .full_o    (                            ),
    .data_o    (prefetch_bytes_rob_data     ),
    .pop_i     (prefetch_axi_ar_rob_pop     ),
    .empty_o   (                            ),
    .mem_o     (prefetch_bytes_rob_mem      ),
    .vld_o     (                            ),
    .usage_o   (                            )
  );

  fifo_v5 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(hdv_pf_stream_id_t    )
  ) i_prefetch_stream_rob (
    .clk_i     (clk_i                       ),
    .rst_ni    (rst_ni                      ),
    .flush_i   (1'b0                        ),
    .testmode_i(1'b0                        ),
    .data_i    (prefetch_stream_at_issue    ),
    .push_i    (prefetch_axi_ar_rob_push    ),
    .full_o    (                            ),
    .data_o    (prefetch_stream_rob_data    ),
    .pop_i     (prefetch_axi_ar_rob_pop     ),
    .empty_o   (                            ),
    .mem_o     (                            ),
    .vld_o     (                            ),
    .usage_o   (                            )
  );

  assign axi_addrgen_prefetch_req_valid_o = !prefetch_axi_ar_rob_empty &&
                                            !prefetch_axi_addr_lookup_fifo_full;
  assign axi_addrgen_prefetch_req_o       = prefetch_axi_ar_rob_data;
  assign prefetch_logical_bytes_o         = prefetch_bytes_rob_data;
  assign prefetch_axi_ar_rob_pop          = axi_addrgen_prefetch_req_valid_o &&
                                            axi_addrgen_prefetch_req_ready_i;

  // ── Prefetch in-flight beat accounting (credit flow control) ──────────────
  // Beats issued to the AXI AR but not yet landed in the vldu buffer:
  //   +burst when a prefetch AR is issued (ROB push, prefetch_req below),
  //   -burst when its last R beat lands (ROB pop = prefetch_req_ready_i).
  // Combined with the vldu resident occupancy this bounds the beats committed
  // to the buffer; the issue gate uses it so landings can never overflow.
  always_comb begin
    prefetch_inflight_beats_d = prefetch_inflight_beats_q;
    if (prefetch_axi_ar_rob_push)
      prefetch_inflight_beats_d = prefetch_inflight_beats_d
                                + ($unsigned(prefetch_axi_ar_data.len) + 1);
    if (prefetch_axi_ar_rob_pop &&
        (prefetch_inflight_beats_d >= ($unsigned(prefetch_axi_ar_rob_data.len) + 1)))
      prefetch_inflight_beats_d = prefetch_inflight_beats_d
                                - ($unsigned(prefetch_axi_ar_rob_data.len) + 1);
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) prefetch_inflight_beats_q <= '0;
    else         prefetch_inflight_beats_q <= prefetch_inflight_beats_d;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) prefetch_bad_cnt_q <= '0;
    else         prefetch_bad_cnt_q <= prefetch_bad_cnt_d;
  end

  // "Wait per loop ITERATION" prefetch pacing. The application AVL decrements by one
  // vl each strip-mine iteration, so pe_req.avl is CONSTANT within an iteration and
  // CHANGES between iterations. While still in the current iteration (avl unchanged)
  // the prefetch issues freely -- feeding all of that iteration's load streams
  // (e.g. src1 + src2). When a NEW iteration begins (avl differs from the last
  // prefetched iteration) it must first wait for the PREVIOUS iteration's prefetch
  // beats to fully drain (in-flight == 0). That inter-iteration drain opens a window
  // where the single-port memory is free for demand STORES, so store-heavy vsaxpy no
  // longer starves -- and it adapts to each kernel's real iteration size (unlike a
  // fixed beat batch, which starved fdotp's larger loads).
  logic [$bits(pe_req_d.avl)-1:0] prefetch_iter_avl_d, prefetch_iter_avl_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) prefetch_iter_avl_q <= '0;
    else         prefetch_iter_avl_q <= prefetch_iter_avl_d;
  end

  // Store-stuck detector. store_pending_i is high while the store unit is working
  // on a vector store. A store that COMPLETES quickly (e.g. vvaddint32, writing a
  // separate array) keeps it high only briefly; a STARVED store (vsaxpy, whose
  // writes lose the single memory port to the prefetch read-flood) keeps it high
  // continuously. Counting the continuous-high cycles distinguishes the two: only
  // once it exceeds StoreStuckThresh do we treat the store as starved and let the
  // per-iteration prefetch drain kick in (freeing the bus for the store). Below the
  // threshold the prefetch runs free, so store-light loops pay no drain penalty.
  localparam int unsigned StoreStuckThresh = 32;
  logic [7:0] store_stuck_cnt_q;
  logic       store_stuck;
  assign store_stuck = (store_stuck_cnt_q >= StoreStuckThresh[7:0]);
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni)              store_stuck_cnt_q <= '0;
    else if (!store_pending_i) store_stuck_cnt_q <= '0;          // store drained -> reset
    else if (store_stuck_cnt_q != 8'hFF)
                              store_stuck_cnt_q <= store_stuck_cnt_q + 1'b1;
  end


  // Same-id redesign: per-AR is_prefetch ORDER TAG for the vldu R-beat demux.
  // Prefetch ARs now carry AXI_ID_DEMAND, so the AXI id can no longer tell a
  // prefetch R burst from a demand one. Push one tag per ACCEPTED AR (demand AND
  // prefetch) in bus-issue order; the vldu pops one per completed R burst to route
  // it. is_prefetch = the prefetch drain won the AR (prefetch_axi_ar_queue_pop).
  // AXI returns same-id bursts strictly in AR-issue order, so tag order == R order.
  // On a prefetch hit no AR is issued (axi_ar_valid_o=0) -> no phantom tag.
  // Depth >> max outstanding ARs (prefetch ROB + demand) so it never fills.
  logic prefetch_tag_full;
  fifo_v3 #(
    .DEPTH (16    ),
    .dtype (logic )
  ) i_prefetch_tag_fifo (
    .clk_i     (clk_i                           ),
    .rst_ni    (rst_ni                          ),
    .flush_i   (1'b0                            ),
    .testmode_i(1'b0                            ),
    .data_i    (prefetch_axi_ar_queue_pop       ), // 1 = prefetch drove this AR
    .push_i    (axi_ar_valid_o && axi_ar_ready_i), // one push per accepted AR
    .full_o    (prefetch_tag_full               ),
    .data_o    (prefetch_tag_head_o             ),
    .pop_i     (prefetch_tag_pop_i              ),
    .empty_o   (prefetch_tag_empty_o            ),
    .usage_o   (/* unused */                    )
  );



  fifo_v5 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(prefetch_lookup_t     )
  ) i_prefetch_axi_addr_lookup_fifo (
    .clk_i     (clk_i                      ),
    .rst_ni    (rst_ni                     ),
    .flush_i   (prefetch_flush_now         ),
    .testmode_i(1'b0                       ),
    .data_i    (prefetch_axi_addr_lookup_fifo_datain),
    .push_i    (prefetch_axi_addr_lookup_fifo_push ),
    .full_o    (prefetch_axi_addr_lookup_fifo_full ),
    .data_o    (prefetch_axi_addr_lookup_fifo_data ),
    .pop_i     (prefetch_axi_addr_lookup_fifo_pop  ),
    .empty_o   (prefetch_axi_addr_lookup_fifo_empty),
    .mem_o     (prefetch_axi_addr_lookup_fifo_mem  ),
    .vld_o     (/* Unused */                       ),
    .usage_o   (/* Unused */                       )
  );

  // fifo_v5 exposes per-slot valid bits, but its flush only resets pointers and
  // occupancy. Keep a local validity mirror whose epoch is explicitly cleared
  // with the lookup FIFO so non-head searches can never observe stale slots
  // after stream recovery or a task boundary.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni || prefetch_flush_now) begin
      prefetch_lookup_slot_valid_q <= '0;
      prefetch_lookup_wr_ptr_q     <= '0;
      prefetch_lookup_rd_ptr_q     <= '0;
    end else begin
      if (prefetch_axi_addr_lookup_fifo_push &&
          !prefetch_axi_addr_lookup_fifo_full) begin
        prefetch_lookup_slot_valid_q[prefetch_lookup_wr_ptr_q] <= 1'b1;
        prefetch_lookup_wr_ptr_q <= prefetch_lookup_wr_ptr_q + 1'b1;
      end
      if (prefetch_axi_addr_lookup_fifo_pop &&
          !prefetch_axi_addr_lookup_fifo_empty) begin
        prefetch_lookup_slot_valid_q[prefetch_lookup_rd_ptr_q] <= 1'b0;
        prefetch_lookup_rd_ptr_q <= prefetch_lookup_rd_ptr_q + 1'b1;
      end
    end
  end

  always_comb begin
    prefetch_lookup_entry_use = '0;
    prefetch_lookup_valid_use = '0;
    for (int unsigned i = 0; i < VaddrgenInsnQueueDepth; i++) begin
      prefetch_lookup_entry_use += prefetch_lookup_slot_valid_q[i];
      prefetch_lookup_entry_use += prefetch_axi_ar_rob_vld[i];
      prefetch_lookup_valid_use += prefetch_lookup_slot_valid_q[i];
    end
  end

  assign prefetch_lookup_entry_credit =
      ($unsigned(prefetch_lookup_entry_use) <=
       $unsigned(VaddrgenInsnQueueDepth - PrefetchLookupEntryReserve));

  //////////////////////////
  //  Indexed Memory Ops  //
  //////////////////////////

  // Support for indexed memory operations (scatter/gather)
  logic [$bits(elen_t)*NrLanes-1:0] shuffled_word;
  logic [$bits(elen_t)*NrLanes-1:0] deshuffled_word;
  elen_t                            reduced_word_d, reduced_word_q;
  elen_t                            idx_vaddr;
  logic                             idx_op_error_d, idx_op_error_q;
  vlen_t                            addrgen_exception_vstart_d;

  // Pointer to point to the correct
  logic [$clog2(NrLanes)-1:0]    word_lane_ptr_d, word_lane_ptr_q;
  logic [$clog2(DataWidthB)-1:0] elm_ptr_d, elm_ptr_q;
  logic [$clog2(DataWidthB)-1:0] last_elm_subw_d, last_elm_subw_q;

  //////////////////////////
  //  Address generation  //
  //////////////////////////
  exception_t mmu_exception_d, mmu_exception_q;
  logic       mmu_req_d;
  logic       last_translation_completed;
  logic       addrgen_fof_exception_d, addrgen_fof_exception_q;

  vlen_t     len_temp;
  axi_addr_t next_addr_strided_temp;

  // Running vector instructions
  logic [NrVInsn-1:0] vinsn_running_d, vinsn_running_q;

  // The Address Generator can be in one of the following three states.
  // IDLE: Waiting for a vector load/store instruction.
  // ADDRGEN: Generates a series of AXI requests from a vector instruction.
  // ADDRGEN_IDX_OP: Generates a series of AXI requests from a
  //    vector instruction, but reading a vector of offsets from Ara's lanes.
  //    This is used for scatter and gather operations.
  // WAIT_LAST_TRANSLATION: Wait for the last address translation to be acknowledged
  enum logic [2:0] {
    IDLE,
    ADDRGEN,
    ADDRGEN_IDX_OP,
    ADDRGEN_IDX_OP_END,
    WAIT_LAST_TRANSLATION
  } state_q, state_d;

  // Do not discard a completed prefetch while an already-accepted demand may
  // still consume it. Queued speculative ARs are intentionally excluded: they
  // are cleared by prefetch_flush_now and have not reached memory.
  assign prefetch_demand_path_idle =
      (state_q == IDLE) &&
      pe_req_fifo_empty &&
      !pe_req_stage_valid_q &&
      ldu_axi_addrgen_queue_empty &&
      stu_axi_addrgen_queue_empty &&
      !(|vinsn_running_d);

  axi_addr_t lookahead_addr_e_d, lookahead_addr_e_q;
  axi_addr_t lookahead_addr_se_d, lookahead_addr_se_q;
  vlen_t lookahead_len_d, lookahead_len_q;

  localparam clog2_AxiStrobeWidth = $clog2(AxiDataWidth/8);

  logic                    vreq_is_vld;
  logic [CVA6Cfg.VLEN-1:0] vreq_addr_d, vreq_addr_q;
  vlen_t                   vreq_blen_d, vreq_blen_q;
  logic                    vreq_is_load_d, vreq_is_load_q;
  logic                    vreq_is_unit_stride_d, vreq_is_unit_stride_q;
  logic                    vreq_is_stride_d, vreq_is_stride_q;
  logic                    vreq_is_index_d, vreq_is_index_q;
  logic                    axi_ax_ready;
  logic [12:0]             num_bytes;
  vlen_t                   remaining_bytes;
  axi_addr_t               paddr;
  axi_addr_t               unit_stride_vaddr;
  axi_addr_t               unit_stride_paddr;
  logic [31:0]             num_beats;
  logic [31:0]             burst_length;
  logic [NrLanes-1:0]      addrgen_operand_valid;
  logic                    curr_req_page_crossed;
  logic                    curr_req_page_crossed_next;

  logic [31:0]             prefetch_num_beats;
  logic [31:0]             prefetch_num_bytes;
  logic [31:0]             prefetch_burst_length;
  logic [31:0]             prefetch_total_beats;
  logic                    prefetch_req_page_crossed;
  axi_addr_t               prefetch_addr;
  axi_addr_t               prefetch_logical_stride_bytes;
  logic [31:0]             prefetch_vl_ext;
  logic [31:0]             prefetch_required_avl;
  logic                    prefetch_avl_enough;
  vlen_t                    prefetch_logical_load_bytes;
  logic                     prefetch_first_logical_chunk;
  axi_addr_t               prefetch_aligned_start_addr;
  
  // A completed task may leave speculative data resident after all
  // architectural vector instructions have retired. The task is clean either
  // after its one cleanup pulse, or in that pulse's cycle: all accepted AXI
  // traffic has drained and local speculative state clears at the same edge.
  assign prefetch_task_clean_o =
      !hdv_task_end_i || task_end_cleaned_q || prefetch_flush_now;

  axi_addr_t    aligned_start_addr_d, aligned_start_addr_q;
  axi_addr_t    aligned_next_start_addr_d, aligned_next_start_addr_q, aligned_next_start_addr_temp;
  axi_addr_t    aligned_end_addr_d, aligned_end_addr_q, aligned_end_addr_temp;

  logic [($bits(aligned_start_addr_d) - 12)-1:0] next_2page_msb_d, next_2page_msb_q;
  logic [clog2_AxiStrobeWidth:0]                 eff_axi_dw_d, eff_axi_dw_q;
  logic [idx_width(clog2_AxiStrobeWidth):0]      eff_axi_dw_log_d, eff_axi_dw_log_q;
  logic [clog2_AxiStrobeWidth-1:0]               narrow_axi_data_bwidth;
  logic [clog2_AxiStrobeWidth-1:0]               axi_addr_misalignment;
  logic [idx_width(clog2_AxiStrobeWidth)-1:0]    zeroes_cnt;


  function automatic void set_end_addr (
      input  logic [($bits(axi_addr_t) - 12)-1:0]      next_2page_msb,
      input  vlen_t                                    num_bytes,
      input  axi_addr_t                                addr,
      input  logic [clog2_AxiStrobeWidth:0]            eff_axi_dw,
      input  logic [idx_width(clog2_AxiStrobeWidth):0] eff_axi_dw_log,
      input  axi_addr_t                                aligned_start_addr,
      output axi_addr_t                                aligned_end_addr,
      output axi_addr_t                                aligned_next_start_addr,
      output logic                                     page_crossed
  );
    automatic int unsigned max_burst_bytes = 256 << eff_axi_dw_log;
    automatic logic [11:0] align_mask;
    automatic logic [15:0] next_sum;
    automatic logic [15:0] end_sum;
    automatic logic [15:0] next_low_ext;
    automatic logic [AxiAddrWidth-13:0] addr_page;
    automatic logic [AxiAddrWidth-13:0] next_page;
    automatic logic [AxiAddrWidth-13:0] end_page;
    page_crossed = 1'b0;
    align_mask = ~(12'(eff_axi_dw) - 12'd1);
    addr_page  = addr[AxiAddrWidth-1:12];

    // Keep the common unit-stride address recurrence on page-local arithmetic.
    // The old full-width addr + bytes path was a top setup violator; AXI bursts
    // are clipped to 4 KiB pages below, so only the low page offset needs the
    // wide add and the page number changes by the small carry.
    if (num_bytes >= max_burst_bytes) begin
        next_sum     = {4'b0, addr[11:0]} + 16'(max_burst_bytes);
        next_low_ext = {4'b0, (next_sum[11:0] & align_mask)};
        next_page    = addr_page + next_sum[15:12];
    end else begin
        end_sum      = {4'b0, addr[11:0]} + 16'(num_bytes) - 16'd1;
        next_low_ext = {4'b0, (end_sum[11:0] & align_mask)} + 16'(eff_axi_dw);
        next_page    = addr_page + end_sum[15:12] + next_low_ext[15:12];
    end
    aligned_next_start_addr = {next_page, next_low_ext[11:0]};
    if (next_low_ext[11:0] == 12'h000) begin
        end_page         = next_page - 1'b1;
        aligned_end_addr = {end_page, 12'hFFF};
    end else begin
        end_page         = next_page;
        aligned_end_addr = {next_page, next_low_ext[11:0] - 12'd1};
    end
    // But since AXI requests are aligned in 4 KiB pages, aligned_end_addr must be in the
    // same page as aligned_start_addr
    if (aligned_start_addr[AxiAddrWidth-1:12] != end_page) begin
        aligned_end_addr        = {aligned_start_addr[AxiAddrWidth-1:12], 12'hFFF};
        aligned_next_start_addr = {                     next_2page_msb  , 12'h000};
        page_crossed = 1'b1;
    end
  endfunction

  // Unit-stride burst and prefetch generation must not share the indexed
  // operand address cone.  In IDLE, use the lookahead address captured with
  // the staged PE request; once running, use the registered request address.
  // This preserves the existing same-cycle first request while preventing an
  // impossible indexed-operand -> unit-prefetch STA path.
  assign unit_stride_vaddr =
      (state_q == IDLE) ? pe_req_unit_stride_addr_stage_q : vreq_addr_q;

  assign unit_stride_paddr = en_ld_st_translation_i ? mmu_paddr_i
                                                     : unit_stride_vaddr;
  assign axi_addr_misalignment =
      unit_stride_vaddr[clog2_AxiStrobeWidth-1:0];

  lzc #(
    .WIDTH(clog2_AxiStrobeWidth),
    .MODE (1'b0                )
  ) i_lzc (
    .in_i   (axi_addr_misalignment),
    .cnt_o  (zeroes_cnt           ),
    .empty_o(/* Unconnected */    )
  );

  assign narrow_axi_data_bwidth = (AxiDataWidth/8) >> (clog2_AxiStrobeWidth - zeroes_cnt);
  assign axi_addrgen_queue_full = vreq_is_load_d ? ldu_axi_addrgen_queue_full
                                                 : stu_axi_addrgen_queue_full;
  assign ldu_axi_addrgen_queue_push = axi_addrgen_queue_push &  vreq_is_load_d;
  assign stu_axi_addrgen_queue_push = axi_addrgen_queue_push & ~vreq_is_load_d;

  always_comb begin
    state_d         = state_q;
    pe_req_d        = pe_req_q;
    vinsn_running_d = vinsn_running_q & pe_vinsn_running_i;

    aligned_start_addr_d         = aligned_start_addr_q;
    aligned_next_start_addr_d    = aligned_next_start_addr_q;
    aligned_end_addr_d           = aligned_end_addr_q;
    aligned_next_start_addr_temp = aligned_next_start_addr_q;
    aligned_end_addr_temp        = aligned_end_addr_q;

    next_2page_msb_d = next_2page_msb_q;

    eff_axi_dw_d     = eff_axi_dw_q;
    eff_axi_dw_log_d = eff_axi_dw_log_q;

    addrgen_exception_vstart_d = '0;
    idx_op_error_d             = 1'b0;
    addrgen_operand_valid      = addrgen_operand_valid_i;

    axi_addrgen_queue      = '0;
    axi_addrgen_queue_push = 1'b0;

    axi_ar_o       = '0;
    axi_ar_valid_o = 1'b0;
    axi_aw_o       = '0;
    axi_aw_valid_o = 1'b0;

    mmu_exception_d = mmu_exception_q;
    mmu_req_d       = 1'b0;
    mmu_vaddr_o     = '0;
    mmu_is_store_o  = 1'b0;

    addrgen_fof_exception_d = addrgen_fof_exception_q;
    // Clean-up fof exception once it's used
    if ((state_q == WAIT_LAST_TRANSLATION) && mmu_exception_q.valid)
      addrgen_fof_exception_d = 1'b0;

    len_temp = '0;
    next_addr_strided_temp = '0;

    last_translation_completed = 1'b0;

    vreq_is_vld           = 1'b0;
    addrgen_ack           = 1'b0;
    pe_req_stage_consume  = 1'b0;
    vreq_addr_d           = vreq_addr_q;
    vreq_blen_d           = vreq_blen_q;
    vreq_is_load_d        = vreq_is_load_q;
    vreq_is_unit_stride_d = vreq_is_unit_stride_q;
    vreq_is_stride_d      = vreq_is_stride_q;
    vreq_is_index_d       = vreq_is_index_q;
    axi_ax_ready          = 1'b0;
    num_bytes             = '0;
    remaining_bytes       = '0;
    paddr                 = '0;
    num_beats             = '0;
    burst_length          = '0;

    addrgen_exception_o       = '0;
    addrgen_exception_o.valid = 1'b0;
    addrgen_exception_o.gva   = '0;
    addrgen_exception_o.tinst = '0;
    addrgen_exception_o.tval  = '0;
    addrgen_exception_o.tval2 = '0;
    addrgen_exception_o.cause = '0;
    addrgen_illegal_load_o    = 1'b0;
    addrgen_illegal_store_o   = 1'b0;

    addrgen_fof_exception_o   = 1'b0;

    addrgen_operand_ready_o   = 1'b0;
    reduced_word_d            = reduced_word_q;
    elm_ptr_d                 = elm_ptr_q;
    word_lane_ptr_d           = word_lane_ptr_q;
    last_elm_subw_d           = last_elm_subw_q;

    shuffled_word             = '0;
    deshuffled_word           = '0;
    idx_vaddr                 = '0;

    //prefetch
    prefetch_axi_ar_hit        = '0;
    stream_break               = 1'b0;
    prefetch_pending_d         = '0;
    prefetch_bad_cnt_d         = prefetch_bad_cnt_q;
    prefetch_axi_ar_queue_datain = '0;
    prefetch_stream_queue_datain = '0;
    prefetch_bytes_queue_datain = '0;
    prefetch_axi_ar_queue_push = '0;
    prefetch_axi_ar_queue_pop  = '0;
    prefetch_axi_ar_queue_cancel = '0;
    prefetch_iter_avl_d        = prefetch_iter_avl_q; // hold the prefetched iteration

    prefetch_axi_ar_rob_push             = '0;
    prefetch_axi_ar_rob_datain           = '0;
    prefetch_axi_ar_rob_match            = 1'b0;
    prefetch_axi_ar_queue_match          = 1'b0;
    prefetch_queue_issue_resources_ready = 1'b0;
    prefetch_queue_promote               = 1'b0;
    prefetch_wait_match                  = 1'b0;
    prefetch_lookup_match                = 1'b0;
    prefetch_lookup_head_match           = 1'b0;
    prefetch_lookup_head_future_near     = 1'b0;
    prefetch_lookup_head_delta           = '0;
    prefetch_lookup_head_same_stream     = 1'b0;
    prefetch_axi_addr_lookup_fifo_push   = '0;
    prefetch_axi_addr_lookup_fifo_pop    = '0;
    prefetch_axi_addr_lookup_fifo_datain = '0;

    curr_req_page_crossed                = '0;
    curr_req_page_crossed_next           = '0;

    prefetch_num_beats               = '0;
    prefetch_burst_length            = '0;
    prefetch_total_beats             = '0;
    prefetch_req_page_crossed        = 1'b0;
    prefetch_addr                    = '0;
    prefetch_logical_stride_bytes    = '0;
    prefetch_vl_ext                  = '0;
    prefetch_required_avl            = '0;
    prefetch_avl_enough              = 1'b0;
    prefetch_logical_load_bytes      = '0;
    prefetch_first_logical_chunk     = 1'b0;
    prefetch_num_bytes               = '0;
    prefetch_aligned_start_addr      = '0;

    case(state_q)
    IDLE: begin : addrgen_state_IDLE
      if (pe_req_valid && (is_load(pe_req.op) || is_store(pe_req.op)) && !vinsn_running_q[pe_req.id]) begin : register_req
        pe_req_d                     = pe_req;
        vinsn_running_d[pe_req_d.id] = 1'b1;
        addrgen_ack                  = 1'b1;
        pe_req_stage_consume         = 1'b1;

        vreq_is_vld           = 1'b1;
        vreq_is_load_d        = is_load(pe_req_d.op);
        vreq_blen_d           = (pe_req_d.vl - pe_req_d.vstart) << unsigned'(pe_req_d.vtype.vsew[1:0]);
        vreq_is_unit_stride_d = pe_req_d.op inside {VLE, VSE};
        vreq_is_stride_d      = pe_req_d.op inside {VLSE, VSSE};
        vreq_is_index_d       = pe_req_d.op inside {VLXE, VSXE};
        axi_ax_ready          = (vreq_is_load_d && axi_ar_ready_i) || (!vreq_is_load_d && axi_aw_ready_i);

        if (vreq_is_unit_stride_d) begin : IDLE_VLSE_VLD
          state_d     = ADDRGEN;
          vreq_addr_d = pe_req_d.scalar_op + (pe_req_d.vstart << unsigned'(pe_req_d.vtype.vsew));

        end : IDLE_VLSE_VLD
        else if (vreq_is_stride_d) begin : IDLE_VLSSE_VLD
          state_d     = ADDRGEN;
          vreq_addr_d = pe_req_d.scalar_op + (pe_req_d.vstart * pe_req_d.stride);

        end : IDLE_VLSSE_VLD
        else begin : IDLE_VLSXE_VLD

          state_d = ADDRGEN_IDX_OP;

          case (pe_req_d.eew_vs2)
            EW8: begin
              last_elm_subw_d = 7;
              word_lane_ptr_d = pe_req_d.vstart[Log2VRFWordWidthB-1:Log2LaneWordWidthB];
              elm_ptr_d       = pe_req_d.vstart[Log2LaneWordWidthB-1:0];
            end
            EW16: begin
              last_elm_subw_d = 3;
              word_lane_ptr_d = pe_req_d.vstart[Log2VRFWordWidthH-1:Log2LaneWordWidthH];
              elm_ptr_d       = pe_req_d.vstart[Log2LaneWordWidthH-1:0];
            end
            EW32: begin
              last_elm_subw_d = 1;
              word_lane_ptr_d = pe_req_d.vstart[Log2VRFWordWidthS-1:Log2LaneWordWidthS];
              elm_ptr_d       = pe_req_d.vstart[Log2LaneWordWidthS-1:0];
            end
            default: begin
              last_elm_subw_d = 0;
              word_lane_ptr_d = pe_req_d.vstart[Log2VRFWordWidthD-1:0];
              elm_ptr_d       = 0;
            end
          endcase

          for (int unsigned lane = 0; lane < NrLanes; lane++) begin : adjust_operand_valid
            if ((vreq_blen_d < (NrLanes * DataWidthB))
                 && (lane < pe_req_d.vstart[idx_width(NrLanes)-1:0])) begin : vstart_lane_adjust
              addrgen_operand_valid[lane] |= 1'b1;
            end : vstart_lane_adjust
          end : adjust_operand_valid

          if (&addrgen_operand_valid) begin
            shuffled_word             = addrgen_operand_i;
            for (int unsigned b = 0; b < 8*NrLanes; b++) begin
              automatic shortint unsigned b_shuffled = shuffle_index(b, NrLanes, pe_req_d.eew_vs2);
              deshuffled_word[8*b +: 8] = shuffled_word[8*b_shuffled +: 8];
            end
      
            for (int unsigned lane = 0; lane < NrLanes; lane++)
              if (lane == word_lane_ptr_d)
                reduced_word_d = deshuffled_word[word_lane_ptr_d*$bits(elen_t) +: $bits(elen_t)];

            case (pe_req_d.eew_vs2)
              EW8: begin
                for (int unsigned b = 0; b < 8; b++)
                  if (b == elm_ptr_d)
                    idx_vaddr = reduced_word_d[b*8 +: 8];
              end
              EW16: begin
                for (int unsigned h = 0; h < 4; h++)
                  if (h == elm_ptr_d)
                    idx_vaddr = reduced_word_d[h*16 +: 16];
              end
              EW32: begin
                for (int unsigned w = 0; w < 2; w++)
                  if (w == elm_ptr_d)
                    idx_vaddr = reduced_word_d[w*32 +: 32];
              end
              EW64: begin
                for (int unsigned d = 0; d < 1; d++)
                  if (d == elm_ptr_d)
                    idx_vaddr = reduced_word_d[d*64 +: 64];
              end
              default: begin
                for (int unsigned b = 0; b < 8; b++)
                  if (b == elm_ptr_d)
                    idx_vaddr = reduced_word_d[b*8 +: 8];
              end
            endcase

            vreq_addr_d = pe_req_d.scalar_op + idx_vaddr;
          end

          vreq_is_vld = &addrgen_operand_valid;
        end : IDLE_VLSXE_VLD
      end : register_req

    end : addrgen_state_IDLE

    ADDRGEN: begin : addrgen_state_ADDRGEN
      vreq_is_vld  = 1'b1;
      axi_ax_ready = (vreq_is_load_d && axi_ar_ready_i) || (!vreq_is_load_d && axi_aw_ready_i);
    end : addrgen_state_ADDRGEN

    ADDRGEN_IDX_OP: begin : addrgen_state_ADDRGEN_IDX_OP
      for (int unsigned lane = 0; lane < NrLanes; lane++) begin : adjust_operand_valid
        if ((vreq_blen_d < (NrLanes * DataWidthB))
             && (lane < pe_req_d.vstart[idx_width(NrLanes)-1:0])) begin : vstart_lane_adjust
          addrgen_operand_valid[lane] |= 1'b1;
        end : vstart_lane_adjust
      end : adjust_operand_valid

      if (&addrgen_operand_valid) begin
        shuffled_word             = addrgen_operand_i;
        for (int unsigned b = 0; b < 8*NrLanes; b++) begin
          automatic shortint unsigned b_shuffled = shuffle_index(b, NrLanes, pe_req_d.eew_vs2);
          deshuffled_word[8*b +: 8] = shuffled_word[8*b_shuffled +: 8];
        end
      
        for (int unsigned lane = 0; lane < NrLanes; lane++)
          if (lane == word_lane_ptr_d)
            reduced_word_d = deshuffled_word[word_lane_ptr_d*$bits(elen_t) +: $bits(elen_t)];

        case (pe_req_d.eew_vs2)
          EW8: begin
            for (int unsigned b = 0; b < 8; b++)
              if (b == elm_ptr_d)
                idx_vaddr = reduced_word_d[b*8 +: 8];
          end
          EW16: begin
            for (int unsigned h = 0; h < 4; h++)
              if (h == elm_ptr_d)
                idx_vaddr = reduced_word_d[h*16 +: 16];
          end
          EW32: begin
            for (int unsigned w = 0; w < 2; w++)
              if (w == elm_ptr_d)
                idx_vaddr = reduced_word_d[w*32 +: 32];
          end
          EW64: begin
            for (int unsigned d = 0; d < 1; d++)
              if (d == elm_ptr_d)
                idx_vaddr = reduced_word_d[d*64 +: 64];
          end
          default: begin
            for (int unsigned b = 0; b < 8; b++)
              if (b == elm_ptr_d)
                idx_vaddr = reduced_word_d[b*8 +: 8];
          end
        endcase

        vreq_addr_d = pe_req_d.scalar_op + idx_vaddr;
      end

      vreq_is_vld  = &addrgen_operand_valid;
      axi_ax_ready = (vreq_is_load_d && axi_ar_ready_i) || (!vreq_is_load_d && axi_aw_ready_i);

    end : addrgen_state_ADDRGEN_IDX_OP

    ADDRGEN_IDX_OP_END : begin
      state_d = IDLE;
    end

    WAIT_LAST_TRANSLATION : begin : addrgen_state_WAIT_LAST_TRANSLATION
      if (last_translation_completed | mmu_exception_q.valid) begin
        state_d = IDLE;
      end
    end : addrgen_state_WAIT_LAST_TRANSLATION
    endcase

    prefetch_logical_load_bytes =
        (pe_req_d.vl - pe_req_d.vstart) <<
        unsigned'(pe_req_d.vtype.vsew[1:0]);
    prefetch_first_logical_chunk =
        vreq_blen_d == prefetch_logical_load_bytes;

    // A logical unit-stride load may be split into multiple AXI descriptors at
    // a page boundary. Only its first descriptor may consume or wait for a
    // whole-load prefetch. A later tail can start at the same address as an
    // unrelated full prefetch and must remain on the demand path.
    if (vreq_is_load_d && vreq_is_unit_stride_d &&
        prefetch_first_logical_chunk) begin
      for (int i = 0; i < VaddrgenInsnQueueDepth; i++) begin
        if (prefetch_axi_ar_rob_vld[i] &&
            (prefetch_axi_ar_rob_mem[i].addr == unit_stride_paddr) &&
            (prefetch_bytes_rob_mem[i] ==
             prefetch_logical_load_bytes)) begin
          prefetch_axi_ar_rob_match = 1'b1;
        end
        if (prefetch_lookup_slot_valid_q[i] &&
            (prefetch_axi_addr_lookup_fifo_mem[i].addr == unit_stride_paddr) &&
            (prefetch_axi_addr_lookup_fifo_mem[i].logical_bytes ==
             prefetch_logical_load_bytes)) begin
          prefetch_lookup_match = 1'b1;
        end
      end
      if (!prefetch_axi_addr_lookup_fifo_empty) begin
        prefetch_lookup_head_same_stream =
            prefetch_axi_addr_lookup_fifo_data.stream_id ==
            pe_req_d.hdv_meta.prefetch_stream_id;
        prefetch_lookup_head_match =
            (prefetch_axi_addr_lookup_fifo_data.addr == unit_stride_paddr) &&
            (prefetch_axi_addr_lookup_fifo_data.logical_bytes ==
             prefetch_logical_load_bytes);
      end
    end
    prefetch_axi_ar_queue_match =
        vreq_is_load_d && vreq_is_unit_stride_d &&
        prefetch_first_logical_chunk &&
        prefetch_axi_ar_queue_valid &&
        !prefetch_stream_queue_empty &&
        (prefetch_axi_ar_data.addr == unit_stride_paddr) &&
        !prefetch_bytes_queue_empty &&
        (prefetch_bytes_at_issue == prefetch_logical_load_bytes);

    // Queue entries were authorized when their request-bound hint generated them.
    // Their later drain must not depend on the metadata of whichever scalar,
    // arithmetic, or store instruction happens to be current at that cycle.
    // Keep hard capacity/order checks separate from speculative lead control so
    // an exact demand match can coalesce with a queued AR without being mistaken
    // for additional speculative traffic.
    prefetch_queue_hard_resources_ready =
        axi_ar_ready_i &&
        prefetch_axi_ar_queue_valid &&
        !prefetch_stream_queue_empty &&
        !prefetch_bytes_queue_empty &&
        !prefetch_axi_ar_rob_full &&
        !prefetch_axi_addr_lookup_fifo_full &&
        prefetch_lookup_entry_credit &&
        !flush_pending_q && !hdv_task_end_i &&
        ((({2'b0, prefetch_buf_occupancy_i} << 1) + prefetch_inflight_beats_q
          + $unsigned(prefetch_axi_ar_data.len) + 1) <= PrefetchBufBeats);
    prefetch_queue_speculative_issue_allowed =
        !prefetch_adaptive_throttle &&
        (!store_stuck ||
         (pe_req_d.avl == prefetch_iter_avl_q) ||
         ((({2'b0, prefetch_buf_occupancy_i} << 1) + prefetch_inflight_beats_q)
          <= prefetch_lead_beats));
    prefetch_queue_issue_resources_ready =
        prefetch_queue_hard_resources_ready &&
        prefetch_queue_speculative_issue_allowed;
    prefetch_queue_promote =
        vreq_is_vld &&
        prefetch_axi_ar_queue_match &&
        !prefetch_pending_d && !axi_ar_valid_o &&
        prefetch_queue_issue_resources_ready;

    // Wait for a matching in-flight prefetch, or for an exact queue-head match
    // that is guaranteed to issue in this cycle. Page-crossing prefetch
    // candidates are never enqueued.
    prefetch_wait_match =
        vreq_is_load_d && vreq_is_unit_stride_d &&
        ((prefetch_axi_ar_rob_match &&
          !prefetch_axi_addr_lookup_fifo_full) ||
         prefetch_queue_promote);

    if (vreq_is_vld &&
        //!(vreq_is_load_d && block_load_addr_i) &&
        !(vreq_is_load_d && prefetch_wait_match)) begin : demand_req
      if (!axi_addrgen_queue_full && axi_ax_ready) begin : start_req
        paddr = vreq_is_unit_stride_d
              ? unit_stride_paddr
              : (en_ld_st_translation_i ? mmu_paddr_i : vreq_addr_d);

        // Prefetch-hit detection. MUST be gated on vreq_is_load_d: the data prefetcher
        // is read-only, so only a LOAD can legitimately hit it. An in-place STORE
        // (vsswap writes the very addresses it loaded/prefetched) would otherwise match
        // here, set prefetch_axi_ar_hit, and POP the lookup FIFO -- stealing a real
        // load's prefetch-hit entry. That desyncs the load hit/descriptor accounting
        // (orphan load descriptors pile up in the ldu queue -> qfull freezes addrgen)
        // and the store path, deadlocking the only in-place-store kernel at max AVL
        // (vsswap@4096). Loads keep the original behavior unchanged -> performance-neutral.
        if (vreq_is_load_d &&
            !prefetch_axi_addr_lookup_fifo_empty &&
            vreq_is_unit_stride_d) begin
          if (prefetch_lookup_head_match) begin
            prefetch_axi_ar_hit                 = 1'b1;
            prefetch_axi_addr_lookup_fifo_pop   = 1'b1;
          end else if (prefetch_lookup_head_same_stream &&
                       ($unsigned(prefetch_axi_addr_lookup_fifo_data.addr) >
                        $unsigned(unit_stride_paddr))) begin
            prefetch_lookup_head_delta =
                prefetch_axi_addr_lookup_fifo_data.addr - unit_stride_paddr;
            prefetch_lookup_head_future_near =
                ($unsigned(prefetch_lookup_head_delta) <=
                 ($unsigned(vreq_blen_d) + 32));
            if (!prefetch_lookup_head_future_near) begin
              stream_break = 1'b1;
            end
          end else if (prefetch_lookup_head_same_stream) begin
            // This static load has moved past its completed prefetch head, so the
            // stream diverged. Other static loads do not trigger this recovery.
            stream_break = 1'b1;
          end
        end

        if (is_addr_error(paddr, pe_req_d.vtype.vsew[1:0])) begin
          state_d                   = IDLE;
          addrgen_ack               = 1'b1;
          addrgen_exception_o.valid = 1'b1;
          addrgen_exception_o.cause = riscv::ILLEGAL_INSTR;
          addrgen_exception_o.tval  = '0;
        end else begin
          // The matching prefetch is queued but cannot be promoted this cycle.
          // Remove it before issuing the demand, otherwise it would return later
          // as an obsolete entry and could flush unrelated streams.
          if (vreq_is_load_d && vreq_is_unit_stride_d &&
              prefetch_axi_ar_queue_match) begin
            prefetch_axi_ar_queue_cancel = 1'b1;
          end

          if (vreq_is_unit_stride_d) begin : unit_stride_req
            automatic logic [clog2_AxiStrobeWidth:0] bytes_to_bus_alignment;

            bytes_to_bus_alignment = '0;
            if (pe_req_d.vstart != 0 && !vreq_is_load_d) begin
              eff_axi_dw_d     = 1 << pe_req_d.vtype.vsew[1:0];
              eff_axi_dw_log_d = pe_req_d.vtype.vsew[1:0];
            end else if ((unit_stride_paddr[clog2_AxiStrobeWidth-1:0] != '0) &&
                         !vreq_is_load_d) begin
              eff_axi_dw_d     = {1'b0, narrow_axi_data_bwidth};
              eff_axi_dw_log_d = zeroes_cnt;
            end else begin
              eff_axi_dw_d     = AxiDataWidth/8;
              eff_axi_dw_log_d = clog2_AxiStrobeWidth;
            end

            // Select the effective store beat width before deriving the aligned
            // range.  Mixing a full-bus aligned range with a narrowed beat size
            // overstates AW.len for unaligned stores (for example 62 e64
            // elements became 64 beats), leaving VSTU waiting for padding beats
            // that do not exist.
            aligned_start_addr_d =
                aligned_addr(unit_stride_paddr, eff_axi_dw_log_d);
            next_2page_msb_d = aligned_start_addr_d[AxiAddrWidth-1:12] + 1;
            set_end_addr (
              next_2page_msb_d,
              vreq_blen_d,
              unit_stride_paddr,
              eff_axi_dw_d,
              eff_axi_dw_log_d,
              aligned_start_addr_d,
              aligned_end_addr_d,
              aligned_next_start_addr_d,
              curr_req_page_crossed
            );

            // Use narrow beats only for the unaligned head. Once the request
            // reaches a full-bus boundary, the next AddrGen iteration widens
            // back to AxiDataWidth. Keeping the entire request narrow is legal
            // but needlessly turns a long vector store into one beat per
            // element.
            if (!vreq_is_load_d &&
                (unit_stride_paddr[clog2_AxiStrobeWidth-1:0] != '0)) begin
              bytes_to_bus_alignment =
                  (AxiDataWidth/8) -
                  unit_stride_paddr[clog2_AxiStrobeWidth-1:0];
              if (vreq_blen_d > bytes_to_bus_alignment) begin
                aligned_end_addr_d =
                    unit_stride_paddr + bytes_to_bus_alignment - 1'b1;
                aligned_next_start_addr_d =
                    unit_stride_paddr + bytes_to_bus_alignment;
                curr_req_page_crossed =
                    aligned_next_start_addr_d[AxiAddrWidth-1:12] !=
                    unit_stride_paddr[AxiAddrWidth-1:12];
              end
            end

            if (curr_req_page_crossed) begin
              num_bytes = 13'h1000 - unit_stride_paddr[11:0];
            end else begin
              num_bytes =
                  aligned_end_addr_d[11:0] - unit_stride_paddr[11:0] + 1;
            end
  
            if (vreq_blen_d < num_bytes) begin
              remaining_bytes = 0;
            end
            else begin
              remaining_bytes = vreq_blen_d - num_bytes;
            end

            num_beats = ((aligned_end_addr_d[11:0] - aligned_start_addr_d[11:0]) >> eff_axi_dw_log_d) + 1;
            burst_length = (num_beats < 256) ? num_beats : 256;

            if (vreq_is_load_d) begin
              axi_ar_o = '{
                id     : AXI_ID_DEMAND,
                addr   : unit_stride_paddr,
                len    : burst_length - 1,
                size   : eff_axi_dw_log_d,
                cache  : CACHE_MODIFIABLE,
                burst  : BURST_INCR,
                default: '0
              };

              if (prefetch_axi_ar_hit) begin
                axi_ar_o = '0;
              end

              prefetch_vl_ext = pe_req_d.vl;
              prefetch_required_avl = prefetch_vl_ext +
                                      (prefetch_vl_ext << prefetch_mul);
              prefetch_avl_enough = ($unsigned(pe_req_d.avl) >=
                                      $unsigned(prefetch_required_avl));
              if (prefetch_avl_enough &&
                  prefetch_axi_ar_queue_not_full &&
                  !prefetch_stream_queue_full &&
                  !prefetch_bytes_queue_full &&
                  prefetch_lookup_entry_credit &&
                  prefetch_en && !prefetch_adaptive_throttle &&
                  !flush_pending_q && !hdv_task_end_i &&
                  prefetch_first_logical_chunk &&
                  !curr_req_page_crossed) begin : first_prefetch
                // Prefetch the same unit-stride stream in a future strip-mined
                // iteration.  The address distance must be the logical vector
                // footprint, not the AXI burst coverage (`num_bytes`), because
                // unaligned loads expand to aligned bus beats and would otherwise
                // overstep the next iteration's real demand address.
                prefetch_logical_stride_bytes = axi_addr_t'(vreq_blen_d) << prefetch_mul;
                prefetch_addr =
                    unit_stride_paddr + prefetch_logical_stride_bytes;
                prefetch_num_bytes = vreq_blen_d;

                // A load prefetch always uses the full AXI data width.  Compute
                // its page-local beat counts directly instead of routing it
                // through the variable-width misaligned-store/LZC cone.
                prefetch_aligned_start_addr =
                    aligned_addr(prefetch_addr, clog2_AxiStrobeWidth);
                prefetch_total_beats =
                    (($unsigned(prefetch_addr[clog2_AxiStrobeWidth-1:0]) +
                      $unsigned(prefetch_num_bytes) + (AxiDataWidth/8) - 1) >>
                     clog2_AxiStrobeWidth);
                prefetch_num_beats =
                    (32'd4096 -
                     $unsigned(prefetch_aligned_start_addr[11:0])) >>
                    clog2_AxiStrobeWidth;
                prefetch_burst_length =
                    (prefetch_total_beats < prefetch_num_beats)
                    ? prefetch_total_beats : prefetch_num_beats;
                if (prefetch_burst_length > 256)
                  prefetch_burst_length = 256;
                prefetch_req_page_crossed =
                    prefetch_total_beats > prefetch_num_beats;
              
                // Do not enqueue a page-crossing candidate. The global prefetch
                // data FIFO and address-only lookup cannot safely let a short
                // next-page tail share an address with another stream's full
                // request. Skip only this boundary candidate; the first demand
                // wholly inside the next page re-establishes the same stream.
                if ((prefetch_burst_length != 0) &&
                    !prefetch_req_page_crossed) begin
                  prefetch_axi_ar_queue_datain = '{
                    id     : AXI_ID_DEMAND,   // same-id: prefetch shares demand id
                    addr   : prefetch_addr,
                    len    : prefetch_burst_length - 1,
                    size   : clog2_AxiStrobeWidth,
                    cache  : CACHE_MODIFIABLE,
                    burst  : BURST_INCR,
                    default: '0
                  };
              
                  prefetch_axi_ar_queue_push = 1'b1;
                  prefetch_stream_queue_datain =
                      pe_req_d.hdv_meta.prefetch_stream_id;
                  prefetch_bytes_queue_datain = vlen_t'(prefetch_num_bytes);
                  prefetch_pending_d         = 1'b1;
                end
              end : first_prefetch

            end
            else begin
              axi_aw_o = '{
                id     : AXI_ID_DEMAND,
                addr   : unit_stride_paddr,
                len    : burst_length - 1,
                size   : eff_axi_dw_log_d,
                cache  : CACHE_MODIFIABLE,
                burst  : BURST_INCR,
                default: '0
              };
            end

            axi_addrgen_queue = '{
              addr            : unit_stride_paddr,
              len             : burst_length - 1,
              size            : eff_axi_dw_log_d,
              is_load         : vreq_is_load_d,
              is_exception    : 1'b0,
              is_prefetch_hit : prefetch_axi_ar_hit
            };

          end : unit_stride_req
          else if (vreq_is_stride_d) begin : stride_req
            if (vreq_is_load_d) begin
              axi_ar_o = '{
                id     : AXI_ID_DEMAND,
                addr   : paddr,
                len    : 0,
                size   : pe_req_d.vtype.vsew[1:0],
                cache  : CACHE_MODIFIABLE,
                burst  : BURST_INCR,
                default: '0
              };
            end
            else begin
              axi_aw_o = '{
                id     : AXI_ID_DEMAND,
                addr   : paddr,
                len    : 0,
                size   : pe_req_d.vtype.vsew[1:0],
                cache  : CACHE_MODIFIABLE,
                burst  : BURST_INCR,
                default: '0
              };
            end

            axi_addrgen_queue = '{
              addr            : paddr,
              size            : pe_req_d.vtype.vsew[1:0],
              len             : 0,
              is_load         : vreq_is_load_d,
              is_exception    : 1'b0,
              is_prefetch_hit : 1'b0
            };

            len_temp = vreq_blen_d - (1 << pe_req_d.vtype.vsew[1:0]);
            next_addr_strided_temp = paddr + pe_req_d.stride;
          end : stride_req
          else begin : index_req

            if (vreq_is_load_d) begin
              axi_ar_o = '{
                id     : AXI_ID_DEMAND,
                addr   : paddr,
                len    : 0,
                size   : pe_req_d.vtype.vsew[1:0],
                cache  : CACHE_MODIFIABLE,
                burst  : BURST_INCR,
                default: '0
              };
            end
            else begin
              axi_aw_o = '{
                id     : AXI_ID_DEMAND,
                addr   : paddr,
                len    : 0,
                size   : pe_req_d.vtype.vsew[1:0],
                cache  : CACHE_MODIFIABLE,
                burst  : BURST_INCR,
                default: '0
              };
            end

            axi_addrgen_queue = '{
              addr            : paddr,
              size            : pe_req_d.vtype.vsew[1:0],
              len             : 0,
              is_load         : vreq_is_load_d,
              is_exception    : 1'b0,
              is_prefetch_hit : 1'b0
            };

            len_temp = vreq_blen_d - (1 << pe_req_d.vtype.vsew[1:0]);

            if (elm_ptr_d == last_elm_subw_d) begin
              elm_ptr_d       = '0;
              if (word_lane_ptr_d == NrLanes - 1) begin
                addrgen_operand_ready_o = 1'b1;
              end
              word_lane_ptr_d += 1;
            end else begin
              elm_ptr_d += 1;
            end
          end : index_req
        end

        if (mmu_exception_i.valid) begin
          state_d = IDLE;
          mmu_exception_d = mmu_exception_i;
          axi_addrgen_queue = '{
            addr            : paddr,
            size            : pe_req_d.vtype.vsew[1:0],
            len             : 0,
            is_load         : vreq_is_load_d,
            is_exception    : 1'b1,
            is_prefetch_hit : 1'b0
          };
          axi_addrgen_queue_push = ~(pe_req_d.fault_only_first
                                   & (pe_req_d.vl != (vreq_blen_d >> pe_req_d.vtype.vsew[1:0])));

          addrgen_fof_exception_d = pe_req_d.fault_only_first && (pe_req_d.vl != (vreq_blen_d >> pe_req_d.vtype.vsew[1:0]));

          addrgen_exception_vstart_d  = pe_req_d.vl - (vreq_blen_d >> pe_req_d.vtype.vsew[1:0]);
        end

        if ((mmu_valid_i && !mmu_exception_i.valid) || !en_ld_st_translation_i) begin
          if (vreq_is_unit_stride_d) begin : unit_stride
            axi_ar_valid_o = vreq_is_load_d;
            if (prefetch_axi_ar_hit) begin
              axi_ar_valid_o = '0;
            end

            axi_aw_valid_o = ~vreq_is_load_d;

            axi_addrgen_queue_push = 1'b1;

            vreq_addr_d = aligned_next_start_addr_d;
            vreq_blen_d = remaining_bytes;
            aligned_start_addr_d = vreq_addr_d;
            next_2page_msb_d  = next_2page_msb_d + 1'b1;

            set_end_addr (
              next_2page_msb_d,
              vreq_blen_d,
              aligned_next_start_addr_d,
              eff_axi_dw_d,
              eff_axi_dw_log_d,
              aligned_next_start_addr_d,
              aligned_end_addr_temp,
              aligned_next_start_addr_temp,
              curr_req_page_crossed_next  
            );
            aligned_end_addr_d        = aligned_end_addr_temp;
            aligned_next_start_addr_d = aligned_next_start_addr_temp;

          end : unit_stride
          else if (vreq_is_stride_d) begin : strided // STRIDED ACCESS
            axi_ar_valid_o = vreq_is_load_d;
            axi_aw_valid_o = ~vreq_is_load_d;

            axi_addrgen_queue_push = 1'b1;

            vreq_addr_d = next_addr_strided_temp;
            vreq_blen_d = len_temp;
          end : strided
          else begin : indexed // INDEXED ACCESS
            axi_ar_valid_o = vreq_is_load_d;
            axi_aw_valid_o = ~vreq_is_load_d;

            axi_addrgen_queue_push = 1'b1;

            if (vreq_blen_d == '0) begin
              addrgen_operand_ready_o = 1'b1;
            end

            vreq_blen_d = len_temp;

          end : indexed
        end

        if (vreq_blen_d == '0) begin
          state_d = IDLE;
          if (en_ld_st_translation_i & !mmu_exception_i.valid) begin
            last_translation_completed = 1'b1;
          end
        end
      end : start_req
    end : demand_req
    // Demand AR has priority on the single AR port. The demand path above may
    // already be driving axi_ar_valid_o this cycle; the prefetch drain must NOT
    // override it (that would silently drop the demand AR while its
    // ldu_addrgen_queue entry still waits for id=DEMAND R beats). Prefetch ARs
    // only fill the cycles where demand is not using the bus.
    // Hard queue/ROB/buffer checks are shared with queue promotion above.
    // Speculative prefetches additionally obey loop, throttle, and bounded-lead
    // pacing. An exact promoted request is no longer speculative: it supplies the
    // demand currently at the head and may bypass only those lead controls.
    if (!axi_ar_valid_o && !prefetch_pending_d &&
        (prefetch_queue_issue_resources_ready || prefetch_queue_promote)) begin : prefetch_req
      prefetch_axi_ar_queue_pop  = 1'b1;
      prefetch_axi_ar_rob_push   = 1'b1;
      prefetch_axi_ar_rob_datain = prefetch_axi_ar_data;
      axi_ar_valid_o             = 1'b1;
      axi_ar_o                   = prefetch_axi_ar_data;
      prefetch_iter_avl_d        = pe_req_d.avl; // mark the iteration we prefetched
    end : prefetch_req

    // Record each completed non-page-crossing prefetch burst.
    if (prefetch_axi_ar_rob_pop) begin : prefetch_data_complete
      prefetch_axi_addr_lookup_fifo_push     = 1'b1;
      prefetch_axi_addr_lookup_fifo_datain   = '{
        addr      : prefetch_axi_ar_rob_data.addr,
        logical_bytes : prefetch_bytes_rob_data,
        stream_id : prefetch_stream_rob_data
      };
    end : prefetch_data_complete

    if (prefetch_flush_now || hdv_task_end_i || loop_active_fall || !prefetch_en) begin
      prefetch_bad_cnt_d = '0;
      if (prefetch_flush_now || hdv_task_end_i)
        prefetch_iter_avl_d = '0;
    end else if (prefetch_axi_ar_hit && (prefetch_bad_cnt_d != '0)) begin
      prefetch_bad_cnt_d = prefetch_bad_cnt_d - 1'b1;
    end else if (stream_break && (prefetch_bad_cnt_d != 4'hf)) begin
      prefetch_bad_cnt_d = prefetch_bad_cnt_d + 1'b1;
    end

  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      aligned_start_addr_q      <= '0;
      aligned_next_start_addr_q <= '0;
      addrgen_fof_exception_q   <= '0;
      aligned_end_addr_q        <= '0;
      eff_axi_dw_q              <= '0;
      eff_axi_dw_log_q          <= '0;
      next_2page_msb_q          <= '0;
    end else begin
      aligned_start_addr_q      <= aligned_start_addr_d;
      aligned_next_start_addr_q <= aligned_next_start_addr_d;
      addrgen_fof_exception_q   <= addrgen_fof_exception_d;
      aligned_end_addr_q        <= aligned_end_addr_d;
      eff_axi_dw_q              <= eff_axi_dw_d;
      eff_axi_dw_log_q          <= eff_axi_dw_log_d;
      next_2page_msb_q          <= next_2page_msb_d;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q                    <= IDLE;
      pe_req_q                   <= '0;
      vinsn_running_q            <= '0;
      word_lane_ptr_q            <= '0;
      reduced_word_q             <= '0;
      elm_ptr_q                  <= '0;
      last_elm_subw_q            <= '0;
      idx_op_error_q             <= '0;
      addrgen_exception_vstart_o <= '0;
      mmu_exception_q            <= '0;
      lookahead_addr_e_q         <= '0;
      lookahead_addr_se_q        <= '0;
      lookahead_len_q            <= '0;
      vreq_addr_q                <= '0;
      vreq_blen_q                <= '0;
      vreq_is_load_q             <= '0;
      vreq_is_unit_stride_q      <= '0;
      vreq_is_stride_q           <= '0;
      vreq_is_index_q            <= '0;
    end else begin
      state_q                    <= state_d;
      pe_req_q                   <= pe_req_d;
      vinsn_running_q            <= vinsn_running_d;
      word_lane_ptr_q            <= word_lane_ptr_d;
      reduced_word_q             <= reduced_word_d;
      elm_ptr_q                  <= elm_ptr_d;
      last_elm_subw_q            <= last_elm_subw_d;
      idx_op_error_q             <= idx_op_error_d;
      addrgen_exception_vstart_o <= addrgen_exception_vstart_d;
      mmu_exception_q            <= mmu_exception_d;
      lookahead_addr_e_q         <= lookahead_addr_e_d;
      lookahead_addr_se_q        <= lookahead_addr_se_d;
      lookahead_len_q            <= lookahead_len_d;
      vreq_addr_q                <= vreq_addr_d;
      vreq_blen_q                <= vreq_blen_d;
      vreq_is_load_q             <= vreq_is_load_d;
      vreq_is_unit_stride_q      <= vreq_is_unit_stride_d;
      vreq_is_stride_q           <= vreq_is_stride_d;
      vreq_is_index_q            <= vreq_is_index_d;
    end
  end

  `ifdef FOR_VERIFY
  // ── Performance counters for quantitative analysis ────────────────────
  localparam int unsigned PfProbeMaxEvents = 4096;
  logic [63:0] cnt_pf_probe_cycle;
  logic [31:0] cnt_pf_probe_events;

  logic [63:0] cnt_demand_ar;       // accepted demand AXI read requests
  logic [63:0] cnt_prefetch_ar;     // accepted prefetch AXI read requests
  logic [63:0] cnt_prefetch_hit;    // demand load hit in prefetch buffer
  logic [63:0] cnt_load_vinsn;      // vector load instructions processed
  logic [63:0] cnt_prefetch_en;     // cycles with prefetch_en=1
  logic [63:0] cnt_demand_aw;       // demand AXI write requests
  logic [63:0] cnt_demand_bytes;    // total bytes of demand reads
  logic [63:0] cnt_prefetch_bytes;  // total bytes prefetched
  // Prefetch suppression breakdown — counted on unit-stride load demand AR
  // that could have generated a prefetch but was suppressed.
  logic [63:0] cnt_pf_disabled;     // prefetch_en==0 (global off or mode==0)
  logic [63:0] cnt_pf_page_cross;   // curr_req_page_crossed (demand itself crosses page)
  logic [63:0] cnt_pf_queue_full;   // prefetch_axi_ar_queue full
  logic [63:0] cnt_pf_avl_low;      // avl < vl*(distance+1): no full future vector
  // Prefetch AR issue drops — prefetch was queued but AR not sent this cycle.
  logic [63:0] cnt_pf_ar_rob_full;      // ROB full
  logic [63:0] cnt_pf_ar_lookup_full;   // addr-lookup FIFO full
  logic [63:0] cnt_pf_ar_pending_block; // prefetch_pending_d still set
  logic [63:0] cnt_pf_ar_disabled;      // prefetch_en went off before issue
  // Other
  logic [63:0] cnt_pf_second_issued; // second (page-cross) prefetch issued
  logic [63:0] cnt_demand_rob_block; // demand AR blocked by ROB match (events)
  logic [63:0] cnt_pf_throttled_cycles; // adaptive throttle active while prefetch enabled
  logic [63:0] cnt_pf_wait_match_cycles; // demand waiting for queued/ROB/page-cross prefetch
  logic [63:0] cnt_pf_wait_match_events; // distinct demand wait-match episodes
  logic [63:0] cnt_pf_queue_valid_cycles; // queued prefetch present
  logic [63:0] cnt_pf_queue_block_cycles; // queued prefetch present but not issued
  logic [63:0] cnt_pf_lookup_full_cycles; // lookup FIFO full pressure
  logic [63:0] cnt_pf_rob_full_cycles; // prefetch ROB full pressure
  logic [63:0] cnt_pf_pending_cycles; // prefetch_pending_d pressure
  logic [63:0] cnt_pf_stream_break; // demand stream changed away from lookup head
  logic [63:0] cnt_pf_future_keep; // lookup head kept as a near-future prefetch
  logic [63:0] cnt_pf_queue_match_cycles; // demand matched queued prefetch
  logic [63:0] cnt_pf_rob_match_cycles; // demand matched in-flight/completed ROB prefetch
  logic [63:0] cnt_pf_page_wait_cycles; // demand waiting for second page-cross prefetch
  logic [63:0] cnt_pf_late; // demand arrived while same-address prefetch was issued but not ready
  logic [63:0] cnt_pf_unused; // issued/completed prefetch entries discarded without demand hit
  logic        demand_rob_blocked_q;  // debounce: demand was ROB-blocked last cycle
  logic        demand_pf_late_counted_q;
  logic [$bits(vreq_addr_d)-1:0] demand_pf_late_addr_q;
  logic        demand_pf_promoted_q;
  logic [$bits(vreq_addr_d)-1:0] demand_pf_promoted_addr_q;
  localparam int unsigned DemandPrefetchWaitWatchdogCycles = 20000;
  localparam int unsigned DemandPrefetchWaitCounterWidth =
      $clog2(DemandPrefetchWaitWatchdogCycles + 1);
  logic [DemandPrefetchWaitCounterWidth-1:0] demand_pf_wait_cnt_q;
  logic [$bits(vreq_addr_d)-1:0]             demand_pf_wait_addr_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cnt_pf_probe_cycle <= '0; cnt_pf_probe_events <= '0;
      cnt_demand_ar <= '0; cnt_prefetch_ar <= '0; cnt_prefetch_hit <= '0;
      cnt_load_vinsn <= '0; cnt_prefetch_en <= '0; cnt_demand_aw <= '0;
      cnt_demand_bytes <= '0; cnt_prefetch_bytes <= '0;
      cnt_pf_disabled <= '0; cnt_pf_page_cross <= '0;
      cnt_pf_queue_full <= '0; cnt_pf_avl_low <= '0;
      cnt_pf_ar_rob_full <= '0; cnt_pf_ar_lookup_full <= '0;
      cnt_pf_ar_pending_block <= '0; cnt_pf_ar_disabled <= '0;
      cnt_pf_second_issued <= '0; cnt_demand_rob_block <= '0;
      cnt_pf_throttled_cycles <= '0;
      cnt_pf_wait_match_cycles <= '0;
      cnt_pf_wait_match_events <= '0;
      cnt_pf_queue_valid_cycles <= '0;
      cnt_pf_queue_block_cycles <= '0;
      cnt_pf_lookup_full_cycles <= '0;
      cnt_pf_rob_full_cycles <= '0;
      cnt_pf_pending_cycles <= '0;
      cnt_pf_stream_break <= '0;
      cnt_pf_future_keep <= '0;
      cnt_pf_queue_match_cycles <= '0;
      cnt_pf_rob_match_cycles <= '0;
      cnt_pf_page_wait_cycles <= '0;
      cnt_pf_late <= '0;
      cnt_pf_unused <= '0;
      demand_rob_blocked_q <= 1'b0;
      demand_pf_late_counted_q <= 1'b0;
      demand_pf_late_addr_q <= '0;
      demand_pf_promoted_q <= 1'b0;
      demand_pf_promoted_addr_q <= '0;
      demand_pf_wait_cnt_q <= '0;
      demand_pf_wait_addr_q <= '0;
    end else begin
      cnt_pf_probe_cycle <= cnt_pf_probe_cycle + 1'b1;

      if (axi_ar_valid_o && axi_ar_ready_i && vreq_is_load_d &&
          !prefetch_axi_ar_queue_pop) begin
        cnt_demand_ar <= cnt_demand_ar + 1;
        cnt_demand_bytes <= cnt_demand_bytes +
                            (($unsigned(axi_ar_o.len) + 64'd1) << axi_ar_o.size);
      end
      if (prefetch_axi_ar_queue_pop) begin
        cnt_prefetch_ar <= cnt_prefetch_ar + 1;
        cnt_prefetch_bytes <= cnt_prefetch_bytes +
                              (($unsigned(prefetch_axi_ar_data.len) + 64'd1) <<
                               prefetch_axi_ar_data.size);
      end
      if (prefetch_axi_ar_hit)
        cnt_prefetch_hit <= cnt_prefetch_hit + 1;
      if (pe_req_valid && addrgen_ack && is_load(pe_req.op))
        cnt_load_vinsn <= cnt_load_vinsn + 1;
      if (prefetch_en)
        cnt_prefetch_en <= cnt_prefetch_en + 1;
      if (prefetch_en && prefetch_adaptive_throttle)
        cnt_pf_throttled_cycles <= cnt_pf_throttled_cycles + 1;
      if (prefetch_axi_ar_queue_valid)
        cnt_pf_queue_valid_cycles <= cnt_pf_queue_valid_cycles + 1;
      if (prefetch_axi_ar_queue_valid &&
          !(prefetch_axi_ar_queue_pop || prefetch_axi_ar_queue_cancel))
        cnt_pf_queue_block_cycles <= cnt_pf_queue_block_cycles + 1;
      if (prefetch_axi_addr_lookup_fifo_full)
        cnt_pf_lookup_full_cycles <= cnt_pf_lookup_full_cycles + 1;
      if (prefetch_axi_ar_rob_full)
        cnt_pf_rob_full_cycles <= cnt_pf_rob_full_cycles + 1;
      if (prefetch_pending_d)
        cnt_pf_pending_cycles <= cnt_pf_pending_cycles + 1;
      if (axi_aw_valid_o && axi_aw_ready_i)
        cnt_demand_aw <= cnt_demand_aw + 1;

      // Prefetch suppression during demand unit-stride load start_req
      // (per-beat counts — a multi-beat load may count several times)
      if (vreq_is_vld && vreq_is_load_d && vreq_is_unit_stride_d &&
          !prefetch_axi_ar_hit && !axi_addrgen_queue_full && axi_ax_ready) begin
        if (!prefetch_en)
          cnt_pf_disabled <= cnt_pf_disabled + 1;
        else if (curr_req_page_crossed)
          cnt_pf_page_cross <= cnt_pf_page_cross + 1;
        else if (!prefetch_axi_ar_queue_not_full)
          cnt_pf_queue_full <= cnt_pf_queue_full + 1;
        else if (!prefetch_avl_enough)
          cnt_pf_avl_low <= cnt_pf_avl_low + 1;
      end

      // Prefetch AR issue drops — per-cycle counts of lost AR bandwidth
      if (axi_ar_ready_i && prefetch_axi_ar_queue_valid) begin
        if (prefetch_axi_ar_rob_full)
          cnt_pf_ar_rob_full <= cnt_pf_ar_rob_full + 1;
        if (prefetch_axi_addr_lookup_fifo_full)
          cnt_pf_ar_lookup_full <= cnt_pf_ar_lookup_full + 1;
        if (prefetch_pending_d)
          cnt_pf_ar_pending_block <= cnt_pf_ar_pending_block + 1;
        if (!prefetch_en)
          cnt_pf_ar_disabled <= cnt_pf_ar_disabled + 1;
      end

      // Demand blocked by prefetch ROB match (distinct events, not cycles)
      demand_rob_blocked_q <= vreq_is_vld && vreq_is_load_d && prefetch_wait_match;
      if (vreq_is_vld && vreq_is_load_d && prefetch_wait_match && !demand_rob_blocked_q) begin
        cnt_demand_rob_block <= cnt_demand_rob_block + 1;
        cnt_pf_wait_match_events <= cnt_pf_wait_match_events + 1;
      end
      if (vreq_is_vld && vreq_is_load_d && prefetch_wait_match) begin
        cnt_pf_wait_match_cycles <= cnt_pf_wait_match_cycles + 1;
        if (prefetch_axi_ar_queue_match)
          cnt_pf_queue_match_cycles <= cnt_pf_queue_match_cycles + 1;
        if (prefetch_axi_ar_rob_match)
          cnt_pf_rob_match_cycles <= cnt_pf_rob_match_cycles + 1;
      end
      if (prefetch_queue_promote) begin
        demand_pf_promoted_q <= 1'b1;
        demand_pf_promoted_addr_q <= vreq_addr_d;
      end else if (!(vreq_is_vld && vreq_is_load_d && prefetch_wait_match)) begin
        demand_pf_promoted_q <= 1'b0;
        demand_pf_promoted_addr_q <= '0;
      end
      // Strict late event: the exact prefetch was already issued before this
      // demand began waiting, but its complete data is not yet consumable.
      // A request issued only because this demand promoted it is coalescing, not
      // a late prefetch.
      if (vreq_is_vld && vreq_is_load_d && prefetch_wait_match &&
          prefetch_axi_ar_rob_match &&
          !(demand_pf_promoted_q &&
            (demand_pf_promoted_addr_q == vreq_addr_d))) begin
        if (!demand_pf_late_counted_q ||
            (demand_pf_late_addr_q != vreq_addr_d)) begin
          cnt_pf_late <= cnt_pf_late + 1;
          demand_pf_late_counted_q <= 1'b1;
          demand_pf_late_addr_q <= vreq_addr_d;
        end
      end else if (!(vreq_is_vld && vreq_is_load_d && prefetch_wait_match)) begin
        demand_pf_late_counted_q <= 1'b0;
        demand_pf_late_addr_q <= '0;
      end
      if (stream_break)
        cnt_pf_stream_break <= cnt_pf_stream_break + 1;
      if (prefetch_lookup_head_future_near)
        cnt_pf_future_keep <= cnt_pf_future_keep + 1;
      if (prefetch_flush_now) begin
        cnt_pf_unused <= cnt_pf_unused + 64'(prefetch_lookup_valid_use);
      end

      assert (prefetch_axi_ar_queue_empty == prefetch_stream_queue_empty)
        else $fatal(1, "[ADDRGEN] prefetch AR/stream queue desynchronized");
      assert (prefetch_axi_ar_queue_empty == prefetch_bytes_queue_empty)
        else $fatal(1, "[ADDRGEN] prefetch AR/byte-count queue desynchronized");
      assert (prefetch_axi_addr_lookup_fifo_empty ==
              !(|prefetch_lookup_slot_valid_q))
        else $fatal(1, "[ADDRGEN] prefetch lookup validity mirror desynchronized");
      assert (!(prefetch_axi_ar_queue_pop && prefetch_axi_ar_queue_cancel))
        else $fatal(1, "[ADDRGEN] prefetch queue issued and cancelled simultaneously");
      assert (!(prefetch_tag_full && axi_ar_valid_o && axi_ar_ready_i))
        else $fatal(1, "[ADDRGEN] accepted an AXI AR while the response tag FIFO was full");
      if ($past(rst_ni && prefetch_flush_now)) begin
        assert (prefetch_axi_ar_queue_empty &&
                prefetch_stream_queue_empty &&
                prefetch_bytes_queue_empty)
          else $fatal(1, "[ADDRGEN] queued prefetch state survived a recovery flush");
        assert (prefetch_axi_addr_lookup_fifo_empty &&
                (prefetch_lookup_slot_valid_q == '0) &&
                (prefetch_buf_occupancy_i == '0))
          else $fatal(1, "[ADDRGEN] completed prefetch state survived a recovery flush");
      end
      if ($past(rst_ni && prefetch_flush_now && hdv_task_end_i)) begin
        assert (task_end_cleaned_q)
          else $fatal(1, "[ADDRGEN] task-end prefetch cleanup did not latch");
      end
      if (prefetch_axi_ar_queue_cancel) begin
        assert (prefetch_axi_ar_queue_valid &&
                prefetch_axi_ar_queue_match)
          else $fatal(1, "[ADDRGEN] invalid prefetch queue cancellation");
      end
      if (prefetch_queue_promote) begin
        assert (prefetch_axi_ar_queue_pop && prefetch_axi_ar_rob_push &&
                axi_ar_valid_o && !prefetch_axi_ar_queue_cancel)
          else $fatal(1, "[ADDRGEN] promoted prefetch did not issue atomically");
      end
      if (prefetch_axi_ar_hit) begin
        assert (prefetch_first_logical_chunk &&
                (prefetch_axi_addr_lookup_fifo_data.addr ==
                 unit_stride_paddr) &&
                (prefetch_axi_addr_lookup_fifo_data.logical_bytes ==
                 prefetch_logical_load_bytes))
          else $fatal(1, "[ADDRGEN] prefetch hit did not cover the whole logical load");
      end

      // Demand should only wait for a matching prefetch briefly.  A long wait means
      // the matching lookup/ROB entry is no longer making forward progress.
      if (vreq_is_vld && vreq_is_load_d && prefetch_wait_match) begin
        if (!demand_rob_blocked_q || (demand_pf_wait_addr_q != vreq_addr_d)) begin
          demand_pf_wait_cnt_q <= '0;
          demand_pf_wait_addr_q <= vreq_addr_d;
        end else begin
          if (demand_pf_wait_cnt_q <
              DemandPrefetchWaitCounterWidth'(DemandPrefetchWaitWatchdogCycles)) begin
            demand_pf_wait_cnt_q <= demand_pf_wait_cnt_q + 1'b1;
          end
          assert (demand_pf_wait_cnt_q <
                  DemandPrefetchWaitCounterWidth'(DemandPrefetchWaitWatchdogCycles - 1))
            else $fatal(1, "[ADDRGEN] demand stuck waiting for prefetch: vaddr=0x%0h avl=%0d vl=%0d wait_cycles=%0d queue_match=%0d rob_match=%0d q_valid=%0d q_addr=0x%0h pending=%0d lookup_full=%0d",
                        vreq_addr_d, pe_req_d.avl, pe_req_d.vl, demand_pf_wait_cnt_q,
                        prefetch_axi_ar_queue_match, prefetch_axi_ar_rob_match,
                        prefetch_axi_ar_queue_valid, prefetch_axi_ar_data.addr,
                        prefetch_pending_d,
                        prefetch_axi_addr_lookup_fifo_full);
        end
      end else begin
        demand_pf_wait_cnt_q <= '0;
        demand_pf_wait_addr_q <= '0;
      end

      if ($test$plusargs("HDV_PF_PROBE") && (cnt_pf_probe_events < PfProbeMaxEvents)) begin
        if (vreq_is_vld && vreq_is_load_d && vreq_is_unit_stride_d &&
            !axi_addrgen_queue_full && axi_ax_ready &&
            !prefetch_wait_match) begin
          $display("[PFPROBE] cyc=%0d ev=demand_load paddr=0x%0h avl=%0d vl=%0d blen=%0d hit=%0d lkup_empty=%0d lkup_head=0x%0h q_valid=%0d q_head=0x%0h wait_match=%0d pending=%0d flush_pending=%0d throttle=%0d bad=%0d",
                   cnt_pf_probe_cycle, paddr, pe_req_d.avl, pe_req_d.vl, vreq_blen_d,
                   prefetch_axi_ar_hit, prefetch_axi_addr_lookup_fifo_empty,
                   prefetch_axi_addr_lookup_fifo_data.addr, prefetch_axi_ar_queue_valid,
                   prefetch_axi_ar_data.addr, prefetch_wait_match,
                   prefetch_pending_d, flush_pending_q, prefetch_adaptive_throttle,
                   prefetch_bad_cnt_q);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (vreq_is_vld && vreq_is_load_d && prefetch_wait_match) begin
          $display("[PFPROBE] cyc=%0d ev=demand_wait_pf vaddr=0x%0h avl=%0d vl=%0d queue_match=%0d rob_match=%0d",
                   cnt_pf_probe_cycle, vreq_addr_d, pe_req_d.avl, pe_req_d.vl,
                   prefetch_axi_ar_queue_match, prefetch_axi_ar_rob_match);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (prefetch_axi_ar_queue_push) begin
          $display("[PFPROBE] cyc=%0d ev=pf_gen demand=0x%0h pf_addr=0x%0h stream=0x%0h avl=%0d vl=%0d stride_bytes=%0d q_not_full=%0d page_cross=%0d",
                   cnt_pf_probe_cycle, paddr, prefetch_addr,
                   pe_req_d.hdv_meta.prefetch_stream_id, pe_req_d.avl, pe_req_d.vl,
                   prefetch_logical_stride_bytes, prefetch_axi_ar_queue_not_full,
                   prefetch_req_page_crossed);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (prefetch_axi_ar_queue_pop) begin
          $display("[PFPROBE] cyc=%0d ev=pf_issue addr=0x%0h len=%0d avl=%0d inflight=%0d buf_occ=%0d store_stuck=%0d",
                   cnt_pf_probe_cycle, prefetch_axi_ar_data.addr, prefetch_axi_ar_data.len,
                   pe_req_d.avl, prefetch_inflight_beats_q, prefetch_buf_occupancy_i,
                   store_stuck);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (prefetch_axi_ar_queue_cancel) begin
          $display("[PFPROBE] cyc=%0d ev=pf_queue_cancel addr=0x%0h stream=0x%0h avl=%0d vl=%0d",
                   cnt_pf_probe_cycle, prefetch_axi_ar_data.addr,
                   prefetch_stream_at_issue, pe_req_d.avl, pe_req_d.vl);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (prefetch_axi_ar_queue_valid &&
            !(prefetch_axi_ar_queue_pop || prefetch_axi_ar_queue_cancel)) begin
          $display("[PFPROBE] cyc=%0d ev=pf_block q_addr=0x%0h q_len=%0d avl=%0d iter_avl=%0d ready=%0d demand_ar=%0d rob_full=%0d lkup_full=%0d pending=%0d pf_en=%0d throttle=%0d flush=%0d credit_ok=%0d store_stuck=%0d same_iter=%0d lead_ok=%0d streams=%0d lead_budget=%0d inflight=%0d buf_occ=%0d",
                   cnt_pf_probe_cycle, prefetch_axi_ar_data.addr,
                   prefetch_axi_ar_data.len, pe_req_d.avl, prefetch_iter_avl_q,
                   axi_ar_ready_i, axi_ar_valid_o, prefetch_axi_ar_rob_full,
                   prefetch_axi_addr_lookup_fifo_full, prefetch_pending_d,
                   prefetch_en, prefetch_adaptive_throttle, flush_pending_q,
                   ((({2'b0, prefetch_buf_occupancy_i} << 1) + prefetch_inflight_beats_q
                     + $unsigned(prefetch_axi_ar_data.len) + 1) <= PrefetchBufBeats),
                   store_stuck, (pe_req_d.avl == prefetch_iter_avl_q),
                   ((({2'b0, prefetch_buf_occupancy_i} << 1) + prefetch_inflight_beats_q)
                    <= prefetch_lead_beats),
                   prefetch_active_stream_count_q, prefetch_lead_beats,
                   prefetch_inflight_beats_q, prefetch_buf_occupancy_i);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (prefetch_axi_addr_lookup_fifo_push) begin
          $display("[PFPROBE] cyc=%0d ev=pf_done_lkup addr=0x%0h stream=0x%0h len=%0d lkup_full=%0d inflight=%0d",
                   cnt_pf_probe_cycle, prefetch_axi_addr_lookup_fifo_datain.addr,
                   prefetch_axi_addr_lookup_fifo_datain.stream_id,
                   prefetch_axi_ar_rob_data.len, prefetch_axi_addr_lookup_fifo_full,
                   prefetch_inflight_beats_q);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (prefetch_axi_ar_hit) begin
          $display("[PFPROBE] cyc=%0d ev=pf_hit paddr=0x%0h stream=0x%0h avl=%0d vl=%0d",
                   cnt_pf_probe_cycle, paddr, pe_req_d.hdv_meta.prefetch_stream_id,
                   pe_req_d.avl, pe_req_d.vl);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (prefetch_lookup_head_future_near) begin
          $display("[PFPROBE] cyc=%0d ev=lookup_future_keep paddr=0x%0h lkup_head=0x%0h delta=%0d avl=%0d vl=%0d",
                   cnt_pf_probe_cycle, paddr, prefetch_axi_addr_lookup_fifo_data.addr,
                   prefetch_lookup_head_delta, pe_req_d.avl, pe_req_d.vl);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
        if (stream_break) begin
          $display("[PFPROBE] cyc=%0d ev=stream_break paddr=0x%0h lkup_head=0x%0h lkup_match=%0d avl=%0d vl=%0d",
                   cnt_pf_probe_cycle, paddr, prefetch_axi_addr_lookup_fifo_data.addr,
                   prefetch_lookup_match, pe_req_d.avl, pe_req_d.vl);
          cnt_pf_probe_events <= cnt_pf_probe_events + 1'b1;
        end
      end
    end
  end
  final begin
    $display("[PERF-ADDRGEN] demand_ar=%0d pf_ar=%0d pf_hit=%0d loads=%0d pf_en_cyc=%0d demand_aw=%0d demand_B=%0d pf_B=%0d",
             cnt_demand_ar, cnt_prefetch_ar, cnt_prefetch_hit, cnt_load_vinsn,
             cnt_prefetch_en, cnt_demand_aw, cnt_demand_bytes, cnt_prefetch_bytes);
    $display("[PERF-ADDRGEN-PF] pf_disabled=%0d pf_page_cross=%0d pf_queue_full=%0d pf_avl_low=%0d",
             cnt_pf_disabled, cnt_pf_page_cross, cnt_pf_queue_full, cnt_pf_avl_low);
    $display("[PERF-ADDRGEN-PF] pf_ar_rob_full=%0d pf_ar_lkup_full=%0d pf_ar_pending=%0d pf_ar_dis=%0d pf_2nd=%0d dem_rob_block=%0d",
             cnt_pf_ar_rob_full, cnt_pf_ar_lookup_full, cnt_pf_ar_pending_block,
             cnt_pf_ar_disabled, cnt_pf_second_issued, cnt_demand_rob_block);
    $display("[PERF-ADDRGEN-PF2] pf_throttle_cyc=%0d pf_late=%0d pf_unused=%0d pf_wait_match_cyc=%0d pf_wait_match_evt=%0d pf_queue_valid_cyc=%0d pf_queue_block_cyc=%0d pf_lkup_full_cyc=%0d pf_rob_full_cyc=%0d pf_pending_cyc=%0d pf_stream_break=%0d pf_future_keep=%0d pf_queue_match_cyc=%0d pf_rob_match_cyc=%0d pf_page_wait_cyc=%0d",
             cnt_pf_throttled_cycles, cnt_pf_late,
             cnt_pf_unused + 64'(prefetch_lookup_entry_use),
             cnt_pf_wait_match_cycles, cnt_pf_wait_match_events,
             cnt_pf_queue_valid_cycles,
             cnt_pf_queue_block_cycles, cnt_pf_lookup_full_cycles,
             cnt_pf_rob_full_cycles, cnt_pf_pending_cycles, cnt_pf_stream_break,
             cnt_pf_future_keep, cnt_pf_queue_match_cycles, cnt_pf_rob_match_cycles,
             cnt_pf_page_wait_cycles);
  end
  `endif

endmodule : addrgen
