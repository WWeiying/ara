// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Mock host core for the standalone HDV prototype.  The block models only the
// host responsibilities that are required to keep the HDV task mechanism live:
// program the task CSRs, accept HEU scalar/vector dispatch handshakes with a
// fixed latency model, count execute-packet backend accepts, and report task
// completion or failure back to hdv_top.

module hdv_mock_host_core import hdv_pkg::*; #(
  parameter int unsigned XLEN                         = 64,
  parameter int unsigned NumSlots                     = 8,
  parameter int unsigned ScalarLatency                = 1,
  parameter int unsigned VectorLatency                = 1,
  parameter bit          AutoStart                    = 1'b0,
  parameter int unsigned AutoStartDelay               = 32,
  parameter logic [XLEN-1:0] AutoTaskEntry            = '0,
  parameter logic [XLEN-1:0] AutoTaskDesc             = '0,
  parameter logic [31:0] AutoExpectedEpAcknowledges   = 32'd1,
  parameter bit          EnableMockBranch             = 1'b0,
  parameter int unsigned MockLoopIterations           = 1,
  parameter int unsigned TaskWatchdogCycles           = 4096,
  parameter int unsigned PacketWatchdogCycles         = 1024,
  parameter type addr_t                               = logic [XLEN-1:0]
) (
  input  logic                         clk_i,
  input  logic                         rst_ni,
  input  logic                         flush_i,

  // HDV task CSR port.
  output logic                         mock_hdv_csr_valid_o,
  output logic                         mock_hdv_csr_write_o,
  output logic [11:0]                  mock_hdv_csr_addr_o,
  output logic [XLEN-1:0]              mock_hdv_csr_wdata_o,
  input  logic                         hdv_mock_csr_ready_i,
  input  logic [XLEN-1:0]              hdv_mock_csr_rdata_i,
  input  logic                         hdv_mock_csr_error_i,

  // HDV task status.
  input  logic                         hdv_mock_task_busy_i,
  input  logic                         hdv_mock_task_done_i,
  input  logic                         hdv_mock_task_error_i,
  output logic                         mock_hdv_task_complete_o,
  output logic                         mock_hdv_task_error_o,

  // HEU scalar pipeline handshake.
  input  logic                         hdv_mock_scalar_valid_i,
  output logic                         mock_hdv_scalar_ready_o,
  output logic                         mock_hdv_scalar_ep_done_o,
  input  logic [NumSlots-1:0]          hdv_mock_scalar_insn_valid_i,
  input  logic [NumSlots-1:0][31:0]    hdv_mock_scalar_insn_i,
  input  logic [NumSlots-1:0]          hdv_mock_scalar_insn_is_32b_i,
  input  addr_t [NumSlots-1:0]         hdv_mock_scalar_insn_pc_i,
  output logic                         mock_hdv_redirect_valid_o,
  output addr_t                        mock_hdv_redirect_pc_o,
  output logic                         mock_hdv_loop_lock_o,

  // HEU vector pipeline handshake.
  input  logic                         hdv_mock_vector_valid_i,
  output logic                         mock_hdv_vector_ready_o,
  output logic                         mock_hdv_vector_ep_acknowledged_o,

  // HEU execute-packet acceptance status.
  input  logic                         hdv_mock_ep_acknowledged_i,
  input  logic                         hdv_mock_ep_error_i,
  output logic                         mock_hdv_backend_error_o
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

  state_e state_d, state_q;
  addr_t task_entry_d, task_entry_q;
  addr_t task_desc_d, task_desc_q;
  logic [31:0] expected_ep_acknowledges_d, expected_ep_acknowledges_q;
  logic [31:0] acknowledged_eps_d, acknowledged_eps_q;
`ifdef FOR_VERIFY
  // Runtime expected-EP override: +HDV_EXPECTED_EP=<N> sets the EP cap at which
  // the host auto-completes the task.  An AVL sweep passes a huge value so the
  // host waits for the kernel's natural `ret` instead of capping at the
  // compile-time AutoExpectedEpAcknowledges (derived from ELEMENTS, e.g. 1024).
  logic [31:0] hdv_ep_ovr;
  logic        hdv_ep_ovr_en;
  initial begin
    longint unsigned v;
    hdv_ep_ovr_en = 1'b0;
    if ($value$plusargs("HDV_EXPECTED_EP=%d", v)) begin
      hdv_ep_ovr_en = 1'b1; hdv_ep_ovr = v[31:0];
    end
  end
  // Runtime task-watchdog override: +HDV_TASK_WATCHDOG=<N> raises the total-task
  // cycle cap so quadratic-work kernels (vsgemm/vstrsm at large N) can finish.
  logic [31:0] hdv_wd_ovr;
  logic        hdv_wd_ovr_en;
  initial begin
    longint unsigned wv;
    hdv_wd_ovr_en = 1'b0;
    if ($value$plusargs("HDV_TASK_WATCHDOG=%d", wv)) begin
      hdv_wd_ovr_en = 1'b1; hdv_wd_ovr = wv[31:0];
    end
  end
  // Runtime packet-watchdog override: +HDV_PACKET_WATCHDOG=<N> raises the
  // inter-packet progress cap for legal long backend drain intervals.
  logic [31:0] hdv_packet_wd_ovr;
  logic        hdv_packet_wd_ovr_en;
  initial begin
    longint unsigned pwv;
    hdv_packet_wd_ovr_en = 1'b0;
    if ($value$plusargs("HDV_PACKET_WATCHDOG=%d", pwv)) begin
      hdv_packet_wd_ovr_en = 1'b1; hdv_packet_wd_ovr = pwv[31:0];
    end
  end
`endif
  logic [ScalarCntWidth-1:0] scalar_count_d, scalar_count_q;
  logic [VectorCntWidth-1:0] vector_count_d, vector_count_q;
  logic [AutoStartCntWidth-1:0] auto_start_count_d, auto_start_count_q;
  logic [31:0] task_watchdog_d, task_watchdog_q;
  logic [31:0] task_wd_limit;
  logic [31:0] packet_watchdog_d, packet_watchdog_q;
  logic [31:0] packet_wd_limit;
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
  logic branch_fire;
  logic branch_taken;
  logic branch_redirect_wait_d, branch_redirect_wait_q;
  logic branch_redirect_valid_d, branch_redirect_valid_q;
  addr_t branch_redirect_pc_d, branch_redirect_pc_q;
  logic [31:0] loop_iters_remaining_d, loop_iters_remaining_q;

  function automatic logic is_mock_bnez(input logic [31:0] insn);
    return (insn[6:0] == 7'b1100011) && (insn[14:12] == 3'b001) &&
           (insn[24:20] == 5'd0);
  endfunction

  function automatic addr_t branch_target(input addr_t pc, input logic [31:0] insn);
    logic [12:0] imm13;
    logic signed [XLEN-1:0] simm;
    imm13 = {insn[31], insn[7], insn[30:25], insn[11:8], 1'b0};
    simm  = {{(XLEN-13){imm13[12]}}, imm13};
    return pc + addr_t'(simm);
  endfunction

  assign csr_fire    = mock_hdv_csr_valid_o & hdv_mock_csr_ready_i;
  assign scalar_fire = hdv_mock_scalar_valid_i & mock_hdv_scalar_ready_o;
  assign vector_fire = hdv_mock_vector_valid_i & mock_hdv_vector_ready_o;
  assign auto_start_pulse = AutoStart
                          & auto_start_armed_q
                          & (auto_start_count_q >= AutoStartCntWidth'(AutoStartDelay));
  assign task_active = (state_q != IDLE) & (state_q != FINISH) & (state_q != FAIL);
`ifdef FOR_VERIFY
  assign task_wd_limit = hdv_wd_ovr_en ? hdv_wd_ovr : 32'(TaskWatchdogCycles);
  assign packet_wd_limit = hdv_packet_wd_ovr_en ? hdv_packet_wd_ovr :
                           32'(PacketWatchdogCycles);
`else
  assign task_wd_limit = 32'(TaskWatchdogCycles);
  assign packet_wd_limit = 32'(PacketWatchdogCycles);
`endif
  assign task_timeout = (task_wd_limit != 0)
                      & task_active
                      & (task_watchdog_q >= task_wd_limit);
  assign packet_timeout = (packet_wd_limit != 0)
                        & (state_q == RUN)
                        & (packet_watchdog_q >= packet_wd_limit);


  assign mock_hdv_backend_error_o = 1'b0;
  assign mock_hdv_scalar_ready_o  = (state_q == RUN) & !scalar_pending_q;
  assign mock_hdv_vector_ready_o  = (state_q == RUN) & !vector_pending_q;
  assign mock_hdv_scalar_ep_done_o   = scalar_pending_q & (scalar_count_q == '0);
  assign mock_hdv_vector_ep_acknowledged_o   = vector_pending_q & (vector_count_q == '0);
  assign mock_hdv_redirect_valid_o = branch_redirect_valid_q;
  assign mock_hdv_redirect_pc_o    = branch_redirect_pc_q;
  assign mock_hdv_loop_lock_o      = EnableMockBranch & (state_q == RUN) &
                                     (loop_iters_remaining_q > 32'd1);

  always_comb begin : p_branch_decode
    branch_fire  = 1'b0;
    branch_taken = 1'b0;
    branch_redirect_pc_d = branch_redirect_pc_q;

    if (EnableMockBranch && scalar_fire) begin
      for (int unsigned i = 0; i < NumSlots; i++) begin
        if (!branch_fire && hdv_mock_scalar_insn_valid_i[i] &&
            hdv_mock_scalar_insn_is_32b_i[i] &&
            is_mock_bnez(hdv_mock_scalar_insn_i[i])) begin
          branch_fire = 1'b1;
          branch_taken = (loop_iters_remaining_q > 32'd1);
          branch_redirect_pc_d = branch_target(hdv_mock_scalar_insn_pc_i[i],
                                               hdv_mock_scalar_insn_i[i]);
        end
      end
    end
  end

  always_comb begin : p_csr_drive
    mock_hdv_csr_valid_o = 1'b0;
    mock_hdv_csr_write_o = 1'b1;
    mock_hdv_csr_addr_o  = HDV_CSR_VTASK_ADDR;
    mock_hdv_csr_wdata_o = '0;

    unique case (state_q)
      WRITE_TASK_ADDR: begin
        mock_hdv_csr_valid_o = 1'b1;
        mock_hdv_csr_addr_o  = HDV_CSR_VTASK_ADDR;
        mock_hdv_csr_wdata_o = task_entry_q;
      end
      WRITE_TASK_DESC: begin
        mock_hdv_csr_valid_o = 1'b1;
        mock_hdv_csr_addr_o  = HDV_CSR_VTASK_PADDR;
        mock_hdv_csr_wdata_o = task_desc_q;
      end
      CLEAR_STATUS: begin
        mock_hdv_csr_valid_o = 1'b1;
        mock_hdv_csr_addr_o  = HDV_CSR_VTASK_STATUS;
        mock_hdv_csr_wdata_o = XLEN'(64'h6);
      end
      WRITE_START: begin
        mock_hdv_csr_valid_o = 1'b1;
        mock_hdv_csr_addr_o  = HDV_CSR_VTASK_START;
        mock_hdv_csr_wdata_o = XLEN'(64'h1);
      end
      READ_STATUS: begin
        mock_hdv_csr_valid_o = 1'b1;
        mock_hdv_csr_write_o = 1'b0;
        mock_hdv_csr_addr_o  = HDV_CSR_VTASK_STATUS;
      end
      default: begin
      end
    endcase
  end

  always_comb begin : p_next
    state_d             = state_q;
    task_entry_d        = task_entry_q;
    task_desc_d         = task_desc_q;
    expected_ep_acknowledges_d  = expected_ep_acknowledges_q;
    acknowledged_eps_d = acknowledged_eps_q;
    auto_start_count_d  = auto_start_count_q;
    auto_start_armed_d  = auto_start_armed_q;
    scalar_pending_d    = scalar_pending_q;
    vector_pending_d    = vector_pending_q;
    scalar_count_d      = scalar_count_q;
    vector_count_d      = vector_count_q;
    task_watchdog_d     = task_watchdog_q;
    packet_watchdog_d   = packet_watchdog_q;
    branch_redirect_wait_d = branch_redirect_wait_q;
    branch_redirect_valid_d = 1'b0;
    loop_iters_remaining_d = loop_iters_remaining_q;
    mock_hdv_task_complete_o = 1'b0;
    mock_hdv_task_error_o    = 1'b0;
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
      if (branch_fire) begin
        if (loop_iters_remaining_q != 32'd0) begin
          loop_iters_remaining_d = loop_iters_remaining_q - 32'd1;
        end
        branch_redirect_wait_d = branch_taken;
      end
    end

    if (branch_redirect_wait_q && mock_hdv_scalar_ep_done_o) begin
      branch_redirect_wait_d = 1'b0;
      branch_redirect_valid_d = 1'b1;
    end

    if (vector_fire) begin
      vector_pending_d = 1'b1;
      vector_count_d   = VectorCntWidth'(VectorLatency - 1);
    end

    if (hdv_mock_ep_acknowledged_i) begin
      acknowledged_eps_d = acknowledged_eps_q + 1'b1;
      packet_watchdog_d   = '0;
    end

    expected_reached = hdv_mock_ep_acknowledged_i
                     & ((acknowledged_eps_q + 1'b1) >= expected_ep_acknowledges_q)
                     & (expected_ep_acknowledges_q != '0);

    unique case (state_q)
      IDLE: begin
        if (auto_start_pulse) begin
          task_entry_d        = addr_t'(AutoTaskEntry);
          task_desc_d         = addr_t'(AutoTaskDesc);
`ifdef FOR_VERIFY
          expected_ep_acknowledges_d  = hdv_ep_ovr_en ? hdv_ep_ovr : AutoExpectedEpAcknowledges;
`else
          expected_ep_acknowledges_d  = AutoExpectedEpAcknowledges;
`endif
          acknowledged_eps_d = '0;
          loop_iters_remaining_d = 32'(MockLoopIterations);
          auto_start_armed_d  = 1'b0;
          state_d             = WRITE_TASK_ADDR;
        end
      end
      WRITE_TASK_ADDR: begin
        if (csr_fire) begin
          state_d = hdv_mock_csr_error_i ? FAIL : WRITE_TASK_DESC;
        end
      end
      WRITE_TASK_DESC: begin
        if (csr_fire) begin
          state_d = hdv_mock_csr_error_i ? FAIL : CLEAR_STATUS;
        end
      end
      CLEAR_STATUS: begin
        if (csr_fire) begin
          state_d = hdv_mock_csr_error_i ? FAIL : WRITE_START;
        end
      end
      WRITE_START: begin
        if (csr_fire) begin
          state_d = hdv_mock_csr_error_i ? FAIL : RUN;
        end
      end
      RUN: begin
        if (hdv_mock_task_error_i || hdv_mock_ep_error_i || packet_timeout) begin
          mock_hdv_task_error_o = 1'b1;
          state_d      = FAIL;
        end else if (expected_reached) begin
          state_d = COMPLETE_TASK;
        end else if (hdv_mock_task_done_i || !hdv_mock_task_busy_i) begin
          // Task finished naturally — expected_ep is a hint, not a pass/fail
          // criterion (different kernels produce different EP counts).
          state_d = READ_STATUS;
        end
      end
      COMPLETE_TASK: begin
        mock_hdv_task_complete_o = 1'b1;
        state_d         = WAIT_TASK_STATUS;
      end
      WAIT_TASK_STATUS: begin
        if (hdv_mock_task_done_i || hdv_mock_task_error_i || !hdv_mock_task_busy_i) begin
          state_d = READ_STATUS;
        end
      end
      READ_STATUS: begin
        if (csr_fire) begin
          state_d = (hdv_mock_csr_rdata_i[2] | hdv_mock_csr_error_i) ? FAIL : FINISH;
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
      mock_hdv_task_error_o = 1'b1;
      state_d      = FAIL;
    end

    if (flush_i) begin
      state_d             = IDLE;
      acknowledged_eps_d = '0;
      auto_start_count_d  = '0;
      auto_start_armed_d  = AutoStart;
      scalar_pending_d    = 1'b0;
      vector_pending_d    = 1'b0;
      branch_redirect_wait_d = 1'b0;
      branch_redirect_valid_d = 1'b0;
      loop_iters_remaining_d = '0;
      scalar_count_d      = '0;
      vector_count_d      = '0;
      task_watchdog_d     = '0;
      packet_watchdog_d   = '0;
      mock_hdv_task_complete_o = 1'b0;
      mock_hdv_task_error_o    = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q             <= IDLE;
      task_entry_q        <= '0;
      task_desc_q         <= '0;
      expected_ep_acknowledges_q  <= '0;
      acknowledged_eps_q <= '0;
      auto_start_count_q  <= '0;
      auto_start_armed_q  <= AutoStart;
      scalar_pending_q    <= 1'b0;
      vector_pending_q    <= 1'b0;
      branch_redirect_wait_q <= 1'b0;
      branch_redirect_valid_q <= 1'b0;
      branch_redirect_pc_q   <= '0;
      loop_iters_remaining_q <= '0;
      scalar_count_q      <= '0;
      vector_count_q      <= '0;
      task_watchdog_q     <= '0;
      packet_watchdog_q   <= '0;
    end else begin
      state_q             <= state_d;
      task_entry_q        <= task_entry_d;
      task_desc_q         <= task_desc_d;
      expected_ep_acknowledges_q  <= expected_ep_acknowledges_d;
      acknowledged_eps_q <= acknowledged_eps_d;
      auto_start_count_q  <= auto_start_count_d;
      auto_start_armed_q  <= auto_start_armed_d;
      scalar_pending_q    <= scalar_pending_d;
      vector_pending_q    <= vector_pending_d;
      branch_redirect_wait_q <= branch_redirect_wait_d;
      branch_redirect_valid_q <= branch_redirect_valid_d;
      branch_redirect_pc_q   <= branch_redirect_pc_d;
      loop_iters_remaining_q <= loop_iters_remaining_d;
      scalar_count_q      <= scalar_count_d;
      vector_count_q      <= vector_count_d;
      task_watchdog_q     <= task_watchdog_d;
      packet_watchdog_q   <= packet_watchdog_d;
    end
  end

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin : p_pf_probe_host
    if (rst_ni && $test$plusargs("HDV_PF_PROBE") && (state_q == RUN) &&
        (hdv_mock_task_error_i || hdv_mock_ep_error_i || packet_timeout ||
         task_timeout || ((packet_wd_limit != 32'd0) &&
                          (packet_watchdog_q + 32'd4 >= packet_wd_limit)))) begin
      $display("[PFPROBE-HOST] time=%0t state=%0d task_err_i=%0d ep_err_i=%0d pkt_to=%0d task_to=%0d pkt_wd=%0d pkt_lim=%0d task_wd=%0d task_lim=%0d busy=%0d done=%0d ep_ack=%0d ack_eps=%0d expected=%0d scalar_pending=%0d vector_pending=%0d scalar_count=%0d vector_count=%0d loop_left=%0d state_d=%0d",
               $time, state_q, hdv_mock_task_error_i, hdv_mock_ep_error_i,
               packet_timeout, task_timeout, packet_watchdog_q, packet_wd_limit,
               task_watchdog_q, task_wd_limit, hdv_mock_task_busy_i,
               hdv_mock_task_done_i, hdv_mock_ep_acknowledged_i,
               acknowledged_eps_q, expected_ep_acknowledges_q,
               scalar_pending_q, vector_pending_q, scalar_count_q,
               vector_count_q, loop_iters_remaining_q, state_d);
    end
  end
`endif

  if (ScalarLatency == 0)
    $error("[hdv_mock_host_core] ScalarLatency must be at least 1.");

  if (VectorLatency == 0)
    $error("[hdv_mock_host_core] VectorLatency must be at least 1.");

endmodule : hdv_mock_host_core
