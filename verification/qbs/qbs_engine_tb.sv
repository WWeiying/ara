`timescale 1ns/1ps

module qbs_engine_tb;
  import qbs_pkg::*;
  import fpnew_pkg::*;
  import axi_pkg::*;

  `include "axi/typedef.svh"

  localparam int unsigned AxiDataWidth = 128;
  localparam int unsigned BeatBytes = AxiDataWidth / 8;
  localparam int unsigned NrLanes = 4;
  localparam int unsigned VLEN = 1024;
  localparam int unsigned WordsPerRegister = VLEN / 8 / (NrLanes * 8);

  typedef logic [63:0] axi_addr_t;
  typedef logic [AxiDataWidth-1:0] axi_data_t;
  typedef logic [0:0] axi_id_t;
  typedef logic [0:0] axi_user_t;
  typedef logic [3:0] vid_t;
  typedef logic [7:0] vaddr_t;
  typedef struct packed {
    logic [63:0] cause;
    logic [63:0] tval;
    logic valid;
  } exception_t;

  `AXI_TYPEDEF_AR_CHAN_T(axi_ar_t, axi_addr_t, axi_id_t, axi_user_t)
  `AXI_TYPEDEF_R_CHAN_T(axi_r_t, axi_data_t, axi_id_t, axi_user_t)

  logic clk;
  logic rst_n;

  logic command_valid;
  logic command_ready;
  vid_t command_id;
  logic [4:0] command_vd;
  logic [3:0] command_m;
  logic [63:0] command_descriptor_address;
  logic [63:0] command_activation_base;
  logic success_valid;
  logic fault_valid;
  logic terminal_ready;
  logic [4:0] result_fflags;
  logic fault_is_validation;
  qbs_validation_error_e validation_error;
  qbs_read_fault_e read_fault_kind;
  logic [63:0] fault_vaddr;
  exception_t fault_mmu_exception;

  logic core_st_pending;
  logic translation_enable;
  logic mmu_req;
  logic [63:0] mmu_vaddr;
  logic mmu_is_store;
  logic mmu_valid;
  logic [63:0] mmu_paddr;
  logic mmu_exception_valid;
  exception_t mmu_exception;
  logic physical_check_valid;
  logic [63:0] physical_check_addr;
  logic [12:0] physical_check_bytes;
  logic physical_range_allowed;

  axi_ar_t axi_ar;
  logic axi_ar_valid;
  logic axi_ar_ready;
  axi_r_t axi_r;
  logic axi_r_valid;
  logic axi_r_ready;

  logic [NrLanes-1:0] ldu_result_req;
  vid_t [NrLanes-1:0] ldu_result_id;
  vaddr_t [NrLanes-1:0] ldu_result_addr;
  logic [63:0] ldu_result_wdata [NrLanes];
  logic [7:0] ldu_result_be [NrLanes];
  logic [NrLanes-1:0] ldu_result_gnt;
  logic [NrLanes-1:0] ldu_result_final_gnt;

  logic busy;
  logic [31:0] command_cycles;
  logic [31:0] read_range_count;
  logic [31:0] read_translation_count;
  logic [31:0] read_ar_count;
  logic [31:0] read_beat_count;
  logic [31:0] read_payload_bytes;
  logic [31:0] read_store_wait_cycles;
  logic [31:0] read_backpressure_cycles;
  logic [31:0] read_outstanding_occupancy_sum;
  logic [1:0] read_outstanding_max;
  logic [31:0] read_outstanding_full_cycles;
  logic [31:0] phase_setup_cycles;
  logic [31:0] phase_activation_cycles;
  logic [31:0] phase_weight_cycles;
  logic [31:0] phase_compute_cycles;
  logic [31:0] phase_overlap_cycles;
  logic [31:0] phase_drain_cycles;
  logic [31:0] phase_scheduler_cycles;
  logic [31:0] phase_commit_cycles;
  logic [31:0] phase_fault_cycles;
  logic [31:0] phase_terminal_cycles;
  logic [31:0] weight_prefetch_wait_cycles;
  logic [31:0] tiles_computed;
  logic [31:0] weight_bytes;
  logic [31:0] activation_bytes;
  logic [31:0] useful_pairs;
  logic [31:0] pair_capacity;
  logic [31:0] dot_active_cycles;
  logic [31:0] fp_uop_issue;
  logic [31:0] fp_table_occupancy_sum;
  logic [4:0] fp_table_occupancy_max;
  logic [31:0] fp_table_full_cycles;
  logic [31:0] accumulator_updates;
  logic [31:0] commit_word_count;
  logic [31:0] commit_backpressure_cycles;
  qbs_activation_access_e activation_access;
  logic [31:0] context_fill_count;
  logic [31:0] context_reuse_count;
  logic [31:0] context_reuse_block_count;
  logic [31:0] context_read_bytes;
  integer activation_ahead_beats;
  integer activation_overlap_beats;
  integer activation_ready_boundaries;
  logic [7:0] observed_k;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      activation_ahead_beats <= 0;
      activation_overlap_beats <= 0;
      activation_ready_boundaries <= 0;
      observed_k <= 0;
    end else if (command_valid && command_ready) begin
      activation_ahead_beats <= 0;
      activation_overlap_beats <= 0;
      activation_ready_boundaries <= 0;
      observed_k <= 0;
    end else begin
      observed_k <= dut.compute_expected_k;
      if (dut.compute_activation_write_valid && dut.compute_activation_write_ready &&
          dut.compute_activation_write_k != dut.compute_expected_k) begin
        activation_ahead_beats <= activation_ahead_beats + 1;
        if (dut.compute_phase_compute)
          activation_overlap_beats <= activation_overlap_beats + 1;
      end
      if (observed_k != dut.compute_expected_k &&
          dut.i_compute_engine.all_activation_complete)
        activation_ready_boundaries <= activation_ready_boundaries + 1;
      if ($test$plusargs("QBS_ACTIVATION_TRACE") && command_cycles < 400 &&
          (dut.read_range_fire || dut.i_compute_engine.integer_start_fire))
        $display("ACT_TRACE cycle=%0d k=%0d act_k=%0d range=%0b role=%0d tag_k=%0d start=%0b bank=%0b complete=%0b%0b",
                 command_cycles, dut.compute_expected_k, dut.compute_expected_activation_k,
                 dut.read_range_fire, dut.read_range_tag.role, dut.read_range_tag.k_block,
                 dut.i_compute_engine.integer_start_fire,
                 dut.i_compute_engine.activation_read_bank,
                 dut.i_compute_engine.all_activation_complete_bank[1],
                 dut.i_compute_engine.all_activation_complete_bank[0]);
    end
  end
  logic [31:0] activation_axi_bytes_saved;
  logic [31:0] context_replay_cycles;
  logic [31:0] context_replay_compute_overlap_cycles;
  logic [31:0] context_validation_fault_count;

  // Testbench-only attribution. Stall categories overlap; do not sum them.
`define FP_PROBE dut.i_compute_engine.i_fp_accumulator
  integer fp_probe_fd = 0;
  integer fp_probe_start = 0;
  integer fp_probe_end = 4000;
  string fp_probe_path;
  integer fp_probe_blocked, fp_probe_slot_sparse, fp_probe_conflict;
  integer fp_probe_issue, fp_probe_no_eligible, fp_probe_backpressure;
  integer fp_probe_dual_issue, fp_probe_cast_issue, fp_probe_half_issue;
`ifdef QBS_SINGLE_FP_PORT
  defparam dut.i_compute_engine.i_fp_accumulator.SplitIssue = 1'b0;
  defparam dut.i_compute_engine.i_fp_accumulator.HalfScaleIssue = 1'b0;
