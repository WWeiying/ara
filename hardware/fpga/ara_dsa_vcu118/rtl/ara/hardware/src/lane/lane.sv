// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// This is one of Ara's  lanes. It contains part of the vector register file
// together with the execution units.

`include "ara/ara.svh"

module lane import ara_pkg::*; import rvv_pkg::*; #(
    parameter  int           unsigned NrLanes               = 1, // Number of lanes
    parameter  int           unsigned VLEN                  = 0,
    parameter  config_pkg::cva6_cfg_t CVA6Cfg               = cva6_config_pkg::cva6_cfg,
    // Support for floating-point data types
    parameter  fpu_support_e          FPUSupport            = FPUSupportHalfSingleDouble,
    // External support for vfrec7, vfrsqrt7
    parameter  fpext_support_e        FPExtSupport          = FPExtSupportEnable,
    // Support for fixed-point data types
    parameter  fixpt_support_e        FixPtSupport          = FixedPointEnable,
    // To please Verilator
    parameter  int           unsigned pe_req_t_bits         = 0,
    parameter  int           unsigned pe_resp_t_bits        = 0,
    // Dependant parameters. DO NOT CHANGE!
    // VRF Parameters
    localparam int           unsigned VLENB           = VLEN / 8,
    localparam int           unsigned MaxVLenPerLane  = VLEN / NrLanes,       // In bits
    localparam int           unsigned MaxVLenBPerLane = VLENB / NrLanes,      // In bytes
    localparam int           unsigned VRFSizePerLane  = MaxVLenPerLane * 32,  // In bits
    localparam int           unsigned VRFBSizePerLane = MaxVLenBPerLane * 32, // In bytes
    // Address of an element in the lane's VRF
    localparam type                   vaddr_t         = logic [$clog2(VRFBSizePerLane)-1:0],
    localparam int           unsigned DataWidth       = $bits(elen_t), // Width of the lane datapath
    localparam type                   strb_t          = logic [DataWidth/8-1:0], // Byte-strobe type
    // vl_csr type
    localparam type                   vlen_t          = logic [$clog2(VLEN+1)-1:0]
  ) (
    input  logic                                           clk_i,
    input  logic                                           rst_ni,
    // Scan chain
    input  logic                                           scan_enable_i,
    input  logic                                           scan_data_i,
    output logic                                           scan_data_o,
    // Lane ID
    input  logic     [cf_math_pkg::idx_width(NrLanes)-1:0] lane_id_i,
    // Interface with the dispatcher
    output logic                                           vxsat_flag_o,
    input  vxrm_t                                          alu_vxrm_i,
    output logic     [4:0]                                 fflags_ex_o,
    output logic                                           fflags_ex_valid_o,
    // Support for store exception flush
    input  logic                                           lsu_ex_flush_i,
    output logic                                           lsu_ex_flush_o,
    // Interface with the sequencer
    input  `STRUCT_PORT_BITS(pe_req_t_bits)                pe_req_i,
    input  logic                                           pe_req_valid_i,
    input  logic     [NrVInsn-1:0]                         pe_vinsn_running_i,
    output logic                                           pe_req_ready_o,
    output `STRUCT_PORT_BITS(pe_resp_t_bits)               pe_resp_o,
    output logic                                           alu_vinsn_done_o,
    output logic                                           mfpu_vinsn_done_o,
    input  logic                [NrVInsn-1:0][NrVInsn-1:0] global_hazard_table_i,
    output logic                                           mfpu_reduction_any_active_o,
    input  logic                                           mfpu_reduction_global_any_active_i,
    // Interface with the Store unit
    output elen_t                                          stu_operand_o,
    output logic                                           stu_operand_valid_o,
    input  logic                                           stu_operand_ready_i,
    // Interface with the Slide/Address Generation unit
    output elen_t                                          sldu_addrgen_operand_o,
    output logic                                           sldu_operand_valid_o,
    output logic                                           sldu_operand_reduction_o,
    output logic                                           addrgen_operand_valid_o,
    input  logic                                           sldu_operand_ready_i,
    input  sldu_mux_e                                      sldu_mux_sel_i,
    input  logic                                           addrgen_operand_ready_i,
    // Interface with the Slide unit
    input  logic                                           sldu_result_req_i,
    input  vid_t                                           sldu_result_id_i,
    input  vaddr_t                                         sldu_result_addr_i,
    input  elen_t                                          sldu_result_wdata_i,
    input  strb_t                                          sldu_result_be_i,
    output logic                                           sldu_result_gnt_o,
    input  logic                                           sldu_red_valid_i,
    output logic                                           sldu_result_final_gnt_o,
    // Interface with the Load unit
    input  logic                                           ldu_result_req_i,
    input  vid_t                                           ldu_result_id_i,
    input  vaddr_t                                         ldu_result_addr_i,
    input  elen_t                                          ldu_result_wdata_i,
    input  strb_t                                          ldu_result_be_i,
    output logic                                           ldu_result_gnt_o,
    output logic                                           ldu_result_final_gnt_o,
    // Interface with the Mask unit
    output `STRUCT_VECT(elen_t, [NrMaskFUnits+2-1:0])      mask_operand_o,
    output logic                [NrMaskFUnits+2-1:0]       mask_operand_valid_o,
    input  logic                [NrMaskFUnits+2-1:0]       mask_operand_ready_i,
    input  logic                                           masku_result_req_i,
    input  vid_t                                           masku_result_id_i,
    input  vaddr_t                                         masku_result_addr_i,
    input  elen_t                                          masku_result_wdata_i,
    input  strb_t                                          masku_result_be_i,
    output logic                                           masku_result_gnt_o,
    output logic                                           masku_result_final_gnt_o,
    input  logic                                           masku_vrgat_req_valid_i,
    output logic                                           masku_vrgat_req_ready_o,
    input  vrgat_req_t                                     masku_vrgat_req_i,
    // Interface between the Mask unit and the VFUs
    input  strb_t                                          mask_i,
    input  logic                                           mask_valid_i,
    input  vfu_e                                           mask_target_fu_i,
    output logic                                           mask_ready_o
