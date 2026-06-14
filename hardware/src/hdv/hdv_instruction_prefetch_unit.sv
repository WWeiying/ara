// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Instruction Prefetch Unit (IPU) with two 64-byte ping-pong buffers and
// 128-bit fetch packets.  Buffer A is served to the VLIW Pack Unit while
// Buffer B is filled from memory in the background (or vice-versa), hiding
// fetch latency.  A loop-lock signal suppresses buffer switches to replay
// the active buffer in tight loops.

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

  localparam int unsigned PacketBytes       = FetchPacketWidth / 8;
  localparam int unsigned PacketsPerBuffer  = BufferBytes / PacketBytes;
  localparam int unsigned PacketIdxWidth    = (PacketsPerBuffer > 1) ? $clog2(PacketsPerBuffer) : 1;
  localparam logic [PacketIdxWidth-1:0] LastPacketIdx = PacketsPerBuffer - 1;

  typedef logic [FetchPacketWidth-1:0] packet_t;
  typedef packet_t buffer_t [PacketsPerBuffer];

  // FILL  = initial blocking fill of the first buffer before serving starts.
  // SERVE = serve from active_buf while concurrently filling fill_buf in the
  //         background.  packet_valid_o is deasserted only when exec_idx
  //         reaches the last slot and the background fill is not yet complete.
  typedef enum logic [1:0] {
    IDLE,
    FILL,
    SERVE
  } state_e;

  state_e state_d, state_q;
  buffer_t buffer_a_q;
  buffer_t buffer_b_q;

  logic active_buf_d, active_buf_q;
  logic fill_buf_d,   fill_buf_q;

  logic [PacketIdxWidth-1:0] fill_idx_d, fill_idx_q;
  logic [PacketIdxWidth-1:0] exec_idx_d, exec_idx_q;

  addr_t fetch_base_d, fetch_base_q;   // byte address of current bg-fill block
  addr_t exec_base_d,  exec_base_q;    // byte address of start of active buffer
  addr_t task_desc_d,  task_desc_q;

  logic req_pending_d,   req_pending_q;
  logic bg_fill_done_d,  bg_fill_done_q; // background fill of fill_buf is complete

  logic fill_done;
  logic accept_req;
  logic accept_rsp;
  logic take_packet;
  logic bg_stall;  // hold at last slot until background fill completes

  assign task_ready_o = (state_q == IDLE);
  assign busy_o       = (state_q != IDLE);

  // Memory request: active in FILL (initial) and in SERVE while bg fill pending.
  assign mem_req_valid_o = ((state_q == FILL) |
                            (state_q == SERVE & !bg_fill_done_q)) & !req_pending_q;
  assign mem_req_addr_o  = fetch_base_q + addr_t'(fill_idx_q * PacketBytes);

  // Accept response in both FILL and SERVE states.
  assign mem_rsp_ready_o = ((state_q == FILL) | (state_q == SERVE)) & req_pending_q;

  assign fill_done   = accept_rsp & (fill_idx_q == LastPacketIdx);
  assign accept_req  = mem_req_valid_o & mem_req_ready_i;
  assign accept_rsp  = mem_rsp_valid_i & mem_rsp_ready_o;

  // Stall at last slot when background fill is not yet ready (unless looping).
  assign bg_stall    = (exec_idx_q == LastPacketIdx) & !bg_fill_done_q & !loop_lock_i;

  assign packet_valid_o = (state_q == SERVE) & !bg_stall;
  assign packet_o       = active_buf_q ? buffer_b_q[exec_idx_q]
                                       : buffer_a_q[exec_idx_q];
  assign packet_pc_o    = exec_base_q + addr_t'(exec_idx_q * PacketBytes);
  assign task_desc_o    = task_desc_q;

  assign take_packet    = packet_valid_o & packet_ready_i;

  always_comb begin : p_next
    state_d        = state_q;
    active_buf_d   = active_buf_q;
    fill_buf_d     = fill_buf_q;
    fill_idx_d     = fill_idx_q;
    exec_idx_d     = exec_idx_q;
    fetch_base_d   = fetch_base_q;
    exec_base_d    = exec_base_q;
    task_desc_d    = task_desc_q;
    req_pending_d  = req_pending_q;
    bg_fill_done_d = bg_fill_done_q;

    // req_pending tracks the in-flight memory request (common to all states).
    if (accept_req) req_pending_d = 1'b1;
    if (accept_rsp) req_pending_d = 1'b0;

    // Highest-priority resets: task complete, redirect, flush.
    if (task_complete_i) begin
      state_d        = IDLE;
      fill_idx_d     = '0;
      exec_idx_d     = '0;
      req_pending_d  = 1'b0;
      bg_fill_done_d = 1'b0;
    end else if (redirect_valid_i) begin
      state_d        = FILL;
      fill_idx_d     = '0;
      exec_idx_d     = '0;
      fetch_base_d   = redirect_pc_i;
      exec_base_d    = redirect_pc_i;
      active_buf_d   = 1'b0;
      fill_buf_d     = 1'b0;
      req_pending_d  = 1'b0;
      bg_fill_done_d = 1'b0;
    end else begin
      unique case (state_q)
        // ----------------------------------------------------------------
        IDLE: begin
          if (task_valid_i) begin
            state_d        = FILL;
            fill_idx_d     = '0;
            exec_idx_d     = '0;
            fetch_base_d   = task_entry_i;
            exec_base_d    = task_entry_i;
            task_desc_d    = task_desc_i;
            active_buf_d   = 1'b0;
            fill_buf_d     = 1'b0;
            req_pending_d  = 1'b0;
            bg_fill_done_d = 1'b0;
          end
        end

        // ----------------------------------------------------------------
        // Initial (blocking) fill: must complete before serving starts.
        FILL: begin
          if (accept_rsp) begin
            if (fill_done) begin
              // First buffer ready — transition to SERVE.
              // Set active buffer to the just-filled one, advance fill_buf
              // and fetch_base for the first background fill.
              state_d        = SERVE;
              active_buf_d   = fill_buf_q;
              exec_idx_d     = '0;
              exec_base_d    = fetch_base_q;
              fill_buf_d     = !fill_buf_q;
              fetch_base_d   = fetch_base_q + addr_t'(BufferBytes);
              fill_idx_d     = '0;
              bg_fill_done_d = 1'b0;
            end else begin
              fill_idx_d = fill_idx_q + 1;
            end
          end
        end

        // ----------------------------------------------------------------
        // Serve from active_buf; concurrently fill fill_buf in background.
        SERVE: begin
          // ---- background fill ------------------------------------------
          if (accept_rsp) begin
            if (fill_done) begin
              // Background fill of fill_buf is complete.  Hold fill_idx at
              // LastPacketIdx; the buffer switch will reset it.
              bg_fill_done_d = 1'b1;
            end else begin
              fill_idx_d = fill_idx_q + 1;
            end
          end

          // ---- serve packets --------------------------------------------
          if (take_packet) begin
            if (exec_idx_q == LastPacketIdx) begin
              if (loop_lock_i) begin
                // Loop optimisation: replay active buffer from the start.
                exec_idx_d = '0;
              end else begin
                // bg_fill_done_q is guaranteed 1 here (bg_stall prevents
                // take_packet when bg fill is incomplete).
                //
                // Switch active buffer to the freshly filled fill_buf.
                // Set exec_base to fetch_base_q (= start addr of fill_buf).
                // Advance fill_buf and fetch_base for the next background fill.
                active_buf_d   = fill_buf_q;
                exec_base_d    = fetch_base_q;
                exec_idx_d     = '0;
                fill_buf_d     = !fill_buf_q;
                fetch_base_d   = fetch_base_q + addr_t'(BufferBytes);
                fill_idx_d     = '0;
                bg_fill_done_d = 1'b0;
              end
            end else begin
              exec_idx_d = exec_idx_q + 1;
            end
          end
        end

        default: state_d = IDLE;
      endcase
    end

    // flush_i overrides everything (highest priority).
    if (flush_i) begin
      state_d        = IDLE;
      fill_idx_d     = '0;
      exec_idx_d     = '0;
      active_buf_d   = 1'b0;
      fill_buf_d     = 1'b0;
      req_pending_d  = 1'b0;
      bg_fill_done_d = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q        <= IDLE;
      active_buf_q   <= 1'b0;
      fill_buf_q     <= 1'b0;
      fill_idx_q     <= '0;
      exec_idx_q     <= '0;
      fetch_base_q   <= '0;
      exec_base_q    <= '0;
      task_desc_q    <= '0;
      req_pending_q  <= 1'b0;
      bg_fill_done_q <= 1'b0;
    end else begin
      state_q        <= state_d;
      active_buf_q   <= active_buf_d;
      fill_buf_q     <= fill_buf_d;
      fill_idx_q     <= fill_idx_d;
      exec_idx_q     <= exec_idx_d;
      fetch_base_q   <= fetch_base_d;
      exec_base_q    <= exec_base_d;
      task_desc_q    <= task_desc_d;
      req_pending_q  <= req_pending_d;
      bg_fill_done_q <= bg_fill_done_d;
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
