// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// Ara's System, containing Ariane and Ara.

`include "rvfi_types.svh"

module ara_system import axi_pkg::*; import ara_pkg::*; #(
    // RVV Parameters
    parameter int                      unsigned NrLanes            = 0,                               // Number of parallel vector lanes.
    parameter int                      unsigned VLEN               = 0,                               // VLEN [bit]
    parameter int                      unsigned OSSupport          = 1,                               // Support for floating-point data types
    parameter fpu_support_e                     FPUSupport         = FPUSupportHalfSingleDouble,
    // External support for vfrec7, vfrsqrt7
    parameter fpext_support_e                   FPExtSupport       = FPExtSupportEnable,
    // Support for fixed-point data types
    parameter fixpt_support_e                   FixPtSupport       = FixedPointEnable,
    // Support for segment memory operations
    parameter seg_support_e                     SegSupport         = SegSupportEnable,
    // Ariane configuration
    parameter config_pkg::cva6_cfg_t            CVA6Cfg            = cva6_config_pkg::cva6_cfg,
    // CVA6-related parameters
    parameter type                              exception_t        = logic,
    parameter type                              accelerator_req_t  = logic,
    parameter type                              accelerator_resp_t = logic,
    parameter type                              acc_mmu_req_t      = logic,
    parameter type                              acc_mmu_resp_t     = logic,
    parameter type                              cva6_to_acc_t      = logic,
    parameter type                              acc_to_cva6_t      = logic,
    // AXI Interface
    parameter int                      unsigned AxiAddrWidth       = 64,
    parameter int                      unsigned AxiIdWidth         = 6,
    parameter int                      unsigned AxiNarrowDataWidth = 64,
    parameter int                      unsigned AxiWideDataWidth   = 64*NrLanes/2,
    parameter type                              ariane_axi_ar_t    = logic,
    parameter type                              ariane_axi_r_t     = logic,
    parameter type                              ariane_axi_aw_t    = logic,
    parameter type                              ariane_axi_w_t     = logic,
    parameter type                              ariane_axi_b_t     = logic,
    parameter type                              ariane_axi_req_t   = logic,
    parameter type                              ariane_axi_resp_t  = logic,
    parameter type                              ara_axi_ar_t       = logic,
    parameter type                              ara_axi_r_t        = logic,
    parameter type                              ara_axi_aw_t       = logic,
    parameter type                              ara_axi_w_t        = logic,
    parameter type                              ara_axi_b_t        = logic,
    parameter type                              ara_axi_req_t      = logic,
    parameter type                              ara_axi_resp_t     = logic,
    parameter type                              system_axi_ar_t    = logic,
    parameter type                              system_axi_r_t     = logic,
    parameter type                              system_axi_aw_t    = logic,
    parameter type                              system_axi_w_t     = logic,
    parameter type                              system_axi_b_t     = logic,
    parameter type                              system_axi_req_t   = logic,
    parameter type                              system_axi_resp_t  = logic
  ) (
    input  logic                    clk_i,
    input  logic                    rst_ni,
    input  logic             [63:0] boot_addr_i,
    input                     [2:0] hart_id_i,
    // Scan chain
    input  logic                    scan_enable_i,
    input  logic                    scan_data_i,
    output logic                    scan_data_o,
    // AXI Interface
    output system_axi_req_t         axi_req_o,
    input  system_axi_resp_t        axi_resp_i
  );

  `include "axi/assign.svh"
  `include "axi/typedef.svh"

  ///////////
  //  AXI  //
  ///////////

  ariane_axi_req_t  ariane_narrow_axi_req;
  ariane_axi_resp_t ariane_narrow_axi_resp;
  ara_axi_req_t     ariane_axi_req, ara_axi_req_inval, ara_axi_req;
  ara_axi_resp_t    ariane_axi_resp, ara_axi_resp_inval, ara_axi_resp;

  //////////////////////
  //  Ara and Ariane  //
  //////////////////////

  // Accelerator ports
  cva6_to_acc_t        acc_req;
  acc_to_cva6_t        acc_resp;
  logic                                 acc_resp_valid;
  logic                                 acc_resp_ready;
  logic                                 acc_cons_en;
  logic              [AxiAddrWidth-1:0] inval_addr;
  logic                                 inval_valid;
  logic                                 inval_ready;

`ifdef FOR_VERIFY
  localparam type rvfi_instr_t = `RVFI_INSTR_T(CVA6Cfg);
  localparam type rvfi_csr_elmt_t = `RVFI_CSR_ELMT_T(CVA6Cfg);
  localparam type rvfi_csr_t = `RVFI_CSR_T(CVA6Cfg, rvfi_csr_elmt_t);
  localparam type rvfi_to_iti_t = `RVFI_TO_ITI_T(CVA6Cfg);
  localparam type rvfi_probes_instr_t = `RVFI_PROBES_INSTR_T(CVA6Cfg);
  localparam type rvfi_probes_csr_t = `RVFI_PROBES_CSR_T(CVA6Cfg);
  localparam type rvfi_probes_t = struct packed {
    rvfi_probes_csr_t   csr;
    rvfi_probes_instr_t instr;
  };

  rvfi_probes_t rvfi_probes;
  rvfi_instr_t [CVA6Cfg.NrCommitPorts-1:0] rvfi_instr;
  rvfi_csr_t rvfi_csr;
  rvfi_to_iti_t rvfi_to_iti;

  localparam int unsigned VerifyVAddrWidth =
      cf_math_pkg::idx_width((VLEN / 8 / NrLanes) * 32);
  logic [NrLanes-1:0][4:0] verify_wb_valid;
  vid_t [NrLanes-1:0][4:0] verify_wb_id;
  logic [NrLanes-1:0][4:0][VerifyVAddrWidth-1:0] verify_wb_addr;
  elen_t [NrLanes-1:0][4:0] verify_wb_wdata;
  logic [NrLanes-1:0][4:0][7:0] verify_wb_be;

