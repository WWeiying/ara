// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Standalone top-level wrapper for the HDV prototype.  It wires the paper-level
// frontend blocks together, instantiates Ara as the vector backend, and connects
// HEU's vector dispatch stream to Ara via hdv_vec_dispatch_unit.
// The scalar dispatch ports remain external for the mock / future scalar backend.
// The AXI mux retains 3 slave slots (Ara, reserved-scalar, HDV-imem) so the
// system ID width is unchanged; the scalar slot is tied to zero until a real
// scalar backend is attached.

module hdv_top import hdv_pkg::*; import ara_pkg::*; import axi_pkg::*; #(
  parameter int unsigned XLEN             = 64,
  parameter int unsigned QueueDepth       = 4,
  parameter int unsigned FetchPacketWidth = 128,
  parameter int unsigned BufferBytes      = 64,
  parameter int unsigned NumSlots         = 6,
  parameter int unsigned SlotWidth        = 16,
  parameter int unsigned MaxIssueSlots    = NumSlots,
  parameter type addr_t = logic [XLEN-1:0],

  // Ara vector backend parameters.
  parameter int unsigned NrLanes      = 0,
  parameter int unsigned VLEN         = 0,
  parameter int unsigned OSSupport    = 1,
  parameter fpu_support_e   FPUSupport   = FPUSupportHalfSingleDouble,
  parameter fpext_support_e FPExtSupport = FPExtSupportEnable,
  parameter fixpt_support_e FixPtSupport = FixedPointEnable,
  parameter seg_support_e   SegSupport   = SegSupportEnable,
  parameter config_pkg::cva6_cfg_t CVA6Cfg = cva6_config_pkg::cva6_cfg,
  parameter type exception_t        = logic,
  parameter type accelerator_req_t  = logic,
  parameter type accelerator_resp_t = logic,
  parameter type acc_mmu_req_t      = logic,
  parameter type acc_mmu_resp_t     = logic,
  parameter type cva6_to_acc_t      = logic,
  parameter type acc_to_cva6_t      = logic,
  parameter int unsigned AxiAddrWidth = 64,
  parameter int unsigned AxiIdWidth   = 6,
  parameter int unsigned AxiNarrowDataWidth = 64,
  parameter int unsigned AxiDataWidth       = 64 * NrLanes / 2,
  parameter type axi_ar_t   = logic,
  parameter type axi_r_t    = logic,
  parameter type axi_aw_t   = logic,
  parameter type axi_w_t    = logic,
  parameter type axi_b_t    = logic,
  parameter type axi_req_t  = logic,
  parameter type axi_resp_t = logic,
  parameter type system_axi_ar_t   = logic,
  parameter type system_axi_r_t    = logic,
  parameter type system_axi_aw_t   = logic,
  parameter type system_axi_w_t    = logic,
  parameter type system_axi_b_t    = logic,
  parameter type system_axi_req_t  = logic,
  parameter type system_axi_resp_t = logic
) (
  input  logic                               clk_i,
  input  logic                               rst_ni,
  input  logic                               flush_i,
  input  logic                               testmode_i,

  // Ara scan chain.
  input  logic                               scan_enable_i,
  input  logic                               scan_data_i,
  output logic                               scan_data_o,

  // Host-side task CSR access.
  input  logic                               host_hdv_csr_valid_i,
  input  logic                               host_hdv_csr_write_i,
  input  logic [11:0]                        host_hdv_csr_addr_i,
  input  logic [XLEN-1:0]                    host_hdv_csr_wdata_i,
  output logic                               hdv_host_csr_ready_o,
  output logic [XLEN-1:0]                    hdv_host_csr_rdata_o,
  output logic                               hdv_host_csr_error_o,

  // Instruction prefetch memory interface.
  output logic                               hdv_imem_req_valid_o,
  input  logic                               imem_hdv_req_ready_i,
  output addr_t                              hdv_imem_req_addr_o,
  input  logic                               imem_hdv_rsp_valid_i,
  output logic                               hdv_imem_rsp_ready_o,
  input  logic [FetchPacketWidth-1:0]        imem_hdv_rsp_data_i,

  // Frontend control hooks from the future scalar/vector backend.
  input  logic                               ctrl_hdv_redirect_valid_i,
  input  addr_t                              ctrl_hdv_redirect_pc_i,
  input  logic                               ctrl_hdv_loop_lock_i,
  input  logic [NumSlots-2:0]                ctrl_hdv_dep_break_i,

  // Task-level completion signals.
  input  logic                               host_hdv_task_complete_i,
  input  logic                               host_hdv_task_error_i,
  output addr_t                              hdv_host_active_task_desc_o,
  output logic                               hdv_host_task_busy_o,
  output logic                               hdv_host_task_done_o,
  output logic                               hdv_host_task_error_o,

  // Scalar pipeline dispatch stream (still external — mock / future backend).
  output logic                               hdv_scalar_valid_o,
  input  logic                               scalar_hdv_ready_i,
  output logic [NumSlots-1:0]                hdv_scalar_insn_valid_o,
  output logic [NumSlots-1:0][31:0]          hdv_scalar_insn_o,
  output logic [NumSlots-1:0]                hdv_scalar_insn_is_32b_o,
  output addr_t [NumSlots-1:0]               hdv_scalar_insn_pc_o,
  output addr_t                              hdv_scalar_pc_o,
  input  logic                               scalar_hdv_accepted_i,

  // Unified memory system AXI port for Ara and the scalar memory master.
  output system_axi_req_t                    axi_req_o,
  input  system_axi_resp_t                   axi_resp_i,

  // Execute-packet status from the hybrid dispatch block.
  input  logic                               backend_hdv_error_i,
  output logic                               hdv_host_ep_busy_o,
  output logic                               hdv_host_ep_accepted_o,
  output logic                               hdv_host_ep_error_o
);

  // ─── Internal task / IPU / VLIWPU wires ────────────────────────────────────

  logic tiu_tsu_task_valid;
  logic tsu_tiu_task_ready;
  addr_t tiu_tsu_task_entry;
  addr_t tiu_tsu_task_desc;
  logic tiu_tsu_status_clear;

  logic tsu_ipu_task_valid;
  logic ipu_tsu_task_ready;
  addr_t tsu_ipu_task_entry;
  addr_t tsu_ipu_task_desc;
  logic tsu_top_busy;
  logic tsu_top_done;
  logic tsu_top_error;

  logic ipu_top_busy;
  logic ipu_vliwpu_packet_valid;
  logic vliwpu_ipu_packet_ready;
  logic [FetchPacketWidth-1:0] ipu_vliwpu_packet;
  addr_t ipu_vliwpu_packet_pc;
  addr_t ipu_top_active_task_desc;
  logic ipu_mem_req_valid;
  logic mem_ipu_req_ready;
  addr_t ipu_mem_req_addr;
  logic mem_ipu_rsp_valid;
  logic ipu_mem_rsp_ready;
  logic [FetchPacketWidth-1:0] mem_ipu_rsp_data;

  logic vliwpu_heu_execute_valid;
  logic heu_vliwpu_execute_ready;
  logic [NumSlots-1:0] vliwpu_heu_execute_slot_valid;
  logic [NumSlots-1:0][SlotWidth-1:0] vliwpu_heu_execute_slot;
  logic [NumSlots-1:0] vliwpu_heu_execute_slot_is_32b;
  hdv_inst_class_e [NumSlots-1:0] vliwpu_heu_execute_class;
  addr_t vliwpu_heu_execute_pc;

  logic heu_top_busy;
  logic heu_top_ep_accepted;
  logic heu_top_ep_error;
  logic task_busy;
  logic task_flush;
  logic dispatch_flush;

  // ─── Vector dispatch (HEU → vec_dispatch_unit → Ara) ─────────────────────

  logic        heu_vec_valid;
  logic        vec_heu_ready;
  logic        vec_heu_accepted;
  logic        vec_heu_error;
  logic [NumSlots-1:0]        heu_vec_insn_valid;
  logic [NumSlots-1:0][31:0]  heu_vec_insn;

  // ─── AXI wires ────────────────────────────────────────────────────────────

  axi_req_t ara_axi_req;
  axi_resp_t ara_axi_resp;
  axi_req_t ara_axi_req_inval;
  axi_resp_t ara_axi_resp_inval;
  // Scalar AXI slot: tied to zero until a real scalar backend is attached.
  axi_req_t  scalar_axi_req;
  axi_resp_t scalar_axi_resp;
  axi_req_t hdv_imem_axi_req;
  axi_resp_t hdv_imem_axi_resp;

  // ─── Ara accelerator interface ────────────────────────────────────────────

  cva6_to_acc_t acc_req;           // driven by vec_dispatch_unit
  acc_to_cva6_t ara_acc_resp;      // from Ara
  acc_to_cva6_t ara_acc_resp_pack; // with inval signals injected

  logic acc_cons_en;
  logic inval_valid;
  logic inval_ready;
  logic [AxiAddrWidth-1:0] inval_addr;
  logic imem_read_inflight_d, imem_read_inflight_q;
  logic imem_ar_accept;
  logic imem_r_accept;

  // ─── Combinatorial assignments ────────────────────────────────────────────

  assign task_busy                   = tsu_top_busy | ipu_top_busy | heu_top_busy;
  assign hdv_host_task_busy_o        = task_busy;
  assign hdv_host_task_done_o        = tsu_top_done;
  assign hdv_host_task_error_o       = tsu_top_error;
  assign hdv_host_active_task_desc_o = ipu_top_active_task_desc;

  assign hdv_host_ep_busy_o  = heu_top_busy;
  assign hdv_host_ep_accepted_o  = heu_top_ep_accepted;
  assign hdv_host_ep_error_o = heu_top_ep_error;

  assign task_flush     = flush_i | host_hdv_task_error_i;
  // A taken branch redirect restarts IPU from ctrl_hdv_redirect_pc_i and drops
  // any already-held packet/execute state in VLIWPU, HEU, and vector dispatch.
  // Do not feed this combined flush into IPU itself, otherwise IPU's redirect
  // path would be overwritten by its flush path.
  assign dispatch_flush = task_flush | ctrl_hdv_redirect_valid_i;

  // Scalar AXI slot produces no traffic until a real scalar backend is connected.
  assign scalar_axi_req = '0;

  // ─── Instruction-fetch AXI bridge ─────────────────────────────────────────

  assign hdv_imem_req_valid_o = ipu_mem_req_valid;
  assign mem_ipu_req_ready    = !imem_read_inflight_q & hdv_imem_axi_resp.ar_ready;
  assign hdv_imem_req_addr_o  = ipu_mem_req_addr;
  assign hdv_imem_rsp_ready_o = ipu_mem_rsp_ready;
  assign mem_ipu_rsp_valid    = imem_read_inflight_q & hdv_imem_axi_resp.r_valid;
  assign mem_ipu_rsp_data     = hdv_imem_axi_resp.r.data[FetchPacketWidth-1:0];

  assign imem_ar_accept = ipu_mem_req_valid & mem_ipu_req_ready;
  assign imem_r_accept  = mem_ipu_rsp_valid & ipu_mem_rsp_ready;

  always_comb begin : p_imem_axi_req
    hdv_imem_axi_req = '0;
    hdv_imem_axi_req.ar_valid      = ipu_mem_req_valid & !imem_read_inflight_q;
    hdv_imem_axi_req.ar.id         = '0;
    hdv_imem_axi_req.ar.addr       = AxiAddrWidth'(ipu_mem_req_addr);
    hdv_imem_axi_req.ar.len        = '0;
    hdv_imem_axi_req.ar.size       = axi_pkg::size_t'($clog2(FetchPacketWidth / 8));
    hdv_imem_axi_req.ar.burst      = axi_pkg::BURST_INCR;
    hdv_imem_axi_req.ar.lock       = 1'b0;
    hdv_imem_axi_req.ar.cache      = axi_pkg::CACHE_MODIFIABLE;
    hdv_imem_axi_req.ar.prot       = '0;
    hdv_imem_axi_req.ar.qos        = '0;
    hdv_imem_axi_req.ar.region     = '0;
    hdv_imem_axi_req.ar.user       = '0;
    hdv_imem_axi_req.r_ready       = imem_read_inflight_q & ipu_mem_rsp_ready;
  end

  always_comb begin : p_imem_state
    imem_read_inflight_d = imem_read_inflight_q;
    if (imem_ar_accept)                              imem_read_inflight_d = 1'b1;
    if (imem_r_accept && hdv_imem_axi_resp.r.last)  imem_read_inflight_d = 1'b0;
    if (dispatch_flush)                              imem_read_inflight_d = 1'b0;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_imem_regs
    if (!rst_ni) imem_read_inflight_q <= 1'b0;
    else         imem_read_inflight_q <= imem_read_inflight_d;
  end

  // ─── Ara cache-line invalidation packing ──────────────────────────────────
  // With acc_cons_en=0 the axi_inval_filter is disabled; inval_valid is always 0.
  // We still wire inval_ready / acc_cons_en from acc_req so the filter is
  // structurally connected and can be re-enabled when CVA6 is reattached.

  always_comb begin : pack_ara_invalidation
    ara_acc_resp_pack                      = ara_acc_resp;
    ara_acc_resp_pack.acc_resp.inval_valid = inval_valid;
    ara_acc_resp_pack.acc_resp.inval_addr  = inval_addr;
    inval_ready                            = acc_req.acc_req.inval_ready;
    acc_cons_en                            = acc_req.acc_req.acc_cons_en;
  end

  // ─── hdv_vec_dispatch_unit ────────────────────────────────────────────────

  hdv_vec_dispatch_unit #(
    .XLEN          (XLEN         ),
    .NumSlots      (NumSlots     ),
    .cva6_to_acc_t (cva6_to_acc_t),
    .acc_to_cva6_t (acc_to_cva6_t)
  ) i_vec_dispatch_unit (
    .clk_i               (clk_i           ),
    .rst_ni              (rst_ni          ),
    .flush_i             (task_flush      ),
    .heu_vec_valid_i     (heu_vec_valid   ),
    .vec_heu_ready_o     (vec_heu_ready   ),
    .heu_vec_insn_valid_i(heu_vec_insn_valid),
    .heu_vec_insn_i      (heu_vec_insn    ),
    .vec_heu_accepted_o      (vec_heu_accepted    ),
    .vec_heu_error_o     (vec_heu_error   ),
    .acc_req_o           (acc_req         ),
    .acc_resp_i          (ara_acc_resp_pack)
  );

  // ─── Ara ──────────────────────────────────────────────────────────────────

  ara #(
    .NrLanes            (NrLanes            ),
    .VLEN               (VLEN               ),
    .OSSupport          (OSSupport          ),
    .FPUSupport         (FPUSupport         ),
    .FPExtSupport       (FPExtSupport       ),
    .FixPtSupport       (FixPtSupport       ),
    .SegSupport         (SegSupport         ),
    .CVA6Cfg            (CVA6Cfg            ),
    .exception_t        (exception_t        ),
    .accelerator_req_t  (accelerator_req_t  ),
    .accelerator_resp_t (accelerator_resp_t ),
    .acc_mmu_req_t      (acc_mmu_req_t      ),
    .acc_mmu_resp_t     (acc_mmu_resp_t     ),
    .cva6_to_acc_t      (cva6_to_acc_t      ),
    .acc_to_cva6_t      (acc_to_cva6_t      ),
    .AxiDataWidth       (AxiDataWidth       ),
    .AxiAddrWidth       (AxiAddrWidth       ),
    .axi_ar_t           (axi_ar_t           ),
    .axi_r_t            (axi_r_t            ),
    .axi_aw_t           (axi_aw_t           ),
    .axi_w_t            (axi_w_t            ),
    .axi_b_t            (axi_b_t            ),
    .axi_req_t          (axi_req_t          ),
    .axi_resp_t         (axi_resp_t         )
  ) i_ara (
    .clk_i         (clk_i         ),
    .rst_ni        (rst_ni        ),
    .scan_enable_i (scan_enable_i ),
    .scan_data_i   (scan_data_i   ),
    .scan_data_o   (scan_data_o   ),
    .acc_req_i     (acc_req       ),
    .acc_resp_o    (ara_acc_resp  ),
    .axi_req_o     (ara_axi_req   ),
    .axi_resp_i    (ara_axi_resp  )
  );

  axi_inval_filter #(
    .MaxTxns     (4),
    .AddrWidth   (AxiAddrWidth),
    .L1LineWidth (CVA6Cfg.DCACHE_LINE_WIDTH / 8),
    .aw_chan_t   (axi_aw_t),
    .req_t       (axi_req_t),
    .resp_t      (axi_resp_t)
  ) i_axi_inval_filter (
    .clk_i         (clk_i          ),
    .rst_ni        (rst_ni         ),
    .en_i          (acc_cons_en    ),
    .slv_req_i     (ara_axi_req    ),
    .slv_resp_o    (ara_axi_resp   ),
    .mst_req_o     (ara_axi_req_inval),
    .mst_resp_i    (ara_axi_resp_inval),
    .inval_addr_o  (inval_addr     ),
    .inval_valid_o (inval_valid    ),
    .inval_ready_i (inval_ready    )
  );

  // Three-slave AXI mux: Ara | scalar (tied to 0) | HDV-imem.
  // The scalar slot is kept at NoSlvPorts=3 to preserve the system AXI ID width
  // (AxiCoreIdWidth + log2(3) = AxiSocIdWidth).
  axi_mux #(
    .SlvAxiIDWidth (AxiIdWidth      ),
    .slv_ar_chan_t (axi_ar_t        ),
    .slv_aw_chan_t (axi_aw_t        ),
    .slv_b_chan_t  (axi_b_t         ),
    .slv_r_chan_t  (axi_r_t         ),
    .slv_req_t     (axi_req_t       ),
    .slv_resp_t    (axi_resp_t      ),
    .mst_ar_chan_t (system_axi_ar_t ),
    .mst_aw_chan_t (system_axi_aw_t ),
    .w_chan_t      (system_axi_w_t  ),
    .mst_b_chan_t  (system_axi_b_t  ),
    .mst_r_chan_t  (system_axi_r_t  ),
    .mst_req_t     (system_axi_req_t),
    .mst_resp_t    (system_axi_resp_t),
    .NoSlvPorts    (3               ),
    .SpillAr       (1'b1            ),
    .SpillR        (1'b1            ),
    .SpillAw       (1'b1            ),
    .SpillW        (1'b1            ),
    .SpillB        (1'b1            )
  ) i_system_mux (
    .clk_i      (clk_i                                              ),
    .rst_ni     (rst_ni                                             ),
    .test_i     (testmode_i                                         ),
    .slv_reqs_i ({ara_axi_req_inval, scalar_axi_req, hdv_imem_axi_req}),
    .slv_resps_o({ara_axi_resp_inval, scalar_axi_resp, hdv_imem_axi_resp}),
    .mst_req_o  (axi_req_o                                         ),
    .mst_resp_i (axi_resp_i                                        )
  );

  // ─── TIU ──────────────────────────────────────────────────────────────────

  hdv_task_interface_unit #(
    .XLEN   (XLEN  ),
    .addr_t (addr_t)
  ) i_task_interface_unit (
    .clk_i                   (clk_i                 ),
    .rst_ni                  (rst_ni                ),
    .host_tiu_csr_valid_i    (host_hdv_csr_valid_i  ),
    .host_tiu_csr_write_i    (host_hdv_csr_write_i  ),
    .host_tiu_csr_addr_i     (host_hdv_csr_addr_i   ),
    .host_tiu_csr_wdata_i    (host_hdv_csr_wdata_i  ),
    .tiu_host_csr_ready_o    (hdv_host_csr_ready_o  ),
    .tiu_host_csr_rdata_o    (hdv_host_csr_rdata_o  ),
    .tiu_host_csr_error_o    (hdv_host_csr_error_o  ),
    .tiu_tsu_task_valid_o    (tiu_tsu_task_valid    ),
    .tsu_tiu_task_ready_i    (tsu_tiu_task_ready    ),
    .tiu_tsu_task_entry_o    (tiu_tsu_task_entry    ),
    .tiu_tsu_task_desc_o     (tiu_tsu_task_desc     ),
    .top_tiu_task_busy_i     (task_busy             ),
    .tsu_tiu_task_done_i     (tsu_top_done          ),
    .tsu_tiu_task_error_i    (tsu_top_error         ),
    .tiu_tsu_status_clear_o  (tiu_tsu_status_clear  )
  );

  // ─── TSU ──────────────────────────────────────────────────────────────────

  hdv_task_schedule_unit #(
    .XLEN       (XLEN       ),
    .QueueDepth (QueueDepth ),
    .addr_t     (addr_t     )
  ) i_task_schedule_unit (
    .clk_i                   (clk_i                 ),
    .rst_ni                  (rst_ni                ),
    .flush_i                 (flush_i               ),
    .testmode_i              (testmode_i            ),
    .tiu_tsu_status_clear_i  (tiu_tsu_status_clear  ),
    .tiu_tsu_task_valid_i    (tiu_tsu_task_valid    ),
    .tsu_tiu_task_ready_o    (tsu_tiu_task_ready    ),
    .tiu_tsu_task_entry_i    (tiu_tsu_task_entry    ),
    .tiu_tsu_task_desc_i     (tiu_tsu_task_desc     ),
    .tsu_ipu_task_valid_o    (tsu_ipu_task_valid    ),
    .ipu_tsu_task_ready_i    (ipu_tsu_task_ready    ),
    .tsu_ipu_task_entry_o    (tsu_ipu_task_entry    ),
    .tsu_ipu_task_desc_o     (tsu_ipu_task_desc     ),
    .top_tsu_task_done_i     (host_hdv_task_complete_i),
    .top_tsu_task_error_i    (host_hdv_task_error_i ),
    .tsu_top_busy_o          (tsu_top_busy          ),
    .tsu_top_done_o          (tsu_top_done          ),
    .tsu_top_error_o         (tsu_top_error         )
  );

  // ─── IPU ──────────────────────────────────────────────────────────────────

  hdv_instruction_prefetch_unit #(
    .XLEN             (XLEN            ),
    .FetchPacketWidth (FetchPacketWidth ),
    .BufferBytes      (BufferBytes     ),
    .addr_t           (addr_t          )
  ) i_instruction_prefetch_unit (
    .clk_i                     (clk_i                   ),
    .rst_ni                    (rst_ni                  ),
    .flush_i                   (task_flush              ),
    .tsu_ipu_task_valid_i      (tsu_ipu_task_valid      ),
    .ipu_tsu_task_ready_o      (ipu_tsu_task_ready      ),
    .tsu_ipu_task_entry_i      (tsu_ipu_task_entry      ),
    .tsu_ipu_task_desc_i       (tsu_ipu_task_desc       ),
    .ipu_mem_req_valid_o       (ipu_mem_req_valid       ),
    .mem_ipu_req_ready_i       (mem_ipu_req_ready       ),
    .ipu_mem_req_addr_o        (ipu_mem_req_addr        ),
    .mem_ipu_rsp_valid_i       (mem_ipu_rsp_valid       ),
    .ipu_mem_rsp_ready_o       (ipu_mem_rsp_ready       ),
    .mem_ipu_rsp_data_i        (mem_ipu_rsp_data        ),
    .ipu_vliwpu_packet_valid_o (ipu_vliwpu_packet_valid ),
    .vliwpu_ipu_packet_ready_i (vliwpu_ipu_packet_ready ),
    .ipu_vliwpu_packet_o       (ipu_vliwpu_packet       ),
    .ipu_vliwpu_packet_pc_o    (ipu_vliwpu_packet_pc    ),
    .ipu_top_task_desc_o       (ipu_top_active_task_desc),
    .redirect_valid_i          (ctrl_hdv_redirect_valid_i),
    .redirect_pc_i             (ctrl_hdv_redirect_pc_i  ),
    .loop_lock_i               (ctrl_hdv_loop_lock_i    ),
    .top_ipu_task_complete_i   (host_hdv_task_complete_i | host_hdv_task_error_i),
    .ipu_top_busy_o            (ipu_top_busy            )
  );

  // ─── VLIWPU ───────────────────────────────────────────────────────────────

  hdv_vliw_pack_unit #(
    .XLEN             (XLEN            ),
    .FetchPacketWidth (FetchPacketWidth ),
    .NumSlots         (NumSlots        ),
    .SlotWidth        (SlotWidth       ),
    .MaxIssueSlots    (MaxIssueSlots   ),
    .addr_t           (addr_t          )
  ) i_vliw_pack_unit (
    .clk_i                              (clk_i                       ),
    .rst_ni                             (rst_ni                      ),
    .flush_i                            (dispatch_flush              ),
    .ipu_vliwpu_packet_valid_i          (ipu_vliwpu_packet_valid     ),
    .vliwpu_ipu_packet_ready_o          (vliwpu_ipu_packet_ready     ),
    .ipu_vliwpu_packet_i                (ipu_vliwpu_packet           ),
    .ipu_vliwpu_packet_pc_i             (ipu_vliwpu_packet_pc        ),
    .ctrl_vliwpu_dep_break_i            (ctrl_hdv_dep_break_i        ),
    .vliwpu_heu_execute_valid_o         (vliwpu_heu_execute_valid    ),
    .heu_vliwpu_execute_ready_i         (heu_vliwpu_execute_ready    ),
    .vliwpu_heu_execute_slot_valid_o    (vliwpu_heu_execute_slot_valid),
    .vliwpu_heu_execute_slot_o          (vliwpu_heu_execute_slot     ),
    .vliwpu_heu_execute_slot_is_32b_o   (vliwpu_heu_execute_slot_is_32b),
    .vliwpu_heu_execute_class_o         (vliwpu_heu_execute_class    ),
    .vliwpu_heu_execute_pc_o            (vliwpu_heu_execute_pc       )
  );

  // ─── HEU ──────────────────────────────────────────────────────────────────

  hdv_hybrid_execution_unit #(
    .XLEN      (XLEN      ),
    .NumSlots  (NumSlots  ),
    .SlotWidth (SlotWidth ),
    .addr_t    (addr_t    )
  ) i_hybrid_execution_unit (
    .clk_i                          (clk_i                    ),
    .rst_ni                         (rst_ni                   ),
    .flush_i                        (dispatch_flush           ),
    .vliwpu_heu_execute_valid_i     (vliwpu_heu_execute_valid ),
    .heu_vliwpu_execute_ready_o     (heu_vliwpu_execute_ready ),
    .vliwpu_heu_execute_slot_valid_i(vliwpu_heu_execute_slot_valid),
    .vliwpu_heu_execute_slot_i      (vliwpu_heu_execute_slot  ),
    .vliwpu_heu_execute_slot_is_32b_i(vliwpu_heu_execute_slot_is_32b),
    .vliwpu_heu_execute_class_i     (vliwpu_heu_execute_class ),
    .vliwpu_heu_execute_pc_i        (vliwpu_heu_execute_pc    ),
    // Scalar dispatch — still exposed externally (mock / future backend)
    .heu_scalar_valid_o             (hdv_scalar_valid_o       ),
    .scalar_heu_ready_i             (scalar_hdv_ready_i       ),
    .heu_scalar_insn_valid_o        (hdv_scalar_insn_valid_o  ),
    .heu_scalar_insn_o              (hdv_scalar_insn_o        ),
    .heu_scalar_insn_is_32b_o       (hdv_scalar_insn_is_32b_o ),
    .heu_scalar_insn_pc_o           (hdv_scalar_insn_pc_o     ),
    .heu_scalar_pc_o                (hdv_scalar_pc_o          ),
    // Vector dispatch — routed internally to vec_dispatch_unit → Ara
    .heu_vector_valid_o             (heu_vec_valid            ),
    .vector_heu_ready_i             (vec_heu_ready            ),
    .heu_vector_insn_valid_o        (heu_vec_insn_valid       ),
    .heu_vector_insn_o              (heu_vec_insn             ),
    .heu_vector_insn_is_32b_o       (/* unconnected */        ),
    .heu_vector_insn_pc_o           (/* unconnected */        ),
    .heu_vector_pc_o                (/* unconnected */        ),
    // Done / error from backends
    .scalar_heu_accepted_i              (scalar_hdv_accepted_i        ),
    .vector_heu_accepted_i              (vec_heu_accepted             ),
    .backend_heu_error_i            (backend_hdv_error_i | vec_heu_error),
    .heu_top_busy_o                 (heu_top_busy             ),
    .heu_top_ep_accepted_o         (heu_top_ep_accepted     ),
    .heu_top_ep_error_o        (heu_top_ep_error    )
  );

endmodule : hdv_top
