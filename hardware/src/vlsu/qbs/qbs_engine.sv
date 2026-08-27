// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Command-level controller for the QBS v1 execution path. All descriptor,
// activation, and weight traffic shares one translated AXI read engine. The
// compute engine accumulates into hidden state; architectural VRF writes start
// only after every command read and all arithmetic have completed without a
// fault.
module qbs_engine
  import qbs_pkg::*;
  import fpnew_pkg::*;
#(
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
    input  vid_t                         command_id_i,
    input  logic [4:0]                   command_vd_i,
    input  logic [2:0]                   command_m_i,
    input  logic [VAddrWidth-1:0]        command_descriptor_address_i,
    input  logic [VAddrWidth-1:0]        command_activation_base_i,
    input  axi_pkg::cache_t              command_cache_i,
    input  axi_pkg::prot_t               command_prot_i,

    output logic                         success_valid_o,
    output logic                         fault_valid_o,
    input  logic                         terminal_ready_i,
    output logic [4:0]                   result_fflags_o,
    output logic                         fault_is_validation_o,
    output qbs_validation_error_e        validation_error_o,
    output qbs_read_fault_e              read_fault_kind_o,
    output logic [VAddrWidth-1:0]        fault_vaddr_o,
    output exception_t                   fault_mmu_exception_o,

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
    output logic [31:0]                  read_range_count_o,
    output logic [31:0]                  read_translation_count_o,
    output logic [31:0]                  read_ar_count_o,
    output logic [31:0]                  read_beat_count_o,
    output logic [31:0]                  read_payload_bytes_o,
    output logic [31:0]                  read_store_wait_cycles_o,
    output logic [31:0]                  read_backpressure_cycles_o,
    output logic [31:0]                  read_outstanding_occupancy_sum_o,
    output logic [1:0]                   read_outstanding_max_o,
    output logic [31:0]                  read_outstanding_full_cycles_o,
    output logic [31:0]                  phase_setup_cycles_o,
    output logic [31:0]                  phase_activation_cycles_o,
    output logic [31:0]                  phase_weight_cycles_o,
    output logic [31:0]                  phase_compute_cycles_o,
    output logic [31:0]                  phase_overlap_cycles_o,
    output logic [31:0]                  phase_drain_cycles_o,
    output logic [31:0]                  phase_scheduler_cycles_o,
    output logic [31:0]                  phase_commit_cycles_o,
    output logic [31:0]                  phase_fault_cycles_o,
    output logic [31:0]                  phase_terminal_cycles_o,
    output logic [31:0]                  weight_prefetch_wait_cycles_o,
    output logic [31:0]                  tiles_computed_o,
    output logic [31:0]                  weight_bytes_o,
    output logic [31:0]                  activation_bytes_o,
    output logic [31:0]                  useful_pairs_o,
    output logic [31:0]                  pair_capacity_o,
    output logic [31:0]                  dot_active_cycles_o,
    output logic [31:0]                  fp_uop_issue_o,
    output logic [31:0]                  fp_table_occupancy_sum_o,
    output logic [4:0]                   fp_table_occupancy_max_o,
    output logic [31:0]                  fp_table_full_cycles_o,
    output logic [31:0]                  accumulator_updates_o,
    output logic [31:0]                  commit_word_count_o,
    output logic [31:0]                  commit_backpressure_cycles_o
  );

  localparam int unsigned RangeBytesWidth = 16;

  typedef enum logic [1:0] {
    QBS_RANGE_DESCRIPTOR,
    QBS_RANGE_ACTIVATION,
    QBS_RANGE_WEIGHT,
    QBS_RANGE_RESERVED
  } qbs_range_role_e;

  typedef struct packed {
    qbs_range_role_e role;
    logic [1:0]      target;
    logic            weight_bank;
    logic [2:0]      weight_row_count;
  } qbs_range_tag_t;

  typedef enum logic [3:0] {
    QBS_ENGINE_IDLE,
    QBS_ENGINE_DESCRIPTOR_REQUEST,
    QBS_ENGINE_DESCRIPTOR_WAIT,
    QBS_ENGINE_VALIDATE,
    QBS_ENGINE_COMPUTE_START,
    QBS_ENGINE_RUN,
    QBS_ENGINE_COMPUTE_FAULT_DRAIN,
    QBS_ENGINE_COMMIT,
    QBS_ENGINE_SUCCESS,
    QBS_ENGINE_FAULT
  } qbs_engine_state_e;

  typedef enum logic [3:0] {
    QBS_PHASE_NONE,
    QBS_PHASE_SETUP,
    QBS_PHASE_ACTIVATION,
    QBS_PHASE_WEIGHT,
    QBS_PHASE_COMPUTE,
    QBS_PHASE_OVERLAP,
    QBS_PHASE_DRAIN,
    QBS_PHASE_SCHEDULER,
    QBS_PHASE_COMMIT,
    QBS_PHASE_FAULT,
    QBS_PHASE_TERMINAL
  } qbs_phase_e;

  qbs_engine_state_e state_d, state_q;

  vid_t id_q;
  logic [4:0] vd_q;
  logic [2:0] m_q;
  logic [VAddrWidth-1:0] descriptor_address_q;
  logic [VAddrWidth-1:0] activation_base_q;
  axi_pkg::cache_t cache_q;
  axi_pkg::prot_t prot_q;

  logic [127:0] descriptor_q;
  logic [15:0] descriptor_byte_valid_q;

  logic descriptor_valid;
  qbs_validation_error_e descriptor_error;
  qbs_weight_profile_e descriptor_weight_profile;
  qbs_activation_profile_e descriptor_activation_profile;
  qbs_weight_layout_e descriptor_weight_layout;
  qbs_activation_layout_e descriptor_activation_layout;
  logic [5:0] descriptor_n;
  logic [8:0] descriptor_k_blocks;
  logic [15:0] descriptor_weight_block_bytes;
  logic [15:0] descriptor_activation_block_bytes;
  logic [63:0] descriptor_weight_storage_bytes;
  logic [63:0] descriptor_activation_storage_bytes;
  logic [63:0] descriptor_weight_last_address;
  logic [63:0] descriptor_activation_last_address;

  qbs_weight_profile_e weight_profile_q;
  qbs_activation_profile_e activation_profile_q;
  qbs_weight_layout_e weight_layout_q;
  qbs_activation_layout_e activation_layout_q;
  logic [5:0] n_q;
  logic [8:0] k_blocks_q;
  logic [15:0] weight_block_bytes_q;
  logic [15:0] activation_block_bytes_q;
  logic [63:0] weight_base_q;

  logic [7:0] scheduler_k_q;
  logic [5:0] scheduler_row_base_q;
  logic [2:0] activation_range_index_q;
  logic [2:0] weight_range_index_q;
  logic [7:0] weight_issue_k_q;
  logic [5:0] weight_issue_row_base_q;
  logic       weight_issue_bank_q;
  logic [1:0] weight_ranges_pending_q;

  logic read_range_valid;
  logic read_range_ready;
  logic [VAddrWidth-1:0] read_range_vaddr;
  logic [RangeBytesWidth-1:0] read_range_bytes;
  qbs_range_tag_t read_range_tag;
  logic read_data_valid;
  logic read_data_ready;
  logic [AxiDataWidth-1:0] read_data;
  logic [AxiDataWidth/8-1:0] read_data_strb;
  logic [RangeBytesWidth-1:0] read_data_offset;
  qbs_range_tag_t read_data_tag;
  logic read_completion_valid;
  logic read_completion_ready;
  qbs_range_tag_t read_completion_tag;
  logic read_fault_valid;
  logic read_fault_ready;
  qbs_read_fault_e read_fault_kind;
  logic [VAddrWidth-1:0] read_fault_vaddr;
  qbs_range_tag_t read_fault_tag;
  exception_t read_fault_mmu_exception;
  logic read_busy;

  logic compute_command_valid;
  logic compute_command_ready;
  logic compute_fault;
  logic compute_fault_done;
  logic compute_weight_write_valid;
  logic compute_weight_write_ready;
  logic compute_weight_write_group;
  logic compute_activation_write_valid;
  logic compute_activation_write_ready;
  logic [7:0] compute_expected_k;
  logic [5:0] compute_expected_row_base;
  logic [2:0] compute_expected_row_count;
  logic compute_expected_weight_bank;
  logic compute_activation_needed;
  logic compute_weight_needed;
  logic compute_result_valid;
  logic compute_result_consumed;
  logic [3:0] compute_result_bank_row;
  logic [7:0] compute_result_bank_valid;
  logic [31:0] compute_result_bank_data [8];
  logic [4:0] compute_result_fflags;
  logic compute_busy;
  logic compute_phase_activation;
  logic compute_phase_weight;
  logic compute_phase_compute;
  logic compute_phase_drain;
  logic [31:0] compute_weight_prefetch_wait_cycles;
  logic compute_counters_valid_q;
  logic [31:0] compute_tiles_computed;
  logic [31:0] compute_weight_bytes;
  logic [31:0] compute_activation_bytes;
  logic [31:0] compute_useful_pairs;
  logic [31:0] compute_pair_capacity;
  logic [31:0] compute_dot_active_cycles;
  logic [31:0] compute_fp_uop_issue;
  logic [31:0] compute_fp_table_occupancy_sum;
  logic [4:0] compute_fp_table_occupancy_max;
  logic [31:0] compute_fp_table_full_cycles;
  logic [31:0] compute_accumulator_updates;

  logic commit_start_valid;
  logic commit_start_ready;
  logic commit_done_valid;
  logic commit_done_ready;
  logic commit_busy;
  logic commit_counters_valid_q;
  logic [31:0] commit_word_count;
  logic [31:0] commit_backpressure_cycles;

  logic fault_is_validation_d, fault_is_validation_q;
  qbs_validation_error_e validation_error_d, validation_error_q;
  qbs_read_fault_e read_fault_kind_d, read_fault_kind_q;
  logic [VAddrWidth-1:0] fault_vaddr_d, fault_vaddr_q;
  exception_t fault_mmu_exception_d, fault_mmu_exception_q;
  logic [4:0] result_fflags_d, result_fflags_q;

  qbs_phase_e command_phase;
  logic [31:0] phase_setup_cycles_q;
  logic [31:0] phase_activation_cycles_q;
  logic [31:0] phase_weight_cycles_q;
  logic [31:0] phase_compute_cycles_q;
  logic [31:0] phase_overlap_cycles_q;
  logic [31:0] phase_drain_cycles_q;
  logic [31:0] phase_scheduler_cycles_q;
  logic [31:0] phase_commit_cycles_q;
  logic [31:0] phase_fault_cycles_q;
  logic [31:0] phase_terminal_cycles_q;