`ifdef FOR_VERIFY
    ,output logic [4:0]                                    verify_wb_valid_o
    ,output vid_t [4:0]                                    verify_wb_id_o
    ,output vaddr_t [4:0]                                  verify_wb_addr_o
    ,output elen_t [4:0]                                   verify_wb_wdata_o
    ,output strb_t [4:0]                                   verify_wb_be_o
`endif
  );

  `include "common_cells/registers.svh"
  `include "ara/ara_typedef.svh"

  ///////////////////
  //  Definitions  //
  ///////////////////

  // This is the interface between the lane's sequencer and the operand request stage, which
  // makes consecutive requests to the vector elements inside the VRF.
  typedef struct packed {
    vid_t id; // ID of the vector instruction

    logic [4:0] vs; // Vector register operand

    logic scale_vl; // Rescale vl taking into account the new and old EEW

    resize_e cvt_resize;    // Resizing of FP conversions

    logic is_reduct; // Is this a reduction?
    logic is_slide; // Is this a slide?
    logic source_snapshot_capture;
    logic source_snapshot_replay;

    rvv_pkg::vew_e eew;        // Effective element width
    opqueue_conversion_e conv; // Type conversion

    target_fu_e target_fu;     // Target FU of the opqueue (if it is not clear)

    // Vector machine metadata
    rvv_pkg::vtype_t vtype;
    vlen_t vl;
    vlen_t vstart;

    // Hazards
    logic [NrVInsn-1:0] hazard;
    logic [NrVInsn-1:0] hazard_source_lifetime;
    logic [NrVInsn-1:0] hazard_wait_complete;
  } operand_request_cmd_t;

  typedef struct packed {
    rvv_pkg::vew_e eew;        // Effective element width
    vlen_t elem_count;         // Vector body length
    opqueue_conversion_e conv; // Type conversion
    logic [1:0] ntr_red;       // Neutral type for reductions
    logic is_reduct;           // Is this a reduction?
    target_fu_e target_fu;     // Target FU of the opqueue (if it is not clear)
  } operand_queue_cmd_t;

  // This is the interface between the lane's sequencer and the lane's VFUs.
  typedef struct packed {
    vid_t id; // ID of the vector instruction

    ara_op_e op; // Operation
    logic vm;    // Masked instruction

    logic use_vs1;   // This operation uses vs1
    logic use_vs2;   // This operation uses vs1
    logic use_vd_op; // This operation uses vd as an operand as well
    // A narrowing instruction may replay an aliased narrow vs1/old-vd after
    // the physical destination group was converted for its wide vs2.
    logic preserve_narrow_vd;

    elen_t scalar_op;    // Scalar operand
    logic use_scalar_op; // This operation uses the scalar operand
    logic skip_sldu_operand; // SLDU operation completes without the shared operand stream

    vfu_e vfu; // VFU responsible for this instruction

    logic [4:0] vd; // Vector destination register
    logic use_vd;

    logic swap_vs2_vd_op; // If asserted: vs2 is kept in MulFPU opqueue C, and vd_op in MulFPU A

    fpnew_pkg::roundmode_e fp_rm; // Rounding-Mode for FP operations
    logic wide_fp_imm;            // Widen FP immediate (re-encoding)
    resize_e cvt_resize;    // Resizing of FP conversions

    // Vector machine metadata
    vlen_t vl;
    vlen_t vstart;
    rvv_pkg::vtype_t vtype;
  } vfu_operation_t;

  /////////////////
  //  Spill Reg  //
  /////////////////

  // Cut the mask_ready_o timing-critical path
  strb_t alu_mask, mfpu_mask;
  logic  alu_mask_valid, alu_mask_ready;
  logic  mfpu_mask_valid, mfpu_mask_ready;
  logic  alu_mask_input_ready, mfpu_mask_input_ready;

  assign mask_ready_o = (mask_target_fu_i inside {VFU_Alu, VFU_MaskUnit})
                      ? alu_mask_input_ready
                      : (mask_target_fu_i == VFU_MFpu)
                        ? mfpu_mask_input_ready : 1'b0;

  spill_register #(
    .T(strb_t)
  ) i_alu_mask_ready_spill_register (
    .clk_i  (clk_i       ),
    .rst_ni (rst_ni      ),
    .valid_i(mask_valid_i &&
             (mask_target_fu_i inside {VFU_Alu, VFU_MaskUnit})),
    .ready_o(alu_mask_input_ready),
    .data_i (mask_i       ),
    .valid_o(alu_mask_valid),
    .ready_i(alu_mask_ready),
    .data_o (alu_mask     )
  );

  spill_register #(
    .T(strb_t)
  ) i_mfpu_mask_ready_spill_register (
    .clk_i  (clk_i       ),
    .rst_ni (rst_ni      ),
    .valid_i(mask_valid_i && mask_target_fu_i == VFU_MFpu),
    .ready_o(mfpu_mask_input_ready),
    .data_i (mask_i       ),
    .valid_o(mfpu_mask_valid),
    .ready_i(mfpu_mask_ready),
    .data_o (mfpu_mask    )
  );

  /////////////////
  //  Sequencer  //
  /////////////////

  // Interface with the operand requesters
  operand_request_cmd_t [NrOperandQueues-1:0] operand_request;
  logic                 [NrOperandQueues-1:0] operand_request_valid;
  logic                 [NrOperandQueues-1:0] operand_request_ready;
  // Interface with the vector functional units
  vfu_operation_t                             vfu_operation;
  logic                                       vfu_operation_valid;
  logic                                       alu_ready;
  logic                 [NrVInsn-1:0]         alu_vinsn_done;
  logic                                       mfpu_ready;
  logic                 [NrVInsn-1:0]         mfpu_vinsn_done;
  // Interface with the MaskB operand queue (VRGATHER/VCOMPRESS)
  logic                                       mask_b_cmd_pop_d, mask_b_cmd_pop_q;
  `FF(mask_b_cmd_pop_q, mask_b_cmd_pop_d, 1'b0, clk_i, rst_ni);


  // Support for store exception flush
  logic lsu_ex_flush_op_req_d, lsu_ex_flush_op_req_q;
  `FF(lsu_ex_flush_op_req_q, lsu_ex_flush_op_req_d, 1'b0, clk_i, rst_ni);

  // Additional signals to please Verilator's hierarchical verilation
  pe_req_t  pe_req;
  pe_resp_t pe_resp;
  assign pe_req    = pe_req_i;
  assign pe_resp_o = pe_resp;

  lane_sequencer #(
    .NrLanes              (NrLanes              ),
    .VLEN                 (VLEN                 ),
    .pe_req_t             (pe_req_t             ),
    .pe_resp_t            (pe_resp_t            ),
    .operand_request_cmd_t(operand_request_cmd_t),
    .vfu_operation_t      (vfu_operation_t      )
  ) i_lane_sequencer (
    .clk_i                  (clk_i                ),
    .rst_ni                 (rst_ni               ),
    .lane_id_i              (lane_id_i            ),
    // Interface with the main sequencer
    .pe_req_i               (pe_req               ),
    .pe_req_valid_i         (pe_req_valid_i       ),
    .pe_vinsn_running_i     (pe_vinsn_running_i   ),
    .pe_req_ready_o         (pe_req_ready_o       ),
    .pe_resp_o              (pe_resp              ),
    // Support for store exception flush
    .lsu_ex_flush_i         (lsu_ex_flush_i       ),
    .lsu_ex_flush_o         (lsu_ex_flush_op_req_d),
    // Interface with the operand requesters
    .operand_request_o      (operand_request      ),
    .operand_request_valid_o(operand_request_valid),
    .operand_request_ready_i(operand_request_ready),
    .alu_vinsn_done_o       (alu_vinsn_done_o     ),
    .mfpu_vinsn_done_o      (mfpu_vinsn_done_o    ),
    // Interface with the Operand Queue
    .mask_b_cmd_pop_i       (mask_b_cmd_pop_q     ),
    // Interface with the VFUs
    .vfu_operation_o        (vfu_operation        ),
    .vfu_operation_valid_o  (vfu_operation_valid  ),
    .alu_ready_i            (alu_ready            ),
    .alu_vinsn_done_i       (alu_vinsn_done       ),
    .mfpu_ready_i           (mfpu_ready           ),
    .mfpu_vinsn_done_i      (mfpu_vinsn_done      ),
    // From the MASKU - for VRGATHER/VCOMPRESS
    .masku_vrgat_req_valid_i(masku_vrgat_req_valid_i ),
    .masku_vrgat_req_ready_o(masku_vrgat_req_ready_o ),
    .masku_vrgat_req_i      (masku_vrgat_req_i       )
  );

  /////////////////////////
  //  Operand Requester  //
  /////////////////////////

  // Interface with the VRF
  logic               [NrVRFBanksPerLane-1:0] vrf_req;
  vaddr_t             [NrVRFBanksPerLane-1:0] vrf_addr;
  logic               [NrVRFBanksPerLane-1:0] vrf_wen;
  elen_t              [NrVRFBanksPerLane-1:0] vrf_wdata;
  strb_t              [NrVRFBanksPerLane-1:0] vrf_be;
  opqueue_e           [NrVRFBanksPerLane-1:0] vrf_tgt_opqueue;
  // Interface with the operand queues
  logic               [NrOperandQueues-1:0]   operand_queue_ready;
  logic               [NrOperandQueues-1:0]   operand_issued;
  localparam int unsigned SourceSnapshotWords = 8*VLEN/(NrLanes*DataWidth);
  localparam int unsigned SourceSnapshotIdxWidth = $clog2(SourceSnapshotWords);
  logic               [NrOperandQueues-1:0]   source_snapshot_replay_valid;
  logic [NrOperandQueues-1:0][SourceSnapshotIdxWidth-1:0]
                                                 source_snapshot_replay_index;
  operand_queue_cmd_t [NrOperandQueues-1:0]   operand_queue_cmd;
  logic               [NrOperandQueues-1:0]   operand_queue_cmd_valid;
  // Interface with the VFUs
  // ALU
  logic                                       alu_result_req;
  vid_t                                       alu_result_id;
  vaddr_t                                     alu_result_addr;
  elen_t                                      alu_result_wdata;
  strb_t                                      alu_result_be;
  logic                                       alu_result_gnt;
  // Multiplier/FPU
  logic                                       mfpu_result_req;
  vid_t                                       mfpu_result_id;
  vaddr_t                                     mfpu_result_addr;
  elen_t                                      mfpu_result_wdata;
  strb_t                                      mfpu_result_be;
  logic                                       mfpu_result_gnt;
  // To the slide unit (reductions)
  logic                                       sldu_result_gnt_opqueues;
  // Support for store exception flush
  logic                                       lsu_ex_flush_op_queues_d, lsu_ex_flush_op_queues_q;
  `FF(lsu_ex_flush_op_queues_q, lsu_ex_flush_op_queues_d, 1'b0, clk_i, rst_ni);

  operand_requester #(
    .NrLanes              (NrLanes              ),
    .VLEN                 (VLEN                 ),
    .NrBanks              (NrVRFBanksPerLane    ),
    .vaddr_t              (vaddr_t              ),
    .operand_request_cmd_t(operand_request_cmd_t),
    .operand_queue_cmd_t  (operand_queue_cmd_t  )
  ) i_operand_requester (
    .clk_i                    (clk_i                   ),
    .rst_ni                   (rst_ni                  ),
    // Interface with the main sequencer
    .global_hazard_table_i    (global_hazard_table_i   ),
    // Interface with the lane sequencer
    .operand_request_i        (operand_request         ),
    .operand_request_valid_i  (operand_request_valid   ),
    .operand_request_ready_o  (operand_request_ready   ),
    // Support for store exception flush
    .lsu_ex_flush_i           (lsu_ex_flush_op_req_q   ),
    .lsu_ex_flush_o           (lsu_ex_flush_op_queues_d),
    // Interface with the VRF
    .vrf_req_o                (vrf_req                 ),
    .vrf_addr_o               (vrf_addr                ),
    .vrf_wen_o                (vrf_wen                 ),
    .vrf_wdata_o              (vrf_wdata               ),
    .vrf_be_o                 (vrf_be                  ),
    .vrf_tgt_opqueue_o        (vrf_tgt_opqueue         ),
    // Interface with the operand queues
    .operand_issued_o         (operand_issued          ),
    .source_snapshot_replay_valid_o(source_snapshot_replay_valid),
    .source_snapshot_replay_index_o(source_snapshot_replay_index),
    .operand_queue_ready_i    (operand_queue_ready     ),
    .operand_queue_cmd_o      (operand_queue_cmd       ),
    .operand_queue_cmd_valid_o(operand_queue_cmd_valid ),
    // Interface with the VFUs
    // ALU
    .alu_result_req_i         (alu_result_req          ),
    .alu_result_id_i          (alu_result_id           ),
    .alu_result_addr_i        (alu_result_addr         ),
    .alu_result_wdata_i       (alu_result_wdata        ),
    .alu_result_be_i          (alu_result_be           ),
    .alu_result_gnt_o         (alu_result_gnt          ),
    // MFPU
    .mfpu_result_req_i        (mfpu_result_req         ),
    .mfpu_result_id_i         (mfpu_result_id          ),
    .mfpu_result_addr_i       (mfpu_result_addr        ),
    .mfpu_result_wdata_i      (mfpu_result_wdata       ),
    .mfpu_result_be_i         (mfpu_result_be          ),
    .mfpu_result_gnt_o        (mfpu_result_gnt         ),
    // Mask Unit
    .masku_result_req_i       (masku_result_req_i      ),
    .masku_result_id_i        (masku_result_id_i       ),
    .masku_result_addr_i      (masku_result_addr_i     ),
    .masku_result_wdata_i     (masku_result_wdata_i    ),
    .masku_result_be_i        (masku_result_be_i       ),
    .masku_result_gnt_o       (masku_result_gnt_o      ),
    .masku_result_final_gnt_o (masku_result_final_gnt_o),
    // Slide Unit
    .sldu_result_req_i        (sldu_result_req_i       ),
    .sldu_result_id_i         (sldu_result_id_i        ),
    .sldu_result_addr_i       (sldu_result_addr_i      ),
    .sldu_result_wdata_i      (sldu_result_wdata_i     ),
    .sldu_result_be_i         (sldu_result_be_i        ),
    .sldu_result_gnt_o        (sldu_result_gnt_opqueues),
    .sldu_result_final_gnt_o  (sldu_result_final_gnt_o ),
    // Load Unit
    .ldu_result_req_i         (ldu_result_req_i        ),
    .ldu_result_id_i          (ldu_result_id_i         ),
    .ldu_result_addr_i        (ldu_result_addr_i       ),
    .ldu_result_wdata_i       (ldu_result_wdata_i      ),
    .ldu_result_be_i          (ldu_result_be_i         ),
    .ldu_result_gnt_o         (ldu_result_gnt_o        ),
    .ldu_result_final_gnt_o   (ldu_result_final_gnt_o  )
`ifdef FOR_VERIFY
    ,.verify_wb_valid_o       (verify_wb_valid_o       )
    ,.verify_wb_id_o          (verify_wb_id_o          )
    ,.verify_wb_addr_o        (verify_wb_addr_o        )
    ,.verify_wb_wdata_o       (verify_wb_wdata_o       )
    ,.verify_wb_be_o          (verify_wb_be_o          )
