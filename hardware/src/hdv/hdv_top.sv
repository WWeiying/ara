// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Standalone top-level wrapper for the HDV prototype.  It wires the paper-level
// frontend blocks together and instantiates Ara as the vector backend shell.
// Ara's memory port and the reserved scalar memory master are merged into one
// system AXI port, following the structure used by ara_system.

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
  parameter type scalar_axi_ar_t   = logic,
  parameter type scalar_axi_r_t    = logic,
  parameter type scalar_axi_aw_t   = logic,
  parameter type scalar_axi_w_t    = logic,
  parameter type scalar_axi_b_t    = logic,
  parameter type scalar_axi_req_t  = logic,
  parameter type scalar_axi_resp_t = logic,
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
  input  logic [63:0]                        boot_addr_i,
  input  logic [2:0]                         hart_id_i,

  // Ara scan chain.
  input  logic                               scan_enable_i,
  input  logic                               scan_data_i,
  output logic                               scan_data_o,

  // Host-side task CSR access.
  input  logic                               csr_valid_i,
  input  logic                               csr_write_i,
  input  logic [11:0]                        csr_addr_i,
  input  logic [XLEN-1:0]                    csr_wdata_i,
  output logic                               csr_ready_o,
  output logic [XLEN-1:0]                    csr_rdata_o,
  output logic                               csr_error_o,

  // Instruction prefetch memory interface.
  output logic                               imem_req_valid_o,
  input  logic                               imem_req_ready_i,
  output addr_t                              imem_req_addr_o,
  input  logic                               imem_rsp_valid_i,
  output logic                               imem_rsp_ready_o,
  input  logic [FetchPacketWidth-1:0]        imem_rsp_data_i,

  // Frontend control hooks from the future scalar/vector backend.
  input  logic                               redirect_valid_i,
  input  addr_t                              redirect_pc_i,
  input  logic                               loop_lock_i,
  input  logic [NumSlots-2:0]                dep_break_i,

  // Task-level completion is intentionally external: a future task controller
  // should assert these only when the whole task, not one execute packet, ends.
  input  logic                               task_complete_i,
  input  logic                               task_error_i,
  output addr_t                              active_task_desc_o,
  output logic                               task_busy_o,
  output logic                               task_done_o,
  output logic                               task_error_o,

  // Scalar pipeline dispatch stream.
  output logic                               scalar_valid_o,
  input  logic                               scalar_ready_i,
  output logic [NumSlots-1:0]                scalar_insn_valid_o,
  output logic [NumSlots-1:0][31:0]          scalar_insn_o,
  output logic [NumSlots-1:0]                scalar_insn_is_32b_o,
  output addr_t [NumSlots-1:0]               scalar_insn_pc_o,
  output addr_t                              scalar_pc_o,
  input  logic                               scalar_done_i,

  // Vector pipeline dispatch stream.
  output logic                               vector_valid_o,
  input  logic                               vector_ready_i,
  output logic [NumSlots-1:0]                vector_insn_valid_o,
  output logic [NumSlots-1:0][31:0]          vector_insn_o,
  output logic [NumSlots-1:0]                vector_insn_is_32b_o,
  output addr_t [NumSlots-1:0]               vector_insn_pc_o,
  output addr_t                              vector_pc_o,
  input  logic                               vector_done_i,

  // Unified memory system AXI port for Ara and the scalar memory master.
  output system_axi_req_t                    axi_req_o,
  input  system_axi_resp_t                   axi_resp_i,

  // Execute-packet status from the hybrid dispatch block.
  input  logic                               backend_error_i,
  output logic                               execute_busy_o,
  output logic                               execute_done_o,
  output logic                               execute_error_o
);

  logic tiu_task_valid;
  logic tiu_task_ready;
  addr_t tiu_task_entry;
  addr_t tiu_task_desc;
  logic task_status_clear;

  logic tsu_task_valid;
  logic tsu_task_ready;
  addr_t tsu_task_entry;
  addr_t tsu_task_desc;
  logic tsu_busy;
  logic tsu_done;
  logic tsu_error;

  logic ipu_busy;
  logic packet_valid;
  logic packet_ready;
  logic [FetchPacketWidth-1:0] packet;
  addr_t packet_pc;
  addr_t active_task_desc;
  logic ipu_mem_req_valid;
  logic ipu_mem_req_ready;
  addr_t ipu_mem_req_addr;
  logic ipu_mem_rsp_valid;
  logic ipu_mem_rsp_ready;
  logic [FetchPacketWidth-1:0] ipu_mem_rsp_data;

  logic execute_valid;
  logic execute_ready;
  logic [NumSlots-1:0] execute_slot_valid;
  logic [NumSlots-1:0][SlotWidth-1:0] execute_slot;
  logic [NumSlots-1:0] execute_slot_is_32b;
  hdv_inst_class_e [NumSlots-1:0] execute_class;
  addr_t execute_pc;

  logic heu_busy;
  logic heu_execute_done;
  logic heu_execute_error;
  logic task_busy;
  logic dispatch_flush;

  axi_req_t ara_axi_req;
  axi_resp_t ara_axi_resp;
  axi_req_t ara_axi_req_inval;
  axi_resp_t ara_axi_resp_inval;
  axi_req_t scalar_axi_req;
  axi_resp_t scalar_axi_resp;
  axi_req_t hdv_imem_axi_req;
  axi_resp_t hdv_imem_axi_resp;
  scalar_axi_req_t scalar_narrow_axi_req;
  scalar_axi_resp_t scalar_narrow_axi_resp;

  cva6_to_acc_t acc_req;
  acc_to_cva6_t ara_acc_resp;
  acc_to_cva6_t ara_acc_resp_pack;
  logic acc_cons_en;
  logic inval_valid;
  logic inval_ready;
  logic [AxiAddrWidth-1:0] inval_addr;
  logic [63:0] hart_id;
  logic imem_read_inflight_d, imem_read_inflight_q;
  logic imem_ar_accept;
  logic imem_r_accept;

  assign task_busy         = tsu_busy | ipu_busy | heu_busy;
  assign task_busy_o       = task_busy;
  assign task_done_o       = tsu_done;
  assign task_error_o      = tsu_error;
  assign active_task_desc_o = active_task_desc;

  assign execute_busy_o  = heu_busy;
  assign execute_done_o  = heu_execute_done;
  assign execute_error_o = heu_execute_error;

  assign dispatch_flush = flush_i | task_error_i;
  assign hart_id = {'0, hart_id_i};

  assign imem_req_valid_o = ipu_mem_req_valid;
  assign ipu_mem_req_ready = !imem_read_inflight_q & hdv_imem_axi_resp.ar_ready;
  assign imem_req_addr_o = ipu_mem_req_addr;
  assign imem_rsp_ready_o = ipu_mem_rsp_ready;
  assign ipu_mem_rsp_valid = imem_read_inflight_q & hdv_imem_axi_resp.r_valid;
  assign ipu_mem_rsp_data = hdv_imem_axi_resp.r.data[FetchPacketWidth-1:0];

  assign imem_ar_accept = ipu_mem_req_valid & ipu_mem_req_ready;
  assign imem_r_accept  = ipu_mem_rsp_valid & ipu_mem_rsp_ready;

  always_comb begin : p_imem_axi_req
    hdv_imem_axi_req = '0;
    hdv_imem_axi_req.ar_valid = ipu_mem_req_valid & !imem_read_inflight_q;
    hdv_imem_axi_req.ar.id     = '0;
    hdv_imem_axi_req.ar.addr   = AxiAddrWidth'(ipu_mem_req_addr);
    hdv_imem_axi_req.ar.len    = '0;
    hdv_imem_axi_req.ar.size   = axi_pkg::size_t'($clog2(FetchPacketWidth / 8));
    hdv_imem_axi_req.ar.burst  = axi_pkg::BURST_INCR;
    hdv_imem_axi_req.ar.lock   = 1'b0;
    hdv_imem_axi_req.ar.cache  = axi_pkg::CACHE_MODIFIABLE;
    hdv_imem_axi_req.ar.prot   = '0;
    hdv_imem_axi_req.ar.qos    = '0;
    hdv_imem_axi_req.ar.region = '0;
    hdv_imem_axi_req.ar.user   = '0;
    hdv_imem_axi_req.r_ready   = imem_read_inflight_q & ipu_mem_rsp_ready;
  end

  always_comb begin : p_imem_state
    imem_read_inflight_d = imem_read_inflight_q;
    if (imem_ar_accept) begin
      imem_read_inflight_d = 1'b1;
    end
    if (imem_r_accept && hdv_imem_axi_resp.r.last) begin
      imem_read_inflight_d = 1'b0;
    end
    if (dispatch_flush) begin
      imem_read_inflight_d = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_imem_regs
    if (!rst_ni) begin
      imem_read_inflight_q <= 1'b0;
    end else begin
      imem_read_inflight_q <= imem_read_inflight_d;
    end
  end

  always_comb begin : pack_ara_invalidation
    ara_acc_resp_pack                      = ara_acc_resp;
    ara_acc_resp_pack.acc_resp.inval_valid = inval_valid;
    ara_acc_resp_pack.acc_resp.inval_addr  = inval_addr;
    inval_ready                            = acc_req.acc_req.inval_ready;
    acc_cons_en                            = acc_req.acc_req.acc_cons_en;
  end

`ifdef IDEAL_DISPATCHER
  accel_dispatcher_ideal #(
    .CVA6Cfg       (CVA6Cfg),
    .cva6_to_acc_t (cva6_to_acc_t),
    .acc_to_cva6_t (acc_to_cva6_t)
  ) i_accel_dispatcher_ideal (
    .clk_i      (clk_i),
    .rst_ni     (rst_ni),
    .acc_req_o  (acc_req),
    .acc_resp_i (ara_acc_resp)
  );

  assign scalar_narrow_axi_req = '0;
`else
  cva6 #(
    .CVA6Cfg            (CVA6Cfg),
    .cvxif_req_t        (cva6_to_acc_t),
    .cvxif_resp_t       (acc_to_cva6_t),
    .axi_ar_chan_t      (scalar_axi_ar_t),
    .axi_aw_chan_t      (scalar_axi_aw_t),
    .axi_w_chan_t       (scalar_axi_w_t),
    .b_chan_t           (scalar_axi_b_t),
    .r_chan_t           (scalar_axi_r_t),
    .noc_req_t          (scalar_axi_req_t),
    .noc_resp_t         (scalar_axi_resp_t),
    .accelerator_req_t  (accelerator_req_t),
    .accelerator_resp_t (accelerator_resp_t),
    .acc_mmu_req_t      (acc_mmu_req_t),
    .acc_mmu_resp_t     (acc_mmu_resp_t)
  ) i_ariane (
    .clk_i            (clk_i),
    .rst_ni           (rst_ni),
    .boot_addr_i      (boot_addr_i),
    .hart_id_i        (hart_id),
    .irq_i            ('0),
    .ipi_i            ('0),
    .time_irq_i       ('0),
    .debug_req_i      ('0),
    .clic_irq_valid_i ('0),
    .clic_irq_id_i    ('0),
    .clic_irq_level_i ('0),
    .clic_irq_priv_i  (riscv::priv_lvl_t'(2'b0)),
    .clic_irq_v_i     ('0),
    .clic_irq_vsid_i  ('0),
    .clic_irq_shv_i   ('0),
    .clic_irq_ready_o (/* Unconnected */),
    .clic_kill_req_i  ('0),
    .clic_kill_ack_o  (/* Unconnected */),
    .rvfi_probes_o    (/* Unconnected */),
    .cvxif_req_o      (acc_req),
    .cvxif_resp_i     (ara_acc_resp_pack),
    .noc_req_o        (scalar_narrow_axi_req),
    .noc_resp_i       (scalar_narrow_axi_resp)
  );
`endif

  ara #(
    .NrLanes            (NrLanes),
    .VLEN               (VLEN),
    .OSSupport          (OSSupport),
    .FPUSupport         (FPUSupport),
    .FPExtSupport       (FPExtSupport),
    .FixPtSupport       (FixPtSupport),
    .SegSupport         (SegSupport),
    .CVA6Cfg            (CVA6Cfg),
    .exception_t        (exception_t),
    .accelerator_req_t  (accelerator_req_t),
    .accelerator_resp_t (accelerator_resp_t),
    .acc_mmu_req_t      (acc_mmu_req_t),
    .acc_mmu_resp_t     (acc_mmu_resp_t),
    .cva6_to_acc_t      (cva6_to_acc_t),
    .acc_to_cva6_t      (acc_to_cva6_t),
    .AxiDataWidth       (AxiDataWidth),
    .AxiAddrWidth       (AxiAddrWidth),
    .axi_ar_t           (axi_ar_t),
    .axi_r_t            (axi_r_t),
    .axi_aw_t           (axi_aw_t),
    .axi_w_t            (axi_w_t),
    .axi_b_t            (axi_b_t),
    .axi_req_t          (axi_req_t),
    .axi_resp_t         (axi_resp_t)
  ) i_ara (
    .clk_i         (clk_i),
    .rst_ni        (rst_ni),
    .scan_enable_i (scan_enable_i),
    .scan_data_i   (scan_data_i),
    .scan_data_o   (scan_data_o),
    .acc_req_i     (acc_req),
    .acc_resp_o    (ara_acc_resp),
    .axi_req_o     (ara_axi_req),
    .axi_resp_i    (ara_axi_resp)
  );

  axi_inval_filter #(
    .MaxTxns     (4),
    .AddrWidth   (AxiAddrWidth),
    .L1LineWidth (CVA6Cfg.DCACHE_LINE_WIDTH / 8),
    .aw_chan_t   (axi_aw_t),
    .req_t       (axi_req_t),
    .resp_t      (axi_resp_t)
  ) i_axi_inval_filter (
    .clk_i         (clk_i),
    .rst_ni        (rst_ni),
    .en_i          (acc_cons_en),
    .slv_req_i     (ara_axi_req),
    .slv_resp_o    (ara_axi_resp),
    .mst_req_o     (ara_axi_req_inval),
    .mst_resp_i    (ara_axi_resp_inval),
    .inval_addr_o  (inval_addr),
    .inval_valid_o (inval_valid),
    .inval_ready_i (inval_ready)
  );

  axi_dw_converter #(
    .AxiSlvPortDataWidth (AxiNarrowDataWidth),
    .AxiMstPortDataWidth (AxiDataWidth),
    .AxiAddrWidth        (AxiAddrWidth),
    .AxiIdWidth          (AxiIdWidth),
    .AxiMaxReads         (2),
    .ar_chan_t           (scalar_axi_ar_t),
    .mst_r_chan_t        (axi_r_t),
    .slv_r_chan_t        (scalar_axi_r_t),
    .aw_chan_t           (scalar_axi_aw_t),
    .b_chan_t            (scalar_axi_b_t),
    .mst_w_chan_t        (axi_w_t),
    .slv_w_chan_t        (scalar_axi_w_t),
    .axi_mst_req_t       (axi_req_t),
    .axi_mst_resp_t      (axi_resp_t),
    .axi_slv_req_t       (scalar_axi_req_t),
    .axi_slv_resp_t      (scalar_axi_resp_t)
  ) i_scalar_axi_dwc (
    .clk_i      (clk_i),
    .rst_ni     (rst_ni),
    .slv_req_i  (scalar_narrow_axi_req),
    .slv_resp_o (scalar_narrow_axi_resp),
    .mst_req_o  (scalar_axi_req),
    .mst_resp_i (scalar_axi_resp)
  );

  axi_mux #(
    .SlvAxiIDWidth (AxiIdWidth),
    .slv_ar_chan_t (axi_ar_t),
    .slv_aw_chan_t (axi_aw_t),
    .slv_b_chan_t  (axi_b_t),
    .slv_r_chan_t  (axi_r_t),
    .slv_req_t     (axi_req_t),
    .slv_resp_t    (axi_resp_t),
    .mst_ar_chan_t (system_axi_ar_t),
    .mst_aw_chan_t (system_axi_aw_t),
    .w_chan_t      (system_axi_w_t),
    .mst_b_chan_t  (system_axi_b_t),
    .mst_r_chan_t  (system_axi_r_t),
    .mst_req_t     (system_axi_req_t),
    .mst_resp_t    (system_axi_resp_t),
    .NoSlvPorts    (3),
    .SpillAr       (1'b1),
    .SpillR        (1'b1),
    .SpillAw       (1'b1),
    .SpillW        (1'b1),
    .SpillB        (1'b1)
  ) i_system_mux (
    .clk_i      (clk_i),
    .rst_ni     (rst_ni),
    .test_i      (testmode_i),
    .slv_reqs_i  ({ara_axi_req_inval, scalar_axi_req, hdv_imem_axi_req}),
    .slv_resps_o ({ara_axi_resp_inval, scalar_axi_resp, hdv_imem_axi_resp}),
    .mst_req_o   (axi_req_o),
    .mst_resp_i  (axi_resp_i)
  );

  hdv_task_interface_unit #(
    .XLEN   (XLEN),
    .addr_t (addr_t)
  ) i_task_interface_unit (
    .clk_i               (clk_i),
    .rst_ni              (rst_ni),
    .csr_valid_i         (csr_valid_i),
    .csr_write_i         (csr_write_i),
    .csr_addr_i          (csr_addr_i),
    .csr_wdata_i         (csr_wdata_i),
    .csr_ready_o         (csr_ready_o),
    .csr_rdata_o         (csr_rdata_o),
    .csr_error_o         (csr_error_o),
    .task_valid_o        (tiu_task_valid),
    .task_ready_i        (tiu_task_ready),
    .task_entry_o        (tiu_task_entry),
    .task_desc_o         (tiu_task_desc),
    .task_busy_i         (task_busy),
    .task_done_i         (tsu_done),
    .task_error_i        (tsu_error),
    .task_status_clear_o (task_status_clear)
  );

  hdv_task_schedule_unit #(
    .XLEN       (XLEN),
    .QueueDepth (QueueDepth),
    .addr_t     (addr_t)
  ) i_task_schedule_unit (
    .clk_i            (clk_i),
    .rst_ni           (rst_ni),
    .flush_i          (flush_i),
    .testmode_i       (testmode_i),
    .status_clear_i   (task_status_clear),
    .task_in_valid_i  (tiu_task_valid),
    .task_in_ready_o  (tiu_task_ready),
    .task_in_entry_i  (tiu_task_entry),
    .task_in_desc_i   (tiu_task_desc),
    .task_out_valid_o (tsu_task_valid),
    .task_out_ready_i (tsu_task_ready),
    .task_out_entry_o (tsu_task_entry),
    .task_out_desc_o  (tsu_task_desc),
    .task_done_i      (task_complete_i),
    .task_error_i     (task_error_i),
    .busy_o           (tsu_busy),
    .done_o           (tsu_done),
    .error_o          (tsu_error)
  );

  hdv_instruction_prefetch_unit #(
    .XLEN             (XLEN),
    .FetchPacketWidth (FetchPacketWidth),
    .BufferBytes      (BufferBytes),
    .addr_t           (addr_t)
  ) i_instruction_prefetch_unit (
    .clk_i            (clk_i),
    .rst_ni           (rst_ni),
    .flush_i            (dispatch_flush),
    .task_valid_i      (tsu_task_valid),
    .task_ready_o      (tsu_task_ready),
    .task_entry_i      (tsu_task_entry),
    .task_desc_i       (tsu_task_desc),
    .mem_req_valid_o   (ipu_mem_req_valid),
    .mem_req_ready_i   (ipu_mem_req_ready),
    .mem_req_addr_o    (ipu_mem_req_addr),
    .mem_rsp_valid_i   (ipu_mem_rsp_valid),
    .mem_rsp_ready_o   (ipu_mem_rsp_ready),
    .mem_rsp_data_i    (ipu_mem_rsp_data),
    .packet_valid_o    (packet_valid),
    .packet_ready_i    (packet_ready),
    .packet_o          (packet),
    .packet_pc_o       (packet_pc),
    .task_desc_o       (active_task_desc),
    .redirect_valid_i  (redirect_valid_i),
    .redirect_pc_i     (redirect_pc_i),
    .loop_lock_i       (loop_lock_i),
    .task_complete_i    (task_complete_i | task_error_i),
    .busy_o            (ipu_busy)
  );

  hdv_vliw_pack_unit #(
    .XLEN             (XLEN),
    .FetchPacketWidth (FetchPacketWidth),
    .NumSlots         (NumSlots),
    .SlotWidth        (SlotWidth),
    .MaxIssueSlots    (MaxIssueSlots),
    .addr_t           (addr_t)
  ) i_vliw_pack_unit (
    .clk_i                  (clk_i),
    .rst_ni                 (rst_ni),
    .flush_i                (dispatch_flush),
    .packet_valid_i        (packet_valid),
    .packet_ready_o        (packet_ready),
    .packet_i              (packet),
    .packet_pc_i           (packet_pc),
    .dep_break_i            (dep_break_i),
    .execute_valid_o       (execute_valid),
    .execute_ready_i       (execute_ready),
    .execute_slot_valid_o  (execute_slot_valid),
    .execute_slot_o        (execute_slot),
    .execute_slot_is_32b_o (execute_slot_is_32b),
    .execute_class_o       (execute_class),
    .execute_pc_o          (execute_pc)
  );

  hdv_hybrid_execution_unit #(
    .XLEN      (XLEN),
    .NumSlots  (NumSlots),
    .SlotWidth (SlotWidth),
    .addr_t    (addr_t)
  ) i_hybrid_execution_unit (
    .clk_i                  (clk_i),
    .rst_ni                 (rst_ni),
    .flush_i                (dispatch_flush),
    .execute_valid_i       (execute_valid),
    .execute_ready_o       (execute_ready),
    .execute_slot_valid_i  (execute_slot_valid),
    .execute_slot_i        (execute_slot),
    .execute_slot_is_32b_i (execute_slot_is_32b),
    .execute_class_i       (execute_class),
    .execute_pc_i          (execute_pc),
    .scalar_valid_o         (scalar_valid_o),
    .scalar_ready_i         (scalar_ready_i),
    .scalar_insn_valid_o    (scalar_insn_valid_o),
    .scalar_insn_o          (scalar_insn_o),
    .scalar_insn_is_32b_o   (scalar_insn_is_32b_o),
    .scalar_insn_pc_o       (scalar_insn_pc_o),
    .scalar_pc_o            (scalar_pc_o),
    .vector_valid_o         (vector_valid_o),
    .vector_ready_i         (vector_ready_i),
    .vector_insn_valid_o    (vector_insn_valid_o),
    .vector_insn_o          (vector_insn_o),
    .vector_insn_is_32b_o   (vector_insn_is_32b_o),
    .vector_insn_pc_o       (vector_insn_pc_o),
    .vector_pc_o            (vector_pc_o),
    .scalar_done_i          (scalar_done_i),
    .vector_done_i          (vector_done_i),
    .backend_error_i        (backend_error_i),
    .busy_o                (heu_busy),
    .execute_done_o        (heu_execute_done),
    .execute_error_o       (heu_execute_error)
  );

endmodule : hdv_top