`ifndef SYNTHESIS
  logic [31:0] probe_weight_wait_no_outstanding_cycles_q;
  logic [31:0] probe_weight_wait_response_idle_cycles_q;
  logic [31:0] probe_weight_wait_r_transfer_cycles_q;
  logic [31:0] probe_weight_wait_r_blocked_cycles_q;
  logic        probe_root_trace_active_q;
  logic        probe_root_trace_done_q;
  logic [7:0]  probe_root_trace_cycle_q;
`endif

  logic command_fire;
  logic read_range_fire;
  logic read_data_fire;
  logic read_completion_fire;
  logic read_fault_fire;
  logic scheduler_tuple_current;
  logic [2:0] activation_range_count;
  logic [2:0] weight_range_count;
  logic weight_lookahead_enabled;
  logic weight_issue_cursor_current;
  logic [2:0] weight_issue_row_count;
  logic lookahead_weight_range_fire;
  logic lookahead_weight_completion_fire;

  assign command_ready_o = state_q == QBS_ENGINE_IDLE;
  assign command_fire = command_valid_i && command_ready_o;
  assign busy_o = state_q != QBS_ENGINE_IDLE;
  assign success_valid_o = state_q == QBS_ENGINE_SUCCESS;
  assign fault_valid_o = state_q == QBS_ENGINE_FAULT;
  assign result_fflags_o = result_fflags_q;
  assign fault_is_validation_o = fault_is_validation_q;
  assign validation_error_o = validation_error_q;
  assign read_fault_kind_o = read_fault_kind_q;
  assign fault_vaddr_o = fault_vaddr_q;
  assign fault_mmu_exception_o = fault_mmu_exception_q;
  assign weight_prefetch_wait_cycles_o = compute_counters_valid_q
      ? compute_weight_prefetch_wait_cycles : '0;

  // Decode-style M=1 R4 commands can keep one current and one future tile in
  // flight. Larger M values retain the demand-coupled scheduler because their
  // compute interval is long enough for a third response to reach an active
  // bank before it is safe to overwrite.
  assign weight_lookahead_enabled = m_q == 3'd1 &&
      weight_layout_q == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR;
  assign weight_issue_cursor_current =
      weight_issue_k_q == compute_expected_k;

  always_comb begin
    automatic int unsigned remaining_rows;
    weight_issue_row_count = '0;
    if (unsigned'(weight_issue_row_base_q) < unsigned'(n_q)) begin
      remaining_rows = unsigned'(n_q) -
                       unsigned'(weight_issue_row_base_q);
      weight_issue_row_count = remaining_rows >= 4
          ? 3'd4 : 3'(remaining_rows);
    end
  end

  always_comb begin
    command_phase = QBS_PHASE_NONE;
    unique case (state_q)
      QBS_ENGINE_DESCRIPTOR_REQUEST,
      QBS_ENGINE_DESCRIPTOR_WAIT,
      QBS_ENGINE_VALIDATE,
      QBS_ENGINE_COMPUTE_START: command_phase = QBS_PHASE_SETUP;
      QBS_ENGINE_RUN: begin
        if (compute_phase_activation)
          command_phase = QBS_PHASE_ACTIVATION;
        else if (compute_phase_weight)
          command_phase = QBS_PHASE_WEIGHT;
        else if (compute_phase_compute) begin
          if (read_busy ||
              (read_range_valid &&
               read_range_tag.role == QBS_RANGE_WEIGHT))
            command_phase = QBS_PHASE_OVERLAP;
          else
            command_phase = QBS_PHASE_COMPUTE;
        end else if (compute_phase_drain)
          command_phase = QBS_PHASE_DRAIN;
        else
          command_phase = QBS_PHASE_SCHEDULER;
      end
      QBS_ENGINE_COMPUTE_FAULT_DRAIN: command_phase = QBS_PHASE_FAULT;
      QBS_ENGINE_COMMIT: command_phase = QBS_PHASE_COMMIT;
      QBS_ENGINE_SUCCESS,
      QBS_ENGINE_FAULT: command_phase = QBS_PHASE_TERMINAL;
      default: ;
    endcase
  end

  assign phase_setup_cycles_o = phase_setup_cycles_q +
      (command_phase == QBS_PHASE_SETUP ? 32'd1 : 32'd0);
  assign phase_activation_cycles_o = phase_activation_cycles_q +
      (command_phase == QBS_PHASE_ACTIVATION ? 32'd1 : 32'd0);
  assign phase_weight_cycles_o = phase_weight_cycles_q +
      (command_phase == QBS_PHASE_WEIGHT ? 32'd1 : 32'd0);
  assign phase_compute_cycles_o = phase_compute_cycles_q +
      (command_phase == QBS_PHASE_COMPUTE ? 32'd1 : 32'd0);
  assign phase_overlap_cycles_o = phase_overlap_cycles_q +
      (command_phase == QBS_PHASE_OVERLAP ? 32'd1 : 32'd0);
  assign phase_drain_cycles_o = phase_drain_cycles_q +
      (command_phase == QBS_PHASE_DRAIN ? 32'd1 : 32'd0);
  assign phase_scheduler_cycles_o = phase_scheduler_cycles_q +
      (command_phase == QBS_PHASE_SCHEDULER ? 32'd1 : 32'd0);
  assign phase_commit_cycles_o = phase_commit_cycles_q +
      (command_phase == QBS_PHASE_COMMIT ? 32'd1 : 32'd0);
  assign phase_fault_cycles_o = phase_fault_cycles_q +
      (command_phase == QBS_PHASE_FAULT ? 32'd1 : 32'd0);
  assign phase_terminal_cycles_o = phase_terminal_cycles_q +
      (command_phase == QBS_PHASE_TERMINAL ? 32'd1 : 32'd0);

