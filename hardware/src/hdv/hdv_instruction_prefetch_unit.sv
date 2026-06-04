// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Instruction Prefetch Unit (IPU) with two 64-byte buffers and 128-bit fetch
// packets.  This standalone version models the paper's fetch-buffer structure
// and exposes a narrow request/response memory interface for later integration.

module hdv_instruction_prefetch_unit #(
  parameter int unsigned XLEN             = 64,
  parameter int unsigned FetchPacketWidth = 128,
  parameter int unsigned BufferBytes      = 64,
  parameter type addr_t = logic [XLEN-1:0]
) (
  input  logic                         clk_i,
  input  logic                         rst_ni,
  input  logic                         flush_i,

  input  logic                         task_valid_i,
  output logic                         task_ready_o,
  input  addr_t                        task_entry_i,
  input  addr_t                        task_desc_i,

  output logic                         mem_req_valid_o,
  input  logic                         mem_req_ready_i,
  output addr_t                        mem_req_addr_o,
  input  logic                         mem_rsp_valid_i,
  output logic                         mem_rsp_ready_o,
  input  logic [FetchPacketWidth-1:0]  mem_rsp_data_i,

  output logic                         packet_valid_o,
  input  logic                         packet_ready_i,
  output logic [FetchPacketWidth-1:0]  packet_o,
  output addr_t                        packet_pc_o,
  output addr_t                        task_desc_o,

  input  logic                         redirect_valid_i,
  input  addr_t                        redirect_pc_i,
  input  logic                         loop_lock_i,
  input  logic                         task_complete_i,
  output logic                         busy_o
);

  localparam int unsigned PacketBytes = FetchPacketWidth / 8;
  localparam int unsigned PacketsPerBuffer = BufferBytes / PacketBytes;
  localparam int unsigned PacketIdxWidth = (PacketsPerBuffer > 1) ? $clog2(PacketsPerBuffer) : 1;
  localparam logic [PacketIdxWidth-1:0] LastPacketIdx = PacketsPerBuffer - 1;

  typedef logic [FetchPacketWidth-1:0] packet_t;
  typedef packet_t buffer_t [PacketsPerBuffer];

  typedef enum logic [1:0] {
    IDLE,
    FILL,
    SERVE
  } state_e;

  state_e state_d, state_q;
  buffer_t buffer_a_q;
  buffer_t buffer_b_q;
  logic active_buf_d, active_buf_q;
  logic fill_buf_d, fill_buf_q;
  logic [PacketIdxWidth-1:0] fill_idx_d, fill_idx_q;
  logic [PacketIdxWidth-1:0] exec_idx_d, exec_idx_q;
  addr_t fetch_base_d, fetch_base_q;
  addr_t exec_base_d, exec_base_q;
  addr_t task_desc_d, task_desc_q;
  logic req_pending_d, req_pending_q;
  logic fill_done;
  logic accept_rsp;
  logic accept_req;
  logic take_packet;

  assign task_ready_o = (state_q == IDLE);
  assign busy_o       = (state_q != IDLE);

  assign fill_done    = accept_rsp & (fill_idx_q == LastPacketIdx);
  assign accept_req   = mem_req_valid_o & mem_req_ready_i;
  assign mem_rsp_ready_o = (state_q == FILL) & req_pending_q;
  assign accept_rsp   = mem_rsp_valid_i & mem_rsp_ready_o;
  assign take_packet  = packet_valid_o & packet_ready_i;

  assign mem_req_valid_o = (state_q == FILL) & !req_pending_q;
  assign mem_req_addr_o  = fetch_base_q + addr_t'(fill_idx_q * PacketBytes);

  assign packet_valid_o = (state_q == SERVE);
  assign packet_o       = active_buf_q ? buffer_b_q[exec_idx_q] : buffer_a_q[exec_idx_q];
  assign packet_pc_o    = exec_base_q + addr_t'(exec_idx_q * PacketBytes);
  assign task_desc_o    = task_desc_q;

  always_comb begin : p_next
    state_d      = state_q;
    active_buf_d = active_buf_q;
    fill_buf_d   = fill_buf_q;
    fill_idx_d   = fill_idx_q;
    exec_idx_d   = exec_idx_q;
    fetch_base_d = fetch_base_q;
    exec_base_d  = exec_base_q;
    task_desc_d  = task_desc_q;
    req_pending_d = req_pending_q;

    if (task_complete_i) begin
      state_d       = IDLE;
      fill_idx_d    = '0;
      exec_idx_d    = '0;
      req_pending_d = 1'b0;
    end else if (redirect_valid_i) begin
      state_d      = FILL;
      fill_idx_d   = '0;
      exec_idx_d   = '0;
      fetch_base_d = redirect_pc_i;
      exec_base_d  = redirect_pc_i;
      active_buf_d = 1'b0;
      fill_buf_d   = 1'b0;
      req_pending_d = 1'b0;
    end else begin
      unique case (state_q)
        IDLE: begin
          if (task_valid_i) begin
            state_d      = FILL;
            fill_idx_d   = '0;
            exec_idx_d   = '0;
            fetch_base_d = task_entry_i;
            exec_base_d  = task_entry_i;
            task_desc_d  = task_desc_i;
            active_buf_d = 1'b0;
            fill_buf_d   = 1'b0;
            req_pending_d = 1'b0;
          end
        end
        FILL: begin
          if (accept_req) begin
            req_pending_d = 1'b1;
          end

          if (accept_rsp) begin
            req_pending_d = 1'b0;

            if (fill_done) begin
              state_d      = SERVE;
              active_buf_d = fill_buf_q;
              exec_idx_d   = '0;
              exec_base_d  = fetch_base_q;
              fill_buf_d   = !fill_buf_q;
              fetch_base_d = fetch_base_q + addr_t'(BufferBytes);
              fill_idx_d   = '0;
            end else begin
              fill_idx_d = fill_idx_q + 1;
            end
          end
        end
        SERVE: begin
          if (take_packet) begin
            if (exec_idx_q == LastPacketIdx) begin
              exec_idx_d = '0;
              if (!loop_lock_i) begin
                state_d = FILL;
              end
            end else begin
              exec_idx_d = exec_idx_q + 1;
            end
          end
        end
        default: begin
          state_d = IDLE;
        end
      endcase
    end

    if (flush_i) begin
      state_d      = IDLE;
      fill_idx_d   = '0;
      exec_idx_d   = '0;
      active_buf_d = 1'b0;
      fill_buf_d   = 1'b0;
      req_pending_d = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q      <= IDLE;
      active_buf_q <= 1'b0;
      fill_buf_q   <= 1'b0;
      fill_idx_q   <= '0;
      exec_idx_q   <= '0;
      fetch_base_q <= '0;
      exec_base_q  <= '0;
      task_desc_q  <= '0;
      req_pending_q <= 1'b0;
    end else begin
      state_q      <= state_d;
      active_buf_q <= active_buf_d;
      fill_buf_q   <= fill_buf_d;
      fill_idx_q   <= fill_idx_d;
      exec_idx_q   <= exec_idx_d;
      fetch_base_q <= fetch_base_d;
      exec_base_q  <= exec_base_d;
      task_desc_q  <= task_desc_d;
      req_pending_q <= req_pending_d;
    end
  end

  always_ff @(posedge clk_i) begin : p_buffer_write
    if (accept_rsp) begin
      if (!fill_buf_q) begin
        buffer_a_q[fill_idx_q] <= mem_rsp_data_i;
      end else begin
        buffer_b_q[fill_idx_q] <= mem_rsp_data_i;
      end
    end
  end

endmodule : hdv_instruction_prefetch_unit