`elsif QBS_NO_HALF_SCALE_PORT
  defparam dut.i_compute_engine.i_fp_accumulator.HalfScaleIssue = 1'b0;
`endif
  initial begin
    if ($value$plusargs("QBS_FP_TRACE=%s", fp_probe_path)) begin
      fp_probe_fd = $fopen(fp_probe_path, "w");
      if (fp_probe_fd == 0) $fatal(1, "Cannot open QBS FP probe");
      $fdisplay(fp_probe_fd, "cycle,k,req_valid,req_ready,req_slot,req_acc,occ,valid_mask,inflight_mask,conflict,selected,state,issue_valid,issue_ready,fire,done,done_tag,cast_fire,cast_tag,cast_done,cast_done_tag,half_fire,half_tag,half_done,half_done_tag");
    end
    void'($value$plusargs("QBS_FP_TRACE_START=%d", fp_probe_start));
    void'($value$plusargs("QBS_FP_TRACE_END=%d", fp_probe_end));
  end
  final if (fp_probe_fd != 0) $fclose(fp_probe_fd);
  always @(posedge clk) begin
    if (!rst_n || (command_valid && command_ready)) begin
      fp_probe_blocked = 0;
      fp_probe_slot_sparse = 0;
      fp_probe_conflict = 0;
      fp_probe_issue = 0;
      fp_probe_no_eligible = 0;
      fp_probe_backpressure = 0;
      fp_probe_dual_issue = 0;
      fp_probe_cast_issue = 0;
      fp_probe_half_issue = 0;
    end else if (dut.busy_o) begin
      if (`FP_PROBE.request_valid_i && !`FP_PROBE.request_ready_o) begin
        fp_probe_blocked++;
        if (`FP_PROBE.entry_valid_q[`FP_PROBE.request_slot_i] &&
            `FP_PROBE.entry_occupancy < 16 && !`FP_PROBE.request_accumulator_conflict)
          fp_probe_slot_sparse++;
        if (`FP_PROBE.request_accumulator_conflict) fp_probe_conflict++;
      end
      fp_probe_issue += int'(`FP_PROBE.fp_fire) + int'(`FP_PROBE.cast_fire) + int'(`FP_PROBE.half_fire);
      if (`FP_PROBE.cast_fire) fp_probe_cast_issue++;
      if (`FP_PROBE.half_fire) fp_probe_half_issue++;
      if (`FP_PROBE.cast_fire && `FP_PROBE.fp_fire) fp_probe_dual_issue++;
      if (`FP_PROBE.busy_o && !`FP_PROBE.schedule_found && !`FP_PROBE.cast_found &&
          !`FP_PROBE.half_found)
        fp_probe_no_eligible++;
      if ((`FP_PROBE.fp_in_valid && !`FP_PROBE.fp_in_ready) ||
          (`FP_PROBE.cast_found && !`FP_PROBE.cast_ready)) fp_probe_backpressure++;
      if (fp_probe_fd != 0 && command_cycles >= fp_probe_start &&
          command_cycles < fp_probe_end)
        $fdisplay(fp_probe_fd, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%h,%h,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
          command_cycles, dut.compute_expected_k,
          `FP_PROBE.request_valid_i, `FP_PROBE.request_ready_o,
          `FP_PROBE.request_slot_i, `FP_PROBE.request_accumulator_index_i,
          `FP_PROBE.entry_occupancy, `FP_PROBE.entry_valid_q,
          `FP_PROBE.entry_inflight_q, `FP_PROBE.request_accumulator_conflict,
          `FP_PROBE.schedule_index, `FP_PROBE.entry_state_q[`FP_PROBE.schedule_index],
          `FP_PROBE.fp_in_valid, `FP_PROBE.fp_in_ready, `FP_PROBE.fp_fire,
          `FP_PROBE.fp_out_valid, `FP_PROBE.fp_tag_out,
          `FP_PROBE.cast_fire, `FP_PROBE.cast_index,
          `FP_PROBE.cast_out_valid, `FP_PROBE.cast_tag_out,
          `FP_PROBE.half_fire, `FP_PROBE.half_index,
          `FP_PROBE.half_out_valid, `FP_PROBE.half_tag_out);
    end
  end
`undef FP_PROBE

  qbs_engine #(
