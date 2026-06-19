// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Instruction Prefetch Unit (IPU) with two 64-byte ping-pong buffers and
// 128-bit fetch packets.  The first returned packet can be served immediately;
// the rest of the active buffer is filled while VLIWPU consumes valid entries.
// Once the active buffer is complete, the other buffer is filled in the
// background.  HDV LUI hint headers can mark loop start/end packets.  The IPU
// protects the marked loop buffers and can replay a taken backward redirect
// from either ping-pong buffer, so a locked loop can occupy up to 2*BufferBytes.

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
  input  logic                         loop_exit_i,
  input  logic                         top_ipu_task_complete_i,
  output logic                         ipu_top_busy_o,
  // High while IPU is auto-locked on a backward-branch loop body.
  output logic                         ipu_top_loop_active_o
);

  localparam int unsigned PacketBytes       = FetchPacketWidth / 8;
  localparam int unsigned PacketsPerBuffer  = BufferBytes / PacketBytes;
  localparam int unsigned PacketIdxWidth    = (PacketsPerBuffer > 1) ? $clog2(PacketsPerBuffer) : 1;
  localparam int unsigned PacketOffsetWidth = (PacketBytes > 1) ? $clog2(PacketBytes) : 1;
  localparam int unsigned IpuSramWords      = 32;
  localparam int unsigned IpuSramAddrWidth  = $clog2(IpuSramWords);
  localparam logic [PacketIdxWidth-1:0] LastPacketIdx = PacketsPerBuffer - 1;

  typedef logic [FetchPacketWidth-1:0] packet_t;

  initial begin : p_static_config_check
    if (FetchPacketWidth != 128) begin
      $fatal(1, "[HDV] IPU SRAM macro binding requires FetchPacketWidth=128, got %0d",
             FetchPacketWidth);
    end
    if ((BufferBytes % PacketBytes) != 0) begin
      $fatal(1, "[HDV] BufferBytes (%0d) must be a multiple of PacketBytes (%0d)",
             BufferBytes, PacketBytes);
    end
    if (PacketsPerBuffer > IpuSramWords) begin
      $fatal(1, "[HDV] BufferBytes=%0d needs %0d packets, but IPU SRAM has %0d words",
             BufferBytes, PacketsPerBuffer, IpuSramWords);
    end
  end

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
  logic [PacketsPerBuffer-1:0] buffer_a_valid_d, buffer_a_valid_q;
  logic [PacketsPerBuffer-1:0] buffer_b_valid_d, buffer_b_valid_q;

  logic                         buffer_a_req;
  logic                         buffer_b_req;
  logic                         buffer_a_we;
  logic                         buffer_b_we;
  logic [IpuSramAddrWidth-1:0]  buffer_a_addr;
  logic [IpuSramAddrWidth-1:0]  buffer_b_addr;
  packet_t                      buffer_a_wdata;
  packet_t                      buffer_b_wdata;
  packet_t                      buffer_a_rdata;
  packet_t                      buffer_b_rdata;
  logic [PacketBytes-1:0]       buffer_be;
  logic [FetchPacketWidth-1:0]  buffer_bweb;

  logic                         buffer_a_write;
  logic                         buffer_b_write;
  logic                         buffer_a_read;
  logic                         buffer_b_read;
  logic                         buffer_read_req;
  logic                         buffer_read_fire;
  logic                         buffer_read_buf;
  logic [PacketIdxWidth-1:0]    buffer_read_idx;
  logic                         buffer_read_pending_q;
  logic                         buffer_read_buf_q;
  logic [PacketIdxWidth-1:0]    buffer_read_idx_q;

  packet_t                      served_packet_q;
  logic                         served_packet_valid_q;
  logic                         served_packet_buf_q;
  logic [PacketIdxWidth-1:0]    served_packet_idx_q;
  logic                         served_packet_hit;
  packet_t                      prefetch_packet_q;
  logic                         prefetch_packet_valid_q;
  logic                         prefetch_packet_buf_q;
  logic [PacketIdxWidth-1:0]    prefetch_packet_idx_q;
  logic                         prefetch_packet_hit;
  logic                         sram_bypass_hit;
  logic                         packet_cache_hit;
  packet_t                      packet_cache_data;
  logic                         active_entry_valid;
  logic                         next_entry_valid;
  logic                         next_buf;
  logic [PacketIdxWidth-1:0]    next_idx;
  logic                         next_packet_hit;
  logic                         demand_read_req;
  logic                         prefetch_read_req;
  logic                         keep_prefetch_valid;
  logic                         keep_prefetch_next_valid;
  logic                         keep_next_buf;
  logic [PacketIdxWidth-1:0]    keep_next_idx;

  logic active_buf_d, active_buf_q;
  logic fill_buf_d,   fill_buf_q;

  logic [PacketIdxWidth-1:0] fill_req_idx_d, fill_req_idx_q;
  logic [PacketIdxWidth-1:0] fill_rsp_idx_d, fill_rsp_idx_q;
  logic [PacketIdxWidth-1:0] exec_idx_d, exec_idx_q;

  addr_t fetch_base_d, fetch_base_q;   // byte address of current bg-fill block
  addr_t exec_base_d,  exec_base_q;    // byte address of start of active buffer
  addr_t task_desc_d,  task_desc_q;

  logic fill_req_done_d, fill_req_done_q;
  logic bg_fill_done_d,  bg_fill_done_q; // background fill of fill_buf is complete
  logic auto_loop_lock_d, auto_loop_lock_q;
  logic loop_wait_d,      loop_wait_q;
  logic loop_exit_seen_d, loop_exit_seen_q; // latched not-taken exit during a hold
  logic loop_build_d,     loop_build_q;
  logic loop_locked_d,    loop_locked_q;
  logic [1:0] loop_protect_d, loop_protect_q;

  logic served_pkt_has_bwd_branch; // served packet carries a backward branch
  logic served_pkt_loop_start;
  logic served_pkt_loop_end;

  logic fill_done;
  logic accept_req;
  logic accept_rsp;
  logic take_packet;
  logic active_packet_valid;
  logic bg_stall;  // hold at last slot until background fill completes
  logic loop_blocks_bg_fetch;
  logic redirect_aligned;
  logic redirect_in_active;
  logic redirect_in_fill;
  logic redirect_active_packet_valid;
  logic redirect_fill_packet_valid;
  logic redirect_is_backward;
  logic effective_loop_fetch_lock;
  logic replay_loop_lock;
  logic fill_buf_protected;
  logic active_buf_protected;
  logic [PacketIdxWidth-1:0] redirect_exec_idx;
  logic [PacketIdxWidth-1:0] redirect_fill_idx;
  addr_t redirect_active_offset;
  addr_t redirect_fill_offset;
  logic [31:0] served_header;
  logic [19:0] served_header_imm20;
  logic served_header_is_lui_hint;

  assign redirect_aligned = (redirect_pc_i[PacketOffsetWidth-1:0] == '0);
  assign redirect_active_offset = redirect_pc_i - exec_base_q;
  assign redirect_fill_offset = redirect_pc_i - fetch_base_q;
  assign redirect_exec_idx = redirect_active_offset[PacketOffsetWidth +: PacketIdxWidth];
  assign redirect_fill_idx = redirect_fill_offset[PacketOffsetWidth +: PacketIdxWidth];
  assign redirect_in_active = (state_q == SERVE) &&
                              (redirect_pc_i >= exec_base_q) &&
                              (redirect_pc_i < (exec_base_q + addr_t'(BufferBytes)));
  assign redirect_in_fill = (state_q == SERVE) &&
                            (fill_buf_q != active_buf_q) &&
                            (redirect_pc_i >= fetch_base_q) &&
                            (redirect_pc_i < (fetch_base_q + addr_t'(BufferBytes)));
  assign redirect_active_packet_valid = active_buf_q ? buffer_b_valid_q[redirect_exec_idx]
                                                     : buffer_a_valid_q[redirect_exec_idx];
  assign redirect_fill_packet_valid = fill_buf_q ? buffer_b_valid_q[redirect_fill_idx]
                                                 : buffer_a_valid_q[redirect_fill_idx];
  assign redirect_is_backward = redirect_pc_i < ipu_vliwpu_packet_pc_o;
  assign effective_loop_fetch_lock = loop_lock_i | auto_loop_lock_q | loop_build_q | loop_locked_q;
  assign replay_loop_lock = loop_lock_i;
  assign fill_buf_protected = fill_buf_q ? loop_protect_q[1] : loop_protect_q[0];
  assign active_buf_protected = active_buf_q ? loop_protect_q[1] : loop_protect_q[0];

  assign ipu_tsu_task_ready_o = (state_q == IDLE);
  assign ipu_top_busy_o       = (state_q != IDLE);
  // Active while a backward-branch loop body is locked in the fetch buffers.
  assign ipu_top_loop_active_o = auto_loop_lock_q | loop_locked_q;

  // Memory request: active in FILL (initial) and in SERVE while bg fill pending.
  // When loop lock is active, keep completing an already-issued request but do
  // not fetch more background packets; taken redirects replay the active body.
  assign loop_blocks_bg_fetch = (loop_lock_i & (fill_buf_q != active_buf_q)) |
                                (effective_loop_fetch_lock & (fill_buf_q != active_buf_q) &
                                 fill_buf_protected);
  assign ipu_mem_req_valid_o = ((state_q == FILL) |
                                (state_q == SERVE & !bg_fill_done_q & !loop_blocks_bg_fetch)) &
                               !fill_req_done_q &
                               !top_ipu_task_complete_i &
                               !redirect_valid_i &
                               !flush_i;
  assign ipu_mem_req_addr_o  = fetch_base_q + addr_t'(fill_req_idx_q * PacketBytes);

  // Accept in-order responses in both FILL and SERVE states.
  assign ipu_mem_rsp_ready_o = ((state_q == FILL) | (state_q == SERVE));

  assign fill_done   = accept_rsp & (fill_rsp_idx_q == LastPacketIdx);
  assign accept_req  = ipu_mem_req_valid_o & mem_ipu_req_ready_i;
  assign accept_rsp  = mem_ipu_rsp_valid_i & ipu_mem_rsp_ready_o;

  assign active_entry_valid = active_buf_q ? buffer_b_valid_q[exec_idx_q]
                                           : buffer_a_valid_q[exec_idx_q];
  assign served_packet_hit = served_packet_valid_q &&
                             (served_packet_buf_q == active_buf_q) &&
                             (served_packet_idx_q == exec_idx_q);
  assign prefetch_packet_hit = prefetch_packet_valid_q &&
                               (prefetch_packet_buf_q == active_buf_q) &&
                               (prefetch_packet_idx_q == exec_idx_q);
  // SRAM bypass: read issued last cycle completes now; if it matches the
  // current exec index, use the SRAM output directly instead of waiting for
  // the served_packet_q latch (saves 1 cycle on every sequential access).
  assign sram_bypass_hit = buffer_read_pending_q &
                           (buffer_read_buf_q == active_buf_q) &
                           (buffer_read_idx_q == exec_idx_q);
  assign packet_cache_hit    = served_packet_hit | prefetch_packet_hit | sram_bypass_hit;
  assign packet_cache_data   = served_packet_hit   ? served_packet_q :
                               prefetch_packet_hit ? prefetch_packet_q :
                               (buffer_read_buf_q ? buffer_b_rdata : buffer_a_rdata);
  assign active_packet_valid = active_entry_valid & packet_cache_hit;

  always_comb begin : p_next_read_target
    next_buf         = active_buf_q;
    next_idx         = '0;
    next_entry_valid = 1'b0;
    if (exec_idx_q != LastPacketIdx) begin
      next_buf = active_buf_q;
      next_idx = exec_idx_q + 1;
      next_entry_valid = active_buf_q ? buffer_b_valid_q[next_idx] : buffer_a_valid_q[next_idx];
    end else if (replay_loop_lock) begin
      next_buf = active_buf_q;
      next_idx = '0;
      next_entry_valid = active_buf_q ? buffer_b_valid_q['0] : buffer_a_valid_q['0];
    end else if ((fill_buf_q != active_buf_q) && bg_fill_done_q) begin
      next_buf = fill_buf_q;
      next_idx = '0;
      next_entry_valid = fill_buf_q ? buffer_b_valid_q['0] : buffer_a_valid_q['0];
    end
  end

  assign next_packet_hit = ((served_packet_valid_q &&
                             (served_packet_buf_q == next_buf) &&
                             (served_packet_idx_q == next_idx)) ||
                            (prefetch_packet_valid_q &&
                             (prefetch_packet_buf_q == next_buf) &&
                             (prefetch_packet_idx_q == next_idx)));

  assign buffer_a_write = accept_rsp & !fill_buf_q;
  assign buffer_b_write = accept_rsp &  fill_buf_q;
  assign demand_read_req = (state_q == SERVE) & active_entry_valid & !packet_cache_hit &
                           !top_ipu_task_complete_i & !redirect_valid_i & !flush_i;
  assign prefetch_read_req = (state_q == SERVE) & active_entry_valid & packet_cache_hit &
                             next_entry_valid & !next_packet_hit & !loop_wait_q &
                             !top_ipu_task_complete_i & !redirect_valid_i & !flush_i;
  assign buffer_read_req = demand_read_req | prefetch_read_req;
  assign buffer_read_buf = demand_read_req ? active_buf_q : next_buf;
  assign buffer_read_idx = demand_read_req ? exec_idx_q : next_idx;
  assign buffer_a_read = buffer_read_req & !buffer_read_buf & !buffer_a_write;
  assign buffer_b_read = buffer_read_req &  buffer_read_buf & !buffer_b_write;
  assign buffer_read_fire = buffer_a_read | buffer_b_read;

  assign buffer_a_req   = buffer_a_write | buffer_a_read;
  assign buffer_b_req   = buffer_b_write | buffer_b_read;
  assign buffer_a_we    = buffer_a_write;
  assign buffer_b_we    = buffer_b_write;
  assign buffer_a_addr  = buffer_a_write ? IpuSramAddrWidth'(fill_rsp_idx_q) :
                                           IpuSramAddrWidth'(buffer_read_idx);
  assign buffer_b_addr  = buffer_b_write ? IpuSramAddrWidth'(fill_rsp_idx_q) :
                                           IpuSramAddrWidth'(buffer_read_idx);
  assign buffer_a_wdata = mem_ipu_rsp_data_i;
  assign buffer_b_wdata = mem_ipu_rsp_data_i;
  assign buffer_be      = '1;
  assign buffer_bweb    = {FetchPacketWidth{1'b0}};

  // Detect a 32-bit backward branch among the words of the packet being served.
  // The HDV task body is uncompressed (32-bit aligned), so each fetch packet
  // holds FetchPacketWidth/32 RISC-V words.  A taken backward branch must not
  // trigger a speculative buffer switch: if it did, the redirect would land
  // after exec_base has already advanced, miss the active buffer, and force a
  // needless refetch of the loop body on every iteration.
  always_comb begin : p_branch_scan
    automatic packet_t served_packet = packet_cache_data;
    served_pkt_has_bwd_branch = 1'b0;
    served_header = served_packet[31:0];
    served_header_imm20 = served_header[31:12];
    served_header_is_lui_hint = (served_header[6:0] == 7'b0110111) &&
                                (served_header[11:7] == 5'd0);
    served_pkt_loop_start = served_header_is_lui_hint & served_header_imm20[15];
    served_pkt_loop_end   = served_header_is_lui_hint & served_header_imm20[16];
    for (int unsigned w = 0; w < FetchPacketWidth/32; w++) begin
      if ((served_packet[w*32 +: 7] == 7'b1100011) &&  // BRANCH opcode
          (served_packet[w*32 + 31]  == 1'b1)) begin    // imm[12]=1 → backward
        served_pkt_has_bwd_branch = 1'b1;
      end
    end
  end

  // Stall at last slot when the next background buffer is not yet ready
  // (unless looping).  During first-buffer early serve, fill_buf==active_buf;
  // packet availability is then guarded by active_packet_valid instead.
  assign bg_stall    = (exec_idx_q == LastPacketIdx) & !bg_fill_done_q &
                       !replay_loop_lock & (fill_buf_q != active_buf_q);

  assign ipu_vliwpu_packet_valid_o = (state_q == SERVE) & active_packet_valid &
                                     !bg_stall & !loop_wait_q;
  assign ipu_vliwpu_packet_o       = packet_cache_data;
  assign ipu_vliwpu_packet_pc_o    = exec_base_q + addr_t'(exec_idx_q * PacketBytes);
  assign ipu_top_task_desc_o     = task_desc_q;

  assign take_packet    = ipu_vliwpu_packet_valid_o & vliwpu_ipu_packet_ready_i;

  always_comb begin : p_next
    state_d        = state_q;
    active_buf_d   = active_buf_q;
    fill_buf_d     = fill_buf_q;
    fill_req_idx_d = fill_req_idx_q;
    fill_rsp_idx_d = fill_rsp_idx_q;
    exec_idx_d     = exec_idx_q;
    fetch_base_d   = fetch_base_q;
    exec_base_d    = exec_base_q;
    task_desc_d    = task_desc_q;
    fill_req_done_d = fill_req_done_q;
    bg_fill_done_d = bg_fill_done_q;
    auto_loop_lock_d = auto_loop_lock_q;
    loop_wait_d      = loop_wait_q;
    loop_exit_seen_d = loop_exit_seen_q;
    loop_build_d     = loop_build_q;
    loop_locked_d    = loop_locked_q;
    loop_protect_d   = loop_protect_q;
    buffer_a_valid_d = buffer_a_valid_q;
    buffer_b_valid_d = buffer_b_valid_q;

    // Request and response indices are split so the IPU can keep several
    // in-order fetch requests outstanding while responses fill the buffer.
    if (accept_req) begin
      if (fill_req_idx_q == LastPacketIdx) begin
        fill_req_done_d = 1'b1;
      end else begin
        fill_req_idx_d = fill_req_idx_q + 1;
      end
    end
    if (accept_rsp && (fill_rsp_idx_q != LastPacketIdx)) begin
      fill_rsp_idx_d = fill_rsp_idx_q + 1;
    end
    if (accept_rsp) begin
      if (!fill_buf_q) begin
        buffer_a_valid_d[fill_rsp_idx_q] = 1'b1;
      end else begin
        buffer_b_valid_d[fill_rsp_idx_q] = 1'b1;
      end
    end

    // Highest-priority resets: task complete, redirect, flush.
    if (top_ipu_task_complete_i) begin
      state_d        = IDLE;
      fill_req_idx_d = '0;
      fill_rsp_idx_d = '0;
      exec_idx_d     = '0;
      fill_req_done_d = 1'b0;
      bg_fill_done_d = 1'b0;
      auto_loop_lock_d = 1'b0;
      loop_wait_d = 1'b0;
      loop_exit_seen_d = 1'b0;
      loop_build_d = 1'b0;
      loop_locked_d = 1'b0;
      loop_protect_d = '0;
      buffer_a_valid_d = '0;
      buffer_b_valid_d = '0;
    end else if (redirect_valid_i && redirect_aligned && redirect_in_active &&
                 redirect_active_packet_valid) begin
      // Redirect hit in the active buffer: replay from the target fetch packet
      // instead of invalidating the buffers and refetching the loop body.
      state_d      = SERVE;
      exec_idx_d   = redirect_exec_idx;
      loop_wait_d  = 1'b0;
      loop_exit_seen_d = 1'b0;
      if (redirect_is_backward) begin
        auto_loop_lock_d = 1'b1;
      end else begin
        auto_loop_lock_d = 1'b0;
      end
    end else if (redirect_valid_i && redirect_aligned && redirect_in_fill &&
                 redirect_fill_packet_valid && effective_loop_fetch_lock) begin
      // Redirect hit in the other protected buffer.  This is the key 2-buffer
      // loop-lock path: the loop body may span both ping-pong buffers.
      state_d      = SERVE;
      active_buf_d = fill_buf_q;
      fill_buf_d   = active_buf_q;
      exec_base_d  = fetch_base_q;
      fetch_base_d = exec_base_q;
      exec_idx_d   = redirect_fill_idx;
      fill_req_done_d = 1'b1;
      bg_fill_done_d = 1'b1;
      loop_wait_d  = 1'b0;
      loop_exit_seen_d = 1'b0;
      if (redirect_is_backward) begin
        auto_loop_lock_d = 1'b1;
      end else begin
        auto_loop_lock_d = 1'b0;
      end
    end else if (redirect_valid_i && redirect_aligned) begin
      state_d        = FILL;
      fill_req_idx_d = '0;
      fill_rsp_idx_d = '0;
      exec_idx_d     = '0;
      fetch_base_d   = redirect_pc_i;
      exec_base_d    = redirect_pc_i;
      active_buf_d   = 1'b0;
      fill_buf_d     = 1'b0;
      fill_req_done_d = 1'b0;
      bg_fill_done_d = 1'b0;
      auto_loop_lock_d = 1'b0;
      loop_wait_d = 1'b0;
      loop_exit_seen_d = 1'b0;
      loop_build_d = 1'b0;
      loop_locked_d = 1'b0;
      loop_protect_d = '0;
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
            fill_req_idx_d = '0;
            fill_rsp_idx_d = '0;
            exec_idx_d     = '0;
            fetch_base_d   = tsu_ipu_task_entry_i;
            exec_base_d    = tsu_ipu_task_entry_i;
            task_desc_d    = tsu_ipu_task_desc_i;
            active_buf_d   = 1'b0;
            fill_buf_d     = 1'b0;
            fill_req_done_d = 1'b0;
            bg_fill_done_d = 1'b0;
            auto_loop_lock_d = 1'b0;
            loop_wait_d = 1'b0;
            loop_exit_seen_d = 1'b0;
            loop_build_d = 1'b0;
            loop_locked_d = 1'b0;
            loop_protect_d = '0;
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
              fill_req_idx_d = '0;
              fill_rsp_idx_d = '0;
              fill_req_done_d = 1'b0;
              bg_fill_done_d = 1'b0;
              if (!fill_buf_q) begin
                buffer_b_valid_d = '0;
              end else begin
                buffer_a_valid_d = '0;
              end
            end
          end
        end

        // ----------------------------------------------------------------
        // Serve from active_buf; concurrently fill fill_buf in background.
        SERVE: begin
          // ---- active/background fill ------------------------------------
          if (loop_exit_i) begin
            auto_loop_lock_d = 1'b0;
            loop_build_d = 1'b0;
            loop_locked_d = 1'b0;
            loop_protect_d = '0;
            // Remember a not-taken exit that arrives while we hold on a branch,
            // so the buffer switch can complete once background fill is ready.
            if (loop_wait_q) loop_exit_seen_d = 1'b1;

            // If the loop lock has preserved the other buffer, repurpose it as
            // the fall-through prefetch buffer immediately after loop exit.
            if ((fill_buf_q != active_buf_q) && fill_buf_protected) begin
              fetch_base_d = exec_base_q + addr_t'(BufferBytes);
              fill_req_idx_d = '0;
              fill_rsp_idx_d = '0;
              fill_req_done_d = 1'b0;
              bg_fill_done_d = 1'b0;
              if (!fill_buf_q) begin
                buffer_a_valid_d = '0;
              end else begin
                buffer_b_valid_d = '0;
              end
            end
          end

          if (accept_rsp) begin
            if (fill_done) begin
              if (fill_buf_q == active_buf_q) begin
                // Early-serve phase completed the active buffer.  Move the
                // fill side to the other buffer and start background fill.
                fill_buf_d     = !fill_buf_q;
                fetch_base_d   = fetch_base_q + addr_t'(BufferBytes);
                fill_req_idx_d = '0;
                fill_rsp_idx_d = '0;
                fill_req_done_d = 1'b0;
                bg_fill_done_d = 1'b0;
                if (!fill_buf_q) begin
                  buffer_b_valid_d = '0;
                end else begin
                  buffer_a_valid_d = '0;
                end
              end else begin
                // Background fill of fill_buf is complete.  Hold indices at
                // their final values; the buffer switch will reset them.
                bg_fill_done_d = 1'b1;
              end
            end
          end

          // ---- release from a backward-branch hold ----------------------
          // A held loop only leaves the active buffer on a confirmed not-taken
          // exit.  We act on the *registered* loop_exit_seen_q, never on the
          // combinational loop_exit_i pulse: on a taken iteration loop_exit_i
          // can transiently pulse one cycle before the (deliberately delayed)
          // redirect arrives.  Acting one cycle later lets the high-priority
          // redirect-in-active block cancel the hold (it clears loop_exit_seen
          // and replays).  Only a genuine not-taken exit survives to here, so
          // taken iterations never switch buffers and never refetch.
          if (loop_wait_q && loop_exit_seen_q) begin
            if (exec_idx_q == LastPacketIdx) begin
              // Fall through to the next buffer once it is filled.
              if (bg_fill_done_q) begin
                active_buf_d   = fill_buf_q;
                exec_base_d    = fetch_base_q;
                exec_idx_d     = '0;
                fill_buf_d     = !fill_buf_q;
                fetch_base_d   = fetch_base_q + addr_t'(BufferBytes);
                fill_req_idx_d = '0;
                fill_rsp_idx_d = '0;
                fill_req_done_d = 1'b0;
                bg_fill_done_d = 1'b0;
                loop_wait_d      = 1'b0;
                loop_exit_seen_d = 1'b0;
                if (!fill_buf_q) begin
                  buffer_b_valid_d = '0;
                end else begin
                  buffer_a_valid_d = '0;
                end
              end
            end else begin
              // Fall-through target is the next packet in the same buffer.
              exec_idx_d       = exec_idx_q + 1;
              loop_wait_d      = 1'b0;
              loop_exit_seen_d = 1'b0;
            end
          end

          // ---- serve packets --------------------------------------------
          if (take_packet) begin
            if (served_pkt_loop_start) begin
              loop_build_d = 1'b1;
              loop_locked_d = 1'b0;
              if (active_buf_q) begin
                loop_protect_d[1] = 1'b1;
              end else begin
                loop_protect_d[0] = 1'b1;
              end
            end

            if (served_pkt_loop_end && (loop_build_q || served_pkt_loop_start)) begin
              loop_build_d = 1'b0;
              loop_locked_d = 1'b1;
              if (active_buf_q) begin
                loop_protect_d[1] = 1'b1;
              end else begin
                loop_protect_d[0] = 1'b1;
              end
            end

            if (served_pkt_has_bwd_branch && !replay_loop_lock) begin
              // Hold after dispatching a backward branch so the active buffer
              // stays resident.  A taken redirect then replays in-active (no
              // refetch); a not-taken loop_exit falls through above.  This is
              // what makes the loop lock actually engage: without it the buffer
              // would be switched speculatively before the branch resolves and
              // every iteration would refetch the loop body.
              loop_wait_d = 1'b1;
            end else if (exec_idx_q == LastPacketIdx) begin
              if (replay_loop_lock) begin
                // Explicit loop lock: external controller already knows the
                // loop is taken, so replay immediately.
                exec_idx_d = '0;
              end else if (effective_loop_fetch_lock && active_buf_protected) begin
                // Move into the other buffer while preserving the just-served
                // active buffer as part of the locked loop body.  Do not clear
                // or refill it; taken redirects may jump back to it.
                active_buf_d   = fill_buf_q;
                exec_base_d    = fetch_base_q;
                exec_idx_d     = '0;
                fill_buf_d     = active_buf_q;
                fetch_base_d   = exec_base_q;
                fill_req_idx_d = '0;
                fill_rsp_idx_d = '0;
                fill_req_done_d = 1'b1;
                bg_fill_done_d = 1'b1;
              end else begin
                // Straight-line last packet (no backward branch): switch to the
                // freshly filled background buffer.  bg_fill_done_q is 1 here
                // (bg_stall blocks take_packet until the bg fill completes).
                active_buf_d   = fill_buf_q;
                exec_base_d    = fetch_base_q;
                exec_idx_d     = '0;
                fill_buf_d     = !fill_buf_q;
                fetch_base_d   = fetch_base_q + addr_t'(BufferBytes);
                fill_req_idx_d = '0;
                fill_rsp_idx_d = '0;
                fill_req_done_d = 1'b0;
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
      fill_req_idx_d = '0;
      fill_rsp_idx_d = '0;
      exec_idx_d     = '0;
      active_buf_d   = 1'b0;
      fill_buf_d     = 1'b0;
      fill_req_done_d = 1'b0;
      bg_fill_done_d = 1'b0;
      auto_loop_lock_d = 1'b0;
      loop_wait_d = 1'b0;
      loop_exit_seen_d = 1'b0;
      loop_build_d = 1'b0;
      loop_locked_d = 1'b0;
      loop_protect_d = '0;
      buffer_a_valid_d = '0;
      buffer_b_valid_d = '0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q        <= IDLE;
      active_buf_q   <= 1'b0;
      fill_buf_q     <= 1'b0;
      fill_req_idx_q <= '0;
      fill_rsp_idx_q <= '0;
      exec_idx_q     <= '0;
      fetch_base_q   <= '0;
      exec_base_q    <= '0;
      task_desc_q    <= '0;
      fill_req_done_q <= 1'b0;
      bg_fill_done_q <= 1'b0;
      auto_loop_lock_q <= 1'b0;
      loop_wait_q <= 1'b0;
      loop_exit_seen_q <= 1'b0;
      loop_build_q <= 1'b0;
      loop_locked_q <= 1'b0;
      loop_protect_q <= '0;
      buffer_a_valid_q <= '0;
      buffer_b_valid_q <= '0;
    end else begin
      state_q        <= state_d;
      active_buf_q   <= active_buf_d;
      fill_buf_q     <= fill_buf_d;
      fill_req_idx_q <= fill_req_idx_d;
      fill_rsp_idx_q <= fill_rsp_idx_d;
      exec_idx_q     <= exec_idx_d;
      fetch_base_q   <= fetch_base_d;
      exec_base_q    <= exec_base_d;
      task_desc_q    <= task_desc_d;
      fill_req_done_q <= fill_req_done_d;
      bg_fill_done_q <= bg_fill_done_d;
      auto_loop_lock_q <= auto_loop_lock_d;
      loop_wait_q <= loop_wait_d;
      loop_exit_seen_q <= loop_exit_seen_d;
      loop_build_q <= loop_build_d;
      loop_locked_q <= loop_locked_d;
      loop_protect_q <= loop_protect_d;
      buffer_a_valid_q <= buffer_a_valid_d;
      buffer_b_valid_q <= buffer_b_valid_d;
    end
  end

`ifndef TARGET_SRAM_MC
  tc_sram #(
    .NumWords (IpuSramWords    ),
    .DataWidth(FetchPacketWidth),
    .NumPorts (1               )
  ) i_buffer_a_sram (
    .clk_i  (clk_i        ),
    .rst_ni (rst_ni       ),
    .req_i  (buffer_a_req ),
    .we_i   (buffer_a_we  ),
    .addr_i (buffer_a_addr),
    .wdata_i(buffer_a_wdata),
    .be_i   (buffer_be    ),
    .rdata_o(buffer_a_rdata)
  );

  tc_sram #(
    .NumWords (IpuSramWords    ),
    .DataWidth(FetchPacketWidth),
    .NumPorts (1               )
  ) i_buffer_b_sram (
    .clk_i  (clk_i        ),
    .rst_ni (rst_ni       ),
    .req_i  (buffer_b_req ),
    .we_i   (buffer_b_we  ),
    .addr_i (buffer_b_addr),
    .wdata_i(buffer_b_wdata),
    .be_i   (buffer_be    ),
    .rdata_o(buffer_b_rdata)
  );
`else
  TS1N28HPCPUHDSVTB32X128M1SWBSO i_buffer_a_sram (
    .SLP   (1'b0          ),
    .SD    (1'b0          ),
    .CLK   (clk_i         ),
    .CEB   (!buffer_a_req ),
    .WEB   (!buffer_a_we  ),
    .CEBM  (1'b1          ),
    .WEBM  (1'b1          ),
    .A     (buffer_a_addr ),
    .D     (buffer_a_wdata),
    .BWEB  (buffer_bweb   ),
    .AM    ('0            ),
    .DM    ('0            ),
    .BWEBM ('1            ),
    .BIST  (1'b0          ),
    .RTSEL (2'b01         ),
    .WTSEL (2'b00         ),
    .Q     (buffer_a_rdata)
  );

  TS1N28HPCPUHDSVTB32X128M1SWBSO i_buffer_b_sram (
    .SLP   (1'b0          ),
    .SD    (1'b0          ),
    .CLK   (clk_i         ),
    .CEB   (!buffer_b_req ),
    .WEB   (!buffer_b_we  ),
    .CEBM  (1'b1          ),
    .WEBM  (1'b1          ),
    .A     (buffer_b_addr ),
    .D     (buffer_b_wdata),
    .BWEB  (buffer_bweb   ),
    .AM    ('0            ),
    .DM    ('0            ),
    .BWEBM ('1            ),
    .BIST  (1'b0          ),
    .RTSEL (2'b01         ),
    .WTSEL (2'b00         ),
    .Q     (buffer_b_rdata)
  );
`endif

  always_comb begin : p_prefetch_keep
    keep_next_buf = active_buf_d;
    keep_next_idx = '0;
    keep_prefetch_next_valid = 1'b0;
    if (state_d == SERVE) begin
      if (exec_idx_d != LastPacketIdx) begin
        keep_next_buf = active_buf_d;
        keep_next_idx = exec_idx_d + 1;
        keep_prefetch_next_valid = active_buf_d ? buffer_b_valid_d[keep_next_idx] :
                                                  buffer_a_valid_d[keep_next_idx];
      end else if (replay_loop_lock) begin
        keep_next_buf = active_buf_d;
        keep_next_idx = '0;
        keep_prefetch_next_valid = active_buf_d ? buffer_b_valid_d['0] :
                                                  buffer_a_valid_d['0];
      end else if ((fill_buf_d != active_buf_d) && bg_fill_done_d) begin
        keep_next_buf = fill_buf_d;
        keep_next_idx = '0;
        keep_prefetch_next_valid = fill_buf_d ? buffer_b_valid_d['0] :
                                                buffer_a_valid_d['0];
      end
    end

    keep_prefetch_valid = prefetch_packet_valid_q && (state_d == SERVE) &&
                          (((prefetch_packet_buf_q == active_buf_d) &&
                            (prefetch_packet_idx_q == exec_idx_d)) ||
                           (keep_prefetch_next_valid &&
                            (prefetch_packet_buf_q == keep_next_buf) &&
                            (prefetch_packet_idx_q == keep_next_idx)));
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_buffer_read_cache
    if (!rst_ni) begin
      buffer_read_pending_q <= 1'b0;
      buffer_read_buf_q     <= 1'b0;
      buffer_read_idx_q     <= '0;
      served_packet_q       <= '0;
      served_packet_valid_q <= 1'b0;
      served_packet_buf_q   <= 1'b0;
      served_packet_idx_q   <= '0;
      prefetch_packet_q       <= '0;
      prefetch_packet_valid_q <= 1'b0;
      prefetch_packet_buf_q   <= 1'b0;
      prefetch_packet_idx_q   <= '0;
    end else begin
      buffer_read_pending_q <= buffer_read_fire;
      buffer_read_buf_q     <= buffer_read_buf;
      buffer_read_idx_q     <= buffer_read_idx;

      if (flush_i || top_ipu_task_complete_i ||
          (redirect_valid_i && !(redirect_aligned &&
            ((redirect_in_active && redirect_active_packet_valid) ||
             (redirect_in_fill && redirect_fill_packet_valid && effective_loop_fetch_lock))))) begin
        served_packet_valid_q <= 1'b0;
        prefetch_packet_valid_q <= 1'b0;
      end else if (served_packet_valid_q &&
                   !((state_d == SERVE) &&
                     (served_packet_buf_q == active_buf_d) &&
                     (served_packet_idx_q == exec_idx_d))) begin
        served_packet_valid_q <= 1'b0;
      end
      if (!keep_prefetch_valid) begin
        prefetch_packet_valid_q <= 1'b0;
      end

      if (buffer_read_pending_q) begin
        if ((state_d == SERVE) &&
            (active_buf_d == buffer_read_buf_q) &&
            (exec_idx_d == buffer_read_idx_q)) begin
          served_packet_q       <= buffer_read_buf_q ? buffer_b_rdata : buffer_a_rdata;
          served_packet_buf_q   <= buffer_read_buf_q;
          served_packet_idx_q   <= buffer_read_idx_q;
          served_packet_valid_q <= 1'b1;
        end else if (state_d == SERVE) begin
          prefetch_packet_q       <= buffer_read_buf_q ? buffer_b_rdata : buffer_a_rdata;
          prefetch_packet_buf_q   <= buffer_read_buf_q;
          prefetch_packet_idx_q   <= buffer_read_idx_q;
          prefetch_packet_valid_q <= 1'b1;
        end
      end

      if (accept_rsp) begin
        if ((state_d == SERVE) &&
            (active_buf_d == fill_buf_q) &&
            (exec_idx_d == fill_rsp_idx_q)) begin
          served_packet_q       <= mem_ipu_rsp_data_i;
          served_packet_buf_q   <= fill_buf_q;
          served_packet_idx_q   <= fill_rsp_idx_q;
          served_packet_valid_q <= 1'b1;
        end
        if ((state_d == SERVE) &&
            keep_prefetch_next_valid &&
            (keep_next_buf == fill_buf_q) &&
            (keep_next_idx == fill_rsp_idx_q)) begin
          prefetch_packet_q       <= mem_ipu_rsp_data_i;
          prefetch_packet_buf_q   <= fill_buf_q;
          prefetch_packet_idx_q   <= fill_rsp_idx_q;
          prefetch_packet_valid_q <= 1'b1;
        end
      end
    end
  end

  always_ff @(posedge clk_i) begin : p_redirect_alignment_check
    if (rst_ni && redirect_valid_i && !redirect_aligned) begin
      $fatal(1, "[HDV] redirect_pc_i must be %0d-byte aligned: 0x%0h",
             PacketBytes, redirect_pc_i);
    end
  end

`ifndef SYNTHESIS
  // Performance counters for IPU packet serving efficiency
  int unsigned ipu_perf_serve_cycles;    // cycles spent in SERVE state
  int unsigned ipu_perf_packets_served;  // total packets taken by VLIWPU
  int unsigned ipu_perf_bypass_hits;     // sram_bypass_hit was the sole hit source
  int unsigned ipu_perf_demand_reads;    // demand_read_req asserted (cache miss)

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_ipu_perf
    if (!rst_ni) begin
      ipu_perf_serve_cycles  <= 0;
      ipu_perf_packets_served <= 0;
      ipu_perf_bypass_hits   <= 0;
      ipu_perf_demand_reads  <= 0;
    end else begin
      if (state_q == SERVE)
        ipu_perf_serve_cycles <= ipu_perf_serve_cycles + 1;
      if (take_packet)
        ipu_perf_packets_served <= ipu_perf_packets_served + 1;
      if (sram_bypass_hit && !served_packet_hit && !prefetch_packet_hit)
        ipu_perf_bypass_hits <= ipu_perf_bypass_hits + 1;
      if (demand_read_req)
        ipu_perf_demand_reads <= ipu_perf_demand_reads + 1;
    end
  end

  final begin : p_ipu_perf_report
    $display("[IPU-PERF] serve_cycles=%0d packets=%0d bypass_hits=%0d demand_reads=%0d avg_cycles_per_pkt=%0d",
             ipu_perf_serve_cycles, ipu_perf_packets_served,
             ipu_perf_bypass_hits, ipu_perf_demand_reads,
             ipu_perf_packets_served > 0 ? ipu_perf_serve_cycles / ipu_perf_packets_served : 0);
  end
`endif

endmodule : hdv_instruction_prefetch_unit
