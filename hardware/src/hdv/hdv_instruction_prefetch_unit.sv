// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Instruction Prefetch Unit (IPU) with two 64-byte ping-pong buffers and
// 128-bit fetch packets.  The first returned packet can be served immediately;
// the rest of the active buffer is filled while VLIWPU consumes valid entries.
// Once the active buffer is complete, the other buffer is filled in the
// background.  A loop-lock signal suppresses buffer switches to replay the
// active buffer in tight loops.

module hdv_instruction_prefetch_unit #(
  parameter int unsigned XLEN             = 64,
  parameter int unsigned FetchPacketWidth = 128,
  parameter int unsigned BufferBytes      = 64,
  parameter type addr_t = logic [XLEN-1:0]
) (
  input  logic                         clk_i,
  input  logic                         rst_ni,
  input  logic                         flush_i,

  input  logic                         tsu_ipu_task_valid_i,
  output logic                         ipu_tsu_task_ready_o,
  input  addr_t                        tsu_ipu_task_entry_i,
  input  addr_t                        tsu_ipu_task_desc_i,

  output logic                         ipu_mem_req_valid_o,
  input  logic                         mem_ipu_req_ready_i,
  output addr_t                        ipu_mem_req_addr_o,
  input  logic                         mem_ipu_rsp_valid_i,
  output logic                         ipu_mem_rsp_ready_o,
  input  logic [FetchPacketWidth-1:0]  mem_ipu_rsp_data_i,

  output logic                         ipu_vliwpu_packet_valid_o,
  input  logic                         vliwpu_ipu_packet_ready_i,
  output logic [FetchPacketWidth-1:0]  ipu_vliwpu_packet_o,
  output addr_t                        ipu_vliwpu_packet_pc_o,
  output addr_t                        ipu_top_task_desc_o,

  input  logic                         redirect_valid_i,
  input  addr_t                        redirect_pc_i,
  input  logic                         loop_lock_i,
  input  logic                         top_ipu_task_complete_i,
  output logic                         ipu_top_busy_o
);

  localparam int unsigned PacketBytes       = FetchPacketWidth / 8;
  localparam int unsigned PacketsPerBuffer  = BufferBytes / PacketBytes;
  localparam int unsigned PacketIdxWidth    = (PacketsPerBuffer > 1) ? $clog2(PacketsPerBuffer) : 1;
  localparam int unsigned PacketOffsetWidth = (PacketBytes > 1) ? $clog2(PacketBytes) : 1;
  localparam logic [PacketIdxWidth-1:0] LastPacketIdx = PacketsPerBuffer - 1;

  typedef logic [FetchPacketWidth-1:0] packet_t;
  typedef packet_t buffer_t [PacketsPerBuffer];

  // FILL  = wait for the first packet of a task/redirect.
  // SERVE = serve valid entries from active_buf.  During the first buffer,
  //         fill_buf==active_buf and the rest of the active buffer is filled
  //         on demand; afterwards fill_buf points to the background buffer.
  typedef enum logic [1:0] {
    IDLE,
    FILL,
    SERVE
  } state_e;

  state_e state_d, state_q;
  buffer_t buffer_a_q;
  buffer_t buffer_b_q;
  logic [PacketsPerBuffer-1:0] buffer_a_valid_d, buffer_a_valid_q;
  logic [PacketsPerBuffer-1:0] buffer_b_valid_d, buffer_b_valid_q;

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
  logic active_packet_valid;
  logic bg_stall;  // hold at last slot until background fill completes
  logic loop_blocks_bg_fetch;
  logic redirect_aligned;
  logic redirect_in_active;
  logic redirect_active_packet_valid;
  logic [PacketIdxWidth-1:0] redirect_exec_idx;
  addr_t redirect_active_offset;

  assign redirect_aligned = (redirect_pc_i[PacketOffsetWidth-1:0] == '0);
  assign redirect_active_offset = redirect_pc_i - exec_base_q;
  assign redirect_exec_idx = redirect_active_offset[PacketOffsetWidth +: PacketIdxWidth];
  assign redirect_in_active = (state_q == SERVE) &&
                              (redirect_pc_i >= exec_base_q) &&
                              (redirect_pc_i < (exec_base_q + addr_t'(BufferBytes)));
  assign redirect_active_packet_valid = active_buf_q ? buffer_b_valid_q[redirect_exec_idx]
                                                     : buffer_a_valid_q[redirect_exec_idx];

  assign ipu_tsu_task_ready_o = (state_q == IDLE);
  assign ipu_top_busy_o       = (state_q != IDLE);

  // Memory request: active in FILL (initial) and in SERVE while bg fill pending.
  // When loop lock is active, keep completing an already-issued request but do
  // not fetch more background packets; the active loop body is replayed locally.
  assign loop_blocks_bg_fetch = loop_lock_i & (fill_buf_q != active_buf_q);
  assign ipu_mem_req_valid_o = ((state_q == FILL) |
                                (state_q == SERVE & !bg_fill_done_q & !loop_blocks_bg_fetch)) &
                               !req_pending_q;
  assign ipu_mem_req_addr_o  = fetch_base_q + addr_t'(fill_idx_q * PacketBytes);

  // Accept response in both FILL and SERVE states.
  assign ipu_mem_rsp_ready_o = ((state_q == FILL) | (state_q == SERVE)) & req_pending_q;

  assign fill_done   = accept_rsp & (fill_idx_q == LastPacketIdx);
  assign accept_req  = ipu_mem_req_valid_o & mem_ipu_req_ready_i;
  assign accept_rsp  = mem_ipu_rsp_valid_i & ipu_mem_rsp_ready_o;

  assign active_packet_valid = active_buf_q ? buffer_b_valid_q[exec_idx_q]
                                            : buffer_a_valid_q[exec_idx_q];

  // Stall at last slot when the next background buffer is not yet ready
  // (unless looping).  During first-buffer early serve, fill_buf==active_buf;
  // packet availability is then guarded by active_packet_valid instead.
  assign bg_stall    = (exec_idx_q == LastPacketIdx) & !bg_fill_done_q & !loop_lock_i
                     & (fill_buf_q != active_buf_q);

  assign ipu_vliwpu_packet_valid_o = (state_q == SERVE) & active_packet_valid & !bg_stall;
  assign ipu_vliwpu_packet_o       = active_buf_q ? buffer_b_q[exec_idx_q]
                                                : buffer_a_q[exec_idx_q];
  assign ipu_vliwpu_packet_pc_o    = exec_base_q + addr_t'(exec_idx_q * PacketBytes);
  assign ipu_top_task_desc_o     = task_desc_q;

  assign take_packet    = ipu_vliwpu_packet_valid_o & vliwpu_ipu_packet_ready_i;

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
    buffer_a_valid_d = buffer_a_valid_q;
    buffer_b_valid_d = buffer_b_valid_q;

    // req_pending tracks the in-flight memory request (common to all states).
    if (accept_req) req_pending_d = 1'b1;
    if (accept_rsp) req_pending_d = 1'b0;
    if (accept_rsp) begin
      if (!fill_buf_q) begin
        buffer_a_valid_d[fill_idx_q] = 1'b1;
      end else begin
        buffer_b_valid_d[fill_idx_q] = 1'b1;
      end
    end

    // Highest-priority resets: task complete, redirect, flush.
    if (top_ipu_task_complete_i) begin
      state_d        = IDLE;
      fill_idx_d     = '0;
      exec_idx_d     = '0;
      req_pending_d  = 1'b0;
      bg_fill_done_d = 1'b0;
      buffer_a_valid_d = '0;
      buffer_b_valid_d = '0;
    end else if (redirect_valid_i && redirect_aligned && redirect_in_active &&
                 redirect_active_packet_valid) begin
      // Redirect hit in the active buffer: replay from the target fetch packet
      // instead of invalidating the buffers and refetching the loop body.
      state_d      = SERVE;
      exec_idx_d   = redirect_exec_idx;
    end else if (redirect_valid_i && redirect_aligned) begin
      state_d        = FILL;
      fill_idx_d     = '0;
      exec_idx_d     = '0;
      fetch_base_d   = redirect_pc_i;
      exec_base_d    = redirect_pc_i;
      active_buf_d   = 1'b0;
      fill_buf_d     = 1'b0;
      req_pending_d  = 1'b0;
      bg_fill_done_d = 1'b0;
      buffer_a_valid_d = '0;
      buffer_b_valid_d = '0;
    end else if (redirect_valid_i) begin
      // Redirect targets are required to be fetch-packet / EP entry points.
      // In simulation the assertion below makes this fatal; here we avoid
      // changing state on an invalid redirect target.
    end else begin
      unique case (state_q)
        // ----------------------------------------------------------------
        IDLE: begin
          if (tsu_ipu_task_valid_i) begin
            state_d        = FILL;
            fill_idx_d     = '0;
            exec_idx_d     = '0;
            fetch_base_d   = tsu_ipu_task_entry_i;
            exec_base_d    = tsu_ipu_task_entry_i;
            task_desc_d    = tsu_ipu_task_desc_i;
            active_buf_d   = 1'b0;
            fill_buf_d     = 1'b0;
            req_pending_d  = 1'b0;
            bg_fill_done_d = 1'b0;
            buffer_a_valid_d = '0;
            buffer_b_valid_d = '0;
          end
        end

        // ----------------------------------------------------------------
        // Initial fill: the first returned packet is enough to start serving.
        FILL: begin
          if (accept_rsp) begin
            state_d      = SERVE;
            active_buf_d = fill_buf_q;
            exec_idx_d   = '0;
            exec_base_d  = fetch_base_q;

            if (fill_done) begin
              // Degenerate case: the first buffer has only one packet.
              // Start filling the other buffer in the background.
              fill_buf_d     = !fill_buf_q;
              fetch_base_d   = fetch_base_q + addr_t'(BufferBytes);
              fill_idx_d     = '0;
              bg_fill_done_d = 1'b0;
              if (!fill_buf_q) begin
                buffer_b_valid_d = '0;
              end else begin
                buffer_a_valid_d = '0;
              end
            end else begin
              fill_idx_d = fill_idx_q + 1;
            end
          end
        end

        // ----------------------------------------------------------------
        // Serve from active_buf; concurrently fill fill_buf in background.
        SERVE: begin
          // ---- active/background fill ------------------------------------
          if (accept_rsp) begin
            if (fill_done) begin
              if (fill_buf_q == active_buf_q) begin
                // Early-serve phase completed the active buffer.  Move the
                // fill side to the other buffer and start background fill.
                fill_buf_d     = !fill_buf_q;
                fetch_base_d   = fetch_base_q + addr_t'(BufferBytes);
                fill_idx_d     = '0;
                bg_fill_done_d = 1'b0;
                if (!fill_buf_q) begin
                  buffer_b_valid_d = '0;
                end else begin
                  buffer_a_valid_d = '0;
                end
              end else begin
                // Background fill of fill_buf is complete.  Hold fill_idx at
                // LastPacketIdx; the buffer switch will reset it.
                bg_fill_done_d = 1'b1;
              end
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
                if (!fill_buf_q) begin
                  buffer_b_valid_d = '0;
                end else begin
                  buffer_a_valid_d = '0;
                end
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
      buffer_a_valid_d = '0;
      buffer_b_valid_d = '0;
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
      buffer_a_valid_q <= '0;
      buffer_b_valid_q <= '0;
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
      buffer_a_valid_q <= buffer_a_valid_d;
      buffer_b_valid_q <= buffer_b_valid_d;
    end
  end

  always_ff @(posedge clk_i) begin : p_buffer_write
    if (accept_rsp) begin
      if (!fill_buf_q) begin
        buffer_a_q[fill_idx_q] <= mem_ipu_rsp_data_i;
      end else begin
        buffer_b_q[fill_idx_q] <= mem_ipu_rsp_data_i;
      end
    end
  end

  always_ff @(posedge clk_i) begin : p_redirect_alignment_check
    if (rst_ni && redirect_valid_i && !redirect_aligned) begin
      $fatal(1, "[HDV] redirect_pc_i must be %0d-byte aligned: 0x%0h",
             PacketBytes, redirect_pc_i);
    end
  end

endmodule : hdv_instruction_prefetch_unit