`endif

  // Support max 8 cores, for now
  logic [63:0] hart_id;
  assign hart_id = {'0, hart_id_i};

  // Pack invalidation interface into acc interface
  acc_to_cva6_t acc_resp_pack;
  always_comb begin : pack_inval
    acc_resp_pack                      = acc_resp;
    acc_resp_pack.acc_resp.inval_valid = inval_valid;
    acc_resp_pack.acc_resp.inval_addr  = inval_addr;
    inval_ready                        = acc_req.acc_req.inval_ready;
    acc_cons_en                        = acc_req.acc_req.acc_cons_en;
  end

`ifdef IDEAL_DISPATCHER
  // Perfect dispatcher to Ara
  accel_dispatcher_ideal #(
    .CVA6Cfg(CVA6Cfg),
    .cva6_to_acc_t(cva6_to_acc_t),
    .acc_to_cva6_t(acc_to_cva6_t)
  ) i_accel_dispatcher_ideal (
    .clk_i            (clk_i                 ),
    .rst_ni           (rst_ni                ),
    .acc_req_o        (acc_req               ),
    .acc_resp_i       (acc_resp              )
  );
`else
  cva6 #(
    .CVA6Cfg          (CVA6Cfg           ),
    .cvxif_req_t      (cva6_to_acc_t     ),
    .cvxif_resp_t     (acc_to_cva6_t     ),
    .axi_ar_chan_t    (ariane_axi_ar_t   ),
    .axi_aw_chan_t    (ariane_axi_aw_t   ),
    .axi_w_chan_t     (ariane_axi_w_t    ),
    .b_chan_t         (ariane_axi_b_t    ),
    .r_chan_t         (ariane_axi_r_t    ),
    .noc_req_t        (ariane_axi_req_t  ),
    .noc_resp_t       (ariane_axi_resp_t ),
    .accelerator_req_t (accelerator_req_t),
    .accelerator_resp_t(accelerator_resp_t),
    .acc_mmu_req_t     (acc_mmu_req_t),
    .acc_mmu_resp_t    (acc_mmu_resp_t)
`ifdef FOR_VERIFY
    ,.rvfi_probes_instr_t(rvfi_probes_instr_t)
    ,.rvfi_probes_csr_t  (rvfi_probes_csr_t  )
    ,.rvfi_probes_t      (rvfi_probes_t      )
