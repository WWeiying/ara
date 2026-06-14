// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Mock host core for the standalone HDV prototype.  The block models only the
// host responsibilities that are required to keep the HDV task mechanism live:
// program the task CSRs, accept HEU scalar/vector dispatch handshakes with a
// fixed latency model, count execute-packet completions, and report task
// completion or failure back to hdv_top.

module hdv_mock_host_core import hdv_pkg::*; #(
  parameter int unsigned XLEN                         = 64,
  parameter int unsigned ScalarLatency                = 1,
  parameter int unsigned VectorLatency                = 1,
  parameter bit          AutoStart                    = 1'b0,
  parameter int unsigned AutoStartDelay               = 32,
  parameter logic [XLEN-1:0] AutoTaskEntry            = '0,
  parameter logic [XLEN-1:0] AutoTaskDesc             = '0,
  parameter logic [31:0] AutoExpectedExecutePackets   = 32'd1,
  parameter int unsigned TaskWatchdogCycles           = 4096,
  parameter int unsigned PacketWatchdogCycles         = 1024,
  parameter type addr_t                               = logic [XLEN-1:0]
) (
  input  logic                         clk_i,
  input  logic                         rst_ni,
  input  logic                         flush_i,

  // HDV task CSR port.
  output logic                         csr_valid_o,
  output logic                         csr_write_o,
  output logic [11:0]                  csr_addr_o,
  output logic [XLEN-1:0]              csr_wdata_o,
  input  logic                         csr_ready_i,
  input  logic [XLEN-1:0]              csr_rdata_i,
  input  logic                         csr_error_i,

  // HDV task status.
  input  logic                         task_busy_i,
  input  logic                         task_done_i,
  input  logic                         task_error_i,
  output logic                         task_complete_o,
  output logic                         task_error_o,

  // HEU scalar pipeline handshake.
  input  logic                         scalar_valid_i,
  output logic                         scalar_ready_o,
  output logic                         scalar_done_o,

  // HEU vector pipeline handshake.
  input  logic                         vector_valid_i,
  output logic                         vector_ready_o,
  output logic                         vector_done_o,

  // HEU execute-packet status.
  input  logic                         execute_done_i,
  input  logic                         execute_error_i,
  output logic                         backend_error_o
);

  typedef enum logic [3:0] {
    IDLE,
    WRITE_TASK_ADDR,
    WRITE_TASK_DESC,
    CLEAR_STATUS,
    WRITE_START,
    RUN,
    COMPLETE_TASK,
    WAIT_TASK_STATUS,
    READ_STATUS,
    FINISH,
    FAIL
  } state_e;

  localparam int unsigned ScalarCntWidth = (ScalarLatency > 1) ? $clog2(ScalarLatency + 1) : 1;
  localparam int unsigned VectorCntWidth = (VectorLatency > 1) ? $clog2(VectorLatency + 1) : 1;
  localparam int unsigned AutoStartCntWidth = (AutoStartDelay > 1) ? $clog2(AutoStartDelay + 1) : 1;
  localparam int unsigned TaskWatchdogWidth = (TaskWatchdogCycles > 1) ? $clog2(TaskWatchdogCycles + 1) : 1;
  localparam int unsigned PacketWatchdogWidth = (PacketWatchdogCycles > 1) ? $clog2(PacketWatchdogCycles + 1) : 1;

  state_e state_d, state_q;
  addr_t task_entry_d, task_entry_q;
  addr_t task_desc_d, task_desc_q;
  logic [31:0] expected_packets_d, expected_packets_q;
  logic [31:0] completed_packets_d, completed_packets_q;
  logic [ScalarCntWidth-1:0] scalar_count_d, scalar_count_q;
  logic [VectorCntWidth-1:0] vector_count_d, vector_count_q;
  logic [AutoStartCntWidth-1:0] auto_start_count_d, auto_start_count_q;
  logic [TaskWatchdogWidth-1:0] task_watchdog_d, task_watchdog_q;
  logic [PacketWatchdogWidth-1:0] packet_watchdog_d, packet_watchdog_q;
  logic scalar_pending_d, scalar_pending_q;
  logic vector_pending_d, vector_pending_q;
  logic auto_start_armed_d, auto_start_armed_q;
  logic csr_fire;
  logic scalar_fire;
  logic vector_fire;
  logic auto_start_pulse;
  logic expected_reached;
  logic task_active;
  logic task_timeout;
  logic packet_timeout;

  assign csr_fire    = csr_valid_o & csr_ready_i;
  assign scalar_fire = scalar_valid_i & scalar_ready_o;
  assign vector_fire = vector_valid_i & vector_ready_o;
  assign auto_start_pulse = AutoStart
                          & auto_start_armed_q
                          & (auto_start_count_q >= AutoStartCntWidth'(AutoStartDelay));
  assign task_active = (state_q != IDLE) & (state_q != FINISH) & (state_q != FAIL);
  assign task_timeout = (TaskWatchdogCycles != 0)
                      & task_active
                      & (task_watchdog_q >= TaskWatchdogWidth'(TaskWatchdogCycles));
  assign packet_timeout = (PacketWatchdogCycles != 0)
                        & (state_q == RUN)
                        & (packet_watchdog_q >= PacketWatchdogWidth'(PacketWatchdogCycles));

  assign backend_error_o = 1'b0;
  assign scalar_ready_o  = (state_q == RUN) & !scalar_pending_q;
  assign vector_ready_o  = (state_q == RUN) & !vector_pending_q;
  assign scalar_done_o   = scalar_pending_q & (scalar_count_q == '0);
  assign vector_done_o   = vector_pending_q & (vector_count_q == '0);

  always_comb begin : p_csr_drive
    csr_valid_o = 1'b0;
    csr_write_o = 1'b1;
    csr_addr_o  = HDV_CSR_VTASK_ADDR;
    csr_wdata_o = '0;

    unique case (state_q)
      WRITE_TASK_ADDR: begin
        csr_valid_o = 1'b1;
        csr_addr_o  = HDV_CSR_VTASK_ADDR;
        csr_wdata_o = task_entry_q;
      end
      WRITE_TASK_DESC: begin
        csr_valid_o = 1'b1;
        csr_addr_o  = HDV_CSR_VTASK_PADDR;
        csr_wdata_o = task_desc_q;
      end
      CLEAR_STATUS: begin
        csr_valid_o = 1'b1;
        csr_addr_o  = HDV_CSR_VTASK_STATUS;
        csr_wdata_o = XLEN'(64'h6);
      end
      WRITE_START: begin
        csr_valid_o = 1'b1;
        csr_addr_o  = HDV_CSR_VTASK_START;
        csr_wdata_o = XLEN'(64'h1);
      end
      READ_STATUS: begin
        csr_valid_o = 1'b1;
        csr_write_o = 1'b0;
        csr_addr_o  = HDV_CSR_VTASK_STATUS;
      end
      default: begin
      end
    endcase
  end

  always_comb begin : p_next
    state_d             = state_q;
    task_entry_d        = task_entry_q;
    task_desc_d         = task_desc_q;
    expected_packets_d  = expected_packets_q;
    completed_packets_d = completed_packets_q;
    auto_start_count_d  = auto_start_count_q;
    auto_start_armed_d  = auto_start_armed_q;
    scalar_pending_d    = scalar_pending_q;
    vector_pending_d    = vector_pending_q;
    scalar_count_d      = scalar_count_q;
    vector_count_d      = vector_count_q;
    task_watchdog_d     = task_watchdog_q;
    packet_watchdog_d   = packet_watchdog_q;
    task_complete_o     = 1'b0;
    task_error_o        = 1'b0;
    expected_reached    = 1'b0;

    if (AutoStart && auto_start_armed_q && (state_q == IDLE) && !auto_start_pulse) begin
      auto_start_count_d = auto_start_count_q + 1'b1;
    end

    if (task_active) begin
      task_watchdog_d = task_watchdog_q + 1'b1;
    end else begin
      task_watchdog_d = '0;
    end

    if (state_q == RUN) begin
      packet_watchdog_d = packet_watchdog_q + 1'b1;
    end else begin
      packet_watchdog_d = '0;
    end

    if (scalar_pending_q) begin
      if (scalar_count_q != '0) begin
        scalar_count_d = scalar_count_q - 1'b1;
      end else begin
        scalar_pending_d = 1'b0;
      end
    end

    if (vector_pending_q) begin
      if (vector_count_q != '0) begin
        vector_count_d = vector_count_q - 1'b1;
      end else begin
        vector_pending_d = 1'b0;
      end
    end

    if (scalar_fire) begin
      scalar_pending_d = 1'b1;
      scalar_count_d   = ScalarCntWidth'(ScalarLatency - 1);
    end

    if (vector_fire) begin
      vector_pending_d = 1'b1;
      vector_count_d   = VectorCntWidth'(VectorLatency - 1);
    end

    if (execute_done_i) begin
      completed_packets_d = completed_packets_q + 1'b1;
      packet_watchdog_d   = '0;
    end

    expected_reached = execute_done_i
                     & ((completed_packets_q + 1'b1) >= expected_packets_q)
                     & (expected_packets_q != '0);

    unique case (state_q)
      IDLE: begin
        if (auto_start_pulse) begin
          task_entry_d        = addr_t'(AutoTaskEntry);
          task_desc_d         = addr_t'(AutoTaskDesc);
          expected_packets_d  = AutoExpectedExecutePackets;
          completed_packets_d = '0;
          auto_start_armed_d  = 1'b0;
          state_d             = WRITE_TASK_ADDR;
        end
      end
      WRITE_TASK_ADDR: begin
        if (csr_fire) begin
          state_d = csr_error_i ? FAIL : WRITE_TASK_DESC;
        end
      end
      WRITE_TASK_DESC: begin
        if (csr_fire) begin
          state_d = csr_error_i ? FAIL : CLEAR_STATUS;
        end
      end
      CLEAR_STATUS: begin
        if (csr_fire) begin
          state_d = csr_error_i ? FAIL : WRITE_START;
        end
      end
      WRITE_START: begin
        if (csr_fire) begin
          state_d = csr_error_i ? FAIL : RUN;
        end
      end
      RUN: begin
        if (task_error_i || execute_error_i || packet_timeout) begin
          task_error_o = 1'b1;
          state_d      = READ_STATUS;
        end else if (expected_reached) begin
          state_d = COMPLETE_TASK;
        end
      end
      COMPLETE_TASK: begin
        task_complete_o = 1'b1;
        state_d         = WAIT_TASK_STATUS;
      end
      WAIT_TASK_STATUS: begin
        if (task_done_i || task_error_i || !task_busy_i) begin
          state_d = READ_STATUS;
        end
      end
      READ_STATUS: begin
        if (csr_fire) begin
          state_d = (csr_rdata_i[2] | csr_error_i) ? FAIL : FINISH;
        end
      end
      FINISH: begin
        state_d = FINISH;
      end
      FAIL: begin
        state_d = FAIL;
      end
      default: begin
        state_d = IDLE;
      end
    endcase

    if (task_timeout) begin
      task_error_o = 1'b1;
      state_d      = FAIL;
    end

    if (flush_i) begin
      state_d             = IDLE;
      completed_packets_d = '0;
      auto_start_count_d  = '0;
      auto_start_armed_d  = AutoStart;
      scalar_pending_d    = 1'b0;
      vector_pending_d    = 1'b0;
      scalar_count_d      = '0;
      vector_count_d      = '0;
      task_watchdog_d     = '0;
      packet_watchdog_d   = '0;
      task_complete_o     = 1'b0;
      task_error_o        = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q             <= IDLE;
      task_entry_q        <= '0;
      task_desc_q         <= '0;
      expected_packets_q  <= '0;
      completed_packets_q <= '0;
      auto_start_count_q  <= '0;
      auto_start_armed_q  <= AutoStart;
      scalar_pending_q    <= 1'b0;
      vector_pending_q    <= 1'b0;
      scalar_count_q      <= '0;
      vector_count_q      <= '0;
      task_watchdog_q     <= '0;
      packet_watchdog_q   <= '0;
    end else begin
      state_q             <= state_d;
      task_entry_q        <= task_entry_d;
      task_desc_q         <= task_desc_d;
      expected_packets_q  <= expected_packets_d;
      completed_packets_q <= completed_packets_d;
      auto_start_count_q  <= auto_start_count_d;
      auto_start_armed_q  <= auto_start_armed_d;
      scalar_pending_q    <= scalar_pending_d;
      vector_pending_q    <= vector_pending_d;
      scalar_count_q      <= scalar_count_d;
      vector_count_q      <= vector_count_d;
      task_watchdog_q     <= task_watchdog_d;
      packet_watchdog_q   <= packet_watchdog_d;
    end
  end

  if (ScalarLatency == 0)
    $error("[hdv_mock_host_core] ScalarLatency must be at least 1.");

  if (VectorLatency == 0)
    $error("[hdv_mock_host_core] VectorLatency must be at least 1.");

endmodule : hdv_mock_host_core