`ifndef SYNTHESIS
  // This is an exclusive cycle classification of the compute engine's strict
  // QBS_WAIT_WEIGHT state, not a general read-engine occupancy breakdown.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      probe_weight_wait_no_outstanding_cycles_q <= '0;
      probe_weight_wait_response_idle_cycles_q <= '0;
      probe_weight_wait_r_transfer_cycles_q <= '0;
      probe_weight_wait_r_blocked_cycles_q <= '0;
    end else if (command_fire) begin
      probe_weight_wait_no_outstanding_cycles_q <= '0;
      probe_weight_wait_response_idle_cycles_q <= '0;
      probe_weight_wait_r_transfer_cycles_q <= '0;
      probe_weight_wait_r_blocked_cycles_q <= '0;
    end else if (i_compute_engine.probe_weight_wait_active) begin
      if (i_read_engine.burst_fifo_count_q == 0) begin
        probe_weight_wait_no_outstanding_cycles_q <=
            probe_weight_wait_no_outstanding_cycles_q + 1'b1;
      end else if (!axi_r_valid_i) begin
        probe_weight_wait_response_idle_cycles_q <=
            probe_weight_wait_response_idle_cycles_q + 1'b1;
      end else if (axi_r_ready_o) begin
        probe_weight_wait_r_transfer_cycles_q <=
            probe_weight_wait_r_transfer_cycles_q + 1'b1;
      end else begin
        probe_weight_wait_r_blocked_cycles_q <=
            probe_weight_wait_r_blocked_cycles_q + 1'b1;
      end
    end
  end

  // Bounded event-correlated trace for one real command. It is disabled by
  // default and intentionally observes only the first 200 cycles beginning at
  // the first integer-tile launch, which keeps long model runs manageable.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      probe_root_trace_active_q <= 1'b0;
      probe_root_trace_done_q <= 1'b0;
      probe_root_trace_cycle_q <= '0;
    end else if ($test$plusargs("QBS_ROOT_TRACE")) begin
      if (!probe_root_trace_active_q && !probe_root_trace_done_q &&
          i_compute_engine.integer_start_fire) begin
        probe_root_trace_active_q <= 1'b1;
        probe_root_trace_cycle_q <= '0;
      end else if (probe_root_trace_active_q) begin
        $display("[QBS_ROOT] c=%0d cs=%0d k=%0d row=%0d istart=%0d idone=%0d cur_done=%0d next_done=%0d bank=%0d issue_k=%0d issue_row=%0d issue_bank=%0d pending=%0d range=%0d/%0d role=%0d tag_bank=%0d tag_rows=%0d plan=%0d rfifo=%0d bfifo=%0d ar=%0d/%0d r=%0d/%0d data=%0d/%0d off=%0d wait=%0d",
                 probe_root_trace_cycle_q,
                 i_compute_engine.state_q,
                 compute_expected_k,
                 compute_expected_row_base,
                 i_compute_engine.integer_start_fire,
                 i_compute_engine.integer_done,
                 i_compute_engine.current_weight_complete,
                 i_compute_engine.load_weight_complete,
                 i_compute_engine.active_weight_bank_q,
                 weight_issue_k_q,
                 weight_issue_row_base_q,
                 weight_issue_bank_q,
                 weight_ranges_pending_q,
                 read_range_valid,
                 read_range_ready,
                 read_range_tag.role,
                 read_range_tag.weight_bank,
                 read_range_tag.weight_row_count,
                 i_read_engine.plan_state_q,
                 i_read_engine.range_fifo_count_q,
                 i_read_engine.burst_fifo_count_q,
                 axi_ar_valid_o,
                 axi_ar_ready_i,
                 axi_r_valid_i,
                 axi_r_ready_o,
                 read_data_valid,
                 read_data_ready,
                 read_data_offset,
                 i_compute_engine.probe_weight_wait_active);
        if (probe_root_trace_cycle_q == 8'd199) begin
          probe_root_trace_active_q <= 1'b0;
          probe_root_trace_done_q <= 1'b1;
        end else begin
          probe_root_trace_cycle_q <= probe_root_trace_cycle_q + 1'b1;
        end
      end
    end
  end
`endif

  // Descriptor faults do not start the compute or commit sub-engines. Keep
  // their retained counters hidden until this command reaches each stage.
  assign tiles_computed_o = compute_counters_valid_q
      ? compute_tiles_computed : '0;
  assign weight_bytes_o = compute_counters_valid_q
      ? compute_weight_bytes : '0;
  assign activation_bytes_o = compute_counters_valid_q
      ? compute_activation_bytes : '0;
  assign useful_pairs_o = compute_counters_valid_q
      ? compute_useful_pairs : '0;
  assign pair_capacity_o = compute_counters_valid_q
      ? compute_pair_capacity : '0;
  assign dot_active_cycles_o = compute_counters_valid_q
      ? compute_dot_active_cycles : '0;
  assign fp_uop_issue_o = compute_counters_valid_q
      ? compute_fp_uop_issue : '0;
  assign fp_table_occupancy_sum_o = compute_counters_valid_q
      ? compute_fp_table_occupancy_sum : '0;
  assign fp_table_occupancy_max_o = compute_counters_valid_q
      ? compute_fp_table_occupancy_max : '0;
  assign fp_table_full_cycles_o = compute_counters_valid_q
      ? compute_fp_table_full_cycles : '0;
  assign accumulator_updates_o = compute_counters_valid_q
      ? compute_accumulator_updates : '0;
  assign commit_word_count_o = commit_counters_valid_q
      ? commit_word_count : '0;
  assign commit_backpressure_cycles_o = commit_counters_valid_q
      ? commit_backpressure_cycles : '0;

  assign read_range_fire = read_range_valid && read_range_ready;
  assign read_data_fire = read_data_valid && read_data_ready;
  assign read_completion_fire = read_completion_valid && read_completion_ready;
  assign read_fault_fire = read_fault_valid && read_fault_ready;
  assign lookahead_weight_range_fire = weight_lookahead_enabled &&
      read_range_fire && read_range_tag.role == QBS_RANGE_WEIGHT;
  assign lookahead_weight_completion_fire = weight_lookahead_enabled &&
      read_completion_fire && read_completion_tag.role == QBS_RANGE_WEIGHT;

  qbs_descriptor_decoder #(
    .VLEN (VLEN)
  ) i_descriptor_decoder (
    .descriptor_address_i         (64'(descriptor_address_q)),
    .descriptor_header_i          (descriptor_q[63:0]),
    .descriptor_weight_base_i     (descriptor_q[127:64]),
    .activation_base_i            (64'(activation_base_q)),
    .m_i                          (m_q),
    .vd_i                         (vd_q),
    .valid_o                      (descriptor_valid),
    .error_o                      (descriptor_error),
    .weight_profile_o             (descriptor_weight_profile),
    .activation_profile_o         (descriptor_activation_profile),
    .weight_layout_o              (descriptor_weight_layout),
    .activation_layout_o          (descriptor_activation_layout),
    .n_o                          (descriptor_n),
    .k_blocks_o                   (descriptor_k_blocks),
    .weight_block_bytes_o         (descriptor_weight_block_bytes),
    .activation_block_bytes_o     (descriptor_activation_block_bytes),
    .weight_storage_bytes_o       (descriptor_weight_storage_bytes),
    .activation_storage_bytes_o   (descriptor_activation_storage_bytes),
    .weight_last_address_o        (descriptor_weight_last_address),
    .activation_last_address_o    (descriptor_activation_last_address)
  );

  always_comb begin : form_read_range
    automatic logic [63:0] logical_row;
    automatic logic [63:0] block_index;
    automatic logic [63:0] address_offset;

    read_range_valid = 1'b0;
    read_range_vaddr = '0;
    read_range_bytes = '0;
    read_range_tag = '{role: QBS_RANGE_RESERVED, target: '0,
                       weight_bank: 1'b0, weight_row_count: '0};

    scheduler_tuple_current =
        scheduler_k_q == compute_expected_k &&
        scheduler_row_base_q == compute_expected_row_base;
    activation_range_count =
        activation_layout_q == QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
            ? 3'd1 : m_q;
    weight_range_count =
        weight_layout_q == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR
            ? 3'd1 : compute_expected_row_count;

    if (state_q == QBS_ENGINE_DESCRIPTOR_REQUEST) begin
      read_range_valid = 1'b1;
      read_range_vaddr = descriptor_address_q;
      read_range_bytes = RangeBytesWidth'(QbsDescriptorBytes);
      read_range_tag = '{role: QBS_RANGE_DESCRIPTOR, target: '0,
                         weight_bank: 1'b0, weight_row_count: '0};
    end else if (state_q == QBS_ENGINE_RUN && scheduler_tuple_current) begin
      if (compute_activation_needed &&
          activation_range_index_q < activation_range_count) begin
        read_range_valid = 1'b1;
        read_range_tag = '{role: QBS_RANGE_ACTIVATION,
                           target: activation_range_index_q[1:0],
                           weight_bank: 1'b0, weight_row_count: '0};
        if (activation_layout_q ==
            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED) begin
          address_offset = 64'(compute_expected_k) *
                           (4 * activation_block_bytes_q);
          read_range_vaddr = activation_base_q + VAddrWidth'(address_offset);
          read_range_bytes = RangeBytesWidth'(4 * activation_block_bytes_q);
        end else begin
          block_index = 64'(activation_range_index_q) * k_blocks_q +
                        compute_expected_k;
          address_offset = block_index * activation_block_bytes_q;
          read_range_vaddr = activation_base_q + VAddrWidth'(address_offset);
          read_range_bytes = RangeBytesWidth'(activation_block_bytes_q);
        end
      end else if (weight_lookahead_enabled &&
                   weight_issue_cursor_current &&
                   weight_issue_row_base_q < n_q &&
                   weight_ranges_pending_q < 2) begin
        logical_row = weight_issue_row_base_q;
        block_index = ((logical_row >> 2) * k_blocks_q +
                       weight_issue_k_q) << 2;
        address_offset = block_index * weight_block_bytes_q;
        read_range_valid = 1'b1;
        read_range_vaddr = VAddrWidth'(weight_base_q + address_offset);
        read_range_bytes = RangeBytesWidth'(weight_issue_row_count *
                                             weight_block_bytes_q);
        read_range_tag = '{role: QBS_RANGE_WEIGHT, target: '0,
                           weight_bank: weight_issue_bank_q,
                           weight_row_count: weight_issue_row_count};
      end else if (!weight_lookahead_enabled && compute_weight_needed &&
                   weight_range_index_q < weight_range_count) begin
        logical_row = 64'(compute_expected_row_base) +
                      weight_range_index_q;
        if (weight_layout_q == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR) begin
          block_index = ((logical_row >> 2) * k_blocks_q +
                         compute_expected_k) << 2;
        end else begin
          block_index = logical_row * k_blocks_q + compute_expected_k;
        end
        address_offset = block_index * weight_block_bytes_q;
        read_range_valid = 1'b1;
        read_range_vaddr = VAddrWidth'(weight_base_q + address_offset);
        read_range_bytes = weight_layout_q ==
                QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR
            ? RangeBytesWidth'(compute_expected_row_count *
                               weight_block_bytes_q)
            : RangeBytesWidth'(weight_block_bytes_q);
        read_range_tag = '{role: QBS_RANGE_WEIGHT,
                           target: weight_range_index_q[1:0],
                           weight_bank: compute_expected_weight_bank,
                           weight_row_count: compute_expected_row_count};
      end
    end
  end

  always_comb begin
    read_data_ready = 1'b0;
    unique case (read_data_tag.role)
      QBS_RANGE_DESCRIPTOR:
        read_data_ready = state_q == QBS_ENGINE_DESCRIPTOR_WAIT;
      QBS_RANGE_ACTIVATION:
        read_data_ready = state_q == QBS_ENGINE_RUN &&
                          compute_activation_write_ready;
      QBS_RANGE_WEIGHT:
        read_data_ready = state_q == QBS_ENGINE_RUN &&
                          compute_weight_write_ready;
      default: ;
    endcase
  end

  assign compute_weight_write_valid = read_data_valid &&
      read_data_tag.role == QBS_RANGE_WEIGHT &&
      state_q == QBS_ENGINE_RUN;
  assign compute_weight_write_group =
      weight_layout_q == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR;
  assign compute_activation_write_valid = read_data_valid &&
      read_data_tag.role == QBS_RANGE_ACTIVATION &&
      state_q == QBS_ENGINE_RUN;

  assign read_completion_ready =
      (state_q == QBS_ENGINE_DESCRIPTOR_WAIT &&
       read_completion_tag.role == QBS_RANGE_DESCRIPTOR) ||
      (state_q == QBS_ENGINE_RUN &&
       read_completion_tag.role inside {
           QBS_RANGE_ACTIVATION, QBS_RANGE_WEIGHT});
  assign read_fault_ready = state_q inside {
      QBS_ENGINE_DESCRIPTOR_WAIT, QBS_ENGINE_RUN};

  qbs_read_engine #(
    .AxiDataWidth    (AxiDataWidth),
    .AxiAddrWidth    (AxiAddrWidth),
    .VAddrWidth      (VAddrWidth),
    .PAddrWidth      (PAddrWidth),
    .RangeBytesWidth (RangeBytesWidth),
    .axi_ar_t        (axi_ar_t),
    .axi_r_t         (axi_r_t),
    .exception_t     (exception_t),
    .tag_t           (qbs_range_tag_t)
  ) i_read_engine (
    .clk_i,
    .rst_ni,
    .range_valid_i                  (read_range_valid),
    .range_ready_o                  (read_range_ready),
    .range_vaddr_i                  (read_range_vaddr),
    .range_bytes_i                  (read_range_bytes),
    .range_tag_i                    (read_range_tag),
    .range_cache_i                  (cache_q),
    .range_prot_i                   (prot_q),
    .data_valid_o                   (read_data_valid),
    .data_ready_i                   (read_data_ready),
    .data_o                         (read_data),
    .data_strb_o                    (read_data_strb),
    .data_offset_o                  (read_data_offset),
    .data_tag_o                     (read_data_tag),
    .completion_valid_o             (read_completion_valid),
    .completion_ready_i             (read_completion_ready),
    .completion_tag_o               (read_completion_tag),
    .fault_valid_o                  (read_fault_valid),
    .fault_ready_i                  (read_fault_ready),
    .fault_kind_o                   (read_fault_kind),
    .fault_vaddr_o                  (read_fault_vaddr),
    .fault_tag_o                    (read_fault_tag),
    .fault_mmu_exception_o          (read_fault_mmu_exception),
    .core_st_pending_i,
    .en_ld_st_translation_i,
    .mmu_req_o,
    .mmu_vaddr_o,
    .mmu_is_store_o,
    .mmu_valid_i,
    .mmu_paddr_i,
    .mmu_exception_valid_i,
    .mmu_exception_i,
    .physical_check_valid_o,
    .physical_check_addr_o,
    .physical_check_bytes_o,
    .physical_range_allowed_i,
    .axi_ar_o,
    .axi_ar_valid_o,
    .axi_ar_ready_i,
    .axi_r_i,
    .axi_r_valid_i,
    .axi_r_ready_o,
    .counters_clear_i               (command_fire),
    .range_count_o                  (read_range_count_o),
    .translation_count_o            (read_translation_count_o),
    .ar_count_o                     (read_ar_count_o),
    .r_beat_count_o                 (read_beat_count_o),
    .payload_byte_count_o           (read_payload_bytes_o),
    .store_wait_cycles_o            (read_store_wait_cycles_o),
    .r_backpressure_cycles_o        (read_backpressure_cycles_o),
    .outstanding_occupancy_sum_o    (read_outstanding_occupancy_sum_o),
    .outstanding_max_o              (read_outstanding_max_o),
    .outstanding_full_cycles_o      (read_outstanding_full_cycles_o),
    .busy_o                         (read_busy)
  );

  assign compute_command_valid = state_q == QBS_ENGINE_COMPUTE_START;
  assign compute_fault = state_q == QBS_ENGINE_COMPUTE_FAULT_DRAIN ||
      (state_q == QBS_ENGINE_RUN && read_fault_valid);

  qbs_compute_engine i_compute_engine (
    .clk_i,
    .rst_ni,
    .command_valid_i                (compute_command_valid),
    .command_ready_o                (compute_command_ready),
    .command_weight_profile_i       (weight_profile_q),
    .command_activation_profile_i   (activation_profile_q),
    .command_weight_layout_i        (weight_layout_q),
    .command_activation_layout_i    (activation_layout_q),
    .command_m_i                    (m_q),
    .command_n_i                    (n_q),
    .command_k_blocks_i             (k_blocks_q),
    .fault_i                        (compute_fault),
    .fault_done_o                   (compute_fault_done),
    .weight_write_valid_i           (compute_weight_write_valid),
    .weight_write_ready_o           (compute_weight_write_ready),
    .weight_write_bank_i            (read_data_tag.weight_bank),
    .weight_write_row_count_i       (read_data_tag.weight_row_count),
    .weight_write_group_i           (compute_weight_write_group),
    .weight_write_row_i             (read_data_tag.target),
    .weight_write_offset_i          (read_data_offset[9:0]),
    .weight_write_data_i            (read_data),
    .weight_write_strb_i            (read_data_strb),
    .activation_write_valid_i       (compute_activation_write_valid),
    .activation_write_ready_o       (compute_activation_write_ready),
    .activation_write_context_i     (read_data_tag.target),
    .activation_write_offset_i      (read_data_offset[10:0]),
    .activation_write_data_i        (read_data),
    .activation_write_strb_i        (read_data_strb),
    .expected_k_block_o             (compute_expected_k),
    .expected_row_base_o            (compute_expected_row_base),
    .expected_row_count_o           (compute_expected_row_count),
    .expected_weight_bank_o         (compute_expected_weight_bank),
    .activation_block_needed_o      (compute_activation_needed),
    .weight_block_needed_o          (compute_weight_needed),
    .result_valid_o                 (compute_result_valid),
    .result_consumed_i              (compute_result_consumed),
    .result_read_index_i            ('0),
    .result_read_valid_o            (),
    .result_read_data_o             (),
    .result_bank_read_row_i         (compute_result_bank_row),
    .result_bank_read_valid_o       (compute_result_bank_valid),
    .result_bank_read_data_o        (compute_result_bank_data),
    .result_fflags_o                (compute_result_fflags),
    .busy_o                         (compute_busy),
    .phase_activation_load_o        (compute_phase_activation),
    .phase_weight_load_o            (compute_phase_weight),
    .phase_compute_o                (compute_phase_compute),
    .phase_drain_o                  (compute_phase_drain),
    .weight_prefetch_wait_cycles_o  (compute_weight_prefetch_wait_cycles),
    .tiles_computed_o              (compute_tiles_computed),
    .weight_bytes_o                (compute_weight_bytes),
    .activation_bytes_o            (compute_activation_bytes),
    .useful_pairs_o                (compute_useful_pairs),
    .pair_capacity_o               (compute_pair_capacity),
    .dot_active_cycles_o           (compute_dot_active_cycles),
    .fp_uop_issue_o                (compute_fp_uop_issue),
    .fp_table_occupancy_sum_o      (compute_fp_table_occupancy_sum),
    .fp_table_occupancy_max_o      (compute_fp_table_occupancy_max),
    .fp_table_full_cycles_o        (compute_fp_table_full_cycles),
    .accumulator_updates_o         (compute_accumulator_updates)
  );

  assign commit_start_valid = state_q == QBS_ENGINE_RUN &&
                              compute_result_valid;
  assign commit_done_ready = state_q == QBS_ENGINE_COMMIT;
  assign compute_result_consumed = commit_done_valid && commit_done_ready;

  qbs_commit #(
    .NrLanes (NrLanes),
    .VLEN    (VLEN),
    .vid_t   (vid_t),
    .vaddr_t (vaddr_t)
  ) i_commit (
    .clk_i,
    .rst_ni,
    .start_valid_i                   (commit_start_valid),
    .start_ready_o                   (commit_start_ready),
    .start_id_i                      (id_q),
    .start_vd_i                      (vd_q),
    .start_m_i                       (m_q),
    .start_n_i                       (n_q),
    .accumulator_bank_row_o          (compute_result_bank_row),
    .accumulator_bank_valid_i        (compute_result_bank_valid),
    .accumulator_bank_data_i         (compute_result_bank_data),
    .ldu_result_req_o,
    .ldu_result_id_o,
    .ldu_result_addr_o,
    .ldu_result_wdata_o,
    .ldu_result_be_o,
    .ldu_result_gnt_i,
    .ldu_result_final_gnt_i,
    .done_valid_o                    (commit_done_valid),
    .done_ready_i                    (commit_done_ready),
    .busy_o                          (commit_busy),
    .commit_word_count_o            (commit_word_count),
    .commit_backpressure_cycles_o   (commit_backpressure_cycles)
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      compute_counters_valid_q <= 1'b0;
      commit_counters_valid_q <= 1'b0;
    end else if (command_fire) begin
      compute_counters_valid_q <= 1'b0;
      commit_counters_valid_q <= 1'b0;
    end else begin
      if (compute_command_valid && compute_command_ready)
        compute_counters_valid_q <= 1'b1;
      if (commit_start_valid && commit_start_ready)
        commit_counters_valid_q <= 1'b1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      phase_setup_cycles_q <= '0;
      phase_activation_cycles_q <= '0;
      phase_weight_cycles_q <= '0;
      phase_compute_cycles_q <= '0;
      phase_overlap_cycles_q <= '0;
      phase_drain_cycles_q <= '0;
      phase_scheduler_cycles_q <= '0;
      phase_commit_cycles_q <= '0;
      phase_fault_cycles_q <= '0;
      phase_terminal_cycles_q <= '0;
    end else if (command_fire) begin
      phase_setup_cycles_q <= '0;
      phase_activation_cycles_q <= '0;
      phase_weight_cycles_q <= '0;
      phase_compute_cycles_q <= '0;
      phase_overlap_cycles_q <= '0;
      phase_drain_cycles_q <= '0;
      phase_scheduler_cycles_q <= '0;
      phase_commit_cycles_q <= '0;
      phase_fault_cycles_q <= '0;
      phase_terminal_cycles_q <= '0;
    end else begin
      unique case (command_phase)
        QBS_PHASE_SETUP:
          phase_setup_cycles_q <= phase_setup_cycles_q + 1'b1;
        QBS_PHASE_ACTIVATION:
          phase_activation_cycles_q <= phase_activation_cycles_q + 1'b1;
        QBS_PHASE_WEIGHT:
          phase_weight_cycles_q <= phase_weight_cycles_q + 1'b1;
        QBS_PHASE_COMPUTE:
          phase_compute_cycles_q <= phase_compute_cycles_q + 1'b1;
        QBS_PHASE_OVERLAP:
          phase_overlap_cycles_q <= phase_overlap_cycles_q + 1'b1;
        QBS_PHASE_DRAIN:
          phase_drain_cycles_q <= phase_drain_cycles_q + 1'b1;
        QBS_PHASE_SCHEDULER:
          phase_scheduler_cycles_q <= phase_scheduler_cycles_q + 1'b1;
        QBS_PHASE_COMMIT:
          phase_commit_cycles_q <= phase_commit_cycles_q + 1'b1;
        QBS_PHASE_FAULT:
          phase_fault_cycles_q <= phase_fault_cycles_q + 1'b1;
        QBS_PHASE_TERMINAL:
          phase_terminal_cycles_q <= phase_terminal_cycles_q + 1'b1;
        default: ;
      endcase
    end
  end

  always_comb begin
    state_d = state_q;
    fault_is_validation_d = fault_is_validation_q;
    validation_error_d = validation_error_q;
    read_fault_kind_d = read_fault_kind_q;
    fault_vaddr_d = fault_vaddr_q;
    fault_mmu_exception_d = fault_mmu_exception_q;
    result_fflags_d = result_fflags_q;

    unique case (state_q)
      QBS_ENGINE_IDLE: begin
        if (command_valid_i)
          state_d = QBS_ENGINE_DESCRIPTOR_REQUEST;
      end

      QBS_ENGINE_DESCRIPTOR_REQUEST: begin
        if (read_range_fire)
          state_d = QBS_ENGINE_DESCRIPTOR_WAIT;
      end

      QBS_ENGINE_DESCRIPTOR_WAIT: begin
        if (read_fault_valid) begin
          fault_is_validation_d = 1'b0;
          read_fault_kind_d = read_fault_kind;
          fault_vaddr_d = read_fault_vaddr;
          fault_mmu_exception_d = read_fault_mmu_exception;
          state_d = QBS_ENGINE_FAULT;
        end else if (read_completion_valid) begin
          if (&descriptor_byte_valid_q) begin
            state_d = QBS_ENGINE_VALIDATE;
          end else begin
            fault_is_validation_d = 1'b0;
            read_fault_kind_d = QBS_READ_FAULT_REQUEST;
            fault_vaddr_d = descriptor_address_q;
            fault_mmu_exception_d = '0;
            state_d = QBS_ENGINE_FAULT;
          end
        end
      end

      QBS_ENGINE_VALIDATE: begin
        if (descriptor_valid) begin
          state_d = QBS_ENGINE_COMPUTE_START;
        end else begin
          fault_is_validation_d = 1'b1;
          validation_error_d = descriptor_error;
          read_fault_kind_d = QBS_READ_FAULT_NONE;
          fault_vaddr_d = descriptor_address_q;
          fault_mmu_exception_d = '0;
          state_d = QBS_ENGINE_FAULT;
        end
      end

      QBS_ENGINE_COMPUTE_START: begin
        if (compute_command_ready)
          state_d = QBS_ENGINE_RUN;
      end

      QBS_ENGINE_RUN: begin
        if (read_fault_valid) begin
          fault_is_validation_d = 1'b0;
          read_fault_kind_d = read_fault_kind;
          fault_vaddr_d = read_fault_vaddr;
          fault_mmu_exception_d = read_fault_mmu_exception;
          state_d = QBS_ENGINE_COMPUTE_FAULT_DRAIN;
        end else if (commit_start_valid && commit_start_ready) begin
          state_d = QBS_ENGINE_COMMIT;
        end
      end

      QBS_ENGINE_COMPUTE_FAULT_DRAIN: begin
        if (compute_fault_done)
          state_d = QBS_ENGINE_FAULT;
      end

      QBS_ENGINE_COMMIT: begin
        if (commit_done_valid) begin
          result_fflags_d = compute_result_fflags;
          state_d = QBS_ENGINE_SUCCESS;
        end
      end

      QBS_ENGINE_SUCCESS: begin
        if (terminal_ready_i)
          state_d = QBS_ENGINE_IDLE;
      end

      QBS_ENGINE_FAULT: begin
        if (terminal_ready_i)
          state_d = QBS_ENGINE_IDLE;
      end

      default: state_d = QBS_ENGINE_IDLE;
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= QBS_ENGINE_IDLE;
      id_q <= '0;
      vd_q <= '0;
      m_q <= '0;
      descriptor_address_q <= '0;
      activation_base_q <= '0;
      cache_q <= '0;
      prot_q <= '0;
      descriptor_q <= '0;
      descriptor_byte_valid_q <= '0;
      weight_profile_q <= QBS_WEIGHT_PROFILE_INVALID;
      activation_profile_q <= QBS_ACTIVATION_PROFILE_INVALID;
      weight_layout_q <= QBS_WEIGHT_LAYOUT_INVALID;
      activation_layout_q <= QBS_ACTIVATION_LAYOUT_INVALID;
      n_q <= '0;
      k_blocks_q <= '0;
      weight_block_bytes_q <= '0;
      activation_block_bytes_q <= '0;
      weight_base_q <= '0;
      scheduler_k_q <= '0;
      scheduler_row_base_q <= '0;
      activation_range_index_q <= '0;
      weight_range_index_q <= '0;
      weight_issue_k_q <= '0;
      weight_issue_row_base_q <= '0;
      weight_issue_bank_q <= 1'b0;
      weight_ranges_pending_q <= '0;
      fault_is_validation_q <= 1'b0;
      validation_error_q <= QBS_VALIDATION_OK;
      read_fault_kind_q <= QBS_READ_FAULT_NONE;
      fault_vaddr_q <= '0;
      fault_mmu_exception_q <= '0;
      result_fflags_q <= '0;
      command_cycles_o <= '0;
    end else begin
      state_q <= state_d;
      fault_is_validation_q <= fault_is_validation_d;
      validation_error_q <= validation_error_d;
      read_fault_kind_q <= read_fault_kind_d;
      fault_vaddr_q <= fault_vaddr_d;
      fault_mmu_exception_q <= fault_mmu_exception_d;
      result_fflags_q <= result_fflags_d;

      if (command_fire) begin
        id_q <= command_id_i;
        vd_q <= command_vd_i;
        m_q <= command_m_i;
        descriptor_address_q <= command_descriptor_address_i;
        activation_base_q <= command_activation_base_i;
        cache_q <= command_cache_i;
        prot_q <= command_prot_i;
        descriptor_q <= '0;
        descriptor_byte_valid_q <= '0;
        fault_is_validation_q <= 1'b0;
        validation_error_q <= QBS_VALIDATION_OK;
        read_fault_kind_q <= QBS_READ_FAULT_NONE;
        fault_vaddr_q <= '0;
        fault_mmu_exception_q <= '0;
        result_fflags_q <= '0;
        command_cycles_o <= '0;
        weight_issue_k_q <= '0;
        weight_issue_row_base_q <= '0;
        weight_issue_bank_q <= 1'b0;
        weight_ranges_pending_q <= '0;
      end else if (busy_o) begin
        command_cycles_o <= command_cycles_o + 1'b1;
      end

      if (state_q == QBS_ENGINE_DESCRIPTOR_REQUEST) begin
        descriptor_q <= '0;
        descriptor_byte_valid_q <= '0;
      end else if (read_data_fire &&
                   read_data_tag.role == QBS_RANGE_DESCRIPTOR) begin
        for (int unsigned byte_lane = 0;
             byte_lane < AxiDataWidth / 8; byte_lane++) begin
          automatic int unsigned descriptor_offset =
              unsigned'(read_data_offset) + byte_lane;
          if (read_data_strb[byte_lane] && descriptor_offset < 16) begin
            descriptor_q[descriptor_offset * 8 +: 8] <=
                read_data[byte_lane * 8 +: 8];
            descriptor_byte_valid_q[descriptor_offset] <= 1'b1;
          end
        end
      end

      if (state_q == QBS_ENGINE_VALIDATE && descriptor_valid) begin
        weight_profile_q <= descriptor_weight_profile;
        activation_profile_q <= descriptor_activation_profile;
        weight_layout_q <= descriptor_weight_layout;
        activation_layout_q <= descriptor_activation_layout;
        n_q <= descriptor_n;
        k_blocks_q <= descriptor_k_blocks;
        weight_block_bytes_q <= descriptor_weight_block_bytes;
        activation_block_bytes_q <= descriptor_activation_block_bytes;
        weight_base_q <= descriptor_q[127:64];
      end

      if (state_q == QBS_ENGINE_COMPUTE_START && compute_command_ready) begin
        scheduler_k_q <= '0;
        scheduler_row_base_q <= '0;
        activation_range_index_q <= '0;
        weight_range_index_q <= '0;
        weight_issue_k_q <= '0;
        weight_issue_row_base_q <= '0;
        weight_issue_bank_q <= 1'b0;
        weight_ranges_pending_q <= '0;
      end else if (state_q == QBS_ENGINE_RUN) begin
        if (!scheduler_tuple_current) begin
          scheduler_k_q <= compute_expected_k;
          scheduler_row_base_q <= compute_expected_row_base;
          activation_range_index_q <= '0;
          weight_range_index_q <= '0;
        end else if (read_range_fire) begin
          unique case (read_range_tag.role)
            QBS_RANGE_ACTIVATION:
              activation_range_index_q <= activation_range_index_q + 1'b1;
            QBS_RANGE_WEIGHT:
              weight_range_index_q <= weight_range_index_q + 1'b1;
            default: ;
          endcase
        end

        if (weight_lookahead_enabled) begin
          if (!weight_issue_cursor_current) begin
            weight_issue_k_q <= compute_expected_k;
            weight_issue_row_base_q <= '0;
            weight_issue_bank_q <= 1'b0;
          end else if (lookahead_weight_range_fire) begin
            weight_issue_row_base_q <=
                weight_issue_row_base_q + weight_issue_row_count;
            weight_issue_bank_q <= ~weight_issue_bank_q;
          end

          unique case ({lookahead_weight_range_fire,
                        lookahead_weight_completion_fire})
            2'b10:
              weight_ranges_pending_q <= weight_ranges_pending_q + 1'b1;
            2'b01:
              weight_ranges_pending_q <= weight_ranges_pending_q - 1'b1;
            default: ;
          endcase
        end
      end
    end
  end

`ifndef SYNTHESIS
  initial begin
    assert (AxiDataWidth == 128)
      else $fatal(1, "QBS v1 block adapter requires a 128-bit read beat");
    assert (NrLanes == 4)
      else $fatal(1, "QBS v1 commit requires four Ara lanes");
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni) begin
      assert (!(success_valid_o && fault_valid_o))
        else $fatal(1, "QBS command cannot succeed and fault together");
      if (state_q inside {QBS_ENGINE_DESCRIPTOR_REQUEST,
                          QBS_ENGINE_DESCRIPTOR_WAIT,
                          QBS_ENGINE_VALIDATE,
                          QBS_ENGINE_COMPUTE_START,
                          QBS_ENGINE_RUN,
                          QBS_ENGINE_COMPUTE_FAULT_DRAIN})
        assert (ldu_result_req_o == '0)
          else $fatal(1, "QBS exposed VRF writes before atomic commit");
      if (read_completion_fire && state_q == QBS_ENGINE_RUN)
        assert (read_completion_tag.role inside {
            QBS_RANGE_ACTIVATION, QBS_RANGE_WEIGHT})
          else $fatal(1, "QBS completed an unexpected command range");
      if (read_fault_fire)
        assert (read_fault_tag.role != QBS_RANGE_RESERVED)
          else $fatal(1, "QBS fault lost its request role");
      if (state_q == QBS_ENGINE_COMMIT)
        assert (!read_busy && compute_result_valid)
          else $fatal(1, "QBS commit started before reads/compute completed");
      if (state_q inside {QBS_ENGINE_SUCCESS, QBS_ENGINE_FAULT}) begin
        assert (phase_setup_cycles_o + phase_activation_cycles_o +
                phase_weight_cycles_o + phase_compute_cycles_o +
                phase_overlap_cycles_o + phase_drain_cycles_o +
                phase_scheduler_cycles_o + phase_commit_cycles_o +
                phase_fault_cycles_o + phase_terminal_cycles_o ==
                command_cycles_o + 1'b1)
          else $fatal(1, "QBS exclusive phase counters do not cover busy time");
      end
      if (state_q == QBS_ENGINE_RUN && scheduler_tuple_current &&
          weight_layout_q == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR)
        assert (compute_expected_row_base[1:0] == 2'b00)
          else $fatal(1, "QBS R4 scheduler row base is not group aligned");
      if (weight_lookahead_enabled && state_q == QBS_ENGINE_RUN) begin
        assert (weight_ranges_pending_q <= 2)
          else $fatal(1, "QBS weight lookahead exceeded its two-bank credit");
        if (!weight_issue_cursor_current)
          assert (weight_ranges_pending_q == 0)
            else $fatal(1, "QBS crossed a K-block with pending weight tiles");
        if (lookahead_weight_completion_fire)
          assert (weight_ranges_pending_q != 0)
            else $fatal(1, "QBS weight lookahead completion underflow");
        if (lookahead_weight_range_fire) begin
          assert (read_range_tag.weight_bank == weight_issue_bank_q &&
                  read_range_tag.weight_row_count ==
                      weight_issue_row_count &&
                  weight_issue_row_base_q[1:0] == 2'b00 &&
                  weight_issue_row_count inside {[1:4]})
            else $fatal(1, "QBS weight lookahead emitted inconsistent metadata");
        end
      end
    end
  end
`endif

  logic unused;
  assign unused = ^{descriptor_weight_storage_bytes,
                    descriptor_activation_storage_bytes,
                    descriptor_weight_last_address,
                    descriptor_activation_last_address,
                    read_busy, compute_busy, commit_busy};

endmodule : qbs_engine