`endif
  );

  ////////////////////////////
  //  Vector Register File  //
  ////////////////////////////

  // Interface with the operand queues
  elen_t [NrOperandQueues-1:0] vrf_operand;
  logic  [NrOperandQueues-1:0] vrf_operand_valid;
  elen_t [NrOperandQueues-1:0] operand_queue_input;
  logic  [NrOperandQueues-1:0] operand_queue_input_valid;

  elen_t [SourceSnapshotWords-1:0] source_snapshot_q;
  logic source_snapshot_capture_q;
  logic [SourceSnapshotIdxWidth-1:0] source_snapshot_capture_index_q;
  logic [SourceSnapshotIdxWidth-1:0] source_snapshot_capture_last_q;

  vector_regfile #(
    .VRFSize(VRFSizePerLane   ),
    .NrBanks(NrVRFBanksPerLane),
    .vaddr_t(vaddr_t          )
  ) i_vrf (
    .clk_i          (clk_i            ),
    .rst_ni         (rst_ni           ),
    // Interface with the operand requester
    .req_i          (vrf_req          ),
    .addr_i         (vrf_addr         ),
    .wen_i          (vrf_wen          ),
    .wdata_i        (vrf_wdata        ),
    .be_i           (vrf_be           ),
    .tgt_opqueue_i  (vrf_tgt_opqueue  ),
    // Interface with the operand queues
    .operand_o      (vrf_operand      ),
    .operand_valid_o(vrf_operand_valid)
  );

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VMSLEU14_VRF") && lane_id_i == 1) begin
      for (int bank = 0; bank < NrVRFBanksPerLane; bank++) begin
        if (vrf_req[bank] && vrf_addr[bank] == vaddr_t'(7)) begin
          $display("[ARA_VMSLEU14_VRF_PORT] t=%0t lane=%0d bank=%0d wen=%0b addr=%0d tgt=%0d be=%02h wdata=%016h",
                   $time, lane_id_i, bank, vrf_wen[bank], vrf_addr[bank],
                   vrf_tgt_opqueue[bank], vrf_be[bank], vrf_wdata[bank]);
        end
      end
      if (vrf_operand_valid[AluB]) begin
        $display("[ARA_VMSLEU14_VRF_RETURN] t=%0t lane=%0d q=%0d data=%016h replay=%0b",
                 $time, lane_id_i, AluB, vrf_operand[AluB],
                 source_snapshot_replay_valid[AluB]);
      end
    end
  end
`endif

  always_comb begin
    operand_queue_input = vrf_operand;
    operand_queue_input_valid = vrf_operand_valid;
    for (int q = 0; q < NrOperandQueues; q++) begin
      if (source_snapshot_replay_valid[q]) begin
        operand_queue_input[q] = source_snapshot_q[source_snapshot_replay_index[q]];
        operand_queue_input_valid[q] = 1'b1;
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      source_snapshot_q <= '0;
      source_snapshot_capture_q <= 1'b0;
      source_snapshot_capture_index_q <= '0;
      source_snapshot_capture_last_q <= '0;
    end else begin
      if (operand_request_valid[SlideAddrGenA] &&
          operand_request_ready[SlideAddrGenA] &&
          operand_request[SlideAddrGenA].source_snapshot_capture) begin
        automatic int unsigned snapshot_bytes;
        automatic int unsigned snapshot_words;
        snapshot_bytes = unsigned'(operand_request[SlideAddrGenA].vl) <<
                         unsigned'(operand_request[SlideAddrGenA].eew);
        // operand_request.vl is already lane-local.  Convert its byte count
        // directly to lane words; dividing by NrLanes again truncates the
        // captured source and makes the replay read uninitialized entries.
        snapshot_words = (snapshot_bytes + DataWidth/8 - 1) / (DataWidth/8);
