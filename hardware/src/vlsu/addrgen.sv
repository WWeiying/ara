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
    output addrgen_axi_req_t               axi_addrgen_req_o,
    output logic                           axi_addrgen_req_valid_o,
    input  logic                           ldu_axi_addrgen_req_ready_i,
    input  logic                           stu_axi_addrgen_req_ready_i,
    // Interface with the lanes (for scatter/gather operations)
    input  elen_t            [NrLanes-1:0] addrgen_operand_i,
    input  logic             [NrLanes-1:0] addrgen_operand_valid_i,
    output logic                           addrgen_operand_ready_o,
    // Indexed LSU exception support
    input  logic                           lsu_ex_flush_i
  );

  localparam unsigned DataWidth = $bits(elen_t);
  localparam unsigned DataWidthB = DataWidth / 8;

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
    .DEPTH(3)
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

  ////////////////////
  //  PE Req Queue  //
  ////////////////////

  // The address generation process interacts with another process, that
  // generates the AXI requests. They interact through the following signals.
  typedef struct packed {
    axi_addr_t addr;
    vlen_t len;
    elen_t stride;
    logic [1:0] vew; // Support only up to 64-bit
    logic is_load;
    logic is_burst; // Unit-strided instructions can be converted into AXI INCR bursts
    logic fault_only_first; // Fault-only-first instruction
    vlen_t vstart;
  } addrgen_req_t;
  addrgen_req_t addrgen_req;
  logic         addrgen_req_valid;
  logic         addrgen_req_ready;

  /////////////////////
  //  Address Queue  //
  /////////////////////

  // Address queue for the vector load/store units
  addrgen_axi_req_t axi_addrgen_queue;
  logic             axi_addrgen_queue_push;
  logic             axi_addrgen_queue_full;
  logic             axi_addrgen_queue_empty;
  logic             axi_addrgen_queue_pop;

  assign axi_addrgen_queue_pop = ldu_axi_addrgen_req_ready_i | stu_axi_addrgen_req_ready_i;

  fifo_v3 #(
    .DEPTH(VaddrgenInsnQueueDepth),
    .dtype(addrgen_axi_req_t     )
  ) i_addrgen_req_queue (
    .clk_i     (clk_i                  ),
    .rst_ni    (rst_ni                 ),
    .flush_i   (1'b0                   ),
    .testmode_i(1'b0                   ),
    .data_i    (axi_addrgen_queue      ),
    .push_i    (axi_addrgen_queue_push ),
    .full_o    (axi_addrgen_queue_full ),
    .data_o    (axi_addrgen_req_o      ),
    .pop_i     (axi_addrgen_queue_pop  ),
    .empty_o   (axi_addrgen_queue_empty),
    .usage_o   (/* Unused */           )
  );
  assign axi_addrgen_req_valid_o = !axi_addrgen_queue_empty;

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
  logic [CVA6Cfg.PLEN-1:0] paddr;
  logic [31:0]             num_beats;
  logic [31:0]             burst_length;
  logic [NrLanes-1:0]      addrgen_operand_valid;

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
      input  logic [($bits(axi_addr_t) - 12)-1:0]       next_2page_msb,
      input  vlen_t                                     num_bytes,
      input  axi_addr_t                                 addr,
      input  logic [clog2_AxiStrobeWidth:0]             eff_axi_dw,
      input  logic [idx_width(clog2_AxiStrobeWidth):0]  eff_axi_dw_log,
      input  axi_addr_t                                 aligned_start_addr,
      output axi_addr_t                                 aligned_end_addr,
      output axi_addr_t                                 aligned_next_start_addr
  );
    automatic int unsigned max_burst_bytes = 256 << eff_axi_dw_log;
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

  always_comb begin
    state_d = state_q;
    pe_req_d = pe_req_q;
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

    addrgen_req_ready = 1'b0;

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

    vreq_is_vld       = 1'b0;
    addrgen_ack       = 1'b0;
    vreq_addr_d       = vreq_addr_q;
    vreq_blen_d       = vreq_blen_q;
    vreq_is_load_d    = vreq_is_load_q;
    vreq_is_unit_stride_d = vreq_is_unit_stride_q;
    vreq_is_stride_d      = vreq_is_stride_q;
    vreq_is_index_d       = vreq_is_index_q;
    axi_ax_ready      = 1'b0;
    num_bytes         = '0;
    remaining_bytes   = '0;
    paddr             = '0;
    num_beats         = '0;
    burst_length      = '0;

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
          state_d = ADDRGEN;
          vreq_addr_d     = pe_req_d.scalar_op + (pe_req_d.vstart << unsigned'(pe_req_d.vtype.vsew));

        end : IDLE_VLSE_VLD
        else if (vreq_is_stride_d) begin : IDLE_VLSSE_VLD
          state_d = ADDRGEN;
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

    if ((axi_addrgen_queue_empty || (axi_addrgen_req_o.is_load && vreq_is_load_d) ||
        (~axi_addrgen_req_o.is_load && ~vreq_is_load_d)) && vreq_is_vld) begin : can_req
      if (!axi_addrgen_queue_full && axi_ax_ready) begin : start_req
        paddr = (en_ld_st_translation_i) ? mmu_paddr_i : vreq_addr_d;

        if (vreq_is_unit_stride_d) begin : unit_stride_req

          aligned_start_addr_d = aligned_addr(vreq_addr_d, clog2_AxiStrobeWidth);
          next_2page_msb_d     = aligned_start_addr_d[AxiAddrWidth-1:12] + 1;
          set_end_addr (
            next_2page_msb_d,
            vreq_blen_d,
            vreq_addr_d,
            AxiDataWidth/8,
            clog2_AxiStrobeWidth,
            aligned_start_addr_d,
            aligned_end_addr_d,
            aligned_next_start_addr_d
          );

          if (pe_req_d.vstart != 0 && !vreq_is_load_d) begin
            eff_axi_dw_d     = 1 << pe_req_d.vtype.vsew[1:0];
            eff_axi_dw_log_d = pe_req_d.vtype.vsew[1:0];
          end else if ((vreq_addr_d[clog2_AxiStrobeWidth-1:0] != '0) && !vreq_is_load_d) begin
            eff_axi_dw_d     = {1'b0, narrow_axi_data_bwidth};
            eff_axi_dw_log_d = zeroes_cnt;
          end else begin
            eff_axi_dw_d     = AxiDataWidth/8;
            eff_axi_dw_log_d = clog2_AxiStrobeWidth;
          end

          if (aligned_end_addr_d[11:0] != 12'hFFF) begin
            num_bytes = aligned_next_start_addr_d[11:0] - vreq_addr_d[11:0];
          end else begin
            num_bytes = 13'h1000 - vreq_addr_d[11:0];
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
              addr   : paddr,
              len    : burst_length - 1,
              size   : eff_axi_dw_log_d,
              cache  : CACHE_MODIFIABLE,
              burst  : BURST_INCR,
              default: '0
            };
          end
          else begin
            axi_aw_o = '{
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
              addr   : vreq_addr_d,
              len    : 0,
              size   : pe_req_d.vtype.vsew[1:0],
              cache  : CACHE_MODIFIABLE,
              burst  : BURST_INCR,
              default: '0
            };
          end
          else begin
            axi_aw_o = '{
              addr   : vreq_addr_d,
              len    : 0,
              size   : pe_req_d.vtype.vsew[1:0],
              cache  : CACHE_MODIFIABLE,
              burst  : BURST_INCR,
              default: '0
            };
          end

          axi_addrgen_queue = '{
            addr         : vreq_addr_d,
            size         : pe_req_d.vtype.vsew[1:0],
            len          : 0,
            is_load      : vreq_is_load_d,
            is_exception : 1'b0
          };

          len_temp = vreq_blen_d - (1 << pe_req_d.vtype.vsew[1:0]);
          next_addr_strided_temp = vreq_addr_d + pe_req_d.stride;
        end : stride_req
        else begin : index_req

          if (vreq_is_load_d) begin
            axi_ar_o = '{
              addr   : vreq_addr_d,
              len    : 0,
              size   : pe_req_d.vtype.vsew[1:0],
              cache  : CACHE_MODIFIABLE,
              burst  : BURST_INCR,
              default: '0
            };
          end
          else begin
            axi_aw_o = '{
              addr   : vreq_addr_d,
              len    : 0,
              size   : pe_req_d.vtype.vsew[1:0],
              cache  : CACHE_MODIFIABLE,
              burst  : BURST_INCR,
              default: '0
            };
          end

          axi_addrgen_queue = '{
            addr         : vreq_addr_d,
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

        if (mmu_exception_i.valid) begin
          state_d = IDLE;
          addrgen_req_ready = 1'b1;
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
              aligned_next_start_addr_temp
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

        if (vreq_blen_d == 0) begin
          state_d = IDLE;
          addrgen_req_ready = 1'b1;
          if (en_ld_st_translation_i & !mmu_exception_i.valid) begin
            last_translation_completed = 1'b1;
          end
        end
      end : start_req
    end : can_req
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

endmodule : addrgen