`ifdef QBS_NO_ACTIVATION_LOOKAHEAD
    .ActivationLookahead(1'b0),
`endif
    .AxiDataWidth (AxiDataWidth),
    .AxiAddrWidth (64),
    .VAddrWidth   (64),
    .PAddrWidth   (64),
    .NrLanes      (NrLanes),
    .VLEN         (VLEN),
    .vid_t        (vid_t),
    .vaddr_t      (vaddr_t),
    .axi_ar_t     (axi_ar_t),
    .axi_r_t      (axi_r_t),
    .exception_t  (exception_t)
  ) dut (
    .clk_i                           (clk),
    .rst_ni                          (rst_n),
    .command_valid_i                 (command_valid),
    .command_ready_o                 (command_ready),
    .command_id_i                    (command_id),
    .command_vd_i                    (command_vd),
    .command_m_i                     (command_m),
    .command_descriptor_address_i    (command_descriptor_address),
    .command_activation_base_i       (command_activation_base),
    .command_cache_i                 (CACHE_MODIFIABLE),
    .command_prot_i                  ('0),
    .success_valid_o                 (success_valid),
    .fault_valid_o                   (fault_valid),
    .terminal_ready_i                (terminal_ready),
    .result_fflags_o                 (result_fflags),
    .fault_is_validation_o           (fault_is_validation),
    .validation_error_o              (validation_error),
    .read_fault_kind_o               (read_fault_kind),
    .fault_vaddr_o                   (fault_vaddr),
    .fault_mmu_exception_o           (fault_mmu_exception),
    .core_st_pending_i               (core_st_pending),
    .en_ld_st_translation_i          (translation_enable),
    .mmu_req_o                       (mmu_req),
    .mmu_vaddr_o                     (mmu_vaddr),
    .mmu_is_store_o                  (mmu_is_store),
    .mmu_valid_i                     (mmu_valid),
    .mmu_paddr_i                     (mmu_paddr),
    .mmu_exception_valid_i           (mmu_exception_valid),
    .mmu_exception_i                 (mmu_exception),
    .physical_check_valid_o          (physical_check_valid),
    .physical_check_addr_o           (physical_check_addr),
    .physical_check_bytes_o          (physical_check_bytes),
    .physical_range_allowed_i        (physical_range_allowed),
    .axi_ar_o                        (axi_ar),
    .axi_ar_valid_o                  (axi_ar_valid),
    .axi_ar_ready_i                  (axi_ar_ready),
    .axi_r_i                         (axi_r),
    .axi_r_valid_i                   (axi_r_valid),
    .axi_r_ready_o                   (axi_r_ready),
    .ldu_result_req_o                (ldu_result_req),
    .ldu_result_id_o                 (ldu_result_id),
    .ldu_result_addr_o               (ldu_result_addr),
    .ldu_result_wdata_o              (ldu_result_wdata),
    .ldu_result_be_o                 (ldu_result_be),
    .ldu_result_gnt_i                (ldu_result_gnt),
    .ldu_result_final_gnt_i          (ldu_result_final_gnt),
    .busy_o                          (busy),
    .command_cycles_o                (command_cycles),
    .read_range_count_o              (read_range_count),
    .read_translation_count_o        (read_translation_count),
    .read_ar_count_o                 (read_ar_count),
    .read_beat_count_o               (read_beat_count),
    .read_payload_bytes_o            (read_payload_bytes),
    .read_store_wait_cycles_o        (read_store_wait_cycles),
    .read_backpressure_cycles_o      (read_backpressure_cycles),
    .read_outstanding_occupancy_sum_o(read_outstanding_occupancy_sum),
    .read_outstanding_max_o          (read_outstanding_max),
    .read_outstanding_full_cycles_o  (read_outstanding_full_cycles),
    .phase_setup_cycles_o            (phase_setup_cycles),
    .phase_activation_cycles_o       (phase_activation_cycles),
    .phase_weight_cycles_o           (phase_weight_cycles),
    .phase_compute_cycles_o          (phase_compute_cycles),
    .phase_overlap_cycles_o          (phase_overlap_cycles),
    .phase_drain_cycles_o            (phase_drain_cycles),
    .phase_scheduler_cycles_o        (phase_scheduler_cycles),
    .phase_commit_cycles_o           (phase_commit_cycles),
    .phase_fault_cycles_o            (phase_fault_cycles),
    .phase_terminal_cycles_o         (phase_terminal_cycles),
    .weight_prefetch_wait_cycles_o   (weight_prefetch_wait_cycles),
    .tiles_computed_o                (tiles_computed),
    .weight_bytes_o                  (weight_bytes),
    .activation_bytes_o              (activation_bytes),
    .useful_pairs_o                  (useful_pairs),
    .pair_capacity_o                 (pair_capacity),
    .dot_active_cycles_o             (dot_active_cycles),
    .fp_uop_issue_o                  (fp_uop_issue),
    .fp_table_occupancy_sum_o        (fp_table_occupancy_sum),
    .fp_table_occupancy_max_o        (fp_table_occupancy_max),
    .fp_table_full_cycles_o          (fp_table_full_cycles),
    .accumulator_updates_o           (accumulator_updates),
    .commit_word_count_o             (commit_word_count),
    .commit_backpressure_cycles_o    (commit_backpressure_cycles),
    .activation_access_o             (activation_access),
    .context_fill_count_o            (context_fill_count),
    .context_reuse_count_o           (context_reuse_count),
    .context_reuse_block_count_o     (context_reuse_block_count),
    .context_read_bytes_o            (context_read_bytes),
    .activation_axi_bytes_saved_o    (activation_axi_bytes_saved),
    .context_replay_cycles_o         (context_replay_cycles),
    .context_replay_compute_overlap_cycles_o(
        context_replay_compute_overlap_cycles),
    .context_validation_fault_count_o(context_validation_fault_count)
  );

  always #5 clk = ~clk;

  byte unsigned memory [longint unsigned];
  logic [31:0] memory_epoch;
  logic [31:0] expected_output [128];
  bit expected_output_valid [128];
  logic score_commit;
  integer score_m;
  integer score_n;
  integer score_vd;
  integer score_id;
  logic score_reset;
  integer commit_aggregate_words;
  integer unexpected_write_count;
  bit functional_only;
  bit context_suite;
  logic [31:0] commit_seen;
  bit saw_dual_read_outstanding;
  bit saw_read_outstanding_full;
  logic activation_ar_monitor;
  logic [63:0] monitored_activation_base;
  logic [63:0] monitored_activation_end;
  integer activation_ar_count;

  function automatic logic [7:0] memory_byte(input logic [63:0] address);
    longint unsigned index;
    index = address;
    if (memory.exists(index))
      return memory[index];
    return 8'h00;
  endfunction

  function automatic logic [63:0] memory_u64(input logic [63:0] address);
    logic [63:0] value;
    value = '0;
    for (int unsigned byte_lane = 0; byte_lane < 8; byte_lane++)
      value[byte_lane*8 +: 8] = memory_byte(address + byte_lane);
    return value;
  endfunction

  function automatic logic [63:0] descriptor_header(
      input integer version,
      input integer profile,
      input integer weight_layout,
      input integer activation_layout,
      input integer n,
      input integer k_blocks
  );
    logic [63:0] header;
    header = '0;
    header[3:0] = version[3:0];
    header[7:4] = profile[3:0];
    header[11:8] = qbs_default_activation_profile(
        qbs_weight_profile_e'(profile));
    header[15:12] = weight_layout[3:0];
    header[19:16] = activation_layout[3:0];
    header[24:20] = (n - 1) & 5'h1f;
    header[32:25] = (k_blocks - 1) & 8'hff;
    return header;
  endfunction

  function automatic logic [63:0] context_descriptor_header(
      input integer profile,
      input integer weight_layout,
      input integer activation_layout,
      input integer n,
      input integer k_blocks,
      input qbs_activation_access_e access,
      input integer context_id,
      input integer generation
  );
    logic [63:0] header;
    header = descriptor_header(QbsDescriptorVersion, profile, weight_layout,
                               activation_layout, n, k_blocks);
    header[QbsDescActivationAccessLsb +: 2] = access;
    header[QbsDescContextIdLsb +: 4] = context_id[3:0];
    header[QbsDescContextGenerationLsb +: 8] = generation[7:0];
    return header;
  endfunction

  task automatic put_u64(input logic [63:0] address,
                         input logic [63:0] value);
    for (int unsigned byte_lane = 0; byte_lane < 8; byte_lane++)
      memory[longint'(address + byte_lane)] = value[byte_lane*8 +: 8];
    memory_epoch++;
  endtask

  task automatic install_descriptor(
      input logic [63:0] descriptor_base,
      input logic [63:0] weight_base,
      input integer version,
      input integer profile,
      input integer weight_layout,
      input integer activation_layout,
      input integer n,
      input integer k_blocks
  );
    put_u64(descriptor_base,
            descriptor_header(version, profile, weight_layout,
                              activation_layout, n, k_blocks));
    put_u64(descriptor_base + 8, weight_base);
  endtask

  task automatic install_context_descriptor(
      input logic [63:0] descriptor_base,
      input logic [63:0] weight_base,
      input integer profile,
      input integer weight_layout,
      input integer activation_layout,
      input integer n,
      input integer k_blocks,
      input qbs_activation_access_e access,
      input integer context_id,
      input integer generation
  );
    put_u64(descriptor_base,
            context_descriptor_header(profile, weight_layout,
                                      activation_layout, n, k_blocks, access,
                                      context_id, generation));
    put_u64(descriptor_base + 8, weight_base);
  endtask

  task automatic put_beat(input logic [63:0] address,
                          input logic [15:0] strb,
                          input logic [127:0] data);
    for (int unsigned byte_lane = 0; byte_lane < 16; byte_lane++) begin
      if (strb[byte_lane])
        memory[longint'(address + byte_lane)] = data[byte_lane*8 +: 8];
    end
    memory_epoch++;
  endtask

  // One-cycle identity translation, with address-selective fault injection.
  logic mmu_pending;
  logic [63:0] mmu_pending_vaddr;
  logic inject_mmu_fault;
  logic [63:0] inject_fault_start;
  logic [63:0] inject_fault_end;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mmu_pending <= 1'b0;
      mmu_pending_vaddr <= '0;
      mmu_valid <= 1'b0;
      mmu_paddr <= '0;
      mmu_exception <= '0;
    end else begin
      mmu_valid <= 1'b0;
      mmu_exception <= '0;
      // The response cycle acknowledges this request, not a new request.
      if (!mmu_pending && mmu_req && !mmu_valid && !mmu_exception.valid) begin
        mmu_pending <= 1'b1;
        mmu_pending_vaddr <= mmu_vaddr;
      end else if (mmu_pending) begin
        mmu_pending <= 1'b0;
        if (inject_mmu_fault && mmu_pending_vaddr >= inject_fault_start &&
            mmu_pending_vaddr < inject_fault_end) begin
          mmu_exception.valid <= 1'b1;
          mmu_exception.cause <= 64'd13;
          mmu_exception.tval <= mmu_pending_vaddr;
        end else begin
          mmu_valid <= 1'b1;
          mmu_paddr <= mmu_pending_vaddr;
        end
      end
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      activation_ar_count <= 0;
    end else begin
      if (!activation_ar_monitor)
        activation_ar_count <= 0;
      else if (axi_ar_valid && axi_ar_ready &&
               axi_ar.addr < monitored_activation_end &&
               axi_ar.addr + (64'(axi_ar.len) + 1) * BeatBytes >
                   monitored_activation_base)
        activation_ar_count <= activation_ar_count + 1;
    end
  end

  assign mmu_exception_valid = mmu_exception.valid;

  logic inject_pma_fault;
  always_comb begin
    physical_range_allowed = 1'b1;
    if (inject_pma_fault && physical_check_addr < inject_fault_end &&
        physical_check_addr + physical_check_bytes > inject_fault_start)
      physical_range_allowed = 1'b0;
  end

  // Deterministic two-request, same-ID AXI slave. Responses remain ordered,
  // while the read engine may issue the next range before the current burst
  // drains.
  logic [63:0] response_addr [2];
  logic [7:0] response_len [2];
  logic [8:0] response_beat;
  logic response_rd;
  logic response_wr;
  logic [1:0] response_count;
  logic inject_axi_fault;
  logic fault_replay_overlap_seen;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n || score_reset) fault_replay_overlap_seen <= 1'b0;
    else if (dut.read_fault_valid && dut.context_replay_busy) begin
      fault_replay_overlap_seen <= 1'b1;
      if (!fault_replay_overlap_seen)
        $display("QBS fault/replay overlap time=%0t access=%0d offset=%0d last=%b ready=%b",
                 $time, activation_access, dut.context_replay_offset,
                 dut.context_replay_last, dut.context_replay_data_ready);
    end
  end
  integer response_gap;
  integer response_delay;

  assign axi_ar_ready = response_count < 2;
  assign axi_r_valid = response_count != 0 && response_delay == 0;

  always_comb begin
    axi_r = '0;
    // Associative-array writes are not inferred in VCS always_comb
    // sensitivity, so explicitly observe the epoch before reading memory.
    axi_r.data = {128{memory_epoch[0]}};
    for (int unsigned byte_lane = 0; byte_lane < BeatBytes; byte_lane++)
      axi_r.data[byte_lane*8 +: 8] =
          memory_byte(response_addr[response_rd] +
                      response_beat * BeatBytes + byte_lane);
    axi_r.resp = inject_axi_fault &&
                 response_addr[response_rd] < inject_fault_end &&
                 response_addr[response_rd] + BeatBytes > inject_fault_start &&
                 response_beat == 0 ? RESP_SLVERR : RESP_OKAY;
    axi_r.last = response_beat == {1'b0, response_len[response_rd]};
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      response_addr[0] <= '0;
      response_addr[1] <= '0;
      response_len[0] <= '0;
      response_len[1] <= '0;
      response_beat <= '0;
      response_rd <= '0;
      response_wr <= '0;
      response_count <= '0;
      response_delay <= 0;
    end else begin
      if (response_delay != 0) response_delay <= response_delay - 1;
      else if (axi_r_valid && axi_r_ready) response_delay <= response_gap;
      if (axi_ar_valid && axi_ar_ready) begin
        response_addr[response_wr] <= axi_ar.addr;
        response_len[response_wr] <= axi_ar.len;
        response_wr <= response_wr + 1'b1;
      end
      if (axi_r_valid && axi_r_ready) begin
        if (axi_r.last) begin
          response_rd <= response_rd + 1'b1;
          response_beat <= '0;
        end else begin
          response_beat <= response_beat + 1'b1;
        end
      end
      unique case ({axi_ar_valid && axi_ar_ready,
                    axi_r_valid && axi_r_ready && axi_r.last})
        2'b10: response_count <= response_count + 1'b1;
        2'b01: response_count <= response_count - 1'b1;
        default: ;
      endcase
    end
  end

  assign ldu_result_gnt = ldu_result_req;
  assign ldu_result_final_gnt = ldu_result_req;

  always_ff @(posedge clk) begin : score_vrf_commit
    if (!rst_n || score_reset) begin
      commit_aggregate_words <= 0;
      unexpected_write_count <= 0;
      commit_seen <= '0;
    end else if (|ldu_result_req) begin
      if (!score_commit) begin
        unexpected_write_count <= unexpected_write_count + 1;
      end else begin
        automatic int relative_word;
        automatic int ctx;
        automatic int register_word;
        automatic int accumulator_stride;
        automatic int words_per_context;
        relative_word = unsigned'(ldu_result_addr[0]) -
                        score_vd * WordsPerRegister;
        words_per_context = score_m > 4 ? (score_n > 8 ? 2 : 1) :
                            WordsPerRegister;
        ctx = relative_word / WordsPerRegister;
        register_word = relative_word % WordsPerRegister;
        accumulator_stride = score_m > 4 ? QbsWideMMaxN : QbsMaxN;
        if (ctx < 0 || ctx >= score_m || register_word < 0 ||
            register_word >= words_per_context)
          $fatal(1, "QBS commit address outside destination group");
        if (commit_seen[relative_word])
          $fatal(1, "QBS committed a destination word twice");
        commit_seen[relative_word] <= 1'b1;
        for (int lane = 0; lane < NrLanes; lane++) begin
          automatic int low_element = register_word * 8 + lane;
          automatic int high_element = low_element + NrLanes;
          automatic int low_index =
              ctx * accumulator_stride + low_element;
          automatic int high_index =
              ctx * accumulator_stride + high_element;
          automatic logic low_active = low_element < score_n;
          automatic logic high_active = high_element < score_n;
          automatic logic [7:0] expected_be = score_m > 4
              ? {{4{high_active}}, {4{low_active}}} : 8'hff;
          automatic logic [31:0] expected_low;
          automatic logic [31:0] expected_high;
          expected_low = low_active
              ? expected_output[low_index] : 32'b0;
          expected_high = high_active
              ? expected_output[high_index] : 32'b0;
          if (!expected_output_valid[low_index] && low_active)
            $fatal(1, "missing expected low result index=%0d", low_index);
          if (!expected_output_valid[high_index] && high_active)
            $fatal(1, "missing expected high result index=%0d", high_index);
          if (ldu_result_req[lane] !== (|expected_be) ||
              ldu_result_be[lane] !== expected_be ||
              ((|expected_be) &&
               (ldu_result_id[lane] !== score_id[3:0] ||
                ldu_result_addr[lane] !== ldu_result_addr[0] ||
                ldu_result_wdata[lane] !== {expected_high, expected_low})))
            $fatal(1,
                   "VRF write mismatch ctx=%0d word=%0d lane=%0d got=%h expected=%h_%h",
                   ctx, register_word, lane, ldu_result_wdata[lane],
                   expected_high, expected_low);
        end
        commit_aggregate_words <= commit_aggregate_words + 1;
      end
    end
  end

  task automatic send_command(input integer id, input integer vd,
                              input integer m,
                              input logic [63:0] descriptor_base,
                              input logic [63:0] activation_base);
    integer timeout;
    timeout = 0;
    while (!command_ready && timeout < 1000) begin
      @(posedge clk);
      timeout++;
    end
    if (!command_ready) $fatal(1, "timeout waiting for QBS command ready");
    @(negedge clk);
    command_id = id[3:0];
    command_vd = vd[4:0];
    command_m = m[3:0];
    command_descriptor_address = descriptor_base;
    command_activation_base = activation_base;
    command_valid = 1'b1;
    @(negedge clk);
    command_valid = 1'b0;
  endtask

  task automatic reset_scoreboard;
    @(negedge clk);
    score_reset = 1'b1;
    @(negedge clk);
    score_reset = 1'b0;
  endtask

  task automatic acknowledge_terminal;
    @(negedge clk);
    terminal_ready = 1'b1;
    @(negedge clk);
    terminal_ready = 1'b0;
  endtask

  task automatic wait_success(input integer case_id);
    integer timeout;
    timeout = 0;
    while (!success_valid && !fault_valid && timeout < 200000) begin
      @(posedge clk);
      timeout++;
    end
    if (success_valid !== 1'b1)
      $fatal(1,
             "case %0d did not succeed fault=%0b validation=%0b verr=%0d read=%0d vaddr=%h",
             case_id, fault_valid, fault_is_validation, validation_error,
             read_fault_kind, fault_vaddr);
    if ($isunknown({result_fflags, command_cycles, commit_aggregate_words,
                    read_payload_bytes, read_range_count, context_read_bytes,
                    context_reuse_count, context_reuse_block_count,
                    activation_axi_bytes_saved, activation_ar_count,
                    commit_word_count, unexpected_write_count, tiles_computed,
                    weight_bytes, activation_bytes, useful_pairs, pair_capacity,
                    dot_active_cycles, fp_uop_issue, accumulator_updates,
                    activation_access, context_fill_count, context_validation_fault_count,
                    phase_setup_cycles, phase_activation_cycles, phase_weight_cycles,
                    phase_compute_cycles, phase_overlap_cycles, phase_drain_cycles,
                    phase_scheduler_cycles, phase_commit_cycles, phase_fault_cycles,
                    phase_terminal_cycles}))
      $fatal(1, "case %0d has unknown completion metadata/counters", case_id);
  endtask

  task automatic expect_fault(input logic expected_validation,
                              input qbs_validation_error_e expected_validation_error,
                              input qbs_read_fault_e expected_read_fault,
                              input logic [63:0] expected_vaddr);
    integer timeout;
    if ($isunknown({expected_validation, expected_validation_error,
                    expected_read_fault, expected_vaddr}))
      $fatal(1, "unknown expected fault metadata");
    timeout = 0;
    while (!fault_valid && !success_valid && timeout < 50000) begin
      @(posedge clk);
      timeout++;
    end
    if (fault_valid !== 1'b1 || fault_is_validation !== expected_validation ||
        validation_error !== expected_validation_error ||
        read_fault_kind !== expected_read_fault ||
        fault_vaddr !== expected_vaddr) begin
      $display("descriptor observed header=%h access=%0d generation=%h k_blocks=%0d; context valid=%0b generation=%h k_blocks=%0d",
               dut.descriptor_q[63:0], dut.descriptor_activation_access,
               dut.descriptor_context_generation, dut.descriptor_k_blocks,
               dut.i_activation_context.context_valid_q,
               dut.i_activation_context.context_generation_q,
               dut.i_activation_context.context_k_blocks_q);
      $fatal(1,
             "fault mismatch valid=%0b validation=%0b/%0b verr=%0d/%0d read=%0d/%0d vaddr=%h/%h",
             fault_valid, fault_is_validation, expected_validation,
             validation_error, expected_validation_error, read_fault_kind,
             expected_read_fault, fault_vaddr, expected_vaddr);
    end
    if (commit_aggregate_words != 0 || unexpected_write_count != 0)
      $fatal(1, "faulting QBS command modified the VRF");
    acknowledge_terminal();
  endtask

  initial begin : run_tests
    string vector_file;
    string token;
    integer fd;
    integer rc;
    integer case_count;
    integer total_errors;
    bit projection_suite;
    integer projection_m, projection_n, projection_k, projection_profile;
    integer projection_layout;
    longint unsigned projection_direct_cycles, projection_context_cycles;
    longint unsigned projection_direct_payload, projection_context_payload;
    longint unsigned projection_saved_bytes;

    clk = 1'b0;
    rst_n = 1'b0;
    command_valid = 1'b0;
    command_id = '0;
    command_vd = '0;
    command_m = '0;
    command_descriptor_address = '0;
    command_activation_base = '0;
    memory_epoch = '0;
    terminal_ready = 1'b0;
    core_st_pending = 1'b0;
    translation_enable = 1'b0;
    inject_mmu_fault = 1'b0;
    inject_pma_fault = 1'b0;
    inject_axi_fault = 1'b0;
    inject_fault_start = '0;
    inject_fault_end = '0;
    score_commit = 1'b0;
    score_m = 0;
    score_n = 0;
    score_vd = 0;
    score_id = 0;
    score_reset = 1'b0;
    total_errors = 0;
    saw_dual_read_outstanding = 1'b0;
    saw_read_outstanding_full = 1'b0;
    activation_ar_monitor = 1'b0;
    monitored_activation_base = '0;
    monitored_activation_end = '0;
    functional_only = $test$plusargs("QBS_FUNCTIONAL_ONLY");
    context_suite = $test$plusargs("QBS_CONTEXT_SUITE");
    projection_suite = $test$plusargs("QBS_PROJECTION_SUITE");
    if (projection_suite && (!functional_only || context_suite))
      $fatal(1, "projection requires functional-only and a separate context suite");
    projection_direct_cycles = 0;
    projection_context_cycles = 0;
    projection_direct_payload = 0;
    projection_context_payload = 0;
    projection_saved_bytes = 0;
    response_gap = 0;
    void'($value$plusargs("QBS_RESPONSE_GAP=%d", response_gap));
    if (response_gap < 0 || response_gap > 8)
      $fatal(1, "QBS_RESPONSE_GAP must be 0..8");
    $display("QBS configuration response_gap=%0d context_suite=%0d", response_gap, context_suite);

    if (!$value$plusargs("QBS_COMMAND_VECTOR_FILE=%s", vector_file))
      vector_file = "../qbs_command_vectors.txt";
    fd = $fopen(vector_file, "r");
    if (fd == 0) $fatal(1, "cannot open QBS command vector file %s",
                        vector_file);
    rc = $fscanf(fd, "%s %d", token, case_count);
    if (rc != 2 || token != "QBSCMD1") $fatal(1, "bad command header");
    if (projection_suite && case_count < 2)
      $fatal(1, "projection requires at least two output tiles");

    repeat (4) @(posedge clk);
    rst_n = 1'b1;
    repeat (2) @(posedge clk);

    for (integer ordinal = 0; ordinal < case_count; ordinal++) begin
      integer case_id;
      integer profile;
      integer weight_layout;
      integer activation_layout;
      integer m;
      integer n;
      integer k_blocks;
      integer expected_flags;
      integer block_bytes;
      integer activation_block_bytes;
      integer expected_tiles;
      integer expected_weight_bytes;
      integer expected_activation_bytes;
      integer expected_useful_pairs;
      integer expected_pair_capacity;
      integer expected_dot_cycles;
      integer expected_fp_uops;
      integer expected_updates;
      integer expected_ranges;
      integer output_records;
      integer case_errors;
      integer direct_activation_ar_count;
      logic [63:0] descriptor_base;
      logic [63:0] weight_base;
      logic [63:0] activation_base;

      memory.delete();
      for (int index = 0; index < 128; index++) begin
        expected_output_valid[index] = 1'b0;
        expected_output[index] = '0;
      end

      rc = $fscanf(fd, "%s %d %d %d %d %d %d %d %h", token, case_id,
                   profile, weight_layout, activation_layout, m, n, k_blocks,
                   expected_flags);
      if (rc != 9 || token != "CMD" || case_id != ordinal)
        $fatal(1, "bad CMD record at ordinal %0d", ordinal);

      descriptor_base = 64'h0000_0000_0000_1000;
      weight_base = 64'h0000_0000_0010_0000;
      activation_base = 64'h0000_0000_0020_0000;
      block_bytes = qbs_weight_block_bytes(qbs_weight_profile_e'(profile));
      activation_block_bytes = qbs_activation_block_bytes(
          qbs_default_activation_profile(qbs_weight_profile_e'(profile)));
      install_descriptor(descriptor_base, weight_base, QbsDescriptorVersion,
                         profile, weight_layout, activation_layout, n,
                         k_blocks);

      for (int tile = 0; tile < k_blocks * ((n + 3) / 4); tile++) begin
        integer tile_k;
        integer tile_row;
        integer tile_rows;
        rc = $fscanf(fd, "%s %d %d %d", token, tile_k, tile_row,
                     tile_rows);
        if (rc != 4 || token != "T")
          $fatal(1, "case %0d: bad T record", case_id);
        while (1) begin
          rc = $fscanf(fd, "%s", token);
          if (rc != 1) $fatal(1, "case %0d: short tile", case_id);
          if (token == "ENDT") break;
          if (token == "W") begin
            integer local_row;
            integer offset;
            integer logical_row;
            longint unsigned block_index;
            logic [15:0] strb;
            logic [127:0] data;
            rc = $fscanf(fd, "%d %d %h %h", local_row, offset, strb, data);
            if (rc != 4) $fatal(1, "case %0d: bad W beat", case_id);
            logical_row = tile_row + local_row;
            if (weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR)
              block_index = (((logical_row / 4) * k_blocks + tile_k) * 4) +
                            logical_row % 4;
            else
              block_index = logical_row * k_blocks + tile_k;
            put_beat(weight_base + block_index * block_bytes + offset,
                     strb, data);
          end else if (token == "A") begin
            integer ctx;
            integer offset;
            longint unsigned activation_offset;
            logic [15:0] strb;
            logic [127:0] data;
            rc = $fscanf(fd, "%d %d %h %h", ctx, offset, strb, data);
            if (rc != 4) $fatal(1, "case %0d: bad A beat", case_id);
            if (activation_layout inside {
                  QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
                  QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED})
              activation_offset =
                  tile_k * ((activation_layout ==
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED ? QbsMaxM : 4) *
                      activation_block_bytes) + offset;
            else
              activation_offset = (ctx * k_blocks + tile_k) *
                                  activation_block_bytes + offset;
            put_beat(activation_base + activation_offset, strb, data);
          end else begin
            $fatal(1, "case %0d: unexpected tile token %s", case_id, token);
          end
        end
      end

      output_records = m * n;
      for (int record = 0; record < output_records; record++) begin
        integer index;
        logic [31:0] bits;
        rc = $fscanf(fd, "%s %d %h", token, index, bits);
        if (rc != 3 || token != "O")
          $fatal(1, "case %0d: bad O record", case_id);
        expected_output_valid[index] = 1'b1;
        expected_output[index] = bits;
      end
      rc = $fscanf(fd, "%s %d %d %d %d %d %d %d %d", token,
                   expected_tiles, expected_weight_bytes,
                   expected_activation_bytes, expected_useful_pairs,
                   expected_pair_capacity, expected_dot_cycles,
                   expected_fp_uops, expected_updates);
      if (rc != 9 || token != "C")
        $fatal(1, "case %0d: bad C record", case_id);
      rc = $fscanf(fd, "%s", token);
      if (rc != 1 || token != "END")
        $fatal(1, "case %0d: missing END", case_id);

      score_commit = 1'b1;
      score_m = m;
      score_n = n;
      score_vd = m == 1 ? 3 : (m == 2 ? 4 : 8);
      score_id = case_id + 1;
      if (context_suite || projection_suite) begin
        if (k_blocks < 2 || k_blocks > QbsActivationContextMaxKBlocks ||
            expected_activation_bytes > QbsActivationContextCapacityBytes ||
            (activation_layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR && m != 1))
          $fatal(1, "context suite requires an admitted multi-block tile");
        activation_ar_monitor = 1'b1;
        monitored_activation_base = activation_base;
        monitored_activation_end = activation_base + expected_activation_bytes;
      end
      reset_scoreboard();
      send_command(score_id, score_vd, m, descriptor_base, activation_base);
      wait_success(case_id);
      saw_dual_read_outstanding |= read_outstanding_max == 2;
      saw_read_outstanding_full |= read_outstanding_full_cycles != 0;

      expected_ranges = 1 +
          (weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR
              ? ((n + 3) / 4) * k_blocks : n * k_blocks) +
          (activation_layout inside {
               QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
               QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED}
              ? k_blocks : m * k_blocks);
      begin
        automatic integer expected_commit_words = m *
            (m > 4 ? ((n + 7) / 8) : WordsPerRegister);
      case_errors = 0;
      if (result_fflags != expected_flags[4:0] ||
          tiles_computed != expected_tiles ||
          weight_bytes != expected_weight_bytes ||
          activation_bytes != expected_activation_bytes ||
          useful_pairs != expected_useful_pairs ||
          pair_capacity != expected_pair_capacity ||
          dot_active_cycles != expected_dot_cycles ||
          fp_uop_issue != expected_fp_uops ||
          accumulator_updates != expected_updates ||
          read_range_count != expected_ranges ||
          read_payload_bytes != 16 + expected_weight_bytes +
                                expected_activation_bytes ||
          phase_setup_cycles + phase_activation_cycles +
              phase_weight_cycles + phase_compute_cycles +
              phase_overlap_cycles + phase_drain_cycles +
              phase_scheduler_cycles + phase_commit_cycles +
              phase_fault_cycles + phase_terminal_cycles !=
              command_cycles + 1 ||
          (n > 4 && phase_overlap_cycles == 0) ||
          commit_word_count != expected_commit_words ||
          commit_aggregate_words != expected_commit_words ||
          activation_access != QBS_ACTIVATION_ACCESS_DIRECT ||
          context_fill_count != 0 || context_reuse_count != 0 ||
          context_reuse_block_count != 0 || context_read_bytes != 0 ||
          activation_axi_bytes_saved != 0 ||
          context_validation_fault_count != 0 ||
          unexpected_write_count != 0) begin
        $error("case %0d: end-to-end counter/commit mismatch", case_id);
        $display("  flags %0h/%0h tiles %0d/%0d W %0d/%0d A %0d/%0d",
                 result_fflags, expected_flags, tiles_computed,
                 expected_tiles, weight_bytes, expected_weight_bytes,
                 activation_bytes, expected_activation_bytes);
        $display("  ranges %0d/%0d payload %0d/%0d commit %0d/%0d",
                 read_range_count, expected_ranges, read_payload_bytes,
                 16 + expected_weight_bytes + expected_activation_bytes,
                 commit_aggregate_words, expected_commit_words);
        $display("  pairs useful=%0d/%0d capacity=%0d/%0d dot_cycles=%0d/%0d fp_uops=%0d/%0d updates=%0d/%0d",
                 useful_pairs, expected_useful_pairs, pair_capacity,
                 expected_pair_capacity, dot_active_cycles,
                 expected_dot_cycles, fp_uop_issue, expected_fp_uops,
                 accumulator_updates, expected_updates);
        $display("  read outstanding max=%0d full_cycles=%0d commit_words=%0d/%0d unexpected=%0d",
                 read_outstanding_max, read_outstanding_full_cycles,
                 commit_word_count, expected_commit_words,
                 unexpected_write_count);
        $display("  phases setup=%0d act=%0d weight=%0d compute=%0d overlap=%0d drain=%0d sched=%0d commit=%0d fault=%0d terminal=%0d prefetch_wait=%0d busy=%0d",
                 phase_setup_cycles, phase_activation_cycles,
                 phase_weight_cycles, phase_compute_cycles,
                 phase_overlap_cycles, phase_drain_cycles,
                 phase_scheduler_cycles, phase_commit_cycles,
                 phase_fault_cycles, phase_terminal_cycles,
                 weight_prefetch_wait_cycles, command_cycles + 1);
        case_errors++;
      end
      end
      if (case_errors == 0)
        $display("QBS end-to-end case %0d PASS profile=%0d M=%0d N=%0d Kb=%0d layouts=%0d/%0d cycles=%0d",
                 case_id, profile, m, n, k_blocks, weight_layout,
                 activation_layout, command_cycles);
      if (case_errors == 0 && functional_only) begin
        if ($test$plusargs("QBS_FP_PROBE"))
          $display("QBS FP probe case=%0d blocked=%0d sparse_slot=%0d conflict=%0d issued=%0d no_eligible=%0d backpressure=%0d occupancy_max=%0d full_cycles=%0d cast_issue=%0d dual_issue=%0d half_issue=%0d",
                   case_id, fp_probe_blocked, fp_probe_slot_sparse, fp_probe_conflict,
                   fp_probe_issue, fp_probe_no_eligible, fp_probe_backpressure,
                   fp_table_occupancy_max, fp_table_full_cycles,
                   fp_probe_cast_issue, fp_probe_dual_issue, fp_probe_half_issue);
        $display("QBS activation lookahead case=%0d ahead_beats=%0d overlap_beats=%0d ready_boundaries=%0d",
                 case_id, activation_ahead_beats, activation_overlap_beats, activation_ready_boundaries);
        if ($test$plusargs("QBS_REQUIRE_ACTIVATION_OVERLAP") && m <= 4 && k_blocks > 1)
          assert (activation_overlap_beats > 0 && activation_ready_boundaries > 0)
            else $fatal(1, "QBS lookahead did not overlap activation loading");
        $display("QBS phase case=%0d setup=%0d activation=%0d weight=%0d compute=%0d overlap=%0d drain=%0d scheduler=%0d commit=%0d terminal=%0d",
                 case_id, phase_setup_cycles, phase_activation_cycles,
                 phase_weight_cycles, phase_compute_cycles,
                 phase_overlap_cycles, phase_drain_cycles,
                 phase_scheduler_cycles, phase_commit_cycles,
                 phase_terminal_cycles);
        $display("QBS traffic case=%0d weight=%0d activation=%0d payload=%0d ranges=%0d dot=%0d prefetch_wait=%0d",
                 case_id, weight_bytes, activation_bytes, read_payload_bytes,
                 read_range_count, dot_active_cycles,
                 weight_prefetch_wait_cycles);
      end
      total_errors += case_errors;
      direct_activation_ar_count = activation_ar_count;
      if (projection_suite) begin
        if (case_errors != 0) $fatal(1, "projection direct command failed");
        projection_direct_cycles += command_cycles;
        projection_direct_payload += read_payload_bytes;
      end
      acknowledge_terminal();
      activation_ar_monitor = 1'b0;

      if (projection_suite) begin
        qbs_activation_access_e access_mode;
        integer context_commit_words;
        integer expected_weight_ranges;
        integer external_activation_bytes;
        if (ordinal == 0) begin
          projection_m = m;
          projection_n = n;
          projection_k = k_blocks;
          projection_profile = profile;
          projection_layout = activation_layout;
          if (dut.i_activation_context.context_valid_q)
            $fatal(1, "projection started with an existing context");
        end else if (m != projection_m || n != projection_n ||
                     k_blocks != projection_k || profile != projection_profile ||
                     activation_layout != projection_layout ||
                     !dut.i_activation_context.context_valid_q) begin
          $fatal(1, "projection geometry/lifetime changed between output tiles");
        end
        access_mode = ordinal == 0 ? QBS_ACTIVATION_ACCESS_FILL :
            ordinal == case_count - 1 ? QBS_ACTIVATION_ACCESS_RELEASE :
                                       QBS_ACTIVATION_ACCESS_REUSE;
        external_activation_bytes = ordinal == 0 ? expected_activation_bytes : 0;
        expected_weight_ranges = weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR
            ? ((n + 3) / 4) * k_blocks : n * k_blocks;
        context_commit_words = m * (m > 4 ? ((n + 7) / 8) : WordsPerRegister);
        install_context_descriptor(descriptor_base, weight_base, profile,
            weight_layout, activation_layout, n, k_blocks, access_mode, 0, 8'h51);
        if (ordinal != 0) begin
          for (int byte_index = 0; byte_index < expected_activation_bytes; byte_index++)
            memory[longint'(activation_base + byte_index)] = 8'ha5;
          memory_epoch++;
        end
        // The AR monitor clears synchronously while disabled. Let that edge
        // occur before starting the next command's independent observation.
        @(negedge clk);
        activation_ar_monitor = 1'b1;
        reset_scoreboard();
        send_command(score_id, score_vd, m, descriptor_base, activation_base);
        if (ordinal == 0 && $test$plusargs("QBS_PROJECTION_INJECT_COUNTER_X"))
          force fp_uop_issue = 32'bx;
        wait_success(case_id);
        if (activation_access !== access_mode ||
            result_fflags !== expected_flags[4:0] ||
            commit_aggregate_words != context_commit_words ||
            commit_word_count != context_commit_words || unexpected_write_count != 0 ||
            tiles_computed != expected_tiles || weight_bytes != expected_weight_bytes ||
            activation_bytes != expected_activation_bytes ||
            useful_pairs != expected_useful_pairs || pair_capacity != expected_pair_capacity ||
            dot_active_cycles != expected_dot_cycles || fp_uop_issue != expected_fp_uops ||
            accumulator_updates != expected_updates || context_validation_fault_count != 0 ||
            context_fill_count != (ordinal == 0 ? 1 : 0) ||
            context_reuse_count != (ordinal == 0 ? 0 : 1) ||
            context_reuse_block_count != (ordinal == 0 ? 0 : k_blocks) ||
            context_read_bytes != expected_activation_bytes - external_activation_bytes ||
            activation_axi_bytes_saved != expected_activation_bytes - external_activation_bytes ||
            activation_ar_count != (ordinal == 0 ? direct_activation_ar_count : 0) ||
            read_payload_bytes != QbsDescriptorBytes + expected_weight_bytes + external_activation_bytes ||
            read_range_count != (ordinal == 0 ? expected_ranges : 1 + expected_weight_ranges) ||
            dut.i_activation_context.context_valid_q !== (ordinal != case_count - 1) ||
            phase_setup_cycles + phase_activation_cycles + phase_weight_cycles +
                phase_compute_cycles + phase_overlap_cycles + phase_drain_cycles +
                phase_scheduler_cycles + phase_commit_cycles + phase_fault_cycles +
                phase_terminal_cycles != command_cycles + 1) begin
          $display("QBS projection mismatch access=%0d/%0d flags=%h/%h commit=%0d/%0d tiles=%0d/%0d W=%0d/%0d A=%0d/%0d",
                   activation_access, access_mode, result_fflags, expected_flags,
                   commit_aggregate_words, context_commit_words, tiles_computed, expected_tiles,
                   weight_bytes, expected_weight_bytes, activation_bytes, expected_activation_bytes);
          $display("QBS projection mismatch AR=%0d/%0d ranges=%0d/%0d payload=%0d/%0d fill=%0d reuse=%0d blocks=%0d read=%0d saved=%0d valid=%b busy=%b",
                   activation_ar_count, ordinal == 0 ? direct_activation_ar_count : 0,
                   read_range_count, ordinal == 0 ? expected_ranges : 1 + expected_weight_ranges,
                   read_payload_bytes, QbsDescriptorBytes + expected_weight_bytes + external_activation_bytes,
                   context_fill_count, context_reuse_count, context_reuse_block_count,
                   context_read_bytes, activation_axi_bytes_saved,
                   dut.i_activation_context.context_valid_q, dut.context_replay_busy);
          $display("QBS projection mismatch pairs=%0d/%0d capacity=%0d/%0d dot=%0d/%0d fp=%0d/%0d updates=%0d/%0d phases=%0d/%0d",
                   useful_pairs, expected_useful_pairs, pair_capacity, expected_pair_capacity,
                   dot_active_cycles, expected_dot_cycles, fp_uop_issue, expected_fp_uops,
                   accumulator_updates, expected_updates,
                   phase_setup_cycles + phase_activation_cycles + phase_weight_cycles +
                     phase_compute_cycles + phase_overlap_cycles + phase_drain_cycles +
                     phase_scheduler_cycles + phase_commit_cycles + phase_fault_cycles + phase_terminal_cycles,
                   command_cycles + 1);
          $fatal(1, "projection context command/counters mismatch tile=%0d access=%0d", ordinal, access_mode);
        end
        projection_context_cycles += command_cycles;
        projection_context_payload += read_payload_bytes;
        projection_saved_bytes += activation_axi_bytes_saved;
        $display("QBS projection tile PASS tile=%0d access=%0d M=%0d N=%0d Kb=%0d cycles=%0d payload=%0d saved=%0d",
                 ordinal, access_mode, m, n, k_blocks, command_cycles,
                 read_payload_bytes, activation_axi_bytes_saved);
        acknowledge_terminal();
        activation_ar_monitor = 1'b0;
      end

      if ((ordinal == 0 && !functional_only) || context_suite) begin
        const integer context_generation = 8'h35;
        integer expected_weight_ranges;
        integer context_block_bytes;
        integer context_commit_words;
        integer fill_cycles, reuse_cycles;
        byte unsigned activation_snapshot[];
        expected_weight_ranges = weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR
            ? ((n + 3) / 4) * k_blocks : n * k_blocks;
        context_block_bytes = expected_activation_bytes / k_blocks;
        context_commit_words = m * (m > 4 ? ((n + 7) / 8) : WordsPerRegister);
        activation_snapshot = new[expected_activation_bytes];
        for (int byte_index = 0; byte_index < expected_activation_bytes; byte_index++)
          activation_snapshot[byte_index] = memory[longint'(activation_base + byte_index)];

        // Fault the second activation block, then replay the original command.
        // Keep the same vectors and strict VRF scoreboard across all trials.
        for (int kind = 0; kind < 3; kind++) begin
          // PMA covers the aligned AXI footprint, including the first
          // block's trailing bytes. Place its fault beyond that footprint.
          inject_fault_start = activation_base + context_block_bytes +
              (kind == 1 ? BeatBytes : 0);
          inject_fault_end = inject_fault_start + 1;
          translation_enable = kind == 0;
          inject_mmu_fault = kind == 0;
          inject_pma_fault = kind == 1;
          inject_axi_fault = kind == 2;
          reset_scoreboard();
          send_command(score_id, score_vd, m, descriptor_base, activation_base);
          expect_fault(1'b0, QBS_VALIDATION_OK,
                       kind == 0 ? QBS_READ_FAULT_MMU :
                       kind == 1 ? QBS_READ_FAULT_PMA : QBS_READ_FAULT_AXI_RESPONSE,
                       activation_base + context_block_bytes);
          inject_mmu_fault = 1'b0;
          inject_pma_fault = 1'b0;
          inject_axi_fault = 1'b0;
          translation_enable = 1'b0;
          reset_scoreboard();
          send_command(score_id, score_vd, m, descriptor_base, activation_base);
          wait_success(200 + kind);
          if (result_fflags != expected_flags[4:0] ||
              commit_aggregate_words != context_commit_words ||
              unexpected_write_count != 0 || read_payload_bytes !=
                  QbsDescriptorBytes + expected_weight_bytes + expected_activation_bytes)
            $fatal(1, "QBS fault recovery mismatch flags=%h/%h commit=%0d/%0d payload=%0d/%0d unexpected=%0d",
                   result_fflags, expected_flags[4:0], commit_aggregate_words,
                   context_commit_words, read_payload_bytes,
                   QbsDescriptorBytes + expected_weight_bytes + expected_activation_bytes,
                   unexpected_write_count);
          acknowledge_terminal();
          $display("QBS next-block fault/replay PASS kind=%0d", kind);
        end

        begin
          integer reset_wait;
          reset_scoreboard();
          send_command(score_id, score_vd, m, descriptor_base, activation_base);
          reset_wait = 0;
          while (!(dut.compute_activation_write_valid &&
                   dut.compute_activation_write_k == 1) && reset_wait < 20000) begin
            @(negedge clk);
            reset_wait++;
          end
          if (reset_wait == 20000) $fatal(1, "No activation response before reset");
          @(negedge clk);
          rst_n = 1'b0;
          repeat (2) @(negedge clk);
          rst_n = 1'b1;
          reset_scoreboard();
          send_command(score_id, score_vd, m, descriptor_base, activation_base);
          wait_success(203);
          if (result_fflags != expected_flags[4:0] ||
              commit_aggregate_words != context_commit_words || unexpected_write_count != 0)
            $fatal(1, "QBS activation reset/replay changed results");
          acknowledge_terminal();
          $display("QBS next-block reset/replay PASS");
        end

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_FILL, 0,
            context_generation);
        monitored_activation_base = activation_base;
        monitored_activation_end = activation_base + expected_activation_bytes;
        activation_ar_monitor = 1'b1;
        reset_scoreboard();
        send_command(score_id, score_vd, m, descriptor_base,
                     activation_base);
        wait_success(100);
        fill_cycles = command_cycles;
        if (activation_access != QBS_ACTIVATION_ACCESS_FILL ||
            context_fill_count != 1 || context_reuse_count != 0 ||
            context_read_bytes != 0 || activation_axi_bytes_saved != 0 ||
            activation_ar_count != (context_suite ? direct_activation_ar_count : k_blocks) ||
            result_fflags != expected_flags[4:0] ||
            read_payload_bytes != QbsDescriptorBytes + expected_weight_bytes + expected_activation_bytes ||
            commit_aggregate_words != context_commit_words ||
            unexpected_write_count != 0)
          $fatal(1, "QBS FILL counters or result mismatch");
        acknowledge_terminal();
        activation_ar_monitor = 1'b0;

        // A DIRECT command may use the datapath but must not replace the saved tile.
        install_descriptor(descriptor_base, weight_base, QbsDescriptorVersion,
                           profile, weight_layout, activation_layout, n, k_blocks);
        reset_scoreboard();
        send_command(score_id, score_vd, m, descriptor_base, activation_base);
        wait_success(104);
        if (result_fflags != expected_flags[4:0] || unexpected_write_count != 0 ||
            commit_aggregate_words != context_commit_words ||
            !dut.i_activation_context.context_valid_q)
          $fatal(1, "DIRECT corrupted the resident context or result");
        acknowledge_terminal();
        // REUSE must not depend on the original bytes after a committed FILL.
        for (int byte_index = 0; byte_index < expected_activation_bytes; byte_index++)
          memory[longint'(activation_base + byte_index)] = 8'ha5;
        memory_epoch++;

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, QbsActivationContextMaxKBlocks + 1,
            QBS_ACTIVATION_ACCESS_FILL, 0, context_generation + 1);
        score_commit = 1'b0;
        reset_scoreboard();
        send_command(13, score_vd, m, descriptor_base,
                     64'hffff_ffff_ffff_ffff);
        expect_fault(1'b1, QBS_VALIDATION_CONTEXT_UNSUPPORTED,
                     QBS_READ_FAULT_NONE, descriptor_base);
        if (read_range_count != 1 || context_validation_fault_count != 0)
          $fatal(1, "invalid FILL accessed payload or changed lookup counters");
        if (!dut.i_activation_context.context_valid_q ||
            dut.i_activation_context.context_generation_q !==
                context_generation[7:0] ||
            dut.i_activation_context.context_k_blocks_q !== k_blocks[8:0])
          $fatal(1, "invalid FILL changed the committed activation context");

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_REUSE, 0,
            context_generation + 1);
        score_commit = 1'b0;
        reset_scoreboard();
        send_command(13, score_vd, m, descriptor_base, 64'hffff_ffff_ffff_ffff);
        expect_fault(1'b1, QBS_VALIDATION_CONTEXT_GENERATION,
                     QBS_READ_FAULT_NONE, descriptor_base);
        if (context_validation_fault_count != 1 || read_range_count != 1)
          $fatal(1, "stale context fault accessed payload or was not counted");
        if (!dut.i_activation_context.context_valid_q ||
            dut.i_activation_context.context_generation_q !==
                context_generation[7:0] ||
            dut.i_activation_context.context_k_blocks_q !== k_blocks[8:0])
          $fatal(1, "stale REUSE changed the committed activation context");

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks - 1,
            QBS_ACTIVATION_ACCESS_REUSE, 0, context_generation);
        if (memory_u64(descriptor_base) !== context_descriptor_header(
                profile, weight_layout, activation_layout, n, k_blocks - 1,
                QBS_ACTIVATION_ACCESS_REUSE, 0, context_generation))
          $fatal(1, "metadata-mismatch descriptor was not installed exactly");
        reset_scoreboard();
        send_command(13, score_vd, m, descriptor_base,
                     64'hffff_ffff_ffff_ffff);
        expect_fault(1'b1, QBS_VALIDATION_CONTEXT_METADATA,
                     QBS_READ_FAULT_NONE, descriptor_base);
        if (context_validation_fault_count != 1 || read_range_count != 1)
          $fatal(1, "metadata mismatch accessed payload or was not counted");

        // A failed consume must stop replay without retiring the saved tile.
        // Probe both REUSE and RELEASE; successful REUSE retries check every
        // result against the original FILL input, now poisoned in memory.
        for (int release_mode = 0; release_mode < 2; release_mode++) begin
          for (int kind = 0; kind < 3; kind++) begin
            install_context_descriptor(
                descriptor_base, weight_base, profile, weight_layout,
                activation_layout, n, k_blocks,
                release_mode ? QBS_ACTIVATION_ACCESS_RELEASE : QBS_ACTIVATION_ACCESS_REUSE,
                0, context_generation);
            score_commit = 1'b0;
            inject_fault_start = weight_base;
            inject_fault_end = weight_base + 1;
            translation_enable = kind == 0;
            inject_mmu_fault = kind == 0;
            inject_pma_fault = kind == 1;
            inject_axi_fault = kind == 2;
            reset_scoreboard();
            send_command(score_id, score_vd, m, descriptor_base, activation_base);
            expect_fault(1'b0, QBS_VALIDATION_OK,
                         kind == 0 ? QBS_READ_FAULT_MMU :
                         kind == 1 ? QBS_READ_FAULT_PMA : QBS_READ_FAULT_AXI_RESPONSE,
                         weight_base);
            if (dut.context_replay_busy !== 1'b0 ||
                dut.i_activation_context.context_valid_q !== 1'b1 ||
                dut.i_activation_context.context_generation_q !== context_generation[7:0])
              $fatal(1, "context fault left replay busy or changed saved tile M=%0d kind=%0d release=%0d busy=%b overlap=%b",
                     m, kind, release_mode, dut.context_replay_busy, fault_replay_overlap_seen);
            if (m >= 4 && context_block_bytes >= 1000 && !fault_replay_overlap_seen)
              $fatal(1, "wide context fault did not interrupt active replay");
            inject_mmu_fault = 1'b0;
            inject_pma_fault = 1'b0;
            inject_axi_fault = 1'b0;
            translation_enable = 1'b0;
            install_context_descriptor(
                descriptor_base, weight_base, profile, weight_layout,
                activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_REUSE,
                0, context_generation);
            score_commit = 1'b1;
            reset_scoreboard();
            send_command(score_id, score_vd, m, descriptor_base, activation_base);
            wait_success(300 + 3 * release_mode + kind);
            if (result_fflags !== expected_flags[4:0] ||
                commit_aggregate_words != context_commit_words || unexpected_write_count != 0 ||
                context_read_bytes != expected_activation_bytes ||
                read_payload_bytes != QbsDescriptorBytes + expected_weight_bytes)
              $fatal(1, "context weight-fault retry mismatch");
            acknowledge_terminal();
            $display("QBS context weight fault/retry PASS case=%0d release=%0d kind=%0d",
                     case_id, release_mode, kind);
          end
        end

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_REUSE, 0,
            context_generation);
        score_commit = 1'b1;
        monitored_activation_base = activation_base;
        monitored_activation_end = activation_base + expected_activation_bytes;
        activation_ar_monitor = 1'b1;
        reset_scoreboard();
        send_command(score_id, score_vd, m, descriptor_base,
                     activation_base);
        wait_success(101);
        reuse_cycles = command_cycles;
        if (activation_access != QBS_ACTIVATION_ACCESS_REUSE ||
            context_reuse_count != 1 ||
            context_reuse_block_count != k_blocks ||
            context_read_bytes != expected_activation_bytes ||
            activation_axi_bytes_saved != expected_activation_bytes ||
            activation_ar_count != 0 ||
            read_range_count != 1 + expected_weight_ranges ||
            read_payload_bytes != 16 + expected_weight_bytes ||
            commit_aggregate_words != context_commit_words ||
            result_fflags != expected_flags[4:0] ||
            unexpected_write_count != 0)
          $fatal(1, "QBS REUSE did not eliminate activation AXI traffic");
        acknowledge_terminal();
        activation_ar_monitor = 1'b0;

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_RELEASE, 0,
            context_generation);
        reset_scoreboard();
        send_command(score_id, score_vd, m, descriptor_base,
                     activation_base);
        wait_success(102);
        if (activation_access != QBS_ACTIVATION_ACCESS_RELEASE ||
            context_reuse_count != 1 ||
            context_reuse_block_count != k_blocks ||
            commit_aggregate_words != context_commit_words ||
            result_fflags != expected_flags[4:0] || unexpected_write_count != 0 ||
            context_read_bytes != expected_activation_bytes ||
            read_payload_bytes != QbsDescriptorBytes + expected_weight_bytes)
          $fatal(1, "QBS RELEASE did not consume the context correctly");
        acknowledge_terminal();

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_REUSE, 0,
            context_generation);
        score_commit = 1'b0;
        reset_scoreboard();
        send_command(0, score_vd, m, descriptor_base, activation_base);
        expect_fault(1'b1, QBS_VALIDATION_CONTEXT_INVALID,
                     QBS_READ_FAULT_NONE, descriptor_base);

        for (int byte_index = 0; byte_index < expected_activation_bytes; byte_index++)
          memory[longint'(activation_base + byte_index)] = activation_snapshot[byte_index];
        memory_epoch++;

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_FILL, 0,
            8'h40);
        score_commit = 1'b1;
        reset_scoreboard();
        send_command(score_id, score_vd, m, descriptor_base,
                     activation_base);
        wait_success(103);
        acknowledge_terminal();

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_FILL, 0,
            8'h41);
        score_commit = 1'b0;
        inject_axi_fault = 1'b1;
        inject_fault_start = activation_base;
        inject_fault_end = activation_base + expected_activation_bytes;
        reset_scoreboard();
        send_command(0, score_vd, m, descriptor_base, activation_base);
        expect_fault(1'b0, QBS_VALIDATION_OK,
                     QBS_READ_FAULT_AXI_RESPONSE, activation_base);
        inject_axi_fault = 1'b0;

        install_context_descriptor(
            descriptor_base, weight_base, profile, weight_layout,
            activation_layout, n, k_blocks, QBS_ACTIVATION_ACCESS_REUSE, 0,
            8'h40);
        reset_scoreboard();
        send_command(0, score_vd, m, descriptor_base, activation_base);
        expect_fault(1'b1, QBS_VALIDATION_CONTEXT_INVALID,
                     QBS_READ_FAULT_NONE, descriptor_base);
        $display("QBS activation context FILL/REUSE/RELEASE PASS case=%0d M=%0d Kb=%0d bytes=%0d fill_cycles=%0d reuse_cycles=%0d",
                 case_id, m, k_blocks, expected_activation_bytes, fill_cycles, reuse_cycles);
      end

      score_commit = 1'b0;
      repeat (2) @(posedge clk);
    end

    $fclose(fd);

    if (functional_only) begin
      if (total_errors != 0)
        $fatal(1, "QBS functional-only run failed with %0d errors",
               total_errors);
      if (projection_suite) begin
        if (projection_direct_payload - projection_context_payload != projection_saved_bytes ||
            dut.i_activation_context.context_valid_q !== 1'b0 ||
            dut.context_replay_busy !== 1'b0 || dut.context_replay_data_valid !== 1'b0)
          $fatal(1, "projection totals/release mismatch");
        $display("QBS projection PASS tiles=%0d M=%0d N=%0d Kb=%0d direct_cycles=%0d context_cycles=%0d direct_payload=%0d context_payload=%0d saved=%0d",
                 case_count, projection_m, projection_n * case_count, projection_k,
                 projection_direct_cycles, projection_context_cycles,
                 projection_direct_payload, projection_context_payload, projection_saved_bytes);
      end
      $display("QBS engine PASS: %0d functional cases", case_count);
      $finish;
    end

    // Descriptor validation failure: no compute or VRF activity may occur.
    memory.delete();
    install_descriptor(64'h3000, 64'h0010_0000,
                       QbsDescriptorVersion + 1,
                       QBS_WEIGHT_PROFILE_Q4_K,
                       QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                       QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 1);
    score_commit = 1'b0;
    reset_scoreboard();
    send_command(1, 0, 1, 64'h3000, 64'h0020_0000);
    expect_fault(1'b1, QBS_VALIDATION_DESCRIPTOR_VERSION,
                 QBS_READ_FAULT_NONE, 64'h3000);
    $display("QBS validation atomic-fault PASS");

    // MMU fault after compute command admission.
    memory.delete();
    install_descriptor(64'h4000, 64'h0010_0000, QbsDescriptorVersion,
                       QBS_WEIGHT_PROFILE_Q4_K,
                       QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                       QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 1);
    translation_enable = 1'b1;
    inject_mmu_fault = 1'b1;
    inject_fault_start = 64'h0020_0000;
    inject_fault_end = 64'h0020_1000;
    reset_scoreboard();
    send_command(2, 0, 1, 64'h4000, 64'h0020_0000);
    expect_fault(1'b0, QBS_VALIDATION_OK, QBS_READ_FAULT_MMU,
                 64'h0020_0000);
    if (!fault_mmu_exception.valid || fault_mmu_exception.cause != 13)
      $fatal(1, "QBS MMU exception metadata was not preserved");
    inject_mmu_fault = 1'b0;
    translation_enable = 1'b0;
    $display("QBS MMU atomic-fault PASS");

    // AXI response and PMA failures exercise the same post-admission drain.
    memory.delete();
    install_descriptor(64'h5000, 64'h0010_0000, QbsDescriptorVersion,
                       QBS_WEIGHT_PROFILE_Q4_K,
                       QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                       QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 1);
    inject_axi_fault = 1'b1;
    inject_fault_start = 64'h0020_0000;
    inject_fault_end = 64'h0020_1000;
    reset_scoreboard();
    send_command(3, 0, 1, 64'h5000, 64'h0020_0000);
    expect_fault(1'b0, QBS_VALIDATION_OK, QBS_READ_FAULT_AXI_RESPONSE,
                 64'h0020_0000);
    inject_axi_fault = 1'b0;
    $display("QBS AXI atomic-fault PASS");

    memory.delete();
    install_descriptor(64'h6000, 64'h0010_0000, QbsDescriptorVersion,
                       QBS_WEIGHT_PROFILE_Q4_K,
                       QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                       QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 1);
    inject_pma_fault = 1'b1;
    inject_fault_start = 64'h0020_0000;
    inject_fault_end = 64'h0020_1000;
    reset_scoreboard();
    send_command(4, 0, 1, 64'h6000, 64'h0020_0000);
    expect_fault(1'b0, QBS_VALIDATION_OK, QBS_READ_FAULT_PMA,
                 64'h0020_0000);
    inject_pma_fault = 1'b0;
    $display("QBS PMA atomic-fault PASS");

    if (total_errors != 0)
      $fatal(1, "QBS end-to-end engine failed with %0d errors", total_errors);
    if (!saw_dual_read_outstanding || !saw_read_outstanding_full)
      $fatal(1, "QBS end-to-end cases did not exercise the full read window");
    if (mmu_is_store)
      $fatal(1, "QBS requested a store translation");
    $display("QBS engine PASS: %0d functional cases plus four fault classes",
             case_count);
    $finish;
  end

endmodule : qbs_engine_tb
