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
    output axi_ar_t                        axi_addrgen_prefetch_req_o,
    output logic                           axi_addrgen_prefetch_req_valid_o,
    input  logic                           axi_addrgen_prefetch_req_ready_i,
    // Resident occupancy of the vldu prefetch R buffer, in 256-bit words.
    // Feeds the prefetch credit flow control (see PrefetchBufBeats).
    input  logic [7:0]                     prefetch_buf_occupancy_i,
    // Same-id order tag (is_prefetch per accepted AR) -> vldu R-beat demux.
    output logic                           prefetch_tag_head_o,
    output logic                           prefetch_tag_empty_o,
    input  logic                           prefetch_tag_pop_i,
    // High while the store unit has a vector store instruction in flight. Used to
    // gate the prefetch's inter-iteration drain ONLY when a store is actually stuck.
    input  logic                           store_pending_i,
    input  logic                           block_load_addr_i,
    input  logic                           hdv_loop_active_i,
    input  logic [1:0]                     hdv_prefetch_mode_i,
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

  // Prefetch mode from VLIWPU header imm20[18:17].  loop_active falling edge
  // clears internal state via loop_active_fall to drain queues on loop exit.
  logic loop_active_q;
  wire  loop_active_fall = loop_active_q && !hdv_loop_active_i;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) loop_active_q <= 1'b0;
    else         loop_active_q <= hdv_loop_active_i;
  end

  always_comb begin
    // Per-request prefetch_mode (pe_req.prefetch_mode, latched from HDV hint
    // at vq enqueue) may be stale if the global mode was disabled afterwards
    // (e.g. loop_exit).  Respect the current global mode as a gate: when the
    // global mode is off, per-request mode is ignored.  Non-HDV paths get
    // pe_req.prefetch_mode == 2'b00 → fall back to global.
    automatic logic [1:0] effective_mode;
    effective_mode = (hdv_prefetch_mode_i == 2'b00) ? 2'b00 :
                     (pe_req_d.prefetch_mode != 2'b00) ? pe_req_d.prefetch_mode
                                                       : hdv_prefetch_mode_i;
    unique case (effective_mode)
      2'b01:   prefetch_info = PF_EN_1X;
      2'b10:   prefetch_info = PF_EN_2X;
      2'b11:   prefetch_info = PF_EN_4X;
      default: prefetch_info = PF_DEN;
    endcase
    // On loop exit, disable prefetch to drain queues
    if (loop_active_fall) prefetch_info = PF_DEN;
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


  // In-flight prefetch beats: issued (ROB-pushed) but not yet landed in the
  // buffer (ROB-popped on the burst's last R beat). Added to the vldu's
  // resident occupancy to get the total beats committed to the buffer.
  logic [9:0] prefetch_inflight_beats_d, prefetch_inflight_beats_q;

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

  pe_req_t pe_req, pe_req_d, pe_req_q;
  logic    pe_req_valid;
  logic    addrgen_ack;

  fall_through_register_v1 #(
    .T(pe_req_t),
    .DEPTH(VaddrgenInsnQueueDepth)
  ) i_pe_req_register (
    .clk_i     (clk_i             ),
    .rst_ni    (rst_ni            ),
    .clr_i     (lsu_ex_flush_d    ),
    .testmode_i(1'b0              ),
    .data_i    (pe_req_i          ),
    .valid_i   (pe_req_valid_i_msk),
    .ready_o   (addrgen_ack_o     ),
    .data_o    (pe_req            ),
    .valid_o   (pe_req_valid      ),
    .ready_i   (addrgen_ack       )
  );

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
  logic    prefetch_axi_ar_queue_valid;
  logic    prefetch_axi_ar_queue_not_full;

  fall_through_register_v1 #(
    .T(axi_ar_t),
    .DEPTH(VaddrgenInsnQueueDepth)
  ) i_prefetch_axi_ar_queue (
    .clk_i     (clk_i                         ),
    .rst_ni    (rst_ni                        ),
    .clr_i     (lsu_ex_flush_d                ),
    .testmode_i(1'b0                          ),
    .data_i    (prefetch_axi_ar_queue_datain  ),
    .valid_i   (prefetch_axi_ar_queue_push    ),
    .ready_o   (prefetch_axi_ar_queue_not_full),
    .data_o    (prefetch_axi_ar_data          ),
    .valid_o   (prefetch_axi_ar_queue_valid   ),
    .ready_i   (prefetch_axi_ar_queue_pop     )
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
  axi_addr_t prefetch_axi_ar_rob_pop_done_addr_d, prefetch_axi_ar_rob_pop_done_addr_q;
  logic    prefetch_axi_ar_rob_pop_done_counter_d, prefetch_axi_ar_rob_pop_done_counter_q;
  // Declared here (ahead of its later siblings) so the pop_done_counter always_comb
  // below can gate on it; it marks an in-flight page-cross prefetch window.
  logic    second_prefetch_vld_compare_d, second_prefetch_vld_compare_q;

  axi_addr_t prefetch_axi_addr_lookup_fifo_datain, prefetch_axi_addr_lookup_fifo_data;
  logic      prefetch_axi_addr_lookup_fifo_push;
  logic      prefetch_axi_addr_lookup_fifo_pop;
  logic      prefetch_axi_addr_lookup_fifo_full;
  logic      prefetch_axi_addr_lookup_fifo_empty;
  
  axi_ar_t   prefetch_axi_ar_rob_mem[VaddrgenInsnQueueDepth];
  logic      prefetch_axi_ar_rob_vld[VaddrgenInsnQueueDepth];
  logic      prefetch_axi_ar_rob_match;

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

  // ── Page-cross segment tag, carried in lockstep with the prefetch AR ───────
  // A prefetch burst that crosses a page is split into two short segments (the
  // in-page 1st part + the next-page 2nd part). The page-cross pairing logic
  // below must know which completing ROB entries are such segments. The old
  // test `len != 7` inferred that from the m1 full-burst length (8 beats) and
  // mis-classified any LMUL>1 full burst (len 15/31/63) as a segment, wrongly
  // toggling the pairing counter when a full burst completed inside a crossing
  // window. Instead tag each AR at generation (1st segment = page-crossed,
  // 2nd segment = 1, full burst = 0) and carry the tag through a queue + ROB
  // mirroring the AR's, so the pairing keys off the real flag for any LMUL.
  logic prefetch_seg_queue_datain, prefetch_seg_at_issue, prefetch_seg_rob_data;

  fall_through_register_v1 #(
    .T(logic),
    .DEPTH(VaddrgenInsnQueueDepth)
  ) i_prefetch_seg_queue (
    .clk_i     (clk_i                       ),
    .rst_ni    (rst_ni                      ),
    .clr_i     (lsu_ex_flush_d              ),
    .testmode_i(1'b0                        ),
    .data_i    (prefetch_seg_queue_datain   ),
    .valid_i   (prefetch_axi_ar_queue_push  ),
    .ready_o   (                            ),
    .data_o    (prefetch_seg_at_issue       ),
    .valid_o   (                            ),
    .ready_i   (prefetch_axi_ar_queue_pop   )
  );

  fifo_v5 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(logic                 )
  ) i_prefetch_seg_rob (
    .clk_i     (clk_i                     ),
    .rst_ni    (rst_ni                    ),
    .flush_i   (1'b0                      ),
    .testmode_i(1'b0                      ),
    .data_i    (prefetch_seg_at_issue     ),
    .push_i    (prefetch_axi_ar_rob_push  ),
    .full_o    (                          ),
    .data_o    (prefetch_seg_rob_data     ),
    .pop_i     (prefetch_axi_ar_rob_pop   ),
    .empty_o   (                          ),
    .mem_o     (                          ),
    .vld_o     (                          ),
    .usage_o   (                          )
  );

  assign axi_addrgen_prefetch_req_valid_o = !prefetch_axi_ar_rob_empty;
  assign axi_addrgen_prefetch_req_o       = prefetch_axi_ar_rob_data;
  assign prefetch_axi_ar_rob_pop          = axi_addrgen_prefetch_req_ready_i;

  always_comb begin
    prefetch_axi_ar_rob_pop_done_counter_d = prefetch_axi_ar_rob_pop_done_counter_q;
    prefetch_axi_ar_rob_pop_done_addr_d = prefetch_axi_ar_rob_pop_done_addr_q;
    // The page-cross pairing counter must only respond to genuine page-cross
    // prefetch segments, NOT to full (non-crossing) bursts. prefetch_seg_rob_data
    // is the per-ROB-entry tag (1 = page-cross 1st/2nd segment, 0 = full burst),
    // replacing the old `len != 7` which assumed an 8-beat m1 full burst and
    // mis-tagged any LMUL>1 full burst (len 15/31/63) as a segment. It is further
    // gated by second_prefetch_vld_compare_q, asserted exactly across a page-cross
    // window (set when the crossing prefetch is generated, cleared when its 2nd
    // segment completes); the two segments are adjacent in the in-order ROB.
    // Without the seg tag a full burst completing inside the window would toggle
    // the counter with no partner, wedging the demand path or truncating a load.
    if (prefetch_seg_rob_data && axi_addrgen_prefetch_req_ready_i
        && second_prefetch_vld_compare_q) begin
      prefetch_axi_ar_rob_pop_done_counter_d = ~prefetch_axi_ar_rob_pop_done_counter_q;
    end
    if (prefetch_axi_ar_rob_pop_done_counter_d) begin
      prefetch_axi_ar_rob_pop_done_addr_d = prefetch_axi_ar_rob_data.addr;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      prefetch_axi_ar_rob_pop_done_counter_q <= '0;
      prefetch_axi_ar_rob_pop_done_addr_q    <= '0;
    end else begin
      prefetch_axi_ar_rob_pop_done_counter_q <= prefetch_axi_ar_rob_pop_done_counter_d;
      prefetch_axi_ar_rob_pop_done_addr_q    <= prefetch_axi_ar_rob_pop_done_addr_d;
    end
  end

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



  fifo_v3 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(axi_addr_t            )
  ) i_prefetch_axi_addr_lookup_fifo (
    .clk_i     (clk_i                      ),
    .rst_ni    (rst_ni                     ),
    .flush_i   (1'b0                       ),
    .testmode_i(1'b0                       ),
    .data_i    (prefetch_axi_addr_lookup_fifo_datain),
    .push_i    (prefetch_axi_addr_lookup_fifo_push ),
    .full_o    (prefetch_axi_addr_lookup_fifo_full ),
    .data_o    (prefetch_axi_addr_lookup_fifo_data ),
    .pop_i     (prefetch_axi_addr_lookup_fifo_pop  ),
    .empty_o   (prefetch_axi_addr_lookup_fifo_empty),
    .usage_o   (/* Unused */             )
  );

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
  logic [31:0]             num_beats;
  logic [31:0]             burst_length;
  logic [NrLanes-1:0]      addrgen_operand_valid;
  logic                    curr_req_page_crossed;
  logic                    curr_req_page_crossed_next;

  logic [31:0]             prefetch_num_beats;
  logic [31:0]             prefetch_num_bytes;
  logic [31:0]             prefetch_burst_length;
  logic                    prefetch_req_page_crossed;
  axi_addr_t               prefetch_addr;
  axi_addr_t               prefetch_aligned_start_addr;
  axi_addr_t               prefetch_aligned_end_addr;
  axi_addr_t               prefetch_aligned_next_start_addr;
  
  logic [($bits(axi_addr_t) - 12)-1:0] prefetch_next_2page_msb;
  
  logic second_prefetch_vld_d, second_prefetch_vld_q;
  logic [31:0] second_prefetch_burst_len_d, second_prefetch_burst_len_q;
  axi_addr_t   second_prefetch_paddr_d, second_prefetch_paddr_q;

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
    page_crossed = 1'b0;
    // The final address can be found similarly...
    if (num_bytes >= max_burst_bytes) begin
        aligned_next_start_addr = aligned_addr(addr + max_burst_bytes, eff_axi_dw_log);
    end else begin
        aligned_next_start_addr = aligned_addr(addr + num_bytes - 1, eff_axi_dw_log) + eff_axi_dw;
    end
    aligned_end_addr = aligned_next_start_addr - 1;
    // But since AXI requests are aligned in 4 KiB pages, aligned_end_addr must be in the
    // same page as aligned_start_addr
    if (aligned_start_addr[AxiAddrWidth-1:12] != aligned_end_addr[AxiAddrWidth-1:12]) begin
        aligned_end_addr        = {aligned_start_addr[AxiAddrWidth-1:12], 12'hFFF};
        aligned_next_start_addr = {                     next_2page_msb  , 12'h000};
        page_crossed = 1'b1;
    end
  endfunction

  assign axi_addr_misalignment = vreq_addr_d[clog2_AxiStrobeWidth-1:0];

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
    prefetch_pending_d         = '0;
    prefetch_axi_ar_queue_datain = '0;
    prefetch_seg_queue_datain  = 1'b0;
    prefetch_axi_ar_queue_push = '0;
    prefetch_axi_ar_queue_pop  = '0;
    prefetch_iter_avl_d        = prefetch_iter_avl_q; // hold the prefetched iteration

    prefetch_axi_ar_rob_push             = '0;
    prefetch_axi_ar_rob_datain           = '0;
    prefetch_axi_ar_rob_match            = 1'b0;
    prefetch_axi_addr_lookup_fifo_push   = '0;
    prefetch_axi_addr_lookup_fifo_pop    = '0;
    prefetch_axi_addr_lookup_fifo_datain = '0;

    curr_req_page_crossed                = '0;
    curr_req_page_crossed_next           = '0;

    prefetch_num_beats               = '0;
    prefetch_burst_length            = '0;
    prefetch_req_page_crossed        = 1'b0;
    prefetch_addr                    = '0;
    prefetch_num_bytes               = '0;
    prefetch_aligned_start_addr      = '0;
    prefetch_aligned_end_addr        = '0;
    prefetch_aligned_next_start_addr = '0;
    prefetch_next_2page_msb          = '0;

    second_prefetch_vld_d         = second_prefetch_vld_q;
    second_prefetch_vld_compare_d = second_prefetch_vld_compare_q;
    second_prefetch_burst_len_d   = second_prefetch_burst_len_q;
    second_prefetch_paddr_d       = second_prefetch_paddr_q;

    case(state_q)
    IDLE: begin : addrgen_state_IDLE
      if (pe_req_valid && (is_load(pe_req.op) || is_store(pe_req.op)) && !vinsn_running_q[pe_req.id]) begin : register_req
        pe_req_d                     = pe_req;
        vinsn_running_d[pe_req_d.id] = 1'b1;
        addrgen_ack                  = 1'b1;

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

    for (int i = 0; i < VaddrgenInsnQueueDepth; i++) begin
      if (prefetch_axi_ar_rob_vld[i] &&
          (prefetch_axi_ar_rob_mem[i].addr  == vreq_addr_d)) begin
        prefetch_axi_ar_rob_match = 1'b1;
      end
    end

    if ((prefetch_seg_rob_data && axi_addrgen_prefetch_req_ready_i) && prefetch_axi_ar_rob_pop_done_counter_q) begin
      second_prefetch_vld_compare_d = '0;
    end

    prefetch_axi_ar_rob_match |= second_prefetch_vld_compare_q;

    if (vreq_is_vld &&
        //!(vreq_is_load_d && block_load_addr_i) &&
        !(vreq_is_load_d && (prefetch_axi_ar_rob_match || prefetch_axi_ar_rob_pop_done_counter_d)) &&
        !second_prefetch_vld_q) begin : demand_req
      if (!axi_addrgen_queue_full && axi_ax_ready) begin : start_req
        paddr = (en_ld_st_translation_i) ? mmu_paddr_i : vreq_addr_d;

        if (!prefetch_axi_addr_lookup_fifo_empty &&
            (paddr == prefetch_axi_addr_lookup_fifo_data) &&
            vreq_is_unit_stride_d) begin
          prefetch_axi_ar_hit               = 1'b1;
          prefetch_axi_addr_lookup_fifo_pop = 1'b1;
        end

        if (is_addr_error(paddr, pe_req_d.vtype.vsew[1:0])) begin
          state_d                   = IDLE;
          addrgen_ack               = 1'b1;
          addrgen_exception_o.valid = 1'b1;
          addrgen_exception_o.cause = riscv::ILLEGAL_INSTR;
          addrgen_exception_o.tval  = '0;
        end else begin
          if (vreq_is_unit_stride_d) begin : unit_stride_req

            aligned_start_addr_d = aligned_addr(paddr, clog2_AxiStrobeWidth);
            next_2page_msb_d     = aligned_start_addr_d[AxiAddrWidth-1:12] + 1;
            set_end_addr (
              next_2page_msb_d,
              vreq_blen_d,
              paddr,
              AxiDataWidth/8,
              clog2_AxiStrobeWidth,
              aligned_start_addr_d,
              aligned_end_addr_d,
              aligned_next_start_addr_d,
              curr_req_page_crossed
            );

            if (pe_req_d.vstart != 0 && !vreq_is_load_d) begin
              eff_axi_dw_d     = 1 << pe_req_d.vtype.vsew[1:0];
              eff_axi_dw_log_d = pe_req_d.vtype.vsew[1:0];
            end else if ((paddr[clog2_AxiStrobeWidth-1:0] != '0) && !vreq_is_load_d) begin
              eff_axi_dw_d     = {1'b0, narrow_axi_data_bwidth};
              eff_axi_dw_log_d = zeroes_cnt;
            end else begin
              eff_axi_dw_d     = AxiDataWidth/8;
              eff_axi_dw_log_d = clog2_AxiStrobeWidth;
            end

            if (curr_req_page_crossed) begin
              num_bytes = 13'h1000 - paddr[11:0];
            end else begin
              num_bytes = aligned_end_addr_d[11:0] - paddr[11:0] + 1;
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
                addr   : paddr,
                len    : burst_length - 1,
                size   : eff_axi_dw_log_d,
                cache  : CACHE_MODIFIABLE,
                burst  : BURST_INCR,
                default: '0
              };

              if (prefetch_axi_ar_hit) begin
                axi_ar_o = '0;
              end

              if ((pe_req_d.avl >= (pe_req_d.vl << 1)) &&
                  prefetch_axi_ar_queue_not_full &&
                  prefetch_en &&
                  !curr_req_page_crossed) begin : first_prefetch
                prefetch_addr = paddr + (num_bytes << prefetch_mul);

                prefetch_aligned_start_addr = aligned_addr(prefetch_addr, eff_axi_dw_log_d);
                // MSB of the page that follows the prefetch start. The demand
                // path computes its next_2page_msb the same way; the prefetch
                // path left it at 0, so a page-crossing prefetch sent its second
                // segment to address {0,12'h0}=0 and the page-crossing iteration
                // missed (and issued a bogus read to address 0).
                prefetch_next_2page_msb = prefetch_aligned_start_addr[AxiAddrWidth-1:12] + 1'b1;

                set_end_addr (
                  prefetch_next_2page_msb,
                  vreq_blen_d,
                  prefetch_addr,
                  eff_axi_dw_d,
                  eff_axi_dw_log_d,
                  prefetch_aligned_start_addr,
                  prefetch_aligned_end_addr,
                  prefetch_aligned_next_start_addr,
                  prefetch_req_page_crossed
                );
              
                prefetch_num_beats = ((prefetch_aligned_end_addr[11:0] - prefetch_aligned_start_addr[11:0]) >> eff_axi_dw_log_d) + 1;
                prefetch_burst_length = (prefetch_num_beats < 256) ? prefetch_num_beats : 256;
              
                if (prefetch_burst_length != 0) begin
                  prefetch_axi_ar_queue_datain = '{
                    id     : AXI_ID_DEMAND,   // same-id: prefetch shares demand id
                    addr   : prefetch_addr,
                    len    : prefetch_burst_length - 1,
                    size   : eff_axi_dw_log_d,
                    cache  : CACHE_MODIFIABLE,
                    burst  : BURST_INCR,
                    default: '0
                  };
              
                  prefetch_axi_ar_queue_push = 1'b1;
                  // This AR is a page-cross 1st segment iff the prefetch crosses
                  // a page; otherwise it is a full (non-segment) burst.
                  prefetch_seg_queue_datain  = prefetch_req_page_crossed;
                  prefetch_pending_d         = 1'b1;
                end

                if (prefetch_req_page_crossed) begin
                  second_prefetch_vld_d   = 1'b1;
                  second_prefetch_vld_compare_d = 1'b1;
                  second_prefetch_paddr_d = prefetch_aligned_next_start_addr;
                  // Next-page segment length = total intended beats minus the
                  // in-page first segment, as an AXI len (beats-1). Was hard-coded
                  // (7 - first), i.e. assuming every prefetch is exactly 8 beats
                  // (true only for vl=32/e32); derive it from the real burst size.
                  second_prefetch_burst_len_d =
                      (vreq_blen_d >> eff_axi_dw_log_d) - prefetch_burst_length - 1;
                end
              end : first_prefetch

            end
            else begin
              axi_aw_o = '{
                id     : AXI_ID_DEMAND,
                addr   : paddr,
                len    : burst_length - 1,
                size   : eff_axi_dw_log_d,
                cache  : CACHE_MODIFIABLE,
                burst  : BURST_INCR,
                default: '0
              };
            end

            axi_addrgen_queue = '{
              addr         : paddr,
              len          : burst_length - 1,
              size         : eff_axi_dw_log_d,
              is_load      : vreq_is_load_d,
              is_exception : 1'b0
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
              addr         : paddr,
              size         : pe_req_d.vtype.vsew[1:0],
              len          : 0,
              is_load      : vreq_is_load_d,
              is_exception : 1'b0
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
              addr         : paddr,
              size         : pe_req_d.vtype.vsew[1:0],
              len          : 0,
              is_load      : vreq_is_load_d,
              is_exception : 1'b0
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
            addr         : paddr,
            size         : pe_req_d.vtype.vsew[1:0],
            len          : 0,
            is_load      : vreq_is_load_d,
            is_exception : 1'b1
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
            if (paddr == prefetch_axi_ar_rob_pop_done_addr_q) begin
              vreq_blen_d = '0;
            end

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
    else if (second_prefetch_vld_q) begin : second_prefetch

      prefetch_axi_ar_queue_datain = '{
        id     : AXI_ID_DEMAND,   // same-id: prefetch shares demand id
        addr   : second_prefetch_paddr_d,
        len    : second_prefetch_burst_len_d,
        size   : eff_axi_dw_log_d,
        cache  : CACHE_MODIFIABLE,
        burst  : BURST_INCR,
        default: '0
      };
      
      prefetch_axi_ar_queue_push = 1'b1;
      prefetch_seg_queue_datain  = 1'b1; // 2nd (next-page) segment of a crossing
      second_prefetch_vld_d = 1'b0;
    end : second_prefetch


    // Demand AR has priority on the single AR port. The demand path above may
    // already be driving axi_ar_valid_o this cycle; the prefetch drain must NOT
    // override it (that would silently drop the demand AR while its
    // ldu_addrgen_queue entry still waits for id=DEMAND R beats). Prefetch ARs
    // only fill the cycles where demand is not using the bus.
    if (axi_ar_ready_i &&
        !axi_ar_valid_o &&
        prefetch_axi_ar_queue_valid &&
        !prefetch_axi_ar_rob_full && !prefetch_axi_addr_lookup_fifo_full &&
        !prefetch_pending_d
        && prefetch_en
        // Credit: only issue if the buffer can still absorb this burst on top of
        // what is already resident (occupancy*2 beats) and in flight. Guarantees
        // the landing R beats never overflow / back-pressure into deadlock.
        && ((({2'b0, prefetch_buf_occupancy_i} << 1) + prefetch_inflight_beats_q
             + $unsigned(prefetch_axi_ar_data.len) + 1) <= PrefetchBufBeats)
        // Wait-per-iteration pacing: issue freely while still in the current iteration
        // (avl unchanged), but on a NEW iteration (avl differs) wait until the previous
        // iteration's prefetch beats have fully drained (in-flight == 0). The drain
        // gap frees the single memory port for demand stores (vsaxpy).
        // Store-aware: only pace the prefetch (drain between iterations) while a
        // store is STARVED; otherwise run free so store-light loops (vvaddint32) pay
        // no penalty. When starved, fall back to the per-iteration drain that frees
        // the memory port for the store (vsaxpy).
        && (!store_stuck
            || (pe_req_d.avl == prefetch_iter_avl_q)
            || (prefetch_inflight_beats_q == '0))
    ) begin : prefetch_req
      prefetch_axi_ar_queue_pop  = 1'b1;
      prefetch_axi_ar_rob_push   = 1'b1;
      prefetch_axi_ar_rob_datain = prefetch_axi_ar_data;
      axi_ar_valid_o             = 1'b1;
      axi_ar_o                   = prefetch_axi_ar_data;
      prefetch_iter_avl_d        = pe_req_d.avl; // mark the iteration we prefetched
    end : prefetch_req

    // Record each completing prefetch burst's OWN start address into the lookup
    // FIFO. A page-crossing prefetch is split into two ROB entries (in-page part
    // + next-page second_prefetch part) and the matching demand also splits into
    // two segments at the page boundary, so BOTH addresses must be recorded --
    // one push per completed burst keyed by that burst's address. The previous
    // pop_done_counter scheme pushed only one entry per crossed pair, so the
    // first segment of every page-crossing iteration missed.
    if (!prefetch_axi_ar_rob_empty &&
        !prefetch_axi_addr_lookup_fifo_full &&
        axi_addrgen_prefetch_req_ready_i) begin : prefetch_data_complete
      prefetch_axi_addr_lookup_fifo_push   = 1'b1;
      prefetch_axi_addr_lookup_fifo_datain = prefetch_axi_ar_rob_data.addr;
    end : prefetch_data_complete

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
      second_prefetch_vld_q      <= '0;
      second_prefetch_vld_compare_q <= '0;
      second_prefetch_burst_len_q <= '0;
      second_prefetch_paddr_q    <= '0;
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
      second_prefetch_vld_q      <= second_prefetch_vld_d;
      second_prefetch_vld_compare_q <= second_prefetch_vld_compare_d;
      second_prefetch_burst_len_q<= second_prefetch_burst_len_d;
      second_prefetch_paddr_q    <= second_prefetch_paddr_d;
    end
  end

  `ifdef FOR_VERIFY
  // ── Performance counters for quantitative analysis ────────────────────
  logic [63:0] cnt_demand_ar;       // demand AXI read requests issued
  logic [63:0] cnt_prefetch_ar;     // prefetch AXI read requests issued
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
  logic [63:0] cnt_pf_avl_low;      // avl < vl*2 (not enough elements left to prefetch)
  // Prefetch AR issue drops — prefetch was queued but AR not sent this cycle.
  logic [63:0] cnt_pf_ar_rob_full;      // ROB full
  logic [63:0] cnt_pf_ar_lookup_full;   // addr-lookup FIFO full
  logic [63:0] cnt_pf_ar_pending_block; // prefetch_pending_d still set
  logic [63:0] cnt_pf_ar_disabled;      // prefetch_en went off before issue
  // Other
  logic [63:0] cnt_pf_second_issued; // second (page-cross) prefetch issued
  logic [63:0] cnt_demand_rob_block; // demand AR blocked by ROB match (events)
  logic        demand_rob_blocked_q;  // debounce: demand was ROB-blocked last cycle

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cnt_demand_ar <= '0; cnt_prefetch_ar <= '0; cnt_prefetch_hit <= '0;
      cnt_load_vinsn <= '0; cnt_prefetch_en <= '0; cnt_demand_aw <= '0;
      cnt_demand_bytes <= '0; cnt_prefetch_bytes <= '0;
      cnt_pf_disabled <= '0; cnt_pf_page_cross <= '0;
      cnt_pf_queue_full <= '0; cnt_pf_avl_low <= '0;
      cnt_pf_ar_rob_full <= '0; cnt_pf_ar_lookup_full <= '0;
      cnt_pf_ar_pending_block <= '0; cnt_pf_ar_disabled <= '0;
      cnt_pf_second_issued <= '0; cnt_demand_rob_block <= '0;
      demand_rob_blocked_q <= 1'b0;
    end else begin
      if (axi_ar_valid_o && axi_ar_ready_i && vreq_is_load_d) begin
        cnt_demand_ar <= cnt_demand_ar + 1;
        cnt_demand_bytes <= cnt_demand_bytes + (eff_axi_dw_d * (burst_length));
      end
      if (prefetch_axi_ar_queue_push) begin
        cnt_prefetch_ar <= cnt_prefetch_ar + 1;
        cnt_prefetch_bytes <= cnt_prefetch_bytes + (eff_axi_dw_d * (prefetch_burst_length > 0 ? prefetch_burst_length : 1));
      end
      if (prefetch_axi_ar_hit)
        cnt_prefetch_hit <= cnt_prefetch_hit + 1;
      if (pe_req_valid && addrgen_ack && is_load(pe_req.op))
        cnt_load_vinsn <= cnt_load_vinsn + 1;
      if (prefetch_en)
        cnt_prefetch_en <= cnt_prefetch_en + 1;
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
        else if (!(pe_req_d.avl >= (pe_req_d.vl << 1)))
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

      if (second_prefetch_vld_d && !second_prefetch_vld_q)
        cnt_pf_second_issued <= cnt_pf_second_issued + 1;

      // Demand blocked by prefetch ROB match (distinct events, not cycles)
      demand_rob_blocked_q <= vreq_is_vld && vreq_is_load_d && prefetch_axi_ar_rob_match;
      if (vreq_is_vld && vreq_is_load_d && prefetch_axi_ar_rob_match && !demand_rob_blocked_q)
        cnt_demand_rob_block <= cnt_demand_rob_block + 1;
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
  end
  `endif
endmodule : addrgen
