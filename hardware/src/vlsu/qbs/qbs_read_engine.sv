// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Two-outstanding QBS byte-range reader. Logical ranges are queued separately
// from AXI burst tags, so translation/AR planning can run ahead of ordered R
// responses. All ARs use the same AXI ID; the two-entry burst FIFO therefore
// provides the complete response-routing order.
module qbs_read_engine import qbs_pkg::*; #(
    parameter int unsigned AxiDataWidth    = 128,
    parameter int unsigned AxiAddrWidth    = 64,
    parameter int unsigned VAddrWidth      = 64,
    parameter int unsigned PAddrWidth      = 56,
    parameter int unsigned RangeBytesWidth = 16,
    parameter int unsigned ReadOutstanding = 2,
    parameter type         axi_ar_t        = logic,
    parameter type         axi_r_t         = logic,
    parameter type         exception_t     = logic,
    parameter type         tag_t           = logic
  ) (
    input  logic                         clk_i,
    input  logic                         rst_ni,

    input  logic                         range_valid_i,
    output logic                         range_ready_o,
    input  logic [VAddrWidth-1:0]        range_vaddr_i,
    input  logic [RangeBytesWidth-1:0]   range_bytes_i,
    input  tag_t                         range_tag_i,
    input  axi_pkg::cache_t              range_cache_i,
    input  axi_pkg::prot_t               range_prot_i,

    output logic                         data_valid_o,
    input  logic                         data_ready_i,
    output logic [AxiDataWidth-1:0]      data_o,
    output logic [AxiDataWidth/8-1:0]    data_strb_o,
    output logic [RangeBytesWidth-1:0]   data_offset_o,
    output tag_t                         data_tag_o,

    output logic                         completion_valid_o,
    input  logic                         completion_ready_i,
    output tag_t                         completion_tag_o,

    output logic                         fault_valid_o,
    input  logic                         fault_ready_i,
    output qbs_read_fault_e              fault_kind_o,
    output logic [VAddrWidth-1:0]        fault_vaddr_o,
    output tag_t                         fault_tag_o,
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

    input  logic                         counters_clear_i,
    output logic [31:0]                  range_count_o,
    output logic [31:0]                  translation_count_o,
    output logic [31:0]                  ar_count_o,
    output logic [31:0]                  r_beat_count_o,
    output logic [31:0]                  payload_byte_count_o,
    output logic [31:0]                  store_wait_cycles_o,
    output logic [31:0]                  r_backpressure_cycles_o,
    output logic [31:0]                  outstanding_occupancy_sum_o,
    output logic [1:0]                   outstanding_max_o,
    output logic [31:0]                  outstanding_full_cycles_o,
    output logic                         busy_o
  );

  localparam int unsigned BeatBytes = AxiDataWidth / 8;
  localparam int unsigned BeatOffsetWidth =
      BeatBytes > 1 ? $clog2(BeatBytes) : 1;
  localparam int unsigned MaxBurstBeats = 256;
  localparam int unsigned MaxBurstBytes = MaxBurstBeats * BeatBytes;
  localparam int unsigned QueueDepth = 2;

  typedef logic [AxiAddrWidth-1:0] axi_addr_t;
  typedef logic [VAddrWidth-1:0] vaddr_t;
  typedef logic [RangeBytesWidth-1:0] range_bytes_t;
  typedef logic [8:0] beat_count_t;

  typedef struct packed {
    vaddr_t          vaddr;
    range_bytes_t    bytes;
    tag_t            tag;
    axi_pkg::cache_t cache;
    axi_pkg::prot_t  prot;
  } range_entry_t;

  typedef struct packed {
    range_bytes_t                  bytes_left;
    beat_count_t                   beats_left;
    logic [BeatOffsetWidth-1:0]    first_lane;
    range_bytes_t                  range_offset;
    vaddr_t                        cursor_vaddr;
    tag_t                          tag;
    logic                          range_last;
    logic [15:0]                   subreq_seq;
  } burst_entry_t;

  typedef enum logic [1:0] {
    QBS_PLAN_IDLE,
    QBS_PLAN_WAIT_STORE,
    QBS_PLAN_TRANSLATE,
    QBS_PLAN_AR
  } qbs_plan_state_e;

  qbs_plan_state_e plan_state_q;

  range_entry_t range_fifo_q [QueueDepth];
  logic range_rd_q, range_wr_q;
  logic [1:0] range_fifo_count_q;

  burst_entry_t burst_fifo_q [QueueDepth];
  logic burst_rd_q, burst_wr_q;
  logic [1:0] burst_fifo_count_q;

  vaddr_t planner_cursor_q;
  range_bytes_t planner_remaining_q;
  range_bytes_t planner_offset_q;
  tag_t planner_tag_q;
  axi_pkg::cache_t planner_cache_q;
  axi_pkg::prot_t planner_prot_q;
  logic [15:0] planner_sequence_q;
  logic [15:0] next_sequence_q;

  axi_addr_t ar_addr_q;
  range_bytes_t ar_chunk_bytes_q;
  beat_count_t ar_beats_q;
  logic [BeatOffsetWidth-1:0] ar_first_lane_q;
  range_bytes_t ar_range_offset_q;
  vaddr_t ar_cursor_vaddr_q;
  tag_t ar_tag_q;
  axi_pkg::cache_t ar_cache_q;
  axi_pkg::prot_t ar_prot_q;
  logic ar_range_last_q;
  logic [15:0] ar_sequence_q;

  logic completion_valid_q;
  tag_t completion_tag_q;

  logic fault_pending_q;
  qbs_read_fault_e fault_kind_q;
  vaddr_t fault_vaddr_q;
  tag_t fault_tag_q;
  exception_t fault_mmu_exception_q;
  logic [15:0] fault_sequence_q;
  logic response_drain_q;

  axi_addr_t translated_addr;
  axi_addr_t planned_ar_addr;
  range_bytes_t planned_chunk_bytes;
  beat_count_t planned_beats;
  logic [BeatOffsetWidth-1:0] planned_first_lane;

  burst_entry_t response_head;
  range_bytes_t beat_take_bytes;
  logic expected_last;
  logic response_ok;
  logic response_error;
  logic protocol_error;
  logic completion_space;

  logic range_fire;
  logic range_pop;
  logic ar_fire;
  logic burst_pop;
  logic r_fire;
  logic data_fire;
  logic response_metadata_fire;
  logic range_completion_event;
  logic translation_complete;

  logic planner_empty_fault;
  logic planner_mmu_fault;
  logic planner_pma_fault;
  logic planner_fault_event;
  qbs_read_fault_e planner_fault_kind;
  vaddr_t planner_fault_vaddr;
  tag_t planner_fault_tag;
  exception_t planner_fault_mmu_exception;
  logic [15:0] planner_fault_sequence;

  logic response_fault_event;
  qbs_read_fault_e response_fault_kind;

