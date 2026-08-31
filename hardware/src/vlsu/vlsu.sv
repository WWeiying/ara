// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// This is Ara's vector load/store unit. It is used exclusively for vector
// loads and vector stores. There are no guarantees regarding concurrency
// and coherence with Ariane's own load/store unit.

module vlsu import ara_pkg::*; import rvv_pkg::*; import qbs_pkg::*;
  import akv_pkg::*; #(
    parameter  int  unsigned NrLanes     = 0,
    parameter  int  unsigned VLEN        = 0,
    parameter  type          vaddr_t     = logic,  // Type used to address vector register file elements
    parameter  type          pe_req_t    = logic,
    parameter  type          pe_resp_t   = logic,
    // CVA6 configuration
    parameter  config_pkg::cva6_cfg_t CVA6Cfg = cva6_config_pkg::cva6_cfg,
    parameter  type          exception_t = logic,
    // AXI Interface parameters
    parameter  int  unsigned AxiDataWidth = 0,
    parameter  int  unsigned AxiAddrWidth = 0,
    parameter  type          axi_ar_t     = logic,
    parameter  type          axi_r_t      = logic,
    parameter  type          axi_aw_t     = logic,
    parameter  type          axi_w_t      = logic,
    parameter  type          axi_b_t      = logic,
    parameter  type          axi_req_t    = logic,
    parameter  type          axi_resp_t   = logic,
    // Dependant parameters. DO NOT CHANGE!
    localparam int  unsigned DataWidth    = $bits(elen_t),
    localparam type          strb_t       = logic [DataWidth/8-1:0],
    localparam type          vlen_t       = logic[$clog2(VLEN+1)-1:0]
  ) (
    input  logic                    clk_i,
    input  logic                    rst_ni,
    // AXI Memory Interface
    output axi_req_t                axi_req_o,
    input  axi_resp_t               axi_resp_i,
    // Interface with the dispatcher
    input  logic                    core_st_pending_i,
    output logic                    load_complete_o,
    output logic                    store_complete_o,
    output logic                    store_pending_o,
    // Interface with the sequencer
    input  pe_req_t                 pe_req_i,
    input  logic                    pe_req_valid_i,
    input  logic      [NrVInsn-1:0] pe_vinsn_running_i,
    output logic      [1:0]         pe_req_ready_o,         // Load (0) and Store (1) units
    output pe_resp_t  [1:0]         pe_resp_o,              // Load (0) and Store (1) units
    output logic                    addrgen_ack_o,
    output exception_t              addrgen_exception_o,
    output vlen_t                   addrgen_exception_vstart_o,
    output logic                    addrgen_fof_exception_o,
    output logic                    lsu_current_burst_exception_o,
    // Interface with the lanes
    // Store unit operands
    input  elen_t     [NrLanes-1:0] stu_operand_i,
    input  logic      [NrLanes-1:0] stu_operand_valid_i,
    output logic      [NrLanes-1:0] stu_operand_ready_o,
    // Address generation operands
    input  elen_t     [NrLanes-1:0] addrgen_operand_i,
    input  logic      [NrLanes-1:0] addrgen_operand_valid_i,
    output logic                    addrgen_operand_ready_o,
    // STU exception support
    input  logic                    lsu_ex_flush_i,
    output logic                    lsu_ex_flush_done_o,
    // Interface with the Mask unit
    input  strb_t     [NrLanes-1:0] mask_i,
    input  logic      [NrLanes-1:0] mask_valid_i,
    input  vfu_e                      mask_target_fu_i,
    output logic                    vldu_mask_ready_o,
    output logic                    vstu_mask_ready_o,

    // CSR input
    input  logic                    en_ld_st_translation_i,

    // Interface with CVA6's sv39 MMU
    // This is everything the MMU can provide, it might be overcomplete for Ara and some signals be useless
    output  logic                          mmu_misaligned_ex_o,
    output  logic                          mmu_req_o,        // request address translation
    output  logic [CVA6Cfg.VLEN-1:0]       mmu_vaddr_o,      // virtual address out
    output  logic                          mmu_is_store_o,   // the translation is requested by a store
    // if we need to walk the page table we can't grant in the same cycle
    // Cycle 0
    input logic                            mmu_dtlb_hit_i,   // sent in the same cycle as the request if translation hits in the DTLB
    input logic [CVA6Cfg.PPNW-1:0]         mmu_dtlb_ppn_i,   // ppn (send same cycle as hit)
    // Cycle 1
    input logic                            mmu_valid_i,      // translation is valid
    input logic [CVA6Cfg.PLEN-1:0]         mmu_paddr_i,      // translated address
    input exception_t                      mmu_exception_i,  // address translation threw an exception

    // Results
    output logic      [NrLanes-1:0] ldu_result_req_o,
    output vid_t      [NrLanes-1:0] ldu_result_id_o,
    output vaddr_t    [NrLanes-1:0] ldu_result_addr_o,
    output elen_t     [NrLanes-1:0] ldu_result_wdata_o,
    output strb_t     [NrLanes-1:0] ldu_result_be_o,
    input  logic      [NrLanes-1:0] ldu_result_gnt_i,
    input  logic      [NrLanes-1:0] ldu_result_final_gnt_i,
    // Floating-point status from a completed blocking QBS command
    output logic                    qbs_fflags_valid_o,
    output logic              [4:0] qbs_fflags_o
  );

  `include "common_cells/registers.svh"

  logic load_complete, store_complete;
  logic qbs_terminal, akv_terminal;
  logic addrgen_illegal_load, addrgen_illegal_store;
  assign load_complete_o  = load_complete | qbs_terminal | akv_terminal;
  assign store_complete_o = store_complete;

  logic stu_current_burst_exception, ldu_current_burst_exception;
  assign lsu_current_burst_exception_o = stu_current_burst_exception | ldu_current_burst_exception;

  `FF(lsu_ex_flush_done_o, lsu_ex_flush_i, 1'b0, clk_i, rst_ni);

  ///////////////////
  //  Definitions  //
  ///////////////////

  typedef logic [AxiAddrWidth-1:0] axi_addr_t;

  ///////////////
  //  AXI Cut  //
  ///////////////

  // Normal vector memory, QBS, and AKV share one slave side of the AXI cut.
  // Special-command ownership is exclusive through all read responses.
  axi_req_t  axi_req;
  axi_resp_t axi_resp;
  axi_req_t  normal_axi_req;
  axi_resp_t normal_axi_resp;

  axi_cut #(
    .ar_chan_t (axi_ar_t  ),
    .r_chan_t  (axi_r_t   ),
    .aw_chan_t (axi_aw_t  ),
    .w_chan_t  (axi_w_t   ),
    .b_chan_t  (axi_b_t   ),
    .axi_req_t (axi_req_t ),
    .axi_resp_t(axi_resp_t)
  ) i_axi_cut (
    .clk_i     (clk_i     ),
    .rst_ni    (rst_ni    ),
    .mst_req_o (axi_req_o ),
    .mst_resp_i(axi_resp_i),
    .slv_req_i (axi_req   ),
    .slv_resp_o(axi_resp  )
  );

  //////////////////////////
  //  Address Generation  //
  //////////////////////////

  // Interface with the load/store units
  addrgen_axi_req_t axi_addrgen_req;
  logic             axi_addrgen_req_valid;
  logic             ldu_axi_addrgen_req_ready;
  logic             stu_axi_addrgen_req_ready;
  logic             addrgen_idle;
  logic             normal_pe_req_valid;
  logic             normal_mmu_misaligned_ex;
  logic             normal_mmu_req;
  logic [CVA6Cfg.VLEN-1:0] normal_mmu_vaddr;
  logic             normal_mmu_is_store;
  logic             normal_addrgen_ack;
  exception_t       normal_addrgen_exception;
  vlen_t            normal_addrgen_exception_vstart;
  logic             normal_addrgen_fof_exception;

  addrgen #(
    .NrLanes     (NrLanes     ),
    .VLEN        (VLEN        ),
    .AxiDataWidth(AxiDataWidth),
    .AxiAddrWidth(AxiAddrWidth),
    .axi_ar_t    (axi_ar_t    ),
    .axi_aw_t    (axi_aw_t    ),
    .pe_req_t    (pe_req_t    ),
    .pe_resp_t   (pe_resp_t   ),
    .CVA6Cfg     (CVA6Cfg     ),
    .exception_t (exception_t )
  ) i_addrgen (
    .clk_i                      (clk_i                      ),
    .rst_ni                     (rst_ni                     ),
    // AXI Memory Interface
    .axi_aw_o                   (normal_axi_req.aw           ),
    .axi_aw_valid_o             (normal_axi_req.aw_valid     ),
    .axi_aw_ready_i             (normal_axi_resp.aw_ready    ),
    .axi_ar_o                   (normal_axi_req.ar           ),
    .axi_ar_valid_o             (normal_axi_req.ar_valid     ),
    .axi_ar_ready_i             (normal_axi_resp.ar_ready    ),
    // Interface with dispatcher
    .core_st_pending_i          (core_st_pending_i          ),
    // Interface with the sequencer
    .pe_req_i                   (pe_req_i                   ),
    .pe_req_valid_i             (normal_pe_req_valid        ),
    .pe_vinsn_running_i         (pe_vinsn_running_i         ),
    .addrgen_ack_o              (normal_addrgen_ack              ),
    .addrgen_exception_o        (normal_addrgen_exception        ),
    .addrgen_exception_vstart_o (normal_addrgen_exception_vstart ),
    .addrgen_fof_exception_o    (normal_addrgen_fof_exception    ),
    .addrgen_illegal_load_o     (addrgen_illegal_load       ),
    .addrgen_illegal_store_o    (addrgen_illegal_store      ),
    // Interface with the lanes
    .addrgen_operand_i          (addrgen_operand_i          ),
    .addrgen_operand_valid_i    (addrgen_operand_valid_i    ),
    .addrgen_operand_ready_o    (addrgen_operand_ready_o    ),
    // Interface with the load/store units
    .axi_addrgen_req_o          (axi_addrgen_req            ),
    .axi_addrgen_req_valid_o    (axi_addrgen_req_valid      ),
    .ldu_axi_addrgen_req_ready_i(ldu_axi_addrgen_req_ready  ),
    .stu_axi_addrgen_req_ready_i(stu_axi_addrgen_req_ready  ),
    .lsu_ex_flush_i             (lsu_ex_flush_i             ),

    // CSR input
    .en_ld_st_translation_i,
    .mmu_misaligned_ex_o        (normal_mmu_misaligned_ex   ),
    .mmu_req_o                  (normal_mmu_req             ),
    .mmu_vaddr_o                (normal_mmu_vaddr           ),
    .mmu_is_store_o             (normal_mmu_is_store        ),
    .mmu_dtlb_hit_i,
    .mmu_dtlb_ppn_i,
    .mmu_valid_i,
    .mmu_paddr_i,
    .mmu_exception_i,
    .idle_o                     (addrgen_idle               )
  );

  ////////////////////////
  //  Vector Load Unit  //
  ////////////////////////

  logic [1:0] normal_pe_req_ready;
  pe_resp_t [1:0] normal_pe_resp;
  logic vldu_idle;
  logic [NrLanes-1:0] normal_ldu_result_req;
  vid_t [NrLanes-1:0] normal_ldu_result_id;
  vaddr_t [NrLanes-1:0] normal_ldu_result_addr;
  elen_t [NrLanes-1:0] normal_ldu_result_wdata;
  strb_t [NrLanes-1:0] normal_ldu_result_be;
  logic [NrLanes-1:0] normal_ldu_result_gnt;
  logic [NrLanes-1:0] normal_ldu_result_final_gnt;

  vldu #(
    .AxiAddrWidth(AxiAddrWidth),
    .AxiDataWidth(AxiDataWidth),
    .axi_r_t     (axi_r_t     ),
    .NrLanes     (NrLanes     ),
    .VLEN        (VLEN        ),
    .vaddr_t     (vaddr_t     ),
    .pe_req_t    (pe_req_t    ),
    .pe_resp_t   (pe_resp_t   )
  ) i_vldu (
    .clk_i                  (clk_i                     ),
    .rst_ni                 (rst_ni                    ),
    // AXI Memory Interface
    .axi_r_i                (normal_axi_resp.r         ),
    .axi_r_valid_i          (normal_axi_resp.r_valid   ),
    .axi_r_ready_o          (normal_axi_req.r_ready    ),
    // Interface with the dispatcher
    .load_complete_o        (load_complete             ),
    // Interface with the main sequencer
    .pe_req_i               (pe_req_i                  ),
    .pe_req_valid_i         (normal_pe_req_valid       ),
    .pe_vinsn_running_i     (pe_vinsn_running_i        ),
    .pe_req_ready_o         (normal_pe_req_ready[OffsetLoad]),
    .pe_resp_o              (normal_pe_resp[OffsetLoad]),
    .ldu_current_burst_exception_o (ldu_current_burst_exception),
    // Interface with the address generator
    .axi_addrgen_req_i      (axi_addrgen_req           ),
    .axi_addrgen_req_valid_i(axi_addrgen_req_valid     ),
    .axi_addrgen_req_ready_o(ldu_axi_addrgen_req_ready ),
    .addrgen_illegal_load_i (addrgen_illegal_load      ),
    // Interface with the Mask unit
    .mask_i                 (mask_i                    ),
    .mask_valid_i           (mask_valid_i & {NrLanes{mask_target_fu_i == VFU_LoadUnit}}),
    .mask_ready_o           (vldu_mask_ready_o         ),
    // Interface with the lanes
    .ldu_result_req_o       (normal_ldu_result_req     ),
    .ldu_result_addr_o      (normal_ldu_result_addr    ),
    .ldu_result_id_o        (normal_ldu_result_id      ),
    .ldu_result_wdata_o     (normal_ldu_result_wdata   ),
    .ldu_result_be_o        (normal_ldu_result_be      ),
    .ldu_result_gnt_i       (normal_ldu_result_gnt     ),
    .ldu_result_final_gnt_i (normal_ldu_result_final_gnt),
    .lsu_ex_flush_i         (lsu_ex_flush_i            ),
    .idle_o                 (vldu_idle                 )
  );

  /////////////////////////
  //  Vector Store Unit  //
  /////////////////////////

  logic vstu_idle;

  vstu #(
    .AxiAddrWidth(AxiAddrWidth),
    .AxiDataWidth(AxiDataWidth),
    .axi_w_t     (axi_w_t     ),
    .axi_b_t     (axi_b_t     ),
    .NrLanes     (NrLanes     ),
    .VLEN        (VLEN        ),
    .vaddr_t     (vaddr_t     ),
    .pe_req_t    (pe_req_t    ),
    .pe_resp_t   (pe_resp_t   )
  ) i_vstu (
    .clk_i                  (clk_i                      ),
    .rst_ni                 (rst_ni                     ),
    // AXI Memory Interface
    .axi_w_o                (normal_axi_req.w           ),
    .axi_w_valid_o          (normal_axi_req.w_valid     ),
    .axi_w_ready_i          (normal_axi_resp.w_ready    ),
    .axi_b_i                (normal_axi_resp.b          ),
    .axi_b_valid_i          (normal_axi_resp.b_valid    ),
    .axi_b_ready_o          (normal_axi_req.b_ready     ),
    // Interface with the dispatcher
    .store_pending_o        (store_pending_o            ),
    .store_complete_o       (store_complete             ),
    // Interface with the main sequencer
    .pe_req_i               (pe_req_i                   ),
    .pe_req_valid_i         (normal_pe_req_valid        ),
    .pe_vinsn_running_i     (pe_vinsn_running_i         ),
    .pe_req_ready_o         (normal_pe_req_ready[OffsetStore]),
    .pe_resp_o              (normal_pe_resp[OffsetStore]),
    .stu_current_burst_exception_o (stu_current_burst_exception),
    // Interface with the address generator
    .axi_addrgen_req_i      (axi_addrgen_req            ),
    .axi_addrgen_req_valid_i(axi_addrgen_req_valid      ),
    .axi_addrgen_req_ready_o(stu_axi_addrgen_req_ready  ),
    .addrgen_illegal_store_i(addrgen_illegal_store      ),
    // Interface with the Mask unit
    .mask_i                 (mask_i                     ),
    .mask_valid_i           (mask_valid_i & {NrLanes{mask_target_fu_i == VFU_StoreUnit}}),
    .mask_ready_o           (vstu_mask_ready_o          ),
    // Interface with the lanes
    .stu_operand_i          (stu_operand_i              ),
    .stu_operand_valid_i    (stu_operand_valid_i        ),
    .stu_operand_ready_o    (stu_operand_ready_o        ),
    .lsu_ex_flush_i         (lsu_ex_flush_i             ),
    .idle_o                 (vstu_idle                  )
  );

  //////////////////////////////////////
  //  Blocking QBS command ownership  //
  //////////////////////////////////////

  logic qbs_active_d, qbs_active_q;
  logic qbs_clk, qbs_clk_en;
  logic qbs_command_valid, qbs_command_ready, qbs_command_fire;
  logic [2:0] qbs_command_m;
  vid_t qbs_command_id_q;

  logic qbs_success_valid, qbs_fault_valid;
  logic [4:0] qbs_result_fflags;
  logic qbs_fault_is_validation;
  qbs_validation_error_e qbs_validation_error;
  qbs_read_fault_e qbs_read_fault_kind;
  logic [CVA6Cfg.VLEN-1:0] qbs_fault_vaddr;
  exception_t qbs_fault_mmu_exception;
  exception_t qbs_terminal_exception;

  logic qbs_mmu_req, qbs_mmu_is_store;
  logic [CVA6Cfg.VLEN-1:0] qbs_mmu_vaddr;
  logic qbs_physical_check_valid;
  logic [AxiAddrWidth-1:0] qbs_physical_check_addr;
  logic [12:0] qbs_physical_check_bytes;
  logic qbs_physical_range_allowed;

  axi_ar_t qbs_axi_ar;
  logic qbs_axi_ar_valid, qbs_axi_ar_ready;
  axi_r_t qbs_axi_r;
  logic qbs_axi_r_valid, qbs_axi_r_ready;

  logic [NrLanes-1:0] qbs_ldu_result_req;
  vid_t [NrLanes-1:0] qbs_ldu_result_id;
  vaddr_t [NrLanes-1:0] qbs_ldu_result_addr;
  logic [63:0] qbs_ldu_result_wdata [NrLanes];
  logic [7:0] qbs_ldu_result_be [NrLanes];
  logic [NrLanes-1:0] qbs_ldu_result_gnt;
  logic [NrLanes-1:0] qbs_ldu_result_final_gnt;

  logic qbs_busy;
  logic [31:0] qbs_command_cycles;
  logic [31:0] qbs_read_range_count, qbs_read_translation_count;
  logic [31:0] qbs_read_ar_count, qbs_read_beat_count;
  logic [31:0] qbs_read_payload_bytes, qbs_read_store_wait_cycles;
  logic [31:0] qbs_read_backpressure_cycles, qbs_tiles_computed;
  logic [31:0] qbs_read_outstanding_occupancy_sum;
  logic [1:0] qbs_read_outstanding_max;
  logic [31:0] qbs_read_outstanding_full_cycles;
  logic [31:0] qbs_phase_setup_cycles, qbs_phase_activation_cycles;
  logic [31:0] qbs_phase_weight_cycles, qbs_phase_compute_cycles;
  logic [31:0] qbs_phase_overlap_cycles, qbs_phase_drain_cycles;
  logic [31:0] qbs_phase_scheduler_cycles, qbs_phase_commit_cycles;
  logic [31:0] qbs_phase_fault_cycles, qbs_phase_terminal_cycles;
  logic [31:0] qbs_weight_prefetch_wait_cycles;
  logic [31:0] qbs_weight_bytes, qbs_activation_bytes;
  logic [31:0] qbs_useful_pairs, qbs_pair_capacity;
  logic [31:0] qbs_dot_active_cycles, qbs_fp_uop_issue;
  logic [31:0] qbs_fp_table_occupancy_sum, qbs_fp_table_full_cycles;
  logic [4:0] qbs_fp_table_occupancy_max;
  logic [31:0] qbs_accumulator_updates, qbs_commit_word_count;
  logic [31:0] qbs_commit_backpressure_cycles;
  qbs_activation_access_e qbs_activation_access;
  logic [31:0] qbs_context_fill_count, qbs_context_reuse_count;
  logic [31:0] qbs_context_reuse_block_count, qbs_context_read_bytes;
  logic [31:0] qbs_activation_axi_bytes_saved;
  logic [31:0] qbs_context_replay_cycles;
  logic [31:0] qbs_context_replay_compute_overlap_cycles;
  logic [31:0] qbs_context_validation_fault_count;

  /////////////////////////////////////////////
  //  Attention/KV context command ownership //
  /////////////////////////////////////////////

  logic akv_active_d, akv_active_q;
  logic akv_clk, akv_clk_en;
  logic akv_command_valid, akv_command_ready, akv_command_fire;
  logic akv_command_early_ack;
  logic akv_command_early_acked_q;
  logic akv_request_consumed_q;
  logic pe_req_is_akv;
  akv_command_e akv_command;
  akv_command_e akv_command_q;
  logic [15:0] akv_command_head_dim;
  vid_t akv_command_id_q;

  logic akv_success_valid, akv_fault_valid;
  logic akv_fault_is_validation;
  akv_validation_error_e akv_validation_error;
  qbs_read_fault_e akv_read_fault_kind;
  logic [CVA6Cfg.VLEN-1:0] akv_fault_vaddr;
  exception_t akv_fault_mmu_exception;
  exception_t akv_terminal_exception;
  logic akv_context_ready;

  logic akv_mmu_req, akv_mmu_is_store;
  logic [CVA6Cfg.VLEN-1:0] akv_mmu_vaddr;
  logic akv_physical_check_valid;
  logic [AxiAddrWidth-1:0] akv_physical_check_addr;
  logic [12:0] akv_physical_check_bytes;
  logic akv_physical_range_allowed;

  axi_ar_t akv_axi_ar;
  logic akv_axi_ar_valid, akv_axi_ar_ready;
  axi_r_t akv_axi_r;
  logic akv_axi_r_valid, akv_axi_r_ready;

  logic [NrLanes-1:0] akv_ldu_result_req;
  vid_t [NrLanes-1:0] akv_ldu_result_id;
  vaddr_t [NrLanes-1:0] akv_ldu_result_addr;
  logic [63:0] akv_ldu_result_wdata [NrLanes];
  logic [7:0] akv_ldu_result_be [NrLanes];
  logic [NrLanes-1:0] akv_ldu_result_gnt;
  logic [NrLanes-1:0] akv_ldu_result_final_gnt;

  logic akv_busy;
  logic [31:0] akv_command_cycles;
  logic [31:0] akv_full_count, akv_refill_count;
  logic [31:0] akv_load_count, akv_release_count;
  logic [31:0] akv_v2_full_count, akv_v2_refill_count;
  logic [31:0] akv_v2_row_load_count, akv_v2_column_load_count;
  logic [31:0] akv_v2_k_view_bank_cycles;
  logic [31:0] akv_v2_bank_conflict_cycles, akv_v2_rejected_count;
  logic [31:0] akv_q_external_bytes, akv_kv_external_bytes;
  logic [31:0] akv_replay_bytes, akv_replay_backpressure_cycles;
  logic [31:0] akv_read_range_count, akv_read_translation_count;
  logic [31:0] akv_read_ar_count, akv_read_beat_count;
  logic [31:0] akv_read_payload_bytes, akv_read_store_wait_cycles;
  logic [31:0] akv_read_backpressure_cycles;
  logic [31:0] akv_read_outstanding_occupancy_sum;
  logic [1:0] akv_read_outstanding_max;
  logic [31:0] akv_read_outstanding_full_cycles;

  logic normal_vlsu_idle;

  function automatic logic qbs_range_is_cacheable_idempotent(
      input logic [AxiAddrWidth-1:0] address,
      input logic [12:0] bytes
  );
    logic [65:0] request_start;
    logic [65:0] request_end;
    logic cached;
    logic nonidempotent;

    request_start = 66'(address);
    request_end = request_start + 66'(bytes);
    cached = 1'b0;
    nonidempotent = 1'b0;

    if (bytes != '0) begin
      for (int unsigned rule = 0; rule < CVA6Cfg.NrCachedRegionRules; rule++) begin
        automatic logic [65:0] region_start =
            66'(CVA6Cfg.CachedRegionAddrBase[rule]);
        automatic logic [65:0] region_end = region_start +
            66'(CVA6Cfg.CachedRegionLength[rule]);
        cached |= request_start >= region_start && request_end <= region_end;
      end
      for (int unsigned rule = 0; rule < CVA6Cfg.NrNonIdempotentRules; rule++) begin
        automatic logic [65:0] region_start =
            66'(CVA6Cfg.NonIdempotentAddrBase[rule]);
        automatic logic [65:0] region_end = region_start +
            66'(CVA6Cfg.NonIdempotentLength[rule]);
        nonidempotent |= request_start < region_end && request_end > region_start;
      end
    end

    return bytes != '0 && cached && !nonidempotent;
  endfunction

  assign pe_req_is_akv = AkvEnable && pe_req_i.op inside {
      VAKVFILL, VAKVLOAD, VAKVRELEASE};
  assign normal_pe_req_valid = pe_req_valid_i &&
      pe_req_i.op != VQBEXEC && !pe_req_is_akv &&
      !qbs_active_q && !akv_active_q;

  // ara_idle is the primary command barrier. These local conditions defend the
  // ownership transfer against stale queue/cut state and make the handoff
  // independent of a fixed drain delay.
  assign normal_vlsu_idle = addrgen_idle && vldu_idle && vstu_idle &&
      !normal_axi_req.ar_valid && !normal_axi_req.aw_valid &&
      !normal_axi_req.w_valid && !normal_axi_resp.r_valid &&
      !normal_axi_resp.b_valid && !axi_req_o.ar_valid &&
      !axi_req_o.aw_valid && !axi_req_o.w_valid &&
      !axi_resp_i.r_valid && !axi_resp_i.b_valid;

  always_comb begin
    qbs_command_m = '0;
    unique case (pe_req_i.vl)
      vlen_t'(VLEN / 32)      : qbs_command_m = 3'd1;
      vlen_t'(2 * VLEN / 32)  : qbs_command_m = 3'd2;
      vlen_t'(3 * VLEN / 32)  : qbs_command_m = 3'd3;
      vlen_t'(4 * VLEN / 32)  : qbs_command_m = 3'd4;
      default                 : qbs_command_m = '0;
    endcase
  end

  assign qbs_command_valid = QbsEnable && pe_req_valid_i &&
      pe_req_i.op == VQBEXEC && !qbs_active_q && !akv_active_q &&
      normal_vlsu_idle;
  assign qbs_command_fire = qbs_command_valid && qbs_command_ready;
  assign qbs_terminal = qbs_active_q &&
      (qbs_success_valid || qbs_fault_valid);
  assign qbs_clk_en = qbs_command_valid || qbs_active_q;

  always_comb begin
    akv_command = AKV_COMMAND_FULL;
    unique case (pe_req_i.op)
      VAKVFILL: begin
        if (pe_req_i.akv_v2)
          akv_command = pe_req_i.akv_refill
              ? AKV_COMMAND_V2_REFILL : AKV_COMMAND_V2_FULL;
        else
          akv_command = pe_req_i.akv_refill
              ? AKV_COMMAND_REFILL : AKV_COMMAND_FULL;
      end
      VAKVLOAD: akv_command = pe_req_i.akv_column
          ? AKV_COMMAND_V2_COLUMN_LOAD : AKV_COMMAND_LOAD;
      VAKVRELEASE: akv_command = AKV_COMMAND_RELEASE;
      default: ;
    endcase
    akv_command_head_dim = pe_req_i.vl == vlen_t'(128)
        ? 16'd128 : 16'd64;
  end

  assign akv_command_valid = AkvEnable && pe_req_valid_i &&
      pe_req_is_akv && !akv_request_consumed_q && !akv_active_q &&
      !qbs_active_q && normal_vlsu_idle;
  assign akv_command_fire = akv_command_valid && akv_command_ready;
  assign akv_terminal = akv_active_q &&
      (akv_success_valid || akv_fault_valid);
  assign akv_clk_en = akv_command_valid || akv_active_q;

  // QBS contains byte-granular block storage, a 16-entry FP scheduler, and an
  // FP pipeline. None of that state needs a clock while no blocking command is
  // present. Besides reducing dynamic power, this prevents idle QBS state from
  // dominating event-driven simulation of ordinary vector code.
  tc_clk_gating #(
    .IS_FUNCTIONAL (1'b1)
  ) i_qbs_clk_gate (
    .clk_i,
    .en_i      (qbs_clk_en),
    .test_en_i (1'b0),
    .clk_o     (qbs_clk)
  );

  always_comb begin
    qbs_active_d = qbs_active_q;
    if (qbs_command_fire)
      qbs_active_d = 1'b1;
    if (qbs_terminal)
      qbs_active_d = 1'b0;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      qbs_active_q <= 1'b0;
      qbs_command_id_q <= '0;
    end else begin
      qbs_active_q <= qbs_active_d;
      if (qbs_command_fire)
        qbs_command_id_q <= pe_req_i.id;
    end
  end

  tc_clk_gating #(
    .IS_FUNCTIONAL (1'b1)
  ) i_akv_clk_gate (
    .clk_i,
    .en_i      (akv_clk_en),
    .test_en_i (1'b0),
    .clk_o     (akv_clk)
  );

  always_comb begin
    akv_active_d = akv_active_q;
    if (akv_command_fire)
      akv_active_d = 1'b1;
    if (akv_terminal)
      akv_active_d = 1'b0;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      akv_active_q <= 1'b0;
      akv_command_id_q <= '0;
      akv_command_q <= AKV_COMMAND_FULL;
      akv_command_early_acked_q <= 1'b0;
      akv_request_consumed_q <= 1'b0;
    end else begin
      akv_active_q <= akv_active_d;
      if (!pe_req_valid_i || !pe_req_is_akv)
        akv_request_consumed_q <= 1'b0;
      if (akv_command_fire) begin
        akv_command_id_q <= pe_req_i.id;
        akv_command_q <= akv_command;
        akv_command_early_acked_q <= akv_command_early_ack;
        akv_request_consumed_q <= 1'b1;
      end else if (akv_terminal) begin
        akv_command_early_acked_q <= 1'b0;
      end
    end
  end

  // AXI ownership includes the registered cut. No normal response is exposed
  // while QBS owns the read channel, and QBS never drives write channels.
  always_comb begin
    axi_req = normal_axi_req;
    normal_axi_resp = axi_resp;
    qbs_axi_ar_ready = 1'b0;
    qbs_axi_r = '0;
    qbs_axi_r_valid = 1'b0;
    akv_axi_ar_ready = 1'b0;
    akv_axi_r = '0;
    akv_axi_r_valid = 1'b0;

    if (qbs_active_q) begin
      axi_req = '0;
      axi_req.ar = qbs_axi_ar;
      axi_req.ar_valid = qbs_axi_ar_valid;
      axi_req.r_ready = qbs_axi_r_ready;
      normal_axi_resp = '0;
      qbs_axi_ar_ready = axi_resp.ar_ready;
      qbs_axi_r = axi_resp.r;
      qbs_axi_r_valid = axi_resp.r_valid;
    end else if (akv_active_q) begin
      axi_req = '0;
      axi_req.ar = akv_axi_ar;
      axi_req.ar_valid = akv_axi_ar_valid;
      axi_req.r_ready = akv_axi_r_ready;
      normal_axi_resp = '0;
      akv_axi_ar_ready = axi_resp.ar_ready;
      akv_axi_r = axi_resp.r;
      akv_axi_r_valid = axi_resp.r_valid;
    end
  end

  // The MMU port follows the same command ownership as AXI.
  always_comb begin
    mmu_misaligned_ex_o = normal_mmu_misaligned_ex;
    mmu_req_o = normal_mmu_req;
    mmu_vaddr_o = normal_mmu_vaddr;
    mmu_is_store_o = normal_mmu_is_store;
    if (qbs_active_q) begin
      mmu_misaligned_ex_o = 1'b0;
      mmu_req_o = qbs_mmu_req;
      mmu_vaddr_o = qbs_mmu_vaddr;
      mmu_is_store_o = qbs_mmu_is_store;
    end else if (akv_active_q) begin
      mmu_misaligned_ex_o = 1'b0;
      mmu_req_o = akv_mmu_req;
      mmu_vaddr_o = akv_mmu_vaddr;
      mmu_is_store_o = akv_mmu_is_store;
    end
  end

  assign qbs_physical_range_allowed = qbs_range_is_cacheable_idempotent(
      qbs_physical_check_addr, qbs_physical_check_bytes);
  assign akv_physical_range_allowed = qbs_range_is_cacheable_idempotent(
      akv_physical_check_addr, akv_physical_check_bytes);

  // QBS and VLDu share the lane result ports. Grant and final-grant feedback
  // returns only to the current owner.
  always_comb begin
    ldu_result_req_o = normal_ldu_result_req;
    ldu_result_id_o = normal_ldu_result_id;
    ldu_result_addr_o = normal_ldu_result_addr;
    ldu_result_wdata_o = normal_ldu_result_wdata;
    ldu_result_be_o = normal_ldu_result_be;
    normal_ldu_result_gnt = ldu_result_gnt_i;
    normal_ldu_result_final_gnt = ldu_result_final_gnt_i;
    qbs_ldu_result_gnt = '0;
    qbs_ldu_result_final_gnt = '0;
    akv_ldu_result_gnt = '0;
    akv_ldu_result_final_gnt = '0;

    if (qbs_active_q) begin
      ldu_result_req_o = qbs_ldu_result_req;
      ldu_result_id_o = qbs_ldu_result_id;
      ldu_result_addr_o = qbs_ldu_result_addr;
      for (int unsigned lane = 0; lane < NrLanes; lane++) begin
        ldu_result_wdata_o[lane] = elen_t'(qbs_ldu_result_wdata[lane]);
        ldu_result_be_o[lane] = strb_t'(qbs_ldu_result_be[lane]);
      end
      normal_ldu_result_gnt = '0;
      normal_ldu_result_final_gnt = '0;
      qbs_ldu_result_gnt = ldu_result_gnt_i;
      qbs_ldu_result_final_gnt = ldu_result_final_gnt_i;
    end else if (akv_active_q) begin
      ldu_result_req_o = akv_ldu_result_req;
      ldu_result_id_o = akv_ldu_result_id;
      ldu_result_addr_o = akv_ldu_result_addr;
      for (int unsigned lane = 0; lane < NrLanes; lane++) begin
        ldu_result_wdata_o[lane] = elen_t'(akv_ldu_result_wdata[lane]);
        ldu_result_be_o[lane] = strb_t'(akv_ldu_result_be[lane]);
      end
      normal_ldu_result_gnt = '0;
      normal_ldu_result_final_gnt = '0;
      akv_ldu_result_gnt = ldu_result_gnt_i;
      akv_ldu_result_final_gnt = ldu_result_final_gnt_i;
    end
  end

  always_comb begin
    pe_req_ready_o = '0;
    pe_resp_o = normal_pe_resp;
    if (!qbs_active_q && !akv_active_q) begin
      pe_req_ready_o = normal_pe_req_ready;
      if (pe_req_i.op == VQBEXEC) begin
        pe_req_ready_o[OffsetLoad] = normal_vlsu_idle && qbs_command_ready;
        pe_req_ready_o[OffsetStore] = 1'b0;
      end else if (pe_req_is_akv) begin
        pe_req_ready_o[OffsetLoad] = AkvEnable && normal_vlsu_idle &&
                                     akv_command_ready;
        pe_req_ready_o[OffsetStore] = 1'b0;
      end
    end else if (qbs_active_q) begin
      pe_resp_o[OffsetLoad] = '0;
      if (qbs_terminal)
        pe_resp_o[OffsetLoad].vinsn_done[qbs_command_id_q] = 1'b1;
    end else begin
      pe_resp_o[OffsetLoad] = '0;
      if (akv_terminal)
        pe_resp_o[OffsetLoad].vinsn_done[akv_command_id_q] = 1'b1;
    end
  end

  always_comb begin
    qbs_terminal_exception = '0;
    if (qbs_fault_valid) begin
      if (qbs_read_fault_kind == QBS_READ_FAULT_MMU) begin
        qbs_terminal_exception = qbs_fault_mmu_exception;
      end else begin
        qbs_terminal_exception.valid = 1'b1;
        qbs_terminal_exception.cause = qbs_fault_is_validation
            ? riscv::ILLEGAL_INSTR : riscv::LD_ACCESS_FAULT;
        qbs_terminal_exception.tval = qbs_fault_is_validation
            ? '0 : qbs_fault_vaddr;
      end
    end
  end

  always_comb begin
    akv_terminal_exception = '0;
    if (akv_fault_valid) begin
      if (akv_read_fault_kind == QBS_READ_FAULT_MMU) begin
        akv_terminal_exception = akv_fault_mmu_exception;
      end else begin
        akv_terminal_exception.valid = 1'b1;
        akv_terminal_exception.cause = akv_fault_is_validation
            ? riscv::ILLEGAL_INSTR : riscv::LD_ACCESS_FAULT;
        akv_terminal_exception.tval = akv_fault_is_validation
            ? '0 : akv_fault_vaddr;
      end
    end
  end

  always_comb begin
    addrgen_ack_o = 1'b0;
    addrgen_exception_o = '0;
    addrgen_exception_vstart_o = '0;
    addrgen_fof_exception_o = 1'b0;
    if (qbs_active_q) begin
      addrgen_ack_o = qbs_terminal;
      addrgen_exception_o = qbs_terminal_exception;
    end else if (akv_active_q) begin
      addrgen_ack_o = akv_terminal && !akv_command_early_acked_q;
      addrgen_exception_o = akv_terminal_exception;
    end else if (akv_command_early_ack) begin
      addrgen_ack_o = 1'b1;
    end else begin
      addrgen_ack_o = normal_addrgen_ack;
      addrgen_exception_o = normal_addrgen_exception;
      addrgen_exception_vstart_o = normal_addrgen_exception_vstart;
      addrgen_fof_exception_o = normal_addrgen_fof_exception;
    end
  end

  assign qbs_fflags_valid_o = qbs_active_q && qbs_success_valid;
  assign qbs_fflags_o = qbs_result_fflags;

  qbs_engine #(
    .AxiDataWidth(AxiDataWidth),
    .AxiAddrWidth(AxiAddrWidth),
    .VAddrWidth(CVA6Cfg.VLEN),
    .PAddrWidth(CVA6Cfg.PLEN),
    .NrLanes(NrLanes),
    .VLEN(VLEN),
    .vid_t(vid_t),
    .vaddr_t(vaddr_t),
    .axi_ar_t(axi_ar_t),
    .axi_r_t(axi_r_t),
    .exception_t(exception_t)
  ) i_qbs_engine (
    .clk_i(qbs_clk),
    .rst_ni,
    .command_valid_i(qbs_command_valid),
    .command_ready_o(qbs_command_ready),
    .command_id_i(pe_req_i.id),
    .command_vd_i(pe_req_i.vd),
    .command_m_i(qbs_command_m),
    .command_descriptor_address_i(pe_req_i.scalar_op),
    .command_activation_base_i(pe_req_i.stride),
    .command_cache_i(axi_pkg::CACHE_MODIFIABLE),
    .command_prot_i('0),
    .success_valid_o(qbs_success_valid),
    .fault_valid_o(qbs_fault_valid),
    .terminal_ready_i(1'b1),
    .result_fflags_o(qbs_result_fflags),
    .fault_is_validation_o(qbs_fault_is_validation),
    .validation_error_o(qbs_validation_error),
    .read_fault_kind_o(qbs_read_fault_kind),
    .fault_vaddr_o(qbs_fault_vaddr),
    .fault_mmu_exception_o(qbs_fault_mmu_exception),
    .core_st_pending_i,
    .en_ld_st_translation_i,
    .mmu_req_o(qbs_mmu_req),
    .mmu_vaddr_o(qbs_mmu_vaddr),
    .mmu_is_store_o(qbs_mmu_is_store),
    .mmu_valid_i,
    .mmu_paddr_i,
    .mmu_exception_valid_i(mmu_exception_i.valid),
    .mmu_exception_i,
    .physical_check_valid_o(qbs_physical_check_valid),
    .physical_check_addr_o(qbs_physical_check_addr),
    .physical_check_bytes_o(qbs_physical_check_bytes),
    .physical_range_allowed_i(qbs_physical_range_allowed),
    .axi_ar_o(qbs_axi_ar),
    .axi_ar_valid_o(qbs_axi_ar_valid),
    .axi_ar_ready_i(qbs_axi_ar_ready),
    .axi_r_i(qbs_axi_r),
    .axi_r_valid_i(qbs_axi_r_valid),
    .axi_r_ready_o(qbs_axi_r_ready),
    .ldu_result_req_o(qbs_ldu_result_req),
    .ldu_result_id_o(qbs_ldu_result_id),
    .ldu_result_addr_o(qbs_ldu_result_addr),
    .ldu_result_wdata_o(qbs_ldu_result_wdata),
    .ldu_result_be_o(qbs_ldu_result_be),
    .ldu_result_gnt_i(qbs_ldu_result_gnt),
    .ldu_result_final_gnt_i(qbs_ldu_result_final_gnt),
    .busy_o(qbs_busy),
    .command_cycles_o(qbs_command_cycles),
    .read_range_count_o(qbs_read_range_count),
    .read_translation_count_o(qbs_read_translation_count),
    .read_ar_count_o(qbs_read_ar_count),
    .read_beat_count_o(qbs_read_beat_count),
    .read_payload_bytes_o(qbs_read_payload_bytes),
    .read_store_wait_cycles_o(qbs_read_store_wait_cycles),
    .read_backpressure_cycles_o(qbs_read_backpressure_cycles),
    .read_outstanding_occupancy_sum_o(qbs_read_outstanding_occupancy_sum),
    .read_outstanding_max_o(qbs_read_outstanding_max),
    .read_outstanding_full_cycles_o(qbs_read_outstanding_full_cycles),
    .phase_setup_cycles_o(qbs_phase_setup_cycles),
    .phase_activation_cycles_o(qbs_phase_activation_cycles),
    .phase_weight_cycles_o(qbs_phase_weight_cycles),
    .phase_compute_cycles_o(qbs_phase_compute_cycles),
    .phase_overlap_cycles_o(qbs_phase_overlap_cycles),
    .phase_drain_cycles_o(qbs_phase_drain_cycles),
    .phase_scheduler_cycles_o(qbs_phase_scheduler_cycles),
    .phase_commit_cycles_o(qbs_phase_commit_cycles),
    .phase_fault_cycles_o(qbs_phase_fault_cycles),
    .phase_terminal_cycles_o(qbs_phase_terminal_cycles),
    .weight_prefetch_wait_cycles_o(qbs_weight_prefetch_wait_cycles),
    .tiles_computed_o(qbs_tiles_computed),
    .weight_bytes_o(qbs_weight_bytes),
    .activation_bytes_o(qbs_activation_bytes),
    .useful_pairs_o(qbs_useful_pairs),
    .pair_capacity_o(qbs_pair_capacity),
    .dot_active_cycles_o(qbs_dot_active_cycles),
    .fp_uop_issue_o(qbs_fp_uop_issue),
    .fp_table_occupancy_sum_o(qbs_fp_table_occupancy_sum),
    .fp_table_occupancy_max_o(qbs_fp_table_occupancy_max),
    .fp_table_full_cycles_o(qbs_fp_table_full_cycles),
    .accumulator_updates_o(qbs_accumulator_updates),
    .commit_word_count_o(qbs_commit_word_count),
    .commit_backpressure_cycles_o(qbs_commit_backpressure_cycles),
    .activation_access_o(qbs_activation_access),
    .context_fill_count_o(qbs_context_fill_count),
    .context_reuse_count_o(qbs_context_reuse_count),
    .context_reuse_block_count_o(qbs_context_reuse_block_count),
    .context_read_bytes_o(qbs_context_read_bytes),
    .activation_axi_bytes_saved_o(qbs_activation_axi_bytes_saved),
    .context_replay_cycles_o(qbs_context_replay_cycles),
    .context_replay_compute_overlap_cycles_o(
        qbs_context_replay_compute_overlap_cycles),
    .context_validation_fault_count_o(qbs_context_validation_fault_count)
  );

  akv_engine #(
    .AxiDataWidth (AxiDataWidth),
    .AxiAddrWidth (AxiAddrWidth),
    .VAddrWidth   (CVA6Cfg.VLEN),
    .PAddrWidth   (CVA6Cfg.PLEN),
    .NrLanes      (NrLanes),
    .VLEN         (VLEN),
    .vid_t        (vid_t),
    .vaddr_t      (vaddr_t),
    .axi_ar_t     (axi_ar_t),
    .axi_r_t      (axi_r_t),
    .exception_t  (exception_t)
  ) i_akv_engine (
    .clk_i                         (akv_clk),
    .rst_ni,
    .command_valid_i               (akv_command_valid),
    .command_ready_o               (akv_command_ready),
    .command_i                     (akv_command),
    .command_id_i                  (pe_req_i.id),
    .command_vd_i                  (pe_req_i.vd),
    .command_head_dim_i            (akv_command_head_dim),
    .command_descriptor_address_i  (pe_req_i.scalar_op),
    .command_tile_start_i          (pe_req_i.stride),
    .command_selector_i            (pe_req_i.scalar_op),
    .command_cache_i               (axi_pkg::CACHE_MODIFIABLE),
    .command_prot_i                ('0),
    .command_early_ack_o           (akv_command_early_ack),
    .success_valid_o               (akv_success_valid),
    .fault_valid_o                 (akv_fault_valid),
    .terminal_ready_i              (1'b1),
    .fault_is_validation_o         (akv_fault_is_validation),
    .validation_error_o            (akv_validation_error),
    .read_fault_kind_o             (akv_read_fault_kind),
    .fault_vaddr_o                 (akv_fault_vaddr),
    .fault_mmu_exception_o         (akv_fault_mmu_exception),
    .context_ready_o               (akv_context_ready),
    .core_st_pending_i,
    .en_ld_st_translation_i,
    .mmu_req_o                     (akv_mmu_req),
    .mmu_vaddr_o                   (akv_mmu_vaddr),
    .mmu_is_store_o                (akv_mmu_is_store),
    .mmu_valid_i,
    .mmu_paddr_i,
    .mmu_exception_valid_i         (mmu_exception_i.valid),
    .mmu_exception_i,
    .physical_check_valid_o        (akv_physical_check_valid),
    .physical_check_addr_o         (akv_physical_check_addr),
    .physical_check_bytes_o        (akv_physical_check_bytes),
    .physical_range_allowed_i      (akv_physical_range_allowed),
    .axi_ar_o                      (akv_axi_ar),
    .axi_ar_valid_o                (akv_axi_ar_valid),
    .axi_ar_ready_i                (akv_axi_ar_ready),
    .axi_r_i                       (akv_axi_r),
    .axi_r_valid_i                 (akv_axi_r_valid),
    .axi_r_ready_o                 (akv_axi_r_ready),
    .ldu_result_req_o              (akv_ldu_result_req),
    .ldu_result_id_o               (akv_ldu_result_id),
    .ldu_result_addr_o             (akv_ldu_result_addr),
    .ldu_result_wdata_o            (akv_ldu_result_wdata),
    .ldu_result_be_o               (akv_ldu_result_be),
    .ldu_result_gnt_i              (akv_ldu_result_gnt),
    .ldu_result_final_gnt_i        (akv_ldu_result_final_gnt),
    .busy_o                        (akv_busy),
    .command_cycles_o              (akv_command_cycles),
    .full_count_o                  (akv_full_count),
    .refill_count_o                (akv_refill_count),
    .load_count_o                  (akv_load_count),
    .release_count_o               (akv_release_count),
    .v2_full_count_o               (akv_v2_full_count),
    .v2_refill_count_o             (akv_v2_refill_count),
    .v2_row_load_count_o           (akv_v2_row_load_count),
    .v2_column_load_count_o        (akv_v2_column_load_count),
    .v2_k_view_bank_cycles_o       (akv_v2_k_view_bank_cycles),
    .v2_bank_conflict_cycles_o     (akv_v2_bank_conflict_cycles),
    .v2_rejected_count_o           (akv_v2_rejected_count),
    .q_external_bytes_o            (akv_q_external_bytes),
    .kv_external_bytes_o           (akv_kv_external_bytes),
    .replay_bytes_o                (akv_replay_bytes),
    .replay_backpressure_cycles_o  (akv_replay_backpressure_cycles),
    .read_range_count_o            (akv_read_range_count),
    .read_translation_count_o      (akv_read_translation_count),
    .read_ar_count_o               (akv_read_ar_count),
    .read_beat_count_o             (akv_read_beat_count),
    .read_payload_bytes_o          (akv_read_payload_bytes),
    .read_store_wait_cycles_o      (akv_read_store_wait_cycles),
    .read_backpressure_cycles_o    (akv_read_backpressure_cycles),
    .read_outstanding_occupancy_sum_o(
        akv_read_outstanding_occupancy_sum),
    .read_outstanding_max_o        (akv_read_outstanding_max),
    .read_outstanding_full_cycles_o(akv_read_outstanding_full_cycles)
  );

  //////////////////
  //  Assertions  //
  //////////////////

`ifndef SYNTHESIS
  if (QbsEnable) begin : gen_qbs_integration_assertions
    longint unsigned qbs_command_sequence_q;

    always_ff @(posedge clk_i) begin
      if (!rst_ni) begin
        qbs_command_sequence_q <= '0;
      end else begin
        if (qbs_command_fire)
          qbs_command_sequence_q <= qbs_command_sequence_q + 1'b1;

        assert (!(qbs_success_valid && qbs_fault_valid))
          else $fatal(1, "QBS command cannot succeed and fault together");
        assert (qbs_busy == qbs_active_q)
          else $fatal(1, "QBS engine activity diverged from VLSU ownership");

        if (qbs_command_fire) begin
          assert (normal_vlsu_idle && (qbs_command_m inside {[1:4]}))
            else $fatal(1, "QBS command accepted before a valid ownership handoff");
        end

        if (qbs_active_q) begin
          // The lanes may pre-stage operands for the next blocked memory
          // instruction. That does not constitute VLSU ownership; only an
          // accepted normal command or activity on a shared interface does.
          assert (!normal_pe_req_valid && addrgen_idle && !normal_mmu_req &&
                  !normal_addrgen_ack && !load_complete && !store_complete &&
                  !(normal_axi_req.ar_valid || normal_axi_req.aw_valid ||
                    normal_axi_req.w_valid || |normal_ldu_result_req))
            else $fatal(1, "Normal VLSU issued memory or VRF work during QBS ownership");
          assert (!(axi_req.aw_valid || axi_req.w_valid || axi_req.b_ready))
            else $fatal(1, "Read-only QBS ownership drove an AXI write channel");
          assert (pe_req_ready_o == '0)
            else $fatal(1, "VLSU accepted another request during blocking QBS execution");
        end

        if (qbs_axi_ar_valid || qbs_axi_r_ready || qbs_mmu_req ||
            |qbs_ldu_result_req) begin
          assert (qbs_active_q)
            else $fatal(1, "QBS used a shared VLSU interface without ownership");
        end

        if (|qbs_ldu_result_req) begin
          assert (!qbs_fault_valid)
            else $fatal(1, "QBS fault overlapped architectural VRF commit");
          for (int unsigned lane = 0; lane < NrLanes; lane++) begin
            if (qbs_ldu_result_req[lane])
              assert (qbs_ldu_result_id[lane] == qbs_command_id_q)
                else $fatal(1, "QBS commit used the wrong vector instruction ID");
          end
        end

        if (qbs_terminal) begin
          assert ($onehot({qbs_success_valid, qbs_fault_valid}))
            else $fatal(1, "QBS terminal response is not a unique outcome");
          assert (addrgen_ack_o &&
                  pe_resp_o[OffsetLoad].vinsn_done[qbs_command_id_q])
            else $fatal(1, "QBS terminal response did not retire its load PE entry");

          if ($test$plusargs("QBS_PERF")) begin
            $display("[QBS_PERF] seq=%0d id=%0d m=%0d vlen=%0d lanes=%0d success=%0d fault=%0d validation_fault=%0d validation_error=%0d read_fault=%0d busy_cycles=%0d read_ranges=%0d translations=%0d ar=%0d r_beats=%0d payload_bytes=%0d store_wait_cycles=%0d read_backpressure_cycles=%0d read_outstanding_occ_sum=%0d read_outstanding_max=%0d read_outstanding_full_cycles=%0d phase_setup_cycles=%0d phase_activation_cycles=%0d phase_weight_cycles=%0d phase_compute_cycles=%0d phase_overlap_cycles=%0d phase_drain_cycles=%0d phase_scheduler_cycles=%0d phase_commit_cycles=%0d phase_fault_cycles=%0d phase_terminal_cycles=%0d weight_prefetch_wait_cycles=%0d tiles=%0d weight_bytes=%0d activation_bytes=%0d useful_pairs=%0d pair_capacity=%0d dot_active_cycles=%0d fp_uop_issue=%0d fp_table_occ_sum=%0d fp_table_occ_max=%0d fp_table_full_cycles=%0d accumulator_updates=%0d commit_groups=%0d commit_backpressure_cycles=%0d activation_access=%0d context_fill_count=%0d context_reuse_count=%0d context_reuse_block_count=%0d context_read_bytes=%0d activation_axi_bytes_saved=%0d context_replay_cycles=%0d context_replay_compute_overlap_cycles=%0d context_validation_fault_count=%0d probe_context_start_blocked_cycles=%0d probe_compute_without_dot_issue_cycles=%0d probe_profile_result_blocked_cycles=%0d probe_fp_slot_blocked_cycles=%0d probe_fp_accumulator_blocked_cycles=%0d probe_fp_other_blocked_cycles=%0d probe_fp_input_blocked_cycles=%0d probe_fp_no_schedulable_uop_cycles=%0d probe_fp_busy_cycles=%0d probe_profile_context_occ_sum=%0d probe_profile_two_context_cycles=%0d probe_profile_drain_only_cycles=%0d probe_profile_correction_pending_cycles=%0d probe_profile_result_pending_cycles=%0d probe_read_range_blocked_cycles=%0d probe_read_range_fifo_blocked_cycles=%0d probe_read_ar_slot_blocked_cycles=%0d probe_read_ar_ready_blocked_cycles=%0d probe_read_response_idle_cycles=%0d probe_read_data_sink_blocked_cycles=%0d probe_read_completion_blocked_cycles=%0d probe_read_translation_wait_cycles=%0d probe_weight_wait_no_outstanding_cycles=%0d probe_weight_wait_response_idle_cycles=%0d probe_weight_wait_r_transfer_cycles=%0d probe_weight_wait_r_blocked_cycles=%0d",
                     qbs_command_sequence_q, qbs_command_id_q, qbs_command_m,
                     VLEN, NrLanes,
                     qbs_success_valid, qbs_fault_valid,
                     qbs_fault_is_validation, qbs_validation_error,
                     qbs_read_fault_kind, qbs_command_cycles + 1'b1,
                     qbs_read_range_count, qbs_read_translation_count,
                     qbs_read_ar_count, qbs_read_beat_count,
                     qbs_read_payload_bytes, qbs_read_store_wait_cycles,
                     qbs_read_backpressure_cycles,
                     qbs_read_outstanding_occupancy_sum,
                     qbs_read_outstanding_max,
                     qbs_read_outstanding_full_cycles,
                     qbs_phase_setup_cycles,
                     qbs_phase_activation_cycles, qbs_phase_weight_cycles,
                     qbs_phase_compute_cycles, qbs_phase_overlap_cycles,
                     qbs_phase_drain_cycles, qbs_phase_scheduler_cycles,
                     qbs_phase_commit_cycles, qbs_phase_fault_cycles,
                     qbs_phase_terminal_cycles,
                     qbs_weight_prefetch_wait_cycles, qbs_tiles_computed,
                     qbs_weight_bytes, qbs_activation_bytes,
                     qbs_useful_pairs, qbs_pair_capacity,
                     qbs_dot_active_cycles, qbs_fp_uop_issue,
                     qbs_fp_table_occupancy_sum,
                     qbs_fp_table_occupancy_max,
                     qbs_fp_table_full_cycles, qbs_accumulator_updates,
                     qbs_commit_word_count,
                     qbs_commit_backpressure_cycles,
                     qbs_activation_access,
                     qbs_context_fill_count, qbs_context_reuse_count,
                     qbs_context_reuse_block_count, qbs_context_read_bytes,
                     qbs_activation_axi_bytes_saved,
                     qbs_context_replay_cycles,
                     qbs_context_replay_compute_overlap_cycles,
                     qbs_context_validation_fault_count,
                     i_qbs_engine.i_compute_engine.
                         probe_context_start_blocked_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_compute_without_dot_issue_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_profile_result_blocked_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_fp_slot_blocked_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_fp_accumulator_blocked_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_fp_other_blocked_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_fp_input_blocked_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_fp_no_schedulable_uop_cycles_q,
                     i_qbs_engine.i_compute_engine.probe_fp_busy_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_profile_context_occupancy_sum_q,
                     i_qbs_engine.i_compute_engine.
                         probe_profile_two_context_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_profile_drain_only_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_profile_correction_pending_cycles_q,
                     i_qbs_engine.i_compute_engine.
                         probe_profile_result_pending_cycles_q,
                     i_qbs_engine.i_read_engine.probe_range_blocked_cycles_q,
                     i_qbs_engine.i_read_engine.
                         probe_range_fifo_blocked_cycles_q,
                     i_qbs_engine.i_read_engine.probe_ar_slot_blocked_cycles_q,
                     i_qbs_engine.i_read_engine.
                         probe_ar_ready_blocked_cycles_q,
                     i_qbs_engine.i_read_engine.probe_response_idle_cycles_q,
                     i_qbs_engine.i_read_engine.
                         probe_data_sink_blocked_cycles_q,
                     i_qbs_engine.i_read_engine.
                         probe_completion_blocked_cycles_q,
                     i_qbs_engine.i_read_engine.
                         probe_translation_wait_cycles_q,
                     i_qbs_engine.probe_weight_wait_no_outstanding_cycles_q,
                     i_qbs_engine.probe_weight_wait_response_idle_cycles_q,
                     i_qbs_engine.probe_weight_wait_r_transfer_cycles_q,
                     i_qbs_engine.probe_weight_wait_r_blocked_cycles_q);
          end
        end

        if (!qbs_active_q && !akv_active_q &&
            pe_req_i.op != VQBEXEC && !pe_req_is_akv) begin
          assert (axi_req.ar_valid == normal_axi_req.ar_valid &&
                  axi_req.aw_valid == normal_axi_req.aw_valid &&
                  axi_req.w_valid == normal_axi_req.w_valid &&
                  ldu_result_req_o == normal_ldu_result_req)
            else $fatal(1, "Idle QBS integration changed the normal VLSU request path");
          assert (normal_ldu_result_gnt == ldu_result_gnt_i &&
                  normal_ldu_result_final_gnt == ldu_result_final_gnt_i)
            else $fatal(1, "Idle QBS integration changed normal VRF grant routing");
        end
      end
    end
  end

  if (AkvEnable) begin : gen_akv_integration_assertions
    longint unsigned akv_command_sequence_q;
    pe_req_t akv_consumed_request_q;

    always_ff @(posedge clk_i) begin
      if (!rst_ni) begin
        akv_command_sequence_q <= '0;
        akv_consumed_request_q <= '0;
      end else begin
        if (akv_command_fire) begin
          akv_command_sequence_q <= akv_command_sequence_q + 1'b1;
          akv_consumed_request_q <= pe_req_i;
        end

        assert (!(qbs_active_q && akv_active_q))
          else $fatal(1, "QBS and AKV cannot own the VLSU together");
        assert (!(akv_success_valid && akv_fault_valid))
          else $fatal(1, "AKV command cannot succeed and fault together");
        assert (akv_busy == akv_active_q)
          else $fatal(1, "AKV engine activity diverged from VLSU ownership");

        if (akv_request_consumed_q && pe_req_valid_i && pe_req_is_akv) begin
          assert (pe_req_i == akv_consumed_request_q)
            else $fatal(1, "Held AKV PE request changed before withdrawal");
        end

        if (akv_command_fire) begin
          assert (!akv_request_consumed_q)
            else $fatal(1, "AKV accepted one held PE request more than once");
          assert (normal_vlsu_idle && !qbs_active_q)
            else $fatal(1, "AKV command accepted before VLSU ownership handoff");
          if (akv_command == AKV_COMMAND_LOAD &&
              pe_req_i.vl == vlen_t'(128)) begin
            assert (!pe_req_i.vd[0] && pe_req_i.vd <= 5'd30)
              else $fatal(1, "Illegal D128 AKV destination reached the VLSU");
          end
        end

        if (akv_command_early_ack) begin
          assert (akv_command_fire && akv_command inside {
                      AKV_COMMAND_LOAD, AKV_COMMAND_V2_COLUMN_LOAD})
            else $fatal(1, "AKV early acknowledgment was not a local load acceptance");
        end

        if (akv_active_q) begin
          // A following vector store may already have operands parked at the
          // VSTU input while its PE request is blocked. Permit that harmless
          // staging, but prohibit every state-changing normal VLSU action.
          assert (!normal_pe_req_valid && addrgen_idle && !normal_mmu_req &&
                  !normal_addrgen_ack && !load_complete && !store_complete &&
                  !(normal_axi_req.ar_valid || normal_axi_req.aw_valid ||
                    normal_axi_req.w_valid || |normal_ldu_result_req))
            else $fatal(1, "Normal VLSU issued work during AKV ownership");
          assert (!(axi_req.aw_valid || axi_req.w_valid || axi_req.b_ready))
            else $fatal(1, "Read-only AKV ownership drove an AXI write channel");
          assert (pe_req_ready_o == '0)
            else $fatal(1, "VLSU accepted another request during AKV execution");
        end

        if (akv_axi_ar_valid || akv_axi_r_ready || akv_mmu_req ||
            |akv_ldu_result_req) begin
          assert (akv_active_q)
            else $fatal(1, "AKV used a shared VLSU interface without ownership");
        end

        if (|akv_ldu_result_req) begin
          assert (!akv_fault_valid)
            else $fatal(1, "AKV fault overlapped architectural VRF replay");
          for (int unsigned lane = 0; lane < NrLanes; lane++) begin
            if (akv_ldu_result_req[lane])
              assert (akv_ldu_result_id[lane] == akv_command_id_q)
                else $fatal(1, "AKV replay used the wrong vector instruction ID");
          end
        end

        if (akv_terminal) begin
          assert ($onehot({akv_success_valid, akv_fault_valid}))
            else $fatal(1, "AKV terminal response is not a unique outcome");
          assert (pe_resp_o[OffsetLoad].vinsn_done[akv_command_id_q])
            else $fatal(1, "AKV terminal response did not retire its load PE entry");
          assert (akv_command_early_acked_q ? !addrgen_ack_o : addrgen_ack_o)
            else $fatal(1, "AKV scalar acknowledgment occurred at the wrong boundary");

          if ($test$plusargs("AKV_PERF")) begin
            $display("[AKV_PERF] seq=%0d id=%0d command=%0d success=%0d fault=%0d validation_fault=%0d validation_error=%0d read_fault=%0d context_ready=%0d busy_cycles=%0d full=%0d refill=%0d load=%0d release=%0d v2_full=%0d v2_refill=%0d v2_row_load=%0d v2_column_load=%0d v2_k_view_bank_cycles=%0d v2_bank_conflict_cycles=%0d v2_rejected=%0d q_external_bytes=%0d kv_external_bytes=%0d replay_bytes=%0d replay_backpressure_cycles=%0d read_ranges=%0d translations=%0d ar=%0d r_beats=%0d read_payload_bytes=%0d store_wait_cycles=%0d read_backpressure_cycles=%0d read_outstanding_occ_sum=%0d read_outstanding_max=%0d read_outstanding_full_cycles=%0d",
                     akv_command_sequence_q, akv_command_id_q, akv_command_q,
                     akv_success_valid, akv_fault_valid,
                     akv_fault_is_validation, akv_validation_error,
                     akv_read_fault_kind, akv_context_ready,
                     akv_command_cycles + 1'b1,
                     akv_full_count, akv_refill_count, akv_load_count,
                     akv_release_count, akv_v2_full_count,
                     akv_v2_refill_count, akv_v2_row_load_count,
                     akv_v2_column_load_count,
                     akv_v2_k_view_bank_cycles,
                     akv_v2_bank_conflict_cycles, akv_v2_rejected_count,
                     akv_q_external_bytes,
                     akv_kv_external_bytes, akv_replay_bytes,
                     akv_replay_backpressure_cycles,
                     akv_read_range_count, akv_read_translation_count,
                     akv_read_ar_count, akv_read_beat_count,
                     akv_read_payload_bytes, akv_read_store_wait_cycles,
                     akv_read_backpressure_cycles,
                     akv_read_outstanding_occupancy_sum,
                     akv_read_outstanding_max,
                     akv_read_outstanding_full_cycles);
          end
        end
      end
    end
  end
`endif

  if (AxiDataWidth == 0)
    $error("[vlsu] The data width of the AXI bus cannot be zero.");

  if (AxiAddrWidth == 0)
    $error("[vlsu] The address width of the AXI bus cannot be zero.");

  if (NrLanes == 0)
    $error("[vlsu] Ara needs to have at least one lane.");

endmodule : vlsu
