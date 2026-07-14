// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// Top level testbench module.

import "DPI-C" function void read_elf (input string filename);
import "DPI-C" function byte get_section (output longint address, output longint len);
import "DPI-C" context function byte read_section(input longint address, inout byte buffer[]);
import ara_pkg::*;

`define STRINGIFY(x) `"x`"

// Architectural RVV/backend classes used by the execution performance monitor.
// Keep these classes mutually exclusive so their instruction counts can be
// added without double-counting instructions that use more than one VFU.  The
// final class is an Ara-internal micro-operation, not an architectural RVV
// instruction; keeping it separate prevents register reshuffles from polluting
// the architectural slide metrics.
localparam int unsigned NrExecClasses = 11;
typedef enum logic [3:0] {
  ExecValu,
  ExecMul,
  ExecDiv,
  ExecFp,
  ExecSlide,
  ExecMask,
  ExecLoad,
  ExecStore,
  ExecMoveToVec,
  ExecMoveFromVec,
  ExecReshuffle
} exec_class_e;
typedef logic [NrExecClasses-1:0] exec_class_mask_t;

// ara_op_e is densely encoded from VADD through VSXE.  Opcode-level counters
// retain this native encoding so a class-level anomaly can be split without
// duplicating the architectural decoder in the testbench.
localparam int unsigned NrAraOps = unsigned'(VSXE) + 1;
localparam int unsigned NrQueueOccupancyBins = MaxVInsnQueueDepth + 2;
localparam int unsigned NrAxiOutstandingBins = 9; // 0..7 and an 8+ overflow bin.
localparam int unsigned AxiLatencyFifoDepth = 16;
localparam int unsigned AxiLatencyPtrWidth = $clog2(AxiLatencyFifoDepth);
localparam int unsigned AxiOutstandingWidth = $clog2(AxiLatencyFifoDepth + 1);
localparam int unsigned NrMaskDensityBins = 6; // 0, (0,25], (25,50], (50,75], (75,100), 100%.
localparam int unsigned NrMfpuSubunits = 3;    // packed multiplier, serial divider, fpnew.
localparam int unsigned NrValuStates = 6;
localparam int unsigned NrMfpuStates = 8;
localparam int unsigned NrSlduStates = 9;
localparam int unsigned NrRedStreamClasses = 2;

typedef enum logic {
  RedStreamValu,
  RedStreamFp
} red_stream_class_e;

// Reduction-stream diagnostics are lane samples.  This is intentional: a
// context may be eligible in three lanes while a fourth lane is still blocked,
// and a wall-cycle OR would hide exactly the desynchronization that constrains
// promotion.  Candidate outcome counters form a priority partition.
typedef struct {
  logic [NrRedStreamClasses-1:0][63:0] window_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] no_candidate_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] candidate_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] eligible_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] reject_unsupported_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] reject_mask_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] reject_short_vl_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] reject_opcode_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] reject_sew_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] reject_rounding_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] start_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] active_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] background_issue_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] primary_conflict_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] complete_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] complete_wait_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] full_promotion_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] partial_promotion_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] root_nonempty_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] root_full_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] root_occupancy_lane_sum;
  logic [NrRedStreamClasses-1:0][63:0] root_push_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] root_pop_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] slack_defer_lane_sample;
  logic [NrRedStreamClasses-1:0][63:0] slack_score_lane_sum;
} red_stream_perf_t;

localparam int unsigned NrMemClasses = 2;
typedef enum logic {
  MemLoad,
  MemStore
} mem_class_e;

typedef struct {
  logic [NrExecClasses-1:0][63:0] insn_count;
  logic [NrExecClasses-1:0][63:0] issued_count;
  logic [NrExecClasses-1:0][63:0] completed_count;
  logic [NrExecClasses-1:0][63:0] requested_element_count;
  logic [NrExecClasses-1:0][63:0] nominal_element_op_count;
  logic [NrExecClasses-1:0][63:0] masked_insn_count;
  logic [NrExecClasses-1:0][63:0] reduction_insn_count;
  logic [NrExecClasses-1:0][63:0] special_insn_count;
  // Backend request shape.  Segment instructions are expanded by the
  // segment sequencer, so these are explicitly micro-operation counts.
  logic [NrExecClasses-1:0][63:0] unit_stride_uop_count;
  logic [NrExecClasses-1:0][63:0] strided_uop_count;
  logic [NrExecClasses-1:0][63:0] indexed_uop_count;
  logic [NrExecClasses-1:0][63:0] segment_uop_count;
  logic [NrExecClasses-1:0][63:0] fault_only_first_uop_count;
  logic [NrExecClasses-1:0][63:0] requested_byte_count;
  logic [NrExecClasses-1:0][3:0][63:0] sew_insn_hist;
  logic [NrExecClasses-1:0][63:0] active_cycle;
  logic [NrExecClasses-1:0][63:0] inflight_insn_cycle;
  logic [NrExecClasses-1:0][63:0] masked_active_cycle;

  logic [NrExecClasses-1:0][63:0] dispatch_wait_cycle;
  logic [NrExecClasses-1:0][3:0][63:0] dispatch_wait_hist;
  logic [NrExecClasses-1:0][63:0] execution_latency_cycle;
  logic [NrExecClasses-1:0][3:0][63:0] execution_latency_hist;
  logic [NrExecClasses-1:0][63:0] end_to_end_latency_cycle;
  logic [NrAraOps-1:0][63:0] opcode_dispatch_wait_cycle;
  logic [NrAraOps-1:0][3:0][63:0] opcode_dispatch_wait_hist;

  logic [NrExecClasses-1:0][63:0] dispatch_request_cycle;
  logic [NrExecClasses-1:0][63:0] dispatch_blocked_cycle;
  logic [NrExecClasses-1:0][63:0] fu_queue_full_cycle;
  logic [NrExecClasses-1:0][63:0] mask_queue_full_cycle;
  logic [NrExecClasses-1:0][63:0] slide_queue_full_cycle;
  logic [NrExecClasses-1:0][63:0] id_pool_full_cycle;
  logic [NrExecClasses-1:0][63:0] response_wait_cycle;
  logic [NrExecClasses-1:0][63:0] other_dispatch_blocked_cycle;
  logic [NrExecClasses-1:0][63:0] operand_request_blocked_cycle;
  logic [NrExecClasses-1:0][63:0] raw_hazard_cycle;
  logic [NrExecClasses-1:0][63:0] war_hazard_cycle;
  logic [NrExecClasses-1:0][63:0] waw_hazard_cycle;
  logic [NrExecClasses-1:0][63:0] false_hazard_cycle;
  logic [NrExecClasses-1:0][63:0] sequencer_block_cycle;
  logic [NrExecClasses-1:0][63:0] lane_desync_cycle;

  logic [NrExecClasses-1:0][63:0] issue_progress_cycle;
  logic [NrExecClasses-1:0][63:0] no_issue_progress_cycle;
  logic [NrExecClasses-1:0][63:0] operand_wait_cycle;
  logic [NrExecClasses-1:0][63:0] unit_input_backpressure_cycle;
  logic [NrExecClasses-1:0][63:0] latency_order_stall_cycle;
  logic [NrExecClasses-1:0][63:0] result_queue_full_cycle;
  logic [NrExecClasses-1:0][63:0] result_backpressure_cycle;
  logic [NrExecClasses-1:0][63:0] long_latency_busy_cycle;
  logic [NrExecClasses-1:0][63:0] reduction_cycle;
  logic [NrExecClasses-1:0][63:0] cross_lane_cycle;
  logic [NrExecClasses-1:0][63:0] special_path_cycle;
  logic [NrExecClasses-1:0][63:0] index_fifo_full_cycle;
  // Mask-unit phase residency.  These counters disambiguate missing operands
  // from the VCOMPRESS issue-end/result-drain/final-grant tail.
  logic [NrExecClasses-1:0][63:0] mask_operand_incomplete_cycle;
  logic [NrExecClasses-1:0][63:0] mask_issue_end_cycle;
  logic [NrExecClasses-1:0][63:0] mask_commit_pending_cycle;
  logic [NrExecClasses-1:0][63:0] mask_result_queue_nonempty_cycle;
  logic [NrExecClasses-1:0][63:0] mask_final_grant_wait_cycle;
  logic [NrExecClasses-1:0][63:0] mask_index_fifo_nonempty_cycle;
  logic [NrExecClasses-1:0][63:0] mask_request_fifo_nonempty_cycle;

  // Deterministic, mutually-exclusive primary attribution.  The raw reason
  // counters above intentionally overlap; these counters apply a documented
  // downstream-to-upstream priority so their sum is exactly active_cycle.
  logic [NrExecClasses-1:0][63:0] primary_result_backpressure_cycle;
  logic [NrExecClasses-1:0][63:0] primary_result_queue_full_cycle;
  logic [NrExecClasses-1:0][63:0] primary_latency_order_stall_cycle;
  logic [NrExecClasses-1:0][63:0] primary_unit_input_backpressure_cycle;
  logic [NrExecClasses-1:0][63:0] primary_operand_wait_cycle;
  logic [NrExecClasses-1:0][63:0] primary_long_latency_busy_cycle;
  logic [NrExecClasses-1:0][63:0] primary_special_path_cycle;
  logic [NrExecClasses-1:0][63:0] primary_progress_cycle;
  logic [NrExecClasses-1:0][63:0] primary_unattributed_cycle;

  // Deterministic, mutually-exclusive dispatch-side attribution.
  // These counters are applied only when dispatch is stalled for a cycle.
  logic [NrExecClasses-1:0][63:0] primary_fu_queue_full_cycle;
  logic [NrExecClasses-1:0][63:0] primary_mask_queue_full_cycle;
  logic [NrExecClasses-1:0][63:0] primary_slide_queue_full_cycle;
  logic [NrExecClasses-1:0][63:0] primary_id_pool_full_cycle;
  logic [NrExecClasses-1:0][63:0] primary_response_wait_cycle;
  logic [NrExecClasses-1:0][63:0] primary_lane_desync_cycle;
  logic [NrExecClasses-1:0][63:0] primary_sequencer_block_cycle;
  logic [NrExecClasses-1:0][63:0] primary_operand_request_blocked_cycle;
  logic [NrExecClasses-1:0][63:0] primary_other_dispatch_blocked_cycle;
  logic [NrExecClasses-1:0][63:0] primary_dispatch_unattributed_cycle;

  // Opcode-level dispatch-side attribution.
  // These counters are intended to be compared with opcode_dispatch_blocked_cycle.
  logic [NrAraOps-1:0][63:0] opcode_primary_fu_queue_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_mask_queue_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_slide_queue_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_id_pool_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_response_wait_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_lane_desync_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_sequencer_block_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_operand_request_blocked_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_other_dispatch_blocked_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_dispatch_unattributed_cycle;
  // Opcode-level execution-side deterministic primary attribution.
  logic [NrAraOps-1:0][63:0] opcode_primary_result_backpressure_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_result_queue_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_latency_order_stall_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_unit_input_backpressure_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_operand_wait_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_long_latency_busy_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_special_path_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_progress_cycle;
  logic [NrAraOps-1:0][63:0] opcode_primary_unattributed_cycle;
  // Opcode wall-clock active cycles used to normalize execution-side primary
  // attribution ratios. This count increments when any instruction of this opcode
  // is active in the selected cycle.
  logic [NrAraOps-1:0][63:0] opcode_active_cycle;

  // These are lane samples, not wall-clock cycles. If all four lanes observe
  // an event in one cycle, the corresponding counter increases by four.
  logic [NrExecClasses-1:0][63:0] issue_progress_lane_sample;
  logic [NrExecClasses-1:0][63:0] operand_wait_lane_sample;
  logic [NrExecClasses-1:0][63:0] unit_input_backpressure_lane_sample;
  logic [NrExecClasses-1:0][63:0] latency_order_stall_lane_sample;
  logic [NrExecClasses-1:0][63:0] result_queue_full_lane_sample;
  logic [NrExecClasses-1:0][63:0] result_backpressure_lane_sample;
  logic [NrExecClasses-1:0][63:0] long_latency_busy_lane_sample;
  // Occupied result-queue entries sampled across all lanes and cycles.
  logic [NrExecClasses-1:0][63:0] result_queue_occupancy_lane_sample;

  // Predicate density is measured when MASKU creates one expanded mask
  // packet, before per-lane consumers can accept it on different cycles.
  // This is actual mask payload, not merely a count of vm=0 instructions.
  logic [NrExecClasses-1:0][63:0] predicate_packet_count;
  logic [NrExecClasses-1:0][63:0] predicate_element_count;
  logic [NrExecClasses-1:0][63:0] predicate_active_element_count;
  logic [NrExecClasses-1:0][NrMaskDensityBins-1:0][63:0] predicate_density_hist;

  // VRF read-side supply diagnostics.  Samples are lane-requester events;
  // conflicts exclude dependency stalls and operand-queue backpressure.
  logic [NrExecClasses-1:0][63:0] vrf_read_request_lane_sample;
  logic [NrExecClasses-1:0][63:0] vrf_read_grant_lane_sample;
  logic [NrExecClasses-1:0][63:0] vrf_bank_conflict_lane_sample;
  logic [NrExecClasses-1:0][63:0] vrf_hazard_stall_lane_sample;
  logic [NrExecClasses-1:0][63:0] operand_queue_backpressure_lane_sample;

  // MASKU gather/compress pipeline work and pressure.  These distinguish
  // index production, address broadcast, and sparse destination generation.
  logic [NrExecClasses-1:0][63:0] mask_index_fifo_push_count;
  logic [NrExecClasses-1:0][63:0] mask_index_fifo_pop_count;
  logic [NrExecClasses-1:0][63:0] gather_request_fifo_push_count;
  logic [NrExecClasses-1:0][63:0] gather_request_fifo_pop_count;
  logic [NrExecClasses-1:0][63:0] gather_broadcast_request_lane_sample;
  logic [NrExecClasses-1:0][63:0] gather_broadcast_grant_lane_sample;
  logic [NrExecClasses-1:0][63:0] gather_out_of_range_index_count;
  logic [NrExecClasses-1:0][63:0] compress_examined_element_count;
  logic [NrExecClasses-1:0][63:0] compress_selected_element_count;

  // Deep execution-path utilization.  State counters are lane-samples for
  // lane-local units and wall cycles for the central SLDU.
  logic [NrMfpuSubunits-1:0][63:0] mfpu_input_fire_lane_sample;
  logic [NrMfpuSubunits-1:0][63:0] mfpu_input_backpressure_lane_sample;
  logic [NrMfpuSubunits-1:0][63:0] mfpu_output_fire_lane_sample;
  logic [NrMfpuSubunits-1:0][63:0] mfpu_processing_lane_sample;
  logic [NrValuStates-1:0][63:0] valu_state_lane_sample;
  logic [NrMfpuStates-1:0][63:0] mfpu_state_lane_sample;
  logic [NrSlduStates-1:0][63:0] sldu_state_cycle;

  // Opcode-level backend shape and latency.  These are deliberately kept in
  // the same snapshot structure as the class counters.
  logic [NrAraOps-1:0][63:0] opcode_uop_count;
  logic [NrAraOps-1:0][63:0] opcode_completed_count;
  logic [NrAraOps-1:0][63:0] opcode_requested_element_count;
  logic [NrAraOps-1:0][63:0] opcode_nominal_element_op_count;
  logic [NrAraOps-1:0][63:0] opcode_dispatch_request_cycle;
  logic [NrAraOps-1:0][63:0] opcode_dispatch_blocked_cycle;
  logic [NrAraOps-1:0][63:0] opcode_fu_queue_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_mask_queue_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_slide_queue_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_id_pool_full_cycle;
  logic [NrAraOps-1:0][63:0] opcode_response_wait_cycle;
  logic [NrAraOps-1:0][63:0] opcode_other_dispatch_blocked_cycle;
  logic [NrAraOps-1:0][63:0] opcode_operand_request_blocked_cycle;
  logic [NrAraOps-1:0][63:0] opcode_masked_count;
  logic [NrAraOps-1:0][63:0] opcode_execution_latency_cycle;
  logic [NrAraOps-1:0][3:0][63:0] opcode_execution_latency_hist;
  logic [NrAraOps-1:0][3:0][63:0] opcode_sew_hist;
  logic [NrAraOps-1:0][7:0][63:0] opcode_lmul_hist;
  logic [NrAraOps-1:0][3:0][7:0][63:0] opcode_shape_uop_count;
  logic [NrAraOps-1:0][3:0][7:0][63:0] opcode_shape_completed_count;
  logic [NrAraOps-1:0][3:0][7:0][63:0] opcode_shape_latency_cycle;
} exec_perf_t;

// Dispatcher-side architectural counters.  These deliberately live beside,
// rather than inside, exec_perf_t: configuration instructions and zero-VL
// no-ops can complete without ever creating a sequencer instruction ID.
typedef struct {
  logic [NrExecClasses-1:0][63:0] arch_insn_count;
  logic [NrExecClasses-1:0][63:0] zero_vl_nop_count;
  logic [NrAraOps-1:0][63:0] arch_opcode_count;
  logic [NrAraOps-1:0][63:0] arch_opcode_zero_vl_count;
  logic [63:0] unclassified_arch_insn_count;
  logic [63:0] arch_exception_count;

  logic [63:0] config_insn_count;
  logic [63:0] vsetvli_count;
  logic [63:0] vsetivli_count;
  logic [63:0] vsetvl_count;
  logic [63:0] vector_csr_count;
  logic [63:0] vector_csr_write_count;
  logic [63:0] vector_csr_read_only_count;
  logic [63:0] config_request_cycle;
  logic [63:0] config_blocked_cycle;
  logic [63:0] config_wait_idle_cycle;
  logic [63:0] config_wait_backend_busy_cycle;
  logic [63:0] config_wait_ara_ready_cycle;
  logic [63:0] config_wait_reshuffle_cycle;
  logic [63:0] config_other_blocked_cycle;
  logic [63:0] vset_result_vl_sum;
  logic [63:0] vset_zero_vl_count;
  logic [63:0] vset_vill_count;
  logic [63:0] vset_vl_change_count;
  logic [63:0] vset_vtype_change_count;
  logic [63:0] vset_lmul_shrink_wait_count;
  logic [3:0][63:0] vset_sew_hist;
  logic [7:0][63:0] vset_lmul_hist;

  // Architectural memory instruction shape.  Unlike exec_perf_t's backend
  // uop counters, one increment here always means one instruction presented
  // by CVA6, even when a segment operation expands into many backend requests.
  logic [NrMemClasses-1:0][63:0] memory_insn_count;
  logic [NrMemClasses-1:0][63:0] memory_unit_stride_count;
  logic [NrMemClasses-1:0][63:0] memory_strided_count;
  logic [NrMemClasses-1:0][63:0] memory_indexed_unordered_count;
  logic [NrMemClasses-1:0][63:0] memory_indexed_ordered_count;
  logic [NrMemClasses-1:0][63:0] memory_segment_count;
  logic [NrMemClasses-1:0][63:0] memory_whole_register_count;
  logic [NrMemClasses-1:0][63:0] memory_mask_count;
  logic [NrMemClasses-1:0][63:0] memory_field_count;
  logic [NrMemClasses-1:0][63:0] memory_requested_element_count;
  logic [NrMemClasses-1:0][63:0] memory_requested_byte_count;
  logic [NrMemClasses-1:0][63:0] memory_exception_count;
  logic [63:0] load_fault_only_first_count;
  // Request-side shape counts are captured when the sequencer accepts an
  // instruction.  Response-side architectural counts above intentionally
  // require retirement; keeping both distinguishes "issued then hung" from
  // "never issued" and preserves mop/nf/lumop detail in watchdog snapshots.
  logic [NrMemClasses-1:0][63:0] memory_accepted_count;
  logic [NrMemClasses-1:0][63:0] memory_accepted_unit_stride_count;
  logic [NrMemClasses-1:0][63:0] memory_accepted_strided_count;
  logic [NrMemClasses-1:0][63:0] memory_accepted_indexed_unordered_count;
  logic [NrMemClasses-1:0][63:0] memory_accepted_indexed_ordered_count;
  logic [NrMemClasses-1:0][63:0] memory_accepted_segment_count;
  logic [NrMemClasses-1:0][63:0] memory_accepted_whole_register_count;
  logic [NrMemClasses-1:0][63:0] memory_accepted_mask_count;
  logic [63:0] load_accepted_fault_only_first_count;
} frontend_perf_t;

// VLSU microarchitecture counters.  A cycle counter answers "how long was
// this condition present"; a transaction/sample counter answers "how much
// work crossed this interface".  Keeping both is important for bottleneck
// attribution because several lane handshakes can happen in one wall cycle.
typedef struct {
  logic [NrMemClasses-1:0][63:0] addrgen_active_cycle;
  logic [NrMemClasses-1:0][63:0] addrgen_progress_cycle;
  logic [NrMemClasses-1:0][63:0] addrgen_no_progress_cycle;
  // State residency makes a no-progress interval actionable: it identifies
  // which address-generation phase owns the stall instead of collapsing all
  // indexed/translation/AXI behavior into the generic "special path" bucket.
  logic [NrMemClasses-1:0][4:0][63:0] addrgen_state_cycle;
  logic [NrMemClasses-1:0][3:0][63:0] axi_addrgen_state_cycle;
  logic [NrMemClasses-1:0][63:0] addrgen_operand_wait_cycle;
  logic [NrMemClasses-1:0][63:0] indexed_spill_wait_cycle;
  logic [NrMemClasses-1:0][63:0] last_translation_wait_cycle;
  logic [NrMemClasses-1:0][63:0] addrgen_queue_consumer_wait_cycle;
  logic [NrMemClasses-1:0][63:0] addrgen_queue_full_cycle;
  logic [NrMemClasses-1:0][63:0] core_store_pending_wait_cycle;
  logic [NrMemClasses-1:0][63:0] mmu_request_cycle;
  logic [NrMemClasses-1:0][63:0] mmu_wait_cycle;
  logic [NrMemClasses-1:0][63:0] mmu_dtlb_hit_count;
  logic [NrMemClasses-1:0][63:0] mmu_response_count;
  logic [NrMemClasses-1:0][63:0] mmu_exception_count;
  logic [NrMemClasses-1:0][63:0] axi_address_valid_cycle;
  logic [NrMemClasses-1:0][63:0] axi_address_fire_count;
  logic [NrMemClasses-1:0][63:0] axi_address_backpressure_cycle;
  logic [NrMemClasses-1:0][63:0] axi_data_valid_cycle;
  logic [NrMemClasses-1:0][63:0] axi_data_fire_count;
  logic [NrMemClasses-1:0][63:0] axi_data_backpressure_cycle;
  logic [NrMemClasses-1:0][63:0] axi_data_wait_cycle;
  logic [NrMemClasses-1:0][63:0] axi_response_valid_cycle;
  logic [NrMemClasses-1:0][63:0] axi_response_fire_count;
  logic [NrMemClasses-1:0][63:0] axi_response_wait_cycle;
  logic [NrMemClasses-1:0][63:0] axi_transfer_byte_count;
  logic [NrMemClasses-1:0][63:0] axi_useful_byte_count;
  logic [NrMemClasses-1:0][63:0] axi_outstanding_sample_cycle;
  logic [NrMemClasses-1:0][63:0] axi_outstanding_cycle_sum;
  logic [NrMemClasses-1:0][63:0] axi_outstanding_nonzero_cycle;
  logic [NrMemClasses-1:0][NrAxiOutstandingBins-1:0][63:0] axi_outstanding_hist;
  logic [NrMemClasses-1:0][63:0] axi_request_latency_count;
  logic [NrMemClasses-1:0][63:0] axi_request_latency_cycle;
  logic [NrMemClasses-1:0][3:0][63:0] axi_request_latency_hist;
  logic [NrMemClasses-1:0][63:0] axi_tracking_overflow_count;
  logic [NrMemClasses-1:0][63:0] axi_tracking_underflow_count;
  logic [NrMemClasses-1:0][63:0] mask_wait_cycle;
  logic [NrMemClasses-1:0][63:0] result_queue_full_cycle;
  logic [NrMemClasses-1:0][63:0] operand_wait_cycle;
  logic [NrMemClasses-1:0][63:0] result_backpressure_cycle;
  logic [NrMemClasses-1:0][63:0] operand_handshake_lane_sample;
  logic [NrMemClasses-1:0][63:0] result_request_lane_sample;
  logic [NrMemClasses-1:0][63:0] result_handshake_lane_sample;
  logic [NrMemClasses-1:0][63:0] result_backpressure_lane_sample;
  logic [NrMemClasses-1:0][63:0] completion_count;
  logic [NrMemClasses-1:0][63:0] exception_count;
} memory_perf_t;

// Main-sequencer VFU queue occupancy.  The final histogram bin includes the
// gold-ticket depth+1 state, so no sample is silently dropped.
typedef struct {
  logic [NrVFUs-1:0][63:0] sample_cycle;
  logic [NrVFUs-1:0][63:0] occupancy_cycle_sum;
  logic [NrVFUs-1:0][63:0] nonempty_cycle;
  logic [NrVFUs-1:0][63:0] at_capacity_cycle;
  logic [NrVFUs-1:0][NrQueueOccupancyBins-1:0][63:0] occupancy_hist;
} vfu_queue_perf_t;

typedef struct packed {
  exec_class_mask_t issue_progress;
  exec_class_mask_t operand_wait;
  exec_class_mask_t unit_input_backpressure;
  exec_class_mask_t latency_order_stall;
  exec_class_mask_t result_queue_full;
  exec_class_mask_t result_backpressure;
  exec_class_mask_t long_latency_busy;
  exec_class_mask_t reduction;
  exec_class_mask_t cross_lane;
  exec_class_mask_t special_path;
  exec_class_mask_t index_fifo_full;
} exec_event_t;

function automatic logic is_exec_reduction(ara_op_e op);
  return op inside {[VREDSUM:VWREDSUM], [VFREDUSUM:VFWREDOSUM]};
endfunction

function automatic logic is_exec_special_path(ara_op_e op, logic is_stride_np2);
  return (op inside {[VRGATHER:VCOMPRESS]}) ||
         ((op inside {[VSLIDEUP:VSLIDEDOWN]}) && is_stride_np2);
endfunction

// A nominal element operation is a workload-normalization unit, not a gate-
// level operation count.  Fused integer/FP multiply-adds contribute two; all
// other non-memory Ara operations contribute one per requested element.
function automatic int unsigned nominal_element_op_weight(ara_op_e op);
  if (op inside {[VMACC:VNMSUB], [VFMACC:VFNMSUB]})
    return 2;
  if (op inside {[VLE:VSXE]})
    return 0;
  return 1;
endfunction

function automatic int unsigned vfu_queue_depth(vfu_e vfu);
  unique case (vfu)
    VFU_Alu:       return ValuInsnQueueDepth;
    VFU_MFpu:      return MfpuInsnQueueDepth;
    VFU_SlideUnit: return SlduInsnQueueDepth;
    VFU_MaskUnit:  return MaskuInsnQueueDepth;
    VFU_LoadUnit:  return VlduInsnQueueDepth;
    VFU_StoreUnit: return VstuInsnQueueDepth;
    VFU_None:      return NoneInsnQueueDepth;
    default:       return 0;
  endcase
endfunction

function automatic exec_class_mask_t classify_exec_op(ara_op_e op);
  exec_class_mask_t op_class;
  op_class = '0;
  unique case (op) inside
    // Integer arithmetic/logic/fixed-point/shift/reduction plus integer
    // comparisons and carry/borrow mask results computed by the VALU.
    [VADD:VMERGE], [VREDSUM:VWREDSUM], [VMSEQ:VMSBC]:
      op_class[ExecValu] = 1'b1;
    // Scalar/FP scalar to vector-register moves execute in the lane VALU, but
    // are kept separate because their operand and useful-work shape differs
    // substantially from ordinary element-wise arithmetic.
    VMVSX, VFMVSF:                    op_class[ExecMoveToVec] = 1'b1;
    // Integer multiply, multiply-accumulate, and fixed-point multiply.
    [VMUL:VSMUL]:                    op_class[ExecMul] = 1'b1;
    // Integer divide and remainder.
    [VDIVU:VREM]:                    op_class[ExecDiv] = 1'b1;
    // Floating-point arithmetic/conversion/reduction/comparison.
    [VFADD:VMFGE]:                   op_class[ExecFp] = 1'b1;
    // Native mask/bit-level/prefix/gather/compress instructions. Integer and
    // FP comparisons stay in their arithmetic class to avoid double counting.
    [VMSBF:VCOMPRESS]:               op_class[ExecMask] = 1'b1;
    // Native slide instructions. Reduction use of the SLDU remains attributed
    // to VALU/FP because it is part of those instructions' execution.
    [VSLIDEUP:VSLIDEDOWN]:           op_class[ExecSlide] = 1'b1;
    [VLE:VLXE]:                       op_class[ExecLoad] = 1'b1;
    [VSE:VSXE]:                       op_class[ExecStore] = 1'b1;
    // These return a scalar and therefore target VFU_None in the sequencer.
    VMVXS, VFMVFS:                    op_class[ExecMoveFromVec] = 1'b1;
    default:                         op_class = '0;
  endcase
  classify_exec_op = op_class;
endfunction

function automatic real perf_ratio(logic [63:0] numerator, logic [63:0] denominator);
  perf_ratio = denominator == '0 ? 0.0 : real'(numerator) / real'(denominator);
endfunction

function automatic red_stream_perf_t red_stream_perf_delta(
  red_stream_perf_t end_count, red_stream_perf_t start_count
);
  red_stream_perf_t delta;
  delta.window_lane_sample =
    end_count.window_lane_sample - start_count.window_lane_sample;
  delta.no_candidate_lane_sample =
    end_count.no_candidate_lane_sample - start_count.no_candidate_lane_sample;
  delta.candidate_lane_sample =
    end_count.candidate_lane_sample - start_count.candidate_lane_sample;
  delta.eligible_lane_sample =
    end_count.eligible_lane_sample - start_count.eligible_lane_sample;
  delta.reject_unsupported_lane_sample = end_count.reject_unsupported_lane_sample -
    start_count.reject_unsupported_lane_sample;
  delta.reject_mask_lane_sample =
    end_count.reject_mask_lane_sample - start_count.reject_mask_lane_sample;
  delta.reject_short_vl_lane_sample = end_count.reject_short_vl_lane_sample -
    start_count.reject_short_vl_lane_sample;
  delta.reject_opcode_lane_sample =
    end_count.reject_opcode_lane_sample - start_count.reject_opcode_lane_sample;
  delta.reject_sew_lane_sample =
    end_count.reject_sew_lane_sample - start_count.reject_sew_lane_sample;
  delta.reject_rounding_lane_sample = end_count.reject_rounding_lane_sample -
    start_count.reject_rounding_lane_sample;
  delta.start_lane_sample =
    end_count.start_lane_sample - start_count.start_lane_sample;
  delta.active_lane_sample =
    end_count.active_lane_sample - start_count.active_lane_sample;
  delta.background_issue_lane_sample = end_count.background_issue_lane_sample -
    start_count.background_issue_lane_sample;
  delta.primary_conflict_lane_sample = end_count.primary_conflict_lane_sample -
    start_count.primary_conflict_lane_sample;
  delta.complete_lane_sample =
    end_count.complete_lane_sample - start_count.complete_lane_sample;
  delta.complete_wait_lane_sample = end_count.complete_wait_lane_sample -
    start_count.complete_wait_lane_sample;
  delta.full_promotion_lane_sample = end_count.full_promotion_lane_sample -
    start_count.full_promotion_lane_sample;
  delta.partial_promotion_lane_sample = end_count.partial_promotion_lane_sample -
    start_count.partial_promotion_lane_sample;
  delta.root_nonempty_lane_sample = end_count.root_nonempty_lane_sample -
    start_count.root_nonempty_lane_sample;
  delta.root_full_lane_sample = end_count.root_full_lane_sample -
    start_count.root_full_lane_sample;
  delta.root_occupancy_lane_sum = end_count.root_occupancy_lane_sum -
    start_count.root_occupancy_lane_sum;
  delta.root_push_lane_sample = end_count.root_push_lane_sample -
    start_count.root_push_lane_sample;
  delta.root_pop_lane_sample = end_count.root_pop_lane_sample -
    start_count.root_pop_lane_sample;
  delta.slack_defer_lane_sample = end_count.slack_defer_lane_sample -
    start_count.slack_defer_lane_sample;
  delta.slack_score_lane_sum = end_count.slack_score_lane_sum -
    start_count.slack_score_lane_sum;
  return delta;
endfunction

function automatic void print_red_stream_report(
  input integer file_handle,
  input red_stream_perf_t stats
);
  for (int unsigned c = 0; c < NrRedStreamClasses; c++) begin
    automatic string name = c == RedStreamValu ? "valu" : "fp";
    automatic logic [63:0] candidate_outcomes =
      stats.eligible_lane_sample[c] +
      stats.reject_unsupported_lane_sample[c] +
      stats.reject_mask_lane_sample[c] +
      stats.reject_short_vl_lane_sample[c] +
      stats.reject_opcode_lane_sample[c] +
      stats.reject_sew_lane_sample[c] +
      stats.reject_rounding_lane_sample[c];
    if (file_handle == 0) begin
      $display("[PERF] red_stream_%s_window_lane_samples: %0d", name,
        stats.window_lane_sample[c]);
      $display("[PERF] red_stream_%s_no_candidate_lane_samples: %0d", name,
        stats.no_candidate_lane_sample[c]);
      $display("[PERF] red_stream_%s_candidate_lane_samples: %0d", name,
        stats.candidate_lane_sample[c]);
      $display("[PERF] red_stream_%s_eligible_lane_samples: %0d", name,
        stats.eligible_lane_sample[c]);
      $display("[PERF] red_stream_%s_hit_ratio: %0.6f", name,
        perf_ratio(stats.eligible_lane_sample[c], stats.candidate_lane_sample[c]));
      $display("[PERF] red_stream_%s_reject_unsupported_lane_samples: %0d", name,
        stats.reject_unsupported_lane_sample[c]);
      $display("[PERF] red_stream_%s_reject_mask_lane_samples: %0d", name,
        stats.reject_mask_lane_sample[c]);
      $display("[PERF] red_stream_%s_reject_short_vl_lane_samples: %0d", name,
        stats.reject_short_vl_lane_sample[c]);
      $display("[PERF] red_stream_%s_reject_opcode_lane_samples: %0d", name,
        stats.reject_opcode_lane_sample[c]);
      $display("[PERF] red_stream_%s_reject_sew_lane_samples: %0d", name,
        stats.reject_sew_lane_sample[c]);
      $display("[PERF] red_stream_%s_reject_rounding_lane_samples: %0d", name,
        stats.reject_rounding_lane_sample[c]);
      $display("[PERF] red_stream_%s_start_lane_samples: %0d", name,
        stats.start_lane_sample[c]);
      $display("[PERF] red_stream_%s_active_lane_samples: %0d", name,
        stats.active_lane_sample[c]);
      $display("[PERF] red_stream_%s_background_issue_lane_samples: %0d", name,
        stats.background_issue_lane_sample[c]);
      $display("[PERF] red_stream_%s_primary_conflict_lane_samples: %0d", name,
        stats.primary_conflict_lane_sample[c]);
      $display("[PERF] red_stream_%s_complete_lane_samples: %0d", name,
        stats.complete_lane_sample[c]);
      $display("[PERF] red_stream_%s_complete_wait_lane_samples: %0d", name,
        stats.complete_wait_lane_sample[c]);
      $display("[PERF] red_stream_%s_full_promotion_lane_samples: %0d", name,
        stats.full_promotion_lane_sample[c]);
      $display("[PERF] red_stream_%s_partial_promotion_lane_samples: %0d", name,
        stats.partial_promotion_lane_sample[c]);
      $display("[PERF] red_stream_%s_root_nonempty_lane_samples: %0d", name,
        stats.root_nonempty_lane_sample[c]);
      $display("[PERF] red_stream_%s_root_full_lane_samples: %0d", name,
        stats.root_full_lane_sample[c]);
      $display("[PERF] red_stream_%s_root_occupancy_lane_sum: %0d", name,
        stats.root_occupancy_lane_sum[c]);
      $display("[PERF] red_stream_%s_root_push_lane_samples: %0d", name,
        stats.root_push_lane_sample[c]);
      $display("[PERF] red_stream_%s_root_pop_lane_samples: %0d", name,
        stats.root_pop_lane_sample[c]);
      $display("[PERF] red_stream_%s_slack_defer_lane_samples: %0d", name,
        stats.slack_defer_lane_sample[c]);
      $display("[PERF] red_stream_%s_slack_score_lane_sum: %0d", name,
        stats.slack_score_lane_sum[c]);
      $display("[PERF] red_stream_%s_candidate_partition_consistent: %0d", name,
        candidate_outcomes == stats.candidate_lane_sample[c]);
    end else begin
      $fwrite(file_handle, "[PERF] red_stream_%s_window_lane_samples: %0d\n", name,
        stats.window_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_no_candidate_lane_samples: %0d\n", name,
        stats.no_candidate_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_candidate_lane_samples: %0d\n", name,
        stats.candidate_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_eligible_lane_samples: %0d\n", name,
        stats.eligible_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_hit_ratio: %0.6f\n", name,
        perf_ratio(stats.eligible_lane_sample[c], stats.candidate_lane_sample[c]));
      $fwrite(file_handle,
        "[PERF] red_stream_%s_reject_unsupported_lane_samples: %0d\n", name,
        stats.reject_unsupported_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_reject_mask_lane_samples: %0d\n", name,
        stats.reject_mask_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_reject_short_vl_lane_samples: %0d\n", name,
        stats.reject_short_vl_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_reject_opcode_lane_samples: %0d\n", name,
        stats.reject_opcode_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_reject_sew_lane_samples: %0d\n", name,
        stats.reject_sew_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_reject_rounding_lane_samples: %0d\n", name,
        stats.reject_rounding_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_start_lane_samples: %0d\n", name,
        stats.start_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_active_lane_samples: %0d\n", name,
        stats.active_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_background_issue_lane_samples: %0d\n", name,
        stats.background_issue_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_primary_conflict_lane_samples: %0d\n", name,
        stats.primary_conflict_lane_sample[c]);
      $fwrite(file_handle, "[PERF] red_stream_%s_complete_lane_samples: %0d\n", name,
        stats.complete_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_complete_wait_lane_samples: %0d\n", name,
        stats.complete_wait_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_full_promotion_lane_samples: %0d\n", name,
        stats.full_promotion_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_partial_promotion_lane_samples: %0d\n", name,
        stats.partial_promotion_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_root_nonempty_lane_samples: %0d\n", name,
        stats.root_nonempty_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_root_full_lane_samples: %0d\n", name,
        stats.root_full_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_root_occupancy_lane_sum: %0d\n", name,
        stats.root_occupancy_lane_sum[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_root_push_lane_samples: %0d\n", name,
        stats.root_push_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_root_pop_lane_samples: %0d\n", name,
        stats.root_pop_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_slack_defer_lane_samples: %0d\n", name,
        stats.slack_defer_lane_sample[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_slack_score_lane_sum: %0d\n", name,
        stats.slack_score_lane_sum[c]);
      $fwrite(file_handle,
        "[PERF] red_stream_%s_candidate_partition_consistent: %0d\n", name,
        candidate_outcomes == stats.candidate_lane_sample[c]);
    end
  end
endfunction

function automatic string exec_class_name(input exec_class_e class_id);
  case (class_id)
    ExecValu:       return "valu";
    ExecMul:        return "mul";
    ExecDiv:        return "div";
    ExecFp:         return "fp";
    ExecSlide:      return "slide";
    ExecMask:       return "mask";
    ExecLoad:       return "load";
    ExecStore:      return "store";
    ExecMoveToVec:  return "move_to_vec";
    ExecMoveFromVec: return "move_from_vec";
    ExecReshuffle:  return "reshuffle";
    default:         return "unknown";
  endcase
endfunction

task automatic update_top2(
  input logic [63:0] value,
  input string reason,
  inout logic [63:0] top1_value,
  inout string top1_reason,
  inout logic [63:0] top2_value,
  inout string top2_reason
);
  if (value > top1_value) begin
    top2_value  = top1_value;
    top2_reason = top1_reason;
    top1_value  = value;
    top1_reason = reason;
  end else if (value > top2_value && value < top1_value) begin
    top2_value  = value;
    top2_reason = reason;
  end
endtask

task automatic print_global_bottleneck_summary(
  input integer         file_handle,
  input exec_perf_t     stats,
  input frontend_perf_t frontend
);
  // Global dispatch-side aggregation.
  logic [63:0] total_dispatch_request;
  logic [63:0] total_dispatch_blocked;
  logic [63:0] top_global_dispatch_reason_count;
  string       top_global_dispatch_reason;
  logic [63:0] second_global_dispatch_reason_count;
  string       second_global_dispatch_reason;
  logic [63:0] top_class_dispatch_blocked_count;
  string       top_class_dispatch_blocked_name;
  logic [63:0] second_class_dispatch_blocked_count;
  string       second_class_dispatch_blocked_name;
  logic [63:0] top_opcode_dispatch_blocked_count;
  string       top_opcode_dispatch_blocked_name;
  logic [63:0] second_opcode_dispatch_blocked_count;
  string       second_opcode_dispatch_blocked_name;
  logic [63:0] top_global_dispatch_gap;
  real         top_global_dispatch_gap_ratio_request;
  real         top_global_dispatch_dominance_ratio;
  real         second_global_dispatch_dominance_ratio;

  // Global execution-side aggregation.
  logic [63:0] total_exec_active;
  logic [63:0] total_exec_wait;
  logic [63:0] top_global_exec_reason_count;
  string       top_global_exec_reason;
  logic [63:0] second_global_exec_reason_count;
  string       second_global_exec_reason;
  logic [63:0] top_global_exec_reason_gap;
  real         top_global_exec_reason_gap_ratio_exec_active;
  real         top_global_exec_dominance_ratio;
  real         second_global_exec_dominance_ratio;
  logic [63:0] top_class_exec_wait_count;
  string       top_class_exec_wait_name;
  logic [63:0] second_class_exec_wait_count;
  string       second_class_exec_wait_name;
  logic [63:0] top_opcode_exec_wait_count;
  string       top_opcode_exec_wait_name;
  logic [63:0] second_opcode_exec_wait_count;
  string       second_opcode_exec_wait_name;
  logic [NrExecClasses-1:0][63:0] class_dispatch_blocked_hist;
  logic [NrExecClasses-1:0][63:0] class_exec_wait_hist;
  logic [NrAraOps-1:0][63:0]      op_dispatch_blocked_hist;
  logic [NrAraOps-1:0][63:0]      op_exec_wait_hist;
  // Global reason totals (deterministic primary attribution where available).
  logic [63:0] g_primary_fu_queue_full;
  logic [63:0] g_primary_mask_queue_full;
  logic [63:0] g_primary_slide_queue_full;
  logic [63:0] g_primary_id_pool_full;
  logic [63:0] g_primary_response_wait;
  logic [63:0] g_primary_lane_desync;
  logic [63:0] g_primary_sequencer_block;
  logic [63:0] g_primary_operand_request_blocked;
  logic [63:0] g_primary_other_dispatch_blocked;
  logic [63:0] g_primary_dispatch_unattributed;
  logic [63:0] g_primary_result_backpressure;
  logic [63:0] g_primary_result_queue_full;
  logic [63:0] g_primary_latency_order_stall;
  logic [63:0] g_primary_unit_input_backpressure;
  logic [63:0] g_primary_operand_wait;
  logic [63:0] g_primary_long_latency_busy;
  logic [63:0] g_primary_special_path;
  logic [63:0] g_primary_progress;
  logic [63:0] g_primary_unattributed;
  // Shared accumulators for class/op ranking.
  logic [63:0] class_dispatch_blocked;
  logic [63:0] class_exec_wait;
  logic [63:0] op_dispatch_blocked;
  logic [63:0] op_exec_wait;
  logic [63:0] class_dispatch_request;
  logic [63:0] class_active;
  logic [63:0] class_completed;
  logic [63:0] class_exec_primary_reason_cycles;
  logic [63:0] class_dispatch_primary_reason_cycles;
  logic [63:0] op_dispatch_request;
  logic [63:0] op_active;
  logic [63:0] op_completed;
  logic [63:0] total_dispatch_primary_reason_cycles;
  logic [63:0] total_exec_primary_reason_cycles;
  logic [63:0] top_class_dispatch_request_count;
  string       top_class_dispatch_request_name;
  logic [63:0] second_class_dispatch_request_count;
  string       second_class_dispatch_request_name;
  logic [63:0] top_class_active_count;
  string       top_class_active_name;
  logic [63:0] second_class_active_count;
  string       second_class_active_name;
  logic [63:0] top_class_completed_count;
  string       top_class_completed_name;
  logic [63:0] second_class_completed_count;
  string       second_class_completed_name;
  logic [63:0] top_opcode_dispatch_request_count;
  string       top_opcode_dispatch_request_name;
  logic [63:0] second_opcode_dispatch_request_count;
  string       second_opcode_dispatch_request_name;
  logic [63:0] top_opcode_active_count;
  string       top_opcode_active_name;
  logic [63:0] second_opcode_active_count;
  string       second_opcode_active_name;
  logic [63:0] top_opcode_completed_count;
  string       top_opcode_completed_name;
  logic [63:0] second_opcode_completed_count;
  string       second_opcode_completed_name;
  logic [63:0] total_issue_progress;
  logic [63:0] total_no_issue_progress;
  real         top_class_dispatch_request_share;
  real         top_class_active_share;
  real         top_class_share_skew;
  real         top_opcode_dispatch_request_share;
  real         top_opcode_active_share;
  real         top_opcode_share_skew;
  real         global_top2_dispatch_request_share;
  real         global_top2_active_share;
  real         global_top2_dispatch_blocked_share;
  real         global_top2_exec_wait_share;
  real         global_top2_dispatch_bottleneck_share;
  real         global_top2_exec_bottleneck_share;
  real         global_dispatch_exec_class_overlap;
  real         global_dispatch_exec_opcode_overlap;
  string       global_bottleneck_pressure_alignment;
  string       global_bottleneck_opcode_alignment;
  real         global_dispatch_blocked_ratio;
  real         global_issue_progress_ratio;
  real         global_no_issue_progress_ratio;
  string       global_stage_mode;
  string       global_bottleneck_focus;
  string       global_bottleneck_secondary_hint;

  total_dispatch_request = '0;
  total_dispatch_blocked = '0;
  total_exec_active = '0;
  total_exec_wait = '0;
  total_issue_progress = '0;
  total_no_issue_progress = '0;
  top_global_dispatch_reason_count = '0;
  top_global_dispatch_reason = "none";
  second_global_dispatch_reason_count = '0;
  second_global_dispatch_reason = "none";
  top_global_exec_reason_count = '0;
  top_global_exec_reason = "none";
  second_global_exec_reason_count = '0;
  second_global_exec_reason = "none";

  top_class_dispatch_blocked_count = '0;
  top_class_dispatch_blocked_name = "none";
  second_class_dispatch_blocked_count = '0;
  second_class_dispatch_blocked_name = "none";
  top_class_exec_wait_count = '0;
  top_class_exec_wait_name = "none";
  second_class_exec_wait_count = '0;
  second_class_exec_wait_name = "none";

  top_opcode_dispatch_blocked_count = '0;
  top_opcode_dispatch_blocked_name = "none";
  second_opcode_dispatch_blocked_count = '0;
  second_opcode_dispatch_blocked_name = "none";
  top_opcode_exec_wait_count = '0;
  top_opcode_exec_wait_name = "none";
  second_opcode_exec_wait_count = '0;
  second_opcode_exec_wait_name = "none";
  top_class_dispatch_request_count = '0;
  top_class_dispatch_request_name = "none";
  second_class_dispatch_request_count = '0;
  second_class_dispatch_request_name = "none";
  top_class_active_count = '0;
  top_class_active_name = "none";
  second_class_active_count = '0;
  second_class_active_name = "none";
  top_class_completed_count = '0;
  top_class_completed_name = "none";
  second_class_completed_count = '0;
  second_class_completed_name = "none";
  top_opcode_dispatch_request_count = '0;
  top_opcode_dispatch_request_name = "none";
  second_opcode_dispatch_request_count = '0;
  second_opcode_dispatch_request_name = "none";
  top_opcode_active_count = '0;
  top_opcode_active_name = "none";
  second_opcode_active_count = '0;
  second_opcode_active_name = "none";
  top_opcode_completed_count = '0;
  top_opcode_completed_name = "none";
  second_opcode_completed_count = '0;
  second_opcode_completed_name = "none";

  g_primary_fu_queue_full = '0;
  g_primary_mask_queue_full = '0;
  g_primary_slide_queue_full = '0;
  g_primary_id_pool_full = '0;
  g_primary_response_wait = '0;
  g_primary_lane_desync = '0;
  g_primary_sequencer_block = '0;
  g_primary_operand_request_blocked = '0;
  g_primary_other_dispatch_blocked = '0;
  g_primary_dispatch_unattributed = '0;
  g_primary_result_backpressure = '0;
  g_primary_result_queue_full = '0;
  g_primary_latency_order_stall = '0;
  g_primary_unit_input_backpressure = '0;
  g_primary_operand_wait = '0;
  g_primary_long_latency_busy = '0;
  g_primary_special_path = '0;
  g_primary_progress = '0;
  g_primary_unattributed = '0;
  total_dispatch_primary_reason_cycles = '0;
  total_exec_primary_reason_cycles = '0;
  global_top2_dispatch_request_share = 0.0;
  global_top2_active_share = 0.0;
  global_top2_dispatch_blocked_share = 0.0;
  global_top2_exec_wait_share = 0.0;
  global_top2_dispatch_bottleneck_share = 0.0;
  global_top2_exec_bottleneck_share = 0.0;
  global_dispatch_exec_class_overlap = 0.0;
  global_dispatch_exec_opcode_overlap = 0.0;
  global_bottleneck_pressure_alignment = "none";
  global_bottleneck_opcode_alignment = "none";
  for (int unsigned c = 0; c < NrExecClasses; c++) begin
    class_dispatch_blocked_hist[c] = '0;
    class_exec_wait_hist[c] = '0;
  end
  for (int unsigned op = 0; op < NrAraOps; op++) begin
    op_dispatch_blocked_hist[op] = '0;
    op_exec_wait_hist[op] = '0;
  end

  for (int unsigned c = 0; c < NrExecClasses; c++) begin
    total_dispatch_request += stats.dispatch_request_cycle[c];
    total_dispatch_blocked += stats.dispatch_blocked_cycle[c];
    total_exec_active += stats.active_cycle[c];
    total_issue_progress += stats.issue_progress_cycle[c];
    total_no_issue_progress += stats.no_issue_progress_cycle[c];
    class_dispatch_request = stats.dispatch_request_cycle[c];
    class_active = stats.active_cycle[c];
    class_completed = stats.completed_count[c];
    class_dispatch_primary_reason_cycles =
      stats.primary_fu_queue_full_cycle[c] +
      stats.primary_mask_queue_full_cycle[c] +
      stats.primary_slide_queue_full_cycle[c] +
      stats.primary_id_pool_full_cycle[c] +
      stats.primary_response_wait_cycle[c] +
      stats.primary_lane_desync_cycle[c] +
      stats.primary_sequencer_block_cycle[c] +
      stats.primary_operand_request_blocked_cycle[c] +
      stats.primary_other_dispatch_blocked_cycle[c] +
      stats.primary_dispatch_unattributed_cycle[c];
    class_exec_primary_reason_cycles =
      stats.primary_result_backpressure_cycle[c] +
      stats.primary_result_queue_full_cycle[c] +
      stats.primary_latency_order_stall_cycle[c] +
      stats.primary_unit_input_backpressure_cycle[c] +
      stats.primary_operand_wait_cycle[c] +
      stats.primary_long_latency_busy_cycle[c] +
      stats.primary_special_path_cycle[c] +
      stats.primary_progress_cycle[c] +
      stats.primary_unattributed_cycle[c];
    total_dispatch_primary_reason_cycles += class_dispatch_primary_reason_cycles;
    total_exec_primary_reason_cycles += class_exec_primary_reason_cycles;
    update_top2(
      class_dispatch_request,
      exec_class_name(c),
      top_class_dispatch_request_count, top_class_dispatch_request_name,
      second_class_dispatch_request_count, second_class_dispatch_request_name
    );
    update_top2(
      class_active,
      exec_class_name(c),
      top_class_active_count, top_class_active_name,
      second_class_active_count, second_class_active_name
    );
    update_top2(
      class_completed,
      exec_class_name(c),
      top_class_completed_count, top_class_completed_name,
      second_class_completed_count, second_class_completed_name
    );

    g_primary_fu_queue_full += stats.primary_fu_queue_full_cycle[c];
    g_primary_mask_queue_full += stats.primary_mask_queue_full_cycle[c];
    g_primary_slide_queue_full += stats.primary_slide_queue_full_cycle[c];
    g_primary_id_pool_full += stats.primary_id_pool_full_cycle[c];
    g_primary_response_wait += stats.primary_response_wait_cycle[c];
    g_primary_lane_desync += stats.primary_lane_desync_cycle[c];
    g_primary_sequencer_block += stats.primary_sequencer_block_cycle[c];
    g_primary_operand_request_blocked += stats.primary_operand_request_blocked_cycle[c];
    g_primary_other_dispatch_blocked += stats.primary_other_dispatch_blocked_cycle[c];
    g_primary_dispatch_unattributed += stats.primary_dispatch_unattributed_cycle[c];

    g_primary_result_backpressure += stats.primary_result_backpressure_cycle[c];
    g_primary_result_queue_full += stats.primary_result_queue_full_cycle[c];
    g_primary_latency_order_stall += stats.primary_latency_order_stall_cycle[c];
    g_primary_unit_input_backpressure += stats.primary_unit_input_backpressure_cycle[c];
    g_primary_operand_wait += stats.primary_operand_wait_cycle[c];
    g_primary_long_latency_busy += stats.primary_long_latency_busy_cycle[c];
    g_primary_special_path += stats.primary_special_path_cycle[c];
    g_primary_progress += stats.primary_progress_cycle[c];
    g_primary_unattributed += stats.primary_unattributed_cycle[c];

    class_dispatch_blocked = stats.dispatch_blocked_cycle[c];
    class_exec_wait = stats.primary_result_backpressure_cycle[c] +
                      stats.primary_result_queue_full_cycle[c] +
                      stats.primary_latency_order_stall_cycle[c] +
                      stats.primary_unit_input_backpressure_cycle[c] +
                      stats.primary_operand_wait_cycle[c] +
                      stats.primary_long_latency_busy_cycle[c] +
                      stats.primary_special_path_cycle[c] +
                      stats.primary_unattributed_cycle[c];
    total_exec_wait += class_exec_wait;
    class_dispatch_blocked_hist[c] = class_dispatch_blocked;
    class_exec_wait_hist[c] = class_exec_wait;

    update_top2(
      class_dispatch_blocked,
      exec_class_name(c),
      top_class_dispatch_blocked_count, top_class_dispatch_blocked_name,
      second_class_dispatch_blocked_count, second_class_dispatch_blocked_name
    );
    update_top2(
      class_exec_wait,
      exec_class_name(c),
      top_class_exec_wait_count, top_class_exec_wait_name,
      second_class_exec_wait_count, second_class_exec_wait_name
    );
  end

  update_top2(
    g_primary_fu_queue_full,
    "primary_fu_queue_full",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_mask_queue_full,
    "primary_mask_queue_full",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_slide_queue_full,
    "primary_slide_queue_full",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_id_pool_full,
    "primary_id_pool_full",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_response_wait,
    "primary_response_wait",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_lane_desync,
    "primary_lane_desync",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_sequencer_block,
    "primary_sequencer_block",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_operand_request_blocked,
    "primary_operand_request_blocked",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_other_dispatch_blocked,
    "primary_other_dispatch_blocked",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );
  update_top2(
    g_primary_dispatch_unattributed,
    "primary_dispatch_unattributed",
    top_global_dispatch_reason_count, top_global_dispatch_reason,
    second_global_dispatch_reason_count, second_global_dispatch_reason
  );

  update_top2(
    g_primary_result_backpressure,
    "primary_result_backpressure",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );
  update_top2(
    g_primary_result_queue_full,
    "primary_result_queue_full",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );
  update_top2(
    g_primary_latency_order_stall,
    "primary_latency_order_stall",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );
  update_top2(
    g_primary_unit_input_backpressure,
    "primary_unit_input_backpressure",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );
  update_top2(
    g_primary_operand_wait,
    "primary_operand_wait",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );
  update_top2(
    g_primary_long_latency_busy,
    "primary_long_latency_busy",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );
  update_top2(
    g_primary_special_path,
    "primary_special_path",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );
  update_top2(
    g_primary_progress,
    "primary_progress",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );
  update_top2(
    g_primary_unattributed,
    "primary_unattributed",
    top_global_exec_reason_count, top_global_exec_reason,
    second_global_exec_reason_count, second_global_exec_reason
  );

  top_global_dispatch_gap =
    (top_global_dispatch_reason_count >= second_global_dispatch_reason_count) ?
      (top_global_dispatch_reason_count - second_global_dispatch_reason_count) : '0;
  top_global_dispatch_gap_ratio_request =
    perf_ratio(top_global_dispatch_gap, total_dispatch_request);
  top_global_dispatch_dominance_ratio =
    perf_ratio(top_global_dispatch_reason_count, total_dispatch_blocked);
  second_global_dispatch_dominance_ratio =
    perf_ratio(second_global_dispatch_reason_count, total_dispatch_blocked);

  top_global_exec_reason_gap =
    (top_global_exec_reason_count >= second_global_exec_reason_count) ?
      (top_global_exec_reason_count - second_global_exec_reason_count) : '0;
  top_global_exec_reason_gap_ratio_exec_active =
    perf_ratio(top_global_exec_reason_gap, total_exec_active);
  top_global_exec_dominance_ratio =
    perf_ratio(top_global_exec_reason_count, total_exec_primary_reason_cycles);
  second_global_exec_dominance_ratio =
    perf_ratio(second_global_exec_reason_count, total_exec_primary_reason_cycles);

  global_dispatch_blocked_ratio = perf_ratio(total_dispatch_blocked, total_dispatch_request);
  global_issue_progress_ratio = perf_ratio(total_issue_progress, total_exec_active);
  global_no_issue_progress_ratio = perf_ratio(total_no_issue_progress, total_exec_active);
  top_class_dispatch_request_share = perf_ratio(top_class_dispatch_request_count, total_dispatch_request);
  top_class_active_share = perf_ratio(top_class_active_count, total_exec_active);
  top_class_share_skew =
    (top_class_dispatch_request_share >= top_class_active_share) ?
      (top_class_dispatch_request_share - top_class_active_share) :
      (top_class_active_share - top_class_dispatch_request_share);
  top_opcode_dispatch_request_share = perf_ratio(top_opcode_dispatch_request_count, total_dispatch_request);
  top_opcode_active_share = perf_ratio(top_opcode_active_count, total_exec_active);
  top_opcode_share_skew =
    (top_opcode_dispatch_request_share >= top_opcode_active_share) ?
      (top_opcode_dispatch_request_share - top_opcode_active_share) :
      (top_opcode_active_share - top_opcode_dispatch_request_share);

  if (global_dispatch_blocked_ratio >= 0.45) begin
    global_stage_mode = "dispatch_bound";
  end else if (global_no_issue_progress_ratio >= 0.45) begin
    global_stage_mode = "execution_progress_bound";
  end else if ((global_dispatch_blocked_ratio + global_no_issue_progress_ratio) >= 0.45) begin
    global_stage_mode = "mixed_dispatch_exec_stress";
  end else if (total_exec_active == '0) begin
    global_stage_mode = "inactive_or_no_exec_activity";
  end else begin
    global_stage_mode = "moderate_progress";
  end

  if ((top_global_dispatch_dominance_ratio >= 0.30) &&
      (global_dispatch_blocked_ratio >= 0.20)) begin
    global_bottleneck_focus = "dispatch_front_pressure";
  end else if ((top_global_exec_dominance_ratio >= 0.30) &&
               (global_no_issue_progress_ratio >= global_issue_progress_ratio)) begin
    global_bottleneck_focus = "execution_wait_bound";
  end else begin
    global_bottleneck_focus = "balanced_multi_factor";
  end

  if (top_class_dispatch_request_name != top_class_active_name) begin
    global_bottleneck_secondary_hint =
      "dispatch-heavy class does not match execution-heavy class; check distribution/shape shift";
  end else if (top_class_share_skew > 0.25) begin
    global_bottleneck_secondary_hint =
      "top class share differs strongly between request and active; verify frontier of workload mix";
  end else if (top_opcode_share_skew > 0.35) begin
    global_bottleneck_secondary_hint =
      "top opcode dominates request but not active share; check front-end enqueue/dispatch scheduling";
  end else begin
    global_bottleneck_secondary_hint = "class/op distribution is largely aligned";
  end

  for (int unsigned op = 0; op < NrAraOps; op++) begin
    if (frontend.arch_opcode_count[op] != '0 || stats.opcode_dispatch_request_cycle[op] != '0 ||
        stats.opcode_active_cycle[op] != '0) begin
      automatic ara_op_e op_e;
      automatic string op_name;
      automatic logic [63:0] class_exec_wait_candidate;
      op_e = ara_op_e'(op);
      op_name = op_e.name();
      op_dispatch_blocked = stats.opcode_dispatch_blocked_cycle[op];
      op_dispatch_request = stats.opcode_dispatch_request_cycle[op];
      op_active = stats.opcode_active_cycle[op];
      op_completed = stats.opcode_completed_count[op];
      update_top2(
        op_dispatch_request,
        op_name,
        top_opcode_dispatch_request_count, top_opcode_dispatch_request_name,
        second_opcode_dispatch_request_count, second_opcode_dispatch_request_name
      );
      update_top2(
        op_active,
        op_name,
        top_opcode_active_count, top_opcode_active_name,
        second_opcode_active_count, second_opcode_active_name
      );
      update_top2(
        op_completed,
        op_name,
        top_opcode_completed_count, top_opcode_completed_name,
        second_opcode_completed_count, second_opcode_completed_name
      );
      class_exec_wait_candidate = stats.opcode_primary_result_backpressure_cycle[op] +
                                 stats.opcode_primary_result_queue_full_cycle[op] +
                                 stats.opcode_primary_latency_order_stall_cycle[op] +
                                 stats.opcode_primary_unit_input_backpressure_cycle[op] +
                                 stats.opcode_primary_operand_wait_cycle[op] +
                                 stats.opcode_primary_long_latency_busy_cycle[op] +
                                 stats.opcode_primary_special_path_cycle[op] +
                                 stats.opcode_primary_unattributed_cycle[op];
      op_exec_wait = class_exec_wait_candidate;
      op_dispatch_blocked_hist[op] = op_dispatch_blocked;
      op_exec_wait_hist[op] = op_exec_wait;
      update_top2(
        op_dispatch_blocked,
        op_name,
        top_opcode_dispatch_blocked_count, top_opcode_dispatch_blocked_name,
        second_opcode_dispatch_blocked_count, second_opcode_dispatch_blocked_name
      );
      update_top2(
        op_exec_wait,
        op_name,
        top_opcode_exec_wait_count, top_opcode_exec_wait_name,
        second_opcode_exec_wait_count, second_opcode_exec_wait_name
      );
    end
  end

  for (int unsigned c = 0; c < NrExecClasses; c++) begin
    real class_dispatch_share;
    real class_exec_wait_share;
    class_dispatch_share = perf_ratio(class_dispatch_blocked_hist[c], total_dispatch_blocked);
    class_exec_wait_share = perf_ratio(class_exec_wait_hist[c], total_exec_wait);
    global_dispatch_exec_class_overlap +=
      (class_dispatch_share < class_exec_wait_share) ? class_dispatch_share : class_exec_wait_share;
  end

  for (int unsigned op = 0; op < NrAraOps; op++) begin
    real op_dispatch_share;
    real op_exec_wait_share;
    op_dispatch_share = perf_ratio(op_dispatch_blocked_hist[op], total_dispatch_blocked);
    op_exec_wait_share = perf_ratio(op_exec_wait_hist[op], total_exec_wait);
    global_dispatch_exec_opcode_overlap +=
      (op_dispatch_share < op_exec_wait_share) ? op_dispatch_share : op_exec_wait_share;
  end

  global_top2_dispatch_request_share =
    perf_ratio(top_class_dispatch_request_count + second_class_dispatch_request_count, total_dispatch_request);
  global_top2_active_share =
    perf_ratio(top_class_active_count + second_class_active_count, total_exec_active);
  global_top2_dispatch_blocked_share =
    perf_ratio(top_class_dispatch_blocked_count + second_class_dispatch_blocked_count, total_dispatch_blocked);
  global_top2_exec_wait_share =
    perf_ratio(top_class_exec_wait_count + second_class_exec_wait_count, total_exec_wait);
  global_top2_dispatch_bottleneck_share =
    perf_ratio(top_global_dispatch_reason_count + second_global_dispatch_reason_count, total_dispatch_blocked);
  global_top2_exec_bottleneck_share =
    perf_ratio(top_global_exec_reason_count + second_global_exec_reason_count, total_exec_primary_reason_cycles);

  if ((top_class_dispatch_blocked_name == top_class_exec_wait_name) &&
      (top_class_dispatch_blocked_count != '0)) begin
    global_bottleneck_pressure_alignment = "aligned";
  end else if ((top_class_dispatch_blocked_count == '0) && (total_dispatch_blocked == '0)) begin
    global_bottleneck_pressure_alignment = "no_dispatch_stall";
  end else begin
    global_bottleneck_pressure_alignment = "misaligned";
  end

  if ((top_opcode_dispatch_blocked_name == top_opcode_exec_wait_name) &&
      (top_opcode_dispatch_blocked_count != '0)) begin
    global_bottleneck_opcode_alignment = "aligned";
  end else if ((top_opcode_dispatch_blocked_count == '0) && (total_dispatch_blocked == '0)) begin
    global_bottleneck_opcode_alignment = "no_dispatch_stall";
  end else begin
    global_bottleneck_opcode_alignment = "misaligned";
  end

  if (file_handle == 0) begin
    $display("[PERF] ==== Global Bottleneck Priorities ====");
    $display("[PERF] global_total_dispatch_request_cycles: %0d", total_dispatch_request);
    $display("[PERF] global_total_dispatch_blocked_cycles: %0d", total_dispatch_blocked);
    $display("[PERF] global_dispatch_blocked_ratio: %0.6f", global_dispatch_blocked_ratio);
    $display("[PERF] global_total_exec_active_cycles: %0d", total_exec_active);
    $display("[PERF] global_exec_wait_cycles: %0d", total_exec_wait);
    $display("[PERF] global_total_issue_progress_cycles: %0d", total_issue_progress);
    $display("[PERF] global_total_no_issue_progress_cycles: %0d", total_no_issue_progress);
    $display("[PERF] global_issue_progress_ratio: %0.6f", global_issue_progress_ratio);
    $display("[PERF] global_no_issue_progress_ratio: %0.6f", global_no_issue_progress_ratio);
    $display("[PERF] global_exec_progress_partition_consistent: %0d",
      (total_issue_progress + total_no_issue_progress) == total_exec_active);
    $display("[PERF] global_exec_primary_reason_cycles: %0d", total_exec_primary_reason_cycles);
    $display("[PERF] global_primary_dispatch_partition_consistent: %0d",
      total_dispatch_primary_reason_cycles == total_dispatch_blocked);
    $display("[PERF] global_primary_exec_partition_consistent: %0d",
      total_exec_primary_reason_cycles == total_exec_active);
    $display("[PERF] global_stage_mode: %s", global_stage_mode);
    $display("[PERF] global_bottleneck_focus: %s", global_bottleneck_focus);
    $display("[PERF] global_bottleneck_secondary_hint: %s", global_bottleneck_secondary_hint);
    $display("[PERF] global_top_class_request_share: %0.6f", top_class_dispatch_request_share);
    $display("[PERF] global_top_class_active_share: %0.6f", top_class_active_share);
    $display("[PERF] global_top_class_share_skew: %0.6f", top_class_share_skew);
    $display("[PERF] global_dispatch_exec_class_overlap: %0.6f", global_dispatch_exec_class_overlap);
    $display("[PERF] global_bottleneck_pressure_alignment: %s", global_bottleneck_pressure_alignment);
    $display("[PERF] global_top2_dispatch_request_share: %0.6f", global_top2_dispatch_request_share);
    $display("[PERF] global_top2_active_share: %0.6f", global_top2_active_share);
    $display("[PERF] global_top2_dispatch_blocked_share: %0.6f", global_top2_dispatch_blocked_share);
    $display("[PERF] global_top2_exec_wait_share: %0.6f", global_top2_exec_wait_share);
    $display("[PERF] global_top2_dispatch_bottleneck_share: %0.6f", global_top2_dispatch_bottleneck_share);
    $display("[PERF] global_top2_exec_bottleneck_share: %0.6f", global_top2_exec_bottleneck_share);
    $display("[PERF] global_top_opcode_request_share: %0.6f", top_opcode_dispatch_request_share);
    $display("[PERF] global_top_opcode_active_share: %0.6f", top_opcode_active_share);
    $display("[PERF] global_top_opcode_share_skew: %0.6f", top_opcode_share_skew);
    $display("[PERF] global_dispatch_exec_opcode_overlap: %0.6f", global_dispatch_exec_opcode_overlap);
    $display("[PERF] global_bottleneck_opcode_alignment: %s", global_bottleneck_opcode_alignment);
    $display("[PERF] global_top_dispatch_request_class: %s", top_class_dispatch_request_name);
    $display("[PERF] global_top_dispatch_request_class_cycles: %0d", top_class_dispatch_request_count);
    $display("[PERF] global_top_dispatch_request_class_ratio_request: %0.6f",
      perf_ratio(top_class_dispatch_request_count, total_dispatch_request));
    $display("[PERF] global_top_dispatch_request_class_ratio_active: %0.6f",
      perf_ratio(top_class_dispatch_request_count, total_exec_active));
    $display("[PERF] global_top_active_class: %s", top_class_active_name);
    $display("[PERF] global_top_active_class_cycles: %0d", top_class_active_count);
    $display("[PERF] global_top_active_class_ratio_active: %0.6f",
      perf_ratio(top_class_active_count, total_exec_active));
    $display("[PERF] global_top_completed_class: %s", top_class_completed_name);
    $display("[PERF] global_top_completed_class_cycles: %0d", top_class_completed_count);
    $display("[PERF] global_top_completed_class_ratio_active: %0.6f",
      perf_ratio(top_class_completed_count, total_exec_active));
    $display("[PERF] global_second_dispatch_request_class: %s", second_class_dispatch_request_name);
    $display("[PERF] global_second_dispatch_request_class_cycles: %0d",
      second_class_dispatch_request_count);
    $display("[PERF] global_second_active_class: %s", second_class_active_name);
    $display("[PERF] global_second_active_class_cycles: %0d", second_class_active_count);
    $display("[PERF] global_second_completed_class: %s", second_class_completed_name);
    $display("[PERF] global_second_completed_class_cycles: %0d", second_class_completed_count);
    $display("[PERF] global_top_dispatch_request_opcode: %s", top_opcode_dispatch_request_name);
    $display("[PERF] global_top_dispatch_request_opcode_cycles: %0d",
      top_opcode_dispatch_request_count);
    $display("[PERF] global_top_dispatch_request_opcode_ratio_request: %0.6f",
      perf_ratio(top_opcode_dispatch_request_count, total_dispatch_request));
    $display("[PERF] global_top_active_opcode: %s", top_opcode_active_name);
    $display("[PERF] global_top_active_opcode_cycles: %0d", top_opcode_active_count);
    $display("[PERF] global_top_active_opcode_ratio_active: %0.6f",
      perf_ratio(top_opcode_active_count, total_exec_active));
    $display("[PERF] global_top_completed_opcode: %s", top_opcode_completed_name);
    $display("[PERF] global_top_completed_opcode_cycles: %0d", top_opcode_completed_count);
    $display("[PERF] global_top_completed_opcode_ratio_active: %0.6f",
      perf_ratio(top_opcode_completed_count, total_exec_active));
    $display("[PERF] global_second_dispatch_request_opcode: %s", second_opcode_dispatch_request_name);
    $display("[PERF] global_second_dispatch_request_opcode_cycles: %0d",
      second_opcode_dispatch_request_count);
    $display("[PERF] global_second_active_opcode: %s", second_opcode_active_name);
    $display("[PERF] global_second_active_opcode_cycles: %0d", second_opcode_active_count);
    $display("[PERF] global_second_completed_opcode: %s", second_opcode_completed_name);
    $display("[PERF] global_second_completed_opcode_cycles: %0d",
      second_opcode_completed_count);
    $display("[PERF] global_top_primary_dispatch_bottleneck_reason: %s", top_global_dispatch_reason);
    $display("[PERF] global_top_secondary_dispatch_bottleneck_reason: %s", second_global_dispatch_reason);
    $display("[PERF] global_top_dispatch_bottleneck_reason_gap_cycles: %0d", top_global_dispatch_gap);
    $display("[PERF] global_top_dispatch_bottleneck_gap_ratio_dispatch_request: %0.6f",
      top_global_dispatch_gap_ratio_request);
    $display("[PERF] global_top_dispatch_bottleneck_dominance_ratio: %0.6f",
      top_global_dispatch_dominance_ratio);
    $display("[PERF] global_second_dispatch_bottleneck_dominance_ratio: %0.6f",
      second_global_dispatch_dominance_ratio);
    $display("[PERF] global_top_dispatch_bottleneck_reason_cycles: %0d", top_global_dispatch_reason_count);
    $display("[PERF] global_top_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f",
      perf_ratio(top_global_dispatch_reason_count, total_dispatch_blocked));
    $display("[PERF] global_top_primary_dispatch_bottleneck_advice: %s",
      dispatch_bottleneck_advice(top_global_dispatch_reason));

    $display("[PERF] global_top_dispatch_blocked_class: %s", top_class_dispatch_blocked_name);
    $display("[PERF] global_top_dispatch_blocked_class_cycles: %0d", top_class_dispatch_blocked_count);
    $display("[PERF] global_top_dispatch_blocked_class_ratio: %0.6f",
      perf_ratio(top_class_dispatch_blocked_count, total_dispatch_blocked));
    $display("[PERF] global_second_dispatch_blocked_class: %s", second_class_dispatch_blocked_name);
    $display("[PERF] global_second_dispatch_blocked_class_cycles: %0d",
      second_class_dispatch_blocked_count);
    $display("[PERF] global_top_dispatch_blocked_opcode: %s", top_opcode_dispatch_blocked_name);
    $display("[PERF] global_top_dispatch_blocked_opcode_cycles: %0d", top_opcode_dispatch_blocked_count);
    $display("[PERF] global_top_dispatch_blocked_opcode_ratio_dispatch_request: %0.6f",
      perf_ratio(top_opcode_dispatch_blocked_count, total_dispatch_request));
    $display("[PERF] global_top_dispatch_blocked_opcode_ratio_dispatch_blocked: %0.6f",
      perf_ratio(top_opcode_dispatch_blocked_count, total_dispatch_blocked));
    $display("[PERF] global_second_dispatch_blocked_opcode: %s", second_opcode_dispatch_blocked_name);
    $display("[PERF] global_second_dispatch_blocked_opcode_cycles: %0d",
      second_opcode_dispatch_blocked_count);

    $display("[PERF] global_top_primary_exec_bottleneck_reason: %s", top_global_exec_reason);
    $display("[PERF] global_top_secondary_exec_bottleneck_reason: %s", second_global_exec_reason);
    $display("[PERF] global_top_exec_bottleneck_reason_gap_cycles: %0d", top_global_exec_reason_gap);
    $display("[PERF] global_top_exec_bottleneck_gap_ratio_exec_active: %0.6f",
      top_global_exec_reason_gap_ratio_exec_active);
    $display("[PERF] global_top_exec_bottleneck_dominance_ratio: %0.6f",
      top_global_exec_dominance_ratio);
    $display("[PERF] global_second_exec_bottleneck_dominance_ratio: %0.6f",
      second_global_exec_dominance_ratio);
    $display("[PERF] global_top_exec_bottleneck_reason_cycles: %0d", top_global_exec_reason_count);
    $display("[PERF] global_top_exec_bottleneck_ratio_exec_active: %0.6f",
      perf_ratio(top_global_exec_reason_count, total_exec_active));
    $display("[PERF] global_top_primary_exec_bottleneck_advice: %s",
      exec_bottleneck_advice(top_global_exec_reason));

    $display("[PERF] global_top_exec_wait_class: %s", top_class_exec_wait_name);
    $display("[PERF] global_top_exec_wait_class_cycles: %0d", top_class_exec_wait_count);
    $display("[PERF] global_top_exec_wait_class_ratio_wait: %0.6f",
      perf_ratio(top_class_exec_wait_count, total_exec_wait));
    $display("[PERF] global_second_exec_wait_class: %s", second_class_exec_wait_name);
    $display("[PERF] global_second_exec_wait_class_cycles: %0d", second_class_exec_wait_count);
    $display("[PERF] global_top_exec_wait_opcode: %s", top_opcode_exec_wait_name);
    $display("[PERF] global_top_exec_wait_opcode_cycles: %0d", top_opcode_exec_wait_count);
    $display("[PERF] global_top_exec_wait_opcode_ratio_exec_active: %0.6f",
      perf_ratio(top_opcode_exec_wait_count, total_exec_active));
    $display("[PERF] global_top_exec_wait_opcode_ratio_wait: %0.6f",
      perf_ratio(top_opcode_exec_wait_count, total_exec_wait));
    $display("[PERF] global_second_exec_wait_opcode: %s", second_opcode_exec_wait_name);
    $display("[PERF] global_second_exec_wait_opcode_cycles: %0d", second_opcode_exec_wait_count);
    $display("[PERF] global_top_exec_wait_opcode_advice: %s",
      exec_bottleneck_advice(top_global_exec_reason));
  end else begin
    $fwrite(file_handle, "[PERF] ==== Global Bottleneck Priorities ====\n");
    $fwrite(file_handle, "[PERF] global_total_dispatch_request_cycles: %0d\n", total_dispatch_request);
    $fwrite(file_handle, "[PERF] global_total_dispatch_blocked_cycles: %0d\n", total_dispatch_blocked);
    $fwrite(file_handle, "[PERF] global_dispatch_blocked_ratio: %0.6f\n",
      global_dispatch_blocked_ratio);
    $fwrite(file_handle, "[PERF] global_total_exec_active_cycles: %0d\n", total_exec_active);
    $fwrite(file_handle, "[PERF] global_exec_wait_cycles: %0d\n", total_exec_wait);
    $fwrite(file_handle, "[PERF] global_total_issue_progress_cycles: %0d\n", total_issue_progress);
    $fwrite(file_handle, "[PERF] global_total_no_issue_progress_cycles: %0d\n", total_no_issue_progress);
    $fwrite(file_handle, "[PERF] global_issue_progress_ratio: %0.6f\n", global_issue_progress_ratio);
    $fwrite(file_handle, "[PERF] global_no_issue_progress_ratio: %0.6f\n", global_no_issue_progress_ratio);
    $fwrite(file_handle, "[PERF] global_exec_progress_partition_consistent: %0d\n",
      (total_issue_progress + total_no_issue_progress) == total_exec_active);
    $fwrite(file_handle, "[PERF] global_exec_primary_reason_cycles: %0d\n", total_exec_primary_reason_cycles);
    $fwrite(file_handle, "[PERF] global_primary_dispatch_partition_consistent: %0d\n",
      total_dispatch_primary_reason_cycles == total_dispatch_blocked);
    $fwrite(file_handle, "[PERF] global_primary_exec_partition_consistent: %0d\n",
      total_exec_primary_reason_cycles == total_exec_active);
    $fwrite(file_handle, "[PERF] global_stage_mode: %s\n", global_stage_mode);
    $fwrite(file_handle, "[PERF] global_bottleneck_focus: %s\n", global_bottleneck_focus);
    $fwrite(file_handle, "[PERF] global_bottleneck_secondary_hint: %s\n",
      global_bottleneck_secondary_hint);
    $fwrite(file_handle, "[PERF] global_top_class_request_share: %0.6f\n",
      top_class_dispatch_request_share);
    $fwrite(file_handle, "[PERF] global_top_class_active_share: %0.6f\n",
      top_class_active_share);
    $fwrite(file_handle, "[PERF] global_top_class_share_skew: %0.6f\n", top_class_share_skew);
    $fwrite(file_handle, "[PERF] global_dispatch_exec_class_overlap: %0.6f\n",
      global_dispatch_exec_class_overlap);
    $fwrite(file_handle, "[PERF] global_bottleneck_pressure_alignment: %0s\n",
      global_bottleneck_pressure_alignment);
    $fwrite(file_handle, "[PERF] global_top2_dispatch_request_share: %0.6f\n",
      global_top2_dispatch_request_share);
    $fwrite(file_handle, "[PERF] global_top2_active_share: %0.6f\n",
      global_top2_active_share);
    $fwrite(file_handle, "[PERF] global_top2_dispatch_blocked_share: %0.6f\n",
      global_top2_dispatch_blocked_share);
    $fwrite(file_handle, "[PERF] global_top2_exec_wait_share: %0.6f\n",
      global_top2_exec_wait_share);
    $fwrite(file_handle, "[PERF] global_top2_dispatch_bottleneck_share: %0.6f\n",
      global_top2_dispatch_bottleneck_share);
    $fwrite(file_handle, "[PERF] global_top2_exec_bottleneck_share: %0.6f\n",
      global_top2_exec_bottleneck_share);
    $fwrite(file_handle, "[PERF] global_top_opcode_request_share: %0.6f\n",
      top_opcode_dispatch_request_share);
    $fwrite(file_handle, "[PERF] global_top_opcode_active_share: %0.6f\n",
      top_opcode_active_share);
    $fwrite(file_handle, "[PERF] global_top_opcode_share_skew: %0.6f\n", top_opcode_share_skew);
    $fwrite(file_handle, "[PERF] global_dispatch_exec_opcode_overlap: %0.6f\n",
      global_dispatch_exec_opcode_overlap);
    $fwrite(file_handle, "[PERF] global_bottleneck_opcode_alignment: %0s\n",
      global_bottleneck_opcode_alignment);
    $fwrite(file_handle, "[PERF] global_top_dispatch_request_class: %s\n", top_class_dispatch_request_name);
    $fwrite(file_handle, "[PERF] global_top_dispatch_request_class_cycles: %0d\n",
      top_class_dispatch_request_count);
    $fwrite(file_handle, "[PERF] global_top_dispatch_request_class_ratio_request: %0.6f\n",
      perf_ratio(top_class_dispatch_request_count, total_dispatch_request));
    $fwrite(file_handle, "[PERF] global_top_dispatch_request_class_ratio_active: %0.6f\n",
      perf_ratio(top_class_dispatch_request_count, total_exec_active));
    $fwrite(file_handle, "[PERF] global_top_active_class: %s\n", top_class_active_name);
    $fwrite(file_handle, "[PERF] global_top_active_class_cycles: %0d\n", top_class_active_count);
    $fwrite(file_handle, "[PERF] global_top_active_class_ratio_active: %0.6f\n",
      perf_ratio(top_class_active_count, total_exec_active));
    $fwrite(file_handle, "[PERF] global_top_completed_class: %s\n", top_class_completed_name);
    $fwrite(file_handle, "[PERF] global_top_completed_class_cycles: %0d\n", top_class_completed_count);
    $fwrite(file_handle, "[PERF] global_top_completed_class_ratio_active: %0.6f\n",
      perf_ratio(top_class_completed_count, total_exec_active));
    $fwrite(file_handle, "[PERF] global_second_dispatch_request_class: %s\n",
      second_class_dispatch_request_name);
    $fwrite(file_handle, "[PERF] global_second_dispatch_request_class_cycles: %0d\n",
      second_class_dispatch_request_count);
    $fwrite(file_handle, "[PERF] global_second_active_class: %s\n", second_class_active_name);
    $fwrite(file_handle, "[PERF] global_second_active_class_cycles: %0d\n", second_class_active_count);
    $fwrite(file_handle, "[PERF] global_second_completed_class: %s\n", second_class_completed_name);
    $fwrite(file_handle, "[PERF] global_second_completed_class_cycles: %0d\n", second_class_completed_count);
    $fwrite(file_handle, "[PERF] global_top_dispatch_request_opcode: %s\n", top_opcode_dispatch_request_name);
    $fwrite(file_handle, "[PERF] global_top_dispatch_request_opcode_cycles: %0d\n",
      top_opcode_dispatch_request_count);
    $fwrite(file_handle, "[PERF] global_top_dispatch_request_opcode_ratio_request: %0.6f\n",
      perf_ratio(top_opcode_dispatch_request_count, total_dispatch_request));
    $fwrite(file_handle, "[PERF] global_top_active_opcode: %s\n", top_opcode_active_name);
    $fwrite(file_handle, "[PERF] global_top_active_opcode_cycles: %0d\n", top_opcode_active_count);
    $fwrite(file_handle, "[PERF] global_top_active_opcode_ratio_active: %0.6f\n",
      perf_ratio(top_opcode_active_count, total_exec_active));
    $fwrite(file_handle, "[PERF] global_top_completed_opcode: %s\n", top_opcode_completed_name);
    $fwrite(file_handle, "[PERF] global_top_completed_opcode_cycles: %0d\n", top_opcode_completed_count);
    $fwrite(file_handle, "[PERF] global_top_completed_opcode_ratio_active: %0.6f\n",
      perf_ratio(top_opcode_completed_count, total_exec_active));
    $fwrite(file_handle, "[PERF] global_second_dispatch_request_opcode: %s\n",
      second_opcode_dispatch_request_name);
    $fwrite(file_handle, "[PERF] global_second_dispatch_request_opcode_cycles: %0d\n",
      second_opcode_dispatch_request_count);
    $fwrite(file_handle, "[PERF] global_second_active_opcode: %s\n", second_opcode_active_name);
    $fwrite(file_handle, "[PERF] global_second_active_opcode_cycles: %0d\n", second_opcode_active_count);
    $fwrite(file_handle, "[PERF] global_second_completed_opcode: %s\n", second_opcode_completed_name);
    $fwrite(file_handle, "[PERF] global_second_completed_opcode_cycles: %0d\n",
      second_opcode_completed_count);
    $fwrite(file_handle, "[PERF] global_top_primary_dispatch_bottleneck_reason: %s\n",
      top_global_dispatch_reason);
    $fwrite(file_handle, "[PERF] global_top_secondary_dispatch_bottleneck_reason: %s\n",
      second_global_dispatch_reason);
    $fwrite(file_handle, "[PERF] global_top_dispatch_bottleneck_reason_gap_cycles: %0d\n",
      top_global_dispatch_gap);
    $fwrite(file_handle, "[PERF] global_top_dispatch_bottleneck_gap_ratio_dispatch_request: %0.6f\n",
      top_global_dispatch_gap_ratio_request);
    $fwrite(file_handle, "[PERF] global_top_dispatch_bottleneck_dominance_ratio: %0.6f\n",
      top_global_dispatch_dominance_ratio);
    $fwrite(file_handle, "[PERF] global_second_dispatch_bottleneck_dominance_ratio: %0.6f\n",
      second_global_dispatch_dominance_ratio);
    $fwrite(file_handle, "[PERF] global_top_dispatch_bottleneck_reason_cycles: %0d\n",
      top_global_dispatch_reason_count);
    $fwrite(file_handle, "[PERF] global_top_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f\n",
      perf_ratio(top_global_dispatch_reason_count, total_dispatch_blocked));
    $fwrite(file_handle, "[PERF] global_top_primary_dispatch_bottleneck_advice: %s\n",
      dispatch_bottleneck_advice(top_global_dispatch_reason));

    $fwrite(file_handle, "[PERF] global_top_dispatch_blocked_class: %s\n",
      top_class_dispatch_blocked_name);
    $fwrite(file_handle, "[PERF] global_top_dispatch_blocked_class_cycles: %0d\n",
      top_class_dispatch_blocked_count);
    $fwrite(file_handle, "[PERF] global_top_dispatch_blocked_class_ratio: %0.6f\n",
      perf_ratio(top_class_dispatch_blocked_count, total_dispatch_blocked));
    $fwrite(file_handle, "[PERF] global_second_dispatch_blocked_class: %s\n",
      second_class_dispatch_blocked_name);
    $fwrite(file_handle, "[PERF] global_second_dispatch_blocked_class_cycles: %0d\n",
      second_class_dispatch_blocked_count);
    $fwrite(file_handle, "[PERF] global_top_dispatch_blocked_opcode: %s\n",
      top_opcode_dispatch_blocked_name);
    $fwrite(file_handle, "[PERF] global_top_dispatch_blocked_opcode_cycles: %0d\n",
      top_opcode_dispatch_blocked_count);
    $fwrite(file_handle, "[PERF] global_top_dispatch_blocked_opcode_ratio_dispatch_request: %0.6f\n",
      perf_ratio(top_opcode_dispatch_blocked_count, total_dispatch_request));
    $fwrite(file_handle, "[PERF] global_top_dispatch_blocked_opcode_ratio_dispatch_blocked: %0.6f\n",
      perf_ratio(top_opcode_dispatch_blocked_count, total_dispatch_blocked));
    $fwrite(file_handle, "[PERF] global_second_dispatch_blocked_opcode: %s\n",
      second_opcode_dispatch_blocked_name);
    $fwrite(file_handle, "[PERF] global_second_dispatch_blocked_opcode_cycles: %0d\n",
      second_opcode_dispatch_blocked_count);

    $fwrite(file_handle, "[PERF] global_top_primary_exec_bottleneck_reason: %s\n",
      top_global_exec_reason);
    $fwrite(file_handle, "[PERF] global_top_secondary_exec_bottleneck_reason: %s\n",
      second_global_exec_reason);
    $fwrite(file_handle, "[PERF] global_top_exec_bottleneck_reason_gap_cycles: %0d\n",
      top_global_exec_reason_gap);
    $fwrite(file_handle, "[PERF] global_top_exec_bottleneck_gap_ratio_exec_active: %0.6f\n",
      top_global_exec_reason_gap_ratio_exec_active);
    $fwrite(file_handle, "[PERF] global_top_exec_bottleneck_dominance_ratio: %0.6f\n",
      top_global_exec_dominance_ratio);
    $fwrite(file_handle, "[PERF] global_second_exec_bottleneck_dominance_ratio: %0.6f\n",
      second_global_exec_dominance_ratio);
    $fwrite(file_handle, "[PERF] global_top_exec_bottleneck_reason_cycles: %0d\n",
      top_global_exec_reason_count);
    $fwrite(file_handle, "[PERF] global_top_exec_bottleneck_ratio_exec_active: %0.6f\n",
      perf_ratio(top_global_exec_reason_count, total_exec_active));
    $fwrite(file_handle, "[PERF] global_top_primary_exec_bottleneck_advice: %s\n",
      exec_bottleneck_advice(top_global_exec_reason));

    $fwrite(file_handle, "[PERF] global_top_exec_wait_class: %s\n", top_class_exec_wait_name);
    $fwrite(file_handle, "[PERF] global_top_exec_wait_class_cycles: %0d\n",
      top_class_exec_wait_count);
    $fwrite(file_handle, "[PERF] global_top_exec_wait_class_ratio_wait: %0.6f\n",
      perf_ratio(top_class_exec_wait_count, total_exec_wait));
    $fwrite(file_handle, "[PERF] global_second_exec_wait_class: %s\n", second_class_exec_wait_name);
    $fwrite(file_handle, "[PERF] global_second_exec_wait_class_cycles: %0d\n",
      second_class_exec_wait_count);
    $fwrite(file_handle, "[PERF] global_top_exec_wait_opcode: %s\n", top_opcode_exec_wait_name);
    $fwrite(file_handle, "[PERF] global_top_exec_wait_opcode_cycles: %0d\n",
      top_opcode_exec_wait_count);
    $fwrite(file_handle, "[PERF] global_top_exec_wait_opcode_ratio_exec_active: %0.6f\n",
      perf_ratio(top_opcode_exec_wait_count, total_exec_active));
    $fwrite(file_handle, "[PERF] global_top_exec_wait_opcode_ratio_wait: %0.6f\n",
      perf_ratio(top_opcode_exec_wait_count, total_exec_wait));
    $fwrite(file_handle, "[PERF] global_second_exec_wait_opcode: %s\n",
      second_opcode_exec_wait_name);
    $fwrite(file_handle, "[PERF] global_second_exec_wait_opcode_cycles: %0d\n",
      second_opcode_exec_wait_count);
    $fwrite(file_handle, "[PERF] global_top_exec_wait_opcode_advice: %s\n",
      exec_bottleneck_advice(top_global_exec_reason));
  end
endtask

function automatic string exec_bottleneck_advice(input string reason);
  case (reason)
    "primary_result_backpressure":     return "inspect result consumer readiness, result path backpressure, and completion fan-out";
    "primary_result_queue_full":       return "increase result queue depth or drain logic throughput, then recheck queue-full frequency";
    "primary_latency_order_stall":     return "reduce critical dependency chains and wakeup latency in the scheduler";
    "primary_unit_input_backpressure": return "raise unit issue bandwidth or reduce operand fan-in pressure";
    "primary_operand_wait":            return "check operand forwarding latency and load data readiness";
    "primary_long_latency_busy":       return "profile long-latency units; consider deeper pipelines or more instances";
    "primary_special_path":            return "investigate special-path instructions (reductions/reduction-like control flow), optimize their microcode";
    "primary_progress":                return "progress dominates while not completing quickly; investigate completion latency and drain behavior";
    "primary_unattributed":            return "noisy attribution overlap, add stronger exclusion categories or finer-grain counters";
    default:                           return "no single dominant execution bottleneck candidate identified";
  endcase
endfunction

function automatic string dispatch_bottleneck_advice(input string reason);
  case (reason)
    "primary_fu_queue_full":          return "dispatch cannot feed FUs fast enough; increase FU input bandwidth or reduce inflight pressure";
    "primary_mask_queue_full":        return "mask unit dispatch queue is full; optimize mask path occupancy and request batching";
    "primary_slide_queue_full":       return "SLDU dispatch queue bottleneck; tune slide queue depth or cross-lane balance";
    "primary_id_pool_full":           return "ID pool overflow; reduce live ID holding time or enlarge pool";
    "primary_response_wait":          return "sequencer response wait dominates; inspect pending response dependencies";
    "primary_lane_desync":            return "lane desynchronization causes dispatch stall; rebalance lane progress";
    "primary_sequencer_block":        return "sequencer global block detected; review hazard or reorder pressure";
    "primary_operand_request_blocked":return "operand requester blocked; reduce operand scoreboard contention";
    "primary_other_dispatch_blocked": return "other dispatch blockers dominate; inspect fallback stall reasons and control logic";
    default:                         return "no single dominant dispatch bottleneck candidate identified";
  endcase
endfunction

function automatic exec_perf_t exec_perf_delta(exec_perf_t end_count, exec_perf_t start_count);
  exec_perf_t delta;
  delta = '{default: '0};
  for (int unsigned c = 0; c < NrExecClasses; c++) begin
    delta.insn_count[c]                  = end_count.insn_count[c]                  - start_count.insn_count[c];
    delta.issued_count[c]                = end_count.issued_count[c]                - start_count.issued_count[c];
    delta.completed_count[c]             = end_count.completed_count[c]             - start_count.completed_count[c];
    delta.requested_element_count[c]     = end_count.requested_element_count[c]     - start_count.requested_element_count[c];
    delta.nominal_element_op_count[c]    = end_count.nominal_element_op_count[c]    - start_count.nominal_element_op_count[c];
    delta.masked_insn_count[c]           = end_count.masked_insn_count[c]           - start_count.masked_insn_count[c];
    delta.reduction_insn_count[c]        = end_count.reduction_insn_count[c]        - start_count.reduction_insn_count[c];
    delta.special_insn_count[c]          = end_count.special_insn_count[c]          - start_count.special_insn_count[c];
    delta.unit_stride_uop_count[c]       = end_count.unit_stride_uop_count[c]       - start_count.unit_stride_uop_count[c];
    delta.strided_uop_count[c]           = end_count.strided_uop_count[c]           - start_count.strided_uop_count[c];
    delta.indexed_uop_count[c]           = end_count.indexed_uop_count[c]           - start_count.indexed_uop_count[c];
    delta.segment_uop_count[c]           = end_count.segment_uop_count[c]           - start_count.segment_uop_count[c];
    delta.fault_only_first_uop_count[c]  = end_count.fault_only_first_uop_count[c]  - start_count.fault_only_first_uop_count[c];
    delta.requested_byte_count[c]        = end_count.requested_byte_count[c]        - start_count.requested_byte_count[c];
    delta.active_cycle[c]                = end_count.active_cycle[c]                - start_count.active_cycle[c];
    delta.inflight_insn_cycle[c]         = end_count.inflight_insn_cycle[c]         - start_count.inflight_insn_cycle[c];
    delta.masked_active_cycle[c]         = end_count.masked_active_cycle[c]         - start_count.masked_active_cycle[c];
    delta.dispatch_wait_cycle[c]         = end_count.dispatch_wait_cycle[c]         - start_count.dispatch_wait_cycle[c];
    delta.execution_latency_cycle[c]     = end_count.execution_latency_cycle[c]     - start_count.execution_latency_cycle[c];
    delta.end_to_end_latency_cycle[c]    = end_count.end_to_end_latency_cycle[c]    - start_count.end_to_end_latency_cycle[c];
    delta.dispatch_request_cycle[c]      = end_count.dispatch_request_cycle[c]      - start_count.dispatch_request_cycle[c];
    delta.dispatch_blocked_cycle[c]      = end_count.dispatch_blocked_cycle[c]      - start_count.dispatch_blocked_cycle[c];
    delta.fu_queue_full_cycle[c]         = end_count.fu_queue_full_cycle[c]         - start_count.fu_queue_full_cycle[c];
    delta.mask_queue_full_cycle[c]       = end_count.mask_queue_full_cycle[c]       - start_count.mask_queue_full_cycle[c];
    delta.slide_queue_full_cycle[c]      = end_count.slide_queue_full_cycle[c]      - start_count.slide_queue_full_cycle[c];
    delta.id_pool_full_cycle[c]          = end_count.id_pool_full_cycle[c]          - start_count.id_pool_full_cycle[c];
    delta.response_wait_cycle[c]         = end_count.response_wait_cycle[c]         - start_count.response_wait_cycle[c];
    delta.other_dispatch_blocked_cycle[c] = end_count.other_dispatch_blocked_cycle[c] - start_count.other_dispatch_blocked_cycle[c];
    delta.operand_request_blocked_cycle[c] = end_count.operand_request_blocked_cycle[c] - start_count.operand_request_blocked_cycle[c];
    delta.raw_hazard_cycle[c]            = end_count.raw_hazard_cycle[c]            - start_count.raw_hazard_cycle[c];
    delta.war_hazard_cycle[c]            = end_count.war_hazard_cycle[c]            - start_count.war_hazard_cycle[c];
    delta.waw_hazard_cycle[c]            = end_count.waw_hazard_cycle[c]            - start_count.waw_hazard_cycle[c];
    delta.false_hazard_cycle[c]          = end_count.false_hazard_cycle[c]          - start_count.false_hazard_cycle[c];
    delta.sequencer_block_cycle[c]       = end_count.sequencer_block_cycle[c]       - start_count.sequencer_block_cycle[c];
    delta.lane_desync_cycle[c]           = end_count.lane_desync_cycle[c]           - start_count.lane_desync_cycle[c];
    delta.issue_progress_cycle[c]        = end_count.issue_progress_cycle[c]        - start_count.issue_progress_cycle[c];
    delta.no_issue_progress_cycle[c]     = end_count.no_issue_progress_cycle[c]     - start_count.no_issue_progress_cycle[c];
    delta.operand_wait_cycle[c]          = end_count.operand_wait_cycle[c]          - start_count.operand_wait_cycle[c];
    delta.unit_input_backpressure_cycle[c] = end_count.unit_input_backpressure_cycle[c] - start_count.unit_input_backpressure_cycle[c];
    delta.latency_order_stall_cycle[c]   = end_count.latency_order_stall_cycle[c]   - start_count.latency_order_stall_cycle[c];
    delta.result_queue_full_cycle[c]     = end_count.result_queue_full_cycle[c]     - start_count.result_queue_full_cycle[c];
    delta.result_backpressure_cycle[c]   = end_count.result_backpressure_cycle[c]   - start_count.result_backpressure_cycle[c];
    delta.long_latency_busy_cycle[c]     = end_count.long_latency_busy_cycle[c]     - start_count.long_latency_busy_cycle[c];
    delta.reduction_cycle[c]             = end_count.reduction_cycle[c]             - start_count.reduction_cycle[c];
    delta.cross_lane_cycle[c]            = end_count.cross_lane_cycle[c]            - start_count.cross_lane_cycle[c];
    delta.special_path_cycle[c]          = end_count.special_path_cycle[c]          - start_count.special_path_cycle[c];
    delta.index_fifo_full_cycle[c]       = end_count.index_fifo_full_cycle[c]       - start_count.index_fifo_full_cycle[c];
    delta.mask_operand_incomplete_cycle[c] = end_count.mask_operand_incomplete_cycle[c] - start_count.mask_operand_incomplete_cycle[c];
    delta.mask_issue_end_cycle[c] = end_count.mask_issue_end_cycle[c] - start_count.mask_issue_end_cycle[c];
    delta.mask_commit_pending_cycle[c] = end_count.mask_commit_pending_cycle[c] - start_count.mask_commit_pending_cycle[c];
    delta.mask_result_queue_nonempty_cycle[c] = end_count.mask_result_queue_nonempty_cycle[c] - start_count.mask_result_queue_nonempty_cycle[c];
    delta.mask_final_grant_wait_cycle[c] = end_count.mask_final_grant_wait_cycle[c] - start_count.mask_final_grant_wait_cycle[c];
    delta.mask_index_fifo_nonempty_cycle[c] = end_count.mask_index_fifo_nonempty_cycle[c] - start_count.mask_index_fifo_nonempty_cycle[c];
    delta.mask_request_fifo_nonempty_cycle[c] = end_count.mask_request_fifo_nonempty_cycle[c] - start_count.mask_request_fifo_nonempty_cycle[c];
    delta.primary_result_backpressure_cycle[c] = end_count.primary_result_backpressure_cycle[c] - start_count.primary_result_backpressure_cycle[c];
    delta.primary_result_queue_full_cycle[c] = end_count.primary_result_queue_full_cycle[c] - start_count.primary_result_queue_full_cycle[c];
    delta.primary_latency_order_stall_cycle[c] = end_count.primary_latency_order_stall_cycle[c] - start_count.primary_latency_order_stall_cycle[c];
    delta.primary_unit_input_backpressure_cycle[c] = end_count.primary_unit_input_backpressure_cycle[c] - start_count.primary_unit_input_backpressure_cycle[c];
    delta.primary_operand_wait_cycle[c] = end_count.primary_operand_wait_cycle[c] - start_count.primary_operand_wait_cycle[c];
    delta.primary_long_latency_busy_cycle[c] = end_count.primary_long_latency_busy_cycle[c] - start_count.primary_long_latency_busy_cycle[c];
    delta.primary_special_path_cycle[c] = end_count.primary_special_path_cycle[c] - start_count.primary_special_path_cycle[c];
    delta.primary_progress_cycle[c] = end_count.primary_progress_cycle[c] - start_count.primary_progress_cycle[c];
    delta.primary_unattributed_cycle[c] = end_count.primary_unattributed_cycle[c] - start_count.primary_unattributed_cycle[c];
    delta.primary_fu_queue_full_cycle[c] = end_count.primary_fu_queue_full_cycle[c] -
      start_count.primary_fu_queue_full_cycle[c];
    delta.primary_mask_queue_full_cycle[c] = end_count.primary_mask_queue_full_cycle[c] -
      start_count.primary_mask_queue_full_cycle[c];
    delta.primary_slide_queue_full_cycle[c] = end_count.primary_slide_queue_full_cycle[c] -
      start_count.primary_slide_queue_full_cycle[c];
    delta.primary_id_pool_full_cycle[c] = end_count.primary_id_pool_full_cycle[c] -
      start_count.primary_id_pool_full_cycle[c];
    delta.primary_response_wait_cycle[c] = end_count.primary_response_wait_cycle[c] -
      start_count.primary_response_wait_cycle[c];
    delta.primary_lane_desync_cycle[c] = end_count.primary_lane_desync_cycle[c] -
      start_count.primary_lane_desync_cycle[c];
    delta.primary_sequencer_block_cycle[c] = end_count.primary_sequencer_block_cycle[c] -
      start_count.primary_sequencer_block_cycle[c];
    delta.primary_operand_request_blocked_cycle[c] = end_count.primary_operand_request_blocked_cycle[c] -
      start_count.primary_operand_request_blocked_cycle[c];
    delta.primary_other_dispatch_blocked_cycle[c] = end_count.primary_other_dispatch_blocked_cycle[c] -
      start_count.primary_other_dispatch_blocked_cycle[c];
    delta.primary_dispatch_unattributed_cycle[c] = end_count.primary_dispatch_unattributed_cycle[c] -
      start_count.primary_dispatch_unattributed_cycle[c];
    delta.issue_progress_lane_sample[c]  = end_count.issue_progress_lane_sample[c]  - start_count.issue_progress_lane_sample[c];
    delta.operand_wait_lane_sample[c]    = end_count.operand_wait_lane_sample[c]    - start_count.operand_wait_lane_sample[c];
    delta.unit_input_backpressure_lane_sample[c] = end_count.unit_input_backpressure_lane_sample[c] - start_count.unit_input_backpressure_lane_sample[c];
    delta.latency_order_stall_lane_sample[c] = end_count.latency_order_stall_lane_sample[c] - start_count.latency_order_stall_lane_sample[c];
    delta.result_queue_full_lane_sample[c] = end_count.result_queue_full_lane_sample[c] - start_count.result_queue_full_lane_sample[c];
    delta.result_backpressure_lane_sample[c] = end_count.result_backpressure_lane_sample[c] - start_count.result_backpressure_lane_sample[c];
    delta.long_latency_busy_lane_sample[c] = end_count.long_latency_busy_lane_sample[c] - start_count.long_latency_busy_lane_sample[c];
    delta.result_queue_occupancy_lane_sample[c] = end_count.result_queue_occupancy_lane_sample[c] - start_count.result_queue_occupancy_lane_sample[c];
    delta.predicate_packet_count[c] = end_count.predicate_packet_count[c] - start_count.predicate_packet_count[c];
    delta.predicate_element_count[c] = end_count.predicate_element_count[c] - start_count.predicate_element_count[c];
    delta.predicate_active_element_count[c] = end_count.predicate_active_element_count[c] - start_count.predicate_active_element_count[c];
    delta.vrf_read_request_lane_sample[c] = end_count.vrf_read_request_lane_sample[c] - start_count.vrf_read_request_lane_sample[c];
    delta.vrf_read_grant_lane_sample[c] = end_count.vrf_read_grant_lane_sample[c] - start_count.vrf_read_grant_lane_sample[c];
    delta.vrf_bank_conflict_lane_sample[c] = end_count.vrf_bank_conflict_lane_sample[c] - start_count.vrf_bank_conflict_lane_sample[c];
    delta.vrf_hazard_stall_lane_sample[c] = end_count.vrf_hazard_stall_lane_sample[c] - start_count.vrf_hazard_stall_lane_sample[c];
    delta.operand_queue_backpressure_lane_sample[c] = end_count.operand_queue_backpressure_lane_sample[c] - start_count.operand_queue_backpressure_lane_sample[c];
    delta.mask_index_fifo_push_count[c] = end_count.mask_index_fifo_push_count[c] - start_count.mask_index_fifo_push_count[c];
    delta.mask_index_fifo_pop_count[c] = end_count.mask_index_fifo_pop_count[c] - start_count.mask_index_fifo_pop_count[c];
    delta.gather_request_fifo_push_count[c] = end_count.gather_request_fifo_push_count[c] - start_count.gather_request_fifo_push_count[c];
    delta.gather_request_fifo_pop_count[c] = end_count.gather_request_fifo_pop_count[c] - start_count.gather_request_fifo_pop_count[c];
    delta.gather_broadcast_request_lane_sample[c] = end_count.gather_broadcast_request_lane_sample[c] - start_count.gather_broadcast_request_lane_sample[c];
    delta.gather_broadcast_grant_lane_sample[c] = end_count.gather_broadcast_grant_lane_sample[c] - start_count.gather_broadcast_grant_lane_sample[c];
    delta.gather_out_of_range_index_count[c] = end_count.gather_out_of_range_index_count[c] - start_count.gather_out_of_range_index_count[c];
    delta.compress_examined_element_count[c] = end_count.compress_examined_element_count[c] - start_count.compress_examined_element_count[c];
    delta.compress_selected_element_count[c] = end_count.compress_selected_element_count[c] - start_count.compress_selected_element_count[c];
    for (int unsigned b = 0; b < NrMaskDensityBins; b++)
      delta.predicate_density_hist[c][b] = end_count.predicate_density_hist[c][b] - start_count.predicate_density_hist[c][b];
    for (int unsigned b = 0; b < 4; b++) begin
      delta.sew_insn_hist[c][b] = end_count.sew_insn_hist[c][b] - start_count.sew_insn_hist[c][b];
      delta.dispatch_wait_hist[c][b] = end_count.dispatch_wait_hist[c][b] - start_count.dispatch_wait_hist[c][b];
      delta.execution_latency_hist[c][b] = end_count.execution_latency_hist[c][b] - start_count.execution_latency_hist[c][b];
    end
  end
  for (int unsigned op = 0; op < NrAraOps; op++) begin
    delta.opcode_active_cycle[op] = end_count.opcode_active_cycle[op] -
      start_count.opcode_active_cycle[op];
    delta.opcode_uop_count[op] = end_count.opcode_uop_count[op] - start_count.opcode_uop_count[op];
    delta.opcode_completed_count[op] = end_count.opcode_completed_count[op] - start_count.opcode_completed_count[op];
    delta.opcode_requested_element_count[op] = end_count.opcode_requested_element_count[op] - start_count.opcode_requested_element_count[op];
    delta.opcode_nominal_element_op_count[op] = end_count.opcode_nominal_element_op_count[op] - start_count.opcode_nominal_element_op_count[op];
    delta.opcode_dispatch_wait_cycle[op] = end_count.opcode_dispatch_wait_cycle[op] - start_count.opcode_dispatch_wait_cycle[op];
    delta.opcode_dispatch_request_cycle[op] = end_count.opcode_dispatch_request_cycle[op] -
      start_count.opcode_dispatch_request_cycle[op];
    delta.opcode_dispatch_blocked_cycle[op] = end_count.opcode_dispatch_blocked_cycle[op] -
      start_count.opcode_dispatch_blocked_cycle[op];
    delta.opcode_fu_queue_full_cycle[op] = end_count.opcode_fu_queue_full_cycle[op] -
      start_count.opcode_fu_queue_full_cycle[op];
    delta.opcode_mask_queue_full_cycle[op] = end_count.opcode_mask_queue_full_cycle[op] -
      start_count.opcode_mask_queue_full_cycle[op];
    delta.opcode_slide_queue_full_cycle[op] = end_count.opcode_slide_queue_full_cycle[op] -
      start_count.opcode_slide_queue_full_cycle[op];
    delta.opcode_id_pool_full_cycle[op] = end_count.opcode_id_pool_full_cycle[op] -
      start_count.opcode_id_pool_full_cycle[op];
    delta.opcode_response_wait_cycle[op] = end_count.opcode_response_wait_cycle[op] -
      start_count.opcode_response_wait_cycle[op];
    delta.opcode_other_dispatch_blocked_cycle[op] = end_count.opcode_other_dispatch_blocked_cycle[op] -
      start_count.opcode_other_dispatch_blocked_cycle[op];
    delta.opcode_operand_request_blocked_cycle[op] = end_count.opcode_operand_request_blocked_cycle[op] -
      start_count.opcode_operand_request_blocked_cycle[op];
    delta.opcode_primary_fu_queue_full_cycle[op] =
      end_count.opcode_primary_fu_queue_full_cycle[op] -
      start_count.opcode_primary_fu_queue_full_cycle[op];
    delta.opcode_primary_mask_queue_full_cycle[op] =
      end_count.opcode_primary_mask_queue_full_cycle[op] -
      start_count.opcode_primary_mask_queue_full_cycle[op];
    delta.opcode_primary_slide_queue_full_cycle[op] =
      end_count.opcode_primary_slide_queue_full_cycle[op] -
      start_count.opcode_primary_slide_queue_full_cycle[op];
    delta.opcode_primary_id_pool_full_cycle[op] =
      end_count.opcode_primary_id_pool_full_cycle[op] -
      start_count.opcode_primary_id_pool_full_cycle[op];
    delta.opcode_primary_response_wait_cycle[op] =
      end_count.opcode_primary_response_wait_cycle[op] -
      start_count.opcode_primary_response_wait_cycle[op];
    delta.opcode_primary_lane_desync_cycle[op] =
      end_count.opcode_primary_lane_desync_cycle[op] -
      start_count.opcode_primary_lane_desync_cycle[op];
    delta.opcode_primary_sequencer_block_cycle[op] =
      end_count.opcode_primary_sequencer_block_cycle[op] -
      start_count.opcode_primary_sequencer_block_cycle[op];
    delta.opcode_primary_operand_request_blocked_cycle[op] =
      end_count.opcode_primary_operand_request_blocked_cycle[op] -
      start_count.opcode_primary_operand_request_blocked_cycle[op];
    delta.opcode_primary_other_dispatch_blocked_cycle[op] =
      end_count.opcode_primary_other_dispatch_blocked_cycle[op] -
      start_count.opcode_primary_other_dispatch_blocked_cycle[op];
    delta.opcode_primary_dispatch_unattributed_cycle[op] =
      end_count.opcode_primary_dispatch_unattributed_cycle[op] -
      start_count.opcode_primary_dispatch_unattributed_cycle[op];
    delta.opcode_primary_result_backpressure_cycle[op] =
      end_count.opcode_primary_result_backpressure_cycle[op] -
      start_count.opcode_primary_result_backpressure_cycle[op];
    delta.opcode_primary_result_queue_full_cycle[op] =
      end_count.opcode_primary_result_queue_full_cycle[op] -
      start_count.opcode_primary_result_queue_full_cycle[op];
    delta.opcode_primary_latency_order_stall_cycle[op] =
      end_count.opcode_primary_latency_order_stall_cycle[op] -
      start_count.opcode_primary_latency_order_stall_cycle[op];
    delta.opcode_primary_unit_input_backpressure_cycle[op] =
      end_count.opcode_primary_unit_input_backpressure_cycle[op] -
      start_count.opcode_primary_unit_input_backpressure_cycle[op];
    delta.opcode_primary_operand_wait_cycle[op] =
      end_count.opcode_primary_operand_wait_cycle[op] -
      start_count.opcode_primary_operand_wait_cycle[op];
    delta.opcode_primary_long_latency_busy_cycle[op] =
      end_count.opcode_primary_long_latency_busy_cycle[op] -
      start_count.opcode_primary_long_latency_busy_cycle[op];
    delta.opcode_primary_special_path_cycle[op] =
      end_count.opcode_primary_special_path_cycle[op] -
      start_count.opcode_primary_special_path_cycle[op];
    delta.opcode_primary_progress_cycle[op] =
      end_count.opcode_primary_progress_cycle[op] -
      start_count.opcode_primary_progress_cycle[op];
    delta.opcode_primary_unattributed_cycle[op] =
      end_count.opcode_primary_unattributed_cycle[op] -
      start_count.opcode_primary_unattributed_cycle[op];
    delta.opcode_masked_count[op] = end_count.opcode_masked_count[op] - start_count.opcode_masked_count[op];
    delta.opcode_execution_latency_cycle[op] = end_count.opcode_execution_latency_cycle[op] - start_count.opcode_execution_latency_cycle[op];
    for (int unsigned b = 0; b < 4; b++) begin
      delta.opcode_dispatch_wait_hist[op][b] =
        end_count.opcode_dispatch_wait_hist[op][b] - start_count.opcode_dispatch_wait_hist[op][b];
      delta.opcode_execution_latency_hist[op][b] = end_count.opcode_execution_latency_hist[op][b] - start_count.opcode_execution_latency_hist[op][b];
      delta.opcode_sew_hist[op][b] = end_count.opcode_sew_hist[op][b] - start_count.opcode_sew_hist[op][b];
    end
    for (int unsigned lmul = 0; lmul < 8; lmul++)
      delta.opcode_lmul_hist[op][lmul] = end_count.opcode_lmul_hist[op][lmul] - start_count.opcode_lmul_hist[op][lmul];
    for (int unsigned sew = 0; sew < 4; sew++) begin
      for (int unsigned lmul = 0; lmul < 8; lmul++) begin
        delta.opcode_shape_uop_count[op][sew][lmul] =
          end_count.opcode_shape_uop_count[op][sew][lmul] -
          start_count.opcode_shape_uop_count[op][sew][lmul];
        delta.opcode_shape_completed_count[op][sew][lmul] =
          end_count.opcode_shape_completed_count[op][sew][lmul] -
          start_count.opcode_shape_completed_count[op][sew][lmul];
        delta.opcode_shape_latency_cycle[op][sew][lmul] =
          end_count.opcode_shape_latency_cycle[op][sew][lmul] -
          start_count.opcode_shape_latency_cycle[op][sew][lmul];
      end
    end
  end
  for (int unsigned u = 0; u < NrMfpuSubunits; u++) begin
    delta.mfpu_input_fire_lane_sample[u] = end_count.mfpu_input_fire_lane_sample[u] - start_count.mfpu_input_fire_lane_sample[u];
    delta.mfpu_input_backpressure_lane_sample[u] = end_count.mfpu_input_backpressure_lane_sample[u] - start_count.mfpu_input_backpressure_lane_sample[u];
    delta.mfpu_output_fire_lane_sample[u] = end_count.mfpu_output_fire_lane_sample[u] - start_count.mfpu_output_fire_lane_sample[u];
    delta.mfpu_processing_lane_sample[u] = end_count.mfpu_processing_lane_sample[u] - start_count.mfpu_processing_lane_sample[u];
  end
  for (int unsigned s = 0; s < NrValuStates; s++)
    delta.valu_state_lane_sample[s] = end_count.valu_state_lane_sample[s] - start_count.valu_state_lane_sample[s];
  for (int unsigned s = 0; s < NrMfpuStates; s++)
    delta.mfpu_state_lane_sample[s] = end_count.mfpu_state_lane_sample[s] - start_count.mfpu_state_lane_sample[s];
  for (int unsigned s = 0; s < NrSlduStates; s++)
    delta.sldu_state_cycle[s] = end_count.sldu_state_cycle[s] - start_count.sldu_state_cycle[s];
  exec_perf_delta = delta;
endfunction

function automatic frontend_perf_t frontend_perf_delta(
  frontend_perf_t end_count,
  frontend_perf_t start_count
);
  frontend_perf_t delta;
  delta = '{default: '0};
  for (int unsigned c = 0; c < NrExecClasses; c++) begin
    delta.arch_insn_count[c] = end_count.arch_insn_count[c] - start_count.arch_insn_count[c];
    delta.zero_vl_nop_count[c] =
      end_count.zero_vl_nop_count[c] - start_count.zero_vl_nop_count[c];
  end
  for (int unsigned op = 0; op < NrAraOps; op++) begin
    delta.arch_opcode_count[op] = end_count.arch_opcode_count[op] - start_count.arch_opcode_count[op];
    delta.arch_opcode_zero_vl_count[op] = end_count.arch_opcode_zero_vl_count[op] - start_count.arch_opcode_zero_vl_count[op];
  end
  delta.unclassified_arch_insn_count = end_count.unclassified_arch_insn_count -
    start_count.unclassified_arch_insn_count;
  delta.arch_exception_count =
    end_count.arch_exception_count - start_count.arch_exception_count;
  delta.config_insn_count = end_count.config_insn_count - start_count.config_insn_count;
  delta.vsetvli_count = end_count.vsetvli_count - start_count.vsetvli_count;
  delta.vsetivli_count = end_count.vsetivli_count - start_count.vsetivli_count;
  delta.vsetvl_count = end_count.vsetvl_count - start_count.vsetvl_count;
  delta.vector_csr_count = end_count.vector_csr_count - start_count.vector_csr_count;
  delta.vector_csr_write_count =
    end_count.vector_csr_write_count - start_count.vector_csr_write_count;
  delta.vector_csr_read_only_count =
    end_count.vector_csr_read_only_count - start_count.vector_csr_read_only_count;
  delta.config_request_cycle = end_count.config_request_cycle - start_count.config_request_cycle;
  delta.config_blocked_cycle = end_count.config_blocked_cycle - start_count.config_blocked_cycle;
  delta.config_wait_idle_cycle =
    end_count.config_wait_idle_cycle - start_count.config_wait_idle_cycle;
  delta.config_wait_backend_busy_cycle = end_count.config_wait_backend_busy_cycle -
    start_count.config_wait_backend_busy_cycle;
  delta.config_wait_ara_ready_cycle = end_count.config_wait_ara_ready_cycle -
    start_count.config_wait_ara_ready_cycle;
  delta.config_wait_reshuffle_cycle = end_count.config_wait_reshuffle_cycle -
    start_count.config_wait_reshuffle_cycle;
  delta.config_other_blocked_cycle = end_count.config_other_blocked_cycle -
    start_count.config_other_blocked_cycle;
  delta.vset_result_vl_sum = end_count.vset_result_vl_sum - start_count.vset_result_vl_sum;
  delta.vset_zero_vl_count = end_count.vset_zero_vl_count - start_count.vset_zero_vl_count;
  delta.vset_vill_count = end_count.vset_vill_count - start_count.vset_vill_count;
  delta.vset_vl_change_count =
    end_count.vset_vl_change_count - start_count.vset_vl_change_count;
  delta.vset_vtype_change_count =
    end_count.vset_vtype_change_count - start_count.vset_vtype_change_count;
  delta.vset_lmul_shrink_wait_count = end_count.vset_lmul_shrink_wait_count -
    start_count.vset_lmul_shrink_wait_count;
  for (int unsigned sew = 0; sew < 4; sew++)
    delta.vset_sew_hist[sew] = end_count.vset_sew_hist[sew] - start_count.vset_sew_hist[sew];
  for (int unsigned lmul = 0; lmul < 8; lmul++)
    delta.vset_lmul_hist[lmul] =
      end_count.vset_lmul_hist[lmul] - start_count.vset_lmul_hist[lmul];
  for (int unsigned m = 0; m < NrMemClasses; m++) begin
    delta.memory_insn_count[m] = end_count.memory_insn_count[m] - start_count.memory_insn_count[m];
    delta.memory_unit_stride_count[m] = end_count.memory_unit_stride_count[m] -
      start_count.memory_unit_stride_count[m];
    delta.memory_strided_count[m] =
      end_count.memory_strided_count[m] - start_count.memory_strided_count[m];
    delta.memory_indexed_unordered_count[m] = end_count.memory_indexed_unordered_count[m] -
      start_count.memory_indexed_unordered_count[m];
    delta.memory_indexed_ordered_count[m] = end_count.memory_indexed_ordered_count[m] -
      start_count.memory_indexed_ordered_count[m];
    delta.memory_segment_count[m] =
      end_count.memory_segment_count[m] - start_count.memory_segment_count[m];
    delta.memory_whole_register_count[m] = end_count.memory_whole_register_count[m] -
      start_count.memory_whole_register_count[m];
    delta.memory_mask_count[m] =
      end_count.memory_mask_count[m] - start_count.memory_mask_count[m];
    delta.memory_field_count[m] =
      end_count.memory_field_count[m] - start_count.memory_field_count[m];
    delta.memory_requested_element_count[m] = end_count.memory_requested_element_count[m] -
      start_count.memory_requested_element_count[m];
    delta.memory_requested_byte_count[m] = end_count.memory_requested_byte_count[m] -
      start_count.memory_requested_byte_count[m];
    delta.memory_exception_count[m] =
      end_count.memory_exception_count[m] - start_count.memory_exception_count[m];
    delta.memory_accepted_count[m] =
      end_count.memory_accepted_count[m] - start_count.memory_accepted_count[m];
    delta.memory_accepted_unit_stride_count[m] =
      end_count.memory_accepted_unit_stride_count[m] -
      start_count.memory_accepted_unit_stride_count[m];
    delta.memory_accepted_strided_count[m] =
      end_count.memory_accepted_strided_count[m] - start_count.memory_accepted_strided_count[m];
    delta.memory_accepted_indexed_unordered_count[m] =
      end_count.memory_accepted_indexed_unordered_count[m] -
      start_count.memory_accepted_indexed_unordered_count[m];
    delta.memory_accepted_indexed_ordered_count[m] =
      end_count.memory_accepted_indexed_ordered_count[m] -
      start_count.memory_accepted_indexed_ordered_count[m];
    delta.memory_accepted_segment_count[m] =
      end_count.memory_accepted_segment_count[m] - start_count.memory_accepted_segment_count[m];
    delta.memory_accepted_whole_register_count[m] =
      end_count.memory_accepted_whole_register_count[m] -
      start_count.memory_accepted_whole_register_count[m];
    delta.memory_accepted_mask_count[m] =
      end_count.memory_accepted_mask_count[m] - start_count.memory_accepted_mask_count[m];
  end
  delta.load_fault_only_first_count = end_count.load_fault_only_first_count -
    start_count.load_fault_only_first_count;
  delta.load_accepted_fault_only_first_count =
    end_count.load_accepted_fault_only_first_count -
    start_count.load_accepted_fault_only_first_count;
  frontend_perf_delta = delta;
endfunction

function automatic memory_perf_t memory_perf_delta(
  memory_perf_t end_count,
  memory_perf_t start_count
);
  memory_perf_t delta;
  delta = '{default: '0};
  for (int unsigned m = 0; m < NrMemClasses; m++) begin
    delta.addrgen_active_cycle[m] = end_count.addrgen_active_cycle[m] - start_count.addrgen_active_cycle[m];
    delta.addrgen_progress_cycle[m] = end_count.addrgen_progress_cycle[m] - start_count.addrgen_progress_cycle[m];
    delta.addrgen_no_progress_cycle[m] = end_count.addrgen_no_progress_cycle[m] - start_count.addrgen_no_progress_cycle[m];
    for (int unsigned s = 0; s < 5; s++)
      delta.addrgen_state_cycle[m][s] =
        end_count.addrgen_state_cycle[m][s] - start_count.addrgen_state_cycle[m][s];
    for (int unsigned s = 0; s < 4; s++)
      delta.axi_addrgen_state_cycle[m][s] =
        end_count.axi_addrgen_state_cycle[m][s] - start_count.axi_addrgen_state_cycle[m][s];
    delta.addrgen_operand_wait_cycle[m] = end_count.addrgen_operand_wait_cycle[m] - start_count.addrgen_operand_wait_cycle[m];
    delta.indexed_spill_wait_cycle[m] =
      end_count.indexed_spill_wait_cycle[m] - start_count.indexed_spill_wait_cycle[m];
    delta.last_translation_wait_cycle[m] =
      end_count.last_translation_wait_cycle[m] - start_count.last_translation_wait_cycle[m];
    delta.addrgen_queue_consumer_wait_cycle[m] =
      end_count.addrgen_queue_consumer_wait_cycle[m] -
      start_count.addrgen_queue_consumer_wait_cycle[m];
    delta.addrgen_queue_full_cycle[m] = end_count.addrgen_queue_full_cycle[m] - start_count.addrgen_queue_full_cycle[m];
    delta.core_store_pending_wait_cycle[m] = end_count.core_store_pending_wait_cycle[m] - start_count.core_store_pending_wait_cycle[m];
    delta.mmu_request_cycle[m] = end_count.mmu_request_cycle[m] - start_count.mmu_request_cycle[m];
    delta.mmu_wait_cycle[m] = end_count.mmu_wait_cycle[m] - start_count.mmu_wait_cycle[m];
    delta.mmu_dtlb_hit_count[m] = end_count.mmu_dtlb_hit_count[m] - start_count.mmu_dtlb_hit_count[m];
    delta.mmu_response_count[m] = end_count.mmu_response_count[m] - start_count.mmu_response_count[m];
    delta.mmu_exception_count[m] = end_count.mmu_exception_count[m] - start_count.mmu_exception_count[m];
    delta.axi_address_valid_cycle[m] = end_count.axi_address_valid_cycle[m] - start_count.axi_address_valid_cycle[m];
    delta.axi_address_fire_count[m] = end_count.axi_address_fire_count[m] - start_count.axi_address_fire_count[m];
    delta.axi_address_backpressure_cycle[m] = end_count.axi_address_backpressure_cycle[m] - start_count.axi_address_backpressure_cycle[m];
    delta.axi_data_valid_cycle[m] = end_count.axi_data_valid_cycle[m] - start_count.axi_data_valid_cycle[m];
    delta.axi_data_fire_count[m] = end_count.axi_data_fire_count[m] - start_count.axi_data_fire_count[m];
    delta.axi_data_backpressure_cycle[m] = end_count.axi_data_backpressure_cycle[m] - start_count.axi_data_backpressure_cycle[m];
    delta.axi_data_wait_cycle[m] = end_count.axi_data_wait_cycle[m] - start_count.axi_data_wait_cycle[m];
    delta.axi_response_valid_cycle[m] = end_count.axi_response_valid_cycle[m] - start_count.axi_response_valid_cycle[m];
    delta.axi_response_fire_count[m] = end_count.axi_response_fire_count[m] - start_count.axi_response_fire_count[m];
    delta.axi_response_wait_cycle[m] = end_count.axi_response_wait_cycle[m] - start_count.axi_response_wait_cycle[m];
    delta.axi_transfer_byte_count[m] = end_count.axi_transfer_byte_count[m] - start_count.axi_transfer_byte_count[m];
    delta.axi_useful_byte_count[m] = end_count.axi_useful_byte_count[m] - start_count.axi_useful_byte_count[m];
    delta.axi_outstanding_sample_cycle[m] = end_count.axi_outstanding_sample_cycle[m] - start_count.axi_outstanding_sample_cycle[m];
    delta.axi_outstanding_cycle_sum[m] = end_count.axi_outstanding_cycle_sum[m] - start_count.axi_outstanding_cycle_sum[m];
    delta.axi_outstanding_nonzero_cycle[m] = end_count.axi_outstanding_nonzero_cycle[m] - start_count.axi_outstanding_nonzero_cycle[m];
    delta.axi_request_latency_count[m] = end_count.axi_request_latency_count[m] - start_count.axi_request_latency_count[m];
    delta.axi_request_latency_cycle[m] = end_count.axi_request_latency_cycle[m] - start_count.axi_request_latency_cycle[m];
    delta.axi_tracking_overflow_count[m] = end_count.axi_tracking_overflow_count[m] - start_count.axi_tracking_overflow_count[m];
    delta.axi_tracking_underflow_count[m] = end_count.axi_tracking_underflow_count[m] - start_count.axi_tracking_underflow_count[m];
    for (int unsigned b = 0; b < NrAxiOutstandingBins; b++)
      delta.axi_outstanding_hist[m][b] = end_count.axi_outstanding_hist[m][b] - start_count.axi_outstanding_hist[m][b];
    for (int unsigned b = 0; b < 4; b++)
      delta.axi_request_latency_hist[m][b] = end_count.axi_request_latency_hist[m][b] - start_count.axi_request_latency_hist[m][b];
    delta.mask_wait_cycle[m] = end_count.mask_wait_cycle[m] - start_count.mask_wait_cycle[m];
    delta.result_queue_full_cycle[m] = end_count.result_queue_full_cycle[m] - start_count.result_queue_full_cycle[m];
    delta.operand_wait_cycle[m] = end_count.operand_wait_cycle[m] - start_count.operand_wait_cycle[m];
    delta.result_backpressure_cycle[m] = end_count.result_backpressure_cycle[m] - start_count.result_backpressure_cycle[m];
    delta.operand_handshake_lane_sample[m] = end_count.operand_handshake_lane_sample[m] - start_count.operand_handshake_lane_sample[m];
    delta.result_request_lane_sample[m] = end_count.result_request_lane_sample[m] - start_count.result_request_lane_sample[m];
    delta.result_handshake_lane_sample[m] = end_count.result_handshake_lane_sample[m] - start_count.result_handshake_lane_sample[m];
    delta.result_backpressure_lane_sample[m] = end_count.result_backpressure_lane_sample[m] - start_count.result_backpressure_lane_sample[m];
    delta.completion_count[m] = end_count.completion_count[m] - start_count.completion_count[m];
    delta.exception_count[m] = end_count.exception_count[m] - start_count.exception_count[m];
  end
  memory_perf_delta = delta;
endfunction

function automatic vfu_queue_perf_t vfu_queue_perf_delta(
  vfu_queue_perf_t end_count,
  vfu_queue_perf_t start_count
);
  vfu_queue_perf_t delta;
  delta = '{default: '0};
  for (int unsigned v = 0; v < NrVFUs; v++) begin
    delta.sample_cycle[v] = end_count.sample_cycle[v] - start_count.sample_cycle[v];
    delta.occupancy_cycle_sum[v] = end_count.occupancy_cycle_sum[v] - start_count.occupancy_cycle_sum[v];
    delta.nonempty_cycle[v] = end_count.nonempty_cycle[v] - start_count.nonempty_cycle[v];
    delta.at_capacity_cycle[v] = end_count.at_capacity_cycle[v] - start_count.at_capacity_cycle[v];
    for (int unsigned b = 0; b < NrQueueOccupancyBins; b++)
      delta.occupancy_hist[v][b] = end_count.occupancy_hist[v][b] - start_count.occupancy_hist[v][b];
  end
  vfu_queue_perf_delta = delta;
endfunction

function automatic void print_exec_class_report(
  input integer      file_handle,
  input string       class_name,
  input exec_class_e class_id,
  input exec_perf_t  stats,
  input logic [63:0] total_rvv_cycles
);
  logic [63:0] dispatch_hist_samples;
  logic [63:0] execution_hist_samples;
  logic [63:0] primary_attribution_samples;
  logic [63:0] primary_dispatch_attribution_samples;
  logic [63:0] predicate_hist_samples;
  automatic logic [63:0] top_exec_bottleneck_count;
  automatic string top_exec_bottleneck_name;
  automatic logic [63:0] second_exec_bottleneck_count;
  automatic string second_exec_bottleneck_name;
  automatic logic [63:0] top_dispatch_bottleneck_count;
  automatic string top_dispatch_bottleneck_name;
  automatic logic [63:0] second_dispatch_bottleneck_count;
  automatic string second_dispatch_bottleneck_name;
  automatic logic [63:0] top_exec_gap;
  automatic logic [63:0] top_dispatch_gap;
  automatic real top_exec_gap_ratio_exec_active;
  automatic real top_dispatch_gap_ratio_dispatch_request;
  automatic real top_exec_dominance_ratio;
  automatic real second_exec_dominance_ratio;
  automatic real top_dispatch_dominance_ratio;
  automatic real second_dispatch_dominance_ratio;
  dispatch_hist_samples = stats.dispatch_wait_hist[class_id][0] +
                          stats.dispatch_wait_hist[class_id][1] +
                          stats.dispatch_wait_hist[class_id][2] +
                          stats.dispatch_wait_hist[class_id][3];
  execution_hist_samples = stats.execution_latency_hist[class_id][0] +
                           stats.execution_latency_hist[class_id][1] +
                           stats.execution_latency_hist[class_id][2] +
                           stats.execution_latency_hist[class_id][3];
  primary_attribution_samples =
    stats.primary_result_backpressure_cycle[class_id] +
    stats.primary_result_queue_full_cycle[class_id] +
    stats.primary_latency_order_stall_cycle[class_id] +
    stats.primary_unit_input_backpressure_cycle[class_id] +
    stats.primary_operand_wait_cycle[class_id] +
    stats.primary_long_latency_busy_cycle[class_id] +
    stats.primary_special_path_cycle[class_id] +
    stats.primary_progress_cycle[class_id] +
    stats.primary_unattributed_cycle[class_id];
  primary_dispatch_attribution_samples =
    stats.primary_fu_queue_full_cycle[class_id] +
    stats.primary_mask_queue_full_cycle[class_id] +
    stats.primary_slide_queue_full_cycle[class_id] +
    stats.primary_id_pool_full_cycle[class_id] +
    stats.primary_response_wait_cycle[class_id] +
    stats.primary_lane_desync_cycle[class_id] +
    stats.primary_sequencer_block_cycle[class_id] +
    stats.primary_operand_request_blocked_cycle[class_id] +
    stats.primary_other_dispatch_blocked_cycle[class_id] +
    stats.primary_dispatch_unattributed_cycle[class_id];
  top_exec_bottleneck_count = '0;
  top_exec_bottleneck_name = "none";
  second_exec_bottleneck_count = '0;
  second_exec_bottleneck_name = "none";
  top_dispatch_bottleneck_count = '0;
  top_dispatch_bottleneck_name = "none";
  second_dispatch_bottleneck_count = '0;
  second_dispatch_bottleneck_name = "none";

  update_top2(
    stats.primary_result_backpressure_cycle[class_id], "primary_result_backpressure",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);
  update_top2(
    stats.primary_result_queue_full_cycle[class_id], "primary_result_queue_full",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);
  update_top2(
    stats.primary_latency_order_stall_cycle[class_id], "primary_latency_order_stall",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);
  update_top2(
    stats.primary_unit_input_backpressure_cycle[class_id], "primary_unit_input_backpressure",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);
  update_top2(
    stats.primary_operand_wait_cycle[class_id], "primary_operand_wait",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);
  update_top2(
    stats.primary_long_latency_busy_cycle[class_id], "primary_long_latency_busy",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);
  update_top2(
    stats.primary_special_path_cycle[class_id], "primary_special_path",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);
  update_top2(
    stats.primary_progress_cycle[class_id], "primary_progress",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);
  update_top2(
    stats.primary_unattributed_cycle[class_id], "primary_unattributed",
    top_exec_bottleneck_count, top_exec_bottleneck_name,
    second_exec_bottleneck_count, second_exec_bottleneck_name);

  update_top2(
    stats.primary_fu_queue_full_cycle[class_id], "primary_fu_queue_full",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_mask_queue_full_cycle[class_id], "primary_mask_queue_full",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_slide_queue_full_cycle[class_id], "primary_slide_queue_full",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_id_pool_full_cycle[class_id], "primary_id_pool_full",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_response_wait_cycle[class_id], "primary_response_wait",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_lane_desync_cycle[class_id], "primary_lane_desync",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_sequencer_block_cycle[class_id], "primary_sequencer_block",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_operand_request_blocked_cycle[class_id], "primary_operand_request_blocked",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_other_dispatch_blocked_cycle[class_id], "primary_other_dispatch_blocked",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
  update_top2(
    stats.primary_dispatch_unattributed_cycle[class_id], "primary_dispatch_unattributed",
    top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
    second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);

  top_exec_gap = (top_exec_bottleneck_count >= second_exec_bottleneck_count) ?
                 (top_exec_bottleneck_count - second_exec_bottleneck_count) : 0;
  top_dispatch_gap = (top_dispatch_bottleneck_count >= second_dispatch_bottleneck_count) ?
                    (top_dispatch_bottleneck_count - second_dispatch_bottleneck_count) : 0;
  top_exec_dominance_ratio = perf_ratio(top_exec_bottleneck_count, primary_attribution_samples);
  top_dispatch_dominance_ratio = perf_ratio(top_dispatch_bottleneck_count,
    primary_dispatch_attribution_samples);
  second_exec_dominance_ratio = perf_ratio(second_exec_bottleneck_count, primary_attribution_samples);
  second_dispatch_dominance_ratio = perf_ratio(second_dispatch_bottleneck_count,
    primary_dispatch_attribution_samples);
  top_exec_gap_ratio_exec_active = perf_ratio(top_exec_gap, stats.active_cycle[class_id]);
  top_dispatch_gap_ratio_dispatch_request = perf_ratio(
    top_dispatch_gap,
    stats.dispatch_request_cycle[class_id]
  );
  predicate_hist_samples = '0;
  for (int unsigned b = 0; b < NrMaskDensityBins; b++)
    predicate_hist_samples += stats.predicate_density_hist[class_id][b];
  if (file_handle == 0) begin
  $display("[PERF] %s_exec_insns: %0d", class_name, stats.insn_count[class_id]);
  $display("[PERF] %s_issued_insns: %0d", class_name, stats.issued_count[class_id]);
  $display("[PERF] %s_completed_insns: %0d", class_name, stats.completed_count[class_id]);
  $display("[PERF] %s_accept_to_issue_ratio: %0.6f", class_name,
    perf_ratio(stats.issued_count[class_id], stats.insn_count[class_id]));
  $display("[PERF] %s_issue_to_completion_ratio: %0.6f", class_name,
    perf_ratio(stats.completed_count[class_id], stats.issued_count[class_id]));
  $display("[PERF] %s_requested_elements: %0d", class_name,
    stats.requested_element_count[class_id]);
  $display("[PERF] %s_avg_requested_elements_per_insn: %0.3f", class_name,
    perf_ratio(stats.requested_element_count[class_id], stats.insn_count[class_id]));
  $display("[PERF] %s_requested_elements_per_rvv_cycle: %0.6f", class_name,
    perf_ratio(stats.requested_element_count[class_id], total_rvv_cycles));
  $display("[PERF] %s_nominal_element_ops: %0d", class_name,
    stats.nominal_element_op_count[class_id]);
  $display("[PERF] %s_nominal_element_ops_per_rvv_cycle: %0.6f", class_name,
    perf_ratio(stats.nominal_element_op_count[class_id], total_rvv_cycles));
  $display("[PERF] %s_masked_insns: %0d", class_name, stats.masked_insn_count[class_id]);
  $display("[PERF] %s_masked_insn_ratio: %0.6f", class_name,
    perf_ratio(stats.masked_insn_count[class_id], stats.insn_count[class_id]));
  $display("[PERF] %s_reduction_insns: %0d", class_name,
    stats.reduction_insn_count[class_id]);
  $display("[PERF] %s_special_path_insns: %0d", class_name,
    stats.special_insn_count[class_id]);
  if (class_id inside {ExecLoad, ExecStore}) begin
    $display("[PERF] %s_unit_stride_backend_uops: %0d", class_name,
      stats.unit_stride_uop_count[class_id]);
    $display("[PERF] %s_strided_backend_uops: %0d", class_name,
      stats.strided_uop_count[class_id]);
    $display("[PERF] %s_indexed_backend_uops: %0d", class_name,
      stats.indexed_uop_count[class_id]);
    $display("[PERF] %s_segment_backend_uops: %0d", class_name,
      stats.segment_uop_count[class_id]);
    $display("[PERF] %s_fault_only_first_backend_uops: %0d", class_name,
      stats.fault_only_first_uop_count[class_id]);
    $display("[PERF] %s_backend_requested_bytes: %0d", class_name,
      stats.requested_byte_count[class_id]);
    $display("[PERF] %s_backend_requested_bytes_per_uop: %0.3f", class_name,
      perf_ratio(stats.requested_byte_count[class_id], stats.insn_count[class_id]));
  end
  $display("[PERF] %s_sew8_insns: %0d", class_name, stats.sew_insn_hist[class_id][0]);
  $display("[PERF] %s_sew16_insns: %0d", class_name, stats.sew_insn_hist[class_id][1]);
  $display("[PERF] %s_sew32_insns: %0d", class_name, stats.sew_insn_hist[class_id][2]);
  $display("[PERF] %s_sew64_insns: %0d", class_name, stats.sew_insn_hist[class_id][3]);
  $display("[PERF] %s_active_cycles: %0d", class_name, stats.active_cycle[class_id]);
  $display("[PERF] %s_inflight_insn_cycles: %0d", class_name, stats.inflight_insn_cycle[class_id]);
  $display("[PERF] %s_masked_active_cycles: %0d", class_name,
    stats.masked_active_cycle[class_id]);
  $display("[PERF] %s_active_ratio: %0.3f", class_name,
    perf_ratio(stats.active_cycle[class_id], total_rvv_cycles));
  $display("[PERF] %s_completion_per_rvv_cycle: %0.6f", class_name,
    perf_ratio(stats.completed_count[class_id], total_rvv_cycles));
  $display("[PERF] %s_avg_inflight_when_active: %0.3f", class_name,
    perf_ratio(stats.inflight_insn_cycle[class_id], stats.active_cycle[class_id]));
  // Keep the original accepted-instruction denominator for report consumers.
  $display("[PERF] %s_active_cycles_per_insn: %0.3f", class_name,
    perf_ratio(stats.active_cycle[class_id], stats.insn_count[class_id]));
  $display("[PERF] %s_active_cycles_per_completed_insn: %0.3f", class_name,
    perf_ratio(stats.active_cycle[class_id], stats.completed_count[class_id]));
  $display("[PERF] %s_requested_elements_per_active_cycle: %0.6f", class_name,
    perf_ratio(stats.requested_element_count[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_masked_active_ratio: %0.6f", class_name,
    perf_ratio(stats.masked_active_cycle[class_id], stats.active_cycle[class_id]));

  $display("[PERF] %s_dispatch_wait_cycles: %0d", class_name, stats.dispatch_wait_cycle[class_id]);
  $display("[PERF] %s_avg_dispatch_wait: %0.3f", class_name,
    perf_ratio(stats.dispatch_wait_cycle[class_id], stats.issued_count[class_id]));
  $display("[PERF] %s_dispatch_wait_0_cycles: %0d", class_name, stats.dispatch_wait_hist[class_id][0]);
  $display("[PERF] %s_dispatch_wait_1_4_cycles: %0d", class_name, stats.dispatch_wait_hist[class_id][1]);
  $display("[PERF] %s_dispatch_wait_5_16_cycles: %0d", class_name, stats.dispatch_wait_hist[class_id][2]);
  $display("[PERF] %s_dispatch_wait_gt16_cycles: %0d", class_name, stats.dispatch_wait_hist[class_id][3]);

  $display("[PERF] %s_execution_latency_cycles: %0d", class_name, stats.execution_latency_cycle[class_id]);
  $display("[PERF] %s_avg_execution_latency: %0.3f", class_name,
    perf_ratio(stats.execution_latency_cycle[class_id], stats.completed_count[class_id]));
  $display("[PERF] %s_execution_latency_le8: %0d", class_name, stats.execution_latency_hist[class_id][0]);
  $display("[PERF] %s_execution_latency_9_32: %0d", class_name, stats.execution_latency_hist[class_id][1]);
  $display("[PERF] %s_execution_latency_33_128: %0d", class_name, stats.execution_latency_hist[class_id][2]);
  $display("[PERF] %s_execution_latency_gt128: %0d", class_name, stats.execution_latency_hist[class_id][3]);
  $display("[PERF] %s_end_to_end_latency_cycles: %0d", class_name, stats.end_to_end_latency_cycle[class_id]);
  $display("[PERF] %s_avg_end_to_end_latency: %0.3f", class_name,
    perf_ratio(stats.end_to_end_latency_cycle[class_id], stats.completed_count[class_id]));

  $display("[PERF] %s_dispatch_request_cycles: %0d", class_name,
    stats.dispatch_request_cycle[class_id]);
  $display("[PERF] %s_dispatch_blocked_cycles: %0d", class_name, stats.dispatch_blocked_cycle[class_id]);
  $display("[PERF] %s_dispatch_blocked_ratio: %0.6f", class_name,
    perf_ratio(stats.dispatch_blocked_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_fu_queue_full_ratio: %0.6f", class_name,
    perf_ratio(stats.fu_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_fu_queue_full_cycles: %0d", class_name, stats.fu_queue_full_cycle[class_id]);
  $display("[PERF] %s_mask_queue_full_ratio: %0.6f", class_name,
    perf_ratio(stats.mask_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_mask_queue_full_cycles: %0d", class_name,
    stats.mask_queue_full_cycle[class_id]);
  $display("[PERF] %s_slide_queue_full_ratio: %0.6f", class_name,
    perf_ratio(stats.slide_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_slide_queue_full_cycles: %0d", class_name,
    stats.slide_queue_full_cycle[class_id]);
  $display("[PERF] %s_id_pool_full_ratio: %0.6f", class_name,
    perf_ratio(stats.id_pool_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_id_pool_full_cycles: %0d", class_name,
    stats.id_pool_full_cycle[class_id]);
  $display("[PERF] %s_response_wait_ratio: %0.6f", class_name,
    perf_ratio(stats.response_wait_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_response_wait_cycles: %0d", class_name,
    stats.response_wait_cycle[class_id]);
  $display("[PERF] %s_other_dispatch_blocked_ratio: %0.6f", class_name,
    perf_ratio(stats.other_dispatch_blocked_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_other_dispatch_blocked_cycles: %0d", class_name,
    stats.other_dispatch_blocked_cycle[class_id]);
  $display("[PERF] %s_operand_request_blocked_ratio: %0.6f", class_name,
    perf_ratio(stats.operand_request_blocked_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_operand_request_blocked_cycles: %0d", class_name,
    stats.operand_request_blocked_cycle[class_id]);
  $display("[PERF] %s_primary_fu_queue_full_cycles: %0d", class_name,
    stats.primary_fu_queue_full_cycle[class_id]);
  $display("[PERF] %s_primary_fu_queue_full_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_fu_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_mask_queue_full_cycles: %0d", class_name,
    stats.primary_mask_queue_full_cycle[class_id]);
  $display("[PERF] %s_primary_mask_queue_full_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_mask_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_slide_queue_full_cycles: %0d", class_name,
    stats.primary_slide_queue_full_cycle[class_id]);
  $display("[PERF] %s_primary_slide_queue_full_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_slide_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_id_pool_full_cycles: %0d", class_name,
    stats.primary_id_pool_full_cycle[class_id]);
  $display("[PERF] %s_primary_id_pool_full_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_id_pool_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_response_wait_cycles: %0d", class_name,
    stats.primary_response_wait_cycle[class_id]);
  $display("[PERF] %s_primary_response_wait_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_response_wait_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_lane_desync_cycles: %0d", class_name,
    stats.primary_lane_desync_cycle[class_id]);
  $display("[PERF] %s_primary_lane_desync_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_lane_desync_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_sequencer_block_cycles: %0d", class_name,
    stats.primary_sequencer_block_cycle[class_id]);
  $display("[PERF] %s_primary_sequencer_block_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_sequencer_block_cycle[class_id], stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_operand_request_blocked_cycles: %0d", class_name,
    stats.primary_operand_request_blocked_cycle[class_id]);
  $display("[PERF] %s_primary_operand_request_blocked_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_operand_request_blocked_cycle[class_id],
               stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_other_dispatch_blocked_cycles: %0d", class_name,
    stats.primary_other_dispatch_blocked_cycle[class_id]);
  $display("[PERF] %s_primary_other_dispatch_blocked_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_other_dispatch_blocked_cycle[class_id],
               stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_primary_dispatch_unattributed_cycles: %0d", class_name,
    stats.primary_dispatch_unattributed_cycle[class_id]);
  $display("[PERF] %s_primary_dispatch_unattributed_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_dispatch_unattributed_cycle[class_id],
               stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_dispatch_reasons_within_request: %0d", class_name,
    stats.dispatch_blocked_cycle[class_id] <= stats.dispatch_request_cycle[class_id]);
  $display("[PERF] %s_primary_dispatch_partition_consistent: %0d", class_name,
    primary_dispatch_attribution_samples == stats.dispatch_blocked_cycle[class_id]);
  $display("[PERF] %s_raw_hazard_cycles: %0d", class_name, stats.raw_hazard_cycle[class_id]);
  $display("[PERF] %s_raw_hazard_ratio: %0.6f", class_name,
    perf_ratio(stats.raw_hazard_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_war_hazard_cycles: %0d", class_name, stats.war_hazard_cycle[class_id]);
  $display("[PERF] %s_war_hazard_ratio: %0.6f", class_name,
    perf_ratio(stats.war_hazard_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_waw_hazard_cycles: %0d", class_name, stats.waw_hazard_cycle[class_id]);
  $display("[PERF] %s_waw_hazard_ratio: %0.6f", class_name,
    perf_ratio(stats.waw_hazard_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_false_hazard_cycles: %0d", class_name, stats.false_hazard_cycle[class_id]);
  $display("[PERF] %s_false_hazard_ratio: %0.6f", class_name,
    perf_ratio(stats.false_hazard_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_sequencer_block_cycles: %0d", class_name, stats.sequencer_block_cycle[class_id]);
  $display("[PERF] %s_sequencer_block_ratio: %0.6f", class_name,
    perf_ratio(stats.sequencer_block_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_lane_desync_cycles: %0d", class_name, stats.lane_desync_cycle[class_id]);
  $display("[PERF] %s_lane_desync_ratio: %0.6f", class_name,
    perf_ratio(stats.lane_desync_cycle[class_id], stats.active_cycle[class_id]));

  $display("[PERF] %s_issue_progress_cycles: %0d", class_name, stats.issue_progress_cycle[class_id]);
  $display("[PERF] %s_no_issue_progress_cycles: %0d", class_name, stats.no_issue_progress_cycle[class_id]);
  $display("[PERF] %s_issue_progress_ratio: %0.6f", class_name,
    perf_ratio(stats.issue_progress_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_no_issue_progress_ratio: %0.6f", class_name,
    perf_ratio(stats.no_issue_progress_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_operand_wait_cycles: %0d", class_name, stats.operand_wait_cycle[class_id]);
  $display("[PERF] %s_operand_wait_ratio: %0.6f", class_name,
    perf_ratio(stats.operand_wait_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_unit_input_backpressure_cycles: %0d", class_name,
    stats.unit_input_backpressure_cycle[class_id]);
  $display("[PERF] %s_unit_input_backpressure_ratio: %0.6f", class_name,
    perf_ratio(stats.unit_input_backpressure_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_latency_order_stall_cycles: %0d", class_name,
    stats.latency_order_stall_cycle[class_id]);
  $display("[PERF] %s_result_queue_full_cycles: %0d", class_name,
    stats.result_queue_full_cycle[class_id]);
  $display("[PERF] %s_result_backpressure_cycles: %0d", class_name,
    stats.result_backpressure_cycle[class_id]);
  $display("[PERF] %s_result_backpressure_ratio: %0.6f", class_name,
    perf_ratio(stats.result_backpressure_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_long_latency_busy_cycles: %0d", class_name,
    stats.long_latency_busy_cycle[class_id]);
  $display("[PERF] %s_long_latency_busy_ratio: %0.6f", class_name,
    perf_ratio(stats.long_latency_busy_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_reduction_cycles: %0d", class_name, stats.reduction_cycle[class_id]);
  $display("[PERF] %s_cross_lane_cycles: %0d", class_name, stats.cross_lane_cycle[class_id]);
  $display("[PERF] %s_special_path_cycles: %0d", class_name, stats.special_path_cycle[class_id]);
  $display("[PERF] %s_index_fifo_full_cycles: %0d", class_name,
    stats.index_fifo_full_cycle[class_id]);

  $display("[PERF] %s_primary_result_backpressure_cycles: %0d", class_name,
    stats.primary_result_backpressure_cycle[class_id]);
  $display("[PERF] %s_primary_result_queue_full_cycles: %0d", class_name,
    stats.primary_result_queue_full_cycle[class_id]);
  $display("[PERF] %s_primary_latency_order_stall_cycles: %0d", class_name,
    stats.primary_latency_order_stall_cycle[class_id]);
  $display("[PERF] %s_primary_unit_input_backpressure_cycles: %0d", class_name,
    stats.primary_unit_input_backpressure_cycle[class_id]);
  $display("[PERF] %s_primary_operand_wait_cycles: %0d", class_name,
    stats.primary_operand_wait_cycle[class_id]);
  $display("[PERF] %s_primary_long_latency_busy_cycles: %0d", class_name,
    stats.primary_long_latency_busy_cycle[class_id]);
  $display("[PERF] %s_primary_special_path_cycles: %0d", class_name,
    stats.primary_special_path_cycle[class_id]);
  $display("[PERF] %s_primary_progress_cycles: %0d", class_name,
    stats.primary_progress_cycle[class_id]);
  $display("[PERF] %s_primary_unattributed_cycles: %0d", class_name,
    stats.primary_unattributed_cycle[class_id]);
  $display("[PERF] %s_primary_result_backpressure_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_result_backpressure_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_primary_result_queue_full_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_result_queue_full_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_primary_latency_order_stall_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_latency_order_stall_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_primary_unit_input_backpressure_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_unit_input_backpressure_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_primary_operand_wait_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_operand_wait_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_primary_long_latency_busy_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_long_latency_busy_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_primary_special_path_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_special_path_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_primary_progress_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_progress_cycle[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_primary_unattributed_ratio: %0.6f", class_name,
    perf_ratio(stats.primary_unattributed_cycle[class_id], stats.active_cycle[class_id]));

  $display("[PERF] %s_issue_progress_lane_samples: %0d", class_name,
    stats.issue_progress_lane_sample[class_id]);
  $display("[PERF] %s_avg_progress_lanes_per_active_cycle: %0.3f", class_name,
    perf_ratio(stats.issue_progress_lane_sample[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_operand_wait_lane_samples: %0d", class_name,
    stats.operand_wait_lane_sample[class_id]);
  $display("[PERF] %s_unit_input_backpressure_lane_samples: %0d", class_name,
    stats.unit_input_backpressure_lane_sample[class_id]);
  $display("[PERF] %s_latency_order_stall_lane_samples: %0d", class_name,
    stats.latency_order_stall_lane_sample[class_id]);
  $display("[PERF] %s_result_queue_full_lane_samples: %0d", class_name,
    stats.result_queue_full_lane_sample[class_id]);
  $display("[PERF] %s_result_backpressure_lane_samples: %0d", class_name,
    stats.result_backpressure_lane_sample[class_id]);
  $display("[PERF] %s_long_latency_busy_lane_samples: %0d", class_name,
    stats.long_latency_busy_lane_sample[class_id]);
  $display("[PERF] %s_result_queue_occupancy_lane_samples: %0d", class_name,
    stats.result_queue_occupancy_lane_sample[class_id]);
  $display("[PERF] %s_avg_result_queue_entries_per_active_cycle: %0.3f", class_name,
    perf_ratio(stats.result_queue_occupancy_lane_sample[class_id], stats.active_cycle[class_id]));
  $display("[PERF] %s_predicate_packets: %0d", class_name,
    stats.predicate_packet_count[class_id]);
  $display("[PERF] %s_predicate_elements: %0d", class_name,
    stats.predicate_element_count[class_id]);
  $display("[PERF] %s_predicate_active_elements: %0d", class_name,
    stats.predicate_active_element_count[class_id]);
  $display("[PERF] %s_predicate_active_ratio: %0.6f", class_name,
    perf_ratio(stats.predicate_active_element_count[class_id],
               stats.predicate_element_count[class_id]));
  for (int unsigned b = 0; b < NrMaskDensityBins; b++)
    $display("[PERF] %s_predicate_density_bin_%0d_packets: %0d", class_name, b,
      stats.predicate_density_hist[class_id][b]);
  $display("[PERF] %s_vrf_read_request_lane_samples: %0d", class_name,
    stats.vrf_read_request_lane_sample[class_id]);
  $display("[PERF] %s_vrf_read_grant_lane_samples: %0d", class_name,
    stats.vrf_read_grant_lane_sample[class_id]);
  $display("[PERF] %s_vrf_bank_conflict_lane_samples: %0d", class_name,
    stats.vrf_bank_conflict_lane_sample[class_id]);
  $display("[PERF] %s_vrf_bank_conflict_ratio: %0.6f", class_name,
    perf_ratio(stats.vrf_bank_conflict_lane_sample[class_id],
               stats.vrf_read_request_lane_sample[class_id]));
  $display("[PERF] %s_vrf_hazard_stall_lane_samples: %0d", class_name,
    stats.vrf_hazard_stall_lane_sample[class_id]);
  $display("[PERF] %s_operand_queue_backpressure_lane_samples: %0d", class_name,
    stats.operand_queue_backpressure_lane_sample[class_id]);
  $display("[PERF] %s_predicate_hist_consistent: %0d", class_name,
    predicate_hist_samples == stats.predicate_packet_count[class_id]);
  $display("[PERF] %s_predicate_active_le_total_consistent: %0d", class_name,
    stats.predicate_active_element_count[class_id] <= stats.predicate_element_count[class_id]);
  $display("[PERF] %s_vrf_request_partition_consistent: %0d", class_name,
    stats.vrf_read_request_lane_sample[class_id] ==
      stats.vrf_read_grant_lane_sample[class_id] +
      stats.vrf_bank_conflict_lane_sample[class_id]);
  if (class_id == ExecMask) begin
    $display("[PERF] mask_operand_incomplete_cycles: %0d", stats.mask_operand_incomplete_cycle[class_id]);
    $display("[PERF] mask_issue_end_cycles: %0d", stats.mask_issue_end_cycle[class_id]);
    $display("[PERF] mask_commit_pending_cycles: %0d", stats.mask_commit_pending_cycle[class_id]);
    $display("[PERF] mask_result_queue_nonempty_cycles: %0d", stats.mask_result_queue_nonempty_cycle[class_id]);
    $display("[PERF] mask_final_grant_wait_cycles: %0d", stats.mask_final_grant_wait_cycle[class_id]);
    $display("[PERF] mask_index_fifo_nonempty_cycles: %0d", stats.mask_index_fifo_nonempty_cycle[class_id]);
    $display("[PERF] mask_request_fifo_nonempty_cycles: %0d", stats.mask_request_fifo_nonempty_cycle[class_id]);
  end
  $display("[PERF] %s_top_primary_exec_bottleneck_reason: %s", class_name,
    top_exec_bottleneck_name);
  $display("[PERF] %s_top_primary_exec_bottleneck_cycles: %0d", class_name,
    top_exec_bottleneck_count);
  $display("[PERF] %s_top_primary_exec_bottleneck_ratio: %0.6f", class_name,
    perf_ratio(top_exec_bottleneck_count, stats.active_cycle[class_id]));
  $display("[PERF] %s_top_secondary_exec_bottleneck_reason: %s", class_name,
    second_exec_bottleneck_name);
  $display("[PERF] %s_top_secondary_exec_bottleneck_cycles: %0d", class_name,
    second_exec_bottleneck_count);
  $display("[PERF] %s_top_secondary_exec_bottleneck_ratio: %0.6f", class_name,
    perf_ratio(second_exec_bottleneck_count, stats.active_cycle[class_id]));
  $display("[PERF] %s_top_exec_bottleneck_reason_gap: %0d", class_name, top_exec_gap);
  $display("[PERF] %s_top_exec_bottleneck_gap_ratio_exec_active: %0.6f", class_name,
    top_exec_gap_ratio_exec_active);
  $display("[PERF] %s_top_exec_bottleneck_dominance_ratio: %0.6f", class_name,
    top_exec_dominance_ratio);
  $display("[PERF] %s_top_secondary_exec_bottleneck_dominance_ratio: %0.6f", class_name,
    second_exec_dominance_ratio);
  $display("[PERF] %s_top_primary_exec_bottleneck_advice: %s", class_name,
    exec_bottleneck_advice(top_exec_bottleneck_name));
  $display("[PERF] %s_top_primary_dispatch_bottleneck_reason: %s", class_name,
    top_dispatch_bottleneck_name);
  $display("[PERF] %s_top_primary_dispatch_bottleneck_cycles: %0d", class_name,
    top_dispatch_bottleneck_count);
  $display("[PERF] %s_top_primary_dispatch_bottleneck_ratio_dispatch_request: %0.6f", class_name,
    perf_ratio(top_dispatch_bottleneck_count, stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_top_primary_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f", class_name,
    perf_ratio(top_dispatch_bottleneck_count, stats.dispatch_blocked_cycle[class_id]));
  $display("[PERF] %s_top_secondary_dispatch_bottleneck_reason: %s", class_name,
    second_dispatch_bottleneck_name);
  $display("[PERF] %s_top_secondary_dispatch_bottleneck_cycles: %0d", class_name,
    second_dispatch_bottleneck_count);
  $display("[PERF] %s_top_secondary_dispatch_bottleneck_ratio_dispatch_request: %0.6f", class_name,
    perf_ratio(second_dispatch_bottleneck_count, stats.dispatch_request_cycle[class_id]));
  $display("[PERF] %s_top_secondary_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f", class_name,
    perf_ratio(second_dispatch_bottleneck_count, stats.dispatch_blocked_cycle[class_id]));
  $display("[PERF] %s_top_dispatch_bottleneck_reason_gap: %0d", class_name,
    top_dispatch_gap);
  $display("[PERF] %s_top_dispatch_bottleneck_gap_ratio_dispatch_request: %0.6f", class_name,
    top_dispatch_gap_ratio_dispatch_request);
  $display("[PERF] %s_top_dispatch_bottleneck_dominance_ratio: %0.6f", class_name,
    top_dispatch_dominance_ratio);
  $display("[PERF] %s_top_secondary_dispatch_bottleneck_dominance_ratio: %0.6f", class_name,
    second_dispatch_dominance_ratio);
  $display("[PERF] %s_top_primary_dispatch_bottleneck_advice: %s", class_name,
    dispatch_bottleneck_advice(top_dispatch_bottleneck_name));
  $display("[PERF] %s_mask_index_fifo_pushes: %0d", class_name,
    stats.mask_index_fifo_push_count[class_id]);
  $display("[PERF] %s_mask_index_fifo_pops: %0d", class_name,
    stats.mask_index_fifo_pop_count[class_id]);
  $display("[PERF] %s_gather_request_fifo_pushes: %0d", class_name,
    stats.gather_request_fifo_push_count[class_id]);
  $display("[PERF] %s_gather_request_fifo_pops: %0d", class_name,
    stats.gather_request_fifo_pop_count[class_id]);
  $display("[PERF] %s_gather_broadcast_request_lane_samples: %0d", class_name,
    stats.gather_broadcast_request_lane_sample[class_id]);
  $display("[PERF] %s_gather_broadcast_grant_lane_samples: %0d", class_name,
    stats.gather_broadcast_grant_lane_sample[class_id]);
  $display("[PERF] %s_gather_broadcast_grant_ratio: %0.6f", class_name,
    perf_ratio(stats.gather_broadcast_grant_lane_sample[class_id],
               stats.gather_broadcast_request_lane_sample[class_id]));
  $display("[PERF] %s_gather_out_of_range_indices: %0d", class_name,
    stats.gather_out_of_range_index_count[class_id]);
  $display("[PERF] %s_compress_examined_elements: %0d", class_name,
    stats.compress_examined_element_count[class_id]);
  $display("[PERF] %s_compress_selected_elements: %0d", class_name,
    stats.compress_selected_element_count[class_id]);
  $display("[PERF] %s_compress_selection_ratio: %0.6f", class_name,
    perf_ratio(stats.compress_selected_element_count[class_id],
               stats.compress_examined_element_count[class_id]));
  $display("[PERF] %s_window_lifecycle_complete: %0d", class_name,
    stats.insn_count[class_id] == stats.issued_count[class_id] &&
    stats.issued_count[class_id] == stats.completed_count[class_id]);
  $display("[PERF] %s_dispatch_hist_consistent: %0d", class_name,
    dispatch_hist_samples == stats.issued_count[class_id]);
  $display("[PERF] %s_execution_hist_consistent: %0d", class_name,
    execution_hist_samples == stats.completed_count[class_id]);
  $display("[PERF] %s_active_partition_consistent: %0d", class_name,
    stats.issue_progress_cycle[class_id] + stats.no_issue_progress_cycle[class_id] ==
      stats.active_cycle[class_id]);
  $display("[PERF] %s_primary_attribution_partition_consistent: %0d", class_name,
    primary_attribution_samples == stats.active_cycle[class_id]);
  end else begin
  $fwrite(file_handle, "[PERF] %s_exec_insns: %0d\n", class_name, stats.insn_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_issued_insns: %0d\n", class_name, stats.issued_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_completed_insns: %0d\n", class_name, stats.completed_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_accept_to_issue_ratio: %0.6f\n", class_name,
    perf_ratio(stats.issued_count[class_id], stats.insn_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_issue_to_completion_ratio: %0.6f\n", class_name,
    perf_ratio(stats.completed_count[class_id], stats.issued_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_requested_elements: %0d\n", class_name,
    stats.requested_element_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_avg_requested_elements_per_insn: %0.3f\n", class_name,
    perf_ratio(stats.requested_element_count[class_id], stats.insn_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_requested_elements_per_rvv_cycle: %0.6f\n", class_name,
    perf_ratio(stats.requested_element_count[class_id], total_rvv_cycles));
  $fwrite(file_handle, "[PERF] %s_nominal_element_ops: %0d\n", class_name,
    stats.nominal_element_op_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_nominal_element_ops_per_rvv_cycle: %0.6f\n", class_name,
    perf_ratio(stats.nominal_element_op_count[class_id], total_rvv_cycles));
  $fwrite(file_handle, "[PERF] %s_masked_insns: %0d\n", class_name,
    stats.masked_insn_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_masked_insn_ratio: %0.6f\n", class_name,
    perf_ratio(stats.masked_insn_count[class_id], stats.insn_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_reduction_insns: %0d\n", class_name,
    stats.reduction_insn_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_special_path_insns: %0d\n", class_name,
    stats.special_insn_count[class_id]);
  if (class_id inside {ExecLoad, ExecStore}) begin
    $fwrite(file_handle, "[PERF] %s_unit_stride_backend_uops: %0d\n", class_name,
      stats.unit_stride_uop_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_strided_backend_uops: %0d\n", class_name,
      stats.strided_uop_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_indexed_backend_uops: %0d\n", class_name,
      stats.indexed_uop_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_segment_backend_uops: %0d\n", class_name,
      stats.segment_uop_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_fault_only_first_backend_uops: %0d\n", class_name,
      stats.fault_only_first_uop_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_backend_requested_bytes: %0d\n", class_name,
      stats.requested_byte_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_backend_requested_bytes_per_uop: %0.3f\n", class_name,
      perf_ratio(stats.requested_byte_count[class_id], stats.insn_count[class_id]));
  end
  $fwrite(file_handle, "[PERF] %s_sew8_insns: %0d\n", class_name,
    stats.sew_insn_hist[class_id][0]);
  $fwrite(file_handle, "[PERF] %s_sew16_insns: %0d\n", class_name,
    stats.sew_insn_hist[class_id][1]);
  $fwrite(file_handle, "[PERF] %s_sew32_insns: %0d\n", class_name,
    stats.sew_insn_hist[class_id][2]);
  $fwrite(file_handle, "[PERF] %s_sew64_insns: %0d\n", class_name,
    stats.sew_insn_hist[class_id][3]);
  $fwrite(file_handle, "[PERF] %s_active_cycles: %0d\n", class_name, stats.active_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_inflight_insn_cycles: %0d\n", class_name,
    stats.inflight_insn_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_masked_active_cycles: %0d\n", class_name,
    stats.masked_active_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_active_ratio: %0.3f\n", class_name,
    perf_ratio(stats.active_cycle[class_id], total_rvv_cycles));
  $fwrite(file_handle, "[PERF] %s_completion_per_rvv_cycle: %0.6f\n", class_name,
    perf_ratio(stats.completed_count[class_id], total_rvv_cycles));
  $fwrite(file_handle, "[PERF] %s_avg_inflight_when_active: %0.3f\n", class_name,
    perf_ratio(stats.inflight_insn_cycle[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_active_cycles_per_insn: %0.3f\n", class_name,
    perf_ratio(stats.active_cycle[class_id], stats.insn_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_active_cycles_per_completed_insn: %0.3f\n", class_name,
    perf_ratio(stats.active_cycle[class_id], stats.completed_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_requested_elements_per_active_cycle: %0.6f\n", class_name,
    perf_ratio(stats.requested_element_count[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_masked_active_ratio: %0.6f\n", class_name,
    perf_ratio(stats.masked_active_cycle[class_id], stats.active_cycle[class_id]));

  $fwrite(file_handle, "[PERF] %s_dispatch_wait_cycles: %0d\n", class_name,
    stats.dispatch_wait_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_avg_dispatch_wait: %0.3f\n", class_name,
    perf_ratio(stats.dispatch_wait_cycle[class_id], stats.issued_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_dispatch_wait_0_cycles: %0d\n", class_name,
    stats.dispatch_wait_hist[class_id][0]);
  $fwrite(file_handle, "[PERF] %s_dispatch_wait_1_4_cycles: %0d\n", class_name,
    stats.dispatch_wait_hist[class_id][1]);
  $fwrite(file_handle, "[PERF] %s_dispatch_wait_5_16_cycles: %0d\n", class_name,
    stats.dispatch_wait_hist[class_id][2]);
  $fwrite(file_handle, "[PERF] %s_dispatch_wait_gt16_cycles: %0d\n", class_name,
    stats.dispatch_wait_hist[class_id][3]);

  $fwrite(file_handle, "[PERF] %s_execution_latency_cycles: %0d\n", class_name,
    stats.execution_latency_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_avg_execution_latency: %0.3f\n", class_name,
    perf_ratio(stats.execution_latency_cycle[class_id], stats.completed_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_execution_latency_le8: %0d\n", class_name,
    stats.execution_latency_hist[class_id][0]);
  $fwrite(file_handle, "[PERF] %s_execution_latency_9_32: %0d\n", class_name,
    stats.execution_latency_hist[class_id][1]);
  $fwrite(file_handle, "[PERF] %s_execution_latency_33_128: %0d\n", class_name,
    stats.execution_latency_hist[class_id][2]);
  $fwrite(file_handle, "[PERF] %s_execution_latency_gt128: %0d\n", class_name,
    stats.execution_latency_hist[class_id][3]);
  $fwrite(file_handle, "[PERF] %s_end_to_end_latency_cycles: %0d\n", class_name,
    stats.end_to_end_latency_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_avg_end_to_end_latency: %0.3f\n", class_name,
    perf_ratio(stats.end_to_end_latency_cycle[class_id], stats.completed_count[class_id]));

        $fwrite(file_handle, "[PERF] %s_dispatch_request_cycles: %0d\n", class_name,
          stats.dispatch_request_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_dispatch_blocked_cycles: %0d\n", class_name,
          stats.dispatch_blocked_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_dispatch_blocked_ratio: %0.6f\n", class_name,
          perf_ratio(stats.dispatch_blocked_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_fu_queue_full_ratio: %0.6f\n", class_name,
          perf_ratio(stats.fu_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_fu_queue_full_cycles: %0d\n", class_name,
          stats.fu_queue_full_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_mask_queue_full_ratio: %0.6f\n", class_name,
          perf_ratio(stats.mask_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_mask_queue_full_cycles: %0d\n", class_name,
          stats.mask_queue_full_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_slide_queue_full_ratio: %0.6f\n", class_name,
          perf_ratio(stats.slide_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_slide_queue_full_cycles: %0d\n", class_name,
          stats.slide_queue_full_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_id_pool_full_ratio: %0.6f\n", class_name,
          perf_ratio(stats.id_pool_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_id_pool_full_cycles: %0d\n", class_name,
          stats.id_pool_full_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_response_wait_ratio: %0.6f\n", class_name,
          perf_ratio(stats.response_wait_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_response_wait_cycles: %0d\n", class_name,
          stats.response_wait_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_other_dispatch_blocked_ratio: %0.6f\n", class_name,
          perf_ratio(stats.other_dispatch_blocked_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_other_dispatch_blocked_cycles: %0d\n", class_name,
          stats.other_dispatch_blocked_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_operand_request_blocked_ratio: %0.6f\n", class_name,
          perf_ratio(stats.operand_request_blocked_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_operand_request_blocked_cycles: %0d\n", class_name,
          stats.operand_request_blocked_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_fu_queue_full_cycles: %0d\n", class_name,
          stats.primary_fu_queue_full_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_fu_queue_full_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_fu_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_mask_queue_full_cycles: %0d\n", class_name,
          stats.primary_mask_queue_full_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_mask_queue_full_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_mask_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_slide_queue_full_cycles: %0d\n", class_name,
          stats.primary_slide_queue_full_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_slide_queue_full_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_slide_queue_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_id_pool_full_cycles: %0d\n", class_name,
          stats.primary_id_pool_full_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_id_pool_full_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_id_pool_full_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_response_wait_cycles: %0d\n", class_name,
          stats.primary_response_wait_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_response_wait_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_response_wait_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_lane_desync_cycles: %0d\n", class_name,
          stats.primary_lane_desync_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_lane_desync_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_lane_desync_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_sequencer_block_cycles: %0d\n", class_name,
          stats.primary_sequencer_block_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_sequencer_block_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_sequencer_block_cycle[class_id], stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_operand_request_blocked_cycles: %0d\n", class_name,
          stats.primary_operand_request_blocked_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_operand_request_blocked_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_operand_request_blocked_cycle[class_id],
            stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_other_dispatch_blocked_cycles: %0d\n", class_name,
          stats.primary_other_dispatch_blocked_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_other_dispatch_blocked_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_other_dispatch_blocked_cycle[class_id],
            stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_dispatch_unattributed_cycles: %0d\n", class_name,
          stats.primary_dispatch_unattributed_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_primary_dispatch_unattributed_ratio: %0.6f\n", class_name,
          perf_ratio(stats.primary_dispatch_unattributed_cycle[class_id],
            stats.dispatch_request_cycle[class_id]));
        $fwrite(file_handle, "[PERF] %s_primary_dispatch_partition_consistent: %0d\n",
          class_name,
          primary_dispatch_attribution_samples == stats.dispatch_blocked_cycle[class_id]);
        $fwrite(file_handle, "[PERF] %s_dispatch_reasons_within_request: %0d\n", class_name,
          stats.dispatch_blocked_cycle[class_id] <= stats.dispatch_request_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_raw_hazard_cycles: %0d\n", class_name,
      stats.raw_hazard_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_raw_hazard_ratio: %0.6f\n", class_name,
      perf_ratio(stats.raw_hazard_cycle[class_id], stats.active_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_war_hazard_cycles: %0d\n", class_name,
      stats.war_hazard_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_war_hazard_ratio: %0.6f\n", class_name,
      perf_ratio(stats.war_hazard_cycle[class_id], stats.active_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_waw_hazard_cycles: %0d\n", class_name,
      stats.waw_hazard_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_waw_hazard_ratio: %0.6f\n", class_name,
      perf_ratio(stats.waw_hazard_cycle[class_id], stats.active_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_false_hazard_cycles: %0d\n", class_name,
      stats.false_hazard_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_false_hazard_ratio: %0.6f\n", class_name,
      perf_ratio(stats.false_hazard_cycle[class_id], stats.active_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_sequencer_block_cycles: %0d\n", class_name,
      stats.sequencer_block_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_sequencer_block_ratio: %0.6f\n", class_name,
      perf_ratio(stats.sequencer_block_cycle[class_id], stats.active_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_lane_desync_cycles: %0d\n", class_name,
      stats.lane_desync_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_lane_desync_ratio: %0.6f\n", class_name,
      perf_ratio(stats.lane_desync_cycle[class_id], stats.active_cycle[class_id]));

  $fwrite(file_handle, "[PERF] %s_issue_progress_cycles: %0d\n", class_name,
    stats.issue_progress_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_no_issue_progress_cycles: %0d\n", class_name,
    stats.no_issue_progress_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_issue_progress_ratio: %0.6f\n", class_name,
    perf_ratio(stats.issue_progress_cycle[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_no_issue_progress_ratio: %0.6f\n", class_name,
    perf_ratio(stats.no_issue_progress_cycle[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_operand_wait_cycles: %0d\n", class_name,
    stats.operand_wait_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_operand_wait_ratio: %0.6f\n", class_name,
    perf_ratio(stats.operand_wait_cycle[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_unit_input_backpressure_cycles: %0d\n", class_name,
    stats.unit_input_backpressure_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_unit_input_backpressure_ratio: %0.6f\n", class_name,
    perf_ratio(stats.unit_input_backpressure_cycle[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_latency_order_stall_cycles: %0d\n", class_name,
    stats.latency_order_stall_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_result_queue_full_cycles: %0d\n", class_name,
    stats.result_queue_full_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_result_backpressure_cycles: %0d\n", class_name,
    stats.result_backpressure_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_result_backpressure_ratio: %0.6f\n", class_name,
    perf_ratio(stats.result_backpressure_cycle[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_long_latency_busy_cycles: %0d\n", class_name,
    stats.long_latency_busy_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_long_latency_busy_ratio: %0.6f\n", class_name,
    perf_ratio(stats.long_latency_busy_cycle[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_reduction_cycles: %0d\n", class_name,
    stats.reduction_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_cross_lane_cycles: %0d\n", class_name,
    stats.cross_lane_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_special_path_cycles: %0d\n", class_name,
    stats.special_path_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_index_fifo_full_cycles: %0d\n", class_name,
    stats.index_fifo_full_cycle[class_id]);

  $fwrite(file_handle, "[PERF] %s_primary_result_backpressure_cycles: %0d\n", class_name,
    stats.primary_result_backpressure_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_result_queue_full_cycles: %0d\n", class_name,
    stats.primary_result_queue_full_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_latency_order_stall_cycles: %0d\n", class_name,
    stats.primary_latency_order_stall_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_unit_input_backpressure_cycles: %0d\n", class_name,
    stats.primary_unit_input_backpressure_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_operand_wait_cycles: %0d\n", class_name,
    stats.primary_operand_wait_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_long_latency_busy_cycles: %0d\n", class_name,
    stats.primary_long_latency_busy_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_special_path_cycles: %0d\n", class_name,
    stats.primary_special_path_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_progress_cycles: %0d\n", class_name,
    stats.primary_progress_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_unattributed_cycles: %0d\n", class_name,
    stats.primary_unattributed_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_result_backpressure_ratio: %0.6f\n",
    class_name, perf_ratio(stats.primary_result_backpressure_cycle[class_id],
                           stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_primary_result_queue_full_ratio: %0.6f\n",
    class_name, perf_ratio(stats.primary_result_queue_full_cycle[class_id],
                           stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_primary_latency_order_stall_ratio: %0.6f\n",
    class_name, perf_ratio(stats.primary_latency_order_stall_cycle[class_id],
                           stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_primary_unit_input_backpressure_ratio: %0.6f\n",
    class_name, perf_ratio(stats.primary_unit_input_backpressure_cycle[class_id],
                           stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_primary_operand_wait_ratio: %0.6f\n",
    class_name, perf_ratio(stats.primary_operand_wait_cycle[class_id],
                           stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_primary_long_latency_busy_ratio: %0.6f\n",
    class_name, perf_ratio(stats.primary_long_latency_busy_cycle[class_id],
                           stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_primary_special_path_ratio: %0.6f\n",
    class_name, perf_ratio(stats.primary_special_path_cycle[class_id],
                           stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_primary_progress_ratio: %0.6f\n", class_name,
    perf_ratio(stats.primary_progress_cycle[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_primary_unattributed_ratio: %0.6f\n", class_name,
    perf_ratio(stats.primary_unattributed_cycle[class_id], stats.active_cycle[class_id]));

  $fwrite(file_handle, "[PERF] %s_issue_progress_lane_samples: %0d\n", class_name,
    stats.issue_progress_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_avg_progress_lanes_per_active_cycle: %0.3f\n", class_name,
    perf_ratio(stats.issue_progress_lane_sample[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_operand_wait_lane_samples: %0d\n", class_name,
    stats.operand_wait_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_unit_input_backpressure_lane_samples: %0d\n", class_name,
    stats.unit_input_backpressure_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_latency_order_stall_lane_samples: %0d\n", class_name,
    stats.latency_order_stall_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_result_queue_full_lane_samples: %0d\n", class_name,
    stats.result_queue_full_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_result_backpressure_lane_samples: %0d\n", class_name,
    stats.result_backpressure_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_long_latency_busy_lane_samples: %0d\n", class_name,
    stats.long_latency_busy_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_result_queue_occupancy_lane_samples: %0d\n", class_name,
    stats.result_queue_occupancy_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_avg_result_queue_entries_per_active_cycle: %0.3f\n", class_name,
    perf_ratio(stats.result_queue_occupancy_lane_sample[class_id], stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_predicate_packets: %0d\n", class_name,
    stats.predicate_packet_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_predicate_elements: %0d\n", class_name,
    stats.predicate_element_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_predicate_active_elements: %0d\n", class_name,
    stats.predicate_active_element_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_predicate_active_ratio: %0.6f\n", class_name,
    perf_ratio(stats.predicate_active_element_count[class_id],
               stats.predicate_element_count[class_id]));
  for (int unsigned b = 0; b < NrMaskDensityBins; b++)
    $fwrite(file_handle, "[PERF] %s_predicate_density_bin_%0d_packets: %0d\n",
      class_name, b, stats.predicate_density_hist[class_id][b]);
  $fwrite(file_handle, "[PERF] %s_vrf_read_request_lane_samples: %0d\n", class_name,
    stats.vrf_read_request_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_vrf_read_grant_lane_samples: %0d\n", class_name,
    stats.vrf_read_grant_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_vrf_bank_conflict_lane_samples: %0d\n", class_name,
    stats.vrf_bank_conflict_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_vrf_bank_conflict_ratio: %0.6f\n", class_name,
    perf_ratio(stats.vrf_bank_conflict_lane_sample[class_id],
               stats.vrf_read_request_lane_sample[class_id]));
  $fwrite(file_handle, "[PERF] %s_vrf_hazard_stall_lane_samples: %0d\n", class_name,
    stats.vrf_hazard_stall_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_operand_queue_backpressure_lane_samples: %0d\n", class_name,
    stats.operand_queue_backpressure_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_predicate_hist_consistent: %0d\n", class_name,
    predicate_hist_samples == stats.predicate_packet_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_predicate_active_le_total_consistent: %0d\n", class_name,
    stats.predicate_active_element_count[class_id] <= stats.predicate_element_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_vrf_request_partition_consistent: %0d\n", class_name,
    stats.vrf_read_request_lane_sample[class_id] ==
      stats.vrf_read_grant_lane_sample[class_id] +
      stats.vrf_bank_conflict_lane_sample[class_id]);
  if (class_id == ExecMask) begin
    $fwrite(file_handle, "[PERF] mask_operand_incomplete_cycles: %0d\n", stats.mask_operand_incomplete_cycle[class_id]);
    $fwrite(file_handle, "[PERF] mask_issue_end_cycles: %0d\n", stats.mask_issue_end_cycle[class_id]);
    $fwrite(file_handle, "[PERF] mask_commit_pending_cycles: %0d\n", stats.mask_commit_pending_cycle[class_id]);
    $fwrite(file_handle, "[PERF] mask_result_queue_nonempty_cycles: %0d\n", stats.mask_result_queue_nonempty_cycle[class_id]);
    $fwrite(file_handle, "[PERF] mask_final_grant_wait_cycles: %0d\n", stats.mask_final_grant_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] mask_index_fifo_nonempty_cycles: %0d\n", stats.mask_index_fifo_nonempty_cycle[class_id]);
    $fwrite(file_handle, "[PERF] mask_request_fifo_nonempty_cycles: %0d\n", stats.mask_request_fifo_nonempty_cycle[class_id]);
  end
  $fwrite(file_handle, "[PERF] %s_top_primary_exec_bottleneck_reason: %s\n", class_name,
    top_exec_bottleneck_name);
  $fwrite(file_handle, "[PERF] %s_top_primary_exec_bottleneck_cycles: %0d\n", class_name,
    top_exec_bottleneck_count);
  $fwrite(file_handle, "[PERF] %s_top_primary_exec_bottleneck_ratio: %0.6f\n", class_name,
    perf_ratio(top_exec_bottleneck_count, stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_top_secondary_exec_bottleneck_reason: %s\n", class_name,
    second_exec_bottleneck_name);
  $fwrite(file_handle, "[PERF] %s_top_secondary_exec_bottleneck_cycles: %0d\n", class_name,
    second_exec_bottleneck_count);
  $fwrite(file_handle, "[PERF] %s_top_secondary_exec_bottleneck_ratio: %0.6f\n", class_name,
    perf_ratio(second_exec_bottleneck_count, stats.active_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_top_exec_bottleneck_reason_gap: %0d\n", class_name, top_exec_gap);
  $fwrite(file_handle, "[PERF] %s_top_exec_bottleneck_gap_ratio_exec_active: %0.6f\n", class_name,
    top_exec_gap_ratio_exec_active);
  $fwrite(file_handle, "[PERF] %s_top_exec_bottleneck_dominance_ratio: %0.6f\n", class_name,
    top_exec_dominance_ratio);
  $fwrite(file_handle, "[PERF] %s_top_secondary_exec_bottleneck_dominance_ratio: %0.6f\n", class_name,
    second_exec_dominance_ratio);
  $fwrite(file_handle, "[PERF] %s_top_primary_exec_bottleneck_advice: %s\n", class_name,
    exec_bottleneck_advice(top_exec_bottleneck_name));
  $fwrite(file_handle, "[PERF] %s_top_primary_dispatch_bottleneck_reason: %s\n", class_name,
    top_dispatch_bottleneck_name);
  $fwrite(file_handle, "[PERF] %s_top_primary_dispatch_bottleneck_cycles: %0d\n", class_name,
    top_dispatch_bottleneck_count);
  $fwrite(file_handle, "[PERF] %s_top_primary_dispatch_bottleneck_ratio_dispatch_request: %0.6f\n",
    class_name, perf_ratio(top_dispatch_bottleneck_count, stats.dispatch_request_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_top_primary_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f\n",
    class_name, perf_ratio(top_dispatch_bottleneck_count, stats.dispatch_blocked_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_top_secondary_dispatch_bottleneck_reason: %s\n", class_name,
    second_dispatch_bottleneck_name);
  $fwrite(file_handle, "[PERF] %s_top_secondary_dispatch_bottleneck_cycles: %0d\n", class_name,
    second_dispatch_bottleneck_count);
  $fwrite(file_handle, "[PERF] %s_top_secondary_dispatch_bottleneck_ratio_dispatch_request: %0.6f\n",
    class_name, perf_ratio(second_dispatch_bottleneck_count, stats.dispatch_request_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_top_secondary_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f\n",
    class_name, perf_ratio(second_dispatch_bottleneck_count, stats.dispatch_blocked_cycle[class_id]));
  $fwrite(file_handle, "[PERF] %s_top_dispatch_bottleneck_reason_gap: %0d\n", class_name,
    top_dispatch_gap);
  $fwrite(file_handle, "[PERF] %s_top_dispatch_bottleneck_gap_ratio_dispatch_request: %0.6f\n", class_name,
    top_dispatch_gap_ratio_dispatch_request);
  $fwrite(file_handle, "[PERF] %s_top_dispatch_bottleneck_dominance_ratio: %0.6f\n", class_name,
    top_dispatch_dominance_ratio);
  $fwrite(file_handle, "[PERF] %s_top_secondary_dispatch_bottleneck_dominance_ratio: %0.6f\n", class_name,
    second_dispatch_dominance_ratio);
  $fwrite(file_handle, "[PERF] %s_top_primary_dispatch_bottleneck_advice: %s\n", class_name,
    dispatch_bottleneck_advice(top_dispatch_bottleneck_name));
  $fwrite(file_handle, "[PERF] %s_mask_index_fifo_pushes: %0d\n", class_name,
    stats.mask_index_fifo_push_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_mask_index_fifo_pops: %0d\n", class_name,
    stats.mask_index_fifo_pop_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_gather_request_fifo_pushes: %0d\n", class_name,
    stats.gather_request_fifo_push_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_gather_request_fifo_pops: %0d\n", class_name,
    stats.gather_request_fifo_pop_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_gather_broadcast_request_lane_samples: %0d\n", class_name,
    stats.gather_broadcast_request_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_gather_broadcast_grant_lane_samples: %0d\n", class_name,
    stats.gather_broadcast_grant_lane_sample[class_id]);
  $fwrite(file_handle, "[PERF] %s_gather_broadcast_grant_ratio: %0.6f\n", class_name,
    perf_ratio(stats.gather_broadcast_grant_lane_sample[class_id],
               stats.gather_broadcast_request_lane_sample[class_id]));
  $fwrite(file_handle, "[PERF] %s_gather_out_of_range_indices: %0d\n", class_name,
    stats.gather_out_of_range_index_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_compress_examined_elements: %0d\n", class_name,
    stats.compress_examined_element_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_compress_selected_elements: %0d\n", class_name,
    stats.compress_selected_element_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_compress_selection_ratio: %0.6f\n", class_name,
    perf_ratio(stats.compress_selected_element_count[class_id],
               stats.compress_examined_element_count[class_id]));
  $fwrite(file_handle, "[PERF] %s_window_lifecycle_complete: %0d\n", class_name,
    stats.insn_count[class_id] == stats.issued_count[class_id] &&
    stats.issued_count[class_id] == stats.completed_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_dispatch_hist_consistent: %0d\n", class_name,
    dispatch_hist_samples == stats.issued_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_execution_hist_consistent: %0d\n", class_name,
    execution_hist_samples == stats.completed_count[class_id]);
  $fwrite(file_handle, "[PERF] %s_active_partition_consistent: %0d\n", class_name,
    stats.issue_progress_cycle[class_id] + stats.no_issue_progress_cycle[class_id] ==
      stats.active_cycle[class_id]);
  $fwrite(file_handle, "[PERF] %s_primary_attribution_partition_consistent: %0d\n", class_name,
    primary_attribution_samples == stats.active_cycle[class_id]);
  end
endfunction

function automatic string mfpu_subunit_name(input int unsigned unit);
  case (unit)
    0: return "mul";
    1: return "div";
    default: return "fpnew";
  endcase
endfunction

function automatic void print_deep_exec_report(
  input integer file_handle,
  input exec_perf_t stats,
  input logic [63:0] total_rvv_cycles
);
  if (file_handle == 0) begin
    $display("[PERF] ==== Deep Execution / State Attribution ====");
    for (int unsigned u = 0; u < NrMfpuSubunits; u++) begin
      $display("[PERF] %s_input_fire_lane_samples: %0d", mfpu_subunit_name(u),
        stats.mfpu_input_fire_lane_sample[u]);
      $display("[PERF] %s_input_backpressure_lane_samples: %0d", mfpu_subunit_name(u),
        stats.mfpu_input_backpressure_lane_sample[u]);
      $display("[PERF] %s_output_fire_lane_samples: %0d", mfpu_subunit_name(u),
        stats.mfpu_output_fire_lane_sample[u]);
      $display("[PERF] %s_processing_lane_samples: %0d", mfpu_subunit_name(u),
        stats.mfpu_processing_lane_sample[u]);
      $display("[PERF] %s_input_fire_per_rvv_cycle: %0.6f", mfpu_subunit_name(u),
        perf_ratio(stats.mfpu_input_fire_lane_sample[u], total_rvv_cycles));
    end
    for (int unsigned s = 0; s < NrValuStates; s++)
      $display("[PERF] valu_state_%0d_lane_samples: %0d", s, stats.valu_state_lane_sample[s]);
    for (int unsigned s = 0; s < NrMfpuStates; s++)
      $display("[PERF] mfpu_state_%0d_lane_samples: %0d", s, stats.mfpu_state_lane_sample[s]);
    for (int unsigned s = 0; s < NrSlduStates; s++)
      $display("[PERF] sldu_state_%0d_cycles: %0d", s, stats.sldu_state_cycle[s]);
  end else begin
    $fwrite(file_handle, "[PERF] ==== Deep Execution / State Attribution ====\n");
    for (int unsigned u = 0; u < NrMfpuSubunits; u++) begin
      $fwrite(file_handle, "[PERF] %s_input_fire_lane_samples: %0d\n", mfpu_subunit_name(u),
        stats.mfpu_input_fire_lane_sample[u]);
      $fwrite(file_handle, "[PERF] %s_input_backpressure_lane_samples: %0d\n", mfpu_subunit_name(u),
        stats.mfpu_input_backpressure_lane_sample[u]);
      $fwrite(file_handle, "[PERF] %s_output_fire_lane_samples: %0d\n", mfpu_subunit_name(u),
        stats.mfpu_output_fire_lane_sample[u]);
      $fwrite(file_handle, "[PERF] %s_processing_lane_samples: %0d\n", mfpu_subunit_name(u),
        stats.mfpu_processing_lane_sample[u]);
      $fwrite(file_handle, "[PERF] %s_input_fire_per_rvv_cycle: %0.6f\n", mfpu_subunit_name(u),
        perf_ratio(stats.mfpu_input_fire_lane_sample[u], total_rvv_cycles));
    end
    for (int unsigned s = 0; s < NrValuStates; s++)
      $fwrite(file_handle, "[PERF] valu_state_%0d_lane_samples: %0d\n", s,
        stats.valu_state_lane_sample[s]);
    for (int unsigned s = 0; s < NrMfpuStates; s++)
      $fwrite(file_handle, "[PERF] mfpu_state_%0d_lane_samples: %0d\n", s,
        stats.mfpu_state_lane_sample[s]);
    for (int unsigned s = 0; s < NrSlduStates; s++)
      $fwrite(file_handle, "[PERF] sldu_state_%0d_cycles: %0d\n", s,
        stats.sldu_state_cycle[s]);
  end
endfunction

function automatic void print_arch_class_report(
  input integer         file_handle,
  input string          class_name,
  input exec_class_e    class_id,
  input frontend_perf_t stats,
  input exec_perf_t     backend
);
  if (file_handle == 0) begin
    $display("[PERF] %s_arch_insns: %0d", class_name, stats.arch_insn_count[class_id]);
    $display("[PERF] %s_zero_vl_nop_insns: %0d", class_name,
      stats.zero_vl_nop_count[class_id]);
    $display("[PERF] %s_zero_vl_nop_ratio: %0.6f", class_name,
      perf_ratio(stats.zero_vl_nop_count[class_id], stats.arch_insn_count[class_id]));
    $display("[PERF] %s_backend_uops_per_arch_insn: %0.6f", class_name,
      perf_ratio(backend.insn_count[class_id], stats.arch_insn_count[class_id]));
    $display("[PERF] %s_nonzero_backend_coverage_ratio: %0.6f", class_name,
      perf_ratio(backend.insn_count[class_id],
        stats.arch_insn_count[class_id] - stats.zero_vl_nop_count[class_id]));
  end else begin
    $fwrite(file_handle, "[PERF] %s_arch_insns: %0d\n", class_name,
      stats.arch_insn_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_zero_vl_nop_insns: %0d\n", class_name,
      stats.zero_vl_nop_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_zero_vl_nop_ratio: %0.6f\n", class_name,
      perf_ratio(stats.zero_vl_nop_count[class_id], stats.arch_insn_count[class_id]));
    $fwrite(file_handle, "[PERF] %s_backend_uops_per_arch_insn: %0.6f\n", class_name,
      perf_ratio(backend.insn_count[class_id], stats.arch_insn_count[class_id]));
    $fwrite(file_handle, "[PERF] %s_nonzero_backend_coverage_ratio: %0.6f\n", class_name,
      perf_ratio(backend.insn_count[class_id],
        stats.arch_insn_count[class_id] - stats.zero_vl_nop_count[class_id]));
  end
endfunction

function automatic void print_arch_memory_report(
  input integer         file_handle,
  input string          class_name,
  input mem_class_e     class_id,
  input frontend_perf_t stats
);
  logic [63:0] address_mode_samples;
  address_mode_samples = stats.memory_unit_stride_count[class_id] +
                         stats.memory_strided_count[class_id] +
                         stats.memory_indexed_unordered_count[class_id] +
                         stats.memory_indexed_ordered_count[class_id];
  if (file_handle == 0) begin
    $display("[PERF] %s_arch_memory_insns: %0d", class_name,
      stats.memory_insn_count[class_id]);
    $display("[PERF] %s_arch_unit_stride_insns: %0d", class_name,
      stats.memory_unit_stride_count[class_id]);
    $display("[PERF] %s_arch_strided_insns: %0d", class_name,
      stats.memory_strided_count[class_id]);
    $display("[PERF] %s_arch_indexed_unordered_insns: %0d", class_name,
      stats.memory_indexed_unordered_count[class_id]);
    $display("[PERF] %s_arch_indexed_ordered_insns: %0d", class_name,
      stats.memory_indexed_ordered_count[class_id]);
    $display("[PERF] %s_arch_segment_insns: %0d", class_name,
      stats.memory_segment_count[class_id]);
    $display("[PERF] %s_arch_whole_register_insns: %0d", class_name,
      stats.memory_whole_register_count[class_id]);
    $display("[PERF] %s_arch_mask_memory_insns: %0d", class_name,
      stats.memory_mask_count[class_id]);
    $display("[PERF] %s_arch_memory_fields: %0d", class_name,
      stats.memory_field_count[class_id]);
    $display("[PERF] %s_avg_fields_per_arch_insn: %0.3f", class_name,
      perf_ratio(stats.memory_field_count[class_id], stats.memory_insn_count[class_id]));
    $display("[PERF] %s_arch_requested_elements: %0d", class_name,
      stats.memory_requested_element_count[class_id]);
    $display("[PERF] %s_arch_requested_bytes: %0d", class_name,
      stats.memory_requested_byte_count[class_id]);
    $display("[PERF] %s_avg_requested_bytes_per_arch_insn: %0.3f", class_name,
      perf_ratio(stats.memory_requested_byte_count[class_id], stats.memory_insn_count[class_id]));
    $display("[PERF] %s_arch_memory_exceptions: %0d", class_name,
      stats.memory_exception_count[class_id]);
    $display("[PERF] %s_accepted_memory_insns: %0d", class_name,
      stats.memory_accepted_count[class_id]);
    $display("[PERF] %s_accepted_unit_stride_insns: %0d", class_name,
      stats.memory_accepted_unit_stride_count[class_id]);
    $display("[PERF] %s_accepted_strided_insns: %0d", class_name,
      stats.memory_accepted_strided_count[class_id]);
    $display("[PERF] %s_accepted_indexed_unordered_insns: %0d", class_name,
      stats.memory_accepted_indexed_unordered_count[class_id]);
    $display("[PERF] %s_accepted_indexed_ordered_insns: %0d", class_name,
      stats.memory_accepted_indexed_ordered_count[class_id]);
    $display("[PERF] %s_accepted_segment_insns: %0d", class_name,
      stats.memory_accepted_segment_count[class_id]);
    $display("[PERF] %s_accepted_whole_register_insns: %0d", class_name,
      stats.memory_accepted_whole_register_count[class_id]);
    $display("[PERF] %s_accepted_mask_memory_insns: %0d", class_name,
      stats.memory_accepted_mask_count[class_id]);
    $display("[PERF] %s_arch_address_mode_hist_consistent: %0d", class_name,
      address_mode_samples == stats.memory_insn_count[class_id]);
  end else begin
    $fwrite(file_handle, "[PERF] %s_arch_memory_insns: %0d\n", class_name,
      stats.memory_insn_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_unit_stride_insns: %0d\n", class_name,
      stats.memory_unit_stride_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_strided_insns: %0d\n", class_name,
      stats.memory_strided_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_indexed_unordered_insns: %0d\n", class_name,
      stats.memory_indexed_unordered_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_indexed_ordered_insns: %0d\n", class_name,
      stats.memory_indexed_ordered_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_segment_insns: %0d\n", class_name,
      stats.memory_segment_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_whole_register_insns: %0d\n", class_name,
      stats.memory_whole_register_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_mask_memory_insns: %0d\n", class_name,
      stats.memory_mask_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_memory_fields: %0d\n", class_name,
      stats.memory_field_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_avg_fields_per_arch_insn: %0.3f\n", class_name,
      perf_ratio(stats.memory_field_count[class_id], stats.memory_insn_count[class_id]));
    $fwrite(file_handle, "[PERF] %s_arch_requested_elements: %0d\n", class_name,
      stats.memory_requested_element_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_requested_bytes: %0d\n", class_name,
      stats.memory_requested_byte_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_avg_requested_bytes_per_arch_insn: %0.3f\n", class_name,
      perf_ratio(stats.memory_requested_byte_count[class_id], stats.memory_insn_count[class_id]));
    $fwrite(file_handle, "[PERF] %s_arch_memory_exceptions: %0d\n", class_name,
      stats.memory_exception_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_accepted_memory_insns: %0d\n", class_name,
      stats.memory_accepted_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_accepted_unit_stride_insns: %0d\n", class_name,
      stats.memory_accepted_unit_stride_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_accepted_strided_insns: %0d\n", class_name,
      stats.memory_accepted_strided_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_accepted_indexed_unordered_insns: %0d\n", class_name,
      stats.memory_accepted_indexed_unordered_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_accepted_indexed_ordered_insns: %0d\n", class_name,
      stats.memory_accepted_indexed_ordered_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_accepted_segment_insns: %0d\n", class_name,
      stats.memory_accepted_segment_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_accepted_whole_register_insns: %0d\n", class_name,
      stats.memory_accepted_whole_register_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_accepted_mask_memory_insns: %0d\n", class_name,
      stats.memory_accepted_mask_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_arch_address_mode_hist_consistent: %0d\n", class_name,
      address_mode_samples == stats.memory_insn_count[class_id]);
  end
endfunction

function automatic void print_frontend_report(
  input integer         file_handle,
  input frontend_perf_t stats,
  input exec_perf_t     backend
);
  logic [63:0] vset_count;
  logic [63:0] vset_sew_samples;
  vset_count = stats.vsetvli_count + stats.vsetivli_count + stats.vsetvl_count;
  vset_sew_samples = stats.vset_sew_hist[0] + stats.vset_sew_hist[1] +
                     stats.vset_sew_hist[2] + stats.vset_sew_hist[3];
  if (file_handle == 0) begin
    $display("[PERF] ==== Architectural RVV Instruction Stream ====");
  end else begin
    $fwrite(file_handle, "[PERF] ==== Architectural RVV Instruction Stream ====\n");
  end
  print_arch_class_report(file_handle, "valu", ExecValu, stats, backend);
  print_arch_class_report(file_handle, "mul", ExecMul, stats, backend);
  print_arch_class_report(file_handle, "div", ExecDiv, stats, backend);
  print_arch_class_report(file_handle, "fp", ExecFp, stats, backend);
  print_arch_class_report(file_handle, "slide", ExecSlide, stats, backend);
  print_arch_class_report(file_handle, "mask", ExecMask, stats, backend);
  print_arch_class_report(file_handle, "load", ExecLoad, stats, backend);
  print_arch_class_report(file_handle, "store", ExecStore, stats, backend);
  print_arch_class_report(file_handle, "move_to_vec", ExecMoveToVec, stats, backend);
  print_arch_class_report(file_handle, "move_from_vec", ExecMoveFromVec, stats, backend);
  if (file_handle == 0) begin
    $display("[PERF] frontend_unclassified_arch_insns: %0d",
      stats.unclassified_arch_insn_count);
    $display("[PERF] frontend_arch_exceptions: %0d", stats.arch_exception_count);
    $display("[PERF] ==== RVV Configuration / Vector CSR ====");
    $display("[PERF] config_insns: %0d", stats.config_insn_count);
    $display("[PERF] vsetvli_insns: %0d", stats.vsetvli_count);
    $display("[PERF] vsetivli_insns: %0d", stats.vsetivli_count);
    $display("[PERF] vsetvl_insns: %0d", stats.vsetvl_count);
    $display("[PERF] vector_csr_insns: %0d", stats.vector_csr_count);
    $display("[PERF] vector_csr_write_insns: %0d", stats.vector_csr_write_count);
    $display("[PERF] vector_csr_read_only_insns: %0d", stats.vector_csr_read_only_count);
    $display("[PERF] config_request_cycles: %0d", stats.config_request_cycle);
    $display("[PERF] config_blocked_cycles: %0d", stats.config_blocked_cycle);
    $display("[PERF] config_blocked_ratio: %0.6f",
      perf_ratio(stats.config_blocked_cycle, stats.config_request_cycle));
    $display("[PERF] config_wait_idle_cycles: %0d", stats.config_wait_idle_cycle);
    $display("[PERF] config_wait_backend_busy_cycles: %0d", stats.config_wait_backend_busy_cycle);
    $display("[PERF] config_wait_ara_ready_cycles: %0d", stats.config_wait_ara_ready_cycle);
    $display("[PERF] config_wait_reshuffle_cycles: %0d", stats.config_wait_reshuffle_cycle);
    $display("[PERF] config_other_blocked_cycles: %0d", stats.config_other_blocked_cycle);
    $display("[PERF] vset_result_vl_sum: %0d", stats.vset_result_vl_sum);
    $display("[PERF] vset_avg_result_vl: %0.3f", perf_ratio(stats.vset_result_vl_sum, vset_count));
    $display("[PERF] vset_zero_vl_insns: %0d", stats.vset_zero_vl_count);
    $display("[PERF] vset_vill_insns: %0d", stats.vset_vill_count);
    $display("[PERF] vset_vl_change_insns: %0d", stats.vset_vl_change_count);
    $display("[PERF] vset_vtype_change_insns: %0d", stats.vset_vtype_change_count);
    $display("[PERF] vset_lmul_shrink_wait_insns: %0d", stats.vset_lmul_shrink_wait_count);
    $display("[PERF] vset_sew8_insns: %0d", stats.vset_sew_hist[0]);
    $display("[PERF] vset_sew16_insns: %0d", stats.vset_sew_hist[1]);
    $display("[PERF] vset_sew32_insns: %0d", stats.vset_sew_hist[2]);
    $display("[PERF] vset_sew64_insns: %0d", stats.vset_sew_hist[3]);
    for (int unsigned lmul = 0; lmul < 8; lmul++)
      $display("[PERF] vset_lmul_encoding_%0d_insns: %0d", lmul,
        stats.vset_lmul_hist[lmul]);
    $display("[PERF] config_subtype_hist_consistent: %0d",
      vset_count + stats.vector_csr_count == stats.config_insn_count);
    $display("[PERF] vset_sew_hist_consistent: %0d", vset_sew_samples == vset_count);
    $display("[PERF] load_fault_only_first_insns: %0d", stats.load_fault_only_first_count);
    $display("[PERF] load_accepted_fault_only_first_insns: %0d",
      stats.load_accepted_fault_only_first_count);
  end else begin
    $fwrite(file_handle, "[PERF] frontend_unclassified_arch_insns: %0d\n",
      stats.unclassified_arch_insn_count);
    $fwrite(file_handle, "[PERF] frontend_arch_exceptions: %0d\n",
      stats.arch_exception_count);
    $fwrite(file_handle, "[PERF] ==== RVV Configuration / Vector CSR ====\n");
    $fwrite(file_handle, "[PERF] config_insns: %0d\n", stats.config_insn_count);
    $fwrite(file_handle, "[PERF] vsetvli_insns: %0d\n", stats.vsetvli_count);
    $fwrite(file_handle, "[PERF] vsetivli_insns: %0d\n", stats.vsetivli_count);
    $fwrite(file_handle, "[PERF] vsetvl_insns: %0d\n", stats.vsetvl_count);
    $fwrite(file_handle, "[PERF] vector_csr_insns: %0d\n", stats.vector_csr_count);
    $fwrite(file_handle, "[PERF] vector_csr_write_insns: %0d\n", stats.vector_csr_write_count);
    $fwrite(file_handle, "[PERF] vector_csr_read_only_insns: %0d\n", stats.vector_csr_read_only_count);
    $fwrite(file_handle, "[PERF] config_request_cycles: %0d\n", stats.config_request_cycle);
    $fwrite(file_handle, "[PERF] config_blocked_cycles: %0d\n", stats.config_blocked_cycle);
    $fwrite(file_handle, "[PERF] config_blocked_ratio: %0.6f\n",
      perf_ratio(stats.config_blocked_cycle, stats.config_request_cycle));
    $fwrite(file_handle, "[PERF] config_wait_idle_cycles: %0d\n", stats.config_wait_idle_cycle);
    $fwrite(file_handle, "[PERF] config_wait_backend_busy_cycles: %0d\n", stats.config_wait_backend_busy_cycle);
    $fwrite(file_handle, "[PERF] config_wait_ara_ready_cycles: %0d\n", stats.config_wait_ara_ready_cycle);
    $fwrite(file_handle, "[PERF] config_wait_reshuffle_cycles: %0d\n", stats.config_wait_reshuffle_cycle);
    $fwrite(file_handle, "[PERF] config_other_blocked_cycles: %0d\n", stats.config_other_blocked_cycle);
    $fwrite(file_handle, "[PERF] vset_result_vl_sum: %0d\n", stats.vset_result_vl_sum);
    $fwrite(file_handle, "[PERF] vset_avg_result_vl: %0.3f\n",
      perf_ratio(stats.vset_result_vl_sum, vset_count));
    $fwrite(file_handle, "[PERF] vset_zero_vl_insns: %0d\n", stats.vset_zero_vl_count);
    $fwrite(file_handle, "[PERF] vset_vill_insns: %0d\n", stats.vset_vill_count);
    $fwrite(file_handle, "[PERF] vset_vl_change_insns: %0d\n", stats.vset_vl_change_count);
    $fwrite(file_handle, "[PERF] vset_vtype_change_insns: %0d\n", stats.vset_vtype_change_count);
    $fwrite(file_handle, "[PERF] vset_lmul_shrink_wait_insns: %0d\n", stats.vset_lmul_shrink_wait_count);
    $fwrite(file_handle, "[PERF] vset_sew8_insns: %0d\n", stats.vset_sew_hist[0]);
    $fwrite(file_handle, "[PERF] vset_sew16_insns: %0d\n", stats.vset_sew_hist[1]);
    $fwrite(file_handle, "[PERF] vset_sew32_insns: %0d\n", stats.vset_sew_hist[2]);
    $fwrite(file_handle, "[PERF] vset_sew64_insns: %0d\n", stats.vset_sew_hist[3]);
    for (int unsigned lmul = 0; lmul < 8; lmul++)
      $fwrite(file_handle, "[PERF] vset_lmul_encoding_%0d_insns: %0d\n", lmul,
        stats.vset_lmul_hist[lmul]);
    $fwrite(file_handle, "[PERF] config_subtype_hist_consistent: %0d\n",
      vset_count + stats.vector_csr_count == stats.config_insn_count);
    $fwrite(file_handle, "[PERF] vset_sew_hist_consistent: %0d\n",
      vset_sew_samples == vset_count);
    $fwrite(file_handle, "[PERF] load_fault_only_first_insns: %0d\n",
      stats.load_fault_only_first_count);
    $fwrite(file_handle, "[PERF] load_accepted_fault_only_first_insns: %0d\n",
      stats.load_accepted_fault_only_first_count);
  end
  print_arch_memory_report(file_handle, "load", MemLoad, stats);
  print_arch_memory_report(file_handle, "store", MemStore, stats);
endfunction

function automatic void print_opcode_report(
  input integer         file_handle,
  input frontend_perf_t frontend,
  input exec_perf_t     backend,
  input logic [63:0]    total_rvv_cycles
);
  if (file_handle == 0)
    $display("[PERF] ==== Opcode-level RVV Breakdown ====");
  else
    $fwrite(file_handle, "[PERF] ==== Opcode-level RVV Breakdown ====\n");

  for (int unsigned op = 0; op < NrAraOps; op++) begin
    if (frontend.arch_opcode_count[op] != '0 || backend.opcode_uop_count[op] != '0 ||
        backend.opcode_completed_count[op] != '0) begin
      automatic ara_op_e op_e = ara_op_e'(op);
      automatic string op_name = op_e.name();
      automatic logic [63:0] latency_hist_samples =
        backend.opcode_execution_latency_hist[op][0] +
        backend.opcode_execution_latency_hist[op][1] +
        backend.opcode_execution_latency_hist[op][2] +
        backend.opcode_execution_latency_hist[op][3];
      automatic logic [63:0] sew_samples = backend.opcode_sew_hist[op][0] +
        backend.opcode_sew_hist[op][1] + backend.opcode_sew_hist[op][2] +
        backend.opcode_sew_hist[op][3];
      automatic logic [63:0] dispatch_hist_samples =
        backend.opcode_dispatch_wait_hist[op][0] +
        backend.opcode_dispatch_wait_hist[op][1] +
        backend.opcode_dispatch_wait_hist[op][2] +
        backend.opcode_dispatch_wait_hist[op][3];
      automatic logic [63:0] primary_dispatch_attribution_samples;
      automatic logic [63:0] primary_exec_attribution_samples;
      automatic logic [63:0] top_dispatch_bottleneck_count;
      automatic string top_dispatch_bottleneck_name;
      automatic logic [63:0] top_exec_bottleneck_count;
      automatic string top_exec_bottleneck_name;
      automatic logic [63:0] second_dispatch_bottleneck_count;
      automatic string second_dispatch_bottleneck_name;
      automatic logic [63:0] second_exec_bottleneck_count;
      automatic string second_exec_bottleneck_name;
      automatic logic [63:0] top_exec_gap;
      automatic logic [63:0] top_dispatch_gap;
      automatic real top_exec_dominance_ratio;
      automatic real second_exec_dominance_ratio;
      automatic real top_dispatch_dominance_ratio;
      automatic real second_dispatch_dominance_ratio;
      automatic real top_exec_gap_ratio_exec_active;
      automatic real top_dispatch_gap_ratio_dispatch_request;
      automatic logic [63:0] lmul_samples = '0;
      automatic logic [63:0] shape_uop_samples = '0;
      automatic logic [63:0] shape_completed_samples = '0;
      automatic logic [63:0] nonzero_arch_insns =
        frontend.arch_opcode_count[op] >= frontend.arch_opcode_zero_vl_count[op]
          ? frontend.arch_opcode_count[op] - frontend.arch_opcode_zero_vl_count[op]
          : 0;
      for (int unsigned lmul = 0; lmul < 8; lmul++)
        lmul_samples += backend.opcode_lmul_hist[op][lmul];
      primary_dispatch_attribution_samples =
        backend.opcode_primary_fu_queue_full_cycle[op] +
        backend.opcode_primary_mask_queue_full_cycle[op] +
        backend.opcode_primary_slide_queue_full_cycle[op] +
        backend.opcode_primary_id_pool_full_cycle[op] +
        backend.opcode_primary_response_wait_cycle[op] +
        backend.opcode_primary_lane_desync_cycle[op] +
        backend.opcode_primary_sequencer_block_cycle[op] +
        backend.opcode_primary_operand_request_blocked_cycle[op] +
        backend.opcode_primary_other_dispatch_blocked_cycle[op] +
        backend.opcode_primary_dispatch_unattributed_cycle[op];
      primary_exec_attribution_samples =
        backend.opcode_primary_result_backpressure_cycle[op] +
        backend.opcode_primary_result_queue_full_cycle[op] +
        backend.opcode_primary_latency_order_stall_cycle[op] +
        backend.opcode_primary_unit_input_backpressure_cycle[op] +
        backend.opcode_primary_operand_wait_cycle[op] +
        backend.opcode_primary_long_latency_busy_cycle[op] +
        backend.opcode_primary_special_path_cycle[op] +
        backend.opcode_primary_progress_cycle[op] +
        backend.opcode_primary_unattributed_cycle[op];
      top_dispatch_bottleneck_count = '0;
      top_dispatch_bottleneck_name = "none";
      second_dispatch_bottleneck_count = '0;
      second_dispatch_bottleneck_name = "none";
      top_exec_bottleneck_count = '0;
      top_exec_bottleneck_name = "none";
      second_exec_bottleneck_count = '0;
      second_exec_bottleneck_name = "none";

      update_top2(
        backend.opcode_primary_fu_queue_full_cycle[op], "primary_fu_queue_full",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_mask_queue_full_cycle[op], "primary_mask_queue_full",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_slide_queue_full_cycle[op], "primary_slide_queue_full",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_id_pool_full_cycle[op], "primary_id_pool_full",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_response_wait_cycle[op], "primary_response_wait",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_lane_desync_cycle[op], "primary_lane_desync",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_sequencer_block_cycle[op], "primary_sequencer_block",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_operand_request_blocked_cycle[op], "primary_operand_request_blocked",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_other_dispatch_blocked_cycle[op], "primary_other_dispatch_blocked",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_dispatch_unattributed_cycle[op], "primary_dispatch_unattributed",
        top_dispatch_bottleneck_count, top_dispatch_bottleneck_name,
        second_dispatch_bottleneck_count, second_dispatch_bottleneck_name);
      update_top2(
        backend.opcode_primary_result_backpressure_cycle[op], "primary_result_backpressure",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);
      update_top2(
        backend.opcode_primary_result_queue_full_cycle[op], "primary_result_queue_full",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);
      update_top2(
        backend.opcode_primary_latency_order_stall_cycle[op], "primary_latency_order_stall",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);
      update_top2(
        backend.opcode_primary_unit_input_backpressure_cycle[op], "primary_unit_input_backpressure",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);
      update_top2(
        backend.opcode_primary_operand_wait_cycle[op], "primary_operand_wait",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);
      update_top2(
        backend.opcode_primary_long_latency_busy_cycle[op], "primary_long_latency_busy",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);
      update_top2(
        backend.opcode_primary_special_path_cycle[op], "primary_special_path",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);
      update_top2(
        backend.opcode_primary_progress_cycle[op], "primary_progress",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);
      update_top2(
        backend.opcode_primary_unattributed_cycle[op], "primary_unattributed",
        top_exec_bottleneck_count, top_exec_bottleneck_name,
        second_exec_bottleneck_count, second_exec_bottleneck_name);

      top_exec_gap = (top_exec_bottleneck_count >= second_exec_bottleneck_count) ?
                     (top_exec_bottleneck_count - second_exec_bottleneck_count) : 0;
      top_dispatch_gap = (top_dispatch_bottleneck_count >= second_dispatch_bottleneck_count) ?
                        (top_dispatch_bottleneck_count - second_dispatch_bottleneck_count) : 0;
      top_exec_dominance_ratio = perf_ratio(top_exec_bottleneck_count, primary_exec_attribution_samples);
      top_dispatch_dominance_ratio = perf_ratio(top_dispatch_bottleneck_count,
                                               primary_dispatch_attribution_samples);
      second_exec_dominance_ratio = perf_ratio(second_exec_bottleneck_count, primary_exec_attribution_samples);
      second_dispatch_dominance_ratio = perf_ratio(second_dispatch_bottleneck_count,
                                                  primary_dispatch_attribution_samples);
      top_exec_gap_ratio_exec_active = perf_ratio(top_exec_gap, backend.opcode_active_cycle[op]);
      top_dispatch_gap_ratio_dispatch_request = perf_ratio(
        top_dispatch_gap,
        backend.opcode_dispatch_request_cycle[op]
      );
      for (int unsigned sew = 0; sew < 4; sew++) begin
        for (int unsigned lmul = 0; lmul < 8; lmul++) begin
          shape_uop_samples += backend.opcode_shape_uop_count[op][sew][lmul];
          shape_completed_samples += backend.opcode_shape_completed_count[op][sew][lmul];
        end
      end

      if (file_handle == 0) begin
        $display("[PERF] op_%s_arch_insns: %0d", op_name, frontend.arch_opcode_count[op]);
        $display("[PERF] op_%s_zero_vl_nop_insns: %0d", op_name,
          frontend.arch_opcode_zero_vl_count[op]);
        $display("[PERF] op_%s_backend_uops: %0d", op_name, backend.opcode_uop_count[op]);
        $display("[PERF] op_%s_backend_uops_per_arch_insn: %0.6f", op_name,
          perf_ratio(backend.opcode_uop_count[op], frontend.arch_opcode_count[op]));
        $display("[PERF] op_%s_nonzero_backend_coverage_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_uop_count[op], nonzero_arch_insns));
        $display("[PERF] op_%s_completed_uops: %0d", op_name,
          backend.opcode_completed_count[op]);
        $display("[PERF] op_%s_completion_per_backend_uop: %0.6f", op_name,
          perf_ratio(backend.opcode_completed_count[op], backend.opcode_uop_count[op]));
        $display("[PERF] op_%s_requested_elements: %0d", op_name,
          backend.opcode_requested_element_count[op]);
        $display("[PERF] op_%s_avg_requested_elements_per_uop: %0.3f", op_name,
          perf_ratio(backend.opcode_requested_element_count[op],
                     backend.opcode_uop_count[op]));
        $display("[PERF] op_%s_nominal_element_ops: %0d", op_name,
          backend.opcode_nominal_element_op_count[op]);
        $display("[PERF] op_%s_nominal_element_ops_per_rvv_cycle: %0.6f", op_name,
          perf_ratio(backend.opcode_nominal_element_op_count[op], total_rvv_cycles));
        $display("[PERF] op_%s_masked_uops: %0d", op_name,
          backend.opcode_masked_count[op]);
        $display("[PERF] op_%s_masked_uop_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_masked_count[op], backend.opcode_uop_count[op]));
        $display("[PERF] op_%s_dispatch_request_cycles: %0d", op_name,
          backend.opcode_dispatch_request_cycle[op]);
        $display("[PERF] op_%s_dispatch_blocked_cycles: %0d", op_name,
          backend.opcode_dispatch_blocked_cycle[op]);
        $display("[PERF] op_%s_dispatch_blocked_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_dispatch_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_fu_queue_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_fu_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_fu_queue_full_cycles: %0d", op_name,
          backend.opcode_fu_queue_full_cycle[op]);
        $display("[PERF] op_%s_mask_queue_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_mask_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_mask_queue_full_cycles: %0d", op_name,
          backend.opcode_mask_queue_full_cycle[op]);
        $display("[PERF] op_%s_slide_queue_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_slide_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_slide_queue_full_cycles: %0d", op_name,
          backend.opcode_slide_queue_full_cycle[op]);
        $display("[PERF] op_%s_id_pool_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_id_pool_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_id_pool_full_cycles: %0d", op_name,
          backend.opcode_id_pool_full_cycle[op]);
        $display("[PERF] op_%s_response_wait_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_response_wait_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_response_wait_cycles: %0d", op_name,
          backend.opcode_response_wait_cycle[op]);
        $display("[PERF] op_%s_other_dispatch_blocked_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_other_dispatch_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_other_dispatch_blocked_cycles: %0d", op_name,
          backend.opcode_other_dispatch_blocked_cycle[op]);
        $display("[PERF] op_%s_operand_request_blocked_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_operand_request_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_operand_request_blocked_cycles: %0d", op_name,
          backend.opcode_operand_request_blocked_cycle[op]);
        $display("[PERF] op_%s_primary_fu_queue_full_cycles: %0d", op_name,
          backend.opcode_primary_fu_queue_full_cycle[op]);
        $display("[PERF] op_%s_primary_fu_queue_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_fu_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_mask_queue_full_cycles: %0d", op_name,
          backend.opcode_primary_mask_queue_full_cycle[op]);
        $display("[PERF] op_%s_primary_mask_queue_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_mask_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_slide_queue_full_cycles: %0d", op_name,
          backend.opcode_primary_slide_queue_full_cycle[op]);
        $display("[PERF] op_%s_primary_slide_queue_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_slide_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_id_pool_full_cycles: %0d", op_name,
          backend.opcode_primary_id_pool_full_cycle[op]);
        $display("[PERF] op_%s_primary_id_pool_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_id_pool_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_response_wait_cycles: %0d", op_name,
          backend.opcode_primary_response_wait_cycle[op]);
        $display("[PERF] op_%s_primary_response_wait_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_response_wait_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_lane_desync_cycles: %0d", op_name,
          backend.opcode_primary_lane_desync_cycle[op]);
        $display("[PERF] op_%s_primary_lane_desync_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_lane_desync_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_sequencer_block_cycles: %0d", op_name,
          backend.opcode_primary_sequencer_block_cycle[op]);
        $display("[PERF] op_%s_primary_sequencer_block_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_sequencer_block_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_operand_request_blocked_cycles: %0d", op_name,
          backend.opcode_primary_operand_request_blocked_cycle[op]);
        $display("[PERF] op_%s_primary_operand_request_blocked_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_operand_request_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_other_dispatch_blocked_cycles: %0d", op_name,
          backend.opcode_primary_other_dispatch_blocked_cycle[op]);
        $display("[PERF] op_%s_primary_other_dispatch_blocked_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_other_dispatch_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_dispatch_unattributed_cycles: %0d", op_name,
          backend.opcode_primary_dispatch_unattributed_cycle[op]);
        $display("[PERF] op_%s_primary_dispatch_unattributed_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_dispatch_unattributed_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_primary_dispatch_partition_consistent: %0d", op_name,
          primary_dispatch_attribution_samples == backend.opcode_dispatch_blocked_cycle[op]);
        $display("[PERF] op_%s_dispatch_reasons_within_request: %0d", op_name,
          backend.opcode_dispatch_blocked_cycle[op] <=
          backend.opcode_dispatch_request_cycle[op]);
        $display("[PERF] op_%s_top_primary_dispatch_bottleneck_reason: %s", op_name,
          top_dispatch_bottleneck_name);
        $display("[PERF] op_%s_top_primary_dispatch_bottleneck_cycles: %0d", op_name,
          top_dispatch_bottleneck_count);
        $display("[PERF] op_%s_top_primary_dispatch_bottleneck_ratio_dispatch_request: %0.6f",
          op_name,
          perf_ratio(top_dispatch_bottleneck_count, backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_top_primary_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f",
          op_name,
          perf_ratio(top_dispatch_bottleneck_count, backend.opcode_dispatch_blocked_cycle[op]));
        $display("[PERF] op_%s_top_secondary_dispatch_bottleneck_reason: %s", op_name,
          second_dispatch_bottleneck_name);
        $display("[PERF] op_%s_top_secondary_dispatch_bottleneck_cycles: %0d", op_name,
          second_dispatch_bottleneck_count);
        $display("[PERF] op_%s_top_secondary_dispatch_bottleneck_ratio_dispatch_request: %0.6f",
          op_name,
          perf_ratio(second_dispatch_bottleneck_count, backend.opcode_dispatch_request_cycle[op]));
        $display("[PERF] op_%s_top_secondary_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f",
          op_name,
          perf_ratio(second_dispatch_bottleneck_count, backend.opcode_dispatch_blocked_cycle[op]));
        $display("[PERF] op_%s_top_dispatch_bottleneck_reason_gap: %0d", op_name,
          top_dispatch_gap);
        $display("[PERF] op_%s_top_dispatch_bottleneck_gap_ratio_dispatch_request: %0.6f",
          op_name, top_dispatch_gap_ratio_dispatch_request);
        $display("[PERF] op_%s_top_dispatch_bottleneck_dominance_ratio: %0.6f",
          op_name, top_dispatch_dominance_ratio);
        $display("[PERF] op_%s_top_secondary_dispatch_bottleneck_dominance_ratio: %0.6f",
          op_name, second_dispatch_dominance_ratio);
        $display("[PERF] op_%s_top_primary_dispatch_bottleneck_advice: %s", op_name,
          dispatch_bottleneck_advice(top_dispatch_bottleneck_name));
        $display("[PERF] op_%s_active_cycles: %0d", op_name,
          backend.opcode_active_cycle[op]);
        $display("[PERF] op_%s_primary_exec_partition_consistent: %0d", op_name,
          primary_exec_attribution_samples == backend.opcode_active_cycle[op]);
        $display("[PERF] op_%s_top_primary_exec_bottleneck_reason: %s", op_name,
          top_exec_bottleneck_name);
        $display("[PERF] op_%s_top_primary_exec_bottleneck_cycles: %0d", op_name,
          top_exec_bottleneck_count);
        $display("[PERF] op_%s_top_primary_exec_bottleneck_ratio_exec_active: %0.6f", op_name,
          perf_ratio(top_exec_bottleneck_count, backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_top_secondary_exec_bottleneck_reason: %s", op_name,
          second_exec_bottleneck_name);
        $display("[PERF] op_%s_top_secondary_exec_bottleneck_cycles: %0d", op_name,
          second_exec_bottleneck_count);
        $display("[PERF] op_%s_top_secondary_exec_bottleneck_ratio_exec_active: %0.6f",
          op_name, perf_ratio(second_exec_bottleneck_count, backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_top_exec_bottleneck_reason_gap: %0d", op_name, top_exec_gap);
        $display("[PERF] op_%s_top_exec_bottleneck_gap_ratio_exec_active: %0.6f",
          op_name, top_exec_gap_ratio_exec_active);
        $display("[PERF] op_%s_top_exec_bottleneck_dominance_ratio: %0.6f",
          op_name, top_exec_dominance_ratio);
        $display("[PERF] op_%s_top_secondary_exec_bottleneck_dominance_ratio: %0.6f",
          op_name, second_exec_dominance_ratio);
        $display("[PERF] op_%s_top_primary_exec_bottleneck_advice: %s", op_name,
          exec_bottleneck_advice(top_exec_bottleneck_name));
        $display("[PERF] op_%s_primary_result_backpressure_cycles: %0d", op_name,
          backend.opcode_primary_result_backpressure_cycle[op]);
        $display("[PERF] op_%s_primary_result_backpressure_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_result_backpressure_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_primary_result_queue_full_cycles: %0d", op_name,
          backend.opcode_primary_result_queue_full_cycle[op]);
        $display("[PERF] op_%s_primary_result_queue_full_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_result_queue_full_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_primary_latency_order_stall_cycles: %0d", op_name,
          backend.opcode_primary_latency_order_stall_cycle[op]);
        $display("[PERF] op_%s_primary_latency_order_stall_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_latency_order_stall_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_primary_unit_input_backpressure_cycles: %0d", op_name,
          backend.opcode_primary_unit_input_backpressure_cycle[op]);
        $display("[PERF] op_%s_primary_unit_input_backpressure_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_unit_input_backpressure_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_primary_operand_wait_cycles: %0d", op_name,
          backend.opcode_primary_operand_wait_cycle[op]);
        $display("[PERF] op_%s_primary_operand_wait_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_operand_wait_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_primary_long_latency_busy_cycles: %0d", op_name,
          backend.opcode_primary_long_latency_busy_cycle[op]);
        $display("[PERF] op_%s_primary_long_latency_busy_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_long_latency_busy_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_primary_special_path_cycles: %0d", op_name,
          backend.opcode_primary_special_path_cycle[op]);
        $display("[PERF] op_%s_primary_special_path_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_special_path_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_primary_progress_cycles: %0d", op_name,
          backend.opcode_primary_progress_cycle[op]);
        $display("[PERF] op_%s_primary_progress_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_progress_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_primary_unattributed_cycles: %0d", op_name,
          backend.opcode_primary_unattributed_cycle[op]);
        $display("[PERF] op_%s_primary_unattributed_ratio: %0.6f", op_name,
          perf_ratio(backend.opcode_primary_unattributed_cycle[op],
                     backend.opcode_active_cycle[op]));
        $display("[PERF] op_%s_avg_execution_latency: %0.3f", op_name,
          perf_ratio(backend.opcode_execution_latency_cycle[op],
                     backend.opcode_completed_count[op]));
        $display("[PERF] op_%s_execution_latency_le8: %0d", op_name,
          backend.opcode_execution_latency_hist[op][0]);
        $display("[PERF] op_%s_execution_latency_9_32: %0d", op_name,
          backend.opcode_execution_latency_hist[op][1]);
        $display("[PERF] op_%s_execution_latency_33_128: %0d", op_name,
          backend.opcode_execution_latency_hist[op][2]);
        $display("[PERF] op_%s_execution_latency_gt128: %0d", op_name,
          backend.opcode_execution_latency_hist[op][3]);
        $display("[PERF] op_%s_dispatch_wait_cycles: %0d", op_name,
          backend.opcode_dispatch_wait_cycle[op]);
        $display("[PERF] op_%s_avg_dispatch_wait: %0.3f", op_name,
          perf_ratio(backend.opcode_dispatch_wait_cycle[op],
                     backend.opcode_completed_count[op]));
        $display("[PERF] op_%s_dispatch_wait_0_cycles: %0d", op_name,
          backend.opcode_dispatch_wait_hist[op][0]);
        $display("[PERF] op_%s_dispatch_wait_1_4_cycles: %0d", op_name,
          backend.opcode_dispatch_wait_hist[op][1]);
        $display("[PERF] op_%s_dispatch_wait_5_16_cycles: %0d", op_name,
          backend.opcode_dispatch_wait_hist[op][2]);
        $display("[PERF] op_%s_dispatch_wait_gt16_cycles: %0d", op_name,
          backend.opcode_dispatch_wait_hist[op][3]);
        $display("[PERF] op_%s_dispatch_wait_hist_consistent: %0d", op_name,
          dispatch_hist_samples == backend.opcode_uop_count[op]);
        for (int unsigned sew = 0; sew < 4; sew++)
          $display("[PERF] op_%s_sew_encoding_%0d_uops: %0d", op_name, sew,
            backend.opcode_sew_hist[op][sew]);
        for (int unsigned lmul = 0; lmul < 8; lmul++)
          $display("[PERF] op_%s_lmul_encoding_%0d_uops: %0d", op_name, lmul,
            backend.opcode_lmul_hist[op][lmul]);
        for (int unsigned sew = 0; sew < 4; sew++) begin
          for (int unsigned lmul = 0; lmul < 8; lmul++) begin
            if (backend.opcode_shape_uop_count[op][sew][lmul] != '0 ||
                backend.opcode_shape_completed_count[op][sew][lmul] != '0) begin
              $display("[PERF] op_%s_sew%0d_lmul%0d_uops: %0d", op_name, sew, lmul,
                backend.opcode_shape_uop_count[op][sew][lmul]);
              $display("[PERF] op_%s_sew%0d_lmul%0d_completed: %0d", op_name, sew, lmul,
                backend.opcode_shape_completed_count[op][sew][lmul]);
              $display("[PERF] op_%s_sew%0d_lmul%0d_avg_latency: %0.3f", op_name, sew, lmul,
                perf_ratio(backend.opcode_shape_latency_cycle[op][sew][lmul],
                           backend.opcode_shape_completed_count[op][sew][lmul]));
            end
          end
        end
        $display("[PERF] op_%s_execution_hist_consistent: %0d", op_name,
          latency_hist_samples == backend.opcode_completed_count[op]);
        $display("[PERF] op_%s_sew_hist_consistent: %0d", op_name,
          sew_samples == backend.opcode_uop_count[op]);
        $display("[PERF] op_%s_lmul_hist_consistent: %0d", op_name,
          lmul_samples == backend.opcode_uop_count[op]);
        $display("[PERF] op_%s_shape_uop_consistent: %0d", op_name,
          shape_uop_samples == backend.opcode_uop_count[op]);
        $display("[PERF] op_%s_shape_completion_consistent: %0d", op_name,
          shape_completed_samples == backend.opcode_completed_count[op]);
        $display("[PERF] op_%s_window_lifecycle_complete: %0d", op_name,
          backend.opcode_completed_count[op] == backend.opcode_uop_count[op]);
      end else begin
        $fwrite(file_handle, "[PERF] op_%s_arch_insns: %0d\n", op_name,
          frontend.arch_opcode_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_zero_vl_nop_insns: %0d\n", op_name,
          frontend.arch_opcode_zero_vl_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_backend_uops: %0d\n", op_name,
          backend.opcode_uop_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_backend_uops_per_arch_insn: %0.6f\n",
          op_name, perf_ratio(backend.opcode_uop_count[op], frontend.arch_opcode_count[op]));
        $fwrite(file_handle, "[PERF] op_%s_nonzero_backend_coverage_ratio: %0.6f\n",
          op_name, perf_ratio(backend.opcode_uop_count[op], nonzero_arch_insns));
        $fwrite(file_handle, "[PERF] op_%s_completed_uops: %0d\n", op_name,
          backend.opcode_completed_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_completion_per_backend_uop: %0.6f\n",
          op_name, perf_ratio(backend.opcode_completed_count[op], backend.opcode_uop_count[op]));
        $fwrite(file_handle, "[PERF] op_%s_requested_elements: %0d\n", op_name,
          backend.opcode_requested_element_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_avg_requested_elements_per_uop: %0.3f\n",
          op_name, perf_ratio(backend.opcode_requested_element_count[op],
                              backend.opcode_uop_count[op]));
        $fwrite(file_handle, "[PERF] op_%s_nominal_element_ops: %0d\n", op_name,
          backend.opcode_nominal_element_op_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_nominal_element_ops_per_rvv_cycle: %0.6f\n",
          op_name, perf_ratio(backend.opcode_nominal_element_op_count[op], total_rvv_cycles));
        $fwrite(file_handle, "[PERF] op_%s_masked_uops: %0d\n", op_name,
          backend.opcode_masked_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_masked_uop_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_masked_count[op], backend.opcode_uop_count[op]));
        $fwrite(file_handle, "[PERF] op_%s_avg_execution_latency: %0.3f\n", op_name,
          perf_ratio(backend.opcode_execution_latency_cycle[op],
                     backend.opcode_completed_count[op]));
        $fwrite(file_handle, "[PERF] op_%s_dispatch_request_cycles: %0d\n",
          op_name, backend.opcode_dispatch_request_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_dispatch_blocked_cycles: %0d\n",
          op_name, backend.opcode_dispatch_blocked_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_dispatch_blocked_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_dispatch_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_fu_queue_full_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_fu_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_fu_queue_full_cycles: %0d\n",
          op_name, backend.opcode_fu_queue_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_mask_queue_full_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_mask_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_mask_queue_full_cycles: %0d\n",
          op_name, backend.opcode_mask_queue_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_slide_queue_full_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_slide_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_slide_queue_full_cycles: %0d\n",
          op_name, backend.opcode_slide_queue_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_id_pool_full_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_id_pool_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_id_pool_full_cycles: %0d\n",
          op_name, backend.opcode_id_pool_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_response_wait_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_response_wait_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_response_wait_cycles: %0d\n",
          op_name, backend.opcode_response_wait_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_other_dispatch_blocked_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_other_dispatch_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_other_dispatch_blocked_cycles: %0d\n",
          op_name, backend.opcode_other_dispatch_blocked_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_operand_request_blocked_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_operand_request_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_operand_request_blocked_cycles: %0d\n",
          op_name, backend.opcode_operand_request_blocked_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_fu_queue_full_cycles: %0d\n", op_name,
          backend.opcode_primary_fu_queue_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_fu_queue_full_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_primary_fu_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_mask_queue_full_cycles: %0d\n", op_name,
          backend.opcode_primary_mask_queue_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_mask_queue_full_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_primary_mask_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_slide_queue_full_cycles: %0d\n", op_name,
          backend.opcode_primary_slide_queue_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_slide_queue_full_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_primary_slide_queue_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_id_pool_full_cycles: %0d\n", op_name,
          backend.opcode_primary_id_pool_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_id_pool_full_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_primary_id_pool_full_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_response_wait_cycles: %0d\n", op_name,
          backend.opcode_primary_response_wait_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_response_wait_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_primary_response_wait_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_lane_desync_cycles: %0d\n", op_name,
          backend.opcode_primary_lane_desync_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_lane_desync_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_primary_lane_desync_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_sequencer_block_cycles: %0d\n", op_name,
          backend.opcode_primary_sequencer_block_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_sequencer_block_ratio: %0.6f\n", op_name,
          perf_ratio(backend.opcode_primary_sequencer_block_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_operand_request_blocked_cycles: %0d\n",
          op_name, backend.opcode_primary_operand_request_blocked_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_operand_request_blocked_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_operand_request_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_other_dispatch_blocked_cycles: %0d\n",
          op_name, backend.opcode_primary_other_dispatch_blocked_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_other_dispatch_blocked_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_other_dispatch_blocked_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_dispatch_unattributed_cycles: %0d\n",
          op_name, backend.opcode_primary_dispatch_unattributed_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_dispatch_unattributed_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_dispatch_unattributed_cycle[op],
                     backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_dispatch_partition_consistent: %0d\n",
          op_name,
          primary_dispatch_attribution_samples == backend.opcode_dispatch_blocked_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_dispatch_reasons_within_request: %0d\n",
          op_name,
          backend.opcode_dispatch_blocked_cycle[op] <= backend.opcode_dispatch_request_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_top_primary_dispatch_bottleneck_reason: %s\n",
          op_name, top_dispatch_bottleneck_name);
        $fwrite(file_handle, "[PERF] op_%s_top_primary_dispatch_bottleneck_cycles: %0d\n",
          op_name, top_dispatch_bottleneck_count);
        $fwrite(file_handle, "[PERF] op_%s_top_primary_dispatch_bottleneck_ratio_dispatch_request: %0.6f\n",
          op_name,
          perf_ratio(top_dispatch_bottleneck_count, backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_top_primary_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f\n",
          op_name,
          perf_ratio(top_dispatch_bottleneck_count, backend.opcode_dispatch_blocked_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_dispatch_bottleneck_reason: %s\n",
          op_name, second_dispatch_bottleneck_name);
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_dispatch_bottleneck_cycles: %0d\n",
          op_name, second_dispatch_bottleneck_count);
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_dispatch_bottleneck_ratio_dispatch_request: %0.6f\n",
          op_name,
          perf_ratio(second_dispatch_bottleneck_count, backend.opcode_dispatch_request_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_dispatch_bottleneck_ratio_dispatch_blocked: %0.6f\n",
          op_name,
          perf_ratio(second_dispatch_bottleneck_count, backend.opcode_dispatch_blocked_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_top_dispatch_bottleneck_reason_gap: %0d\n", op_name,
          top_dispatch_gap);
        $fwrite(file_handle, "[PERF] op_%s_top_dispatch_bottleneck_gap_ratio_dispatch_request: %0.6f\n",
          op_name, top_dispatch_gap_ratio_dispatch_request);
        $fwrite(file_handle, "[PERF] op_%s_top_dispatch_bottleneck_dominance_ratio: %0.6f\n",
          op_name, top_dispatch_dominance_ratio);
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_dispatch_bottleneck_dominance_ratio: %0.6f\n",
          op_name, second_dispatch_dominance_ratio);
        $fwrite(file_handle, "[PERF] op_%s_top_primary_dispatch_bottleneck_advice: %s\n",
          op_name, dispatch_bottleneck_advice(top_dispatch_bottleneck_name));
        $fwrite(file_handle, "[PERF] op_%s_active_cycles: %0d\n", op_name,
          backend.opcode_active_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_exec_partition_consistent: %0d\n",
          op_name,
          primary_exec_attribution_samples == backend.opcode_active_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_top_primary_exec_bottleneck_reason: %s\n",
          op_name, top_exec_bottleneck_name);
        $fwrite(file_handle, "[PERF] op_%s_top_primary_exec_bottleneck_cycles: %0d\n",
          op_name, top_exec_bottleneck_count);
        $fwrite(file_handle, "[PERF] op_%s_top_primary_exec_bottleneck_ratio_exec_active: %0.6f\n",
          op_name, perf_ratio(top_exec_bottleneck_count, backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_exec_bottleneck_reason: %s\n",
          op_name, second_exec_bottleneck_name);
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_exec_bottleneck_cycles: %0d\n",
          op_name, second_exec_bottleneck_count);
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_exec_bottleneck_ratio_exec_active: %0.6f\n",
          op_name, perf_ratio(second_exec_bottleneck_count, backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_top_exec_bottleneck_reason_gap: %0d\n", op_name,
          top_exec_gap);
        $fwrite(file_handle, "[PERF] op_%s_top_exec_bottleneck_gap_ratio_exec_active: %0.6f\n",
          op_name, top_exec_gap_ratio_exec_active);
        $fwrite(file_handle, "[PERF] op_%s_top_exec_bottleneck_dominance_ratio: %0.6f\n",
          op_name, top_exec_dominance_ratio);
        $fwrite(file_handle, "[PERF] op_%s_top_secondary_exec_bottleneck_dominance_ratio: %0.6f\n",
          op_name, second_exec_dominance_ratio);
        $fwrite(file_handle, "[PERF] op_%s_top_primary_exec_bottleneck_advice: %s\n",
          op_name, exec_bottleneck_advice(top_exec_bottleneck_name));
        $fwrite(file_handle, "[PERF] op_%s_primary_result_backpressure_cycles: %0d\n",
          op_name, backend.opcode_primary_result_backpressure_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_result_backpressure_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_result_backpressure_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_result_queue_full_cycles: %0d\n",
          op_name, backend.opcode_primary_result_queue_full_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_result_queue_full_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_result_queue_full_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_latency_order_stall_cycles: %0d\n",
          op_name, backend.opcode_primary_latency_order_stall_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_latency_order_stall_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_latency_order_stall_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_unit_input_backpressure_cycles: %0d\n",
          op_name, backend.opcode_primary_unit_input_backpressure_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_unit_input_backpressure_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_unit_input_backpressure_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_operand_wait_cycles: %0d\n",
          op_name, backend.opcode_primary_operand_wait_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_operand_wait_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_operand_wait_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_long_latency_busy_cycles: %0d\n",
          op_name, backend.opcode_primary_long_latency_busy_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_long_latency_busy_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_long_latency_busy_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_special_path_cycles: %0d\n",
          op_name, backend.opcode_primary_special_path_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_special_path_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_special_path_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_progress_cycles: %0d\n",
          op_name, backend.opcode_primary_progress_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_progress_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_progress_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_primary_unattributed_cycles: %0d\n",
          op_name, backend.opcode_primary_unattributed_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_primary_unattributed_ratio: %0.6f\n",
          op_name,
          perf_ratio(backend.opcode_primary_unattributed_cycle[op],
                     backend.opcode_active_cycle[op]));
        $fwrite(file_handle, "[PERF] op_%s_dispatch_wait_cycles: %0d\n",
          op_name, backend.opcode_dispatch_wait_cycle[op]);
        $fwrite(file_handle, "[PERF] op_%s_avg_dispatch_wait: %0.3f\n",
          op_name, perf_ratio(backend.opcode_dispatch_wait_cycle[op],
                             backend.opcode_completed_count[op]));
        $fwrite(file_handle, "[PERF] op_%s_dispatch_wait_0_cycles: %0d\n",
          op_name, backend.opcode_dispatch_wait_hist[op][0]);
        $fwrite(file_handle, "[PERF] op_%s_dispatch_wait_1_4_cycles: %0d\n",
          op_name, backend.opcode_dispatch_wait_hist[op][1]);
        $fwrite(file_handle, "[PERF] op_%s_dispatch_wait_5_16_cycles: %0d\n",
          op_name, backend.opcode_dispatch_wait_hist[op][2]);
        $fwrite(file_handle, "[PERF] op_%s_dispatch_wait_gt16_cycles: %0d\n",
          op_name, backend.opcode_dispatch_wait_hist[op][3]);
        $fwrite(file_handle, "[PERF] op_%s_dispatch_wait_hist_consistent: %0d\n",
          op_name,
          dispatch_hist_samples == backend.opcode_uop_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_execution_latency_le8: %0d\n", op_name,
          backend.opcode_execution_latency_hist[op][0]);
        $fwrite(file_handle, "[PERF] op_%s_execution_latency_9_32: %0d\n", op_name,
          backend.opcode_execution_latency_hist[op][1]);
        $fwrite(file_handle, "[PERF] op_%s_execution_latency_33_128: %0d\n", op_name,
          backend.opcode_execution_latency_hist[op][2]);
        $fwrite(file_handle, "[PERF] op_%s_execution_latency_gt128: %0d\n", op_name,
          backend.opcode_execution_latency_hist[op][3]);
        for (int unsigned sew = 0; sew < 4; sew++)
          $fwrite(file_handle, "[PERF] op_%s_sew_encoding_%0d_uops: %0d\n", op_name,
            sew, backend.opcode_sew_hist[op][sew]);
        for (int unsigned lmul = 0; lmul < 8; lmul++)
          $fwrite(file_handle, "[PERF] op_%s_lmul_encoding_%0d_uops: %0d\n", op_name,
            lmul, backend.opcode_lmul_hist[op][lmul]);
        for (int unsigned sew = 0; sew < 4; sew++) begin
          for (int unsigned lmul = 0; lmul < 8; lmul++) begin
            if (backend.opcode_shape_uop_count[op][sew][lmul] != '0 ||
                backend.opcode_shape_completed_count[op][sew][lmul] != '0) begin
              $fwrite(file_handle, "[PERF] op_%s_sew%0d_lmul%0d_uops: %0d\n",
                op_name, sew, lmul, backend.opcode_shape_uop_count[op][sew][lmul]);
              $fwrite(file_handle, "[PERF] op_%s_sew%0d_lmul%0d_completed: %0d\n",
                op_name, sew, lmul, backend.opcode_shape_completed_count[op][sew][lmul]);
              $fwrite(file_handle, "[PERF] op_%s_sew%0d_lmul%0d_avg_latency: %0.3f\n",
                op_name, sew, lmul,
                perf_ratio(backend.opcode_shape_latency_cycle[op][sew][lmul],
                           backend.opcode_shape_completed_count[op][sew][lmul]));
            end
          end
        end
        $fwrite(file_handle, "[PERF] op_%s_execution_hist_consistent: %0d\n", op_name,
          latency_hist_samples == backend.opcode_completed_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_sew_hist_consistent: %0d\n", op_name,
          sew_samples == backend.opcode_uop_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_lmul_hist_consistent: %0d\n", op_name,
          lmul_samples == backend.opcode_uop_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_shape_uop_consistent: %0d\n", op_name,
          shape_uop_samples == backend.opcode_uop_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_shape_completion_consistent: %0d\n", op_name,
          shape_completed_samples == backend.opcode_completed_count[op]);
        $fwrite(file_handle, "[PERF] op_%s_window_lifecycle_complete: %0d\n", op_name,
          backend.opcode_completed_count[op] == backend.opcode_uop_count[op]);
      end
    end
  end
endfunction

function automatic void print_vfu_queue_unit_report(
  input integer          file_handle,
  input string           queue_name,
  input vfu_e            vfu,
  input vfu_queue_perf_t stats
);
  logic [63:0] hist_samples;
  int unsigned peak_occupancy;
  hist_samples = '0;
  peak_occupancy = 0;
  for (int unsigned b = 0; b < NrQueueOccupancyBins; b++) begin
    hist_samples += stats.occupancy_hist[vfu][b];
    if (stats.occupancy_hist[vfu][b] != '0)
      peak_occupancy = b;
  end
  if (file_handle == 0) begin
    $display("[PERF] %s_vfu_queue_depth: %0d", queue_name, vfu_queue_depth(vfu));
    $display("[PERF] %s_vfu_queue_sample_cycles: %0d", queue_name,
      stats.sample_cycle[vfu]);
    $display("[PERF] %s_vfu_queue_occupancy_sum: %0d", queue_name,
      stats.occupancy_cycle_sum[vfu]);
    $display("[PERF] %s_vfu_queue_avg_occupancy: %0.3f", queue_name,
      perf_ratio(stats.occupancy_cycle_sum[vfu], stats.sample_cycle[vfu]));
    $display("[PERF] %s_vfu_queue_avg_occupancy_ratio: %0.6f", queue_name,
      perf_ratio(stats.occupancy_cycle_sum[vfu],
                 stats.sample_cycle[vfu] * vfu_queue_depth(vfu)));
    $display("[PERF] %s_vfu_queue_avg_occupancy_when_nonempty: %0.3f", queue_name,
      perf_ratio(stats.occupancy_cycle_sum[vfu], stats.nonempty_cycle[vfu]));
    $display("[PERF] %s_vfu_queue_nonempty_cycles: %0d", queue_name,
      stats.nonempty_cycle[vfu]);
    $display("[PERF] %s_vfu_queue_nonempty_ratio: %0.6f", queue_name,
      perf_ratio(stats.nonempty_cycle[vfu], stats.sample_cycle[vfu]));
    $display("[PERF] %s_vfu_queue_at_capacity_cycles: %0d", queue_name,
      stats.at_capacity_cycle[vfu]);
    $display("[PERF] %s_vfu_queue_at_capacity_ratio: %0.6f", queue_name,
      perf_ratio(stats.at_capacity_cycle[vfu], stats.sample_cycle[vfu]));
    $display("[PERF] %s_vfu_queue_peak_occupancy: %0d", queue_name, peak_occupancy);
    for (int unsigned b = 0; b < NrQueueOccupancyBins; b++)
      $display("[PERF] %s_vfu_queue_occupancy_%0d_cycles: %0d", queue_name, b,
        stats.occupancy_hist[vfu][b]);
    $display("[PERF] %s_vfu_queue_hist_consistent: %0d", queue_name,
      hist_samples == stats.sample_cycle[vfu]);
  end else begin
    $fwrite(file_handle, "[PERF] %s_vfu_queue_depth: %0d\n", queue_name,
      vfu_queue_depth(vfu));
    $fwrite(file_handle, "[PERF] %s_vfu_queue_sample_cycles: %0d\n", queue_name,
      stats.sample_cycle[vfu]);
    $fwrite(file_handle, "[PERF] %s_vfu_queue_occupancy_sum: %0d\n", queue_name,
      stats.occupancy_cycle_sum[vfu]);
    $fwrite(file_handle, "[PERF] %s_vfu_queue_avg_occupancy: %0.3f\n", queue_name,
      perf_ratio(stats.occupancy_cycle_sum[vfu], stats.sample_cycle[vfu]));
    $fwrite(file_handle, "[PERF] %s_vfu_queue_avg_occupancy_ratio: %0.6f\n",
      queue_name, perf_ratio(stats.occupancy_cycle_sum[vfu],
                             stats.sample_cycle[vfu] * vfu_queue_depth(vfu)));
    $fwrite(file_handle, "[PERF] %s_vfu_queue_avg_occupancy_when_nonempty: %0.3f\n",
      queue_name, perf_ratio(stats.occupancy_cycle_sum[vfu], stats.nonempty_cycle[vfu]));
    $fwrite(file_handle, "[PERF] %s_vfu_queue_nonempty_cycles: %0d\n", queue_name,
      stats.nonempty_cycle[vfu]);
    $fwrite(file_handle, "[PERF] %s_vfu_queue_nonempty_ratio: %0.6f\n", queue_name,
      perf_ratio(stats.nonempty_cycle[vfu], stats.sample_cycle[vfu]));
    $fwrite(file_handle, "[PERF] %s_vfu_queue_at_capacity_cycles: %0d\n", queue_name,
      stats.at_capacity_cycle[vfu]);
    $fwrite(file_handle, "[PERF] %s_vfu_queue_at_capacity_ratio: %0.6f\n", queue_name,
      perf_ratio(stats.at_capacity_cycle[vfu], stats.sample_cycle[vfu]));
    $fwrite(file_handle, "[PERF] %s_vfu_queue_peak_occupancy: %0d\n", queue_name,
      peak_occupancy);
    for (int unsigned b = 0; b < NrQueueOccupancyBins; b++)
      $fwrite(file_handle, "[PERF] %s_vfu_queue_occupancy_%0d_cycles: %0d\n",
        queue_name, b, stats.occupancy_hist[vfu][b]);
    $fwrite(file_handle, "[PERF] %s_vfu_queue_hist_consistent: %0d\n", queue_name,
      hist_samples == stats.sample_cycle[vfu]);
  end
endfunction

function automatic void print_vfu_queue_report(
  input integer          file_handle,
  input vfu_queue_perf_t stats
);
  if (file_handle == 0)
    $display("[PERF] ==== Sequencer VFU Queue Occupancy ====");
  else
    $fwrite(file_handle, "[PERF] ==== Sequencer VFU Queue Occupancy ====\n");
  print_vfu_queue_unit_report(file_handle, "alu", VFU_Alu, stats);
  print_vfu_queue_unit_report(file_handle, "mfpu", VFU_MFpu, stats);
  print_vfu_queue_unit_report(file_handle, "sldu", VFU_SlideUnit, stats);
  print_vfu_queue_unit_report(file_handle, "masku", VFU_MaskUnit, stats);
  print_vfu_queue_unit_report(file_handle, "load", VFU_LoadUnit, stats);
  print_vfu_queue_unit_report(file_handle, "store", VFU_StoreUnit, stats);
  print_vfu_queue_unit_report(file_handle, "none", VFU_None, stats);
endfunction

function automatic void print_memory_pipeline_report(
  input integer       file_handle,
  input string        class_name,
  input mem_class_e   class_id,
  input memory_perf_t stats,
  input exec_perf_t   backend,
  input exec_class_e  exec_id
);
  logic [63:0] outstanding_hist_samples;
  logic [63:0] latency_hist_samples;
  int unsigned peak_outstanding;
  outstanding_hist_samples = '0;
  latency_hist_samples = stats.axi_request_latency_hist[class_id][0] +
    stats.axi_request_latency_hist[class_id][1] +
    stats.axi_request_latency_hist[class_id][2] +
    stats.axi_request_latency_hist[class_id][3];
  peak_outstanding = 0;
  for (int unsigned b = 0; b < NrAxiOutstandingBins; b++) begin
    outstanding_hist_samples += stats.axi_outstanding_hist[class_id][b];
    if (stats.axi_outstanding_hist[class_id][b] != '0)
      peak_outstanding = b;
  end
  if (file_handle == 0) begin
    $display("[PERF] %s_addrgen_active_cycles: %0d", class_name, stats.addrgen_active_cycle[class_id]);
    $display("[PERF] %s_addrgen_progress_cycles: %0d", class_name, stats.addrgen_progress_cycle[class_id]);
    $display("[PERF] %s_addrgen_no_progress_cycles: %0d", class_name, stats.addrgen_no_progress_cycle[class_id]);
    $display("[PERF] %s_addrgen_progress_ratio: %0.6f", class_name,
      perf_ratio(stats.addrgen_progress_cycle[class_id], stats.addrgen_active_cycle[class_id]));
    for (int unsigned s = 0; s < 5; s++)
      $display("[PERF] %s_addrgen_state_%0d_cycles: %0d", class_name, s,
        stats.addrgen_state_cycle[class_id][s]);
    for (int unsigned s = 0; s < 4; s++)
      $display("[PERF] %s_axi_addrgen_state_%0d_cycles: %0d", class_name, s,
        stats.axi_addrgen_state_cycle[class_id][s]);
    $display("[PERF] %s_addrgen_operand_wait_cycles: %0d", class_name, stats.addrgen_operand_wait_cycle[class_id]);
    $display("[PERF] %s_indexed_spill_wait_cycles: %0d", class_name,
      stats.indexed_spill_wait_cycle[class_id]);
    $display("[PERF] %s_last_translation_wait_cycles: %0d", class_name,
      stats.last_translation_wait_cycle[class_id]);
    $display("[PERF] %s_addrgen_queue_consumer_wait_cycles: %0d", class_name,
      stats.addrgen_queue_consumer_wait_cycle[class_id]);
    $display("[PERF] %s_addrgen_queue_full_cycles: %0d", class_name, stats.addrgen_queue_full_cycle[class_id]);
    $display("[PERF] %s_core_store_pending_wait_cycles: %0d", class_name, stats.core_store_pending_wait_cycle[class_id]);
    $display("[PERF] %s_mmu_request_cycles: %0d", class_name, stats.mmu_request_cycle[class_id]);
    $display("[PERF] %s_mmu_wait_cycles: %0d", class_name, stats.mmu_wait_cycle[class_id]);
    $display("[PERF] %s_mmu_dtlb_hit_count: %0d", class_name, stats.mmu_dtlb_hit_count[class_id]);
    $display("[PERF] %s_mmu_dtlb_hit_ratio: %0.6f", class_name,
      perf_ratio(stats.mmu_dtlb_hit_count[class_id], stats.mmu_request_cycle[class_id]));
    $display("[PERF] %s_mmu_response_count: %0d", class_name, stats.mmu_response_count[class_id]);
    $display("[PERF] %s_mmu_exception_count: %0d", class_name, stats.mmu_exception_count[class_id]);
    $display("[PERF] %s_axi_address_valid_cycles: %0d", class_name, stats.axi_address_valid_cycle[class_id]);
    $display("[PERF] %s_axi_address_fire_count: %0d", class_name, stats.axi_address_fire_count[class_id]);
    $display("[PERF] %s_axi_address_backpressure_cycles: %0d", class_name, stats.axi_address_backpressure_cycle[class_id]);
    $display("[PERF] %s_axi_address_backpressure_ratio: %0.6f", class_name,
      perf_ratio(stats.axi_address_backpressure_cycle[class_id], stats.axi_address_valid_cycle[class_id]));
    $display("[PERF] %s_axi_data_valid_cycles: %0d", class_name, stats.axi_data_valid_cycle[class_id]);
    $display("[PERF] %s_axi_data_fire_count: %0d", class_name, stats.axi_data_fire_count[class_id]);
    $display("[PERF] %s_axi_data_backpressure_cycles: %0d", class_name, stats.axi_data_backpressure_cycle[class_id]);
    $display("[PERF] %s_axi_data_wait_cycles: %0d", class_name, stats.axi_data_wait_cycle[class_id]);
    $display("[PERF] %s_axi_response_valid_cycles: %0d", class_name, stats.axi_response_valid_cycle[class_id]);
    $display("[PERF] %s_axi_response_fire_count: %0d", class_name, stats.axi_response_fire_count[class_id]);
    $display("[PERF] %s_axi_response_wait_cycles: %0d", class_name, stats.axi_response_wait_cycle[class_id]);
    $display("[PERF] %s_axi_transfer_bytes: %0d", class_name, stats.axi_transfer_byte_count[class_id]);
    $display("[PERF] %s_axi_useful_bytes: %0d", class_name, stats.axi_useful_byte_count[class_id]);
    $display("[PERF] %s_axi_bus_efficiency: %0.6f", class_name,
      perf_ratio(stats.axi_useful_byte_count[class_id], stats.axi_transfer_byte_count[class_id]));
    $display("[PERF] %s_axi_transfer_bytes_per_cycle: %0.6f", class_name,
      perf_ratio(stats.axi_transfer_byte_count[class_id],
                 stats.axi_outstanding_sample_cycle[class_id]));
    $display("[PERF] %s_axi_useful_bytes_per_cycle: %0.6f", class_name,
      perf_ratio(stats.axi_useful_byte_count[class_id],
                 stats.axi_outstanding_sample_cycle[class_id]));
    $display("[PERF] %s_axi_avg_beats_per_response: %0.3f", class_name,
      perf_ratio(stats.axi_data_fire_count[class_id],
                 stats.axi_response_fire_count[class_id]));
    $display("[PERF] %s_axi_outstanding_sample_cycles: %0d", class_name,
      stats.axi_outstanding_sample_cycle[class_id]);
    $display("[PERF] %s_axi_outstanding_cycle_sum: %0d", class_name,
      stats.axi_outstanding_cycle_sum[class_id]);
    $display("[PERF] %s_axi_avg_outstanding: %0.3f", class_name,
      perf_ratio(stats.axi_outstanding_cycle_sum[class_id],
                 stats.axi_outstanding_sample_cycle[class_id]));
    $display("[PERF] %s_axi_outstanding_nonzero_cycles: %0d", class_name,
      stats.axi_outstanding_nonzero_cycle[class_id]);
    $display("[PERF] %s_axi_outstanding_nonzero_ratio: %0.6f", class_name,
      perf_ratio(stats.axi_outstanding_nonzero_cycle[class_id],
                 stats.axi_outstanding_sample_cycle[class_id]));
    $display("[PERF] %s_axi_peak_outstanding_bin: %0d", class_name, peak_outstanding);
    for (int unsigned b = 0; b < NrAxiOutstandingBins; b++)
      $display("[PERF] %s_axi_outstanding_%0d_cycles: %0d", class_name, b,
        stats.axi_outstanding_hist[class_id][b]);
    $display("[PERF] %s_axi_request_latency_samples: %0d", class_name,
      stats.axi_request_latency_count[class_id]);
    $display("[PERF] %s_axi_request_latency_cycles: %0d", class_name,
      stats.axi_request_latency_cycle[class_id]);
    $display("[PERF] %s_axi_avg_request_to_response_latency: %0.3f", class_name,
      perf_ratio(stats.axi_request_latency_cycle[class_id],
                 stats.axi_request_latency_count[class_id]));
    $display("[PERF] %s_axi_request_latency_le8: %0d", class_name,
      stats.axi_request_latency_hist[class_id][0]);
    $display("[PERF] %s_axi_request_latency_9_32: %0d", class_name,
      stats.axi_request_latency_hist[class_id][1]);
    $display("[PERF] %s_axi_request_latency_33_128: %0d", class_name,
      stats.axi_request_latency_hist[class_id][2]);
    $display("[PERF] %s_axi_request_latency_gt128: %0d", class_name,
      stats.axi_request_latency_hist[class_id][3]);
    $display("[PERF] %s_axi_tracking_overflows: %0d", class_name,
      stats.axi_tracking_overflow_count[class_id]);
    $display("[PERF] %s_axi_tracking_underflows: %0d", class_name,
      stats.axi_tracking_underflow_count[class_id]);
    $display("[PERF] %s_axi_outstanding_hist_consistent: %0d", class_name,
      outstanding_hist_samples == stats.axi_outstanding_sample_cycle[class_id]);
    $display("[PERF] %s_axi_latency_hist_consistent: %0d", class_name,
      latency_hist_samples == stats.axi_request_latency_count[class_id]);
    $display("[PERF] %s_axi_tracking_consistent: %0d", class_name,
      stats.axi_tracking_overflow_count[class_id] == '0 &&
      stats.axi_tracking_underflow_count[class_id] == '0);
    $display("[PERF] %s_axi_response_latency_coverage_consistent: %0d", class_name,
      stats.axi_request_latency_count[class_id] +
        stats.axi_tracking_underflow_count[class_id] ==
      stats.axi_response_fire_count[class_id]);
    $display("[PERF] %s_axi_request_response_window_complete: %0d", class_name,
      stats.axi_address_fire_count[class_id] == stats.axi_response_fire_count[class_id] &&
      stats.axi_response_fire_count[class_id] == stats.axi_request_latency_count[class_id]);
    $display("[PERF] %s_mask_wait_cycles: %0d", class_name, stats.mask_wait_cycle[class_id]);
    $display("[PERF] %s_vlsu_operand_wait_cycles: %0d", class_name, stats.operand_wait_cycle[class_id]);
    $display("[PERF] %s_vlsu_result_queue_full_cycles: %0d", class_name, stats.result_queue_full_cycle[class_id]);
    $display("[PERF] %s_vlsu_result_backpressure_cycles: %0d", class_name, stats.result_backpressure_cycle[class_id]);
    $display("[PERF] %s_operand_handshake_lane_samples: %0d", class_name, stats.operand_handshake_lane_sample[class_id]);
    $display("[PERF] %s_result_request_lane_samples: %0d", class_name, stats.result_request_lane_sample[class_id]);
    $display("[PERF] %s_result_handshake_lane_samples: %0d", class_name, stats.result_handshake_lane_sample[class_id]);
    $display("[PERF] %s_result_backpressure_lane_samples: %0d", class_name, stats.result_backpressure_lane_sample[class_id]);
    $display("[PERF] %s_vlsu_completion_count: %0d", class_name, stats.completion_count[class_id]);
    $display("[PERF] %s_vlsu_exception_count: %0d", class_name, stats.exception_count[class_id]);
    $display("[PERF] %s_addrgen_partition_consistent: %0d", class_name,
      stats.addrgen_progress_cycle[class_id] + stats.addrgen_no_progress_cycle[class_id] ==
        stats.addrgen_active_cycle[class_id]);
    $display("[PERF] %s_addrgen_state_hist_consistent: %0d", class_name,
      stats.addrgen_state_cycle[class_id][0] + stats.addrgen_state_cycle[class_id][1] +
      stats.addrgen_state_cycle[class_id][2] + stats.addrgen_state_cycle[class_id][3] +
      stats.addrgen_state_cycle[class_id][4] == stats.addrgen_active_cycle[class_id]);
    $display("[PERF] %s_axi_addrgen_state_hist_consistent: %0d", class_name,
      stats.axi_addrgen_state_cycle[class_id][0] + stats.axi_addrgen_state_cycle[class_id][1] +
      stats.axi_addrgen_state_cycle[class_id][2] + stats.axi_addrgen_state_cycle[class_id][3] ==
        stats.addrgen_active_cycle[class_id]);
    $display("[PERF] %s_backend_vs_vlsu_completion_consistent: %0d", class_name,
      backend.completed_count[exec_id] == stats.completion_count[class_id]);
  end else begin
    $fwrite(file_handle, "[PERF] %s_addrgen_active_cycles: %0d\n", class_name, stats.addrgen_active_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_addrgen_progress_cycles: %0d\n", class_name, stats.addrgen_progress_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_addrgen_no_progress_cycles: %0d\n", class_name, stats.addrgen_no_progress_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_addrgen_progress_ratio: %0.6f\n", class_name,
      perf_ratio(stats.addrgen_progress_cycle[class_id], stats.addrgen_active_cycle[class_id]));
    for (int unsigned s = 0; s < 5; s++)
      $fwrite(file_handle, "[PERF] %s_addrgen_state_%0d_cycles: %0d\n", class_name, s,
        stats.addrgen_state_cycle[class_id][s]);
    for (int unsigned s = 0; s < 4; s++)
      $fwrite(file_handle, "[PERF] %s_axi_addrgen_state_%0d_cycles: %0d\n", class_name, s,
        stats.axi_addrgen_state_cycle[class_id][s]);
    $fwrite(file_handle, "[PERF] %s_addrgen_operand_wait_cycles: %0d\n", class_name, stats.addrgen_operand_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_indexed_spill_wait_cycles: %0d\n", class_name,
      stats.indexed_spill_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_last_translation_wait_cycles: %0d\n", class_name,
      stats.last_translation_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_addrgen_queue_consumer_wait_cycles: %0d\n", class_name,
      stats.addrgen_queue_consumer_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_addrgen_queue_full_cycles: %0d\n", class_name, stats.addrgen_queue_full_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_core_store_pending_wait_cycles: %0d\n", class_name, stats.core_store_pending_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_mmu_request_cycles: %0d\n", class_name, stats.mmu_request_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_mmu_wait_cycles: %0d\n", class_name, stats.mmu_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_mmu_dtlb_hit_count: %0d\n", class_name, stats.mmu_dtlb_hit_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_mmu_dtlb_hit_ratio: %0.6f\n", class_name,
      perf_ratio(stats.mmu_dtlb_hit_count[class_id], stats.mmu_request_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_mmu_response_count: %0d\n", class_name, stats.mmu_response_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_mmu_exception_count: %0d\n", class_name, stats.mmu_exception_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_address_valid_cycles: %0d\n", class_name, stats.axi_address_valid_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_address_fire_count: %0d\n", class_name, stats.axi_address_fire_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_address_backpressure_cycles: %0d\n", class_name, stats.axi_address_backpressure_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_address_backpressure_ratio: %0.6f\n", class_name,
      perf_ratio(stats.axi_address_backpressure_cycle[class_id], stats.axi_address_valid_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_axi_data_valid_cycles: %0d\n", class_name, stats.axi_data_valid_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_data_fire_count: %0d\n", class_name, stats.axi_data_fire_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_data_backpressure_cycles: %0d\n", class_name, stats.axi_data_backpressure_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_data_wait_cycles: %0d\n", class_name, stats.axi_data_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_response_valid_cycles: %0d\n", class_name, stats.axi_response_valid_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_response_fire_count: %0d\n", class_name, stats.axi_response_fire_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_response_wait_cycles: %0d\n", class_name, stats.axi_response_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_transfer_bytes: %0d\n", class_name, stats.axi_transfer_byte_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_useful_bytes: %0d\n", class_name, stats.axi_useful_byte_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_bus_efficiency: %0.6f\n", class_name,
      perf_ratio(stats.axi_useful_byte_count[class_id], stats.axi_transfer_byte_count[class_id]));
    $fwrite(file_handle, "[PERF] %s_axi_transfer_bytes_per_cycle: %0.6f\n", class_name,
      perf_ratio(stats.axi_transfer_byte_count[class_id],
                 stats.axi_outstanding_sample_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_axi_useful_bytes_per_cycle: %0.6f\n", class_name,
      perf_ratio(stats.axi_useful_byte_count[class_id],
                 stats.axi_outstanding_sample_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_axi_avg_beats_per_response: %0.3f\n", class_name,
      perf_ratio(stats.axi_data_fire_count[class_id],
                 stats.axi_response_fire_count[class_id]));
    $fwrite(file_handle, "[PERF] %s_axi_outstanding_sample_cycles: %0d\n", class_name,
      stats.axi_outstanding_sample_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_outstanding_cycle_sum: %0d\n", class_name,
      stats.axi_outstanding_cycle_sum[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_avg_outstanding: %0.3f\n", class_name,
      perf_ratio(stats.axi_outstanding_cycle_sum[class_id],
                 stats.axi_outstanding_sample_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_axi_outstanding_nonzero_cycles: %0d\n", class_name,
      stats.axi_outstanding_nonzero_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_outstanding_nonzero_ratio: %0.6f\n", class_name,
      perf_ratio(stats.axi_outstanding_nonzero_cycle[class_id],
                 stats.axi_outstanding_sample_cycle[class_id]));
    $fwrite(file_handle, "[PERF] %s_axi_peak_outstanding_bin: %0d\n", class_name,
      peak_outstanding);
    for (int unsigned b = 0; b < NrAxiOutstandingBins; b++)
      $fwrite(file_handle, "[PERF] %s_axi_outstanding_%0d_cycles: %0d\n", class_name,
        b, stats.axi_outstanding_hist[class_id][b]);
    $fwrite(file_handle, "[PERF] %s_axi_request_latency_samples: %0d\n", class_name,
      stats.axi_request_latency_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_request_latency_cycles: %0d\n", class_name,
      stats.axi_request_latency_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_avg_request_to_response_latency: %0.3f\n",
      class_name, perf_ratio(stats.axi_request_latency_cycle[class_id],
                             stats.axi_request_latency_count[class_id]));
    $fwrite(file_handle, "[PERF] %s_axi_request_latency_le8: %0d\n", class_name,
      stats.axi_request_latency_hist[class_id][0]);
    $fwrite(file_handle, "[PERF] %s_axi_request_latency_9_32: %0d\n", class_name,
      stats.axi_request_latency_hist[class_id][1]);
    $fwrite(file_handle, "[PERF] %s_axi_request_latency_33_128: %0d\n", class_name,
      stats.axi_request_latency_hist[class_id][2]);
    $fwrite(file_handle, "[PERF] %s_axi_request_latency_gt128: %0d\n", class_name,
      stats.axi_request_latency_hist[class_id][3]);
    $fwrite(file_handle, "[PERF] %s_axi_tracking_overflows: %0d\n", class_name,
      stats.axi_tracking_overflow_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_tracking_underflows: %0d\n", class_name,
      stats.axi_tracking_underflow_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_outstanding_hist_consistent: %0d\n", class_name,
      outstanding_hist_samples == stats.axi_outstanding_sample_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_latency_hist_consistent: %0d\n", class_name,
      latency_hist_samples == stats.axi_request_latency_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_tracking_consistent: %0d\n", class_name,
      stats.axi_tracking_overflow_count[class_id] == '0 &&
      stats.axi_tracking_underflow_count[class_id] == '0);
    $fwrite(file_handle,
      "[PERF] %s_axi_response_latency_coverage_consistent: %0d\n", class_name,
      stats.axi_request_latency_count[class_id] +
        stats.axi_tracking_underflow_count[class_id] ==
      stats.axi_response_fire_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_request_response_window_complete: %0d\n",
      class_name,
      stats.axi_address_fire_count[class_id] == stats.axi_response_fire_count[class_id] &&
      stats.axi_response_fire_count[class_id] == stats.axi_request_latency_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_mask_wait_cycles: %0d\n", class_name, stats.mask_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_vlsu_operand_wait_cycles: %0d\n", class_name, stats.operand_wait_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_vlsu_result_queue_full_cycles: %0d\n", class_name, stats.result_queue_full_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_vlsu_result_backpressure_cycles: %0d\n", class_name, stats.result_backpressure_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_operand_handshake_lane_samples: %0d\n", class_name, stats.operand_handshake_lane_sample[class_id]);
    $fwrite(file_handle, "[PERF] %s_result_request_lane_samples: %0d\n", class_name, stats.result_request_lane_sample[class_id]);
    $fwrite(file_handle, "[PERF] %s_result_handshake_lane_samples: %0d\n", class_name, stats.result_handshake_lane_sample[class_id]);
    $fwrite(file_handle, "[PERF] %s_result_backpressure_lane_samples: %0d\n", class_name, stats.result_backpressure_lane_sample[class_id]);
    $fwrite(file_handle, "[PERF] %s_vlsu_completion_count: %0d\n", class_name, stats.completion_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_vlsu_exception_count: %0d\n", class_name, stats.exception_count[class_id]);
    $fwrite(file_handle, "[PERF] %s_addrgen_partition_consistent: %0d\n", class_name,
      stats.addrgen_progress_cycle[class_id] + stats.addrgen_no_progress_cycle[class_id] ==
        stats.addrgen_active_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_addrgen_state_hist_consistent: %0d\n", class_name,
      stats.addrgen_state_cycle[class_id][0] + stats.addrgen_state_cycle[class_id][1] +
      stats.addrgen_state_cycle[class_id][2] + stats.addrgen_state_cycle[class_id][3] +
      stats.addrgen_state_cycle[class_id][4] == stats.addrgen_active_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_axi_addrgen_state_hist_consistent: %0d\n", class_name,
      stats.axi_addrgen_state_cycle[class_id][0] + stats.axi_addrgen_state_cycle[class_id][1] +
      stats.axi_addrgen_state_cycle[class_id][2] + stats.axi_addrgen_state_cycle[class_id][3] ==
        stats.addrgen_active_cycle[class_id]);
    $fwrite(file_handle, "[PERF] %s_backend_vs_vlsu_completion_consistent: %0d\n", class_name,
      backend.completed_count[exec_id] == stats.completion_count[class_id]);
  end
endfunction

`ifndef SAIF
`ifndef IDEAL_DISPATCHER
typedef struct {
  realtime timestamp;
  logic [63:0] cycle;
  logic [63:0] instret;
  logic [63:0] rvv_cycle;
  logic [63:0] rvv_lane_cycle;
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;
  logic [63:0] rvv_instret;
  logic [63:0] rvv_op;
  logic [63:0] rvv_op_fs1;
  logic [63:0] rvv_op_fd;
  logic [63:0] rvv_op_load;
  logic [63:0] rvv_op_store;
  logic [63:0] rvv_axi_aw_count;
  logic [63:0] rvv_axi_w_count;
  logic [63:0] rvv_axi_b_count;
  logic [63:0] rvv_axi_ar_count;
  logic [63:0] rvv_axi_r_count;
  logic [63:0] ara_req_valid_cycles;
  logic [63:0] ara_req_fire_count;
  logic [63:0] ara_req_blocked_cycles;
  exec_perf_t  exec;
  frontend_perf_t frontend;
  memory_perf_t memory;
  vfu_queue_perf_t vfu_queue;
  red_stream_perf_t red_stream;
`ifdef FOR_VERIFY
  logic [63:0] seq_raw_hazard_cycle;
  logic [63:0] seq_war_hazard_cycle;
  logic [63:0] seq_waw_hazard_cycle;
  logic [63:0] seq_false_hazard_cycle;
  logic [63:0] seq_block_cycle;
`endif
} perf_t;

function automatic perf_t get_perf_counters();
    perf_t counters;
    counters.timestamp = $realtime;
    counters.cycle = ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.cycle_q[63:0];
    counters.instret = ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.instret_q[63:0];
    counters.rvv_cycle            = ara_tb.rvv_cycle           ;
    counters.rvv_lane_cycle       = ara_tb.rvv_lane_cycle      ;
    counters.rvv_mem_only_cycle  = ara_tb.rvv_mem_only_cycle ;
    counters.rvv_mem_lane_cycle  = ara_tb.rvv_mem_lane_cycle ;
    counters.rvv_load_only_cycle  = ara_tb.rvv_load_only_cycle ;
    counters.rvv_load_lane_cycle  = ara_tb.rvv_load_lane_cycle ;
    counters.rvv_store_only_cycle = ara_tb.rvv_store_only_cycle;
    counters.rvv_store_lane_cycle = ara_tb.rvv_store_lane_cycle;
    counters.rvv_instret = ara_tb.rvv_instret;
    counters.rvv_op       = ara_tb.rvv_op      ;
    counters.rvv_op_fs1   = ara_tb.rvv_op_fs1  ;
    counters.rvv_op_fd    = ara_tb.rvv_op_fd   ;
    counters.rvv_op_load  = ara_tb.rvv_op_load ;
    counters.rvv_op_store = ara_tb.rvv_op_store;
    counters.rvv_axi_aw_count = ara_tb.rvv_axi_aw_count;
    counters.rvv_axi_w_count  = ara_tb.rvv_axi_w_count ;
    counters.rvv_axi_b_count  = ara_tb.rvv_axi_b_count ;
    counters.rvv_axi_ar_count = ara_tb.rvv_axi_ar_count;
    counters.rvv_axi_r_count  = ara_tb.rvv_axi_r_count ;
    counters.ara_req_valid_cycles  = ara_tb.ara_req_valid_cycles;
    counters.ara_req_fire_count    = ara_tb.ara_req_fire_count;
    counters.ara_req_blocked_cycles = ara_tb.ara_req_blocked_cycles;
    counters.exec = ara_tb.exec_perf_counters;
    counters.frontend = ara_tb.frontend_perf_counters;
    counters.memory = ara_tb.memory_perf_counters;
    counters.vfu_queue = ara_tb.vfu_queue_perf_counters;
    counters.red_stream = ara_tb.red_stream_perf_counters;
`ifdef FOR_VERIFY
    counters.seq_raw_hazard_cycle   = ara_tb.seq_raw_hazard_cycle;
    counters.seq_war_hazard_cycle   = ara_tb.seq_war_hazard_cycle;
    counters.seq_waw_hazard_cycle   = ara_tb.seq_waw_hazard_cycle;
    counters.seq_false_hazard_cycle = ara_tb.seq_false_hazard_cycle;
    counters.seq_block_cycle        = ara_tb.seq_block_cycle;
`endif
    return counters;
endfunction

function void print_perf_report();
      realtime duration;
      int total_cycles;
      int total_insns;
      int total_rvv_cycles          ;
      int total_rvv_lane_cycles     ;
      int total_rvv_mem_only_cycles;
      int total_rvv_mem_lane_cycles;
      int total_rvv_load_only_cycles;
      int total_rvv_load_lane_cycles;
      int total_rvv_store_only_cycles;
      int total_rvv_store_lane_cycles;
      int total_vector_insns;
      int total_rvv_op      ;
      int total_rvv_op_fs1  ;
      int total_rvv_op_fd   ;
      int total_rvv_op_load ;
      int total_rvv_op_store;
      int total_rvv_axi_aw_count;
      int total_rvv_axi_w_count ;
      int total_rvv_axi_b_count ;
      int total_rvv_axi_ar_count;
      int total_rvv_axi_r_count ;
      int total_ara_req_valid_cycles;
      int total_ara_req_fire_count;
      int total_ara_req_blocked_cycles;
      exec_perf_t total_exec;
      frontend_perf_t total_frontend;
      memory_perf_t total_memory;
      vfu_queue_perf_t total_vfu_queue;
      red_stream_perf_t total_red_stream;
`ifdef FOR_VERIFY
      int total_seq_raw_hazard_cycle;
      int total_seq_war_hazard_cycle;
      int total_seq_waw_hazard_cycle;
      int total_seq_false_hazard_cycle;
      int total_seq_block_cycle;
`endif
      
      real ipc;
      real lane_utilization;
      real vecinst_rate;
      real main_vector_req_per_cycle;
      real main_vector_req_blocked_ratio;
      int file_handle;

      string testcase;
      void'($value$plusargs("TESTCASE=%s", testcase));

      duration = ara_tb.perf_end_n.timestamp - ara_tb.perf_start_n.timestamp;
      total_cycles = ara_tb.perf_end_n.cycle - ara_tb.perf_start_n.cycle;
      total_insns = ara_tb.perf_end_n.instret - ara_tb.perf_start_n.instret;
      total_rvv_cycles            = ara_tb.perf_end_n.rvv_cycle            - ara_tb.perf_start_n.rvv_cycle           ;
      total_rvv_lane_cycles       = ara_tb.perf_end_n.rvv_lane_cycle       - ara_tb.perf_start_n.rvv_lane_cycle      ;
      total_rvv_mem_only_cycles  = ara_tb.perf_end_n.rvv_mem_only_cycle  - ara_tb.perf_start_n.rvv_mem_only_cycle ;
      total_rvv_mem_lane_cycles  = ara_tb.perf_end_n.rvv_mem_lane_cycle  - ara_tb.perf_start_n.rvv_mem_lane_cycle ;
      total_rvv_load_only_cycles  = ara_tb.perf_end_n.rvv_load_only_cycle  - ara_tb.perf_start_n.rvv_load_only_cycle ;
      total_rvv_load_lane_cycles  = ara_tb.perf_end_n.rvv_load_lane_cycle  - ara_tb.perf_start_n.rvv_load_lane_cycle ;
      total_rvv_store_only_cycles = ara_tb.perf_end_n.rvv_store_only_cycle - ara_tb.perf_start_n.rvv_store_only_cycle;
      total_rvv_store_lane_cycles = ara_tb.perf_end_n.rvv_store_lane_cycle - ara_tb.perf_start_n.rvv_store_lane_cycle;
      total_vector_insns = ara_tb.perf_end_n.rvv_instret - ara_tb.perf_start_n.rvv_instret;
      total_rvv_op       = ara_tb.perf_end_n.rvv_op       - ara_tb.perf_start_n.rvv_op      ;
      total_rvv_op_fs1   = ara_tb.perf_end_n.rvv_op_fs1   - ara_tb.perf_start_n.rvv_op_fs1  ;
      total_rvv_op_fd    = ara_tb.perf_end_n.rvv_op_fd    - ara_tb.perf_start_n.rvv_op_fd   ;
      total_rvv_op_load  = ara_tb.perf_end_n.rvv_op_load  - ara_tb.perf_start_n.rvv_op_load ;
      total_rvv_op_store = ara_tb.perf_end_n.rvv_op_store - ara_tb.perf_start_n.rvv_op_store;
      total_rvv_axi_aw_count = ara_tb.perf_end_n.rvv_axi_aw_count - ara_tb.perf_start_n.rvv_axi_aw_count;
      total_rvv_axi_w_count  = ara_tb.perf_end_n.rvv_axi_w_count  - ara_tb.perf_start_n.rvv_axi_w_count ;
      total_rvv_axi_b_count  = ara_tb.perf_end_n.rvv_axi_b_count  - ara_tb.perf_start_n.rvv_axi_b_count ;
      total_rvv_axi_ar_count = ara_tb.perf_end_n.rvv_axi_ar_count - ara_tb.perf_start_n.rvv_axi_ar_count;
      total_rvv_axi_r_count  = ara_tb.perf_end_n.rvv_axi_r_count  - ara_tb.perf_start_n.rvv_axi_r_count ;
      total_ara_req_valid_cycles  = ara_tb.perf_end_n.ara_req_valid_cycles  - ara_tb.perf_start_n.ara_req_valid_cycles;
      total_ara_req_fire_count    = ara_tb.perf_end_n.ara_req_fire_count    - ara_tb.perf_start_n.ara_req_fire_count;
      total_ara_req_blocked_cycles = ara_tb.perf_end_n.ara_req_blocked_cycles - ara_tb.perf_start_n.ara_req_blocked_cycles;
      total_exec = exec_perf_delta(ara_tb.perf_end_n.exec, ara_tb.perf_start_n.exec);
      total_frontend = frontend_perf_delta(
        ara_tb.perf_end_n.frontend, ara_tb.perf_start_n.frontend
      );
      total_memory = memory_perf_delta(ara_tb.perf_end_n.memory, ara_tb.perf_start_n.memory);
      total_vfu_queue = vfu_queue_perf_delta(
        ara_tb.perf_end_n.vfu_queue, ara_tb.perf_start_n.vfu_queue
      );
      total_red_stream = red_stream_perf_delta(
        ara_tb.perf_end_n.red_stream, ara_tb.perf_start_n.red_stream
      );
`ifdef FOR_VERIFY
      total_seq_raw_hazard_cycle   = ara_tb.perf_end_n.seq_raw_hazard_cycle   - ara_tb.perf_start_n.seq_raw_hazard_cycle;
      total_seq_war_hazard_cycle   = ara_tb.perf_end_n.seq_war_hazard_cycle   - ara_tb.perf_start_n.seq_war_hazard_cycle;
      total_seq_waw_hazard_cycle   = ara_tb.perf_end_n.seq_waw_hazard_cycle   - ara_tb.perf_start_n.seq_waw_hazard_cycle;
      total_seq_false_hazard_cycle = ara_tb.perf_end_n.seq_false_hazard_cycle - ara_tb.perf_start_n.seq_false_hazard_cycle;
      total_seq_block_cycle        = ara_tb.perf_end_n.seq_block_cycle        - ara_tb.perf_start_n.seq_block_cycle;
`endif

      ipc = real'(total_insns) / total_cycles;
      lane_utilization = real'(total_rvv_lane_cycles) / total_cycles;
      vecinst_rate = real'(total_vector_insns) / total_insns;
      main_vector_req_per_cycle = real'(total_ara_req_fire_count) / total_cycles;
      main_vector_req_blocked_ratio = real'(total_ara_req_blocked_cycles) / total_cycles;
      file_handle = $fopen($sformatf("perf_report_%s.log", testcase), "a");
      
      $display("\n[PERF] ==== Performance Report Start ====");
      $display("[PERF] duration                   : %0t x100fs", duration);
      $display("[PERF] total_cycles               : %0d", total_cycles);
      $display("[PERF] total_insns                : %0d", total_insns);
      $display("[PERF] total_rvv_cycles           : %0d", total_rvv_cycles           );
      $display("[PERF] total_rvv_lane_cycles      : %0d", total_rvv_lane_cycles      );
      $display("[PERF] total_rvv_mem_only_cycles  : %0d", total_rvv_mem_only_cycles );
      $display("[PERF] total_rvv_mem_lane_cycles  : %0d", total_rvv_mem_lane_cycles );
      $display("[PERF] total_rvv_load_only_cycles : %0d", total_rvv_load_only_cycles );
      $display("[PERF] total_rvv_load_lane_cycles : %0d", total_rvv_load_lane_cycles );
      $display("[PERF] total_rvv_store_only_cycles: %0d", total_rvv_store_only_cycles);
      $display("[PERF] total_rvv_store_lane_cycles: %0d", total_rvv_store_lane_cycles);
      $display("[PERF] total_vector_insns         : %0d", total_vector_insns);
      $display("[PERF] IPC                        : %0.3f", ipc);
      $display("[PERF] lane utilization           : %0.3f", lane_utilization);
      $display("[PERF] vector inst rate           : %0.3f", vecinst_rate);
      $display("[PERF] ara_req_valid_cycles       : %0d", total_ara_req_valid_cycles);
      $display("[PERF] ara_req_fire_count         : %0d", total_ara_req_fire_count);
      $display("[PERF] ara_req_blocked_cycles     : %0d", total_ara_req_blocked_cycles);
      $display("[PERF] main_vector_req_per_cycle  : %0.3f", main_vector_req_per_cycle);
      $display("[PERF] main_vector_req_blocked_ratio: %0.3f", main_vector_req_blocked_ratio);
      print_frontend_report(0, total_frontend, total_exec);
      print_opcode_report(0, total_frontend, total_exec, total_rvv_cycles);
      print_global_bottleneck_summary(0, total_exec, total_frontend);
      print_vfu_queue_report(0, total_vfu_queue);
      print_red_stream_report(0, total_red_stream);
      print_deep_exec_report(0, total_exec, total_rvv_cycles);
      $display("[PERF] ==== Backend Instruction / Micro-op Execution ====");
      print_exec_class_report(0, "valu",  ExecValu,  total_exec, total_rvv_cycles);
      print_exec_class_report(0, "mul",   ExecMul,   total_exec, total_rvv_cycles);
      print_exec_class_report(0, "div",   ExecDiv,   total_exec, total_rvv_cycles);
      print_exec_class_report(0, "fp",    ExecFp,    total_exec, total_rvv_cycles);
      print_exec_class_report(0, "slide", ExecSlide, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "mask",  ExecMask,  total_exec, total_rvv_cycles);
      print_exec_class_report(0, "load", ExecLoad, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "store", ExecStore, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "move_to_vec", ExecMoveToVec, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "move_from_vec", ExecMoveFromVec, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "reshuffle", ExecReshuffle, total_exec, total_rvv_cycles);
      $display("[PERF] ==== VLSU Pipeline / Memory-System Attribution ====");
      print_memory_pipeline_report(0, "load", MemLoad, total_memory, total_exec, ExecLoad);
      print_memory_pipeline_report(0, "store", MemStore, total_memory, total_exec, ExecStore);
      $display("[PERF] rvv_op                     : %0d", total_rvv_op      );
      $display("[PERF] rvv_op_fs1                 : %0d", total_rvv_op_fs1  );
      $display("[PERF] rvv_op_fd                  : %0d", total_rvv_op_fd   );
      $display("[PERF] rvv_op_load                : %0d", total_rvv_op_load );
      $display("[PERF] rvv_op_store               : %0d", total_rvv_op_store);
`ifdef FOR_VERIFY
      $display("[PERF] seq_raw_hazard_cycles      : %0d", total_seq_raw_hazard_cycle  );
      $display("[PERF] seq_war_hazard_cycles      : %0d", total_seq_war_hazard_cycle  );
      $display("[PERF] seq_waw_hazard_cycles      : %0d", total_seq_waw_hazard_cycle  );
      $display("[PERF] seq_false_hazard_cycles    : %0d", total_seq_false_hazard_cycle);
      $display("[PERF] seq_block_cycles           : %0d", total_seq_block_cycle       );
`endif
      $display("[PERF] ==== Performance Report End ====\n");


      $fwrite(file_handle, "[PERF] ==== Performance Report Start ====\n");
      $fwrite(file_handle, "[PERF] duration                   : %0t x100fs\n", duration);
      $fwrite(file_handle, "[PERF] total_cycles               : %0d\n", total_cycles);
      $fwrite(file_handle, "[PERF] total_insns                : %0d\n", total_insns);
      $fwrite(file_handle, "[PERF] total_rvv_cycles           : %0d\n", total_rvv_cycles           );
      $fwrite(file_handle, "[PERF] total_rvv_lane_cycles      : %0d\n", total_rvv_lane_cycles      );
      $fwrite(file_handle, "[PERF] total_rvv_mem_only_cycles  : %0d\n", total_rvv_mem_only_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_mem_lane_cycles  : %0d\n", total_rvv_mem_lane_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_load_only_cycles : %0d\n", total_rvv_load_only_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_load_lane_cycles : %0d\n", total_rvv_load_lane_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_store_only_cycles: %0d\n", total_rvv_store_only_cycles);
      $fwrite(file_handle, "[PERF] total_rvv_store_lane_cycles: %0d\n", total_rvv_store_lane_cycles);
      $fwrite(file_handle, "[PERF] total_vector_insns         : %0d\n", total_vector_insns);
      $fwrite(file_handle, "[PERF] IPC                        : %0.3f\n", ipc);
      $fwrite(file_handle, "[PERF] lane utilization           : %0.3f\n", lane_utilization);
      $fwrite(file_handle, "[PERF] vector inst rate           : %0.3f\n", vecinst_rate);
      $fwrite(file_handle, "[PERF] ara_req_valid_cycles       : %0d\n", total_ara_req_valid_cycles);
      $fwrite(file_handle, "[PERF] ara_req_fire_count         : %0d\n", total_ara_req_fire_count);
      $fwrite(file_handle, "[PERF] ara_req_blocked_cycles     : %0d\n", total_ara_req_blocked_cycles);
      $fwrite(file_handle, "[PERF] main_vector_req_per_cycle  : %0.3f\n", main_vector_req_per_cycle);
      $fwrite(file_handle, "[PERF] main_vector_req_blocked_ratio: %0.3f\n", main_vector_req_blocked_ratio);
      print_frontend_report(file_handle, total_frontend, total_exec);
      print_opcode_report(file_handle, total_frontend, total_exec, total_rvv_cycles);
      print_global_bottleneck_summary(file_handle, total_exec, total_frontend);
      print_vfu_queue_report(file_handle, total_vfu_queue);
      print_red_stream_report(file_handle, total_red_stream);
      print_deep_exec_report(file_handle, total_exec, total_rvv_cycles);
      $fwrite(file_handle, "[PERF] ==== Backend Instruction / Micro-op Execution ====\n");
      print_exec_class_report(file_handle, "valu",  ExecValu,  total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "mul",   ExecMul,   total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "div",   ExecDiv,   total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "fp",    ExecFp,    total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "slide", ExecSlide, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "mask",  ExecMask,  total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "load", ExecLoad, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "store", ExecStore, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "move_to_vec", ExecMoveToVec, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "move_from_vec", ExecMoveFromVec, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "reshuffle", ExecReshuffle, total_exec, total_rvv_cycles);
      $fwrite(file_handle, "[PERF] ==== VLSU Pipeline / Memory-System Attribution ====\n");
      print_memory_pipeline_report(file_handle, "load", MemLoad, total_memory, total_exec, ExecLoad);
      print_memory_pipeline_report(file_handle, "store", MemStore, total_memory, total_exec, ExecStore);
      $fwrite(file_handle, "[PERF] rvv_op                     : %0d\n", total_rvv_op      );
      $fwrite(file_handle, "[PERF] rvv_op_fs1                 : %0d\n", total_rvv_op_fs1  );
      $fwrite(file_handle, "[PERF] rvv_op_fd                  : %0d\n", total_rvv_op_fd   );
      $fwrite(file_handle, "[PERF] rvv_op_load                : %0d\n", total_rvv_op_load );
      $fwrite(file_handle, "[PERF] rvv_op_store               : %0d\n", total_rvv_op_store);
`ifdef FOR_VERIFY
      $fwrite(file_handle, "[PERF] seq_raw_hazard_cycles      : %0d\n", total_seq_raw_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_war_hazard_cycles      : %0d\n", total_seq_war_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_waw_hazard_cycles      : %0d\n", total_seq_waw_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_false_hazard_cycles    : %0d\n", total_seq_false_hazard_cycle);
      $fwrite(file_handle, "[PERF] seq_block_cycles           : %0d\n", total_seq_block_cycle       );
`endif
      $fwrite(file_handle, "[PERF] ==== AXI Transaction ====\n");
      $fwrite(file_handle, "[PERF] rvv_axi_aw_count           : %0d\n", total_rvv_axi_aw_count);
      $fwrite(file_handle, "[PERF] rvv_axi_w_count            : %0d\n", total_rvv_axi_w_count );
      $fwrite(file_handle, "[PERF] rvv_axi_b_count            : %0d\n", total_rvv_axi_b_count );
      $fwrite(file_handle, "[PERF] rvv_axi_ar_count           : %0d\n", total_rvv_axi_ar_count);
      $fwrite(file_handle, "[PERF] rvv_axi_r_count            : %0d\n", total_rvv_axi_r_count );
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane0 ====\n");
      $fwrite(file_handle, "[PERF] lane0 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane0 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane0 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane0 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane0 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane0 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane0 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane0 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane0 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane0 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane0 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane0 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane0 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane0 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane0 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane0 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane0 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane0 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane0 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane0 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane0 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane0 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane0 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane0 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane0 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane0 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane0 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane0 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane0 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane0 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane0 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane1 ====\n");
      $fwrite(file_handle, "[PERF] lane1 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane1 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane1 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane1 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane1 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane1 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane1 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane1 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane1 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane1 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane1 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane1 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane1 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane1 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane1 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane1 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane1 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane1 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane1 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane1 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane1 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane1 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane1 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane1 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane1 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane1 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane1 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane1 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane1 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane1 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane1 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
`ifdef ARA_HAS_LANE_2_3
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane2 ====\n");
      $fwrite(file_handle, "[PERF] lane2 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane2 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane2 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane2 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane2 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane2 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane2 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane2 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane2 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane2 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane2 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane2 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane2 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane2 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane2 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane2 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane2 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane2 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane2 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane2 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane2 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane2 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane2 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane2 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane2 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane2 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane2 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane2 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane2 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane2 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane2 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane3 ====\n");
      $fwrite(file_handle, "[PERF] lane3 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane3 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane3 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane3 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane3 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane3 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane3 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane3 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane3 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane3 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane3 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane3 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane3 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane3 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane3 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane3 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane3 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane3 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane3 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane3 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane3 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane3 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane3 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane3 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane3 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane3 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane3 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane3 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane3 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane3 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane3 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
`endif
      $fwrite(file_handle, "[PERF] ==== Performance Report End ====\n");

      $fclose(file_handle);
endfunction
`else
typedef struct {
  realtime timestamp;
  logic [63:0] rvv_cycle;
  logic [63:0] rvv_lane_cycle;
  logic [63:0] rvv_lane_compute_cycle[4];
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;
  logic [63:0] ara_req_valid_cycles;
  logic [63:0] ara_req_fire_count;
  logic [63:0] ara_req_blocked_cycles;
  exec_perf_t  exec;
  frontend_perf_t frontend;
  memory_perf_t memory;
  vfu_queue_perf_t vfu_queue;
  red_stream_perf_t red_stream;
`ifdef FOR_VERIFY
  logic [63:0] seq_raw_hazard_cycle;
  logic [63:0] seq_war_hazard_cycle;
  logic [63:0] seq_waw_hazard_cycle;
  logic [63:0] seq_false_hazard_cycle;
  logic [63:0] seq_block_cycle;
`endif
} perf_t;

function automatic perf_t get_perf_counters();
    perf_t counters;
    counters.timestamp = $realtime;
    counters.rvv_cycle              = ara_tb.rvv_cycle;
    counters.rvv_lane_cycle         = ara_tb.rvv_lane_cycle;
    counters.rvv_lane_compute_cycle[0] = ara_tb.lane_compute_add[0];
    counters.rvv_lane_compute_cycle[1] = ara_tb.lane_compute_add[1];
`ifdef ARA_HAS_LANE_2_3
    counters.rvv_lane_compute_cycle[2] = ara_tb.lane_compute_add[2];
    counters.rvv_lane_compute_cycle[3] = ara_tb.lane_compute_add[3];
`else
    counters.rvv_lane_compute_cycle[2] = '0;
    counters.rvv_lane_compute_cycle[3] = '0;
`endif
    counters.rvv_mem_only_cycle     = ara_tb.rvv_mem_only_cycle ;
    counters.rvv_mem_lane_cycle     = ara_tb.rvv_mem_lane_cycle ;
    counters.rvv_load_only_cycle    = ara_tb.rvv_load_only_cycle ;
    counters.rvv_load_lane_cycle    = ara_tb.rvv_load_lane_cycle ;
    counters.rvv_store_only_cycle   = ara_tb.rvv_store_only_cycle;
    counters.rvv_store_lane_cycle   = ara_tb.rvv_store_lane_cycle;
    counters.ara_req_valid_cycles   = ara_tb.ara_req_valid_cycles;
    counters.ara_req_fire_count     = ara_tb.ara_req_fire_count;
    counters.ara_req_blocked_cycles = ara_tb.ara_req_blocked_cycles;
    counters.exec = ara_tb.exec_perf_counters;
    counters.frontend = ara_tb.frontend_perf_counters;
    counters.memory = ara_tb.memory_perf_counters;
    counters.vfu_queue = ara_tb.vfu_queue_perf_counters;
    counters.red_stream = ara_tb.red_stream_perf_counters;
`ifdef FOR_VERIFY
    counters.seq_raw_hazard_cycle   = ara_tb.seq_raw_hazard_cycle;
    counters.seq_war_hazard_cycle   = ara_tb.seq_war_hazard_cycle;
    counters.seq_waw_hazard_cycle   = ara_tb.seq_waw_hazard_cycle;
    counters.seq_false_hazard_cycle = ara_tb.seq_false_hazard_cycle;
    counters.seq_block_cycle        = ara_tb.seq_block_cycle;
`endif
    return counters;
endfunction

function void print_perf_report();
      realtime duration;
      int total_rvv_cycles          ;
      int total_rvv_lane_cycles     ;
      int total_rvv_mem_only_cycles;
      int total_rvv_mem_lane_cycles;
      int total_rvv_load_only_cycles;
      int total_rvv_load_lane_cycles;
      int total_rvv_store_only_cycles;
      int total_ara_req_valid_cycles;
      int total_ara_req_fire_count;
      int total_ara_req_blocked_cycles;
      exec_perf_t total_exec;
      frontend_perf_t total_frontend;
      memory_perf_t total_memory;
      vfu_queue_perf_t total_vfu_queue;
      red_stream_perf_t total_red_stream;
`ifdef FOR_VERIFY
      int total_seq_raw_hazard_cycle;
      int total_seq_war_hazard_cycle;
      int total_seq_waw_hazard_cycle;
      int total_seq_false_hazard_cycle;
      int total_seq_block_cycle;
`endif
       
      int total_rvv_store_lane_cycles;
      
      real lane_utilization;
      real lane_compute_utilization;
      real main_vector_req_per_cycle;
      real main_vector_req_blocked_ratio;
      int file_handle;

      string testcase;
      void'($value$plusargs("TESTCASE=%s", testcase));

      duration = ara_tb.perf_end_n.timestamp - ara_tb.perf_start_n.timestamp;
      total_rvv_cycles            = ara_tb.perf_end_n.rvv_cycle            - ara_tb.perf_start_n.rvv_cycle           ;
      total_rvv_lane_cycles       = ara_tb.perf_end_n.rvv_lane_cycle       - ara_tb.perf_start_n.rvv_lane_cycle      ;
      total_rvv_mem_only_cycles  = ara_tb.perf_end_n.rvv_mem_only_cycle  - ara_tb.perf_start_n.rvv_mem_only_cycle ;
      total_rvv_mem_lane_cycles  = ara_tb.perf_end_n.rvv_mem_lane_cycle  - ara_tb.perf_start_n.rvv_mem_lane_cycle ;
      total_rvv_load_only_cycles  = ara_tb.perf_end_n.rvv_load_only_cycle  - ara_tb.perf_start_n.rvv_load_only_cycle ;
      total_rvv_load_lane_cycles  = ara_tb.perf_end_n.rvv_load_lane_cycle  - ara_tb.perf_start_n.rvv_load_lane_cycle ;
      total_rvv_store_only_cycles = ara_tb.perf_end_n.rvv_store_only_cycle - ara_tb.perf_start_n.rvv_store_only_cycle;
      total_rvv_store_lane_cycles = ara_tb.perf_end_n.rvv_store_lane_cycle - ara_tb.perf_start_n.rvv_store_lane_cycle;
      total_ara_req_valid_cycles  = ara_tb.perf_end_n.ara_req_valid_cycles - ara_tb.perf_start_n.ara_req_valid_cycles;
      total_ara_req_fire_count    = ara_tb.perf_end_n.ara_req_fire_count - ara_tb.perf_start_n.ara_req_fire_count;
      total_ara_req_blocked_cycles = ara_tb.perf_end_n.ara_req_blocked_cycles - ara_tb.perf_start_n.ara_req_blocked_cycles;
      total_exec = exec_perf_delta(ara_tb.perf_end_n.exec, ara_tb.perf_start_n.exec);
      total_frontend = frontend_perf_delta(
        ara_tb.perf_end_n.frontend, ara_tb.perf_start_n.frontend
      );
      total_memory = memory_perf_delta(ara_tb.perf_end_n.memory, ara_tb.perf_start_n.memory);
      total_vfu_queue = vfu_queue_perf_delta(
        ara_tb.perf_end_n.vfu_queue, ara_tb.perf_start_n.vfu_queue
      );
      total_red_stream = red_stream_perf_delta(
        ara_tb.perf_end_n.red_stream, ara_tb.perf_start_n.red_stream
      );

`ifdef FOR_VERIFY
      total_seq_raw_hazard_cycle   = ara_tb.perf_end_n.seq_raw_hazard_cycle   - ara_tb.perf_start_n.seq_raw_hazard_cycle;
      total_seq_war_hazard_cycle   = ara_tb.perf_end_n.seq_war_hazard_cycle   - ara_tb.perf_start_n.seq_war_hazard_cycle;
      total_seq_waw_hazard_cycle   = ara_tb.perf_end_n.seq_waw_hazard_cycle   - ara_tb.perf_start_n.seq_waw_hazard_cycle;
      total_seq_false_hazard_cycle = ara_tb.perf_end_n.seq_false_hazard_cycle - ara_tb.perf_start_n.seq_false_hazard_cycle;
      total_seq_block_cycle        = ara_tb.perf_end_n.seq_block_cycle        - ara_tb.perf_start_n.seq_block_cycle;
`endif

      lane_utilization = real'(total_rvv_lane_cycles) / total_rvv_cycles;
      main_vector_req_per_cycle = real'(total_ara_req_fire_count) / total_rvv_cycles;
      main_vector_req_blocked_ratio = real'(total_ara_req_blocked_cycles) / total_rvv_cycles;
      file_handle = $fopen($sformatf("perf_report_%s_ideal.log", testcase), "a");
      
      $display("\n[PERF] ==== Performance Report Start ====");
      $display("[PERF] duration                       : %0t x100fs", duration);
      $display("[PERF] total_rvv_cycles               : %0d", total_rvv_cycles           );
      $display("[PERF] total_rvv_lane_cycles          : %0d", total_rvv_lane_cycles      );
      $display("[PERF] total_rvv_lane0_compute_cycles : %0d", ara_tb.perf_end_n.rvv_lane_compute_cycle[0] - ara_tb.perf_start_n.rvv_lane_compute_cycle[0]);
      $display("[PERF] total_rvv_lane1_compute_cycles : %0d", ara_tb.perf_end_n.rvv_lane_compute_cycle[1] - ara_tb.perf_start_n.rvv_lane_compute_cycle[1]);
      $display("[PERF] total_rvv_lane2_compute_cycles : %0d", ara_tb.perf_end_n.rvv_lane_compute_cycle[2] - ara_tb.perf_start_n.rvv_lane_compute_cycle[2]);
      $display("[PERF] total_rvv_lane3_compute_cycles : %0d", ara_tb.perf_end_n.rvv_lane_compute_cycle[3] - ara_tb.perf_start_n.rvv_lane_compute_cycle[3]);
      $display("[PERF] total_rvv_mem_only_cycles      : %0d", total_rvv_mem_only_cycles );
      $display("[PERF] total_rvv_mem_lane_cycles      : %0d", total_rvv_mem_lane_cycles );
      $display("[PERF] total_rvv_load_only_cycles     : %0d", total_rvv_load_only_cycles );
      $display("[PERF] total_rvv_load_lane_cycles     : %0d", total_rvv_load_lane_cycles );
      $display("[PERF] total_rvv_store_only_cycles    : %0d", total_rvv_store_only_cycles);
      $display("[PERF] total_rvv_store_lane_cycles    : %0d", total_rvv_store_lane_cycles);
      $display("[PERF] ara_req_valid_cycles           : %0d", total_ara_req_valid_cycles);
      $display("[PERF] ara_req_fire_count             : %0d", total_ara_req_fire_count);
      $display("[PERF] ara_req_blocked_cycles         : %0d", total_ara_req_blocked_cycles);
      $display("[PERF] main_vector_req_per_cycle      : %0.3f", main_vector_req_per_cycle);
      $display("[PERF] main_vector_req_blocked_ratio  : %0.3f", main_vector_req_blocked_ratio);
      print_frontend_report(0, total_frontend, total_exec);
      print_opcode_report(0, total_frontend, total_exec, total_rvv_cycles);
      print_global_bottleneck_summary(0, total_exec, total_frontend);
      print_vfu_queue_report(0, total_vfu_queue);
      print_red_stream_report(0, total_red_stream);
      print_deep_exec_report(0, total_exec, total_rvv_cycles);
      $display("[PERF] ==== Backend Instruction / Micro-op Execution ====");
      print_exec_class_report(0, "valu",  ExecValu,  total_exec, total_rvv_cycles);
      print_exec_class_report(0, "mul",   ExecMul,   total_exec, total_rvv_cycles);
      print_exec_class_report(0, "div",   ExecDiv,   total_exec, total_rvv_cycles);
      print_exec_class_report(0, "fp",    ExecFp,    total_exec, total_rvv_cycles);
      print_exec_class_report(0, "slide", ExecSlide, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "mask",  ExecMask,  total_exec, total_rvv_cycles);
      print_exec_class_report(0, "load", ExecLoad, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "store", ExecStore, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "move_to_vec", ExecMoveToVec, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "move_from_vec", ExecMoveFromVec, total_exec, total_rvv_cycles);
      print_exec_class_report(0, "reshuffle", ExecReshuffle, total_exec, total_rvv_cycles);
      $display("[PERF] ==== VLSU Pipeline / Memory-System Attribution ====");
      print_memory_pipeline_report(0, "load", MemLoad, total_memory, total_exec, ExecLoad);
      print_memory_pipeline_report(0, "store", MemStore, total_memory, total_exec, ExecStore);
`ifdef FOR_VERIFY
      $display("[PERF] seq_raw_hazard_cycles          : %0d", total_seq_raw_hazard_cycle  );
      $display("[PERF] seq_war_hazard_cycles          : %0d", total_seq_war_hazard_cycle  );
      $display("[PERF] seq_waw_hazard_cycles          : %0d", total_seq_waw_hazard_cycle  );
      $display("[PERF] seq_false_hazard_cycles        : %0d", total_seq_false_hazard_cycle);
      $display("[PERF] seq_block_cycles               : %0d", total_seq_block_cycle       );
`endif
      $display("[PERF] lane utilization               : %0.3f", lane_utilization);
      $display("[PERF] lane0 compute utilization      : %0.3f", real'(ara_tb.perf_end_n.rvv_lane_compute_cycle[0] - ara_tb.perf_start_n.rvv_lane_compute_cycle[0]) / total_rvv_cycles);
      $display("[PERF] lane1 compute utilization      : %0.3f", real'(ara_tb.perf_end_n.rvv_lane_compute_cycle[1] - ara_tb.perf_start_n.rvv_lane_compute_cycle[1]) / total_rvv_cycles);
      $display("[PERF] lane2 compute utilization      : %0.3f", real'(ara_tb.perf_end_n.rvv_lane_compute_cycle[2] - ara_tb.perf_start_n.rvv_lane_compute_cycle[2]) / total_rvv_cycles);
      $display("[PERF] lane3 compute utilization      : %0.3f", real'(ara_tb.perf_end_n.rvv_lane_compute_cycle[3] - ara_tb.perf_start_n.rvv_lane_compute_cycle[3]) / total_rvv_cycles);
      $display("[PERF] ==== VRF Perf lane0 ====");
      $display("[PERF] lane0 total_bank_requests      : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $display("[PERF] lane0 total_bank_conflicts     : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $display("[PERF] lane0 total_hp_bank_requests   : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $display("[PERF] lane0 total_hp_bank_conflicts  : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $display("[PERF] lane0 total_lp_bank_requests   : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $display("[PERF] lane0 total_lp_bank_conflicts  : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $display("[PERF] lane0 hp_block_lp              : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $display("[PERF] lane0 conflict_ratio           : %0.3f", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_conflicts) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_requests));
      $display("[PERF] ==== Performance Report End ====\n");

      $fwrite(file_handle, "[PERF] ==== Performance Report Start ====\n");
      $fwrite(file_handle, "[PERF] duration                   : %0t x100fs\n", duration);
      $fwrite(file_handle, "[PERF] total_rvv_cycles           : %0d\n", total_rvv_cycles           );
      $fwrite(file_handle, "[PERF] total_rvv_lane_cycles      : %0d\n", total_rvv_lane_cycles      );
      $fwrite(file_handle, "[PERF] total_rvv_mem_only_cycles  : %0d\n", total_rvv_mem_only_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_mem_lane_cycles  : %0d\n", total_rvv_mem_lane_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_load_only_cycles : %0d\n", total_rvv_load_only_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_load_lane_cycles : %0d\n", total_rvv_load_lane_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_store_only_cycles: %0d\n", total_rvv_store_only_cycles);
      $fwrite(file_handle, "[PERF] total_rvv_store_lane_cycles: %0d\n", total_rvv_store_lane_cycles);
      $fwrite(file_handle, "[PERF] ara_req_valid_cycles       : %0d\n", total_ara_req_valid_cycles);
      $fwrite(file_handle, "[PERF] ara_req_fire_count         : %0d\n", total_ara_req_fire_count);
      $fwrite(file_handle, "[PERF] ara_req_blocked_cycles     : %0d\n", total_ara_req_blocked_cycles);
      $fwrite(file_handle, "[PERF] main_vector_req_per_cycle  : %0.3f\n", main_vector_req_per_cycle);
      $fwrite(file_handle, "[PERF] main_vector_req_blocked_ratio: %0.3f\n", main_vector_req_blocked_ratio);
      print_frontend_report(file_handle, total_frontend, total_exec);
      print_opcode_report(file_handle, total_frontend, total_exec, total_rvv_cycles);
      print_global_bottleneck_summary(file_handle, total_exec, total_frontend);
      print_vfu_queue_report(file_handle, total_vfu_queue);
      print_red_stream_report(file_handle, total_red_stream);
      print_deep_exec_report(file_handle, total_exec, total_rvv_cycles);
      $fwrite(file_handle, "[PERF] ==== Backend Instruction / Micro-op Execution ====\n");
      print_exec_class_report(file_handle, "valu",  ExecValu,  total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "mul",   ExecMul,   total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "div",   ExecDiv,   total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "fp",    ExecFp,    total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "slide", ExecSlide, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "mask",  ExecMask,  total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "load", ExecLoad, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "store", ExecStore, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "move_to_vec", ExecMoveToVec, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "move_from_vec", ExecMoveFromVec, total_exec, total_rvv_cycles);
      print_exec_class_report(file_handle, "reshuffle", ExecReshuffle, total_exec, total_rvv_cycles);
      $fwrite(file_handle, "[PERF] ==== VLSU Pipeline / Memory-System Attribution ====\n");
      print_memory_pipeline_report(file_handle, "load", MemLoad, total_memory, total_exec, ExecLoad);
      print_memory_pipeline_report(file_handle, "store", MemStore, total_memory, total_exec, ExecStore);
`ifdef FOR_VERIFY
      $fwrite(file_handle, "[PERF] seq_raw_hazard_cycles      : %0d\n", total_seq_raw_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_war_hazard_cycles      : %0d\n", total_seq_war_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_waw_hazard_cycles      : %0d\n", total_seq_waw_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_false_hazard_cycles    : %0d\n", total_seq_false_hazard_cycle);
      $fwrite(file_handle, "[PERF] seq_block_cycles           : %0d\n", total_seq_block_cycle       );
`endif
      $fwrite(file_handle, "[PERF] lane utilization           : %0.3f\n", lane_utilization);
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane0 ====\n");
      $fwrite(file_handle, "[PERF] lane0 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane0 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane0 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane0 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane0 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane0 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane0 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane0 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane0 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane0 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane0 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane0 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane0 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane0 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane0 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane0 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane0 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane0 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane0 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane0 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane0 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane0 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane0 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane0 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane0 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane0 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane0 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane0 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane0 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane0 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane0 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane1 ====\n");
      $fwrite(file_handle, "[PERF] lane1 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane1 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane1 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane1 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane1 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane1 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane1 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane1 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane1 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane1 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane1 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane1 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane1 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane1 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane1 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane1 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane1 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane1 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane1 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane1 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane1 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane1 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane1 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane1 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane1 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane1 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane1 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane1 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane1 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane1 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane1 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
`ifdef ARA_HAS_LANE_2_3
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane2 ====\n");
      $fwrite(file_handle, "[PERF] lane2 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane2 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane2 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane2 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane2 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane2 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane2 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane2 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane2 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane2 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane2 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane2 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane2 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane2 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane2 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane2 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane2 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane2 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane2 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane2 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane2 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane2 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane2 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane2 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane2 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane2 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane2 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane2 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane2 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane2 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane2 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane3 ====\n");
      $fwrite(file_handle, "[PERF] lane3 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane3 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane3 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane3 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane3 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane3 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane3 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane3 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane3 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane3 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane3 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane3 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane3 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane3 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane3 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane3 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane3 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane3 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane3 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane3 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane3 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane3 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane3 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane3 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane3 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane3 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane3 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane3 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane3 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane3 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane3 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
`endif
      $fclose(file_handle);
endfunction


function void print_perf_csv();
    string testcase;
    int csv_handle;

    int cycle_count;

    void'($value$plusargs("TESTCASE=%s", testcase));
    csv_handle = $fopen($sformatf("perf_report_%s_ideal.csv", testcase), "w");

    cycle_count = ara_tb.wall_cycle;


    $fwrite(csv_handle, "wall_cycle");
    for (int i = 0; i < cycle_count; i++) begin
        $fwrite(csv_handle, ",%0d", ara_tb.wall_cycle_history[i]);
    end
    $fwrite(csv_handle, "\n");
    
    for (int j = 0; j < 4; j++) begin
      $fwrite(csv_handle, "lane%0d_compute", j);
      for (int i = 0; i < cycle_count; i++) begin
          $fwrite(csv_handle, ",%0d", ara_tb.lane_compute_history[j][i]);
      end
      $fwrite(csv_handle, "\n");
    end

    $fclose(csv_handle);
endfunction

`endif
`endif

module ara_tb;
  /*****************
   *  Definitions  *
   *****************/

  `ifdef NR_LANES
  localparam NrLanes = `NR_LANES;
  `else
  localparam NrLanes = 8;
  `endif

  `ifdef VLEN
  localparam VLEN = `VLEN;
  `else
  localparam VLEN = 256;
  `endif

  localparam ClockPeriod  = 1ns;
  // Axi response delay [ps]
  localparam int unsigned AxiRespDelay = 200;

  localparam AxiAddrWidth      = 64;
  localparam AxiWideDataWidth  = 64 * NrLanes/2;
  localparam AxiWideBeWidth    = AxiWideDataWidth / 8;
  localparam AxiWideByteOffset = $clog2(AxiWideBeWidth);

  localparam DRAMAddrBase = 64'h8000_0000;
  localparam DRAMLength   = 64'h4000_0000; // 1GByte of DDR (split between two chips on Genesys2)

  /********************************
   *  Clock and Reset Generation  *
   ********************************/

  logic clk;
  logic rst_n;

  // Controlling the reset
  initial begin
    clk   = 1'b0;
    rst_n = 1'b0;

    // Synch reset for TB memories
    repeat (10) #(ClockPeriod/2) clk = ~clk;
    clk = 1'b0;

    // Asynch reset for main system
    repeat (5) #(ClockPeriod);
    rst_n = 1'b1;
    repeat (5) #(ClockPeriod);

    // Start the clock
    forever #(ClockPeriod/2) clk = ~clk;
  end

  logic [63:0] wall_cycle;
  logic        lane_compute[NrLanes];
  logic [63:0] lane_compute_add[NrLanes];
  logic [63:0] wall_cycle_history[100000];
  logic lane_compute_history[NrLanes][100000];

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      wall_cycle <= '0;
    end
    else begin
      wall_cycle <= wall_cycle + 1;
    end

    wall_cycle_history[wall_cycle] <= wall_cycle;
  end

  for (genvar i = 0; i < NrLanes; i++) begin
    assign lane_compute[i] = (|(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_vfus.mfpu_operand_valid_i[2:0] & ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_vfus.mfpu_operand_ready_o[2:0])) || (|(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_vfus.alu_operand_valid_i[1:0] & ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_vfus.alu_operand_ready_o[1:0]));

    always_ff @(posedge clk, negedge rst_n) begin
      lane_compute_history[i][wall_cycle] <= lane_compute[i];
    end

    always_ff @(posedge clk, negedge rst_n) begin
      if(!rst_n) begin
        lane_compute_add[i] <= '0;
      end
      else begin
        lane_compute_add[i] <= lane_compute_add[i] + lane_compute[i];
      end
    end

  end

  /***************************************************
   *  Dispatcher-side architectural RVV accounting  *
   ***************************************************/

  riscv::instruction_t       frontend_instr;
  rvv_pkg::rvv_instruction_t frontend_rvv_instr;
  exec_class_mask_t          frontend_arch_class;
  logic frontend_response_fire;
  logic frontend_zero_vl_fire;
  logic frontend_is_vset_request;
  logic frontend_is_vector_csr_request;
  logic frontend_is_config_request;
  logic frontend_config_blocked;
  logic frontend_config_wait_idle;
  logic frontend_config_wait_ara_ready;
  logic frontend_config_wait_reshuffle;
  logic frontend_config_other_blocked;
  logic frontend_memory_request_open_q;
  frontend_perf_t frontend_perf_counters;

  always_comb begin : p_frontend_perf_events
    frontend_instr = ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.instr;
    frontend_rvv_instr = rvv_pkg::rvv_instruction_t'(frontend_instr.instr);
    frontend_arch_class = classify_exec_op(
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.op
    );

    frontend_response_fire =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_decoding &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o.req_ready &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o.resp_valid;
    frontend_zero_vl_fire = frontend_response_fire &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o.exception.valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_config &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ignore_zero_vl_check &&
      ((ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vstart_q >=
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vl_q) ||
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.null_vslideup);

    frontend_is_vset_request =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_req_i.req_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_req_i.resp_ready &&
      (frontend_instr.itype.opcode == riscv::OpcodeVec) &&
      (frontend_rvv_instr.varith_type.func3 == rvv_pkg::OPCFG);
    frontend_is_vector_csr_request =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_req_i.req_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_req_i.resp_ready &&
      (frontend_instr.itype.opcode == riscv::OpcodeSystem) &&
      rvv_pkg::is_vector_csr(riscv::csr_reg_t'(frontend_instr.itype.imm));
    frontend_is_config_request = frontend_is_vset_request || frontend_is_vector_csr_request;
    frontend_config_blocked = frontend_is_config_request &&
      !(ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o.req_ready &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o.resp_valid);
    frontend_config_wait_idle = frontend_config_blocked &&
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q == 2'd1);
    frontend_config_wait_ara_ready = frontend_config_blocked &&
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q == 2'd0) &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req_ready_i;
    frontend_config_wait_reshuffle = frontend_config_blocked &&
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q == 2'd3);
    frontend_config_other_blocked = frontend_config_blocked &&
      !(frontend_config_wait_idle || frontend_config_wait_ara_ready ||
        frontend_config_wait_reshuffle);
  end

  always_ff @(posedge clk or negedge rst_n) begin : p_frontend_perf_counters
    if (!rst_n) begin
      frontend_perf_counters <= '{default: '0};
      frontend_memory_request_open_q <= 1'b0;
    end else begin
      if (frontend_response_fire)
        frontend_memory_request_open_q <= 1'b0;
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_decoding &&
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_vload ||
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_vstore) &&
          !frontend_memory_request_open_q) begin
        automatic mem_class_e accepted_mem_id =
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_vload ? MemLoad : MemStore;
        automatic logic accepted_whole_register =
          frontend_rvv_instr.vmem_type.mop == 2'b00 &&
          frontend_rvv_instr.vmem_type.rs2 == 5'b01000;
        automatic logic accepted_mask_memory =
          frontend_rvv_instr.vmem_type.mop == 2'b00 &&
          frontend_rvv_instr.vmem_type.rs2 == 5'b01011;
        automatic logic accepted_segment_memory =
          frontend_rvv_instr.vmem_type.nf != 3'b000 && !accepted_whole_register;
        frontend_memory_request_open_q <= 1'b1;
        frontend_perf_counters.memory_accepted_count[accepted_mem_id] <=
          frontend_perf_counters.memory_accepted_count[accepted_mem_id] + 1;
        frontend_perf_counters.memory_accepted_unit_stride_count[accepted_mem_id] <=
          frontend_perf_counters.memory_accepted_unit_stride_count[accepted_mem_id] +
          (frontend_rvv_instr.vmem_type.mop == 2'b00);
        frontend_perf_counters.memory_accepted_strided_count[accepted_mem_id] <=
          frontend_perf_counters.memory_accepted_strided_count[accepted_mem_id] +
          (frontend_rvv_instr.vmem_type.mop == 2'b10);
        frontend_perf_counters.memory_accepted_indexed_unordered_count[accepted_mem_id] <=
          frontend_perf_counters.memory_accepted_indexed_unordered_count[accepted_mem_id] +
          (frontend_rvv_instr.vmem_type.mop == 2'b01);
        frontend_perf_counters.memory_accepted_indexed_ordered_count[accepted_mem_id] <=
          frontend_perf_counters.memory_accepted_indexed_ordered_count[accepted_mem_id] +
          (frontend_rvv_instr.vmem_type.mop == 2'b11);
        frontend_perf_counters.memory_accepted_segment_count[accepted_mem_id] <=
          frontend_perf_counters.memory_accepted_segment_count[accepted_mem_id] +
          accepted_segment_memory;
        frontend_perf_counters.memory_accepted_whole_register_count[accepted_mem_id] <=
          frontend_perf_counters.memory_accepted_whole_register_count[accepted_mem_id] +
          accepted_whole_register;
        frontend_perf_counters.memory_accepted_mask_count[accepted_mem_id] <=
          frontend_perf_counters.memory_accepted_mask_count[accepted_mem_id] +
          accepted_mask_memory;
        if (accepted_mem_id == MemLoad)
          frontend_perf_counters.load_accepted_fault_only_first_count <=
            frontend_perf_counters.load_accepted_fault_only_first_count +
            (frontend_rvv_instr.vmem_type.mop == 2'b00 &&
             frontend_rvv_instr.vmem_type.rs2 == 5'b10000);
      end
      frontend_perf_counters.config_request_cycle <=
        frontend_perf_counters.config_request_cycle + frontend_is_config_request;
      frontend_perf_counters.config_blocked_cycle <=
        frontend_perf_counters.config_blocked_cycle + frontend_config_blocked;
      frontend_perf_counters.config_wait_idle_cycle <=
        frontend_perf_counters.config_wait_idle_cycle + frontend_config_wait_idle;
      frontend_perf_counters.config_wait_backend_busy_cycle <=
        frontend_perf_counters.config_wait_backend_busy_cycle +
        (frontend_config_wait_idle &&
         !ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_idle_i);
      frontend_perf_counters.config_wait_ara_ready_cycle <=
        frontend_perf_counters.config_wait_ara_ready_cycle + frontend_config_wait_ara_ready;
      frontend_perf_counters.config_wait_reshuffle_cycle <=
        frontend_perf_counters.config_wait_reshuffle_cycle + frontend_config_wait_reshuffle;
      frontend_perf_counters.config_other_blocked_cycle <=
        frontend_perf_counters.config_other_blocked_cycle + frontend_config_other_blocked;

      if (frontend_response_fire) begin
        if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_config) begin
          frontend_perf_counters.config_insn_count <=
            frontend_perf_counters.config_insn_count + 1;
          if (frontend_instr.itype.opcode == riscv::OpcodeVec) begin
            automatic logic is_vsetvli = frontend_rvv_instr.vsetvli_type.func1 == 1'b0;
            automatic logic is_vsetivli = !is_vsetvli &&
              frontend_rvv_instr.vsetivli_type.func2 == 2'b11;
            automatic logic is_vsetvl = !is_vsetvli && !is_vsetivli &&
              frontend_rvv_instr.vsetvl_type.func7 == 7'b100_0000;
            frontend_perf_counters.vsetvli_count <=
              frontend_perf_counters.vsetvli_count + is_vsetvli;
            frontend_perf_counters.vsetivli_count <=
              frontend_perf_counters.vsetivli_count + is_vsetivli;
            frontend_perf_counters.vsetvl_count <=
              frontend_perf_counters.vsetvl_count + is_vsetvl;
            frontend_perf_counters.vset_result_vl_sum <=
              frontend_perf_counters.vset_result_vl_sum +
              ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vl_d;
            frontend_perf_counters.vset_zero_vl_count <=
              frontend_perf_counters.vset_zero_vl_count +
              (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vl_d == '0);
            frontend_perf_counters.vset_vill_count <=
              frontend_perf_counters.vset_vill_count +
              ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vtype_d.vill;
            frontend_perf_counters.vset_vl_change_count <=
              frontend_perf_counters.vset_vl_change_count +
              (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vl_d !=
               ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vl_q);
            frontend_perf_counters.vset_vtype_change_count <=
              frontend_perf_counters.vset_vtype_change_count +
              (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vtype_d !=
               ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vtype_q);
            frontend_perf_counters.vset_lmul_shrink_wait_count <=
              frontend_perf_counters.vset_lmul_shrink_wait_count +
              (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_d == 2'd1);
            for (int unsigned sew = 0; sew < 4; sew++)
              frontend_perf_counters.vset_sew_hist[sew] <=
                frontend_perf_counters.vset_sew_hist[sew] +
                (unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vtype_d.vsew) == sew);
            for (int unsigned lmul = 0; lmul < 8; lmul++)
              frontend_perf_counters.vset_lmul_hist[lmul] <=
                frontend_perf_counters.vset_lmul_hist[lmul] +
                (unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.csr_vtype_d.vlmul) == lmul);
          end else begin
            automatic logic csr_write =
              (frontend_instr.itype.funct3 inside {3'b001, 3'b101}) ||
              ((frontend_instr.itype.funct3 inside {3'b010, 3'b011, 3'b110, 3'b111}) &&
               (frontend_instr.itype.rs1 != '0));
            frontend_perf_counters.vector_csr_count <=
              frontend_perf_counters.vector_csr_count + 1;
            frontend_perf_counters.vector_csr_write_count <=
              frontend_perf_counters.vector_csr_write_count + csr_write;
            frontend_perf_counters.vector_csr_read_only_count <=
              frontend_perf_counters.vector_csr_read_only_count + !csr_write;
          end
        end else begin
          if (|frontend_arch_class) begin
            frontend_perf_counters.arch_opcode_count[
              unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.op)
            ] <= frontend_perf_counters.arch_opcode_count[
              unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.op)
            ] + 1;
            frontend_perf_counters.arch_opcode_zero_vl_count[
              unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.op)
            ] <= frontend_perf_counters.arch_opcode_zero_vl_count[
              unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.op)
            ] + frontend_zero_vl_fire;
            for (int unsigned c = 0; c < NrExecClasses; c++) begin
              frontend_perf_counters.arch_insn_count[c] <=
                frontend_perf_counters.arch_insn_count[c] + frontend_arch_class[c];
              frontend_perf_counters.zero_vl_nop_count[c] <=
                frontend_perf_counters.zero_vl_nop_count[c] +
                (frontend_arch_class[c] && frontend_zero_vl_fire);
            end
          end else begin
            frontend_perf_counters.unclassified_arch_insn_count <=
              frontend_perf_counters.unclassified_arch_insn_count + 1;
          end
        end

        if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o.exception.valid)
          frontend_perf_counters.arch_exception_count <=
            frontend_perf_counters.arch_exception_count + 1;

        if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_vload ||
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_vstore) begin
          automatic mem_class_e mem_id =
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.is_vload ? MemLoad : MemStore;
          automatic logic whole_register =
            frontend_rvv_instr.vmem_type.mop == 2'b00 &&
            frontend_rvv_instr.vmem_type.rs2 == 5'b01000;
          automatic logic mask_memory =
            frontend_rvv_instr.vmem_type.mop == 2'b00 &&
            frontend_rvv_instr.vmem_type.rs2 == 5'b01011;
          automatic logic segment_memory =
            frontend_rvv_instr.vmem_type.nf != 3'b000 && !whole_register;
          automatic logic [63:0] fields = frontend_rvv_instr.vmem_type.nf + 1;
          automatic logic [63:0] elements =
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vl >=
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vstart
              ? ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vl -
                ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vstart
              : 0;
          automatic logic [63:0] total_elements =
            segment_memory ? elements * fields : elements;
          automatic logic [63:0] total_bytes = total_elements <<
            unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.ara_req.vtype.vsew);
          frontend_perf_counters.memory_insn_count[mem_id] <=
            frontend_perf_counters.memory_insn_count[mem_id] + 1;
          frontend_perf_counters.memory_unit_stride_count[mem_id] <=
            frontend_perf_counters.memory_unit_stride_count[mem_id] +
            (frontend_rvv_instr.vmem_type.mop == 2'b00);
          frontend_perf_counters.memory_strided_count[mem_id] <=
            frontend_perf_counters.memory_strided_count[mem_id] +
            (frontend_rvv_instr.vmem_type.mop == 2'b10);
          frontend_perf_counters.memory_indexed_unordered_count[mem_id] <=
            frontend_perf_counters.memory_indexed_unordered_count[mem_id] +
            (frontend_rvv_instr.vmem_type.mop == 2'b01);
          frontend_perf_counters.memory_indexed_ordered_count[mem_id] <=
            frontend_perf_counters.memory_indexed_ordered_count[mem_id] +
            (frontend_rvv_instr.vmem_type.mop == 2'b11);
          frontend_perf_counters.memory_segment_count[mem_id] <=
            frontend_perf_counters.memory_segment_count[mem_id] + segment_memory;
          frontend_perf_counters.memory_whole_register_count[mem_id] <=
            frontend_perf_counters.memory_whole_register_count[mem_id] + whole_register;
          frontend_perf_counters.memory_mask_count[mem_id] <=
            frontend_perf_counters.memory_mask_count[mem_id] + mask_memory;
          frontend_perf_counters.memory_field_count[mem_id] <=
            frontend_perf_counters.memory_field_count[mem_id] + fields;
          frontend_perf_counters.memory_requested_element_count[mem_id] <=
            frontend_perf_counters.memory_requested_element_count[mem_id] + total_elements;
          frontend_perf_counters.memory_requested_byte_count[mem_id] <=
            frontend_perf_counters.memory_requested_byte_count[mem_id] + total_bytes;
          frontend_perf_counters.memory_exception_count[mem_id] <=
            frontend_perf_counters.memory_exception_count[mem_id] +
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.acc_resp_o.exception.valid;
          if (mem_id == MemLoad)
            frontend_perf_counters.load_fault_only_first_count <=
              frontend_perf_counters.load_fault_only_first_count +
              (frontend_rvv_instr.vmem_type.mop == 2'b00 &&
               frontend_rvv_instr.vmem_type.rs2 == 5'b10000);
        end
      end
    end
  end

  /*******************************************
   *  Main sequencer VFU queue occupancy     *
   *******************************************/

  vfu_queue_perf_t vfu_queue_perf_counters;

  always_ff @(posedge clk or negedge rst_n) begin : p_vfu_queue_perf_counters
    if (!rst_n) begin
      vfu_queue_perf_counters <= '{default: '0};
    end else begin
      for (int unsigned v = 0; v < NrVFUs; v++) begin
        automatic int unsigned occupancy = unsigned'(
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.insn_queue_cnt_q[v]
        );
        automatic int unsigned occupancy_bin =
          occupancy < NrQueueOccupancyBins ? occupancy : NrQueueOccupancyBins - 1;
        vfu_queue_perf_counters.sample_cycle[v] <=
          vfu_queue_perf_counters.sample_cycle[v] + 1;
        vfu_queue_perf_counters.occupancy_cycle_sum[v] <=
          vfu_queue_perf_counters.occupancy_cycle_sum[v] + occupancy;
        vfu_queue_perf_counters.nonempty_cycle[v] <=
          vfu_queue_perf_counters.nonempty_cycle[v] + (occupancy != 0);
        vfu_queue_perf_counters.at_capacity_cycle[v] <=
          vfu_queue_perf_counters.at_capacity_cycle[v] +
          (occupancy >= vfu_queue_depth(vfu_e'(v)));
        for (int unsigned b = 0; b < NrQueueOccupancyBins; b++)
          vfu_queue_perf_counters.occupancy_hist[v][b] <=
            vfu_queue_perf_counters.occupancy_hist[v][b] + (occupancy_bin == b);
      end
    end
  end

  /**********************************************
   *  VLSU pipeline and AXI bottleneck metrics  *
   **********************************************/

  logic [NrMemClasses-1:0] memory_addrgen_class;
  logic [NrMemClasses-1:0] memory_addrgen_active;
  logic [NrMemClasses-1:0] memory_addrgen_progress;
  logic [NrMemClasses-1:0] memory_addrgen_operand_wait;
  logic [NrMemClasses-1:0] memory_indexed_spill_wait;
  logic [NrMemClasses-1:0] memory_last_translation_wait;
  logic [NrMemClasses-1:0] memory_addrgen_queue_consumer_wait;
  logic [NrMemClasses-1:0] memory_addrgen_queue_full;
  logic [NrMemClasses-1:0] memory_core_store_pending_wait;
  logic [NrMemClasses-1:0] memory_mmu_request;
  logic [NrMemClasses-1:0] memory_mmu_wait;
  logic [NrMemClasses-1:0] memory_mmu_dtlb_hit;
  logic [NrMemClasses-1:0] memory_mmu_response;
  logic [NrMemClasses-1:0] memory_mmu_exception;
  logic [NrMemClasses-1:0] memory_axi_address_valid;
  logic [NrMemClasses-1:0] memory_axi_address_fire;
  logic [NrMemClasses-1:0] memory_axi_address_backpressure;
  logic [NrMemClasses-1:0] memory_axi_data_valid;
  logic [NrMemClasses-1:0] memory_axi_data_fire;
  logic [NrMemClasses-1:0] memory_axi_data_backpressure;
  logic [NrMemClasses-1:0] memory_axi_data_wait;
  logic [NrMemClasses-1:0] memory_axi_response_valid;
  logic [NrMemClasses-1:0] memory_axi_response_fire;
  logic [NrMemClasses-1:0] memory_axi_response_wait;
  logic [NrMemClasses-1:0] memory_mask_wait;
  logic [NrMemClasses-1:0] memory_result_queue_full;
  logic [NrMemClasses-1:0] memory_operand_wait;
  logic [NrMemClasses-1:0] memory_result_backpressure;
  logic [NrMemClasses-1:0] memory_completion;
  logic [NrMemClasses-1:0] memory_exception;
  logic [NrMemClasses-1:0][63:0] memory_axi_transfer_bytes;
  logic [NrMemClasses-1:0][63:0] memory_axi_useful_bytes;
  logic [NrMemClasses-1:0][63:0] memory_operand_handshake_lane_samples;
  logic [NrMemClasses-1:0][63:0] memory_result_request_lane_samples;
  logic [NrMemClasses-1:0][63:0] memory_result_handshake_lane_samples;
  logic [NrMemClasses-1:0][63:0] memory_result_backpressure_lane_samples;
  memory_perf_t memory_perf_counters;
  logic [NrMemClasses-1:0][AxiLatencyFifoDepth-1:0][63:0]
    memory_axi_start_cycle_q;
  logic [NrMemClasses-1:0][AxiLatencyPtrWidth-1:0]
    memory_axi_start_write_pnt_q, memory_axi_start_read_pnt_q;
  logic [NrMemClasses-1:0][AxiOutstandingWidth-1:0]
    memory_axi_outstanding_q;

  always_comb begin : p_memory_perf_events
    automatic ara_op_e addrgen_op =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.pe_req_q.op;
    automatic logic addrgen_is_load = addrgen_op inside {[VLE:VLXE]};
    automatic logic addrgen_busy =
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.state_q != '0) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_state_q != '0) ||
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_empty;
    automatic logic addrgen_made_progress;
    automatic logic load_r_fire;
    automatic logic store_w_fire;

    memory_addrgen_class = '0;
    if (addrgen_busy)
      memory_addrgen_class[addrgen_is_load ? MemLoad : MemStore] = 1'b1;
    memory_addrgen_active = memory_addrgen_class & {NrMemClasses{addrgen_busy}};

    load_r_fire =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.r_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.r_ready;
    store_w_fire =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.w_ready;
    addrgen_made_progress =
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.state_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.state_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_state_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_state_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_op_cnt_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_op_cnt_q) ||
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_push ||
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_pop ||
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.addrgen_ack_o ||
      load_r_fire || store_w_fire ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.b_valid &&
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.b_ready);
    memory_addrgen_progress = memory_addrgen_class & {NrMemClasses{addrgen_made_progress}};
    memory_addrgen_operand_wait = memory_addrgen_class &
      {NrMemClasses{(addrgen_op inside {VLXE, VSXE}) &&
                    (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.state_q == 3'd2) &&
                    !(&ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.addrgen_operand_valid_i)}};
    memory_indexed_spill_wait = memory_addrgen_class &
      {NrMemClasses{(addrgen_op inside {VLXE, VSXE}) &&
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_vaddr_valid_q &&
                    !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_vaddr_ready_d}};
    memory_last_translation_wait = memory_addrgen_class &
      {NrMemClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.state_q == 3'd4}};
    memory_addrgen_queue_consumer_wait = memory_addrgen_class &
      {NrMemClasses{!ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_empty &&
                    !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_pop}};
    memory_addrgen_queue_full = memory_addrgen_class &
      {NrMemClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_full}};
    memory_core_store_pending_wait = memory_addrgen_class &
      {NrMemClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_state_q == 3'd2}};

    memory_mmu_request = '0;
    memory_mmu_wait = '0;
    memory_mmu_dtlb_hit = '0;
    if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_req_o) begin
      automatic mem_class_e mmu_id =
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_is_store_o
          ? MemStore : MemLoad;
      memory_mmu_request[mmu_id] = 1'b1;
      memory_mmu_wait[mmu_id] =
        !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_valid_i;
      memory_mmu_dtlb_hit[mmu_id] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_dtlb_hit_i;
    end
    memory_mmu_response = '0;
    memory_mmu_exception = '0;
    if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_valid_i && addrgen_busy) begin
      automatic mem_class_e mmu_id =
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_q.is_load
          ? MemLoad : MemStore;
      memory_mmu_response[mmu_id] = 1'b1;
      memory_mmu_exception[mmu_id] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_exception_i.valid;
    end

    memory_axi_address_valid = '0;
    memory_axi_address_fire = '0;
    memory_axi_address_backpressure = '0;
    memory_axi_address_valid[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.ar_valid;
    memory_axi_address_fire[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.ar_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.ar_ready;
    memory_axi_address_backpressure[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.ar_valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.ar_ready;
    memory_axi_address_valid[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.aw_valid;
    memory_axi_address_fire[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.aw_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.aw_ready;
    memory_axi_address_backpressure[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.aw_valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.aw_ready;

    memory_axi_data_valid = '0;
    memory_axi_data_fire = '0;
    memory_axi_data_backpressure = '0;
    memory_axi_data_wait = '0;
    memory_axi_data_valid[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.r_valid;
    memory_axi_data_fire[MemLoad] = load_r_fire;
    memory_axi_data_backpressure[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.r_valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.r_ready;
    memory_axi_data_wait[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vldu.vinsn_issue_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_addrgen_req_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_addrgen_req.is_load &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.r_valid;
    memory_axi_data_valid[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w_valid;
    memory_axi_data_fire[MemStore] = store_w_fire;
    memory_axi_data_backpressure[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w_valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.w_ready;
    memory_axi_data_wait[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.vinsn_issue_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_addrgen_req_valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_addrgen_req.is_load &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w_valid;

    memory_axi_response_valid = '0;
    memory_axi_response_fire = '0;
    memory_axi_response_wait = '0;
    memory_axi_response_valid[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.r_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.r.last;
    memory_axi_response_fire[MemLoad] = memory_axi_response_valid[MemLoad] &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.r_ready;
    memory_axi_response_valid[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.b_valid;
    memory_axi_response_fire[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.b_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.b_ready;
    memory_axi_response_wait[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.vinsn_commit_valid &&
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.vinsn_queue_q.issue_pnt !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.vinsn_queue_q.commit_pnt) &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.b_valid;

    memory_mask_wait = '0;
    memory_mask_wait[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vldu.vinsn_issue_valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vldu.vinsn_issue_q.vm &&
      !(|ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vldu.mask_valid_q);
    memory_mask_wait[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.vinsn_issue_valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.vinsn_issue_q.vm &&
      !(|ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.mask_valid_q);
    memory_result_queue_full = '0;
    memory_result_queue_full[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vldu.result_queue_full;
    memory_operand_wait = '0;
    memory_operand_wait[MemLoad] = memory_addrgen_operand_wait[MemLoad];
    memory_operand_wait[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.vinsn_issue_valid &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_addrgen_req_valid &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_addrgen_req.is_load &&
      !(&ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.stu_operand_valid);
    memory_result_backpressure = '0;
    memory_result_backpressure[MemLoad] =
      |(ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_req_o &
        ~ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_gnt_i);
    memory_result_backpressure[MemStore] =
      memory_axi_data_backpressure[MemStore] ||
      (memory_axi_response_valid[MemStore] && !memory_axi_response_fire[MemStore]);

    memory_axi_transfer_bytes = '0;
    if (load_r_fire)
      memory_axi_transfer_bytes[MemLoad] = 64'd1 <<
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_addrgen_req.size;
    if (store_w_fire)
      memory_axi_transfer_bytes[MemStore] = 64'd1 <<
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_addrgen_req.size;
    memory_axi_useful_bytes = '0;
    if (store_w_fire)
      memory_axi_useful_bytes[MemStore] =
        $countones(ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w.strb);

    memory_operand_handshake_lane_samples = '0;
    memory_result_request_lane_samples = '0;
    memory_result_handshake_lane_samples = '0;
    memory_result_backpressure_lane_samples = '0;
    for (int unsigned lane = 0; lane < NrLanes; lane++) begin
      memory_operand_handshake_lane_samples[MemLoad] +=
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.addrgen_operand_valid_i[lane] &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.addrgen_operand_ready_o;
      memory_operand_handshake_lane_samples[MemStore] +=
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.stu_operand_valid_i[lane] &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.stu_operand_ready_o[lane];
      memory_result_request_lane_samples[MemLoad] +=
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_req_o[lane];
      memory_result_handshake_lane_samples[MemLoad] +=
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_req_o[lane] &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_gnt_i[lane];
      memory_result_backpressure_lane_samples[MemLoad] +=
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_req_o[lane] &&
        !ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_gnt_i[lane];
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_req_o[lane] &&
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_gnt_i[lane])
        memory_axi_useful_bytes[MemLoad] +=
          $countones(ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.ldu_result_be_o[lane]);
    end

    memory_completion = '0;
    memory_completion[MemLoad] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.load_complete;
    memory_completion[MemStore] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.store_complete;
    memory_exception = '0;
    if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.addrgen_ack_o &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.addrgen_exception_o.valid)
      memory_exception[addrgen_is_load ? MemLoad : MemStore] = 1'b1;
  end

  always_ff @(posedge clk or negedge rst_n) begin : p_memory_perf_counters
    if (!rst_n) begin
      memory_perf_counters <= '{default: '0};
      memory_axi_start_cycle_q <= '0;
      memory_axi_start_write_pnt_q <= '0;
      memory_axi_start_read_pnt_q <= '0;
      memory_axi_outstanding_q <= '0;
    end else begin
      for (int unsigned m = 0; m < NrMemClasses; m++) begin
        automatic int unsigned outstanding = unsigned'(memory_axi_outstanding_q[m]);
        automatic int unsigned outstanding_bin = outstanding < NrAxiOutstandingBins
          ? outstanding : NrAxiOutstandingBins - 1;
        automatic logic pop_accepted = memory_axi_response_fire[m] &&
          (outstanding != 0);
        automatic logic push_accepted = memory_axi_address_fire[m] &&
          ((outstanding < AxiLatencyFifoDepth) || pop_accepted);
        memory_perf_counters.addrgen_active_cycle[m] <=
          memory_perf_counters.addrgen_active_cycle[m] + memory_addrgen_active[m];
        memory_perf_counters.addrgen_progress_cycle[m] <=
          memory_perf_counters.addrgen_progress_cycle[m] + memory_addrgen_progress[m];
        memory_perf_counters.addrgen_no_progress_cycle[m] <=
          memory_perf_counters.addrgen_no_progress_cycle[m] +
          (memory_addrgen_active[m] && !memory_addrgen_progress[m]);
        for (int unsigned s = 0; s < 5; s++)
          memory_perf_counters.addrgen_state_cycle[m][s] <=
            memory_perf_counters.addrgen_state_cycle[m][s] +
            (memory_addrgen_active[m] &&
             unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.state_q) == s);
        for (int unsigned s = 0; s < 4; s++)
          memory_perf_counters.axi_addrgen_state_cycle[m][s] <=
            memory_perf_counters.axi_addrgen_state_cycle[m][s] +
            (memory_addrgen_active[m] &&
             unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_state_q) == s);
        memory_perf_counters.addrgen_operand_wait_cycle[m] <=
          memory_perf_counters.addrgen_operand_wait_cycle[m] + memory_addrgen_operand_wait[m];
        memory_perf_counters.indexed_spill_wait_cycle[m] <=
          memory_perf_counters.indexed_spill_wait_cycle[m] + memory_indexed_spill_wait[m];
        memory_perf_counters.last_translation_wait_cycle[m] <=
          memory_perf_counters.last_translation_wait_cycle[m] + memory_last_translation_wait[m];
        memory_perf_counters.addrgen_queue_consumer_wait_cycle[m] <=
          memory_perf_counters.addrgen_queue_consumer_wait_cycle[m] +
          memory_addrgen_queue_consumer_wait[m];
        memory_perf_counters.addrgen_queue_full_cycle[m] <=
          memory_perf_counters.addrgen_queue_full_cycle[m] + memory_addrgen_queue_full[m];
        memory_perf_counters.core_store_pending_wait_cycle[m] <=
          memory_perf_counters.core_store_pending_wait_cycle[m] + memory_core_store_pending_wait[m];
        memory_perf_counters.mmu_request_cycle[m] <=
          memory_perf_counters.mmu_request_cycle[m] + memory_mmu_request[m];
        memory_perf_counters.mmu_wait_cycle[m] <=
          memory_perf_counters.mmu_wait_cycle[m] + memory_mmu_wait[m];
        memory_perf_counters.mmu_dtlb_hit_count[m] <=
          memory_perf_counters.mmu_dtlb_hit_count[m] + memory_mmu_dtlb_hit[m];
        memory_perf_counters.mmu_response_count[m] <=
          memory_perf_counters.mmu_response_count[m] + memory_mmu_response[m];
        memory_perf_counters.mmu_exception_count[m] <=
          memory_perf_counters.mmu_exception_count[m] + memory_mmu_exception[m];
        memory_perf_counters.axi_address_valid_cycle[m] <=
          memory_perf_counters.axi_address_valid_cycle[m] + memory_axi_address_valid[m];
        memory_perf_counters.axi_address_fire_count[m] <=
          memory_perf_counters.axi_address_fire_count[m] + memory_axi_address_fire[m];
        memory_perf_counters.axi_address_backpressure_cycle[m] <=
          memory_perf_counters.axi_address_backpressure_cycle[m] +
          memory_axi_address_backpressure[m];
        memory_perf_counters.axi_data_valid_cycle[m] <=
          memory_perf_counters.axi_data_valid_cycle[m] + memory_axi_data_valid[m];
        memory_perf_counters.axi_data_fire_count[m] <=
          memory_perf_counters.axi_data_fire_count[m] + memory_axi_data_fire[m];
        memory_perf_counters.axi_data_backpressure_cycle[m] <=
          memory_perf_counters.axi_data_backpressure_cycle[m] + memory_axi_data_backpressure[m];
        memory_perf_counters.axi_data_wait_cycle[m] <=
          memory_perf_counters.axi_data_wait_cycle[m] + memory_axi_data_wait[m];
        memory_perf_counters.axi_response_valid_cycle[m] <=
          memory_perf_counters.axi_response_valid_cycle[m] + memory_axi_response_valid[m];
        memory_perf_counters.axi_response_fire_count[m] <=
          memory_perf_counters.axi_response_fire_count[m] + memory_axi_response_fire[m];
        memory_perf_counters.axi_response_wait_cycle[m] <=
          memory_perf_counters.axi_response_wait_cycle[m] + memory_axi_response_wait[m];
        memory_perf_counters.axi_transfer_byte_count[m] <=
          memory_perf_counters.axi_transfer_byte_count[m] + memory_axi_transfer_bytes[m];
        memory_perf_counters.axi_useful_byte_count[m] <=
          memory_perf_counters.axi_useful_byte_count[m] + memory_axi_useful_bytes[m];
        memory_perf_counters.axi_outstanding_sample_cycle[m] <=
          memory_perf_counters.axi_outstanding_sample_cycle[m] + 1;
        memory_perf_counters.axi_outstanding_cycle_sum[m] <=
          memory_perf_counters.axi_outstanding_cycle_sum[m] + outstanding;
        memory_perf_counters.axi_outstanding_nonzero_cycle[m] <=
          memory_perf_counters.axi_outstanding_nonzero_cycle[m] + (outstanding != 0);
        for (int unsigned b = 0; b < NrAxiOutstandingBins; b++)
          memory_perf_counters.axi_outstanding_hist[m][b] <=
            memory_perf_counters.axi_outstanding_hist[m][b] + (outstanding_bin == b);
        memory_perf_counters.axi_tracking_overflow_count[m] <=
          memory_perf_counters.axi_tracking_overflow_count[m] +
          (memory_axi_address_fire[m] && !push_accepted);
        memory_perf_counters.axi_tracking_underflow_count[m] <=
          memory_perf_counters.axi_tracking_underflow_count[m] +
          (memory_axi_response_fire[m] && !pop_accepted);

        if (push_accepted) begin
          memory_axi_start_cycle_q[m][memory_axi_start_write_pnt_q[m]] <= wall_cycle;
          memory_axi_start_write_pnt_q[m] <= memory_axi_start_write_pnt_q[m] + 1'b1;
        end
        if (pop_accepted) begin
          automatic logic [63:0] request_latency = wall_cycle -
            memory_axi_start_cycle_q[m][memory_axi_start_read_pnt_q[m]] + 1;
          memory_axi_start_read_pnt_q[m] <= memory_axi_start_read_pnt_q[m] + 1'b1;
          memory_perf_counters.axi_request_latency_count[m] <=
            memory_perf_counters.axi_request_latency_count[m] + 1;
          memory_perf_counters.axi_request_latency_cycle[m] <=
            memory_perf_counters.axi_request_latency_cycle[m] + request_latency;
          if (request_latency <= 8)
            memory_perf_counters.axi_request_latency_hist[m][0] <=
              memory_perf_counters.axi_request_latency_hist[m][0] + 1;
          else if (request_latency <= 32)
            memory_perf_counters.axi_request_latency_hist[m][1] <=
              memory_perf_counters.axi_request_latency_hist[m][1] + 1;
          else if (request_latency <= 128)
            memory_perf_counters.axi_request_latency_hist[m][2] <=
              memory_perf_counters.axi_request_latency_hist[m][2] + 1;
          else
            memory_perf_counters.axi_request_latency_hist[m][3] <=
              memory_perf_counters.axi_request_latency_hist[m][3] + 1;
        end
        unique case ({push_accepted, pop_accepted})
          2'b10: memory_axi_outstanding_q[m] <= memory_axi_outstanding_q[m] + 1'b1;
          2'b01: memory_axi_outstanding_q[m] <= memory_axi_outstanding_q[m] - 1'b1;
          default: memory_axi_outstanding_q[m] <= memory_axi_outstanding_q[m];
        endcase
        memory_perf_counters.mask_wait_cycle[m] <=
          memory_perf_counters.mask_wait_cycle[m] + memory_mask_wait[m];
        memory_perf_counters.result_queue_full_cycle[m] <=
          memory_perf_counters.result_queue_full_cycle[m] + memory_result_queue_full[m];
        memory_perf_counters.operand_wait_cycle[m] <=
          memory_perf_counters.operand_wait_cycle[m] + memory_operand_wait[m];
        memory_perf_counters.result_backpressure_cycle[m] <=
          memory_perf_counters.result_backpressure_cycle[m] + memory_result_backpressure[m];
        memory_perf_counters.operand_handshake_lane_sample[m] <=
          memory_perf_counters.operand_handshake_lane_sample[m] +
          memory_operand_handshake_lane_samples[m];
        memory_perf_counters.result_request_lane_sample[m] <=
          memory_perf_counters.result_request_lane_sample[m] +
          memory_result_request_lane_samples[m];
        memory_perf_counters.result_handshake_lane_sample[m] <=
          memory_perf_counters.result_handshake_lane_sample[m] +
          memory_result_handshake_lane_samples[m];
        memory_perf_counters.result_backpressure_lane_sample[m] <=
          memory_perf_counters.result_backpressure_lane_sample[m] +
          memory_result_backpressure_lane_samples[m];
        memory_perf_counters.completion_count[m] <=
          memory_perf_counters.completion_count[m] + memory_completion[m];
        memory_perf_counters.exception_count[m] <=
          memory_perf_counters.exception_count[m] + memory_exception[m];
      end
    end
  end

  /********************************************
   *  Backend-instruction execution metrics  *
   ********************************************/

  // Per-instruction bookkeeping supplies additive latency sums and histograms.
  // The instruction ID is assigned when pe_req_d first becomes valid.
  exec_class_mask_t [NrVInsn-1:0] exec_class_by_id_q;
  ara_op_e [NrVInsn-1:0]          exec_op_by_id_q;
  logic [NrVInsn-1:0][1:0]        exec_sew_by_id_q;
  logic [NrVInsn-1:0][2:0]        exec_lmul_by_id_q;
  logic [NrVInsn-1:0]             exec_masked_by_id_q;
  logic [NrVInsn-1:0][63:0]       exec_issue_cycle_by_id_q;
  logic [NrVInsn-1:0][63:0]       exec_dispatch_wait_by_id_q;
  logic [63:0]                    exec_pending_accept_cycle_q;
  logic                           exec_pending_accept_valid_q;
  exec_class_mask_t               exec_pending_class_q;
  ara_op_e                        exec_pending_op_q;
  logic                           exec_scalar_move_pending_q;
  exec_class_mask_t               exec_scalar_move_class_q;
  ara_op_e                        exec_scalar_move_op_q;
  logic [1:0]                     exec_scalar_move_sew_q;
  logic [2:0]                     exec_scalar_move_lmul_q;
  logic [63:0]                    exec_scalar_move_issue_cycle_q;
  logic [63:0]                    exec_scalar_move_dispatch_wait_q;

  exec_class_mask_t accepted_exec_class;
  exec_class_mask_t first_issue_class;
  ara_op_e          first_issue_op;
  exec_class_mask_t exec_class_active;
  exec_class_mask_t exec_masked_class_active;
  exec_class_mask_t exec_completion_class;
  logic [NrExecClasses-1:0][63:0] exec_inflight_count;
  logic [NrExecClasses-1:0][63:0] exec_completion_count;
  logic [NrExecClasses-1:0][63:0] exec_completion_latency;
  logic [NrExecClasses-1:0][63:0] exec_completion_end_to_end_latency;
  logic [NrExecClasses-1:0][3:0][63:0] exec_completion_latency_hist;
  logic [NrAraOps-1:0][63:0] exec_opcode_completion_count;
  logic [NrAraOps-1:0][63:0] exec_opcode_completion_latency;
  logic [NrAraOps-1:0][3:0][63:0] exec_opcode_completion_latency_hist;
  logic [NrAraOps-1:0][3:0][7:0][63:0] exec_opcode_shape_completion_count;
  logic [NrAraOps-1:0][3:0][7:0][63:0] exec_opcode_shape_completion_latency;
  logic        exec_scalar_move_complete;

  logic        exec_first_issue;
  logic [63:0] exec_dispatch_wait;
  logic [1:0]  exec_dispatch_wait_bin;
  logic [NrExecClasses-1:0] exec_dispatch_request;
  logic [NrExecClasses-1:0] exec_dispatch_blocked;
  logic [NrExecClasses-1:0] exec_fu_queue_full;
  logic [NrExecClasses-1:0] exec_mask_queue_full;
  logic [NrExecClasses-1:0] exec_slide_queue_full;
  logic [NrExecClasses-1:0] exec_id_pool_full;
  logic [NrExecClasses-1:0] exec_response_wait;
  logic [NrExecClasses-1:0] exec_other_dispatch_blocked;
  logic [NrExecClasses-1:0] exec_operand_request_blocked;
  logic [NrAraOps-1:0]       exec_opcode_dispatch_request;
  logic [NrAraOps-1:0]       exec_opcode_dispatch_blocked;
  logic [NrAraOps-1:0]       exec_opcode_fu_queue_full;
  logic [NrAraOps-1:0]       exec_opcode_mask_queue_full;
  logic [NrAraOps-1:0]       exec_opcode_slide_queue_full;
  logic [NrAraOps-1:0]       exec_opcode_id_pool_full;
  logic [NrAraOps-1:0]       exec_opcode_response_wait;
  logic [NrAraOps-1:0]       exec_opcode_other_dispatch_blocked;
  logic [NrAraOps-1:0]       exec_opcode_operand_request_blocked;
  logic [NrAraOps-1:0]       exec_opcode_primary_fu_queue_full;
  logic [NrAraOps-1:0]       exec_opcode_primary_mask_queue_full;
  logic [NrAraOps-1:0]       exec_opcode_primary_slide_queue_full;
  logic [NrAraOps-1:0]       exec_opcode_primary_id_pool_full;
  logic [NrAraOps-1:0]       exec_opcode_primary_response_wait;
  logic [NrAraOps-1:0]       exec_opcode_primary_lane_desync;
  logic [NrAraOps-1:0]       exec_opcode_primary_sequencer_block;
  logic [NrAraOps-1:0]       exec_opcode_primary_operand_request_blocked;
  logic [NrAraOps-1:0]       exec_opcode_primary_other_dispatch_blocked;
  logic [NrAraOps-1:0]       exec_opcode_primary_dispatch_unattributed;
  logic [NrAraOps-1:0]       exec_opcode_active_cycle;
  logic [NrAraOps-1:0]       exec_opcode_primary_result_backpressure;
  logic [NrAraOps-1:0]       exec_opcode_primary_result_queue_full;
  logic [NrAraOps-1:0]       exec_opcode_primary_latency_order_stall;
  logic [NrAraOps-1:0]       exec_opcode_primary_unit_input_backpressure;
  logic [NrAraOps-1:0]       exec_opcode_primary_operand_wait;
  logic [NrAraOps-1:0]       exec_opcode_primary_long_latency_busy;
  logic [NrAraOps-1:0]       exec_opcode_primary_special_path;
  logic [NrAraOps-1:0]       exec_opcode_primary_progress;
  logic [NrAraOps-1:0]       exec_opcode_primary_unattributed;
  logic [NrExecClasses-1:0] exec_raw_hazard;
  logic [NrExecClasses-1:0] exec_war_hazard;
  logic [NrExecClasses-1:0] exec_waw_hazard;
  logic [NrExecClasses-1:0] exec_false_hazard;
  logic [NrExecClasses-1:0] exec_sequencer_block;
  logic [NrExecClasses-1:0] exec_lane_desync;
  exec_class_mask_t exec_primary_result_backpressure;
  exec_class_mask_t exec_primary_result_queue_full;
  exec_class_mask_t exec_primary_latency_order_stall;
  exec_class_mask_t exec_primary_unit_input_backpressure;
  exec_class_mask_t exec_primary_operand_wait;
  exec_class_mask_t exec_primary_long_latency_busy;
  exec_class_mask_t exec_primary_special_path;
  exec_class_mask_t exec_primary_progress;
  exec_class_mask_t exec_primary_unattributed;
  exec_class_mask_t exec_primary_fu_queue_full;
  exec_class_mask_t exec_primary_mask_queue_full;
  exec_class_mask_t exec_primary_slide_queue_full;
  exec_class_mask_t exec_primary_id_pool_full;
  exec_class_mask_t exec_primary_response_wait;
  exec_class_mask_t exec_primary_lane_desync;
  exec_class_mask_t exec_primary_sequencer_block;
  exec_class_mask_t exec_primary_operand_request_blocked;
  exec_class_mask_t exec_primary_other_dispatch_blocked;
  exec_class_mask_t exec_primary_dispatch_unattributed;
  logic [NrExecClasses-1:0][63:0] exec_result_queue_occupancy_lane_samples;
  logic [NrExecClasses-1:0][63:0] exec_issue_progress_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_operand_wait_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_unit_input_backpressure_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_latency_order_stall_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_result_queue_full_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_result_backpressure_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_long_latency_busy_lane_sample;
  logic [NrLanes-1:0][NrExecClasses-1:0][63:0]
    exec_lane_result_queue_occupancy;
  logic [NrLanes-1:0][NrExecClasses-1:0][63:0] exec_lane_vrf_read_request;
  logic [NrLanes-1:0][NrExecClasses-1:0][63:0] exec_lane_vrf_read_grant;
  logic [NrLanes-1:0][NrExecClasses-1:0][63:0] exec_lane_vrf_bank_conflict;
  logic [NrLanes-1:0][NrExecClasses-1:0][63:0] exec_lane_vrf_hazard_stall;
  logic [NrLanes-1:0][NrExecClasses-1:0][63:0] exec_lane_operand_queue_backpressure;
  logic [NrExecClasses-1:0][63:0] exec_vrf_read_request_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_vrf_read_grant_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_vrf_bank_conflict_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_vrf_hazard_stall_lane_sample;
  logic [NrExecClasses-1:0][63:0] exec_operand_queue_backpressure_lane_sample;
  logic [NrLanes-1:0][NrMfpuSubunits-1:0] exec_lane_mfpu_input_fire;
  logic [NrLanes-1:0][NrMfpuSubunits-1:0] exec_lane_mfpu_input_backpressure;
  logic [NrLanes-1:0][NrMfpuSubunits-1:0] exec_lane_mfpu_output_fire;
  logic [NrLanes-1:0][NrMfpuSubunits-1:0] exec_lane_mfpu_processing;
  logic [NrLanes-1:0][NrValuStates-1:0] exec_lane_valu_state;
  logic [NrLanes-1:0][NrMfpuStates-1:0] exec_lane_mfpu_state;
  logic [NrMfpuSubunits-1:0][63:0] exec_mfpu_input_fire_lane_sample;
  logic [NrMfpuSubunits-1:0][63:0] exec_mfpu_input_backpressure_lane_sample;
  logic [NrMfpuSubunits-1:0][63:0] exec_mfpu_output_fire_lane_sample;
  logic [NrMfpuSubunits-1:0][63:0] exec_mfpu_processing_lane_sample;
  logic [NrValuStates-1:0][63:0] exec_valu_state_lane_sample;
  logic [NrMfpuStates-1:0][63:0] exec_mfpu_state_lane_sample;
  exec_class_mask_t exec_predicate_class;
  exec_class_mask_t exec_mask_issue_class;
  logic exec_predicate_packet;
  logic [63:0] exec_predicate_elements;
  logic [63:0] exec_predicate_active_elements;
  logic [2:0] exec_predicate_density_bin;

  exec_event_t [NrLanes-1:0] lane_exec_event;
  exec_event_t                exec_event;
  exec_perf_t                 exec_perf_counters;

  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_window;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_no_candidate;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_candidate;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_eligible;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_reject_unsupported;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_reject_mask;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_reject_short_vl;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_reject_opcode;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_reject_sew;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_reject_rounding;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_start;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_active;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_background_issue;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_primary_conflict;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_complete;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_complete_wait;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_full_promotion;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_partial_promotion;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_root_nonempty;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_root_full;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0][2:0] red_stream_root_occupancy;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_root_push;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_root_pop;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0] red_stream_slack_defer;
  logic [NrLanes-1:0][NrRedStreamClasses-1:0][2:0] red_stream_slack_score;
  red_stream_perf_t red_stream_perf_counters;

  // Observe lane-local VALU/VMFPU progress and backpressure. OR-reduction in
  // the central block turns simultaneous lane events into one wall-clock cycle.
  for (genvar l = 0; l < NrLanes; l++) begin : gen_exec_perf_lane_events
    // Stream opportunity and rejection attribution.  Keep the outcome
    // partition in the observer rather than the scheduler so the experiment
    // can evolve without turning performance accounting into functional RTL.
    always_comb begin : p_red_stream_lane_events
`ifdef ARA_RED_CONTEXT_STREAM_4LANE
      automatic int unsigned valu_next_pnt =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_queue_q.issue_pnt == ValuInsnQueueDepth-1
          ? 0
          : ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
              vinsn_queue_q.issue_pnt + 1;
      automatic int unsigned fp_next_pnt =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_queue_q.issue_pnt == MfpuInsnQueueDepth-1
          ? 0
          : ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
              vinsn_queue_q.issue_pnt + 1;
      automatic ara_op_e valu_fg_op =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_commit.op;
      automatic ara_op_e valu_next_op =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_queue_q.vinsn[valu_next_pnt].op;
      automatic logic valu_fg_vm =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_commit.vm;
      automatic logic valu_next_vm =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_queue_q.vinsn[valu_next_pnt].vm;
      automatic int unsigned valu_fg_vl =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_commit.vl;
      automatic int unsigned valu_next_vl =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_queue_q.vinsn[valu_next_pnt].vl;
      automatic rvv_pkg::vew_e valu_fg_sew =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_commit.vtype.vsew;
      automatic rvv_pkg::vew_e valu_next_sew =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_queue_q.vinsn[valu_next_pnt].vtype.vsew;
      automatic ara_op_e fp_fg_op =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_processing_q.op;
      automatic ara_op_e fp_next_op =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_queue_q.vinsn[fp_next_pnt].op;
      automatic logic fp_fg_vm =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_processing_q.vm;
      automatic logic fp_next_vm =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_queue_q.vinsn[fp_next_pnt].vm;
      automatic int unsigned fp_fg_vl =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_processing_q.vl;
      automatic int unsigned fp_next_vl =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_queue_q.vinsn[fp_next_pnt].vl;
      automatic rvv_pkg::vew_e fp_fg_sew =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_processing_q.vtype.vsew;
      automatic rvv_pkg::vew_e fp_next_sew =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_queue_q.vinsn[fp_next_pnt].vtype.vsew;
      automatic fpnew_pkg::roundmode_e fp_fg_rm =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_processing_q.fp_rm;
      automatic fpnew_pkg::roundmode_e fp_next_rm =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_queue_q.vinsn[fp_next_pnt].fp_rm;
      automatic logic valu_window =
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          alu_state_q inside {3'd2, 3'd3, 3'd5}) &&
        !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_active_q &&
        !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_complete_q &&
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_root_count_q < ValuInsnQueueDepth-1);
      automatic logic fp_window =
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          mfpu_state_q inside {3'd2, 3'd3, 3'd5}) &&
        !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_active_q &&
        !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_complete_q &&
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_root_count_q < MfpuInsnQueueDepth-1);
      automatic logic valu_candidate = valu_window &&
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          vinsn_queue_q.issue_cnt > 1);
      automatic logic fp_candidate = fp_window &&
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          vinsn_queue_q.issue_cnt > 1);
`endif

      red_stream_window[l] = '0;
      red_stream_no_candidate[l] = '0;
      red_stream_candidate[l] = '0;
      red_stream_eligible[l] = '0;
      red_stream_reject_unsupported[l] = '0;
      red_stream_reject_mask[l] = '0;
      red_stream_reject_short_vl[l] = '0;
      red_stream_reject_opcode[l] = '0;
      red_stream_reject_sew[l] = '0;
      red_stream_reject_rounding[l] = '0;
      red_stream_start[l] = '0;
      red_stream_active[l] = '0;
      red_stream_background_issue[l] = '0;
      red_stream_primary_conflict[l] = '0;
      red_stream_complete[l] = '0;
      red_stream_complete_wait[l] = '0;
      red_stream_full_promotion[l] = '0;
      red_stream_partial_promotion[l] = '0;
      red_stream_root_nonempty[l] = '0;
      red_stream_root_full[l] = '0;
      red_stream_root_occupancy[l] = '0;
      red_stream_root_push[l] = '0;
      red_stream_root_pop[l] = '0;
      red_stream_slack_defer[l] = '0;
      red_stream_slack_score[l] = '0;

`ifdef ARA_RED_CONTEXT_STREAM_4LANE
      red_stream_window[l][RedStreamValu] = valu_window;
      red_stream_window[l][RedStreamFp] = fp_window;
      red_stream_no_candidate[l][RedStreamValu] = valu_window && !valu_candidate;
      red_stream_no_candidate[l][RedStreamFp] = fp_window && !fp_candidate;
      red_stream_candidate[l][RedStreamValu] = valu_candidate;
      red_stream_candidate[l][RedStreamFp] = fp_candidate;

      // Priority-partition every candidate into one terminal outcome.
      if (valu_candidate) begin
        if (!(valu_fg_op inside {[VREDSUM:VWREDSUM]}) ||
            !(valu_next_op inside {[VREDSUM:VWREDSUM]}))
          red_stream_reject_unsupported[l][RedStreamValu] = 1'b1;
        else if (!valu_fg_vm || !valu_next_vm)
          red_stream_reject_mask[l][RedStreamValu] = 1'b1;
        else if (valu_fg_vl < 8 || valu_next_vl < 8)
          red_stream_reject_short_vl[l][RedStreamValu] = 1'b1;
`ifndef ARA_RED_HETERO_STREAM_4LANE
        else if (valu_fg_op != valu_next_op)
          red_stream_reject_opcode[l][RedStreamValu] = 1'b1;
        else if (valu_fg_sew != valu_next_sew)
          red_stream_reject_sew[l][RedStreamValu] = 1'b1;
`endif
        else
          red_stream_eligible[l][RedStreamValu] = 1'b1;
      end
      if (fp_candidate) begin
        if (!(fp_fg_op inside {VFREDUSUM, VFREDMIN, VFREDMAX}) ||
            !(fp_next_op inside {VFREDUSUM, VFREDMIN, VFREDMAX}))
          red_stream_reject_unsupported[l][RedStreamFp] = 1'b1;
        else if (!fp_fg_vm || !fp_next_vm)
          red_stream_reject_mask[l][RedStreamFp] = 1'b1;
        else if (fp_fg_vl < 8 || fp_next_vl < 8)
          red_stream_reject_short_vl[l][RedStreamFp] = 1'b1;
`ifndef ARA_RED_HETERO_STREAM_4LANE
        else if (fp_fg_op != fp_next_op)
          red_stream_reject_opcode[l][RedStreamFp] = 1'b1;
`endif
        else if (fp_fg_sew != rvv_pkg::EW32 || fp_next_sew != rvv_pkg::EW32 ||
                 fp_fg_sew != fp_next_sew)
          red_stream_reject_sew[l][RedStreamFp] = 1'b1;
`ifndef ARA_RED_HETERO_STREAM_4LANE
        else if (fp_fg_rm != fp_next_rm)
          red_stream_reject_rounding[l][RedStreamFp] = 1'b1;
`endif
        else
          red_stream_eligible[l][RedStreamFp] = 1'b1;
      end

      red_stream_start[l][RedStreamValu] =
        !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_active_q &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_active_d;
      red_stream_start[l][RedStreamFp] =
        !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_active_q &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_active_d;
      red_stream_active[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_active_q;
      red_stream_active[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_active_q;
      red_stream_background_issue[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_issue_cycles_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_issue_cycles_q;
      red_stream_background_issue[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_issue_cycles_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_issue_cycles_q;
      red_stream_primary_conflict[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_primary_conflict_cycles_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_primary_conflict_cycles_q;
      red_stream_primary_conflict[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_primary_conflict_cycles_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_primary_conflict_cycles_q;
      red_stream_complete[l][RedStreamValu] =
        !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_complete_q &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_complete_d;
      red_stream_complete[l][RedStreamFp] =
        !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_complete_q &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_complete_d;
      red_stream_complete_wait[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_complete_q;
      red_stream_complete_wait[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_complete_q;
      red_stream_full_promotion[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_retire_foreground &&
        ((ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_root_count_q != '0) ||
         ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_complete_q);
      red_stream_partial_promotion[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_retire_foreground &&
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_root_count_q == '0) &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_bg_active_q;
      red_stream_full_promotion[l][RedStreamFp] =
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          mfpu_state_q == 3'd7) &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_foreground_advanced_q &&
        ((ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_root_count_q != '0) ||
         ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_complete_q);
      red_stream_partial_promotion[l][RedStreamFp] =
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          mfpu_state_q == 3'd7) &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_foreground_advanced_q &&
        (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_root_count_q == '0) &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_bg_active_q;

      red_stream_root_occupancy[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_root_count_q;
      red_stream_root_occupancy[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_root_count_q;
      red_stream_root_nonempty[l][RedStreamValu] =
        red_stream_root_occupancy[l][RedStreamValu] != '0;
      red_stream_root_nonempty[l][RedStreamFp] =
        red_stream_root_occupancy[l][RedStreamFp] != '0;
      red_stream_root_full[l][RedStreamValu] =
        red_stream_root_occupancy[l][RedStreamValu] == ValuInsnQueueDepth-1;
      red_stream_root_full[l][RedStreamFp] =
        red_stream_root_occupancy[l][RedStreamFp] == MfpuInsnQueueDepth-1;
      red_stream_root_push[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_root_write_pnt_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_root_write_pnt_q;
      red_stream_root_push[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_root_write_pnt_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_root_write_pnt_q;
      red_stream_root_pop[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_root_read_pnt_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_root_read_pnt_q;
      red_stream_root_pop[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_root_read_pnt_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_root_read_pnt_q;
`ifdef ARA_RED_SLACK_SCHED_4LANE
      red_stream_slack_defer[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_slack_defer_cycles_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_slack_defer_cycles_q;
      red_stream_slack_defer[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_slack_defer_cycles_d !=
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_slack_defer_cycles_q;
      red_stream_slack_score[l][RedStreamValu] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
          red_stream_slack_score_q;
      red_stream_slack_score[l][RedStreamFp] =
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
          red_stream_slack_score_q;
`endif
`endif
    end

    assign lane_exec_event[l].issue_progress =
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.vinsn_issue_q.op) &
       {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.valu_valid}}) |
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op) &
       {NrExecClasses{(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vmul_in_valid &&
                       ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vmul_in_ready) ||
                      (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vdiv_in_valid &&
                       ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vdiv_in_ready) ||
                      (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vfpu_in_valid &&
                       ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vfpu_in_ready)}}) |
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_processing_q.op) &
       {NrExecClasses{(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.unit_out_valid &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.result_queue_full)}});

    assign lane_exec_event[l].operand_wait =
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.vinsn_issue_q.op) &
       {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.vinsn_issue_valid &&
                      (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.alu_state_q inside
                        {3'd0, 3'd1}) &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.valu_valid &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.result_queue_full}}) |
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op) &
       {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_issue_q_valid &&
                      (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.mfpu_state_q inside
                        {3'd0, 3'd1, 3'd6}) &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.operands_valid &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.latency_stall}});

    assign lane_exec_event[l].unit_input_backpressure =
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op) &
       {NrExecClasses{(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vmul_in_valid &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vmul_in_ready) ||
                      (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vdiv_in_valid &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vdiv_in_ready) ||
                      (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vfpu_in_valid &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vfpu_in_ready)}});

    assign lane_exec_event[l].latency_order_stall =
      classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op) &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.latency_stall}};

    assign lane_exec_event[l].result_queue_full =
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.vinsn_issue_q.op) &
       {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.vinsn_issue_valid &&
                      ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.result_queue_full}}) |
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_processing_q.op) &
       {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.unit_out_valid &&
                      ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.result_queue_full}});

    assign lane_exec_event[l].result_backpressure =
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.vinsn_commit.op) &
       {NrExecClasses{(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.alu_result_req_o &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.alu_result_gnt_i) ||
                      (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.mask_operand_valid &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.mask_operand_ready)}}) |
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_commit.op) &
       {NrExecClasses{(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.mfpu_result_req_o &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.mfpu_result_gnt_i) ||
                      (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.result_queue_valid_q[
                         ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.result_queue_read_pnt_q] &&
                       ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.result_queue_q[
                         ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.result_queue_read_pnt_q].mask &&
                      !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.mask_operand_ready)}});

    assign lane_exec_event[l].long_latency_busy =
      classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_processing_q.op) &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_processing_q_valid}};

    assign lane_exec_event[l].reduction =
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.vinsn_issue_q.op) &
       {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.alu_state_q != '0}}) |
      (classify_exec_op(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op) &
       {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.mfpu_state_q != '0}});

    assign lane_exec_event[l].cross_lane = '0;
    assign lane_exec_event[l].special_path = '0;
    assign lane_exec_event[l].index_fifo_full = '0;

    always_comb begin : p_deep_lane_events
      automatic logic [NrMfpuSubunits-1:0] mfpu_input_valid;
      automatic logic [NrMfpuSubunits-1:0] mfpu_input_ready;
      automatic ara_op_e processing_op;
      exec_lane_mfpu_input_fire[l] = '0;
      exec_lane_mfpu_input_backpressure[l] = '0;
      exec_lane_mfpu_output_fire[l] = '0;
      exec_lane_mfpu_processing[l] = '0;
      exec_lane_valu_state[l] = '0;
      exec_lane_mfpu_state[l] = '0;

      mfpu_input_valid = {
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vfpu_in_valid,
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vdiv_in_valid,
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vmul_in_valid
      };
      mfpu_input_ready = {
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vfpu_in_ready,
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vdiv_in_ready,
        ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vmul_in_ready
      };
      exec_lane_mfpu_input_fire[l] = mfpu_input_valid & mfpu_input_ready;
      exec_lane_mfpu_input_backpressure[l] = mfpu_input_valid & ~mfpu_input_ready;

      processing_op = ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_processing_q.op;
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_processing_q_valid) begin
        if (processing_op inside {[VMUL:VSMUL]})
          exec_lane_mfpu_processing[l][0] = 1'b1;
        else if (processing_op inside {[VDIVU:VREM]})
          exec_lane_mfpu_processing[l][1] = 1'b1;
        else
          exec_lane_mfpu_processing[l][2] = 1'b1;
      end
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.unit_out_valid &&
          !ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.result_queue_full)
        exec_lane_mfpu_output_fire[l] = exec_lane_mfpu_processing[l];

      if (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.vinsn_issue_valid)
        exec_lane_valu_state[l][unsigned'(
          ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.alu_state_q)] = 1'b1;
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_issue_q_valid ||
          ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.vinsn_processing_q_valid)
        exec_lane_mfpu_state[l][unsigned'(
          ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.mfpu_state_q)] = 1'b1;
    end

    // Split a missing operand into true bank arbitration loss, dependency
    // hazard, and a full downstream operand queue.  The older standalone VRF
    // monitor only provided cumulative bank totals and could not attribute
    // them to the instruction class in the selected ROI.
    always_comb begin : p_vrf_supply_events
      exec_lane_vrf_read_request[l] = '0;
      exec_lane_vrf_read_grant[l] = '0;
      exec_lane_vrf_bank_conflict[l] = '0;
      exec_lane_vrf_hazard_stall[l] = '0;
      exec_lane_operand_queue_backpressure[l] = '0;
      for (int unsigned r = 0; r < NrOperandQueues; r++) begin
        automatic logic requesting =
          ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_operand_requester.state_q[r] == 1'b1;
        automatic logic bank_request =
          |ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_operand_requester.lane_operand_req_transposed[r];
        automatic logic bank_grant =
          |ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_operand_requester.operand_requester_gnt[r];
        automatic logic hazard_stall =
          ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_operand_requester.stall[r];
        automatic logic queue_ready =
          ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_operand_requester.operand_queue_ready_i[r];
        automatic vid_t id =
          ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_operand_requester.requester_metadata_q[r].id;
        for (int unsigned c = 0; c < NrExecClasses; c++) begin
          exec_lane_vrf_read_request[l][c] += exec_class_by_id_q[id][c] && bank_request;
          exec_lane_vrf_read_grant[l][c] += exec_class_by_id_q[id][c] && bank_grant;
          exec_lane_vrf_bank_conflict[l][c] +=
            exec_class_by_id_q[id][c] && bank_request && !bank_grant;
          exec_lane_vrf_hazard_stall[l][c] +=
            exec_class_by_id_q[id][c] && requesting && queue_ready && hazard_stall;
          exec_lane_operand_queue_backpressure[l][c] +=
            exec_class_by_id_q[id][c] && requesting && !queue_ready;
        end
      end
    end

    // A generated observer is required here because the lane hierarchy is a
    // generate array; using a procedural lane index in an XMR is not portable.
    always_comb begin : p_lane_result_queue_occupancy
      exec_lane_result_queue_occupancy[l] = '0;
      for (int unsigned slot = 0; slot < 2; slot++) begin
        if (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
              result_queue_valid_q[slot]) begin
          for (int unsigned c = 0; c < NrExecClasses; c++)
            exec_lane_result_queue_occupancy[l][c] += exec_class_by_id_q[
              ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_valu.
                result_queue_q[slot].id][c];
        end
        if (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
              result_queue_valid_q[slot]) begin
          for (int unsigned c = 0; c < NrExecClasses; c++)
            exec_lane_result_queue_occupancy[l][c] += exec_class_by_id_q[
              ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[l].i_lane.i_vfus.i_vmfpu.
                result_queue_q[slot].id][c];
        end
      end
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin : p_red_stream_perf_counters
    if (!rst_n) begin
      red_stream_perf_counters <= '{default: '0};
    end else begin
      for (int unsigned c = 0; c < NrRedStreamClasses; c++) begin
        automatic logic [63:0] window_inc = '0;
        automatic logic [63:0] no_candidate_inc = '0;
        automatic logic [63:0] candidate_inc = '0;
        automatic logic [63:0] eligible_inc = '0;
        automatic logic [63:0] reject_unsupported_inc = '0;
        automatic logic [63:0] reject_mask_inc = '0;
        automatic logic [63:0] reject_short_vl_inc = '0;
        automatic logic [63:0] reject_opcode_inc = '0;
        automatic logic [63:0] reject_sew_inc = '0;
        automatic logic [63:0] reject_rounding_inc = '0;
        automatic logic [63:0] start_inc = '0;
        automatic logic [63:0] active_inc = '0;
        automatic logic [63:0] background_issue_inc = '0;
        automatic logic [63:0] primary_conflict_inc = '0;
        automatic logic [63:0] complete_inc = '0;
        automatic logic [63:0] complete_wait_inc = '0;
        automatic logic [63:0] full_promotion_inc = '0;
        automatic logic [63:0] partial_promotion_inc = '0;
        automatic logic [63:0] root_nonempty_inc = '0;
        automatic logic [63:0] root_full_inc = '0;
        automatic logic [63:0] root_occupancy_inc = '0;
        automatic logic [63:0] root_push_inc = '0;
        automatic logic [63:0] root_pop_inc = '0;
        automatic logic [63:0] slack_defer_inc = '0;
        automatic logic [63:0] slack_score_inc = '0;
        for (int unsigned l = 0; l < NrLanes; l++) begin
          window_inc += red_stream_window[l][c];
          no_candidate_inc += red_stream_no_candidate[l][c];
          candidate_inc += red_stream_candidate[l][c];
          eligible_inc += red_stream_eligible[l][c];
          reject_unsupported_inc += red_stream_reject_unsupported[l][c];
          reject_mask_inc += red_stream_reject_mask[l][c];
          reject_short_vl_inc += red_stream_reject_short_vl[l][c];
          reject_opcode_inc += red_stream_reject_opcode[l][c];
          reject_sew_inc += red_stream_reject_sew[l][c];
          reject_rounding_inc += red_stream_reject_rounding[l][c];
          start_inc += red_stream_start[l][c];
          active_inc += red_stream_active[l][c];
          background_issue_inc += red_stream_background_issue[l][c];
          primary_conflict_inc += red_stream_primary_conflict[l][c];
          complete_inc += red_stream_complete[l][c];
          complete_wait_inc += red_stream_complete_wait[l][c];
          full_promotion_inc += red_stream_full_promotion[l][c];
          partial_promotion_inc += red_stream_partial_promotion[l][c];
          root_nonempty_inc += red_stream_root_nonempty[l][c];
          root_full_inc += red_stream_root_full[l][c];
          root_occupancy_inc += red_stream_root_occupancy[l][c];
          root_push_inc += red_stream_root_push[l][c];
          root_pop_inc += red_stream_root_pop[l][c];
          slack_defer_inc += red_stream_slack_defer[l][c];
          slack_score_inc += red_stream_slack_score[l][c];
        end
        red_stream_perf_counters.window_lane_sample[c] <=
          red_stream_perf_counters.window_lane_sample[c] + window_inc;
        red_stream_perf_counters.no_candidate_lane_sample[c] <=
          red_stream_perf_counters.no_candidate_lane_sample[c] + no_candidate_inc;
        red_stream_perf_counters.candidate_lane_sample[c] <=
          red_stream_perf_counters.candidate_lane_sample[c] + candidate_inc;
        red_stream_perf_counters.eligible_lane_sample[c] <=
          red_stream_perf_counters.eligible_lane_sample[c] + eligible_inc;
        red_stream_perf_counters.reject_unsupported_lane_sample[c] <=
          red_stream_perf_counters.reject_unsupported_lane_sample[c] +
          reject_unsupported_inc;
        red_stream_perf_counters.reject_mask_lane_sample[c] <=
          red_stream_perf_counters.reject_mask_lane_sample[c] + reject_mask_inc;
        red_stream_perf_counters.reject_short_vl_lane_sample[c] <=
          red_stream_perf_counters.reject_short_vl_lane_sample[c] +
          reject_short_vl_inc;
        red_stream_perf_counters.reject_opcode_lane_sample[c] <=
          red_stream_perf_counters.reject_opcode_lane_sample[c] + reject_opcode_inc;
        red_stream_perf_counters.reject_sew_lane_sample[c] <=
          red_stream_perf_counters.reject_sew_lane_sample[c] + reject_sew_inc;
        red_stream_perf_counters.reject_rounding_lane_sample[c] <=
          red_stream_perf_counters.reject_rounding_lane_sample[c] +
          reject_rounding_inc;
        red_stream_perf_counters.start_lane_sample[c] <=
          red_stream_perf_counters.start_lane_sample[c] + start_inc;
        red_stream_perf_counters.active_lane_sample[c] <=
          red_stream_perf_counters.active_lane_sample[c] + active_inc;
        red_stream_perf_counters.background_issue_lane_sample[c] <=
          red_stream_perf_counters.background_issue_lane_sample[c] +
          background_issue_inc;
        red_stream_perf_counters.primary_conflict_lane_sample[c] <=
          red_stream_perf_counters.primary_conflict_lane_sample[c] +
          primary_conflict_inc;
        red_stream_perf_counters.complete_lane_sample[c] <=
          red_stream_perf_counters.complete_lane_sample[c] + complete_inc;
        red_stream_perf_counters.complete_wait_lane_sample[c] <=
          red_stream_perf_counters.complete_wait_lane_sample[c] + complete_wait_inc;
        red_stream_perf_counters.full_promotion_lane_sample[c] <=
          red_stream_perf_counters.full_promotion_lane_sample[c] +
          full_promotion_inc;
        red_stream_perf_counters.partial_promotion_lane_sample[c] <=
          red_stream_perf_counters.partial_promotion_lane_sample[c] +
          partial_promotion_inc;
        red_stream_perf_counters.root_nonempty_lane_sample[c] <=
          red_stream_perf_counters.root_nonempty_lane_sample[c] +
          root_nonempty_inc;
        red_stream_perf_counters.root_full_lane_sample[c] <=
          red_stream_perf_counters.root_full_lane_sample[c] + root_full_inc;
        red_stream_perf_counters.root_occupancy_lane_sum[c] <=
          red_stream_perf_counters.root_occupancy_lane_sum[c] +
          root_occupancy_inc;
        red_stream_perf_counters.root_push_lane_sample[c] <=
          red_stream_perf_counters.root_push_lane_sample[c] + root_push_inc;
        red_stream_perf_counters.root_pop_lane_sample[c] <=
          red_stream_perf_counters.root_pop_lane_sample[c] + root_pop_inc;
        red_stream_perf_counters.slack_defer_lane_sample[c] <=
          red_stream_perf_counters.slack_defer_lane_sample[c] + slack_defer_inc;
        red_stream_perf_counters.slack_score_lane_sum[c] <=
          red_stream_perf_counters.slack_score_lane_sum[c] + slack_score_inc;
      end
    end
  end

  always_comb begin : p_exec_perf_events
    automatic exec_class_mask_t dispatch_class;
    automatic exec_class_mask_t pe_req_class;
    automatic exec_class_mask_t sldu_issue_class;
    automatic exec_class_mask_t sldu_commit_class;
    automatic exec_class_mask_t mask_issue_class;
    automatic exec_class_mask_t mask_commit_class;
    automatic logic sldu_progress;
    automatic logic mask_progress;

    accepted_exec_class = classify_exec_op(
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op
    );
    // The dispatcher emits internal VSLIDEDOWN requests while leaving the
    // RESHUFFLE state.  state_qq is therefore needed for the cycle in which
    // the registered request first reaches the sequencer.
    if ((ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q == 2'd3) ||
        (ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_qq == 2'd3)) begin
      accepted_exec_class = '0;
      accepted_exec_class[ExecReshuffle] = 1'b1;
    end
    if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q[
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_o.id])
      pe_req_class = exec_class_by_id_q[
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_o.id];
    else if (exec_pending_accept_valid_q)
      pe_req_class = exec_pending_class_q;
    else if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn)
      pe_req_class = accepted_exec_class;
    else
      pe_req_class = classify_exec_op(
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_o.op
      );
    dispatch_class = accepted_exec_class;

    exec_first_issue =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_d &&
      !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q[
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_d.id] &&
      (exec_pending_accept_valid_q ||
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn);
    first_issue_class = exec_pending_accept_valid_q
      ? exec_pending_class_q
      : accepted_exec_class;
    first_issue_op = exec_pending_accept_valid_q
      ? exec_pending_op_q
      : ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op;
    exec_dispatch_wait = exec_pending_accept_valid_q
                       ? wall_cycle - exec_pending_accept_cycle_q
                       : '0;
    if (exec_dispatch_wait == 0)       exec_dispatch_wait_bin = 0;
    else if (exec_dispatch_wait <= 4)  exec_dispatch_wait_bin = 1;
    else if (exec_dispatch_wait <= 16) exec_dispatch_wait_bin = 2;
    else                               exec_dispatch_wait_bin = 3;

    exec_class_active = '0;
    exec_masked_class_active = '0;
    exec_completion_class = '0;
    exec_inflight_count = '0;
    exec_completion_count = '0;
    exec_completion_latency = '0;
    exec_completion_end_to_end_latency = '0;
    exec_completion_latency_hist = '0;
    exec_opcode_completion_count = '0;
    exec_opcode_completion_latency = '0;
    exec_opcode_completion_latency_hist = '0;
    exec_opcode_shape_completion_count = '0;
    exec_opcode_shape_completion_latency = '0;
    exec_scalar_move_complete = exec_scalar_move_pending_q &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_scalar_resp_valid_i &&
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_scalar_resp_ready_o;
    for (int unsigned id = 0; id < NrVInsn; id++) begin
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q[id]) begin
        exec_class_active |= exec_class_by_id_q[id];
        if (exec_masked_by_id_q[id])
          exec_masked_class_active |= exec_class_by_id_q[id];
        for (int unsigned c = 0; c < NrExecClasses; c++)
          exec_inflight_count[c] += exec_class_by_id_q[id][c];
      end

      if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q[id] &&
          !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_d[id]) begin
        automatic logic [63:0] latency = wall_cycle - exec_issue_cycle_by_id_q[id] + 1;
        automatic int unsigned op = unsigned'(exec_op_by_id_q[id]);
        exec_completion_class |= exec_class_by_id_q[id];
        exec_opcode_completion_count[op] += 1;
        exec_opcode_completion_latency[op] += latency;
        exec_opcode_shape_completion_count[op][exec_sew_by_id_q[id]][exec_lmul_by_id_q[id]] += 1;
        exec_opcode_shape_completion_latency[op][exec_sew_by_id_q[id]][exec_lmul_by_id_q[id]] += latency;
        if (latency <= 8)        exec_opcode_completion_latency_hist[op][0] += 1;
        else if (latency <= 32)  exec_opcode_completion_latency_hist[op][1] += 1;
        else if (latency <= 128) exec_opcode_completion_latency_hist[op][2] += 1;
        else                     exec_opcode_completion_latency_hist[op][3] += 1;
        for (int unsigned c = 0; c < NrExecClasses; c++) begin
          if (exec_class_by_id_q[id][c]) begin
            exec_completion_count[c] += 1;
            exec_completion_latency[c] += latency;
            exec_completion_end_to_end_latency[c] += latency + exec_dispatch_wait_by_id_q[id];
            if (latency <= 8)        exec_completion_latency_hist[c][0] += 1;
            else if (latency <= 32)  exec_completion_latency_hist[c][1] += 1;
            else if (latency <= 128) exec_completion_latency_hist[c][2] += 1;
            else                     exec_completion_latency_hist[c][3] += 1;
          end
        end
      end
    end

    // VFU_None scalar moves never set vinsn_running_q.  Track their WAIT-state
    // lifetime explicitly so they obey the same issued/completed/latency
    // definitions as every other class.
    if (exec_scalar_move_pending_q) begin
      exec_class_active |= exec_scalar_move_class_q;
      for (int unsigned c = 0; c < NrExecClasses; c++)
        exec_inflight_count[c] += exec_scalar_move_class_q[c];
    end
    if (exec_scalar_move_complete) begin
      automatic logic [63:0] latency = wall_cycle - exec_scalar_move_issue_cycle_q + 1;
      automatic int unsigned op = unsigned'(exec_scalar_move_op_q);
      exec_completion_class |= exec_scalar_move_class_q;
      exec_opcode_completion_count[op] += 1;
      exec_opcode_completion_latency[op] += latency;
      exec_opcode_shape_completion_count[op][exec_scalar_move_sew_q][exec_scalar_move_lmul_q] += 1;
      exec_opcode_shape_completion_latency[op][exec_scalar_move_sew_q][exec_scalar_move_lmul_q] += latency;
      if (latency <= 8)        exec_opcode_completion_latency_hist[op][0] += 1;
      else if (latency <= 32)  exec_opcode_completion_latency_hist[op][1] += 1;
      else if (latency <= 128) exec_opcode_completion_latency_hist[op][2] += 1;
      else                     exec_opcode_completion_latency_hist[op][3] += 1;
      for (int unsigned c = 0; c < NrExecClasses; c++) begin
        if (exec_scalar_move_class_q[c]) begin
          exec_completion_count[c] += 1;
          exec_completion_latency[c] += latency;
          exec_completion_end_to_end_latency[c] +=
            latency + exec_scalar_move_dispatch_wait_q;
          if (latency <= 8)        exec_completion_latency_hist[c][0] += 1;
          else if (latency <= 32)  exec_completion_latency_hist[c][1] += 1;
          else if (latency <= 128) exec_completion_latency_hist[c][2] += 1;
          else                     exec_completion_latency_hist[c][3] += 1;
        end
      end
    end

    exec_dispatch_request = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i}};
    exec_dispatch_blocked = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_ready_o}};
    exec_fu_queue_full = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_ready_o &&
                     |(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.target_vfus_vec &
                       ~ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_queue_issue)}};
    exec_mask_queue_full = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_ready_o &&
                     ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.target_vfus_vec[VFU_MaskUnit] &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_queue_issue[VFU_MaskUnit]}};
    exec_slide_queue_full = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_ready_o &&
                     ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.target_vfus_vec[VFU_SlideUnit] &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_queue_issue[VFU_SlideUnit]}};
    exec_id_pool_full = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_ready_o &&
                     ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_full}};
    exec_response_wait = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_ready_o &&
                     ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.state_q != '0}};
    exec_operand_request_blocked = pe_req_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_o &&
                     !(&ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.operand_requester_ready)}};
    exec_opcode_dispatch_request = '0;
    exec_opcode_dispatch_blocked = '0;
    exec_opcode_fu_queue_full = '0;
    exec_opcode_mask_queue_full = '0;
    exec_opcode_slide_queue_full = '0;
    exec_opcode_id_pool_full = '0;
    exec_opcode_response_wait = '0;
    exec_opcode_other_dispatch_blocked = '0;
    exec_opcode_primary_fu_queue_full = '0;
    exec_opcode_primary_mask_queue_full = '0;
    exec_opcode_primary_slide_queue_full = '0;
    exec_opcode_primary_id_pool_full = '0;
    exec_opcode_primary_response_wait = '0;
    exec_opcode_primary_lane_desync = '0;
    exec_opcode_primary_sequencer_block = '0;
    exec_opcode_primary_operand_request_blocked = '0;
    exec_opcode_primary_other_dispatch_blocked = '0;
    exec_opcode_primary_dispatch_unattributed = '0;
    if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i) begin
      automatic int unsigned req_op =
        unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op);
      automatic logic req_not_ready =
        !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_ready_o;
      automatic logic req_fu_queue_full =
        req_not_ready &&
        |(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.target_vfus_vec &
          ~ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_queue_issue);
      automatic logic req_mask_queue_full =
        req_not_ready &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.target_vfus_vec[VFU_MaskUnit] &&
        !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_queue_issue[VFU_MaskUnit];
      automatic logic req_slide_queue_full =
        req_not_ready &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.target_vfus_vec[VFU_SlideUnit] &&
        !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_queue_issue[VFU_SlideUnit];
      automatic logic req_id_pool_full =
        req_not_ready &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_full;
      automatic logic req_response_wait =
        req_not_ready &&
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.state_q != '0;
      automatic logic req_other_blocked =
        req_not_ready &&
        !req_fu_queue_full &&
        !req_mask_queue_full &&
        !req_slide_queue_full &&
        !req_id_pool_full &&
        !req_response_wait &&
        !(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.stall_lanes_desynch) &&
        !(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_o &&
          !(&ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.operand_requester_ready)) &&
        !(exec_sequencer_block != '0);
      exec_opcode_dispatch_request[req_op] = 1'b1;
      exec_opcode_dispatch_blocked[req_op] = req_not_ready;
      exec_opcode_fu_queue_full[req_op] = req_fu_queue_full;
      exec_opcode_mask_queue_full[req_op] = req_mask_queue_full;
      exec_opcode_slide_queue_full[req_op] = req_slide_queue_full;
      exec_opcode_id_pool_full[req_op] = req_id_pool_full;
      exec_opcode_response_wait[req_op] = req_response_wait;
      exec_opcode_other_dispatch_blocked[req_op] = req_other_blocked;
      if (req_not_ready) begin
        automatic logic req_lane_desync =
          |(exec_lane_desync & dispatch_class);
        automatic logic req_sequencer_block =
          |(exec_sequencer_block & dispatch_class);
        automatic logic req_other_dispatch_blocked = req_other_blocked;
        automatic logic req_operand_request_blocked =
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_o &&
          !(&ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.operand_requester_ready);

        if (req_fu_queue_full)
          exec_opcode_primary_fu_queue_full[req_op] = 1'b1;
        else if (req_mask_queue_full)
          exec_opcode_primary_mask_queue_full[req_op] = 1'b1;
        else if (req_slide_queue_full)
          exec_opcode_primary_slide_queue_full[req_op] = 1'b1;
        else if (req_id_pool_full)
          exec_opcode_primary_id_pool_full[req_op] = 1'b1;
        else if (req_response_wait)
          exec_opcode_primary_response_wait[req_op] = 1'b1;
        else if (req_lane_desync)
          exec_opcode_primary_lane_desync[req_op] = 1'b1;
        else if (req_sequencer_block)
          exec_opcode_primary_sequencer_block[req_op] = 1'b1;
        else if (req_operand_request_blocked)
          exec_opcode_primary_operand_request_blocked[req_op] = 1'b1;
        else if (req_other_dispatch_blocked)
          exec_opcode_primary_other_dispatch_blocked[req_op] = 1'b1;
        else
          exec_opcode_primary_dispatch_unattributed[req_op] = 1'b1;
      end
    end
    exec_opcode_operand_request_blocked = '0;
    if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_o) begin
      automatic int unsigned req_op =
        unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_o.op);
      exec_opcode_operand_request_blocked[req_op] = !(
        &ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.operand_requester_ready);
    end
    exec_lane_desync =
      (pe_req_class &
        {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_o &&
                       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.stall_lanes_desynch}}) |
      (dispatch_class &
        {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_valid_i &&
                       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.stall_lanes_desynch}});

    exec_raw_hazard = '0;
    exec_war_hazard = '0;
    exec_waw_hazard = '0;
    exec_false_hazard = '0;
    exec_sequencer_block = '0;
`ifdef FOR_VERIFY
    exec_raw_hazard = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.raw_hazard}};
    exec_war_hazard = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.war_hazard}};
    exec_waw_hazard = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.waw_hazard}};
    exec_false_hazard = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.false_hazard}};
    exec_sequencer_block = dispatch_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.sequencer_block}};
`endif

    // Count only dispatch-blocked cycles for which none of the observed
    // structural causes is present. This residual is intentionally exclusive;
    // the individual observed causes above may overlap with one another.
    exec_other_dispatch_blocked = exec_dispatch_blocked &
      ~(exec_fu_queue_full | exec_id_pool_full | exec_response_wait |
        exec_sequencer_block |
        (dispatch_class &
          {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.stall_lanes_desynch}}) |
        (dispatch_class &
          {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_valid_o &&
                         !(&ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.operand_requester_ready)}}));

    exec_primary_fu_queue_full = '0;
    exec_primary_mask_queue_full = '0;
    exec_primary_slide_queue_full = '0;
    exec_primary_id_pool_full = '0;
    exec_primary_response_wait = '0;
    exec_primary_lane_desync = '0;
    exec_primary_sequencer_block = '0;
    exec_primary_operand_request_blocked = '0;
    exec_primary_other_dispatch_blocked = '0;
    exec_primary_dispatch_unattributed = '0;
    for (int unsigned c = 0; c < NrExecClasses; c++) begin
      if (exec_dispatch_blocked[c]) begin
        if (exec_fu_queue_full[c])
          exec_primary_fu_queue_full[c] = 1'b1;
        else if (exec_mask_queue_full[c])
          exec_primary_mask_queue_full[c] = 1'b1;
        else if (exec_slide_queue_full[c])
          exec_primary_slide_queue_full[c] = 1'b1;
        else if (exec_id_pool_full[c])
          exec_primary_id_pool_full[c] = 1'b1;
        else if (exec_response_wait[c])
          exec_primary_response_wait[c] = 1'b1;
        else if (exec_lane_desync[c])
          exec_primary_lane_desync[c] = 1'b1;
        else if (exec_sequencer_block[c])
          exec_primary_sequencer_block[c] = 1'b1;
        else if (exec_operand_request_blocked[c])
          exec_primary_operand_request_blocked[c] = 1'b1;
        else if (exec_other_dispatch_blocked[c])
          exec_primary_other_dispatch_blocked[c] = 1'b1;
        else
          exec_primary_dispatch_unattributed[c] = 1'b1;
      end
    end

    // Project execution-side primary attribution back to concrete opcodes.
    // This enables opcode-level execution top-N bottleneck decomposition and
    // keeps the same deterministic priority as class-side primary attribution.
    exec_opcode_active_cycle = '0;
    exec_opcode_primary_result_backpressure = '0;
    exec_opcode_primary_result_queue_full = '0;
    exec_opcode_primary_latency_order_stall = '0;
    exec_opcode_primary_unit_input_backpressure = '0;
    exec_opcode_primary_operand_wait = '0;
    exec_opcode_primary_long_latency_busy = '0;
    exec_opcode_primary_special_path = '0;
    exec_opcode_primary_progress = '0;
    exec_opcode_primary_unattributed = '0;
    for (int unsigned id = 0; id < NrVInsn; id++) begin
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q[id] &&
          (exec_class_by_id_q[id][ExecValu] || exec_class_by_id_q[id][ExecMul] ||
          exec_class_by_id_q[id][ExecDiv] || exec_class_by_id_q[id][ExecFp] ||
          exec_class_by_id_q[id][ExecSlide] || exec_class_by_id_q[id][ExecMask] ||
          exec_class_by_id_q[id][ExecLoad] || exec_class_by_id_q[id][ExecStore] ||
          exec_class_by_id_q[id][ExecMoveToVec] || exec_class_by_id_q[id][ExecMoveFromVec] ||
          exec_class_by_id_q[id][ExecReshuffle])) begin
        automatic int unsigned op = unsigned'(exec_op_by_id_q[id]);
        exec_opcode_active_cycle[op] = 1'b1;
        for (int unsigned c = 0; c < NrExecClasses; c++) begin
          if (exec_primary_result_backpressure[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_result_backpressure[op] = 1'b1;
          if (exec_primary_result_queue_full[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_result_queue_full[op] = 1'b1;
          if (exec_primary_latency_order_stall[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_latency_order_stall[op] = 1'b1;
          if (exec_primary_unit_input_backpressure[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_unit_input_backpressure[op] = 1'b1;
          if (exec_primary_operand_wait[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_operand_wait[op] = 1'b1;
          if (exec_primary_long_latency_busy[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_long_latency_busy[op] = 1'b1;
          if (exec_primary_special_path[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_special_path[op] = 1'b1;
          if (exec_primary_progress[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_progress[op] = 1'b1;
          if (exec_primary_unattributed[c] && exec_class_by_id_q[id][c])
            exec_opcode_primary_unattributed[op] = 1'b1;
        end
      end
    end
    if (exec_scalar_move_pending_q) begin
      automatic int unsigned op = unsigned'(exec_scalar_move_op_q);
      exec_opcode_active_cycle[op] = 1'b1;
      for (int unsigned c = 0; c < NrExecClasses; c++) begin
        if (exec_primary_result_backpressure[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_result_backpressure[op] = 1'b1;
        if (exec_primary_result_queue_full[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_result_queue_full[op] = 1'b1;
        if (exec_primary_latency_order_stall[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_latency_order_stall[op] = 1'b1;
        if (exec_primary_unit_input_backpressure[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_unit_input_backpressure[op] = 1'b1;
        if (exec_primary_operand_wait[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_operand_wait[op] = 1'b1;
        if (exec_primary_long_latency_busy[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_long_latency_busy[op] = 1'b1;
        if (exec_primary_special_path[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_special_path[op] = 1'b1;
        if (exec_primary_progress[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_progress[op] = 1'b1;
        if (exec_primary_unattributed[c] && exec_scalar_move_class_q[c])
          exec_opcode_primary_unattributed[op] = 1'b1;
      end
    end

    exec_event = '0;
    exec_issue_progress_lane_sample = '0;
    exec_operand_wait_lane_sample = '0;
    exec_unit_input_backpressure_lane_sample = '0;
    exec_latency_order_stall_lane_sample = '0;
    exec_result_queue_full_lane_sample = '0;
    exec_result_backpressure_lane_sample = '0;
    exec_long_latency_busy_lane_sample = '0;
    exec_result_queue_occupancy_lane_samples = '0;
    exec_vrf_read_request_lane_sample = '0;
    exec_vrf_read_grant_lane_sample = '0;
    exec_vrf_bank_conflict_lane_sample = '0;
    exec_vrf_hazard_stall_lane_sample = '0;
    exec_operand_queue_backpressure_lane_sample = '0;
    exec_mfpu_input_fire_lane_sample = '0;
    exec_mfpu_input_backpressure_lane_sample = '0;
    exec_mfpu_output_fire_lane_sample = '0;
    exec_mfpu_processing_lane_sample = '0;
    exec_valu_state_lane_sample = '0;
    exec_mfpu_state_lane_sample = '0;
    for (int unsigned lane = 0; lane < NrLanes; lane++) begin
      exec_event |= lane_exec_event[lane];
      for (int unsigned c = 0; c < NrExecClasses; c++) begin
        exec_issue_progress_lane_sample[c] += lane_exec_event[lane].issue_progress[c];
        exec_operand_wait_lane_sample[c] += lane_exec_event[lane].operand_wait[c];
        exec_unit_input_backpressure_lane_sample[c] +=
          lane_exec_event[lane].unit_input_backpressure[c];
        exec_latency_order_stall_lane_sample[c] += lane_exec_event[lane].latency_order_stall[c];
        exec_result_queue_full_lane_sample[c] += lane_exec_event[lane].result_queue_full[c];
        exec_result_backpressure_lane_sample[c] += lane_exec_event[lane].result_backpressure[c];
        exec_long_latency_busy_lane_sample[c] += lane_exec_event[lane].long_latency_busy[c];
        exec_result_queue_occupancy_lane_samples[c] +=
          exec_lane_result_queue_occupancy[lane][c];
        exec_vrf_read_request_lane_sample[c] += exec_lane_vrf_read_request[lane][c];
        exec_vrf_read_grant_lane_sample[c] += exec_lane_vrf_read_grant[lane][c];
        exec_vrf_bank_conflict_lane_sample[c] += exec_lane_vrf_bank_conflict[lane][c];
        exec_vrf_hazard_stall_lane_sample[c] += exec_lane_vrf_hazard_stall[lane][c];
        exec_operand_queue_backpressure_lane_sample[c] +=
          exec_lane_operand_queue_backpressure[lane][c];
      end
      for (int unsigned u = 0; u < NrMfpuSubunits; u++) begin
        exec_mfpu_input_fire_lane_sample[u] += exec_lane_mfpu_input_fire[lane][u];
        exec_mfpu_input_backpressure_lane_sample[u] +=
          exec_lane_mfpu_input_backpressure[lane][u];
        exec_mfpu_output_fire_lane_sample[u] += exec_lane_mfpu_output_fire[lane][u];
        exec_mfpu_processing_lane_sample[u] += exec_lane_mfpu_processing[lane][u];
      end
      for (int unsigned s = 0; s < NrValuStates; s++)
        exec_valu_state_lane_sample[s] += exec_lane_valu_state[lane][s];
      for (int unsigned s = 0; s < NrMfpuStates; s++)
        exec_mfpu_state_lane_sample[s] += exec_lane_mfpu_state[lane][s];
    end

    // SLDU, MASKU, and VLDU have one two-entry result queue per lane in a
    // central unit.  Sampling both dimensions exposes queue pressure even
    // before the queue reaches its binary full flag.
    for (int unsigned slot = 0; slot < 2; slot++) begin
      for (int unsigned lane = 0; lane < NrLanes; lane++) begin
        if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_valid_q[slot][lane]) begin
          for (int unsigned c = 0; c < NrExecClasses; c++)
            exec_result_queue_occupancy_lane_samples[c] += exec_class_by_id_q[
              ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_q[slot][lane].id][c];
        end
        if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_valid_q[slot][lane]) begin
          for (int unsigned c = 0; c < NrExecClasses; c++)
            exec_result_queue_occupancy_lane_samples[c] += exec_class_by_id_q[
              ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_q[slot][lane].id][c];
        end
        if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vldu.
              result_queue_valid_q[slot][lane]) begin
          for (int unsigned c = 0; c < NrExecClasses; c++)
            exec_result_queue_occupancy_lane_samples[c] += exec_class_by_id_q[
              ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vldu.
                result_queue_q[slot][lane].id][c];
        end
      end
    end

    // Attribute SLDU activity to native slide instructions or to the original
    // integer/FP reduction class according to the queued operation.
    sldu_issue_class = exec_class_by_id_q[
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_q.id
    ];
    if (!(|sldu_issue_class))
      sldu_issue_class = classify_exec_op(
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_q.op
      );
    sldu_commit_class = exec_class_by_id_q[
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_commit.id
    ];
    if (!(|sldu_commit_class))
      sldu_commit_class = classify_exec_op(
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_commit.op
      );
    sldu_progress =
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_cnt_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_cnt_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_valid_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_valid_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.issue_cnt_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.issue_cnt_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.commit_cnt_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.commit_cnt_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.in_pnt_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.in_pnt_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.out_pnt_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.out_pnt_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vrf_pnt_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vrf_pnt_q) ||
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.state_d !=
       ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.state_q);
    exec_event.issue_progress |= sldu_issue_class & {NrExecClasses{sldu_progress}};
    exec_event.operand_wait |= sldu_issue_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_valid_q &&
                     !sldu_progress &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_full}};
    exec_event.result_queue_full |= sldu_issue_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_valid_q &&
                     ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.result_queue_full}};
    exec_event.result_backpressure |= sldu_commit_class &
      {NrExecClasses{|(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_result_req_o &
                       ~ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.sldu_result_gnt_i)}};
    exec_event.cross_lane |= sldu_issue_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.is_issue_reduction}};
    exec_event.special_path |= sldu_issue_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_valid_q &&
                     ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_q.is_stride_np2}};

    // MASKU progress includes slice advancement and gather/compress FIFO work.
    mask_issue_class = classify_exec_op(
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.op
    );
    exec_mask_issue_class = mask_issue_class;
    exec_predicate_class = exec_class_by_id_q[
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.id
    ];
    if (!(|exec_predicate_class))
      exec_predicate_class = mask_issue_class;
    exec_predicate_packet =
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_cnt_d >
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_cnt_q &&
      !(ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.op inside
        {[VMADC:VMSBC]});
    exec_predicate_elements = '0;
    exec_predicate_active_elements = '0;
    exec_predicate_density_bin = '0;
    if (exec_predicate_packet) begin
      automatic int unsigned elements_per_packet = NrLanes *
        (1 << (3 - unsigned'(
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.vtype.vsew)));
      automatic int unsigned remaining_elements =
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.read_cnt_q;
      automatic int unsigned valid_elements =
        remaining_elements < elements_per_packet ? remaining_elements : elements_per_packet;
      exec_predicate_elements = valid_elements;
      for (int unsigned elm = 0; elm < NrLanes * 8; elm++) begin
        if (elm < valid_elements) begin
          automatic int unsigned seq_byte = elm << unsigned'(
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.vtype.vsew);
          automatic int unsigned vrf_byte = shuffle_index(
            seq_byte, NrLanes,
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.vtype.vsew
          );
          automatic int unsigned lane = vrf_byte >> 3;
          automatic int unsigned byte_offset = vrf_byte & 7;
          exec_predicate_active_elements +=
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_d[
              ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.mask_queue_write_pnt_q
            ][lane][byte_offset];
        end
      end
      if (exec_predicate_active_elements == 0)
        exec_predicate_density_bin = 0;
      else if (exec_predicate_active_elements == exec_predicate_elements)
        exec_predicate_density_bin = 5;
      else if (4 * exec_predicate_active_elements <= exec_predicate_elements)
        exec_predicate_density_bin = 1;
      else if (2 * exec_predicate_active_elements <= exec_predicate_elements)
        exec_predicate_density_bin = 2;
      else if (4 * exec_predicate_active_elements <= 3 * exec_predicate_elements)
        exec_predicate_density_bin = 3;
      else
        exec_predicate_density_bin = 4;
    end
    mask_commit_class = classify_exec_op(
      ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_commit.op
    );
    mask_progress = ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.in_ready_cnt_en ||
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.in_m_ready_cnt_en ||
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.out_valid_cnt_en ||
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_push ||
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_pop ||
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.out_vrf_word_valid ||
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.out_scalar_valid;
    exec_event.issue_progress |= mask_issue_class & {NrExecClasses{mask_progress}};
    exec_event.operand_wait |= mask_issue_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid &&
                     !mask_progress &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_full &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_full &&
                     !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_req_fifo_full}};
    exec_event.result_queue_full |= mask_issue_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid &&
                     ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_full}};
    exec_event.result_backpressure |= mask_commit_class &
      {NrExecClasses{|(ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_result_req_o &
                       ~ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_result_gnt_i)}};
    exec_event.special_path |= mask_issue_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid &&
                     (ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.op inside
                       {[VRGATHER:VCOMPRESS]})}};
    exec_event.index_fifo_full |= mask_issue_class &
      {NrExecClasses{ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid &&
                     (ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.op inside
                       {[VRGATHER:VCOMPRESS]}) &&
                     (ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_full ||
                      ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_req_fifo_full)}};

    // VLSU progress is observed at every independently blocking boundary:
    // address generation/MMU, AXI address/data/response, lane operands and VRF
    // writeback.  OR-reduction retains wall-cycle semantics for exec_event.
    exec_event.issue_progress[ExecLoad] |=
      memory_addrgen_progress[MemLoad] || memory_axi_address_fire[MemLoad] ||
      memory_axi_data_fire[MemLoad] || memory_axi_response_fire[MemLoad] ||
      (memory_result_handshake_lane_samples[MemLoad] != '0) || memory_completion[MemLoad];
    exec_event.issue_progress[ExecStore] |=
      memory_addrgen_progress[MemStore] || memory_axi_address_fire[MemStore] ||
      memory_axi_data_fire[MemStore] || memory_axi_response_fire[MemStore] ||
      (memory_operand_handshake_lane_samples[MemStore] != '0) || memory_completion[MemStore];
    exec_event.operand_wait[ExecLoad] |=
      memory_operand_wait[MemLoad] || memory_mask_wait[MemLoad];
    exec_event.operand_wait[ExecStore] |=
      memory_operand_wait[MemStore] || memory_mask_wait[MemStore];
    exec_event.unit_input_backpressure[ExecLoad] |=
      memory_axi_address_backpressure[MemLoad] || memory_axi_data_backpressure[MemLoad];
    exec_event.unit_input_backpressure[ExecStore] |=
      memory_axi_address_backpressure[MemStore] || memory_axi_data_backpressure[MemStore];
    exec_event.result_queue_full[ExecLoad] |= memory_result_queue_full[MemLoad];
    exec_event.result_backpressure[ExecLoad] |= memory_result_backpressure[MemLoad];
    exec_event.result_backpressure[ExecStore] |= memory_result_backpressure[MemStore];
    exec_event.long_latency_busy[ExecLoad] |=
      memory_mmu_wait[MemLoad] || memory_axi_data_wait[MemLoad];
    exec_event.long_latency_busy[ExecStore] |=
      memory_mmu_wait[MemStore] || memory_axi_data_wait[MemStore] ||
      memory_axi_response_wait[MemStore];
    exec_event.special_path[ExecLoad] |= memory_addrgen_active[MemLoad] &&
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.pe_req_q.op inside
        {VLSE, VLXE});
    exec_event.special_path[ExecStore] |= memory_addrgen_active[MemStore] &&
      (ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.pe_req_q.op inside
        {VSSE, VSXE});

    // Completion is architectural progress even when no datapath issue occurs.
    exec_event.issue_progress |= exec_completion_class;

    // Produce one deterministic primary label for every active class-cycle.
    // Raw event counters above remain overlapping evidence; this priority
    // partition is a stable first-pass attribution for automated ranking.
    exec_primary_result_backpressure = '0;
    exec_primary_result_queue_full = '0;
    exec_primary_latency_order_stall = '0;
    exec_primary_unit_input_backpressure = '0;
    exec_primary_operand_wait = '0;
    exec_primary_long_latency_busy = '0;
    exec_primary_special_path = '0;
    exec_primary_progress = '0;
    exec_primary_unattributed = '0;
    for (int unsigned c = 0; c < NrExecClasses; c++) begin
      if (exec_class_active[c]) begin
        if (exec_event.result_backpressure[c])
          exec_primary_result_backpressure[c] = 1'b1;
        else if (exec_event.result_queue_full[c])
          exec_primary_result_queue_full[c] = 1'b1;
        else if (exec_event.latency_order_stall[c])
          exec_primary_latency_order_stall[c] = 1'b1;
        else if (exec_event.unit_input_backpressure[c])
          exec_primary_unit_input_backpressure[c] = 1'b1;
        else if (exec_event.operand_wait[c])
          exec_primary_operand_wait[c] = 1'b1;
        else if (exec_event.long_latency_busy[c])
          exec_primary_long_latency_busy[c] = 1'b1;
        else if (exec_event.special_path[c])
          exec_primary_special_path[c] = 1'b1;
        else if (exec_event.issue_progress[c])
          exec_primary_progress[c] = 1'b1;
        else
          exec_primary_unattributed[c] = 1'b1;
      end
    end

    // Project the *current-cycle* primary class attribution to every active
    // opcode.  Keep this after the primary-label loop above: always_comb does
    // not guarantee a second evaluation for variables written earlier in the
    // same block, so projecting before the labels are formed can lag by one
    // cycle and break the opcode primary partition.
    exec_opcode_primary_result_backpressure = '0;
    exec_opcode_primary_result_queue_full = '0;
    exec_opcode_primary_latency_order_stall = '0;
    exec_opcode_primary_unit_input_backpressure = '0;
    exec_opcode_primary_operand_wait = '0;
    exec_opcode_primary_long_latency_busy = '0;
    exec_opcode_primary_special_path = '0;
    exec_opcode_primary_progress = '0;
    exec_opcode_primary_unattributed = '0;
    for (int unsigned id = 0; id < NrVInsn; id++) begin
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q[id] &&
          |exec_class_by_id_q[id]) begin
        automatic int unsigned op = unsigned'(exec_op_by_id_q[id]);
        for (int unsigned c = 0; c < NrExecClasses; c++) begin
          if (exec_class_by_id_q[id][c]) begin
            exec_opcode_primary_result_backpressure[op] |= exec_primary_result_backpressure[c];
            exec_opcode_primary_result_queue_full[op] |= exec_primary_result_queue_full[c];
            exec_opcode_primary_latency_order_stall[op] |= exec_primary_latency_order_stall[c];
            exec_opcode_primary_unit_input_backpressure[op] |= exec_primary_unit_input_backpressure[c];
            exec_opcode_primary_operand_wait[op] |= exec_primary_operand_wait[c];
            exec_opcode_primary_long_latency_busy[op] |= exec_primary_long_latency_busy[c];
            exec_opcode_primary_special_path[op] |= exec_primary_special_path[c];
            exec_opcode_primary_progress[op] |= exec_primary_progress[c];
            exec_opcode_primary_unattributed[op] |= exec_primary_unattributed[c];
          end
        end
      end
    end
    if (exec_scalar_move_pending_q) begin
      automatic int unsigned op = unsigned'(exec_scalar_move_op_q);
      for (int unsigned c = 0; c < NrExecClasses; c++) begin
        if (exec_scalar_move_class_q[c]) begin
          exec_opcode_primary_result_backpressure[op] |= exec_primary_result_backpressure[c];
          exec_opcode_primary_result_queue_full[op] |= exec_primary_result_queue_full[c];
          exec_opcode_primary_latency_order_stall[op] |= exec_primary_latency_order_stall[c];
          exec_opcode_primary_unit_input_backpressure[op] |= exec_primary_unit_input_backpressure[c];
          exec_opcode_primary_operand_wait[op] |= exec_primary_operand_wait[c];
          exec_opcode_primary_long_latency_busy[op] |= exec_primary_long_latency_busy[c];
          exec_opcode_primary_special_path[op] |= exec_primary_special_path[c];
          exec_opcode_primary_progress[op] |= exec_primary_progress[c];
          exec_opcode_primary_unattributed[op] |= exec_primary_unattributed[c];
        end
      end
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin : p_exec_perf_counters
    if (!rst_n) begin
      exec_class_by_id_q           <= '0;
      exec_op_by_id_q              <= '{default: VADD};
      exec_sew_by_id_q             <= '0;
      exec_lmul_by_id_q            <= '0;
      exec_masked_by_id_q          <= '0;
      exec_issue_cycle_by_id_q     <= '0;
      exec_dispatch_wait_by_id_q   <= '0;
      exec_pending_accept_cycle_q  <= '0;
      exec_pending_accept_valid_q  <= 1'b0;
      exec_pending_class_q         <= '0;
      exec_pending_op_q            <= VADD;
      exec_scalar_move_pending_q   <= 1'b0;
      exec_scalar_move_class_q     <= '0;
      exec_scalar_move_op_q        <= VADD;
      exec_scalar_move_sew_q       <= '0;
      exec_scalar_move_lmul_q      <= '0;
      exec_scalar_move_issue_cycle_q <= '0;
      exec_scalar_move_dispatch_wait_q <= '0;
      exec_perf_counters           <= '{default: '0};
    end else begin
      if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn) begin
        exec_pending_accept_cycle_q <= wall_cycle;
        exec_pending_accept_valid_q <= 1'b1;
        exec_pending_class_q        <= accepted_exec_class;
        exec_pending_op_q           <=
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op;
      end

      if (exec_first_issue) begin
        automatic vid_t issue_id =
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_d.id;
        exec_class_by_id_q[issue_id]         <= first_issue_class;
        exec_op_by_id_q[issue_id]            <= first_issue_op;
        exec_sew_by_id_q[issue_id]           <= unsigned'(
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_d.vtype.vsew);
        exec_lmul_by_id_q[issue_id]          <= unsigned'(
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_d.vtype.vlmul);
        exec_masked_by_id_q[issue_id]        <=
          !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_d.vm;
        exec_issue_cycle_by_id_q[issue_id]   <= wall_cycle;
        exec_dispatch_wait_by_id_q[issue_id] <= exec_dispatch_wait;
        exec_pending_accept_valid_q          <= 1'b0;
        if (first_issue_class[ExecMoveFromVec]) begin
          exec_scalar_move_pending_q       <= 1'b1;
          exec_scalar_move_class_q         <= first_issue_class;
          exec_scalar_move_op_q            <= first_issue_op;
          exec_scalar_move_sew_q           <= unsigned'(
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_d.vtype.vsew);
          exec_scalar_move_lmul_q          <= unsigned'(
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_d.vtype.vlmul);
          exec_scalar_move_issue_cycle_q   <= wall_cycle;
          exec_scalar_move_dispatch_wait_q <= exec_dispatch_wait;
        end
      end

      if (exec_scalar_move_complete)
        exec_scalar_move_pending_q <= 1'b0;

      for (int unsigned c = 0; c < NrExecClasses; c++) begin
        exec_perf_counters.insn_count[c] <= exec_perf_counters.insn_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c]);
        exec_perf_counters.issued_count[c] <= exec_perf_counters.issued_count[c] +
          (exec_first_issue && first_issue_class[c]);
        exec_perf_counters.completed_count[c] <= exec_perf_counters.completed_count[c] +
          exec_completion_count[c];
        exec_perf_counters.requested_element_count[c] <=
          exec_perf_counters.requested_element_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c]
             ? (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vl >=
                ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vstart
                  ? ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vl -
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vstart
                  : 0)
             : 0);
        exec_perf_counters.nominal_element_op_count[c] <=
          exec_perf_counters.nominal_element_op_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c]
             ? (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vl >=
                ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vstart
                  ? ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vl -
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vstart
                  : 0) * nominal_element_op_weight(
                    ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op)
             : 0);
        exec_perf_counters.masked_insn_count[c] <=
          exec_perf_counters.masked_insn_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c] &&
           !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vm);
        exec_perf_counters.reduction_insn_count[c] <=
          exec_perf_counters.reduction_insn_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c] &&
           is_exec_reduction(
             ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op));
        exec_perf_counters.special_insn_count[c] <=
          exec_perf_counters.special_insn_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c] &&
           is_exec_special_path(
             ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op,
             ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.is_stride_np2));
        exec_perf_counters.unit_stride_uop_count[c] <=
          exec_perf_counters.unit_stride_uop_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c] &&
           (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op inside
             {VLE, VSE}));
        exec_perf_counters.strided_uop_count[c] <=
          exec_perf_counters.strided_uop_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c] &&
           (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op inside
             {VLSE, VSSE}));
        exec_perf_counters.indexed_uop_count[c] <=
          exec_perf_counters.indexed_uop_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c] &&
           (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op inside
             {VLXE, VSXE}));
        exec_perf_counters.segment_uop_count[c] <=
          exec_perf_counters.segment_uop_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c] &&
           (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op inside
             {[VLE:VSXE]}) &&
           (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.nf != '0));
        exec_perf_counters.fault_only_first_uop_count[c] <=
          exec_perf_counters.fault_only_first_uop_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c] &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.fault_only_first);
        exec_perf_counters.requested_byte_count[c] <=
          exec_perf_counters.requested_byte_count[c] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
           accepted_exec_class[c]
             ? ((ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vl >=
                 ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vstart
                   ? ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vl -
                     ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vstart
                   : 0) <<
                unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vtype.vsew))
             : 0);
        for (int unsigned sew = 0; sew < 4; sew++) begin
          exec_perf_counters.sew_insn_hist[c][sew] <=
            exec_perf_counters.sew_insn_hist[c][sew] +
            (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
             accepted_exec_class[c] &&
             unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vtype.vsew) == sew);
        end

        exec_perf_counters.active_cycle[c] <= exec_perf_counters.active_cycle[c] +
          exec_class_active[c];
        exec_perf_counters.inflight_insn_cycle[c] <=
          exec_perf_counters.inflight_insn_cycle[c] + exec_inflight_count[c];
        exec_perf_counters.masked_active_cycle[c] <=
          exec_perf_counters.masked_active_cycle[c] + exec_masked_class_active[c];

        exec_perf_counters.dispatch_wait_cycle[c] <=
          exec_perf_counters.dispatch_wait_cycle[c] +
          (exec_first_issue && first_issue_class[c] ? exec_dispatch_wait : 0);
        for (int unsigned b = 0; b < 4; b++) begin
          exec_perf_counters.dispatch_wait_hist[c][b] <=
            exec_perf_counters.dispatch_wait_hist[c][b] +
            (exec_first_issue && first_issue_class[c] && exec_dispatch_wait_bin == b);
          exec_perf_counters.execution_latency_hist[c][b] <=
            exec_perf_counters.execution_latency_hist[c][b] +
            exec_completion_latency_hist[c][b];
        end
        exec_perf_counters.execution_latency_cycle[c] <=
          exec_perf_counters.execution_latency_cycle[c] + exec_completion_latency[c];
        exec_perf_counters.end_to_end_latency_cycle[c] <=
          exec_perf_counters.end_to_end_latency_cycle[c] +
          exec_completion_end_to_end_latency[c];

        exec_perf_counters.dispatch_request_cycle[c] <=
          exec_perf_counters.dispatch_request_cycle[c] + exec_dispatch_request[c];
        exec_perf_counters.dispatch_blocked_cycle[c] <=
          exec_perf_counters.dispatch_blocked_cycle[c] + exec_dispatch_blocked[c];
        exec_perf_counters.primary_fu_queue_full_cycle[c] <=
          exec_perf_counters.primary_fu_queue_full_cycle[c] +
          exec_primary_fu_queue_full[c];
        exec_perf_counters.primary_mask_queue_full_cycle[c] <=
          exec_perf_counters.primary_mask_queue_full_cycle[c] +
          exec_primary_mask_queue_full[c];
        exec_perf_counters.primary_slide_queue_full_cycle[c] <=
          exec_perf_counters.primary_slide_queue_full_cycle[c] +
          exec_primary_slide_queue_full[c];
        exec_perf_counters.primary_id_pool_full_cycle[c] <=
          exec_perf_counters.primary_id_pool_full_cycle[c] +
          exec_primary_id_pool_full[c];
        exec_perf_counters.primary_response_wait_cycle[c] <=
          exec_perf_counters.primary_response_wait_cycle[c] +
          exec_primary_response_wait[c];
        exec_perf_counters.primary_lane_desync_cycle[c] <=
          exec_perf_counters.primary_lane_desync_cycle[c] +
          exec_primary_lane_desync[c];
        exec_perf_counters.primary_sequencer_block_cycle[c] <=
          exec_perf_counters.primary_sequencer_block_cycle[c] +
          exec_primary_sequencer_block[c];
        exec_perf_counters.primary_operand_request_blocked_cycle[c] <=
          exec_perf_counters.primary_operand_request_blocked_cycle[c] +
          exec_primary_operand_request_blocked[c];
        exec_perf_counters.primary_other_dispatch_blocked_cycle[c] <=
          exec_perf_counters.primary_other_dispatch_blocked_cycle[c] +
          exec_primary_other_dispatch_blocked[c];
        exec_perf_counters.fu_queue_full_cycle[c] <=
          exec_perf_counters.fu_queue_full_cycle[c] + exec_fu_queue_full[c];
        exec_perf_counters.mask_queue_full_cycle[c] <=
          exec_perf_counters.mask_queue_full_cycle[c] + exec_mask_queue_full[c];
        exec_perf_counters.slide_queue_full_cycle[c] <=
          exec_perf_counters.slide_queue_full_cycle[c] + exec_slide_queue_full[c];
        exec_perf_counters.id_pool_full_cycle[c] <=
          exec_perf_counters.id_pool_full_cycle[c] + exec_id_pool_full[c];
        exec_perf_counters.response_wait_cycle[c] <=
          exec_perf_counters.response_wait_cycle[c] + exec_response_wait[c];
        exec_perf_counters.other_dispatch_blocked_cycle[c] <=
          exec_perf_counters.other_dispatch_blocked_cycle[c] + exec_other_dispatch_blocked[c];
        exec_perf_counters.operand_request_blocked_cycle[c] <=
          exec_perf_counters.operand_request_blocked_cycle[c] + exec_operand_request_blocked[c];
        exec_perf_counters.raw_hazard_cycle[c] <=
          exec_perf_counters.raw_hazard_cycle[c] + exec_raw_hazard[c];
        exec_perf_counters.war_hazard_cycle[c] <=
          exec_perf_counters.war_hazard_cycle[c] + exec_war_hazard[c];
        exec_perf_counters.waw_hazard_cycle[c] <=
          exec_perf_counters.waw_hazard_cycle[c] + exec_waw_hazard[c];
        exec_perf_counters.false_hazard_cycle[c] <=
          exec_perf_counters.false_hazard_cycle[c] + exec_false_hazard[c];
        exec_perf_counters.sequencer_block_cycle[c] <=
          exec_perf_counters.sequencer_block_cycle[c] + exec_sequencer_block[c];
        exec_perf_counters.lane_desync_cycle[c] <=
          exec_perf_counters.lane_desync_cycle[c] + exec_lane_desync[c];

        exec_perf_counters.issue_progress_cycle[c] <=
          exec_perf_counters.issue_progress_cycle[c] + exec_event.issue_progress[c];
        exec_perf_counters.no_issue_progress_cycle[c] <=
          exec_perf_counters.no_issue_progress_cycle[c] +
          (exec_class_active[c] && !exec_event.issue_progress[c]);
        exec_perf_counters.operand_wait_cycle[c] <=
          exec_perf_counters.operand_wait_cycle[c] + exec_event.operand_wait[c];
        exec_perf_counters.unit_input_backpressure_cycle[c] <=
          exec_perf_counters.unit_input_backpressure_cycle[c] +
          exec_event.unit_input_backpressure[c];
        exec_perf_counters.latency_order_stall_cycle[c] <=
          exec_perf_counters.latency_order_stall_cycle[c] +
          exec_event.latency_order_stall[c];
        exec_perf_counters.result_queue_full_cycle[c] <=
          exec_perf_counters.result_queue_full_cycle[c] + exec_event.result_queue_full[c];
        exec_perf_counters.result_backpressure_cycle[c] <=
          exec_perf_counters.result_backpressure_cycle[c] + exec_event.result_backpressure[c];
        exec_perf_counters.long_latency_busy_cycle[c] <=
          exec_perf_counters.long_latency_busy_cycle[c] + exec_event.long_latency_busy[c];
        exec_perf_counters.reduction_cycle[c] <=
          exec_perf_counters.reduction_cycle[c] + exec_event.reduction[c];
        exec_perf_counters.cross_lane_cycle[c] <=
          exec_perf_counters.cross_lane_cycle[c] + exec_event.cross_lane[c];
        exec_perf_counters.special_path_cycle[c] <=
          exec_perf_counters.special_path_cycle[c] + exec_event.special_path[c];
        exec_perf_counters.index_fifo_full_cycle[c] <=
          exec_perf_counters.index_fifo_full_cycle[c] + exec_event.index_fifo_full[c];
        if (c == ExecMask) begin
          exec_perf_counters.mask_operand_incomplete_cycle[c] <=
            exec_perf_counters.mask_operand_incomplete_cycle[c] +
            (ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid &&
             !(&ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_alu_valid));
          exec_perf_counters.mask_issue_end_cycle[c] <=
            exec_perf_counters.mask_issue_end_cycle[c] +
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vcompress_issue_end_q;
          exec_perf_counters.mask_commit_pending_cycle[c] <=
            exec_perf_counters.mask_commit_pending_cycle[c] +
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_commit_valid;
          exec_perf_counters.mask_result_queue_nonempty_cycle[c] <=
            exec_perf_counters.mask_result_queue_nonempty_cycle[c] +
            !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_empty;
          exec_perf_counters.mask_final_grant_wait_cycle[c] <=
            exec_perf_counters.mask_final_grant_wait_cycle[c] +
            (ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_commit_valid &&
             (ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.commit_cnt_d == '0) &&
             !(&ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_final_gnt_d));
          exec_perf_counters.mask_index_fifo_nonempty_cycle[c] <=
            exec_perf_counters.mask_index_fifo_nonempty_cycle[c] +
            !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_empty;
          exec_perf_counters.mask_request_fifo_nonempty_cycle[c] <=
            exec_perf_counters.mask_request_fifo_nonempty_cycle[c] +
            !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_req_fifo_empty;
        end

        exec_perf_counters.primary_result_backpressure_cycle[c] <=
          exec_perf_counters.primary_result_backpressure_cycle[c] +
          exec_primary_result_backpressure[c];
        exec_perf_counters.primary_result_queue_full_cycle[c] <=
          exec_perf_counters.primary_result_queue_full_cycle[c] +
          exec_primary_result_queue_full[c];
        exec_perf_counters.primary_latency_order_stall_cycle[c] <=
          exec_perf_counters.primary_latency_order_stall_cycle[c] +
          exec_primary_latency_order_stall[c];
        exec_perf_counters.primary_unit_input_backpressure_cycle[c] <=
          exec_perf_counters.primary_unit_input_backpressure_cycle[c] +
          exec_primary_unit_input_backpressure[c];
        exec_perf_counters.primary_operand_wait_cycle[c] <=
          exec_perf_counters.primary_operand_wait_cycle[c] + exec_primary_operand_wait[c];
        exec_perf_counters.primary_long_latency_busy_cycle[c] <=
          exec_perf_counters.primary_long_latency_busy_cycle[c] +
          exec_primary_long_latency_busy[c];
        exec_perf_counters.primary_special_path_cycle[c] <=
          exec_perf_counters.primary_special_path_cycle[c] + exec_primary_special_path[c];
        exec_perf_counters.primary_progress_cycle[c] <=
          exec_perf_counters.primary_progress_cycle[c] + exec_primary_progress[c];
        exec_perf_counters.primary_unattributed_cycle[c] <=
          exec_perf_counters.primary_unattributed_cycle[c] + exec_primary_unattributed[c];
        exec_perf_counters.primary_dispatch_unattributed_cycle[c] <=
          exec_perf_counters.primary_dispatch_unattributed_cycle[c] +
          exec_primary_dispatch_unattributed[c];

        exec_perf_counters.issue_progress_lane_sample[c] <=
          exec_perf_counters.issue_progress_lane_sample[c] + exec_issue_progress_lane_sample[c];
        exec_perf_counters.operand_wait_lane_sample[c] <=
          exec_perf_counters.operand_wait_lane_sample[c] + exec_operand_wait_lane_sample[c];
        exec_perf_counters.unit_input_backpressure_lane_sample[c] <=
          exec_perf_counters.unit_input_backpressure_lane_sample[c] +
          exec_unit_input_backpressure_lane_sample[c];
        exec_perf_counters.latency_order_stall_lane_sample[c] <=
          exec_perf_counters.latency_order_stall_lane_sample[c] +
          exec_latency_order_stall_lane_sample[c];
        exec_perf_counters.result_queue_full_lane_sample[c] <=
          exec_perf_counters.result_queue_full_lane_sample[c] +
          exec_result_queue_full_lane_sample[c];
        exec_perf_counters.result_backpressure_lane_sample[c] <=
          exec_perf_counters.result_backpressure_lane_sample[c] +
          exec_result_backpressure_lane_sample[c];
        exec_perf_counters.long_latency_busy_lane_sample[c] <=
          exec_perf_counters.long_latency_busy_lane_sample[c] +
          exec_long_latency_busy_lane_sample[c];
        exec_perf_counters.result_queue_occupancy_lane_sample[c] <=
          exec_perf_counters.result_queue_occupancy_lane_sample[c] +
          exec_result_queue_occupancy_lane_samples[c];
        exec_perf_counters.vrf_read_request_lane_sample[c] <=
          exec_perf_counters.vrf_read_request_lane_sample[c] +
          exec_vrf_read_request_lane_sample[c];
        exec_perf_counters.vrf_read_grant_lane_sample[c] <=
          exec_perf_counters.vrf_read_grant_lane_sample[c] +
          exec_vrf_read_grant_lane_sample[c];
        exec_perf_counters.vrf_bank_conflict_lane_sample[c] <=
          exec_perf_counters.vrf_bank_conflict_lane_sample[c] +
          exec_vrf_bank_conflict_lane_sample[c];
        exec_perf_counters.vrf_hazard_stall_lane_sample[c] <=
          exec_perf_counters.vrf_hazard_stall_lane_sample[c] +
          exec_vrf_hazard_stall_lane_sample[c];
        exec_perf_counters.operand_queue_backpressure_lane_sample[c] <=
          exec_perf_counters.operand_queue_backpressure_lane_sample[c] +
          exec_operand_queue_backpressure_lane_sample[c];
        exec_perf_counters.predicate_packet_count[c] <=
          exec_perf_counters.predicate_packet_count[c] +
          (exec_predicate_packet && exec_predicate_class[c]);
        exec_perf_counters.predicate_element_count[c] <=
          exec_perf_counters.predicate_element_count[c] +
          (exec_predicate_packet && exec_predicate_class[c]
            ? exec_predicate_elements : 0);
        exec_perf_counters.predicate_active_element_count[c] <=
          exec_perf_counters.predicate_active_element_count[c] +
          (exec_predicate_packet && exec_predicate_class[c]
            ? exec_predicate_active_elements : 0);
        for (int unsigned b = 0; b < NrMaskDensityBins; b++)
          exec_perf_counters.predicate_density_hist[c][b] <=
            exec_perf_counters.predicate_density_hist[c][b] +
            (exec_predicate_packet && exec_predicate_class[c] &&
             exec_predicate_density_bin == b);
        exec_perf_counters.mask_index_fifo_push_count[c] <=
          exec_perf_counters.mask_index_fifo_push_count[c] +
          (exec_mask_issue_class[c] &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_push);
        exec_perf_counters.mask_index_fifo_pop_count[c] <=
          exec_perf_counters.mask_index_fifo_pop_count[c] +
          (exec_mask_issue_class[c] &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_pop);
        exec_perf_counters.gather_request_fifo_push_count[c] <=
          exec_perf_counters.gather_request_fifo_push_count[c] +
          (exec_mask_issue_class[c] &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_req_fifo_push);
        exec_perf_counters.gather_request_fifo_pop_count[c] <=
          exec_perf_counters.gather_request_fifo_pop_count[c] +
          (exec_mask_issue_class[c] &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_req_fifo_pop);
        exec_perf_counters.gather_broadcast_request_lane_sample[c] <=
          exec_perf_counters.gather_broadcast_request_lane_sample[c] +
          (exec_mask_issue_class[c] ? $countones(
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_vrgat_req_valid_o) : 0);
        exec_perf_counters.gather_broadcast_grant_lane_sample[c] <=
          exec_perf_counters.gather_broadcast_grant_lane_sample[c] +
          (exec_mask_issue_class[c] ? $countones(
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_vrgat_req_valid_o &
            ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_vrgat_req_ready_i) : 0);
        exec_perf_counters.gather_out_of_range_index_count[c] <=
          exec_perf_counters.gather_out_of_range_index_count[c] +
          (exec_mask_issue_class[c] &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.op != VCOMPRESS &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_push &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_oor_d);
        exec_perf_counters.compress_examined_element_count[c] <=
          exec_perf_counters.compress_examined_element_count[c] +
          (exec_mask_issue_class[c] &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.op == VCOMPRESS &&
           &ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_alu_valid &&
           !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_full &&
           !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_req_fifo_full);
        exec_perf_counters.compress_selected_element_count[c] <=
          exec_perf_counters.compress_selected_element_count[c] +
          (exec_mask_issue_class[c] &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue_valid &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vinsn_issue.op == VCOMPRESS &&
           &ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.masku_operand_alu_valid &&
           !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_idx_fifo_full &&
           !ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vrgat_req_fifo_full &&
           ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vcompress_bit);
      end

      for (int unsigned u = 0; u < NrMfpuSubunits; u++) begin
        exec_perf_counters.mfpu_input_fire_lane_sample[u] <=
          exec_perf_counters.mfpu_input_fire_lane_sample[u] +
          exec_mfpu_input_fire_lane_sample[u];
        exec_perf_counters.mfpu_input_backpressure_lane_sample[u] <=
          exec_perf_counters.mfpu_input_backpressure_lane_sample[u] +
          exec_mfpu_input_backpressure_lane_sample[u];
        exec_perf_counters.mfpu_output_fire_lane_sample[u] <=
          exec_perf_counters.mfpu_output_fire_lane_sample[u] +
          exec_mfpu_output_fire_lane_sample[u];
        exec_perf_counters.mfpu_processing_lane_sample[u] <=
          exec_perf_counters.mfpu_processing_lane_sample[u] +
          exec_mfpu_processing_lane_sample[u];
      end
      for (int unsigned s = 0; s < NrValuStates; s++)
        exec_perf_counters.valu_state_lane_sample[s] <=
          exec_perf_counters.valu_state_lane_sample[s] + exec_valu_state_lane_sample[s];
      for (int unsigned s = 0; s < NrMfpuStates; s++)
        exec_perf_counters.mfpu_state_lane_sample[s] <=
          exec_perf_counters.mfpu_state_lane_sample[s] + exec_mfpu_state_lane_sample[s];
      for (int unsigned s = 0; s < NrSlduStates; s++)
        exec_perf_counters.sldu_state_cycle[s] <=
          exec_perf_counters.sldu_state_cycle[s] +
          (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.vinsn_issue_valid_q &&
           unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sldu.state_q) == s);

      // Backend opcode accounting uses the accepted Ara request, so segment
      // expansion and internal reshuffle requests remain visible as uops.
      for (int unsigned op = 0; op < NrAraOps; op++) begin
        logic accepted_op;
        logic [63:0] elements;
        exec_perf_counters.opcode_dispatch_wait_cycle[op] <=
          exec_perf_counters.opcode_dispatch_wait_cycle[op] +
          (exec_first_issue && first_issue_op == ara_op_e'(op) ? exec_dispatch_wait : 0);
        for (int unsigned b = 0; b < 4; b++) begin
          exec_perf_counters.opcode_dispatch_wait_hist[op][b] <=
            exec_perf_counters.opcode_dispatch_wait_hist[op][b] +
            (exec_first_issue && first_issue_op == ara_op_e'(op) &&
             exec_dispatch_wait_bin == b);
        end
        exec_perf_counters.opcode_dispatch_request_cycle[op] <=
          exec_perf_counters.opcode_dispatch_request_cycle[op] +
          exec_opcode_dispatch_request[op];
        exec_perf_counters.opcode_dispatch_blocked_cycle[op] <=
          exec_perf_counters.opcode_dispatch_blocked_cycle[op] +
          exec_opcode_dispatch_blocked[op];
        exec_perf_counters.opcode_active_cycle[op] <=
          exec_perf_counters.opcode_active_cycle[op] +
          exec_opcode_active_cycle[op];
        exec_perf_counters.opcode_fu_queue_full_cycle[op] <=
          exec_perf_counters.opcode_fu_queue_full_cycle[op] +
          exec_opcode_fu_queue_full[op];
        exec_perf_counters.opcode_mask_queue_full_cycle[op] <=
          exec_perf_counters.opcode_mask_queue_full_cycle[op] +
          exec_opcode_mask_queue_full[op];
        exec_perf_counters.opcode_slide_queue_full_cycle[op] <=
          exec_perf_counters.opcode_slide_queue_full_cycle[op] +
          exec_opcode_slide_queue_full[op];
        exec_perf_counters.opcode_id_pool_full_cycle[op] <=
          exec_perf_counters.opcode_id_pool_full_cycle[op] +
          exec_opcode_id_pool_full[op];
        exec_perf_counters.opcode_response_wait_cycle[op] <=
          exec_perf_counters.opcode_response_wait_cycle[op] +
          exec_opcode_response_wait[op];
        exec_perf_counters.opcode_other_dispatch_blocked_cycle[op] <=
          exec_perf_counters.opcode_other_dispatch_blocked_cycle[op] +
          exec_opcode_other_dispatch_blocked[op];
        exec_perf_counters.opcode_operand_request_blocked_cycle[op] <=
          exec_perf_counters.opcode_operand_request_blocked_cycle[op] +
          exec_opcode_operand_request_blocked[op];
        exec_perf_counters.opcode_primary_fu_queue_full_cycle[op] <=
          exec_perf_counters.opcode_primary_fu_queue_full_cycle[op] +
          exec_opcode_primary_fu_queue_full[op];
        exec_perf_counters.opcode_primary_mask_queue_full_cycle[op] <=
          exec_perf_counters.opcode_primary_mask_queue_full_cycle[op] +
          exec_opcode_primary_mask_queue_full[op];
        exec_perf_counters.opcode_primary_slide_queue_full_cycle[op] <=
          exec_perf_counters.opcode_primary_slide_queue_full_cycle[op] +
          exec_opcode_primary_slide_queue_full[op];
        exec_perf_counters.opcode_primary_id_pool_full_cycle[op] <=
          exec_perf_counters.opcode_primary_id_pool_full_cycle[op] +
          exec_opcode_primary_id_pool_full[op];
        exec_perf_counters.opcode_primary_response_wait_cycle[op] <=
          exec_perf_counters.opcode_primary_response_wait_cycle[op] +
          exec_opcode_primary_response_wait[op];
        exec_perf_counters.opcode_primary_lane_desync_cycle[op] <=
          exec_perf_counters.opcode_primary_lane_desync_cycle[op] +
          exec_opcode_primary_lane_desync[op];
        exec_perf_counters.opcode_primary_sequencer_block_cycle[op] <=
          exec_perf_counters.opcode_primary_sequencer_block_cycle[op] +
          exec_opcode_primary_sequencer_block[op];
        exec_perf_counters.opcode_primary_operand_request_blocked_cycle[op] <=
          exec_perf_counters.opcode_primary_operand_request_blocked_cycle[op] +
          exec_opcode_primary_operand_request_blocked[op];
        exec_perf_counters.opcode_primary_other_dispatch_blocked_cycle[op] <=
          exec_perf_counters.opcode_primary_other_dispatch_blocked_cycle[op] +
          exec_opcode_primary_other_dispatch_blocked[op];
        exec_perf_counters.opcode_primary_dispatch_unattributed_cycle[op] <=
          exec_perf_counters.opcode_primary_dispatch_unattributed_cycle[op] +
          exec_opcode_primary_dispatch_unattributed[op];
        exec_perf_counters.opcode_primary_result_backpressure_cycle[op] <=
          exec_perf_counters.opcode_primary_result_backpressure_cycle[op] +
          exec_opcode_primary_result_backpressure[op];
        exec_perf_counters.opcode_primary_result_queue_full_cycle[op] <=
          exec_perf_counters.opcode_primary_result_queue_full_cycle[op] +
          exec_opcode_primary_result_queue_full[op];
        exec_perf_counters.opcode_primary_latency_order_stall_cycle[op] <=
          exec_perf_counters.opcode_primary_latency_order_stall_cycle[op] +
          exec_opcode_primary_latency_order_stall[op];
        exec_perf_counters.opcode_primary_unit_input_backpressure_cycle[op] <=
          exec_perf_counters.opcode_primary_unit_input_backpressure_cycle[op] +
          exec_opcode_primary_unit_input_backpressure[op];
        exec_perf_counters.opcode_primary_operand_wait_cycle[op] <=
          exec_perf_counters.opcode_primary_operand_wait_cycle[op] +
          exec_opcode_primary_operand_wait[op];
        exec_perf_counters.opcode_primary_long_latency_busy_cycle[op] <=
          exec_perf_counters.opcode_primary_long_latency_busy_cycle[op] +
          exec_opcode_primary_long_latency_busy[op];
        exec_perf_counters.opcode_primary_special_path_cycle[op] <=
          exec_perf_counters.opcode_primary_special_path_cycle[op] +
          exec_opcode_primary_special_path[op];
        exec_perf_counters.opcode_primary_progress_cycle[op] <=
          exec_perf_counters.opcode_primary_progress_cycle[op] +
          exec_opcode_primary_progress[op];
        exec_perf_counters.opcode_primary_unattributed_cycle[op] <=
          exec_perf_counters.opcode_primary_unattributed_cycle[op] +
          exec_opcode_primary_unattributed[op];

        accepted_op =
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.accepted_insn &&
          (unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.op) == op);
        elements =
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vl >=
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vstart
            ? ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vl -
              ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vstart
            : 0;
        exec_perf_counters.opcode_uop_count[op] <=
          exec_perf_counters.opcode_uop_count[op] + accepted_op;
        exec_perf_counters.opcode_completed_count[op] <=
          exec_perf_counters.opcode_completed_count[op] + exec_opcode_completion_count[op];
        exec_perf_counters.opcode_requested_element_count[op] <=
          exec_perf_counters.opcode_requested_element_count[op] +
          (accepted_op ? elements : 0);
        exec_perf_counters.opcode_nominal_element_op_count[op] <=
          exec_perf_counters.opcode_nominal_element_op_count[op] +
          (accepted_op ? elements * nominal_element_op_weight(ara_op_e'(op)) : 0);
        exec_perf_counters.opcode_masked_count[op] <=
          exec_perf_counters.opcode_masked_count[op] +
          (accepted_op && !ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_req_i.vm);
        exec_perf_counters.opcode_execution_latency_cycle[op] <=
          exec_perf_counters.opcode_execution_latency_cycle[op] +
          exec_opcode_completion_latency[op];
        for (int unsigned b = 0; b < 4; b++) begin
          exec_perf_counters.opcode_execution_latency_hist[op][b] <=
            exec_perf_counters.opcode_execution_latency_hist[op][b] +
            exec_opcode_completion_latency_hist[op][b];
          exec_perf_counters.opcode_sew_hist[op][b] <=
            exec_perf_counters.opcode_sew_hist[op][b] +
            (accepted_op &&
             unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.
               ara_req_i.vtype.vsew) == b);
        end
        for (int unsigned lmul = 0; lmul < 8; lmul++) begin
          exec_perf_counters.opcode_lmul_hist[op][lmul] <=
            exec_perf_counters.opcode_lmul_hist[op][lmul] +
            (accepted_op &&
             unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.
               ara_req_i.vtype.vlmul) == lmul);
        end
        for (int unsigned sew = 0; sew < 4; sew++) begin
          for (int unsigned lmul = 0; lmul < 8; lmul++) begin
            // Avoid scheduling thousands of no-op NBA updates every cycle.
            // This keeps the detailed joint histogram practical in long
            // simulations without changing its event definitions.
            if (accepted_op &&
                unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.
                  ara_req_i.vtype.vsew) == sew &&
                unsigned'(ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.
                  ara_req_i.vtype.vlmul) == lmul)
              exec_perf_counters.opcode_shape_uop_count[op][sew][lmul] <=
                exec_perf_counters.opcode_shape_uop_count[op][sew][lmul] + 1;
            if (exec_opcode_shape_completion_count[op][sew][lmul] != 0)
              exec_perf_counters.opcode_shape_completed_count[op][sew][lmul] <=
                exec_perf_counters.opcode_shape_completed_count[op][sew][lmul] +
                exec_opcode_shape_completion_count[op][sew][lmul];
            if (exec_opcode_shape_completion_latency[op][sew][lmul] != 0)
              exec_perf_counters.opcode_shape_latency_cycle[op][sew][lmul] <=
                exec_perf_counters.opcode_shape_latency_cycle[op][sew][lmul] +
                exec_opcode_shape_completion_latency[op][sew][lmul];
          end
        end
      end
    end
  end

  /*********
   *  DUT  *
   *********/

  `ifndef SAIF
  `ifndef IDEAL_DISPATCHER
  logic        perf_time_q;
  logic        perf_time_n;
  perf_t       perf_start_q, perf_end_q;
  perf_t       perf_start_n, perf_end_n;
  longint unsigned perf_watchdog_limit;
  longint unsigned perf_watchdog_count;
  logic            perf_watchdog_pending;
  logic [NrLanes-1:0][2:0]  watchdog_div_issue_state;
  logic [NrLanes-1:0][1:0]  watchdog_div_commit_state;
  logic [NrLanes-1:0][63:0] watchdog_div_operand_a, watchdog_div_operand_b;
  logic [NrLanes-1:0][1:0]  watchdog_div_serdiv_state;
  logic [NrLanes-1:0][5:0]  watchdog_div_serdiv_count;
  for (genvar watchdog_lane = 0; watchdog_lane < NrLanes; watchdog_lane++) begin : gen_watchdog_div
    assign watchdog_div_issue_state[watchdog_lane] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[watchdog_lane].i_lane.i_vfus.i_vmfpu.i_simd_div.issue_state_q;
    assign watchdog_div_commit_state[watchdog_lane] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[watchdog_lane].i_lane.i_vfus.i_vmfpu.i_simd_div.commit_state_q;
    assign watchdog_div_operand_a[watchdog_lane] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[watchdog_lane].i_lane.i_vfus.i_vmfpu.i_simd_div.opa_q;
    assign watchdog_div_operand_b[watchdog_lane] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[watchdog_lane].i_lane.i_vfus.i_vmfpu.i_simd_div.opb_q;
    assign watchdog_div_serdiv_state[watchdog_lane] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[watchdog_lane].i_lane.i_vfus.i_vmfpu.i_simd_div.i_serdiv.state_q;
    assign watchdog_div_serdiv_count[watchdog_lane] =
      ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[watchdog_lane].i_lane.i_vfus.i_vmfpu.i_simd_div.i_serdiv.cnt_q;
  end
  logic [63:0] rvv_cycle;
  logic [63:0] rvv_lane_cycle;
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;
  logic [63:0] rvv_instret;
  logic [63:0] rvv_op      ;
  logic [63:0] rvv_op_fs1  ;
  logic [63:0] rvv_op_fd   ;
  logic [63:0] rvv_op_load ;
  logic [63:0] rvv_op_store;
  logic [63:0] rvv_axi_aw_count;
  logic [63:0] rvv_axi_w_count;
  logic [63:0] rvv_axi_b_count;
  logic [63:0] rvv_axi_ar_count;
  logic [63:0] rvv_axi_r_count;
  logic [63:0] ara_req_valid_cycles;
  logic [63:0] ara_req_fire_count;
  logic [63:0] ara_req_blocked_cycles;
`ifdef FOR_VERIFY
  logic [63:0] seq_raw_hazard_cycle;
  logic [63:0] seq_war_hazard_cycle;
  logic [63:0] seq_waw_hazard_cycle;
  logic [63:0] seq_false_hazard_cycle;
  logic [63:0] seq_block_cycle;
`endif

  `else
  logic        perf_monitor;
  perf_t       perf_start_n, perf_end_n;
  logic [63:0] rvv_cycle;
  logic [63:0] rvv_lane_cycle;
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;
  logic [63:0] ara_req_valid_cycles;
  logic [63:0] ara_req_fire_count;
  logic [63:0] ara_req_blocked_cycles;
`ifdef FOR_VERIFY
  logic [63:0] seq_raw_hazard_cycle;
  logic [63:0] seq_war_hazard_cycle;
  logic [63:0] seq_waw_hazard_cycle;
  logic [63:0] seq_false_hazard_cycle;
  logic [63:0] seq_block_cycle;
`endif

  `endif
  `endif

  initial begin
    string testcase;
    if (!$test$plusargs("NO_FSDB")) begin
      $fsdbDumpfile("ara_tb.fsdb");
      $fsdbDumpvars(0, ara_tb);
      $fsdbDumpMDA(0, ara_tb);
      $fsdbDumpvars("+all");
    end

    void'($value$plusargs("TESTCASE=%s", testcase));
    
    `ifdef SAIF
    if(testcase != "") begin
        $dumpfile($sformatf("../vcd/%s.vcd", testcase));
    end else begin
        $dumpfile("../vcd/default.vcd");
    end
    $dumpvars(0, dut.i_ara_soc);
    `endif
  end

  logic [63:0] exit;

  // This TB must be implemented in C for integration with Verilator.
  // In order to Verilator to understand that the ara_testharness module is the top-level,
  // we do not instantiate it when Verilating this module.
  `ifndef VERILATOR
  ara_testharness #(
    .NrLanes     (NrLanes         ),
    .VLEN        (VLEN            ),
    .AxiAddrWidth(AxiAddrWidth    ),
    .AxiDataWidth(AxiWideDataWidth),
    .AxiRespDelay(AxiRespDelay    )
  ) dut (
    .clk_i (clk  ),
    .rst_ni(rst_n),
    .exit_o(exit )
  );
  `endif

  `ifdef TARGET_SRAM_MC 
  //`ifdef SAIF
  //localparam DRAMNumBanks=16;
  //localparam DRAMWordsPerBank=8192;
  //localparam DRAMBankSizeBytes=8192*AxiWideBeWidth;

  ///*************************
  // *  DRAM Initialization  *
  // *************************/
  //typedef logic [AxiAddrWidth-1:0] addr_t;
  //typedef logic [AxiWideDataWidth-1:0] data_t;

  //initial begin : dram_init
  //  automatic data_t mem_row;
  //  byte buffer [];
  //  addr_t address;
  //  addr_t length;
  //  string binary;
  //  addr_t word_addr;
  //  int bank_index;
  //  addr_t bank_offset;
  //  int word_index;
  //  data_t bank_data [DRAMNumBanks][DRAMWordsPerBank];

  //  for (int i = 0; i < DRAMNumBanks; i++) begin
  //      for (int j = 0; j < DRAMWordsPerBank; j++) begin
  //          bank_data[i][j] = '0;
  //      end
  //  end

  //  // tc_sram is initialized with zeros. We need to overwrite this value.
  //  repeat (2)
  //    #ClockPeriod;

  //  // Initialize memories
  //  void'($value$plusargs("PRELOAD=%s", binary));
  //  if (binary != "") begin
  //    // Read ELF
  //    read_elf(binary);
  //    $display("Loading ELF file %s", binary);
  //    while (get_section(address, length)) begin
  //      // Read sections
  //      automatic int nwords = (length + AxiWideBeWidth - 1)/AxiWideBeWidth;
  //      $display("Loading section %x of length %x", address, length);
  //      buffer = new[nwords * AxiWideBeWidth];
  //      void'(read_section(address, buffer));

  //      // Initializing memories
  //      for (int w = 0; w < nwords; w++) begin
  //        mem_row = '0;
  //        for (int b = 0; b < AxiWideBeWidth; b++) begin
  //          mem_row[8 * b +: 8] = buffer[w * AxiWideBeWidth + b];
  //        end

  //        word_addr = address + (w << AxiWideByteOffset);
  //        
  //        if (word_addr >= DRAMAddrBase && word_addr < DRAMAddrBase + (DRAMNumBanks * DRAMBankSizeBytes)) begin
  //          bank_index = (word_addr - DRAMAddrBase) / DRAMBankSizeBytes;
  //          bank_offset = (word_addr - DRAMAddrBase) % DRAMBankSizeBytes;
  //          word_index = bank_offset >> AxiWideByteOffset;
  //          
  //          if (bank_index < DRAMNumBanks && word_index < DRAMWordsPerBank) begin
  //            bank_data[bank_index][word_index] = mem_row;
  //          end else begin
  //            $display("Error: Address %x maps to invalid bank(%0d) or word(%0d)", 
  //                     word_addr, bank_index, word_index);
  //          end
  //        end else begin
  //              $display("Cannot initialize address %x, which doesn't fall into the L2 region.", word_addr);
  //        end
  //      end
  //    end

  //    for (int i = 0; i < DRAMNumBanks; i++) begin
  //      automatic string temp_file = $sformatf("temp_bank_%0d.dat", i);
  //      automatic int fd = $fopen(temp_file, "w");
  //      
  //      if (!fd) begin
  //        $error("Failed to open temporary file for bank %0d: %s", i, temp_file);
  //        $finish;
  //      end

  //      for (int w = 0; w < DRAMWordsPerBank; w++) begin
  //        $fdisplay(fd,  "%032h", bank_data[i][w]);
  //      end

  //      $fclose(fd);

  //      $display("Initializing bank %0d with file %s", i, temp_file);
  //      case (i)
  //        0:  dut.i_ara_soc.gen_dram_0__i_dram.preloadData(temp_file);
  //        1:  dut.i_ara_soc.gen_dram_1__i_dram.preloadData(temp_file);
  //        2:  dut.i_ara_soc.gen_dram_2__i_dram.preloadData(temp_file);
  //        3:  dut.i_ara_soc.gen_dram_3__i_dram.preloadData(temp_file);
  //        4:  dut.i_ara_soc.gen_dram_4__i_dram.preloadData(temp_file);
  //        5:  dut.i_ara_soc.gen_dram_5__i_dram.preloadData(temp_file);
  //        6:  dut.i_ara_soc.gen_dram_6__i_dram.preloadData(temp_file);
  //        7:  dut.i_ara_soc.gen_dram_7__i_dram.preloadData(temp_file);
  //        8:  dut.i_ara_soc.gen_dram_8__i_dram.preloadData(temp_file);
  //        9:  dut.i_ara_soc.gen_dram_9__i_dram.preloadData(temp_file);
  //        10: dut.i_ara_soc.gen_dram_10__i_dram.preloadData(temp_file);
  //        11: dut.i_ara_soc.gen_dram_11__i_dram.preloadData(temp_file);
  //        12: dut.i_ara_soc.gen_dram_12__i_dram.preloadData(temp_file);
  //        13: dut.i_ara_soc.gen_dram_13__i_dram.preloadData(temp_file);
  //        14: dut.i_ara_soc.gen_dram_14__i_dram.preloadData(temp_file);
  //        15: dut.i_ara_soc.gen_dram_15__i_dram.preloadData(temp_file);
  //        default: $display("Invalid bank index: %0d", bank_index);
  //      endcase
  //      //$system($sformatf("rm -f %s", temp_file));
  //    end

  //  end else begin
  //    $error("Expecting a firmware to run, none was provided!");
  //    $finish;
  //  end
  //end : dram_init

  //`else
  localparam DRAMNumBanks=8;
  localparam DRAMWordsPerBank=8192;
  localparam DRAMBankSizeBytes=8192*AxiWideBeWidth;

  /*************************
   *  DRAM Initialization  *
   *************************/
  typedef logic [AxiAddrWidth-1:0] addr_t;
  typedef logic [AxiWideDataWidth-1:0] data_t;

  initial begin : dram_init
    automatic data_t mem_row;
    byte buffer [];
    addr_t address;
    addr_t length;
    string binary;
    addr_t word_addr;
    int bank_index;
    addr_t bank_offset;
    int word_index;
    data_t bank_data [DRAMNumBanks][DRAMWordsPerBank];

    for (int i = 0; i < DRAMNumBanks; i++) begin
        for (int j = 0; j < DRAMWordsPerBank; j++) begin
            bank_data[i][j] = '0;
        end
    end

    // tc_sram is initialized with zeros. We need to overwrite this value.
    repeat (2)
      #ClockPeriod;

    // Initialize memories
    void'($value$plusargs("PRELOAD=%s", binary));
    if (binary != "") begin
      // Read ELF
      read_elf(binary);
      $display("Loading ELF file %s", binary);
      while (get_section(address, length)) begin
        // Read sections
        automatic int nwords = (length + AxiWideBeWidth - 1)/AxiWideBeWidth;
        $display("Loading section %x of length %x", address, length);
        buffer = new[nwords * AxiWideBeWidth];
        void'(read_section(address, buffer));

        // Initializing memories
        for (int w = 0; w < nwords; w++) begin
          mem_row = '0;
          for (int b = 0; b < AxiWideBeWidth; b++) begin
            mem_row[8 * b +: 8] = buffer[w * AxiWideBeWidth + b];
          end

          word_addr = address + (w << AxiWideByteOffset);
          
          if (word_addr >= DRAMAddrBase && word_addr < DRAMAddrBase + (DRAMNumBanks * DRAMBankSizeBytes)) begin
            bank_index = (word_addr - DRAMAddrBase) / DRAMBankSizeBytes;
            bank_offset = (word_addr - DRAMAddrBase) % DRAMBankSizeBytes;
            word_index = bank_offset >> AxiWideByteOffset;
            
            if (bank_index < DRAMNumBanks && word_index < DRAMWordsPerBank) begin
              bank_data[bank_index][word_index] = mem_row;
            end else begin
              $display("Error: Address %x maps to invalid bank(%0d) or word(%0d)", 
                       word_addr, bank_index, word_index);
            end
          end else begin
                $display("Cannot initialize address %x, which doesn't fall into the L2 region.", word_addr);
          end
        end
      end

      for (int i = 0; i < DRAMNumBanks; i++) begin
        automatic string temp_file = $sformatf("temp_bank_%0d.dat", i);
        automatic int fd = $fopen(temp_file, "w");
        
        if (!fd) begin
          $error("Failed to open temporary file for bank %0d: %s", i, temp_file);
          $finish;
        end

        for (int w = 0; w < DRAMWordsPerBank; w++) begin
          $fdisplay(fd,  "%032h", bank_data[i][w]);
        end

        $fclose(fd);

        $display("Initializing bank %0d with file %s", i, temp_file);
        case (i)
          0:  dut.i_ara_soc.gen_dram[0 ].i_dram.preloadData(temp_file);
          1:  dut.i_ara_soc.gen_dram[1 ].i_dram.preloadData(temp_file);
          2:  dut.i_ara_soc.gen_dram[2 ].i_dram.preloadData(temp_file);
          3:  dut.i_ara_soc.gen_dram[3 ].i_dram.preloadData(temp_file);
          4:  dut.i_ara_soc.gen_dram[4 ].i_dram.preloadData(temp_file);
          5:  dut.i_ara_soc.gen_dram[5 ].i_dram.preloadData(temp_file);
          6:  dut.i_ara_soc.gen_dram[6 ].i_dram.preloadData(temp_file);
          7:  dut.i_ara_soc.gen_dram[7 ].i_dram.preloadData(temp_file);
          //8:  dut.i_ara_soc.gen_dram[8 ].i_dram.preloadData(temp_file);
          //9:  dut.i_ara_soc.gen_dram[9 ].i_dram.preloadData(temp_file);
          //10: dut.i_ara_soc.gen_dram[10].i_dram.preloadData(temp_file);
          //11: dut.i_ara_soc.gen_dram[11].i_dram.preloadData(temp_file);
          //12: dut.i_ara_soc.gen_dram[12].i_dram.preloadData(temp_file);
          //13: dut.i_ara_soc.gen_dram[13].i_dram.preloadData(temp_file);
          //14: dut.i_ara_soc.gen_dram[14].i_dram.preloadData(temp_file);
          //15: dut.i_ara_soc.gen_dram[15].i_dram.preloadData(temp_file);
          default: $display("Invalid bank index: %0d", bank_index);
        endcase
        //$system($sformatf("rm -f %s", temp_file));
      end

    end else begin
      $error("Expecting a firmware to run, none was provided!");
      $finish;
    end
  end : dram_init

  //`endif
  `else
  /*************************
   *  DRAM Initialization  *
   *************************/
  typedef logic [AxiAddrWidth-1:0] addr_t;
  typedef logic [AxiWideDataWidth-1:0] data_t;

  initial begin : dram_init
    automatic data_t mem_row;
    byte buffer [];
    addr_t address;
    addr_t length;
    string binary;

    // tc_sram is initialized with zeros. We need to overwrite this value.
    repeat (2)
      #ClockPeriod;

    // Initialize memories
    void'($value$plusargs("PRELOAD=%s", binary));
    if (binary != "") begin
      // Read ELF
      read_elf(binary);
      $display("Loading ELF file %s", binary);
      while (get_section(address, length)) begin
        // Read sections
        automatic int nwords = (length + AxiWideBeWidth - 1)/AxiWideBeWidth;
        $display("Loading section %x of length %x", address, length);
        buffer = new[nwords * AxiWideBeWidth];
        void'(read_section(address, buffer));
        // Initializing memories
        for (int w = 0; w < nwords; w++) begin
          mem_row = '0;
          for (int b = 0; b < AxiWideBeWidth; b++) begin
            mem_row[8 * b +: 8] = buffer[w * AxiWideBeWidth + b];
          end
          if (address >= DRAMAddrBase && address < DRAMAddrBase + DRAMLength)
            // This requires the sections to be aligned to AxiWideByteOffset,
            // otherwise, they can be over-written.
              dut.i_ara_soc.i_dram.init_val[(address - DRAMAddrBase + (w << AxiWideByteOffset)) >> AxiWideByteOffset] = mem_row;
          else
            $display("Cannot initialize address %x, which doesn't fall into the L2 region.", address);
        end
      end
    end else begin
      $error("Expecting a firmware to run, none was provided!");
      $finish;
    end
  end : dram_init
  `endif


`ifndef TARGET_GATESIM

  /*************************
   *  PRINT STORED VALUES  *
   *************************/

  // This is useful to check that the ideal dispatcher simulation was correct

`ifndef IDEAL_DISPATCHER
  localparam OutResultFile = "../gold_results.txt";
`else
  localparam OutResultFile = "../id_results.txt";
`endif

  int fd;

  data_t                     ara_w;
  logic [AxiWideBeWidth-1:0] ara_w_strb;
  logic                      ara_w_valid;
  logic                      ara_w_ready;

  // Avoid dumping what it's not measured, e.g. cache warming
  logic dump_en_mask;

  initial begin
    fd = $fopen(OutResultFile, "w");
    $display("Dump results on %s", OutResultFile);
  end

  `ifdef SAIF 
  assign ara_w       = dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.axi_w_o[145:18];
  assign ara_w_strb  = dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.axi_w_o[17:2];
  assign ara_w_valid = dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.axi_w_valid_o;
  assign ara_w_ready = dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.axi_w_ready_i;
  `else
  assign ara_w       = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w.data;
  assign ara_w_strb  = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w.strb;
  assign ara_w_valid = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w_valid;
  assign ara_w_ready = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.w_ready;
  `endif

`ifndef IDEAL_DISPATCHER
  assign dump_en_mask = dut.i_ara_soc.hw_cnt_en_o[0];
`else
  // Ideal-Dispatcher system does not warm the scalar cache
  assign dump_en_mask = 1'b1;
`endif
  always_ff @(posedge clk)
    if (dump_en_mask)
      if (ara_w_valid && ara_w_ready)
        for (int b = 0; b < AxiWideBeWidth; b++)
          if (ara_w_strb[b])
            $fdisplay(fd, "%0x", ara_w[b*8 +: 8]);

`endif

  /*********
   *  EOC  *
   *********/

  always @(posedge clk) begin
    if (exit[0]) begin
      if (exit >> 1) begin
        $warning("Core Test ", $sformatf("*** FAILED *** (tohost = %0d)", (exit >> 1)));
      end else begin
        // Print vector HW runtime
`ifndef TARGET_GATESIM
        $display("[hw-cycles]: %d", int'(dut.runtime_buf_q));
        $display("[cva6-d$-stalls]: %d", int'(dut.dcache_stall_buf_q));
        $display("[cva6-i$-stalls]: %d", int'(dut.icache_stall_buf_q));
        $display("[cva6-sb-full]: %d", int'(dut.sb_full_buf_q));
`endif
        $info("Core Test ", $sformatf("*** SUCCESS *** (tohost = %0d)", (exit >> 1)));
      end

`ifndef TARGET_GATESIM
      $fclose(fd);
`endif

`ifdef SAIF
   $dumpoff;
   $dumpflush;
`endif
      $finish(exit >> 1);
    end
  end

// Dump VCD with a SW trigger
`ifdef VCD_DUMP

  /****************
  *  VCD DUMPING  *
  ****************/

`ifdef VCD_PATH
  string vcd_path = `STRINGIFY(`VCD_PATH);
`else
  string vcd_path = "../vcd/last_sim.vcd";
`endif

  localparam logic [63:0] VCD_TRIGGER_ON  = 64'h0000_0000_0000_0001;
  localparam logic [63:0] VCD_TRIGGER_OFF = 64'hFFFF_FFFF_FFFF_FFFF;

  event start_dump_event;
  event stop_dump_event;

  logic [63:0] event_trigger_reg;
  logic        dumping = 1'b0;

  assign event_trigger_reg =
           dut.i_ara_soc.i_ctrl_registers.event_trigger_o;

  initial begin
    $display("VCD_DUMP successfully defined\n");
  end

  always_ff @(posedge clk) begin
    if(event_trigger_reg == VCD_TRIGGER_ON && !dumping) begin
       $display("[TB - VCD] START DUMPING\n");
       -> start_dump_event;
       dumping = 1'b1;
    end
    if(event_trigger_reg == VCD_TRIGGER_OFF) begin
       -> stop_dump_event;
       $display("[TB - VCD] STOP DUMPING\n");
    end
  end

  initial begin
    @(start_dump_event);
    $vcdplusfile(vcd_path);
    $vcdpluson(0, dut.i_ara_soc);

    #1 $display("[TB - VCD] DUMPING...\n");

    @(stop_dump_event)
    $vcdplusclose;
    $finish;
  end

`endif


`ifndef SAIF
`ifndef IDEAL_DISPATCHER
 /***************************
  *  VRF PERFMENCE MONITOR  *
  ***************************/
  for(genvar i = 0; i < NrLanes; i++) begin: vrf_perf_monitor
    vrf_perf_monitor u_vrf_perf_monitor(
      .clk_i           (clk),
      .rst_ni          (rst_n),
      .lane_operand_req(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_operand_requester.lane_operand_req),
      .ext_operand_req (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_operand_requester.ext_operand_req)
    );
  end
`else
 /***************************
  *  VRF PERFMENCE MONITOR  *
  ***************************/
  for(genvar i = 0; i < NrLanes; i++) begin: vrf_perf_monitor
    vrf_perf_monitor u_vrf_perf_monitor(
      .clk_i           (clk),
      .rst_ni          (rst_n),
      .lane_operand_req(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_operand_requester.lane_operand_req),
      .ext_operand_req (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_operand_requester.ext_operand_req)
    );
  end
`endif
`endif


`ifndef SAIF
`ifndef IDEAL_DISPATCHER
 /**********************
  *  PERFMENCE MONITOR  *
  ***********************/
  logic rvv_lane_en,rvv_load_en,rvv_store_en;

  always_comb begin
    rvv_lane_en = (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[0]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[1]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[2]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[3]);
    rvv_load_en = |ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[4];
    rvv_store_en = |ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[5];
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_cycle <= '0;
    end
    else if(!ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_idle_o) begin
      rvv_cycle <= rvv_cycle + 1;
    end
    else begin
      rvv_cycle <= rvv_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_lane_cycle <= '0;
    end
    else if(rvv_lane_en) begin
      rvv_lane_cycle <= rvv_lane_cycle + 1;
    end
    else begin
      rvv_lane_cycle <= rvv_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_mem_only_cycle <= '0;
    end
    else if((rvv_load_en || rvv_store_en) && !rvv_lane_en) begin
      rvv_mem_only_cycle <= rvv_mem_only_cycle + 1;
    end
    else begin
      rvv_mem_only_cycle <= rvv_mem_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_mem_lane_cycle <= '0;
    end
    else if((rvv_load_en || rvv_store_en) && rvv_lane_en) begin
      rvv_mem_lane_cycle <= rvv_mem_lane_cycle + 1;
    end
    else begin
      rvv_mem_lane_cycle <= rvv_mem_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_load_only_cycle <= '0;
    end
    else if(rvv_load_en && !rvv_lane_en) begin
      rvv_load_only_cycle <= rvv_load_only_cycle + 1;
    end
    else begin
      rvv_load_only_cycle <= rvv_load_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_load_lane_cycle <= '0;
    end
    else if(rvv_load_en && rvv_lane_en) begin
      rvv_load_lane_cycle <= rvv_load_lane_cycle + 1;
    end
    else begin
      rvv_load_lane_cycle <= rvv_load_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_store_only_cycle <= '0;
    end
    else if(rvv_store_en && !rvv_lane_en) begin
      rvv_store_only_cycle <= rvv_store_only_cycle + 1;
    end
    else begin
      rvv_store_only_cycle <= rvv_store_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_store_lane_cycle <= '0;
    end
    else if(rvv_store_en && rvv_lane_en) begin
      rvv_store_lane_cycle <= rvv_store_lane_cycle + 1;
    end
    else begin
      rvv_store_lane_cycle <= rvv_store_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      ara_req_valid_cycles   <= '0;
      ara_req_fire_count     <= '0;
      ara_req_blocked_cycles <= '0;
    end
    else begin
      ara_req_valid_cycles   <= ara_req_valid_cycles +
        ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid;
      ara_req_fire_count     <= ara_req_fire_count +
        (ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
         ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready);
      ara_req_blocked_cycles <= ara_req_blocked_cycles +
        (ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
         !ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready);
    end
  end

`ifdef FOR_VERIFY
  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      seq_raw_hazard_cycle   <= '0;
      seq_war_hazard_cycle   <= '0;
      seq_waw_hazard_cycle   <= '0;
      seq_false_hazard_cycle <= '0;
      seq_block_cycle        <= '0;
    end
    else begin
      seq_raw_hazard_cycle   <= seq_raw_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.raw_hazard;
      seq_war_hazard_cycle   <= seq_war_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.war_hazard;
      seq_waw_hazard_cycle   <= seq_waw_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.waw_hazard;
      seq_false_hazard_cycle <= seq_false_hazard_cycle + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.false_hazard;
      seq_block_cycle        <= seq_block_cycle        + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.sequencer_block;
    end
  end
`endif

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_instret  <= '0;
      rvv_op       <= '0;
      rvv_op_fs1   <= '0;
      rvv_op_fd    <= '0;
      rvv_op_load  <= '0;
      rvv_op_store <= '0;
    end
    else begin
      if (|ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1:0]) begin
        rvv_instret  <= rvv_instret + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].fu == 4'b1010)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].fu == 4'b1010));
        rvv_op       <= rvv_op       + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10110110)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10110110));
        rvv_op_fs1   <= rvv_op_fs1   + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10110111)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10110111));
        rvv_op_fd    <= rvv_op_fd    + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111000)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111000));
        rvv_op_load  <= rvv_op_load  + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111001)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111001));
        rvv_op_store <= rvv_op_store + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111010)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111010));
      end
      else begin
        rvv_instret  <= rvv_instret;
        rvv_op       <= rvv_op      ;
        rvv_op_fs1   <= rvv_op_fs1  ;
        rvv_op_fd    <= rvv_op_fd   ;
        rvv_op_load  <= rvv_op_load ;
        rvv_op_store <= rvv_op_store;
      end
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_axi_aw_count <= '0;
      rvv_axi_w_count  <= '0;
      rvv_axi_b_count  <= '0;
      rvv_axi_ar_count <= '0;
      rvv_axi_r_count  <= '0;
    end
    else begin
      rvv_axi_aw_count <= rvv_axi_aw_count + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.aw_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.aw_ready);
      rvv_axi_w_count  <= rvv_axi_w_count  + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.w_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.w_ready);
      rvv_axi_b_count  <= rvv_axi_b_count  + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.b_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.b_ready);
      rvv_axi_ar_count <= rvv_axi_ar_count + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.ar_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.ar_ready);
      rvv_axi_r_count  <= rvv_axi_r_count  + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.r_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.r_ready);
    end
  end

  always_comb begin
    perf_time_n = perf_time_q;
    if(ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_csr_o &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.csr_addr_i[11:0] == 12'hc00 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.csr_op_o[7:0] == 8'b100010 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.waddr_o[0][4:0] == 5'h0 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.we_gpr_o[0]) begin
      perf_time_n = !perf_time_q;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      perf_time_q  <= '0;
      perf_start_q <= '{default: '0};
      perf_end_q   <= '{default: '0};
`ifdef FOR_VERIFY
      perf_watchdog_count   <= '0;
      perf_watchdog_pending <= 1'b0;
`endif
    end
    else begin
      perf_time_q  <= perf_time_n ;
      perf_start_q <= perf_start_n;
      perf_end_q   <= perf_end_n  ;
`ifdef FOR_VERIFY
      if (!perf_time_q && perf_time_n)
        perf_watchdog_count <= '0;
      else if (perf_time_q && perf_watchdog_limit != 0 &&
               !perf_watchdog_pending) begin
        if (perf_watchdog_count + 1 >= perf_watchdog_limit) begin
          // Freeze a coherent end snapshot.  The reporting block consumes it
          // on the following clock, after the NBA update reaches perf_end_q.
          perf_end_q <= get_perf_counters();
          perf_watchdog_pending <= 1'b1;
        end else begin
          perf_watchdog_count <= perf_watchdog_count + 1;
        end
      end
`endif
    end
  end

`ifdef FOR_VERIFY
  initial begin
    perf_watchdog_limit = '0;
    void'($value$plusargs("PERF_WATCHDOG_CYCLES=%d", perf_watchdog_limit));
  end

  always_ff @(posedge clk) begin : p_perf_watchdog_report
    if (perf_watchdog_pending) begin
      automatic string testcase;
      automatic int watchdog_file;
      automatic int unsigned inflight_count = 0;
      void'($value$plusargs("TESTCASE=%s", testcase));

      $display("[PERF] watchdog_timeout: 1");
      $display("[PERF] watchdog_limit_cycles: %0d", perf_watchdog_limit);
      $display("[PERF] watchdog_observed_cycles: %0d", perf_watchdog_count + 1);
      $display("[PERF] watchdog_dispatcher_state: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q);
      $display("[PERF] watchdog_sequencer_raw_hazard: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.raw_hazard);
      $display("[PERF] watchdog_sequencer_war_hazard: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.war_hazard);
      $display("[PERF] watchdog_sequencer_waw_hazard: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.waw_hazard);
      $display("[PERF] watchdog_sequencer_block: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.sequencer_block);
      $display("[PERF] watchdog_vlsu_addrgen_state: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.state_q);
      $display("[PERF] watchdog_vlsu_axi_addrgen_state: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_state_q);
      $display("[PERF] watchdog_vlsu_idx_spill_valid: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_vaddr_valid_q);
      $display("[PERF] watchdog_vlsu_idx_spill_ready: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_vaddr_ready_d);
      $display("[PERF] watchdog_vlsu_addr_queue_empty: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_empty);
      $display("[PERF] watchdog_vlsu_addr_queue_full: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_queue_full);
      $display("[PERF] watchdog_vlsu_ar_ready: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_ar_ready_i);
      $display("[PERF] watchdog_vlsu_ldu_addr_ready: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.ldu_axi_addrgen_req_ready_i);
      $display("[PERF] watchdog_vlsu_remaining_bytes: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_q.len);
      $display("[PERF] watchdog_vlsu_index_vaddr: 0x%0h",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.idx_final_vaddr_q);
      $display("[PERF] watchdog_vlsu_data_vew: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.axi_addrgen_q.vew);
      $display("[PERF] watchdog_vlsu_translation_enabled: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.en_ld_st_translation_i);
      $display("[PERF] watchdog_vlsu_mmu_valid: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_addrgen.mmu_valid_i);
      $display("[PERF] watchdog_mask_issue_cnt: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.issue_cnt_q);
      $display("[PERF] watchdog_mask_commit_cnt: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.commit_cnt_q);
      $display("[PERF] watchdog_mask_vcompress_issue_end: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.vcompress_issue_end_q);
      $display("[PERF] watchdog_mask_result_queue_count: %0d",
        ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.result_queue_cnt_q);
      for (int unsigned lane = 0; lane < NrLanes; lane++) begin
        $display("[PERF] watchdog_div_lane_%0d_issue_state: %0d", lane,
          watchdog_div_issue_state[lane]);
        $display("[PERF] watchdog_div_lane_%0d_commit_state: %0d", lane,
          watchdog_div_commit_state[lane]);
        $display("[PERF] watchdog_div_lane_%0d_operand_a: 0x%0h", lane,
          watchdog_div_operand_a[lane]);
        $display("[PERF] watchdog_div_lane_%0d_operand_b: 0x%0h", lane,
          watchdog_div_operand_b[lane]);
        $display("[PERF] watchdog_div_lane_%0d_serdiv_state: %0d", lane,
          watchdog_div_serdiv_state[lane]);
        $display("[PERF] watchdog_div_lane_%0d_serdiv_count: %0d", lane,
          watchdog_div_serdiv_count[lane]);
      end
      for (int unsigned id = 0; id < NrVInsn; id++) begin
        if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q[id]) begin
          inflight_count++;
          $display("[PERF] watchdog_inflight_id_%0d_opcode: %s", id,
            exec_op_by_id_q[id].name());
        end
      end
      $display("[PERF] watchdog_inflight_count: %0d", inflight_count);

      // Emit the normal full report from the frozen snapshot first, then add
      // timeout metadata to the same per-testcase log for offline analyzers.
      print_perf_report();
      watchdog_file = $fopen($sformatf("perf_report_%s.log", testcase), "a");
      if (watchdog_file != 0) begin
        $fwrite(watchdog_file, "[PERF] watchdog_timeout: 1\n");
        $fwrite(watchdog_file, "[PERF] watchdog_limit_cycles: %0d\n",
          perf_watchdog_limit);
        $fwrite(watchdog_file, "[PERF] watchdog_observed_cycles: %0d\n",
          perf_watchdog_count + 1);
        $fwrite(watchdog_file, "[PERF] watchdog_dispatcher_state: %0d\n",
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher.state_q);
        $fwrite(watchdog_file, "[PERF] watchdog_sequencer_raw_hazard: %0d\n",
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.raw_hazard);
        $fwrite(watchdog_file, "[PERF] watchdog_sequencer_war_hazard: %0d\n",
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.war_hazard);
        $fwrite(watchdog_file, "[PERF] watchdog_sequencer_waw_hazard: %0d\n",
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.waw_hazard);
        $fwrite(watchdog_file, "[PERF] watchdog_sequencer_block: %0d\n",
          ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.sequencer_block);
        $fwrite(watchdog_file, "[PERF] watchdog_inflight_count: %0d\n",
          inflight_count);
        for (int unsigned id = 0; id < NrVInsn; id++) begin
          if (ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q[id])
            $fwrite(watchdog_file, "[PERF] watchdog_inflight_id_%0d_opcode: %s\n",
              id, exec_op_by_id_q[id].name());
        end
        $fclose(watchdog_file);
      end
      $finish(124);
    end
  end
`endif

  always_comb begin
    perf_start_n = perf_start_q;
    perf_end_n = perf_end_q;

    if(!perf_time_q && perf_time_n) begin
      perf_start_n = get_perf_counters();
    end
    if(perf_time_q && !perf_time_n) begin
      perf_end_n = get_perf_counters();
    end
  end

  always_ff @(posedge clk) begin
    if(perf_time_q && !perf_time_n) begin
      print_perf_report();
    end
  end

`else
 /**********************
  *  PERFMENCE MONITOR  *
  ***********************/
  logic rvv_lane_en,rvv_load_en,rvv_store_en;

  always_comb begin
    rvv_lane_en = (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[0]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[1]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[2]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[3]);
    rvv_load_en = |ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[4];
    rvv_store_en = |ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[5];
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_cycle <= '0;
    end
    else if(perf_monitor) begin
      rvv_cycle <= rvv_cycle + 1;
    end
    else begin
      rvv_cycle <= rvv_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_lane_cycle <= '0;
    end
    else if(rvv_lane_en) begin
      rvv_lane_cycle <= rvv_lane_cycle + 1;
    end
    else begin
      rvv_lane_cycle <= rvv_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_mem_only_cycle <= '0;
    end
    else if((rvv_load_en || rvv_store_en) && !rvv_lane_en) begin
      rvv_mem_only_cycle <= rvv_mem_only_cycle + 1;
    end
    else begin
      rvv_mem_only_cycle <= rvv_mem_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_mem_lane_cycle <= '0;
    end
    else if((rvv_load_en || rvv_store_en) && rvv_lane_en) begin
      rvv_mem_lane_cycle <= rvv_mem_lane_cycle + 1;
    end
    else begin
      rvv_mem_lane_cycle <= rvv_mem_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_load_only_cycle <= '0;
    end
    else if(rvv_load_en && !rvv_lane_en) begin
      rvv_load_only_cycle <= rvv_load_only_cycle + 1;
    end
    else begin
      rvv_load_only_cycle <= rvv_load_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_load_lane_cycle <= '0;
    end
    else if(rvv_load_en && rvv_lane_en) begin
      rvv_load_lane_cycle <= rvv_load_lane_cycle + 1;
    end
    else begin
      rvv_load_lane_cycle <= rvv_load_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_store_only_cycle <= '0;
    end
    else if(rvv_store_en && !rvv_lane_en) begin
      rvv_store_only_cycle <= rvv_store_only_cycle + 1;
    end
    else begin
      rvv_store_only_cycle <= rvv_store_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_store_lane_cycle <= '0;
    end
    else if(rvv_store_en && rvv_lane_en) begin
      rvv_store_lane_cycle <= rvv_store_lane_cycle + 1;
    end
    else begin
      rvv_store_lane_cycle <= rvv_store_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      ara_req_valid_cycles   <= '0;
      ara_req_fire_count     <= '0;
      ara_req_blocked_cycles <= '0;
    end
    else begin
      ara_req_valid_cycles   <= ara_req_valid_cycles +
        ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid;
      ara_req_fire_count     <= ara_req_fire_count +
        (ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
         ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready);
      ara_req_blocked_cycles <= ara_req_blocked_cycles +
        (ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
         !ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready);
    end
  end

`ifdef FOR_VERIFY
  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      seq_raw_hazard_cycle   <= '0;
      seq_war_hazard_cycle   <= '0;
      seq_waw_hazard_cycle   <= '0;
      seq_false_hazard_cycle <= '0;
      seq_block_cycle        <= '0;
    end
    else begin
      seq_raw_hazard_cycle   <= seq_raw_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.raw_hazard;
      seq_war_hazard_cycle   <= seq_war_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.war_hazard;
      seq_waw_hazard_cycle   <= seq_waw_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.waw_hazard;
      seq_false_hazard_cycle <= seq_false_hazard_cycle + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.false_hazard;
      seq_block_cycle        <= seq_block_cycle        + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.sequencer_block;
    end
  end
`endif

  initial begin
    #15.5;
    perf_start_n = get_perf_counters();
    perf_monitor = 1'b1;
  end

  final begin
    perf_end_n = get_perf_counters();
    print_perf_report();
    print_perf_csv();
  end

`endif
`endif

endmodule : ara_tb