`ifdef FOR_VERIFY
        assert (snapshot_words <= SourceSnapshotWords)
          else $error("source snapshot requires %0d words, capacity is %0d",
                      snapshot_words, SourceSnapshotWords);
`endif
        source_snapshot_capture_q <= snapshot_words != 0;
        source_snapshot_capture_index_q <= '0;
        source_snapshot_capture_last_q <=
            SourceSnapshotIdxWidth'(snapshot_words == 0 ? 0 : snapshot_words - 1);
      end

      if (source_snapshot_capture_q && vrf_operand_valid[SlideAddrGenA]) begin
        source_snapshot_q[source_snapshot_capture_index_q] <=
            vrf_operand[SlideAddrGenA];
`ifdef FOR_VERIFY
        if ($test$plusargs("ARA_DEBUG_SOURCE_SNAPSHOT"))
          $display("[ARA_SOURCE_CAPTURE] %m t=%0t lane=%0d idx=%0d/%0d data=%016h",
                   $time, lane_id_i, source_snapshot_capture_index_q,
                   source_snapshot_capture_last_q, vrf_operand[SlideAddrGenA]);
`endif
        if (source_snapshot_capture_index_q == source_snapshot_capture_last_q)
          source_snapshot_capture_q <= 1'b0;
        else
          source_snapshot_capture_index_q <= source_snapshot_capture_index_q + 1'b1;
      end

    end
  end

