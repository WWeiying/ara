`timescale 1ns/1ps

// Observation only. Inputs are sampled before the DUT's accepting edge/NBA.
module akv_legacy_latency_monitor (
  input logic clk, rst_n,
  input logic command_valid, command_ready,
  input akv_pkg::akv_command_e command,
  input logic [3:0] command_id,
  input logic [4:0] command_vd,
  input logic [15:0] command_head_dim,
  input logic [63:0] command_descriptor_address, command_tile_start, command_selector,
  input logic [2:0] command_column_count,
  input logic translation_enable,
  input logic success_valid, fault_valid, terminal_ready, context_ready,
  input logic fault_is_validation,
  input akv_pkg::akv_validation_error_e validation_error,
  input qbs_pkg::qbs_read_fault_e read_fault_kind,
  input logic [63:0] fault_vaddr,
  input logic mmu_valid,
  input logic [63:0] mmu_cause, mmu_tval,
  input logic [30:0][31:0] stats
);
  localparam string Names [31] = '{
    "command_cycles", "full_count", "refill_count", "load_count", "release_count",
    "v2_full_count", "v2_refill_count", "v2_row_load_count", "v2_column_load_count",
    "v2_column_panel_count", "v2_logical_column_count", "v2_k_view_bank_cycles",
    "v2_bank_conflict_cycles", "v2_rejected_count", "q_external_bytes", "kv_external_bytes",
    "replay_bytes", "replay_backpressure_cycles", "read_range_count", "read_translation_count",
    "read_ar_count", "read_beat_count", "read_payload_bytes", "read_store_wait_cycles",
    "read_backpressure_cycles", "read_outstanding_occupancy_sum", "read_outstanding_max",
    "read_outstanding_full_cycles", "aggregate_write_count", "early_ack_count", "busy"
  };
  clocking sampled @(posedge clk);
    default input #1step;
    input rst_n, command_valid, command_ready, command, command_id, command_vd;
    input command_head_dim, command_descriptor_address, command_tile_start, command_selector;
    input command_column_count, translation_enable, success_valid, fault_valid, terminal_ready;
    input context_ready, fault_is_validation, validation_error, read_fault_kind, fault_vaddr;
    input mmu_valid, mmu_cause, mmu_tval, stats;
  endclocking

  longint unsigned tick = 0, accepted = 0, completed = 0, errors = 0;
  longint unsigned accept_tick, first_tick;
  bit active = 0, seen_valid = 0;
  logic [1:0] first_outcome;
  logic [2:0] saved_command, saved_columns;
  logic [3:0] saved_id;
  logic [4:0] saved_vd;
  logic [15:0] saved_dim;
  logic [63:0] saved_descriptor, saved_tile, saved_selector;
  logic saved_translation;

  task automatic error(input string reason);
    errors++;
    $display("AKV_LATENCY_ERROR %s", reason);
  endtask

  initial $display("AKV_LATENCY_BEGIN version=1");

  always @(sampled) begin
    tick++;
    if (sampled.rst_n !== 1'b1) begin
      if (accepted != 0) error("reset after first acceptance");
    end else begin
      if ($isunknown({sampled.command_valid, sampled.command_ready,
                      sampled.success_valid, sampled.fault_valid, sampled.terminal_ready}))
        error("unknown handshake");
      if (sampled.command_valid && sampled.command_ready) begin
        if (active) error("overlapping commands");
        if ($isunknown({sampled.command, sampled.command_id, sampled.command_vd,
                        sampled.command_head_dim, sampled.command_descriptor_address,
                        sampled.command_tile_start, sampled.command_selector,
                        sampled.command_column_count, sampled.translation_enable}))
          error("unknown accepted metadata");
        accepted++;
        active = 1;
        seen_valid = 0;
        accept_tick = tick;
        saved_command = sampled.command;
        saved_id = sampled.command_id;
        saved_vd = sampled.command_vd;
        saved_dim = sampled.command_head_dim;
        saved_descriptor = sampled.command_descriptor_address;
        saved_tile = sampled.command_tile_start;
        saved_selector = sampled.command_selector;
        saved_columns = sampled.command_column_count;
        saved_translation = sampled.translation_enable;
      end
      if (sampled.success_valid || sampled.fault_valid) begin
        if (!active || (sampled.success_valid && sampled.fault_valid))
          error("unowned or ambiguous terminal");
        if (!seen_valid) begin
          first_tick = tick;
          first_outcome = {sampled.success_valid, sampled.fault_valid};
          seen_valid = 1;
        end else if ({sampled.success_valid, sampled.fault_valid} !== first_outcome)
          error("terminal changed under hold");
        if (sampled.terminal_ready) begin
          if ($isunknown({sampled.context_ready, sampled.stats})) error("unknown terminal counters");
          if (sampled.fault_valid && $isunknown({sampled.fault_is_validation,
                sampled.validation_error, sampled.read_fault_kind, sampled.fault_vaddr}))
            error("unknown valid fault metadata");
          if (sampled.fault_valid && !sampled.fault_is_validation &&
              sampled.read_fault_kind == qbs_pkg::QBS_READ_FAULT_MMU &&
              $isunknown({sampled.mmu_valid, sampled.mmu_cause, sampled.mmu_tval}))
            error("unknown MMU exception metadata");
          $write({"AKV_LATENCY_COMMAND seq=%0d command=%0d id=%0d vd=%0d dim=%0d ",
                  "descriptor=%016h tile=%016h selector=%016h columns=%0d translation=%0d ",
                  "accept=%0d first=%0d fire=%0d first_latency=%0d fire_latency=%0d wait_cycles=%0d ",
                  "success=%0d fault=%0d context_ready=%0d validation=%0d validation_error=%0d ",
                  "read_fault_kind=%0d fault_vaddr=%016h mmu_valid=%0d mmu_cause=%016h mmu_tval=%016h"},
            accepted, saved_command, saved_id, saved_vd, saved_dim, saved_descriptor,
            saved_tile, saved_selector, saved_columns, saved_translation,
            accept_tick, first_tick, tick, first_tick-accept_tick, tick-accept_tick, tick-first_tick,
            sampled.success_valid, sampled.fault_valid, sampled.context_ready,
            sampled.fault_valid ? sampled.fault_is_validation : 1'b0,
            sampled.fault_valid ? sampled.validation_error : 5'b0,
            sampled.fault_valid ? sampled.read_fault_kind : 3'b0,
            sampled.fault_valid ? sampled.fault_vaddr : 64'b0,
            (sampled.fault_valid && !sampled.fault_is_validation && sampled.read_fault_kind == qbs_pkg::QBS_READ_FAULT_MMU) ? sampled.mmu_valid : 1'b0,
            (sampled.fault_valid && !sampled.fault_is_validation && sampled.read_fault_kind == qbs_pkg::QBS_READ_FAULT_MMU) ? sampled.mmu_cause : 64'b0,
            (sampled.fault_valid && !sampled.fault_is_validation && sampled.read_fault_kind == qbs_pkg::QBS_READ_FAULT_MMU) ? sampled.mmu_tval : 64'b0);
          for (int i = 0; i < 31; i++) $write(" %s=%0d", Names[i], sampled.stats[30-i]);
          $write("\n");
          completed++;
          active = 0;
          seen_valid = 0;
        end
      end else if (active && seen_valid) error("terminal disappeared before acceptance");
    end
  end

  final $display("AKV_LATENCY_SUMMARY version=1 accepted=%0d completed=%0d pending=%0d errors=%0d",
                 accepted, completed, active, errors);
endmodule

bind akv_engine_tb akv_legacy_latency_monitor i_latency_monitor (
  .mmu_valid(fault_mmu_exception.valid), .mmu_cause(fault_mmu_exception.cause),
  .mmu_tval(fault_mmu_exception.tval),
  .stats({command_cycles, full_count, refill_count, load_count, release_count,
    v2_full_count, v2_refill_count, v2_row_load_count, v2_column_load_count,
    v2_column_panel_count, v2_logical_column_count, v2_k_view_bank_cycles,
    v2_bank_conflict_cycles, v2_rejected_count, q_external_bytes, kv_external_bytes,
    replay_bytes, replay_backpressure_cycles, read_range_count, read_translation_count,
    read_ar_count, read_beat_count, read_payload_bytes, read_store_wait_cycles,
    read_backpressure_cycles, read_outstanding_occupancy_sum, 32'(read_outstanding_max),
    read_outstanding_full_cycles, 32'(aggregate_write_count), 32'(early_ack_count), 32'(busy)}),
  .*
);