`endif
  ) i_ariane (
    .clk_i            (clk_i                   ),
    .rst_ni           (rst_ni                  ),
    .boot_addr_i      (boot_addr_i             ),
    .hart_id_i        (hart_id                 ),
    .irq_i            ('0                      ),
    .ipi_i            ('0                      ),
    .time_irq_i       ('0                      ),
    .debug_req_i      ('0                      ),
    .clic_irq_valid_i ('0                      ),
    .clic_irq_id_i    ('0                      ),
    .clic_irq_level_i ('0                      ),
    .clic_irq_priv_i  (riscv::priv_lvl_t'(2'b0)),
    .clic_irq_shv_i   ('0                      ),
    .clic_irq_ready_o (/* empty */             ),
    .clic_kill_req_i  ('0                      ),
    .clic_kill_ack_o  (/* empty */             ),
`ifdef FOR_VERIFY
    .rvfi_probes_o    (rvfi_probes             ),
`else
    .rvfi_probes_o    (/* empty */             ),
`endif
    // Accelerator ports
    .cvxif_req_o      (acc_req                 ),
    .cvxif_resp_i     (acc_resp_pack           ),
    .noc_req_o        (ariane_narrow_axi_req   ),
    .noc_resp_i       (ariane_narrow_axi_resp  )
  );

