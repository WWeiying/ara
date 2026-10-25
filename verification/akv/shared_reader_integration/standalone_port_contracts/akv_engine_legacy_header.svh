// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Bounded Attention/KV residency and replay engine. The engine intentionally
// performs no vector arithmetic: fills use the existing translated VLSU read
// path and local loads return captured F16 payload through the normal LDU
// result interface. Existing sequencer hazards and lane completion therefore
// remain authoritative for every architectural VRF write.
module akv_engine import ara_pkg::*; import rvv_pkg::*; import qbs_pkg::*;
  import akv_pkg::*; #(
    parameter int unsigned AxiDataWidth = 128,
    parameter int unsigned AxiAddrWidth = 64,
    parameter int unsigned VAddrWidth = 64,
    parameter int unsigned PAddrWidth = 56,
    parameter int unsigned NrLanes = 4,
    parameter int unsigned VLEN = 1024,
    parameter type         vid_t = logic,
    parameter type         vaddr_t = logic,
    parameter type         axi_ar_t = logic,
    parameter type         axi_r_t = logic,
    parameter type         exception_t = logic
  ) (
    input  logic                         clk_i,
    input  logic                         rst_ni,

    input  logic                         command_valid_i,
    output logic                         command_ready_o,
    input  akv_command_e                 command_i,
    input  vid_t                         command_id_i,
    input  logic [4:0]                   command_vd_i,
    input  logic [15:0]                  command_head_dim_i,
    input  logic [VAddrWidth-1:0]        command_descriptor_address_i,
    input  logic [VAddrWidth-1:0]        command_tile_start_i,
    input  logic [VAddrWidth-1:0]        command_selector_i,
    input  logic [2:0]                   command_column_count_i,
    input  axi_pkg::cache_t              command_cache_i,
    input  axi_pkg::prot_t               command_prot_i,

    // Pulses with acceptance of a valid local load. Fill, refill, release,
    // and invalid loads acknowledge only with their terminal response.
    output logic                         command_early_ack_o,
    output logic                         success_valid_o,
    output logic                         fault_valid_o,
    input  logic                         terminal_ready_i,
    output logic                         fault_is_validation_o,
    output akv_validation_error_e        validation_error_o,
    output qbs_read_fault_e              read_fault_kind_o,
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
    output vid_t [NrLanes-1:0]          ldu_result_id_o,
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