`ifdef FOR_VERIFY
  logic debug_vrem_overlap_active_q;
  vid_t debug_vrem_overlap_id_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      debug_vrem_overlap_active_q <= 1'b0;
      debug_vrem_overlap_id_q <= '0;
    end else begin
      if (pe_req_valid_i && pe_req_ready_o && pe_req.op == VREMU &&
          pe_req.vd == 5'd8 && pe_req.vtype.vsew == EW8 &&
          pe_req.vtype.vlmul == LMUL_8) begin
        debug_vrem_overlap_active_q <= 1'b1;
        debug_vrem_overlap_id_q <= pe_req.id;
        if ($test$plusargs("ARA_DEBUG_VREM_OVERLAP"))
          $display("[ARA_VREM_ACCEPT] %m t=%0t lane=%0d id=%0d vd=v%0d vl=%0d",
                   $time, lane_id_i, pe_req.id, pe_req.vd, pe_req.vl);
      end
      if (debug_vrem_overlap_active_q &&
          mfpu_vinsn_done[debug_vrem_overlap_id_q])
        debug_vrem_overlap_active_q <= 1'b0;
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VREM_OVERLAP") &&
        debug_vrem_overlap_active_q) begin
      for (int bank = 0; bank < NrVRFBanksPerLane; bank++) begin
        if (vrf_req[bank] && !vrf_wen[bank] &&
            vrf_tgt_opqueue[bank] inside {MulFPUA, MulFPUB})
          $display("[ARA_VREM_VRF_READ] %m t=%0t lane=%0d bank=%0d q=%0d addr=%0d",
                   $time, lane_id_i, bank, vrf_tgt_opqueue[bank], vrf_addr[bank]);
      end
      if (vrf_operand_valid[MulFPUA])
        $display("[ARA_VREM_VRF_RETURN] %m t=%0t lane=%0d q=A data=%016h",
                 $time, lane_id_i, vrf_operand[MulFPUA]);
      if (vrf_operand_valid[MulFPUB])
        $display("[ARA_VREM_VRF_RETURN] %m t=%0t lane=%0d q=B data=%016h",
                 $time, lane_id_i, vrf_operand[MulFPUB]);
      if (mfpu_result_req && mfpu_result_id == debug_vrem_overlap_id_q)
        $display("[ARA_VREM_WRITE] %m t=%0t lane=%0d gnt=%0b addr=%0d be=%02h data=%016h",
                 $time, lane_id_i, mfpu_result_gnt, mfpu_result_addr,
                 mfpu_result_be, mfpu_result_wdata);
    end
    if (rst_ni && $test$plusargs("ARA_DEBUG_SOURCE_SNAPSHOT")) begin
      for (int q = 0; q < NrOperandQueues; q++) begin
        if (source_snapshot_replay_valid[q])
          $display("[ARA_SOURCE_REPLAY] %m t=%0t lane=%0d q=%0d idx=%0d data=%016h",
                   $time, lane_id_i, q, source_snapshot_replay_index[q],
                   source_snapshot_q[source_snapshot_replay_index[q]]);
      end
    end
  end
`endif

  //////////////////////
  //  Operand queues  //
  //////////////////////

  // Interface with the VFUs
  // ALU
  elen_t [1:0] alu_operand;
  logic  [1:0] alu_operand_valid;
  logic  [1:0] alu_operand_ready;
  // Multiplier/FPU
  elen_t [2:0] mfpu_operand;
  logic  [2:0] mfpu_operand_valid;
  logic  [2:0] mfpu_operand_ready;

  elen_t sldu_addrgen_operand_opqueues;
  target_fu_e sldu_addrgen_operand_target_fu;
  logic sldu_addrgen_cmd_pop;

  logic sldu_operand_opqueues_ready, sldu_addrgen_opqueue_ready;
  logic sldu_addrgen_operand_opqueues_valid;

  operand_queues_stage #(
    .NrLanes            (NrLanes            ),
    .VLEN               (VLEN               ),
    .FPUSupport         (FPUSupport         ),
    .operand_queue_cmd_t(operand_queue_cmd_t)
  ) i_operand_queues (
    .clk_i                            (clk_i                              ),
    .rst_ni                           (rst_ni                             ),
    .lane_id_i                        (lane_id_i                          ),
    // Interface with the Vector Register File
    .operand_i                        (operand_queue_input                 ),
    .operand_valid_i                  (operand_queue_input_valid           ),
    // Interface with the operand requester
    .operand_issued_i                 (operand_issued                     ),
    .operand_queue_ready_o            (operand_queue_ready                ),
    .operand_queue_cmd_i              (operand_queue_cmd                  ),
    .operand_queue_cmd_valid_i        (operand_queue_cmd_valid            ),
    // Support for store exception flush
    .lsu_ex_flush_i                   (lsu_ex_flush_op_queues_q           ),
    .lsu_ex_flush_o                   (lsu_ex_flush_o                     ),
    // Interface with the Lane Sequencer
    .mask_b_cmd_pop_o                 (mask_b_cmd_pop_d                   ),
    // Interface with the Lane
    .sldu_addrgen_cmd_pop_o           (sldu_addrgen_cmd_pop               ),
    // Interface with the VFUs
    // ALU
    .alu_operand_o                    (alu_operand                        ),
    .alu_operand_valid_o              (alu_operand_valid                  ),
    .alu_operand_ready_i              (alu_operand_ready                  ),
    // Multiplier/FPU
    .mfpu_operand_o                   (mfpu_operand                       ),
    .mfpu_operand_valid_o             (mfpu_operand_valid                 ),
    .mfpu_operand_ready_i             (mfpu_operand_ready                 ),
    // Store Unit
    .stu_operand_o                    (stu_operand_o                      ),
    .stu_operand_valid_o              (stu_operand_valid_o                ),
    .stu_operand_ready_i              (stu_operand_ready_i                ),
    // Address Generation Unit
    .sldu_addrgen_operand_o           (sldu_addrgen_operand_opqueues      ),
    .sldu_addrgen_operand_target_fu_o (sldu_addrgen_operand_target_fu     ),
    .sldu_addrgen_operand_valid_o     (sldu_addrgen_operand_opqueues_valid),
    .sldu_addrgen_operand_ready_i     (sldu_addrgen_opqueue_ready         ),
    // Mask Unit
    .mask_operand_o                   (mask_operand_o[1:0]                ),
    .mask_operand_valid_o             (mask_operand_valid_o[1:0]          ),
    .mask_operand_ready_i             (mask_operand_ready_i[1:0]          )
  );

  ///////////////////////////////
  //  Vector Functional Units  //
  ///////////////////////////////

  // Reductions
  logic sldu_alu_gnt, sldu_mfpu_gnt;
  logic sldu_alu_valid, sldu_mfpu_valid;
  logic sldu_alu_req_valid_o, sldu_mfpu_req_valid_o;
  logic sldu_alu_ready, sldu_mfpu_ready;
  logic alu_red_complete, fpu_red_complete;

  vector_fus_stage #(
    .NrLanes        (NrLanes        ),
    .VLEN           (VLEN           ),
    .CVA6Cfg        (CVA6Cfg        ),
    .FPUSupport     (FPUSupport     ),
    .FPExtSupport   (FPExtSupport   ),
    .FixPtSupport   (FixPtSupport   ),
    .vaddr_t        (vaddr_t        ),
    .vfu_operation_t(vfu_operation_t)
  ) i_vfus (
    .clk_i                (clk_i                                  ),
    .rst_ni               (rst_ni                                 ),
    .lane_id_i            (lane_id_i                              ),
    // Interface with Dispatcher
    .vxsat_flag_o         (vxsat_flag_o                           ),
    .alu_vxrm_i           (alu_vxrm_i                             ),
    // Interface with CVA6
    .fflags_ex_o          (fflags_ex_o                            ),
    .fflags_ex_valid_o    (fflags_ex_valid_o                      ),
    // Interface with the lane sequencer
    .vfu_operation_i      (vfu_operation                          ),
    .vfu_operation_valid_i(vfu_operation_valid                    ),
    .alu_ready_o          (alu_ready                              ),
    .alu_vinsn_done_o     (alu_vinsn_done                         ),
    .mfpu_ready_o         (mfpu_ready                             ),
    .mfpu_vinsn_done_o    (mfpu_vinsn_done                        ),
    // Interface with the SLDU/ADDRGEN arbiter
    .alu_red_complete_o   (alu_red_complete                       ),
    .fpu_red_complete_o   (fpu_red_complete                       ),
    .mfpu_reduction_any_active_o(mfpu_reduction_any_active_o      ),
    .mfpu_reduction_global_any_active_i(mfpu_reduction_global_any_active_i),
    // Interface with the operand requester
    // ALU
    .alu_result_req_o     (alu_result_req                         ),
    .alu_result_id_o      (alu_result_id                          ),
    .alu_result_addr_o    (alu_result_addr                        ),
    .alu_result_wdata_o   (alu_result_wdata                       ),
    .alu_result_be_o      (alu_result_be                          ),
    .alu_result_gnt_i     (alu_result_gnt                         ),
    // MFPU
    .mfpu_result_req_o    (mfpu_result_req                        ),
    .mfpu_result_id_o     (mfpu_result_id                         ),
    .mfpu_result_addr_o   (mfpu_result_addr                       ),
    .mfpu_result_wdata_o  (mfpu_result_wdata                      ),
    .mfpu_result_be_o     (mfpu_result_be                         ),
    .mfpu_result_gnt_i    (mfpu_result_gnt                        ),
    // Interface with the Slide Unit
    .sldu_alu_req_valid_o (sldu_alu_req_valid_o                   ),
    .sldu_alu_valid_i     (sldu_alu_valid                         ),
    .sldu_alu_ready_o     (sldu_alu_ready                         ),
    .sldu_alu_gnt_i       (sldu_alu_gnt                           ),
    .sldu_mfpu_req_valid_o(sldu_mfpu_req_valid_o                  ),
    .sldu_mfpu_valid_i    (sldu_mfpu_valid                        ),
    .sldu_mfpu_ready_o    (sldu_mfpu_ready                        ),
    .sldu_mfpu_gnt_i      (sldu_mfpu_gnt                          ),
    .sldu_operand_i       (sldu_result_wdata_i                    ),
    // Interface with the operand queues
    // ALU
    .alu_operand_i        (alu_operand                            ),
    .alu_operand_valid_i  (alu_operand_valid                      ),
    .alu_operand_ready_o  (alu_operand_ready                      ),
    // Multiplier/FPU
    .mfpu_operand_i       (mfpu_operand                           ),
    .mfpu_operand_valid_i (mfpu_operand_valid                     ),
    .mfpu_operand_ready_o (mfpu_operand_ready                     ),
    // Interface with the Mask unit
    .mask_operand_o       (mask_operand_o[2 +: NrMaskFUnits]      ),
    .mask_operand_valid_o (mask_operand_valid_o[2 +: NrMaskFUnits]),
    .mask_operand_ready_i (mask_operand_ready_i[2 +: NrMaskFUnits]),
    .alu_mask_i           (alu_mask                               ),
    .alu_mask_valid_i     (alu_mask_valid                         ),
    .alu_mask_ready_o     (alu_mask_ready                         ),
    .mfpu_mask_i          (mfpu_mask                              ),
    .mfpu_mask_valid_i    (mfpu_mask_valid                        ),
    .mfpu_mask_ready_o    (mfpu_mask_ready                        )
  );

  /******************************
   *  SLDU/ADDRGEN arbitration  *
   *****************************/

  // The SLDU and the ADDRGEN share the same data bus from the lanes.
  // This bus is connected to ALU, FPU, and one operand queue.
  // Arbitration is necessary due to the serialization on the unique databus.
  // The easiest form of arbitration is to follow instruction order.
  typedef enum logic [1:0] {
    SLDU_SEL    = 2'd0,
    ADDRGEN_SEL = 2'd1,
    ALU_RED_SEL = 2'd2,
    FPU_RED_SEL = 2'd3
  } sldu_addrgen_sel_e;
  typedef enum logic [1:0] {
    MUX_OPQUEUE_SEL = 2'd0,
    MUX_ALU_SEL     = 2'd1,
    MUX_FPU_SEL     = 2'd2
  } sldu_addrgen_mux_sel_e;
  sldu_addrgen_sel_e sldu_addrgen_sel_d, sldu_addrgen_sel_q;
  sldu_addrgen_mux_sel_e sldu_addrgen_mux_sel;
  logic sldu_addrgen_arbiter_push, sldu_addrgen_arbiter_pop, sldu_addrgen_arbiter_empty;

  ara_op_e vfu_operation_op_q;
  logic vfu_operation_valid_q;
  logic vfu_operation_skip_sldu_operand_q;
  logic sldu_operand_opqueues_valid;

  assign sldu_operand_reduction_o =
      sldu_addrgen_sel_q inside {ALU_RED_SEL, FPU_RED_SEL};