`ifdef FOR_VERIFY
  for (genvar lane = 0; lane < NrLanes; lane++) begin : gen_verify_wb
    assign verify_wb_valid[lane] = i_ara.gen_lanes[lane].i_lane.verify_wb_valid_o;
    assign verify_wb_id[lane]    = i_ara.gen_lanes[lane].i_lane.verify_wb_id_o;
    assign verify_wb_addr[lane]  = i_ara.gen_lanes[lane].i_lane.verify_wb_addr_o;
    assign verify_wb_wdata[lane] = i_ara.gen_lanes[lane].i_lane.verify_wb_wdata_o;
    assign verify_wb_be[lane]    = i_ara.gen_lanes[lane].i_lane.verify_wb_be_o;
  end

  cva6_rvfi #(
    .CVA6Cfg            (CVA6Cfg            ),
    .rvfi_instr_t       (rvfi_instr_t       ),
    .rvfi_csr_t         (rvfi_csr_t         ),
    .rvfi_probes_instr_t(rvfi_probes_instr_t),
    .rvfi_probes_csr_t  (rvfi_probes_csr_t  ),
    .rvfi_probes_t      (rvfi_probes_t      ),
    .rvfi_to_iti_t      (rvfi_to_iti_t      )
  ) i_cva6_rvfi (
    .clk_i         (clk_i       ),
    .rst_ni        (rst_ni      ),
    .rvfi_probes_i (rvfi_probes),
    .rvfi_instr_o  (rvfi_instr ),
    .rvfi_to_iti_o (rvfi_to_iti),
    .rvfi_csr_o    (rvfi_csr   )
  );

  ara_commit_monitor #(
    .NrCommitPorts    (CVA6Cfg.NrCommitPorts),
    .NrVInsn          (NrVInsn                 ),
    .TransIdWidth     (CVA6Cfg.TRANS_ID_BITS   ),
    .NrLanes          (NrLanes                  ),
    .VLEN             (VLEN                     ),
    .VAddrWidth       (VerifyVAddrWidth         ),
    .rvfi_instr_t     (rvfi_instr_t          ),
    .accelerator_req_t(accelerator_req_t     ),
    .accelerator_resp_t(accelerator_resp_t   )
  ) i_ara_commit_monitor (
    .clk_i       (clk_i            ),
    .rst_ni      (rst_ni           ),
    .rvfi_instr_i(rvfi_instr       ),
    .acc_req_i   (acc_req.acc_req  ),
    .acc_resp_i  (acc_resp.acc_resp),
    .backend_alloc_i   (i_ara.i_sequencer.verify_vinsn_alloc),
    .backend_alloc_id_i(i_ara.i_sequencer.vinsn_id_n),
    .backend_arch_seq_i(i_ara.ara_req.verify_arch_seq),
    .backend_arch_insn_i(i_ara.ara_req.verify_arch_insn),
    .backend_trans_id_i(i_ara.ara_req.verify_trans_id),
    .backend_done_i    (i_ara.i_sequencer.verify_vinsn_done),
    .backend_use_vd_i  (i_ara.ara_req.use_vd),
    .backend_vd_i      (i_ara.ara_req.vd),
    .backend_eew_i     (i_ara.ara_req.vtype.vsew),
    .backend_vl_i      (i_ara.ara_req.vl),
    .backend_vstart_i  (i_ara.ara_req.vstart),
    .wb_valid_i        (verify_wb_valid),
    .wb_id_i           (verify_wb_id),
    .wb_addr_i         (verify_wb_addr),
    .wb_wdata_i        (verify_wb_wdata),
    .wb_be_i           (verify_wb_be)
  );
`endif
`endif

  axi_dw_converter #(
    .AxiSlvPortDataWidth(AxiNarrowDataWidth),
    .AxiMstPortDataWidth(AxiWideDataWidth  ),
    .AxiAddrWidth       (AxiAddrWidth      ),
    .AxiIdWidth         (AxiIdWidth        ),
    .AxiMaxReads        (2                 ),
    .ar_chan_t          (ariane_axi_ar_t   ),
    .mst_r_chan_t       (ara_axi_r_t       ),
    .slv_r_chan_t       (ariane_axi_r_t    ),
    .aw_chan_t          (ariane_axi_aw_t   ),
    .b_chan_t           (ariane_axi_b_t    ),
    .mst_w_chan_t       (ara_axi_w_t       ),
    .slv_w_chan_t       (ariane_axi_w_t    ),
    .axi_mst_req_t      (ara_axi_req_t     ),
    .axi_mst_resp_t     (ara_axi_resp_t    ),
    .axi_slv_req_t      (ariane_axi_req_t  ),
    .axi_slv_resp_t     (ariane_axi_resp_t )
  ) i_ariane_axi_dwc (
    .clk_i     (clk_i                 ),
    .rst_ni    (rst_ni                ),
`ifdef IDEAL_DISPATCHER
    .slv_req_i ('0                    ),
`else
    .slv_req_i (ariane_narrow_axi_req ),
`endif
    .slv_resp_o(ariane_narrow_axi_resp),
    .mst_req_o (ariane_axi_req        ),
    .mst_resp_i(ariane_axi_resp       )
  );

  axi_inval_filter #(
    .MaxTxns    (4                              ),
    .AddrWidth  (AxiAddrWidth                   ),
    .L1LineWidth(CVA6Cfg.DCACHE_LINE_WIDTH/8    ),
    .aw_chan_t  (ara_axi_aw_t                   ),
    .req_t      (ara_axi_req_t                  ),
    .resp_t     (ara_axi_resp_t                 )
  ) i_axi_inval_filter (
    .clk_i        (clk_i             ),
    .rst_ni       (rst_ni            ),
`ifdef IDEAL_DISPATCHER
    .en_i         (1'b0              ),
`else
    .en_i         (acc_cons_en       ),
`endif
    .slv_req_i    (ara_axi_req       ),
    .slv_resp_o   (ara_axi_resp      ),
    .mst_req_o    (ara_axi_req_inval ),
    .mst_resp_i   (ara_axi_resp_inval),
    .inval_addr_o (inval_addr        ),
    .inval_valid_o(inval_valid       ),
`ifdef IDEAL_DISPATCHER
    .inval_ready_i(1'b0              )
`else
    .inval_ready_i(inval_ready       )
`endif
  );

  ara #(
    .NrLanes           (NrLanes           ),
    .VLEN              (VLEN              ),
    .OSSupport         (OSSupport         ),
    .FPUSupport        (FPUSupport        ),
    .FPExtSupport      (FPExtSupport      ),
    .FixPtSupport      (FixPtSupport      ),
    .SegSupport        (SegSupport        ),
    .CVA6Cfg           (CVA6Cfg           ),
    .exception_t       (exception_t       ),
    .accelerator_req_t (accelerator_req_t ),
    .accelerator_resp_t(accelerator_resp_t),
    .acc_mmu_req_t     (acc_mmu_req_t     ),
    .acc_mmu_resp_t    (acc_mmu_resp_t    ),
    .cva6_to_acc_t     (cva6_to_acc_t     ),
    .acc_to_cva6_t     (acc_to_cva6_t     ),
    .AxiDataWidth      (AxiWideDataWidth  ),
    .AxiAddrWidth      (AxiAddrWidth      ),
    .axi_ar_t          (ara_axi_ar_t      ),
    .axi_r_t           (ara_axi_r_t       ),
    .axi_aw_t          (ara_axi_aw_t      ),
    .axi_w_t           (ara_axi_w_t       ),
    .axi_b_t           (ara_axi_b_t       ),
    .axi_req_t         (ara_axi_req_t     ),
    .axi_resp_t        (ara_axi_resp_t    )
  ) i_ara (
    .clk_i           (clk_i         ),
    .rst_ni          (rst_ni        ),
    .scan_enable_i   (scan_enable_i ),
    .scan_data_i     (1'b0          ),
    .scan_data_o     (/* Unused */  ),
    .acc_req_i       (acc_req       ),
    .acc_resp_o      (acc_resp      ),
    .axi_req_o       (ara_axi_req   ),
    .axi_resp_i      (ara_axi_resp  )
  );

  axi_mux #(
    .SlvAxiIDWidth(AxiIdWidth       ),
    .slv_ar_chan_t(ara_axi_ar_t     ),
    .slv_aw_chan_t(ara_axi_aw_t     ),
    .slv_b_chan_t (ara_axi_b_t      ),
    .slv_r_chan_t (ara_axi_r_t      ),
    .slv_req_t    (ara_axi_req_t    ),
    .slv_resp_t   (ara_axi_resp_t   ),
    .mst_ar_chan_t(system_axi_ar_t  ),
    .mst_aw_chan_t(system_axi_aw_t  ),
    .w_chan_t     (system_axi_w_t   ),
    .mst_b_chan_t (system_axi_b_t   ),
    .mst_r_chan_t (system_axi_r_t   ),
    .mst_req_t    (system_axi_req_t ),
    .mst_resp_t   (system_axi_resp_t),
    .NoSlvPorts   (2                ),
    .SpillAr      (1'b1             ),
    .SpillR       (1'b1             ),
    .SpillAw      (1'b1             ),
    .SpillW       (1'b1             ),
    .SpillB       (1'b1             )
  ) i_system_mux (
    .clk_i      (clk_i                                ),
    .rst_ni     (rst_ni                               ),
    .test_i     (1'b0                                 ),
    .slv_reqs_i ({ara_axi_req_inval, ariane_axi_req}  ),
    .slv_resps_o({ara_axi_resp_inval, ariane_axi_resp}),
    .mst_req_o  (axi_req_o                            ),
    .mst_resp_i (axi_resp_i                           )
  );

endmodule : ara_system