`ifndef SYNTHESIS
  // Strict observation-only blocking counters for root-cause attribution.
  logic [31:0] probe_range_blocked_cycles_q;
  logic [31:0] probe_range_fifo_blocked_cycles_q;
  logic [31:0] probe_ar_slot_blocked_cycles_q;
  logic [31:0] probe_ar_ready_blocked_cycles_q;
  logic [31:0] probe_response_idle_cycles_q;
  logic [31:0] probe_data_sink_blocked_cycles_q;
  logic [31:0] probe_completion_blocked_cycles_q;
  logic [31:0] probe_translation_wait_cycles_q;
`endif

  // Do not acknowledge a range in the cycle that either side discovers a
  // command fault. Otherwise the FIFO write pointer can advance while the
  // accepted entry is discarded by the command-wide flush.
  assign range_ready_o = range_fifo_count_q < QueueDepth && !fault_pending_q &&
                         !planner_fault_event && !response_fault_event;
  assign range_fire = range_valid_i && range_ready_o;
  assign range_pop = plan_state_q == QBS_PLAN_IDLE &&
                     range_fifo_count_q != 0 && !fault_pending_q;

  assign completion_valid_o = completion_valid_q;
  assign completion_tag_o = completion_tag_q;
  assign fault_valid_o = fault_pending_q && burst_fifo_count_q == 0;
  assign fault_kind_o = fault_kind_q;
  assign fault_vaddr_o = fault_vaddr_q;
  assign fault_tag_o = fault_tag_q;
  assign fault_mmu_exception_o = fault_mmu_exception_q;

  assign busy_o = range_fifo_count_q != 0 ||
                  plan_state_q != QBS_PLAN_IDLE ||
                  burst_fifo_count_q != 0 || completion_valid_q ||
                  fault_pending_q;

  assign mmu_req_o = plan_state_q == QBS_PLAN_TRANSLATE &&
      en_ld_st_translation_i && !mmu_valid_i &&
      !mmu_exception_valid_i && !fault_pending_q;
  assign mmu_vaddr_o = planner_cursor_q;
  assign mmu_is_store_o = 1'b0;
  assign translation_complete = plan_state_q == QBS_PLAN_TRANSLATE &&
      en_ld_st_translation_i &&
      (mmu_exception_valid_i || mmu_valid_i);

  always_comb begin : plan_burst
    automatic int unsigned first_lane;
    automatic int unsigned bytes_to_page;
    automatic int unsigned bytes_to_axi_limit;
    automatic int unsigned chunk_bytes;
    automatic int unsigned span_bytes;
    automatic int unsigned beat_count;

    if (en_ld_st_translation_i)
      translated_addr = AxiAddrWidth'(mmu_paddr_i);
    else
      translated_addr = AxiAddrWidth'(planner_cursor_q);

    first_lane = unsigned'(translated_addr[BeatOffsetWidth-1:0]);
    bytes_to_page = 4096 - unsigned'(planner_cursor_q[11:0]);
    bytes_to_axi_limit = MaxBurstBytes - first_lane;
    chunk_bytes = unsigned'(planner_remaining_q);
    if (chunk_bytes > bytes_to_page)
      chunk_bytes = bytes_to_page;
    if (chunk_bytes > bytes_to_axi_limit)
      chunk_bytes = bytes_to_axi_limit;
    span_bytes = first_lane + chunk_bytes;
    beat_count = (span_bytes + BeatBytes - 1) / BeatBytes;

    planned_ar_addr = translated_addr;
    planned_ar_addr[BeatOffsetWidth-1:0] = '0;
    planned_chunk_bytes = RangeBytesWidth'(chunk_bytes);
    planned_beats = beat_count_t'(beat_count);
    planned_first_lane = BeatOffsetWidth'(first_lane);
  end

  assign physical_check_valid_o = plan_state_q == QBS_PLAN_TRANSLATE &&
      !fault_pending_q && !mmu_exception_valid_i &&
      (!en_ld_st_translation_i || mmu_valid_i);
  assign physical_check_addr_o = planned_ar_addr;
  assign physical_check_bytes_o =
      13'(unsigned'(planned_beats) * BeatBytes);

  assign axi_ar_o = '{
    addr   : ar_addr_q,
    len    : axi_pkg::len_t'(ar_beats_q - 1'b1),
    size   : axi_pkg::size_t'(BeatOffsetWidth),
    burst  : axi_pkg::BURST_INCR,
    cache  : ar_cache_q,
    prot   : ar_prot_q,
    default: '0
  };
  assign axi_ar_valid_o = plan_state_q == QBS_PLAN_AR &&
      burst_fifo_count_q < ReadOutstanding && !fault_pending_q &&
      !response_fault_event;
  assign ar_fire = axi_ar_valid_o && axi_ar_ready_i;

  always_comb begin
    response_head = '0;
    if (burst_fifo_count_q != 0)
      response_head = burst_fifo_q[burst_rd_q];
  end

  always_comb begin : compact_read_beat
    automatic int unsigned available_bytes;
    automatic int unsigned take_bytes;

    available_bytes = BeatBytes - unsigned'(response_head.first_lane);
    take_bytes = unsigned'(response_head.bytes_left);
    if (take_bytes > available_bytes)
      take_bytes = available_bytes;
    beat_take_bytes = RangeBytesWidth'(take_bytes);

    data_o = '0;
    data_strb_o = '0;
    for (int unsigned byte_lane = 0; byte_lane < BeatBytes; byte_lane++) begin
      if (byte_lane < take_bytes) begin
        data_o[byte_lane*8 +: 8] =
            axi_r_i.data[(unsigned'(response_head.first_lane) +
                          byte_lane)*8 +: 8];
        data_strb_o[byte_lane] = 1'b1;
      end
    end
  end

  assign data_offset_o = response_head.range_offset;
  assign data_tag_o = response_head.tag;
  assign expected_last = response_head.beats_left == 1;
  assign response_ok = axi_r_i.resp == axi_pkg::RESP_OKAY ||
                       axi_r_i.resp == axi_pkg::RESP_EXOKAY;
  assign response_error = axi_r_valid_i && burst_fifo_count_q != 0 &&
                          !response_drain_q && !response_ok;
  assign protocol_error = axi_r_valid_i && burst_fifo_count_q != 0 &&
                          !response_drain_q &&
                          (axi_r_i.last != expected_last);
  assign response_fault_event = response_error || protocol_error;
  assign response_fault_kind = response_error
      ? QBS_READ_FAULT_AXI_RESPONSE : QBS_READ_FAULT_AXI_PROTOCOL;

  assign completion_space = !completion_valid_q || completion_ready_i;
  assign data_valid_o = axi_r_valid_i && burst_fifo_count_q != 0 &&
                        !fault_pending_q && !response_drain_q &&
                        !response_fault_event &&
                        (!(expected_last && response_head.range_last) ||
                         completion_space);

  always_comb begin
    axi_r_ready_o = 1'b0;
    if (burst_fifo_count_q != 0) begin
      if (fault_pending_q || response_drain_q || response_fault_event)
        axi_r_ready_o = 1'b1;
      else
        axi_r_ready_o = data_ready_i &&
            (!(expected_last && response_head.range_last) ||
             completion_space);
    end
  end

  assign r_fire = axi_r_valid_i && axi_r_ready_o;
  assign data_fire = data_valid_o && data_ready_i && axi_r_ready_o;
  // A planner fault stops payload delivery but older AXI responses must still
  // advance their burst metadata while draining. Otherwise a legal RLAST is
  // compared against stale beats_left and can fabricate an earlier fault.
  assign response_metadata_fire = r_fire && !response_fault_event &&
                                  !response_drain_q;
  assign burst_pop = r_fire && axi_r_i.last;
  assign range_completion_event = data_fire && expected_last && axi_r_i.last &&
                                  response_head.range_last;

  assign planner_empty_fault = range_pop && range_fifo_q[range_rd_q].bytes == 0;
  assign planner_mmu_fault = plan_state_q == QBS_PLAN_TRANSLATE &&
                             mmu_exception_valid_i;
  assign planner_pma_fault = physical_check_valid_o &&
                             !physical_range_allowed_i;
  assign planner_fault_event = planner_empty_fault || planner_mmu_fault ||
                               planner_pma_fault;

  always_comb begin
    planner_fault_kind = QBS_READ_FAULT_REQUEST;
    planner_fault_vaddr = planner_cursor_q;
    planner_fault_tag = planner_tag_q;
    planner_fault_mmu_exception = '0;
    planner_fault_sequence = planner_sequence_q;
    if (planner_empty_fault) begin
      planner_fault_vaddr = range_fifo_q[range_rd_q].vaddr;
      planner_fault_tag = range_fifo_q[range_rd_q].tag;
      planner_fault_sequence = next_sequence_q;
    end else if (planner_mmu_fault) begin
      planner_fault_kind = QBS_READ_FAULT_MMU;
      planner_fault_mmu_exception = mmu_exception_i;
    end else if (planner_pma_fault) begin
      planner_fault_kind = QBS_READ_FAULT_PMA;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      range_rd_q <= '0;
      range_wr_q <= '0;
      range_fifo_count_q <= '0;
    end else begin
      if (range_fire) begin
        range_fifo_q[range_wr_q] <= '{
          vaddr: range_vaddr_i,
          bytes: range_bytes_i,
          tag  : range_tag_i,
          cache: range_cache_i,
          prot : range_prot_i
        };
        range_wr_q <= range_wr_q + 1'b1;
      end
      if (range_pop)
        range_rd_q <= range_rd_q + 1'b1;

      unique case ({range_fire, range_pop})
        2'b10: range_fifo_count_q <= range_fifo_count_q + 1'b1;
        2'b01: range_fifo_count_q <= range_fifo_count_q - 1'b1;
        default: ;
      endcase

      if (planner_fault_event || response_fault_event || fault_pending_q) begin
        range_rd_q <= range_wr_q;
        range_fifo_count_q <= '0;
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      plan_state_q <= QBS_PLAN_IDLE;
      planner_cursor_q <= '0;
      planner_remaining_q <= '0;
      planner_offset_q <= '0;
      planner_tag_q <= '0;
      planner_cache_q <= '0;
      planner_prot_q <= '0;
      planner_sequence_q <= '0;
      next_sequence_q <= '0;
      ar_addr_q <= '0;
      ar_chunk_bytes_q <= '0;
      ar_beats_q <= '0;
      ar_first_lane_q <= '0;
      ar_range_offset_q <= '0;
      ar_cursor_vaddr_q <= '0;
      ar_tag_q <= '0;
      ar_cache_q <= '0;
      ar_prot_q <= '0;
      ar_range_last_q <= 1'b0;
      ar_sequence_q <= '0;
    end else begin
      if (counters_clear_i)
        next_sequence_q <= '0;

      if (planner_fault_event || response_fault_event || fault_pending_q) begin
        plan_state_q <= QBS_PLAN_IDLE;
      end else begin
        unique case (plan_state_q)
          QBS_PLAN_IDLE: begin
            if (range_pop) begin
              planner_cursor_q <= range_fifo_q[range_rd_q].vaddr;
              planner_remaining_q <= range_fifo_q[range_rd_q].bytes;
              planner_offset_q <= '0;
              planner_tag_q <= range_fifo_q[range_rd_q].tag;
              planner_cache_q <= range_fifo_q[range_rd_q].cache;
              planner_prot_q <= range_fifo_q[range_rd_q].prot;
              planner_sequence_q <= next_sequence_q;
              next_sequence_q <= next_sequence_q + 1'b1;
              if (range_fifo_q[range_rd_q].bytes != 0)
                plan_state_q <= QBS_PLAN_WAIT_STORE;
            end
          end

          QBS_PLAN_WAIT_STORE: begin
            if (!core_st_pending_i)
              plan_state_q <= QBS_PLAN_TRANSLATE;
          end

          QBS_PLAN_TRANSLATE: begin
            if (!mmu_exception_valid_i &&
                (!en_ld_st_translation_i || mmu_valid_i) &&
                physical_range_allowed_i) begin
              ar_addr_q <= planned_ar_addr;
              ar_chunk_bytes_q <= planned_chunk_bytes;
              ar_beats_q <= planned_beats;
              ar_first_lane_q <= planned_first_lane;
              ar_range_offset_q <= planner_offset_q;
              ar_cursor_vaddr_q <= planner_cursor_q;
              ar_tag_q <= planner_tag_q;
              ar_cache_q <= planner_cache_q;
              ar_prot_q <= planner_prot_q;
              ar_range_last_q <= planner_remaining_q == planned_chunk_bytes;
              ar_sequence_q <= planner_sequence_q;
              plan_state_q <= QBS_PLAN_AR;
            end
          end

          QBS_PLAN_AR: begin
            if (ar_fire) begin
              if (planner_remaining_q == ar_chunk_bytes_q) begin
                plan_state_q <= QBS_PLAN_IDLE;
              end else begin
                planner_cursor_q <= planner_cursor_q + ar_chunk_bytes_q;
                planner_remaining_q <= planner_remaining_q - ar_chunk_bytes_q;
                planner_offset_q <= planner_offset_q + ar_chunk_bytes_q;
                planner_sequence_q <= next_sequence_q;
                next_sequence_q <= next_sequence_q + 1'b1;
                plan_state_q <= QBS_PLAN_TRANSLATE;
              end
            end
          end

          default: plan_state_q <= QBS_PLAN_IDLE;
        endcase
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      burst_rd_q <= '0;
      burst_wr_q <= '0;
      burst_fifo_count_q <= '0;
      response_drain_q <= 1'b0;
    end else begin
      if (ar_fire) begin
        burst_fifo_q[burst_wr_q] <= '{
          bytes_left : ar_chunk_bytes_q,
          beats_left : ar_beats_q,
          first_lane : ar_first_lane_q,
          range_offset: ar_range_offset_q,
          cursor_vaddr: ar_cursor_vaddr_q,
          tag         : ar_tag_q,
          range_last  : ar_range_last_q,
          subreq_seq  : ar_sequence_q
        };
        burst_wr_q <= burst_wr_q + 1'b1;
      end

      if (response_metadata_fire && !burst_pop) begin
        burst_fifo_q[burst_rd_q].bytes_left <=
            response_head.bytes_left - beat_take_bytes;
        burst_fifo_q[burst_rd_q].beats_left <=
            response_head.beats_left - 1'b1;
        burst_fifo_q[burst_rd_q].first_lane <= '0;
        burst_fifo_q[burst_rd_q].range_offset <=
            response_head.range_offset + beat_take_bytes;
        burst_fifo_q[burst_rd_q].cursor_vaddr <=
            response_head.cursor_vaddr + beat_take_bytes;
      end

      if (response_fault_event && axi_r_valid_i && !axi_r_i.last)
        response_drain_q <= 1'b1;
      if (burst_pop) begin
        burst_rd_q <= burst_rd_q + 1'b1;
        response_drain_q <= 1'b0;
      end

      unique case ({ar_fire, burst_pop})
        2'b10: burst_fifo_count_q <= burst_fifo_count_q + 1'b1;
        2'b01: burst_fifo_count_q <= burst_fifo_count_q - 1'b1;
        default: ;
      endcase
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      completion_valid_q <= 1'b0;
      completion_tag_q <= '0;
    end else begin
      if (completion_valid_q && completion_ready_i)
        completion_valid_q <= 1'b0;
      if (range_completion_event) begin
        completion_valid_q <= 1'b1;
        completion_tag_q <= response_head.tag;
      end
      if (planner_fault_event || response_fault_event || fault_pending_q)
        completion_valid_q <= 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      fault_pending_q <= 1'b0;
      fault_kind_q <= QBS_READ_FAULT_NONE;
      fault_vaddr_q <= '0;
      fault_tag_q <= '0;
      fault_mmu_exception_q <= '0;
      fault_sequence_q <= '1;
    end else begin
      if (fault_valid_o && fault_ready_i) begin
        fault_pending_q <= 1'b0;
        fault_sequence_q <= '1;
      end

      if (planner_fault_event &&
          (!fault_pending_q || planner_fault_sequence < fault_sequence_q)) begin
        fault_pending_q <= 1'b1;
        fault_kind_q <= planner_fault_kind;
        fault_vaddr_q <= planner_fault_vaddr;
        fault_tag_q <= planner_fault_tag;
        fault_mmu_exception_q <= planner_fault_mmu_exception;
        fault_sequence_q <= planner_fault_sequence;
      end

      if (response_fault_event &&
          (!fault_pending_q || response_head.subreq_seq < fault_sequence_q) &&
          !(planner_fault_event &&
            planner_fault_sequence < response_head.subreq_seq)) begin
        fault_pending_q <= 1'b1;
        fault_kind_q <= response_fault_kind;
        fault_vaddr_q <= response_head.cursor_vaddr;
        fault_tag_q <= response_head.tag;
        fault_mmu_exception_q <= '0;
        fault_sequence_q <= response_head.subreq_seq;
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      range_count_o <= '0;
      translation_count_o <= '0;
      ar_count_o <= '0;
      r_beat_count_o <= '0;
      payload_byte_count_o <= '0;
      store_wait_cycles_o <= '0;
      r_backpressure_cycles_o <= '0;
      outstanding_occupancy_sum_o <= '0;
      outstanding_max_o <= '0;
      outstanding_full_cycles_o <= '0;
    end else if (counters_clear_i) begin
      range_count_o <= '0;
      translation_count_o <= '0;
      ar_count_o <= '0;
      r_beat_count_o <= '0;
      payload_byte_count_o <= '0;
      store_wait_cycles_o <= '0;
      r_backpressure_cycles_o <= '0;
      outstanding_occupancy_sum_o <= '0;
      outstanding_max_o <= '0;
      outstanding_full_cycles_o <= '0;
    end else begin
      if (range_fire)
        range_count_o <= range_count_o + 1'b1;
      if (translation_complete)
        translation_count_o <= translation_count_o + 1'b1;
      if (ar_fire)
        ar_count_o <= ar_count_o + 1'b1;
      if (r_fire)
        r_beat_count_o <= r_beat_count_o + 1'b1;
      if (data_fire)
        payload_byte_count_o <= payload_byte_count_o + beat_take_bytes;
      if (plan_state_q == QBS_PLAN_WAIT_STORE && core_st_pending_i)
        store_wait_cycles_o <= store_wait_cycles_o + 1'b1;
      if (burst_fifo_count_q != 0 && axi_r_valid_i &&
          !response_fault_event && !fault_pending_q && !response_drain_q &&
          !axi_r_ready_o)
        r_backpressure_cycles_o <= r_backpressure_cycles_o + 1'b1;
      outstanding_occupancy_sum_o <= outstanding_occupancy_sum_o +
          burst_fifo_count_q;
      if (burst_fifo_count_q > outstanding_max_o)
        outstanding_max_o <= burst_fifo_count_q;
      if (burst_fifo_count_q == ReadOutstanding)
        outstanding_full_cycles_o <= outstanding_full_cycles_o + 1'b1;
    end
  end