`ifdef FOR_VERIFY
  logic debug_vzext_reshuffle_lane_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      debug_vzext_reshuffle_lane_q <= 1'b0;
    end else if ($test$plusargs("ARA_DEBUG_VZEXT_RESHUFFLE")) begin
      if (vfu_operation_valid && vfu_operation.id == 3 &&
          vfu_operation.op == VSLIDEDOWN && vfu_operation.vl == 16 &&
          vfu_operation.vtype.vsew == EW16) begin
        debug_vzext_reshuffle_lane_q <= 1'b1;
      end else if (debug_vzext_reshuffle_lane_q && sldu_addrgen_cmd_pop) begin
        debug_vzext_reshuffle_lane_q <= 1'b0;
      end
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && debug_vzext_reshuffle_lane_q) begin
      $display("[ARA_VZEXT_RESHUFFLE_QUEUE] %m t=%0t lane=%0d issued=%0b vrf_valid=%0b oq_valid=%0b oq_ready=%0b cmd_pop=%0b",
               $time, lane_id_i, operand_issued[SlideAddrGenA],
               operand_queue_input_valid[SlideAddrGenA],
               sldu_addrgen_operand_opqueues_valid,
               sldu_addrgen_opqueue_ready, sldu_addrgen_cmd_pop);
    end
  end
`endif

  // Selector FIFO to enforce instruction order
  fifo_v3 #(
    .DEPTH     (NrVInsn),
    .dtype     (sldu_addrgen_sel_e)
  ) i_sldu_addrgen_arbiter (
    .clk_i,
    .rst_ni,
    .flush_i   (lsu_ex_flush_op_queues_q),
    .testmode_i(1'b0),
    .full_o    (/**/),
    .empty_o   (sldu_addrgen_arbiter_empty),
    .usage_o   (/**/),
    .data_i    (sldu_addrgen_sel_d),
    .push_i    (sldu_addrgen_arbiter_push),
    .data_o    (sldu_addrgen_sel_q),
    .pop_i     (sldu_addrgen_arbiter_pop)
  );

  // Break timing path
  `FF(vfu_operation_valid_q, vfu_operation_valid, 1'b0, clk_i, rst_ni);
  `FF(vfu_operation_op_q, vfu_operation.op, VADD, clk_i, rst_ni);
  `FF(vfu_operation_skip_sldu_operand_q, vfu_operation.skip_sldu_operand,
      1'b0, clk_i, rst_ni);

  always_comb begin
    sldu_addrgen_sel_d = SLDU_SEL;
    sldu_addrgen_arbiter_push = 1'b0;
    sldu_addrgen_arbiter_pop  = 1'b0;
    sldu_addrgen_mux_sel = MUX_OPQUEUE_SEL;

    // Push a new entry when a new instruction arrives
    if (vfu_operation_valid_q) begin
      case (vfu_operation_op_q) inside
        VSLIDEUP, VSLIDEDOWN: begin
          sldu_addrgen_sel_d = SLDU_SEL;
          sldu_addrgen_arbiter_push = !vfu_operation_skip_sldu_operand_q;
        end
        VLXE, VSXE: begin
          sldu_addrgen_sel_d = ADDRGEN_SEL;
          sldu_addrgen_arbiter_push = 1'b1;
        end
        [VREDSUM:VWREDSUM]: begin
          sldu_addrgen_sel_d = ALU_RED_SEL;
          sldu_addrgen_arbiter_push = 1'b1;
        end
        [VFREDUSUM:VFWREDOSUM]: begin
          sldu_addrgen_sel_d = FPU_RED_SEL;
          sldu_addrgen_arbiter_push = !vfu_operation_skip_sldu_operand_q;
        end
        default:;
      endcase
    end

    // Pop an entry when the instruction completes
    if (!sldu_addrgen_arbiter_empty) begin
      unique case (sldu_addrgen_sel_q)
        SLDU_SEL: begin
          sldu_addrgen_arbiter_pop = sldu_addrgen_cmd_pop;
        end
        ADDRGEN_SEL: begin
          sldu_addrgen_arbiter_pop = sldu_addrgen_cmd_pop;
        end
        ALU_RED_SEL: begin
          sldu_addrgen_arbiter_pop = alu_red_complete;
        end
        FPU_RED_SEL: begin
          sldu_addrgen_arbiter_pop = fpu_red_complete;
        end
        default:;
      endcase
    end

    // MUX the alu, fpu, and opqueue stream
    unique case (sldu_addrgen_sel_q)
      ALU_RED_SEL: sldu_addrgen_mux_sel = MUX_ALU_SEL;
      FPU_RED_SEL: sldu_addrgen_mux_sel = MUX_FPU_SEL;
      default: sldu_addrgen_mux_sel = MUX_OPQUEUE_SEL;
    endcase
  end

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_REDUCTION") &&
        (sldu_addrgen_arbiter_push || sldu_addrgen_arbiter_pop ||
         sldu_addrgen_operand_opqueues_valid || sldu_alu_req_valid_o ||
         sldu_mfpu_req_valid_o || sldu_mfpu_valid ||
         alu_red_complete || fpu_red_complete)) begin
      $display("[ARA_LANE_RED_ARB] t=%0t lane=%0d sel=%0d empty=%0b push=%0b push_sel=%0d pop=%0b op_valid=%0b op=%0d oq_v=%0b oq_target=%0d oq_ready=%0b ag_v=%0b ag_r=%0b alu_tx=%0b/%0b fpu_tx=%0b/%0b fpu_rx=%0b/%0b alu_done=%0b fpu_done=%0b sldu_ready=%0b",
               $time, lane_id_i, sldu_addrgen_sel_q,
               sldu_addrgen_arbiter_empty, sldu_addrgen_arbiter_push,
               sldu_addrgen_sel_d, sldu_addrgen_arbiter_pop,
               vfu_operation_valid_q, vfu_operation_op_q,
               sldu_addrgen_operand_opqueues_valid,
               sldu_addrgen_operand_target_fu,
               sldu_addrgen_opqueue_ready,
               addrgen_operand_valid_o, addrgen_operand_ready_i,
               sldu_alu_req_valid_o, sldu_alu_gnt,
               sldu_mfpu_req_valid_o, sldu_mfpu_gnt,
               sldu_mfpu_valid, sldu_mfpu_ready,
               alu_red_complete, fpu_red_complete, sldu_operand_ready_i);
    end
  end
`endif

  // Stream MUX to select the transmitter
  stream_mux #(
    .DATA_T(elen_t),
    .N_INP (3) // ALU, FPU, OpQueue
  ) i_sldu_addrgen_stream_mux (
    .inp_data_i ({mfpu_result_wdata, alu_result_wdata, sldu_addrgen_operand_opqueues}),
    .inp_valid_i({sldu_mfpu_req_valid_o, sldu_alu_req_valid_o, sldu_operand_opqueues_valid}),
    .inp_ready_o({sldu_mfpu_gnt, sldu_alu_gnt, sldu_operand_opqueues_ready}),
    .inp_sel_i  (sldu_addrgen_mux_sel),
    .oup_data_o (sldu_addrgen_operand_o),
    .oup_valid_o(sldu_operand_valid_o),
    .oup_ready_i(sldu_operand_ready_i)
  );

  // OpQueue-valid DEMUX
  // Ready can come from either addrgen or sldu
  always_comb begin
    sldu_operand_opqueues_valid = 1'b0;
    addrgen_operand_valid_o = 1'b0;
    if (sldu_addrgen_sel_q == SLDU_SEL)
      sldu_operand_opqueues_valid = sldu_addrgen_operand_opqueues_valid;
    if (sldu_addrgen_sel_q == ADDRGEN_SEL)
      addrgen_operand_valid_o = sldu_addrgen_operand_opqueues_valid;
  end

  // OpQueue-ready MUX
  // Ready can come from either addrgen or sldu
  always_comb begin
    sldu_addrgen_opqueue_ready = 1'b0;
    if (sldu_addrgen_sel_q == SLDU_SEL)
      sldu_addrgen_opqueue_ready = sldu_operand_ready_i;
    if (sldu_addrgen_sel_q == ADDRGEN_SEL)
      sldu_addrgen_opqueue_ready = addrgen_operand_ready_i;
  end

  // During a reduction, the slide unit is directly connected to the functional units.
  // The selectors are controlled by the slide unit itself, which must know what it will receive next.
  assign sldu_alu_valid    = sldu_red_valid_i & (sldu_addrgen_sel_q == ALU_RED_SEL);
  assign sldu_mfpu_valid   = sldu_red_valid_i & (sldu_addrgen_sel_q == FPU_RED_SEL);
  assign sldu_result_gnt_o = sldu_addrgen_sel_q == SLDU_SEL ? sldu_result_gnt_opqueues :
                            (sldu_addrgen_sel_q == ALU_RED_SEL ? sldu_alu_ready : sldu_mfpu_ready);

  //////////////////
  //  Assertions  //
  //////////////////

  if (NrLanes == 0)
    $error("[lane] Ara needs to have at least one lane.");

endmodule : lane
