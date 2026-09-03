// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

`include "axi/typedef.svh"
`include "ara/intf_typedef.svh"

package akv_engine_synth_types_pkg;
  localparam int unsigned AxiDataWidth = 128;
  localparam int unsigned AxiAddrWidth = 64;
  localparam int unsigned AxiIdWidth = 4;
  localparam int unsigned AxiUserWidth = 1;
  localparam int unsigned NrLanes = 4;
  localparam int unsigned VLEN = 1024;
  localparam int unsigned VAddrWidth = 64;
  localparam int unsigned PAddrWidth = 56;
  localparam int unsigned VRFBytesPerLane = (VLEN / 8 / NrLanes) * 32;

  typedef logic [AxiAddrWidth-1:0] axi_addr_t;
  typedef logic [AxiDataWidth-1:0] axi_data_t;
  typedef logic [AxiIdWidth-1:0] axi_id_t;
  typedef logic [AxiUserWidth-1:0] axi_user_t;
  typedef logic [$clog2(VRFBytesPerLane)-1:0] vaddr_t;

  `AXI_TYPEDEF_AR_CHAN_T(axi_ar_t, axi_addr_t, axi_id_t, axi_user_t)
  `AXI_TYPEDEF_R_CHAN_T(axi_r_t, axi_data_t, axi_id_t, axi_user_t)

  localparam config_pkg::cva6_cfg_t CVA6Cfg =
      build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  `CVA6_TYPEDEF_EXCEPTION(exception_t, CVA6Cfg)
endpackage

// Measurement-only wrapper. Every functional input and output remains visible
// at the top level so synthesis cannot collapse the engine around tied inputs.
module akv_engine_synth_wrapper import akv_engine_synth_types_pkg::*; (
    input  logic                         clk_i,
    input  logic                         rst_ni,

    input  logic                         command_valid_i,
    output logic                         command_ready_o,
    input  akv_pkg::akv_command_e        command_i,
    input  ara_pkg::vid_t                command_id_i,
    input  logic [4:0]                   command_vd_i,
    input  logic [15:0]                  command_head_dim_i,
    input  logic [VAddrWidth-1:0]        command_descriptor_address_i,
    input  logic [VAddrWidth-1:0]        command_tile_start_i,
    input  logic [VAddrWidth-1:0]        command_selector_i,
    input  logic [2:0]                   command_column_count_i,
    input  axi_pkg::cache_t              command_cache_i,
    input  axi_pkg::prot_t               command_prot_i,

    output logic                         command_early_ack_o,
    output logic                         success_valid_o,
    output logic                         fault_valid_o,
    input  logic                         terminal_ready_i,
    output logic                         fault_is_validation_o,
    output akv_pkg::akv_validation_error_e validation_error_o,
    output qbs_pkg::qbs_read_fault_e     read_fault_kind_o,
    output logic [VAddrWidth-1:0]        fault_vaddr_o,
    output exception_t                   fault_mmu_exception_o,
    output logic                         context_ready_o,

    input  logic                         core_st_pending_i,
    input  logic                         en_ld_st_translation_i,
    output logic                         mmu_req_o,
    output logic [VAddrWidth-1:0]        mmu_vaddr_o,
    output logic                         mmu_is_store_o,
    input  logic                         mmu_valid_i,
    input  logic [PAddrWidth-1:0]        mmu_paddr_i,
    input  logic                         mmu_exception_valid_i,
    input  exception_t                   mmu_exception_i,

    output logic                         physical_check_valid_o,
    output logic [AxiAddrWidth-1:0]      physical_check_addr_o,
    output logic [12:0]                  physical_check_bytes_o,
    input  logic                         physical_range_allowed_i,

    output axi_ar_t                      axi_ar_o,
    output logic                         axi_ar_valid_o,
    input  logic                         axi_ar_ready_i,
    input  axi_r_t                       axi_r_i,
    input  logic                         axi_r_valid_i,
    output logic                         axi_r_ready_o,

    output logic [NrLanes-1:0]          ldu_result_req_o,
    output ara_pkg::vid_t [NrLanes-1:0] ldu_result_id_o,
    output vaddr_t [NrLanes-1:0]        ldu_result_addr_o,
    output logic [63:0]                 ldu_result_wdata_o [NrLanes],
    output logic [7:0]                  ldu_result_be_o [NrLanes],
    input  logic [NrLanes-1:0]          ldu_result_gnt_i,
    input  logic [NrLanes-1:0]          ldu_result_final_gnt_i,

    output logic                         busy_o,
    output logic [31:0]                  command_cycles_o,
    output logic [31:0]                  full_count_o,
    output logic [31:0]                  refill_count_o,
    output logic [31:0]                  load_count_o,
    output logic [31:0]                  release_count_o,
    output logic [31:0]                  v2_full_count_o,
    output logic [31:0]                  v2_refill_count_o,
    output logic [31:0]                  v2_row_load_count_o,
    output logic [31:0]                  v2_column_load_count_o,
    output logic [31:0]                  v2_column_panel_count_o,
    output logic [31:0]                  v2_logical_column_count_o,
    output logic [31:0]                  v2_k_view_bank_cycles_o,
    output logic [31:0]                  v2_bank_conflict_cycles_o,
    output logic [31:0]                  v2_rejected_count_o,
    output logic [31:0]                  q_external_bytes_o,
    output logic [31:0]                  kv_external_bytes_o,
    output logic [31:0]                  replay_bytes_o,
    output logic [31:0]                  replay_backpressure_cycles_o,
    output logic [31:0]                  read_range_count_o,
    output logic [31:0]                  read_translation_count_o,
    output logic [31:0]                  read_ar_count_o,
    output logic [31:0]                  read_beat_count_o,
    output logic [31:0]                  read_payload_bytes_o,
    output logic [31:0]                  read_store_wait_cycles_o,
    output logic [31:0]                  read_backpressure_cycles_o,
    output logic [31:0]                  read_outstanding_occupancy_sum_o,
    output logic [1:0]                   read_outstanding_max_o,
    output logic [31:0]                  read_outstanding_full_cycles_o
  );

  akv_engine #(
    .AxiDataWidth (AxiDataWidth),
    .AxiAddrWidth (AxiAddrWidth),
    .VAddrWidth   (VAddrWidth),
    .PAddrWidth   (PAddrWidth),
    .NrLanes      (NrLanes),
    .VLEN         (VLEN),
    .vid_t        (ara_pkg::vid_t),
    .vaddr_t      (vaddr_t),
    .axi_ar_t     (axi_ar_t),
    .axi_r_t      (axi_r_t),
    .exception_t  (exception_t)
  ) i_akv_engine (.*);
endmodule