`ifndef SYNTHESIS
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      probe_range_blocked_cycles_q <= '0;
      probe_range_fifo_blocked_cycles_q <= '0;
      probe_ar_slot_blocked_cycles_q <= '0;
      probe_ar_ready_blocked_cycles_q <= '0;
      probe_response_idle_cycles_q <= '0;
      probe_data_sink_blocked_cycles_q <= '0;
      probe_completion_blocked_cycles_q <= '0;
      probe_translation_wait_cycles_q <= '0;
    end else if (counters_clear_i) begin
      probe_range_blocked_cycles_q <= '0;
      probe_range_fifo_blocked_cycles_q <= '0;
      probe_ar_slot_blocked_cycles_q <= '0;
      probe_ar_ready_blocked_cycles_q <= '0;
      probe_response_idle_cycles_q <= '0;
      probe_data_sink_blocked_cycles_q <= '0;
      probe_completion_blocked_cycles_q <= '0;
      probe_translation_wait_cycles_q <= '0;
    end else begin
      if (range_valid_i && !range_ready_o) begin
        probe_range_blocked_cycles_q <= probe_range_blocked_cycles_q + 1'b1;
        if (range_fifo_count_q == QueueDepth)
          probe_range_fifo_blocked_cycles_q <=
              probe_range_fifo_blocked_cycles_q + 1'b1;
      end
      if (plan_state_q == QBS_PLAN_AR &&
          burst_fifo_count_q == ReadOutstanding && !fault_pending_q &&
          !response_fault_event)
        probe_ar_slot_blocked_cycles_q <=
            probe_ar_slot_blocked_cycles_q + 1'b1;
      if (axi_ar_valid_o && !axi_ar_ready_i)
        probe_ar_ready_blocked_cycles_q <=
            probe_ar_ready_blocked_cycles_q + 1'b1;
      if (burst_fifo_count_q != 0 && !axi_r_valid_i)
        probe_response_idle_cycles_q <=
            probe_response_idle_cycles_q + 1'b1;
      if (data_valid_o && !data_ready_i)
        probe_data_sink_blocked_cycles_q <=
            probe_data_sink_blocked_cycles_q + 1'b1;
      if (completion_valid_o && !completion_ready_i)
        probe_completion_blocked_cycles_q <=
            probe_completion_blocked_cycles_q + 1'b1;
      if (plan_state_q == QBS_PLAN_TRANSLATE &&
          en_ld_st_translation_i && !mmu_valid_i &&
          !mmu_exception_valid_i)
        probe_translation_wait_cycles_q <=
            probe_translation_wait_cycles_q + 1'b1;
    end
  end

  initial begin
    assert (AxiDataWidth >= 8 && AxiDataWidth % 8 == 0)
      else $fatal(1, "QBS AXI data width must contain whole bytes");
    assert ((BeatBytes & (BeatBytes - 1)) == 0)
      else $fatal(1, "QBS AXI beat bytes must be a power of two");
    assert (BeatBytes <= 4096)
      else $fatal(1, "QBS AXI beat cannot exceed a page");
    assert (RangeBytesWidth >= 13)
      else $fatal(1, "QBS range width must represent a full page");
    assert (ReadOutstanding == 2)
      else $fatal(1, "QBS Full read engine requires two ordered slots");
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni) begin
      assert (range_fifo_count_q <= QueueDepth)
        else $fatal(1, "QBS range FIFO overflow");
      assert (burst_fifo_count_q <= ReadOutstanding)
        else $fatal(1, "QBS burst tag FIFO overflow");
      if (axi_r_valid_i)
        assert (burst_fifo_count_q != 0)
          else $fatal(1, "QBS received R data without an outstanding tag");
      if (ar_fire) begin
        assert (ar_beats_q inside {[1:MaxBurstBeats]});
        assert (ar_addr_q[BeatOffsetWidth-1:0] == '0);
        assert (unsigned'(ar_addr_q[11:0]) +
                unsigned'(ar_beats_q) * BeatBytes <= 4096)
          else $fatal(1, "QBS AR crosses a 4-KiB page");
      end
      if (data_fire) begin
        assert (beat_take_bytes != 0);
        assert (response_head.bytes_left >= beat_take_bytes);
      end
      if (range_completion_event)
        assert (completion_space)
          else $fatal(1, "QBS completion register overflow");
      if (fault_valid_o)
        assert (burst_fifo_count_q == 0 && !axi_ar_valid_o)
          else $fatal(1, "QBS fault reported before read drain");
    end
  end
`endif

endmodule : qbs_read_engine
