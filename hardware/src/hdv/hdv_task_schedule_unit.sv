// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// FIFO-backed Task Schedule Unit (TSU).  Tasks enter in host submission order
// and are dispatched one at a time to the Instruction Prefetch Unit.

module hdv_task_schedule_unit #(
  parameter int unsigned XLEN       = 64,
  parameter int unsigned QueueDepth = 4,
  parameter type addr_t = logic [XLEN-1:0]
) (
  input  logic  clk_i,
  input  logic  rst_ni,
  input  logic  flush_i,
  input  logic  testmode_i,
  input  logic  status_clear_i,

  input  logic  task_in_valid_i,
  output logic  task_in_ready_o,
  input  addr_t task_in_entry_i,
  input  addr_t task_in_desc_i,

  output logic  task_out_valid_o,
  input  logic  task_out_ready_i,
  output addr_t task_out_entry_o,
  output addr_t task_out_desc_o,

  input  logic  task_done_i,
  input  logic  task_error_i,
  output logic  busy_o,
  output logic  done_o,
  output logic  error_o
);

  typedef struct packed {
    addr_t entry;
    addr_t desc;
  } task_t;

  task_t fifo_in, fifo_out;
  logic  fifo_full, fifo_empty;
  logic  fifo_push, fifo_pop;
  logic  active_d, active_q;
  logic  done_d, done_q;
  logic  error_d, error_q;

  assign fifo_in = '{
    entry: task_in_entry_i,
    desc : task_in_desc_i
  };

  assign fifo_push       = task_in_valid_i & task_in_ready_o;
  assign fifo_pop        = task_out_valid_o & task_out_ready_i;
  assign task_in_ready_o = !fifo_full;

  assign task_out_valid_o = !fifo_empty & !active_q;
  assign task_out_entry_o = fifo_out.entry;
  assign task_out_desc_o  = fifo_out.desc;

  assign busy_o  = active_q | !fifo_empty;
  assign done_o  = done_q;
  assign error_o = error_q;

  fifo_v3 #(
    .FALL_THROUGH (1'b1),
    .DEPTH        (QueueDepth),
    .dtype        (task_t)
  ) i_task_queue (
    .clk_i     (clk_i),
    .rst_ni    (rst_ni),
    .flush_i    (flush_i),
    .testmode_i (testmode_i),
    .full_o     (fifo_full),
    .empty_o    (fifo_empty),
    .usage_o    (/* Unused */),
    .data_i     (fifo_in),
    .push_i     (fifo_push),
    .data_o     (fifo_out),
    .pop_i      (fifo_pop)
  );

  always_comb begin : p_next
    active_d = active_q;
    done_d   = done_q;
    error_d  = error_q;

    if (fifo_pop) begin
      active_d = 1'b1;
      done_d   = 1'b0;
      error_d  = 1'b0;
    end

    if (status_clear_i) begin
      done_d   = 1'b0;
      error_d  = 1'b0;
    end

    if (active_q && task_error_i) begin
      active_d = 1'b0;
      done_d   = 1'b0;
      error_d  = 1'b1;
    end else if (active_q && task_done_i) begin
      active_d = 1'b0;
      done_d   = 1'b1;
    end

    if (flush_i) begin
      active_d = 1'b0;
      done_d   = 1'b0;
      error_d  = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      active_q <= 1'b0;
      done_q   <= 1'b0;
      error_q  <= 1'b0;
    end else begin
      active_q <= active_d;
      done_q   <= done_d;
      error_q  <= error_d;
    end
  end

endmodule : hdv_task_schedule_unit
