`timescale 1ns/1ps

module qbs_read_engine_tb;
  import qbs_pkg::*;
  import axi_pkg::*;

  `include "axi/typedef.svh"

  localparam int unsigned AxiDataWidth = 128;
  localparam int unsigned BeatBytes = AxiDataWidth / 8;

  typedef logic [63:0] axi_addr_t;
  typedef logic [AxiDataWidth-1:0] axi_data_t;
  typedef logic [0:0] axi_id_t;
  typedef logic [0:0] axi_user_t;
  typedef logic [7:0] tag_t;
  typedef struct packed {
    logic [63:0] cause;
    logic [63:0] tval;
    logic valid;
  } exception_t;

  `AXI_TYPEDEF_AR_CHAN_T(axi_ar_t, axi_addr_t, axi_id_t, axi_user_t)
  `AXI_TYPEDEF_R_CHAN_T(axi_r_t, axi_data_t, axi_id_t, axi_user_t)

  logic clk;
  logic rst_n;

  logic range_valid;
  logic range_ready;
  logic [63:0] range_vaddr;
  logic [15:0] range_bytes;
  tag_t range_tag;
  cache_t range_cache;
  prot_t range_prot;

  logic data_valid;
  logic data_ready;
  logic [127:0] data;
  logic [15:0] data_strb;
  logic [15:0] data_offset;
  tag_t data_tag;

  logic completion_valid;
  logic completion_ready;
  tag_t completion_tag;
  logic fault_valid;
  logic fault_ready;
  qbs_read_fault_e fault_kind;
  logic [63:0] fault_vaddr;
  tag_t fault_tag;
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

  logic counters_clear;
  logic [31:0] range_count;
  logic [31:0] translation_count;
  logic [31:0] ar_count;
  logic [31:0] r_beat_count;
  logic [31:0] payload_byte_count;
  logic [31:0] store_wait_cycles;
  logic [31:0] r_backpressure_cycles;
  logic [31:0] outstanding_occupancy_sum;
  logic [1:0] outstanding_max;
  logic [31:0] outstanding_full_cycles;
  logic busy;

  qbs_read_engine #(
    .AxiDataWidth    (AxiDataWidth),
    .AxiAddrWidth    (64),
    .VAddrWidth      (64),
    .PAddrWidth      (64),
    .RangeBytesWidth (16),
    .axi_ar_t        (axi_ar_t),
    .axi_r_t         (axi_r_t),
    .exception_t     (exception_t),
    .tag_t           (tag_t)
  ) dut (
    .clk_i                     (clk),
    .rst_ni                    (rst_n),
    .range_valid_i             (range_valid),
    .range_ready_o             (range_ready),
    .range_vaddr_i             (range_vaddr),
    .range_bytes_i             (range_bytes),
    .range_tag_i               (range_tag),
    .range_cache_i             (range_cache),
    .range_prot_i              (range_prot),
    .data_valid_o              (data_valid),
    .data_ready_i              (data_ready),
    .data_o                    (data),
    .data_strb_o               (data_strb),
    .data_offset_o             (data_offset),
    .data_tag_o                (data_tag),
    .completion_valid_o        (completion_valid),
    .completion_ready_i        (completion_ready),
    .completion_tag_o          (completion_tag),
    .fault_valid_o             (fault_valid),
    .fault_ready_i             (fault_ready),
    .fault_kind_o              (fault_kind),
    .fault_vaddr_o             (fault_vaddr),
    .fault_tag_o               (fault_tag),
    .fault_mmu_exception_o     (fault_mmu_exception),
    .core_st_pending_i         (core_st_pending),
    .en_ld_st_translation_i    (translation_enable),
    .mmu_req_o                 (mmu_req),
    .mmu_vaddr_o               (mmu_vaddr),
    .mmu_is_store_o            (mmu_is_store),
    .mmu_valid_i               (mmu_valid),
    .mmu_paddr_i               (mmu_paddr),
    .mmu_exception_valid_i     (mmu_exception_valid),
    .mmu_exception_i           (mmu_exception),
    .physical_check_valid_o    (physical_check_valid),
    .physical_check_addr_o     (physical_check_addr),
    .physical_check_bytes_o    (physical_check_bytes),
    .physical_range_allowed_i  (physical_range_allowed),
    .axi_ar_o                  (axi_ar),
    .axi_ar_valid_o            (axi_ar_valid),
    .axi_ar_ready_i            (axi_ar_ready),
    .axi_r_i                   (axi_r),
    .axi_r_valid_i             (axi_r_valid),
    .axi_r_ready_o             (axi_r_ready),
    .counters_clear_i          (counters_clear),
    .range_count_o             (range_count),
    .translation_count_o       (translation_count),
    .ar_count_o                (ar_count),
    .r_beat_count_o            (r_beat_count),
    .payload_byte_count_o      (payload_byte_count),
    .store_wait_cycles_o       (store_wait_cycles),
    .r_backpressure_cycles_o   (r_backpressure_cycles),
    .outstanding_occupancy_sum_o(outstanding_occupancy_sum),
    .outstanding_max_o         (outstanding_max),
    .outstanding_full_cycles_o (outstanding_full_cycles),
    .busy_o                    (busy)
  );

  always #5 clk = ~clk;

  function automatic logic [7:0] memory_byte(input logic [63:0] address);
    return address[7:0] ^ address[15:8] ^ address[23:16] ^ 8'h5a;
  endfunction

  // Synthetic page translations, not a page-table walker or a CVA6 MMU model.
  localparam logic [63:0] ContractVa0 = 64'h0000_0040_0120_0000;
  localparam logic [63:0] ContractVa1 = ContractVa0 + 64'h1000;
  localparam logic [63:0] ContractPa0 = 64'h0000_0002_83a5_0000;
  localparam logic [63:0] ContractPa1 = 64'h0000_0000_915b_7000;
  localparam logic [63:0] ContractOldVa = 64'h0000_0040_0240_0000;
  localparam logic [63:0] ContractOldPa = 64'h0000_0003_a67c_2000;
  localparam logic [63:0] ContractQueuedVa = 64'h0000_0040_0350_0000;
  localparam logic [63:0] ContractQueuedPa = 64'h0000_0001_b89d_4000;
  localparam cache_t ContractCache = 4'b1011;
  localparam prot_t ContractProt = 3'b010;
  logic mapped_mmu;
  logic second_page_fault;
  logic contract_active;
  logic inject_mmu_fault;

  function automatic logic [63:0] model_paddr(input logic [63:0] vaddr);
    if (!mapped_mmu)
      return vaddr;
    case ({vaddr[63:12], 12'b0})
      ContractVa0: return ContractPa0 + {52'b0, vaddr[11:0]};
      ContractVa1: return ContractPa1 + {52'b0, vaddr[11:0]};
      ContractOldVa: return ContractOldPa + {52'b0, vaddr[11:0]};
      ContractQueuedVa: return ContractQueuedPa + {52'b0, vaddr[11:0]};
      default: begin
        $fatal(1, "unmapped synthetic MMU request vaddr=%h", vaddr);
        return '0;
      end
    endcase
  endfunction

  function automatic logic model_mmu_fault(input logic [63:0] vaddr);
    return inject_mmu_fault || (mapped_mmu && second_page_fault &&
                               vaddr[63:12] == ContractVa1[63:12]);
  endfunction

  // A response acknowledges the level request; it must not start a duplicate
  // translation. COMBINATIONAL_MMU also models a same-cycle TLB/PMP response.
  logic mmu_pending;
  logic [63:0] mmu_pending_vaddr;
  logic mmu_pending_fault;
  bit combinational_mmu;
  logic mmu_reply_valid;
  logic [63:0] mmu_reply_paddr;
  exception_t mmu_reply_exception;

  always_comb begin
    mmu_valid = mmu_reply_valid;
    mmu_paddr = mmu_reply_paddr;
    mmu_exception = mmu_reply_exception;
    if (combinational_mmu) begin
      mmu_valid = mmu_req && !model_mmu_fault(mmu_vaddr);
      mmu_paddr = mmu_req ? model_paddr(mmu_vaddr) : '0;
      mmu_exception = '0;
      if (mmu_req && model_mmu_fault(mmu_vaddr)) begin
        mmu_exception.valid = 1'b1;
        mmu_exception.cause = 64'd13;
        mmu_exception.tval = mmu_vaddr;
      end
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mmu_pending <= 1'b0;
      mmu_pending_vaddr <= '0;
      mmu_pending_fault <= 1'b0;
      mmu_reply_valid <= 1'b0;
      mmu_reply_paddr <= '0;
      mmu_reply_exception <= '0;
    end else begin
      mmu_reply_valid <= 1'b0;
      mmu_reply_exception <= '0;
      if (!combinational_mmu && !mmu_pending && mmu_req && !mmu_reply_valid) begin
        mmu_pending <= 1'b1;
        mmu_pending_vaddr <= mmu_vaddr;
        mmu_pending_fault <= model_mmu_fault(mmu_vaddr);
      end else if (mmu_pending) begin
        mmu_pending <= 1'b0;
        mmu_reply_valid <= 1'b1;
        mmu_reply_paddr <= model_paddr(mmu_pending_vaddr);
        if (mmu_pending_fault) begin
          mmu_reply_exception.valid <= 1'b1;
          mmu_reply_exception.cause <= 64'd13;
          mmu_reply_exception.tval <= mmu_pending_vaddr;
        end
      end
    end
  end

  assign mmu_exception_valid = mmu_exception.valid;

  always @(posedge clk) begin
    if (rst_n && dut.translation_complete && !dut.fault_pending_q) begin
      assert (mmu_req)
        else $fatal(1, "MMU request withdrawn before response was sampled");
      $display("QBS_MMU_RESPONSE t=%0t combinational=%0b req=%0b valid=%0b exception=%0b vaddr=%h",
               $time, combinational_mmu, mmu_req, mmu_valid,
               mmu_exception_valid, mmu_vaddr);
    end
  end

  // Deterministic, two-request, same-ID AXI read slave. Responses are returned
  // in AR order. last_mode 1 emits an early last; last_mode 2 emits one late
  // drain beat for the current head request.
  axi_addr_t response_addr [2];
  logic [7:0] response_len [2];
  logic [8:0] response_beat;
  logic response_rd;
  logic response_wr;
  logic [1:0] response_count;
  integer response_error_beat;
  logic response_error_address_enable;
  axi_addr_t response_error_address;
  integer last_mode;
  logic hold_axi_responses;
  logic hold_axi_addresses;
  logic trace_ar_fault;
  integer ar_log_count;
  logic [63:0] ar_log_addr [0:63];
  logic [7:0] ar_log_len [0:63];

  assign axi_ar_ready = response_count < 2 && !hold_axi_addresses;
  assign axi_r_valid = response_count != 0 && !hold_axi_responses;

  always_comb begin
    axi_r = '0;
    for (int unsigned byte_lane = 0; byte_lane < BeatBytes; byte_lane++) begin
      axi_r.data[byte_lane*8 +: 8] =
          memory_byte(response_addr[response_rd] +
                      response_beat * BeatBytes + byte_lane);
    end
    axi_r.resp = integer'(response_beat) == response_error_beat &&
                 (!response_error_address_enable ||
                  response_addr[response_rd] == response_error_address) ?
                 RESP_SLVERR : RESP_OKAY;
    unique case (last_mode)
      1: axi_r.last = response_beat == 0;
      2: axi_r.last = response_beat ==
                      {1'b0, response_len[response_rd]} + 1'b1;
      default: axi_r.last = response_beat ==
                            {1'b0, response_len[response_rd]};
    endcase
  end

  // Check the entire AR bundle, including the cycle that finally accepts it.
  logic stalled_ar_q;
  axi_ar_t stalled_ar_payload_q;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      stalled_ar_q <= 1'b0;
      stalled_ar_payload_q <= '0;
    end else begin
      if (trace_ar_fault)
        $display("AR_FAULT t=%0t ar_v=%0b ar_r=%0b addr=%h r_v=%0b r_r=%0b resp=%0d last=%0b slots=%0d pending=%0b fault=%0b",
                 $time, axi_ar_valid, axi_ar_ready, axi_ar.addr,
                 axi_r_valid, axi_r_ready, axi_r.resp, axi_r.last,
                 dut.burst_fifo_count_q, dut.fault_pending_q, fault_valid);
      if (stalled_ar_q && (!axi_ar_valid || axi_ar !== stalled_ar_payload_q))
        $fatal(1, "AR changed or was withdrawn before handshake");
      stalled_ar_q <= axi_ar_valid && !axi_ar_ready;
      stalled_ar_payload_q <= axi_ar;
    end
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
      ar_log_count <= 0;
    end else begin
      if (axi_ar_valid && axi_ar_ready) begin
        if (ar_log_count >= 64)
          $fatal(1, "AR log capacity exceeded");
        response_addr[response_wr] <= axi_ar.addr;
        response_len[response_wr] <= axi_ar.len;
        response_wr <= response_wr + 1'b1;
        ar_log_addr[ar_log_count] <= axi_ar.addr;
        ar_log_len[ar_log_count] <= axi_ar.len;
        ar_log_count <= ar_log_count + 1;
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

  logic use_backpressure;
  always_ff @(negedge clk or negedge rst_n) begin
    if (!rst_n)
      data_ready <= 1'b1;
    else if (use_backpressure)
      data_ready <= ~data_ready;
    else
      data_ready <= 1'b1;
  end

  logic score_enable;
  logic [63:0] score_base;
  logic [15:0] score_expected_bytes;
  logic [15:0] score_received_bytes;
  tag_t score_tag;
  logic score_reset;

  always_ff @(posedge clk) begin : score_payload
    automatic int unsigned bytes_this_beat;
    automatic logic saw_hole;
    if (!rst_n || score_reset) begin
      score_received_bytes <= '0;
    end else if (!contract_active && data_valid && data_ready) begin
      if (!score_enable)
        $fatal(1, "unexpected QBS payload");
      if (data_tag != score_tag)
        $fatal(1, "payload tag got=%0d expected=%0d", data_tag, score_tag);
      if (data_offset != score_received_bytes)
        $fatal(1, "payload offset got=%0d expected=%0d",
               data_offset, score_received_bytes);

      bytes_this_beat = 0;
      saw_hole = 1'b0;
      for (int unsigned byte_lane = 0; byte_lane < BeatBytes; byte_lane++) begin
        if (data_strb[byte_lane]) begin
          if (saw_hole)
            $fatal(1, "payload strobe is not low-lane compacted");
          if (data[byte_lane*8 +: 8] !=
              memory_byte(score_base + score_received_bytes + byte_lane))
            $fatal(1, "payload byte mismatch offset=%0d",
                   score_received_bytes + byte_lane);
          bytes_this_beat++;
        end else begin
          saw_hole = 1'b1;
        end
      end
      if (bytes_this_beat == 0)
        $fatal(1, "empty QBS payload beat");
      score_received_bytes <= score_received_bytes + bytes_this_beat;
    end
  end

  task automatic clear_read_counters;
    @(negedge clk);
    counters_clear = 1'b1;
    @(negedge clk);
    counters_clear = 1'b0;
  endtask

  // The contract oracle uses explicit PA burst descriptors, independently of
  // model_paddr and the DUT planner. All stimulus/check tasks sample negedge;
  // this monitor samples handshakes and old registered state before posedge NBA.
  localparam int ContractLimit = 4;
  localparam int ContractCycleLimit = 256;
  typedef struct packed {
    logic [63:0] vaddr;
    logic [15:0] bytes;
    tag_t tag;
  } contract_range_t;
  typedef struct packed {
    logic [63:0] vaddr;
    logic [63:0] paddr;
    logic fault;
  } contract_translation_t;
  typedef struct packed {
    axi_ar_t ar;
    logic [63:0] vaddr;
    integer bytes;
    integer first_lane;
    integer offset;
    tag_t tag;
    logic range_last;
    logic [15:0] sequence_id;
  } contract_burst_t;

  contract_range_t contract_ranges [ContractLimit];
  contract_translation_t contract_translations [ContractLimit];
  contract_burst_t contract_bursts [ContractLimit];
  integer contract_range_expected, contract_translation_expected;
  integer contract_burst_expected, contract_payload_expected;
  integer contract_range_seen, contract_translation_seen, contract_pma_seen;
  integer contract_ar_seen, contract_r_seen, contract_r_index, contract_r_beat;
  integer contract_meta_bytes, contract_meta_beats, contract_payload_seen;
  integer contract_completion_seen, contract_fault_seen;
  integer contract_mmu_fault_seen, contract_axi_error_seen;
  integer contract_completion_hold, contract_fault_hold;
  integer contract_ar_hold, contract_data_hold;
  integer contract_cycle, contract_epoch;
  logic [31:0] contract_range_base, contract_translation_base, contract_ar_base;
  logic [31:0] contract_r_base, contract_payload_base;
  logic contract_reset, contract_expect_fault, contract_older_error;
  logic contract_error_drain, contract_mmu_waiting;
  logic contract_data_stalled, contract_completion_stalled, contract_fault_stalled;
  logic [63:0] contract_mmu_held_vaddr;
  tag_t contract_completion_tag;
  string contract_name;

  task automatic check_contract_fault(input bit older_error);
    exception_t expected_exception;
    expected_exception = '0;
    if (!older_error) begin
      expected_exception.valid = 1'b1;
      expected_exception.cause = 64'd13;
      expected_exception.tval = ContractVa1;
    end
    if (fault_kind !== (older_error ? QBS_READ_FAULT_AXI_RESPONSE :
                                    QBS_READ_FAULT_MMU) ||
        fault_tag !== (older_error ? 8'ha0 : 8'ha1) ||
        fault_vaddr !== (older_error ? ContractOldVa + 64'h110 : ContractVa1) ||
        fault_mmu_exception !== expected_exception)
      $fatal(1, "%s fault attribution kind=%0d tag=%h va=%h exception=%h older=%0b",
             contract_name, fault_kind, fault_tag, fault_vaddr,
             fault_mmu_exception, older_error);
  endtask

  always @(posedge clk) begin : contract_monitor
    contract_burst_t expected_burst;
    axi_data_t expected_data;
    logic [15:0] expected_strb;
    integer lane_start, take_bytes;
    logic expected_error;
    if (!rst_n || contract_reset) begin
      contract_cycle = 0;
      contract_range_seen = 0;
      contract_translation_seen = 0;
      contract_pma_seen = 0;
      contract_ar_seen = 0;
      contract_r_seen = 0;
      contract_r_index = 0;
      contract_r_beat = 0;
      contract_meta_bytes = 0;
      contract_meta_beats = 0;
      contract_payload_seen = 0;
      contract_completion_seen = 0;
      contract_fault_seen = 0;
      contract_mmu_fault_seen = 0;
      contract_axi_error_seen = 0;
      contract_completion_hold = 0;
      contract_fault_hold = 0;
      contract_ar_hold = 0;
      contract_data_hold = 0;
      contract_error_drain = 1'b0;
      contract_mmu_waiting = 1'b0;
      contract_mmu_held_vaddr = '0;
      contract_data_stalled = 1'b0;
      contract_completion_stalled = 1'b0;
      contract_fault_stalled = 1'b0;
    end else if (contract_active) begin
      if (contract_cycle >= ContractCycleLimit)
        $fatal(1, "%s exceeded bounded trace window", contract_name);
      $display("QBS_READ_TRACE case=%s epoch=%0d cycle=%0d t=%0t phase=pre_NBA plan=%0d cursor=%h remaining=%0d offset=%0d ptag=%h pseq=%0d next_seq=%0d rq=%0d/%0b/%0b bq=%0d/%0b/%0b slave_q=%0d pop=%0b/%0b pending=%0b drain=%0b ar_stalled=%0b fault_seq=%0d",
               contract_name, contract_epoch, contract_cycle, $time,
               dut.plan_state_q, dut.planner_cursor_q, dut.planner_remaining_q,
               dut.planner_offset_q, dut.planner_tag_q, dut.planner_sequence_q,
               dut.next_sequence_q, dut.range_fifo_count_q, dut.range_rd_q,
               dut.range_wr_q, dut.burst_fifo_count_q, dut.burst_rd_q,
               dut.burst_wr_q, response_count, dut.range_pop, dut.burst_pop,
               dut.fault_pending_q, dut.response_drain_q, dut.ar_stalled_q,
               dut.fault_sequence_q);
      $display("QBS_READ_IO epoch=%0d cycle=%0d range_v/r/f=%b%b%b va=%h bytes=%0d tag=%h mmu_req/valid/exc=%b%b%b va=%h pa=%h pma=%b/%h/%0d ar_v/r/f=%b%b%b addr=%h len=%0d r_v/r/f=%b%b%b resp=%0d last=%b metadata_fire=%b head_tag=%h seq=%0d left=%0d/%0d head_va=%h head_off=%0d",
               contract_epoch, contract_cycle, range_valid, range_ready,
               range_valid && range_ready, range_vaddr, range_bytes, range_tag,
               mmu_req, mmu_valid, mmu_exception_valid, mmu_vaddr, mmu_paddr,
               physical_check_valid, physical_check_addr, physical_check_bytes,
               axi_ar_valid, axi_ar_ready, axi_ar_valid && axi_ar_ready,
               axi_ar.addr, axi_ar.len, axi_r_valid, axi_r_ready,
               axi_r_valid && axi_r_ready, axi_r.resp, axi_r.last,
               dut.response_metadata_fire, dut.response_head.tag,
               dut.response_head.subreq_seq, dut.response_head.bytes_left,
               dut.response_head.beats_left, dut.response_head.cursor_vaddr,
               dut.response_head.range_offset);
      $display("QBS_READ_OUT epoch=%0d cycle=%0d data_v/r/f=%b%b%b tag=%h off=%0d strb=%h data=%h comp_v/r/f=%b%b%b tag=%h fault_v/r/f=%b%b%b kind=%0d tag=%h va=%h exc=%h planner_fault=%b response_fault=%b counters=range:%0d,mmu:%0d,ar:%0d,r:%0d,bytes:%0d,max:%0d,full:%0d",
               contract_epoch, contract_cycle, data_valid, data_ready,
               data_valid && data_ready, data_tag, data_offset, data_strb, data,
               completion_valid, completion_ready, completion_valid && completion_ready,
               completion_tag, fault_valid, fault_ready, fault_valid && fault_ready,
               fault_kind, fault_tag, fault_vaddr, fault_mmu_exception,
               dut.planner_fault_event, dut.response_fault_event,
               range_count, translation_count, ar_count, r_beat_count,
               payload_byte_count, outstanding_max, outstanding_full_cycles);
      contract_cycle++;

      // Counters below denote accepted events, not asserted VALID levels.
      if (range_count !== contract_range_base + 32'(contract_range_seen) ||
          translation_count !== contract_translation_base + 32'(contract_translation_seen) ||
          ar_count !== contract_ar_base + 32'(contract_ar_seen) ||
          r_beat_count !== contract_r_base + 32'(contract_r_seen) ||
          payload_byte_count !== contract_payload_base + 32'(contract_payload_seen))
        $fatal(1, "%s DUT counters differ from interface handshakes", contract_name);
      if (integer'(response_count) != contract_ar_seen - contract_r_index ||
          dut.burst_fifo_count_q !== response_count ||
          dut.response_drain_q !== contract_error_drain)
        $fatal(1, "%s outstanding/drain state mismatch", contract_name);
      if ((contract_data_stalled && !data_valid) ||
          (contract_completion_stalled && !completion_valid) ||
          (contract_fault_stalled && !fault_valid))
        $fatal(1, "%s withdrew a stalled output", contract_name);

      if (dut.fault_pending_q) begin
        if (!contract_expect_fault || contract_mmu_fault_seen != 1 ||
            range_ready || mmu_req || axi_ar_valid || data_valid ||
            completion_valid || dut.range_fifo_count_q != 0)
          $fatal(1, "%s advanced/flushed work incorrectly during fault drain", contract_name);
        check_contract_fault(contract_axi_error_seen != 0);
        if (response_count != 0 && fault_valid)
          $fatal(1, "%s fault escaped before all accepted RLASTs", contract_name);
      end
      if (range_valid && range_ready) begin
        if (contract_range_seen >= contract_range_expected)
          $fatal(1, "%s extra range acceptance", contract_name);
        if ({range_vaddr, range_bytes, range_tag} !== contract_ranges[contract_range_seen] ||
            range_cache !== ContractCache || range_prot !== ContractProt)
          $fatal(1, "%s accepted range differs from stimulus contract", contract_name);
        contract_range_seen++;
      end

      if (contract_mmu_waiting && (!mmu_req || mmu_vaddr !== contract_mmu_held_vaddr))
        $fatal(1, "%s changed/withdrew MMU request before response", contract_name);
      if (mmu_req) begin
        if (contract_translation_seen >= contract_translation_expected)
          $fatal(1, "%s extra MMU request (possibly flushed work)", contract_name);
        if (mmu_vaddr !== contract_translations[contract_translation_seen].vaddr ||
            mmu_is_store !== 1'b0)
          $fatal(1, "%s wrong translation cursor/type", contract_name);
        contract_mmu_held_vaddr = mmu_vaddr;
      end
      contract_mmu_waiting = mmu_req && !(mmu_valid || mmu_exception_valid);
      if (mmu_valid || mmu_exception_valid) begin
        if (!mmu_req)
          $fatal(1, "%s unsolicited MMU response", contract_name);
        if (contract_translations[contract_translation_seen].fault) begin
          if (mmu_exception_valid !== 1'b1 || mmu_exception.cause !== 64'd13 ||
              mmu_exception.tval !== ContractVa1 || physical_check_valid ||
              axi_ar_valid || fault_valid || contract_range_seen != 3 ||
              contract_ar_seen != 2 || contract_r_seen != 0 ||
              response_count != 2 || dut.range_fifo_count_q != 1)
            $fatal(1, "%s page-two fault did not overlap two older ARs and queued work",
                   contract_name);
          contract_mmu_fault_seen++;
        end else if (mmu_valid !== 1'b1 || mmu_exception_valid !== 1'b0 ||
                     mmu_paddr !== contract_translations[contract_translation_seen].paddr ||
                     physical_check_valid !== 1'b1) begin
          $fatal(1, "%s successful translation/PMA handshake mismatch", contract_name);
        end
        contract_translation_seen++;
      end
      if (physical_check_valid) begin
        if (contract_pma_seen >= contract_burst_expected)
          $fatal(1, "%s extra physical check", contract_name);
        expected_burst = contract_bursts[contract_pma_seen];
        if (!mmu_req || !mmu_valid || mmu_exception_valid ||
            physical_check_addr !== expected_burst.ar.addr ||
            physical_check_bytes !== 13'((integer'(expected_burst.ar.len) + 1) * BeatBytes))
          $fatal(1, "%s physical check did not cover exact translated AXI span", contract_name);
        contract_pma_seen++;
      end

      if (axi_ar_valid) begin
        if (contract_ar_seen >= contract_burst_expected)
          $fatal(1, "%s extra AR (faulting page or flushed range)", contract_name);
        expected_burst = contract_bursts[contract_ar_seen];
        if (axi_ar !== expected_burst.ar ||
            dut.ar_tag_q !== expected_burst.tag ||
            dut.ar_range_offset_q !== 16'(expected_burst.offset) ||
            dut.ar_sequence_q !== expected_burst.sequence_id)
          $fatal(1, "%s AR bundle/tag/offset/sequence mismatch index=%0d addr=%h expected=%h",
                 contract_name, contract_ar_seen, axi_ar.addr, expected_burst.ar.addr);
        if (axi_ar_ready)
          contract_ar_seen++;
        else
          contract_ar_hold++;
      end

      if (data_valid && (contract_expect_fault || !axi_r_valid))
        $fatal(1, "%s unexpected payload valid", contract_name);
      if (axi_r_valid) begin
        if (contract_r_index >= contract_ar_seen)
          $fatal(1, "%s R without accepted AR", contract_name);
        expected_burst = contract_bursts[contract_r_index];
        expected_error = contract_older_error && contract_r_index == 0 && contract_r_beat == 1;
        expected_data = '0;
        for (int lane = 0; lane < BeatBytes; lane++)
          expected_data[lane*8 +: 8] = memory_byte(expected_burst.ar.addr +
                                                 contract_r_beat * BeatBytes + lane);
        if (axi_r.id !== '0 || axi_r.user !== '0 || axi_r.data !== expected_data ||
            axi_r.last !== (contract_r_beat == integer'(expected_burst.ar.len)) ||
            axi_r.resp !== (expected_error ? RESP_SLVERR : RESP_OKAY))
          $fatal(1, "%s AXI slave response differs from independent burst oracle", contract_name);
        if (dut.response_head.tag !== expected_burst.tag ||
            dut.response_head.subreq_seq !== expected_burst.sequence_id ||
            dut.response_head.bytes_left !== 16'(expected_burst.bytes - contract_meta_bytes) ||
            dut.response_head.beats_left !== 9'(integer'(expected_burst.ar.len) + 1 - contract_meta_beats) ||
            dut.response_head.cursor_vaddr !== expected_burst.vaddr + 64'(contract_meta_bytes) ||
            dut.response_head.range_offset !== 16'(expected_burst.offset + contract_meta_bytes) ||
            dut.response_head.range_last !== expected_burst.range_last ||
            dut.response_head.first_lane !== 4'(contract_meta_beats == 0 ? expected_burst.first_lane : 0))
          $fatal(1, "%s response metadata did not advance with accepted drain beats", contract_name);
        if (dut.response_fault_event !== (expected_error && !contract_error_drain) ||
            dut.response_metadata_fire !== (axi_r_ready && !expected_error && !contract_error_drain))
          $fatal(1, "%s fabricated fault or missed response metadata advancement", contract_name);
        lane_start = contract_meta_beats == 0 ? expected_burst.first_lane : 0;
        take_bytes = expected_burst.bytes - contract_meta_bytes;
        if (take_bytes > BeatBytes - lane_start)
          take_bytes = BeatBytes - lane_start;
        if (contract_expect_fault) begin
          if (!dut.fault_pending_q || !axi_r_ready || data_valid || completion_valid)
            $fatal(1, "%s fault drain published payload/completion or stalled", contract_name);
        end else begin
          expected_strb = 16'((1 << take_bytes) - 1);
          expected_data = '0;
          for (int lane = 0; lane < take_bytes; lane++)
            expected_data[lane*8 +: 8] = memory_byte(expected_burst.ar.addr +
                contract_r_beat * BeatBytes + lane_start + lane);
          if (data_valid !== 1'b1 || axi_r_ready !== data_ready ||
              data_tag !== expected_burst.tag || data !== expected_data ||
              data_strb !== expected_strb ||
              data_offset !== 16'(expected_burst.offset + contract_meta_bytes) ||
              data_offset !== 16'(contract_payload_seen))
            $fatal(1, "%s payload bytes/strobe/tag/offset/handshake mismatch", contract_name);
          if (data_ready) begin
            contract_payload_seen += take_bytes;
            if (contract_payload_seen > contract_payload_expected)
              $fatal(1, "%s excess payload", contract_name);
          end else
            contract_data_hold++;
        end
        if (axi_r_ready) begin
          contract_r_seen++;
          if (!expected_error && !contract_error_drain) begin
            contract_meta_bytes += take_bytes;
            contract_meta_beats++;
          end
          if (expected_error) begin
            contract_axi_error_seen++;
            contract_error_drain = 1'b1;
          end
          if (axi_r.last) begin
            contract_r_index++;
            contract_r_beat = 0;
            contract_meta_bytes = 0;
            contract_meta_beats = 0;
            contract_error_drain = 1'b0;
          end else
            contract_r_beat++;
        end
      end
      if (completion_valid) begin
        if (contract_expect_fault || contract_completion_seen != 0 ||
            completion_tag !== contract_completion_tag ||
            contract_payload_seen != contract_payload_expected ||
            contract_r_index != contract_burst_expected)
          $fatal(1, "%s unexpected/early/duplicate completion", contract_name);
        if (completion_ready)
          contract_completion_seen++;
        else
          contract_completion_hold++;
      end
      if (fault_valid) begin
        if (!contract_expect_fault || contract_fault_seen != 0 ||
            response_count != 0 || axi_ar_valid || axi_r_valid ||
            data_valid || completion_valid || contract_r_index != contract_burst_expected ||
            contract_axi_error_seen != integer'(contract_older_error))
          $fatal(1, "%s unexpected/early/duplicate fault", contract_name);
        check_contract_fault(contract_older_error);
        if (fault_ready)
          contract_fault_seen++;
        else
          contract_fault_hold++;
      end
      contract_data_stalled = data_valid && !data_ready;
      contract_completion_stalled = completion_valid && !completion_ready;
      contract_fault_stalled = fault_valid && !fault_ready;
    end
  end

  task automatic prepare_contract(input string name,
                                  input bit expect_fault,
                                  input bit older_error,
                                  input bit clear_counters);
    @(negedge clk);
    if (contract_active || busy || response_count != 0 || range_valid ||
        mmu_req || mmu_pending || mmu_valid || mmu_exception_valid ||
        data_valid || completion_valid || fault_valid || axi_ar_valid || axi_r_valid)
      $fatal(1, "%s started without a quiescent reader/slave", name);
    contract_name = name;
    contract_range_expected = 0;
    contract_translation_expected = 0;
    contract_burst_expected = 0;
    contract_payload_expected = 0;
    contract_completion_tag = '0;
    contract_expect_fault = expect_fault;
    contract_older_error = older_error;
    mapped_mmu = 1'b1;
    second_page_fault = expect_fault;
    translation_enable = 1'b1;
    inject_mmu_fault = 1'b0;
    physical_range_allowed = 1'b1;
    core_st_pending = 1'b0;
    range_cache = ContractCache;
    range_prot = ContractProt;
    score_enable = 1'b0;
    completion_ready = 1'b0;
    fault_ready = 1'b0;
    hold_axi_responses = 1'b1;
    hold_axi_addresses = 1'b0;
    use_backpressure = !expect_fault;
    last_mode = 0;
    response_error_beat = older_error ? 1 : -1;
    response_error_address_enable = older_error;
    response_error_address = ContractOldPa + 64'h100;
    if (clear_counters)
      clear_read_counters();
    // Reuse cases retain DUT counters and sequence allocation across the fault.
    contract_range_base = range_count;
    contract_translation_base = translation_count;
    contract_ar_base = ar_count;
    contract_r_base = r_beat_count;
    contract_payload_base = payload_byte_count;
    contract_reset = 1'b1;
    @(negedge clk);
    contract_reset = 1'b0;
  endtask

  task automatic expect_contract_range(input logic [63:0] vaddr,
                                       input integer bytes, input tag_t tag);
    if (contract_range_expected >= ContractLimit)
      $fatal(1, "contract range table overflow");
    contract_ranges[contract_range_expected] = '{vaddr, 16'(bytes), tag};
    contract_range_expected++;
  endtask

  task automatic expect_contract_translation(input logic [63:0] vaddr,
                                             input logic [63:0] paddr,
                                             input bit fault);
    if (contract_translation_expected >= ContractLimit)
      $fatal(1, "contract translation table overflow");
    contract_translations[contract_translation_expected] = '{vaddr, paddr, fault};
    contract_translation_expected++;
  endtask

  task automatic expect_contract_burst(input logic [63:0] paddr,
                                       input integer len,
                                       input logic [63:0] vaddr,
                                       input integer bytes,
                                       input integer first_lane,
                                       input integer offset,
                                       input tag_t tag,
                                       input bit range_last,
                                       input logic [15:0] sequence_id);
    if (contract_burst_expected >= ContractLimit)
      $fatal(1, "contract burst table overflow");
    contract_bursts[contract_burst_expected] = '{
      ar: '{addr: paddr, len: axi_pkg::len_t'(len),
            size: axi_pkg::size_t'(4), burst: BURST_INCR,
            cache: ContractCache, prot: ContractProt, default: '0},
      vaddr: vaddr, bytes: bytes, first_lane: first_lane, offset: offset,
      tag: tag, range_last: range_last, sequence_id: sequence_id
    };
    contract_burst_expected++;
  endtask

  task automatic start_contract;
    contract_epoch++;
    contract_active = 1'b1;
    $display("QBS_READ_BEGIN case=%s epoch=%0d mmu=%s trace_limit=%0d phase=posedge_pre_NBA",
             contract_name, contract_epoch,
             combinational_mmu ? "combinational" : "delayed", ContractCycleLimit);
  endtask

  task automatic send_contract_range(input logic [63:0] base,
                                     input integer bytes, input tag_t tag);
    integer before_fire, timeout_cycles;
    @(negedge clk);
    before_fire = contract_range_seen;
    range_vaddr = base;
    range_bytes = 16'(bytes);
    range_tag = tag;
    range_valid = 1'b1;
    timeout_cycles = 0;
    // VALID and payload remain asserted until the posedge monitor records FIRE.
    do begin
      @(negedge clk);
      timeout_cycles++;
    end while (contract_range_seen == before_fire && timeout_cycles < 100);
    range_valid = 1'b0;
    if (contract_range_seen != before_fire + 1)
      $fatal(1, "%s range did not handshake exactly once", contract_name);
  endtask

  task automatic wait_contract_ars(input integer count);
    integer timeout_cycles;
    timeout_cycles = 0;
    while (contract_ar_seen < count && timeout_cycles < 100) begin
      @(negedge clk);
      timeout_cycles++;
    end
    if (contract_ar_seen != count)
      $fatal(1, "%s expected %0d accepted ARs", contract_name, count);
  endtask

  task automatic retire_contract;
    integer timeout_cycles;
    timeout_cycles = 0;
    while (!(contract_expect_fault ? fault_valid : completion_valid) &&
           timeout_cycles < 100) begin
      @(negedge clk);
      timeout_cycles++;
    end
    if (!(contract_expect_fault ? fault_valid : completion_valid))
      $fatal(1, "%s terminal output timed out", contract_name);
    repeat (4) @(negedge clk);
    if (contract_expect_fault)
      fault_ready = 1'b1;
    else
      completion_ready = 1'b1;
    @(negedge clk);
    fault_ready = 1'b0;
    completion_ready = 1'b0;
    if (contract_completion_seen != (contract_expect_fault ? 0 : 1) ||
        contract_fault_seen != (contract_expect_fault ? 1 : 0))
      $fatal(1, "%s terminal output did not handshake exactly once", contract_name);
    // Keep the oracle live after retirement to catch duplicates and stale work.
    repeat (4) @(negedge clk);
  endtask

  task automatic finish_contract(input bit require_ar_stall,
                                 input bit require_two_slots);
    integer expected_r_beats;
    expected_r_beats = 0;
    for (int i = 0; i < contract_burst_expected; i++)
      expected_r_beats += integer'(contract_bursts[i].ar.len) + 1;
    if (contract_range_seen != contract_range_expected ||
        contract_translation_seen != contract_translation_expected ||
        contract_pma_seen != contract_burst_expected ||
        contract_ar_seen != contract_burst_expected ||
        contract_r_index != contract_burst_expected || contract_r_seen != expected_r_beats ||
        contract_payload_seen != contract_payload_expected ||
        contract_mmu_fault_seen != integer'(contract_expect_fault) ||
        contract_axi_error_seen != integer'(contract_older_error) ||
        (contract_expect_fault ? contract_fault_hold < 4 : contract_completion_hold < 4) ||
        (require_ar_stall && contract_ar_hold < 3) ||
        (!contract_expect_fault && (contract_data_hold == 0 || r_backpressure_cycles == 0)) ||
        (require_two_slots && (outstanding_max != 2 || outstanding_full_cycles == 0)) ||
        busy || !range_ready || response_count != 0 || dut.range_fifo_count_q != 0 ||
        dut.burst_fifo_count_q != 0 || dut.ar_stalled_q ||
        mmu_pending || mmu_req || mmu_valid || mmu_exception_valid ||
        axi_ar_valid || axi_r_valid || data_valid || completion_valid || fault_valid)
      $fatal(1, "%s final contract accounting/quiescence/coverage mismatch", contract_name);
    $display("[QBS_READ_SUBCASE] %s PASS", contract_name);
    contract_active = 1'b0;
  endtask

  task automatic nonidentity_pages_contract;
    integer timeout_cycles;
    prepare_contract("NONIDENTITY_NONCONTIGUOUS_PAGES", 1'b0, 1'b0, 1'b1);
    // 61 bytes on page zero, then 45 on a nonadjacent physical page.
    expect_contract_range(ContractVa0 + 64'hfc3, 106, 8'h91);
    expect_contract_translation(ContractVa0 + 64'hfc3, ContractPa0 + 64'hfc3, 1'b0);
    expect_contract_translation(ContractVa1, ContractPa1, 1'b0);
    expect_contract_burst(ContractPa0 + 64'hfc0, 3, ContractVa0 + 64'hfc3,
                          61, 3, 0, 8'h91, 1'b0, 16'd0);
    expect_contract_burst(ContractPa1, 2, ContractVa1,
                          45, 0, 61, 8'h91, 1'b1, 16'd1);
    contract_payload_expected = 106;
    contract_completion_tag = 8'h91;
    hold_axi_addresses = 1'b1;
    start_contract();
    send_contract_range(ContractVa0 + 64'hfc3, 106, 8'h91);
    timeout_cycles = 0;
    while (!axi_ar_valid && timeout_cycles < 100) begin
      @(negedge clk);
      timeout_cycles++;
    end
    if (!axi_ar_valid)
      $fatal(1, "%s never offered its first AR", contract_name);
    repeat (3) @(negedge clk);
    hold_axi_addresses = 1'b0;
    wait_contract_ars(2);
    repeat (2) @(negedge clk);
    if (response_count != 2 || contract_r_seen != 0)
      $fatal(1, "%s did not plan both physical pages before R drain", contract_name);
    hold_axi_responses = 1'b0;
    retire_contract();
    finish_contract(1'b1, 1'b1);
  endtask

  task automatic post_fault_reuse_contract(input bit older_error);
    tag_t reused_tag;
    reused_tag = older_error ? 8'ha0 : 8'ha1;
    prepare_contract(older_error ? "POST_OLDER_AXI_FAULT_REUSE" : "POST_MMU_FAULT_REUSE",
                     1'b0, 1'b0, 1'b0);
    // Retry the formerly faulting VA page with the failed tag, no reset/clear.
    expect_contract_range(ContractVa1 + 64'h23, 21, reused_tag);
    expect_contract_translation(ContractVa1 + 64'h23, ContractPa1 + 64'h23, 1'b0);
    expect_contract_burst(ContractPa1 + 64'h20, 1, ContractVa1 + 64'h23,
                          21, 3, 0, reused_tag, 1'b1, 16'd3);
    contract_payload_expected = 21;
    contract_completion_tag = reused_tag;
    start_contract();
    send_contract_range(ContractVa1 + 64'h23, 21, reused_tag);
    wait_contract_ars(1);
    hold_axi_responses = 1'b0;
    retire_contract();
    finish_contract(1'b0, 1'b0);
  endtask

  task automatic second_page_fault_contract(input bit older_error);
    integer timeout_cycles;
    prepare_contract(older_error ? "SECOND_PAGE_MMU_FAULT_OLDER_AXI_ERROR" :
                                  "SECOND_PAGE_MMU_FAULT_DRAIN",
                     1'b1, older_error, 1'b1);
    expect_contract_range(ContractOldVa + 64'h100, 64, 8'ha0);
    expect_contract_range(ContractVa0 + 64'hfc3, 106, 8'ha1);
    expect_contract_range(ContractQueuedVa + 64'h200, 16, 8'ha2);
    expect_contract_translation(ContractOldVa + 64'h100, ContractOldPa + 64'h100, 1'b0);
    expect_contract_translation(ContractVa0 + 64'hfc3, ContractPa0 + 64'hfc3, 1'b0);
    expect_contract_translation(ContractVa1, ContractPa1, 1'b1);
    expect_contract_burst(ContractOldPa + 64'h100, 3, ContractOldVa + 64'h100,
                          64, 0, 0, 8'ha0, 1'b1, 16'd0);
    expect_contract_burst(ContractPa0 + 64'hfc0, 3, ContractVa0 + 64'hfc3,
                          61, 3, 0, 8'ha1, 1'b0, 16'd1);
    start_contract();
    send_contract_range(ContractOldVa + 64'h100, 64, 8'ha0);
    wait_contract_ars(1);
    send_contract_range(ContractVa0 + 64'hfc3, 106, 8'ha1);
    send_contract_range(ContractQueuedVa + 64'h200, 16, 8'ha2);
    timeout_cycles = 0;
    while (contract_mmu_fault_seen == 0 && timeout_cycles < 100) begin
      @(negedge clk);
      timeout_cycles++;
    end
    if (contract_mmu_fault_seen != 1 || !dut.fault_pending_q || response_count != 2)
      $fatal(1, "%s did not latch second-page fault with older reads outstanding", contract_name);
    repeat (3) begin
      @(negedge clk);
      if (fault_valid || range_ready || data_valid || completion_valid ||
          contract_r_seen != 0 || response_count != 2)
        $fatal(1, "%s fault/work escaped while older R was held", contract_name);
    end
    hold_axi_responses = 1'b0;
    retire_contract();
    finish_contract(1'b0, 1'b1);
    post_fault_reuse_contract(older_error);
  endtask

  task automatic begin_score(input logic [63:0] base,
                             input integer bytes,
                             input integer tag);
    @(negedge clk);
    score_enable = 1'b1;
    score_base = base;
    score_expected_bytes = bytes[15:0];
    score_tag = tag[7:0];
    score_reset = 1'b1;
    @(negedge clk);
    score_reset = 1'b0;
  endtask

  task automatic send_range(input logic [63:0] base,
                            input integer bytes,
                            input integer tag);
    integer timeout;
    timeout = 0;
    while (!range_ready && timeout < 1000) begin
      @(posedge clk);
      timeout++;
    end
    if (!range_ready)
      $fatal(1, "timeout waiting for range_ready");
    @(negedge clk);
    range_vaddr = base;
    range_bytes = bytes[15:0];
    range_tag = tag[7:0];
    range_valid = 1'b1;
    @(negedge clk);
    range_valid = 1'b0;
  endtask

  task automatic wait_completion(input integer tag,
                                 input integer expected_bytes);
    integer timeout;
    timeout = 0;
    while (!completion_valid && timeout < 20000) begin
      @(posedge clk);
      timeout++;
    end
    if (!completion_valid)
      $fatal(1, "timeout waiting for QBS completion");
    if (completion_tag != tag[7:0])
      $fatal(1, "completion tag got=%0d expected=%0d", completion_tag, tag);
    if (score_received_bytes != expected_bytes)
      $fatal(1, "payload bytes got=%0d expected=%0d",
             score_received_bytes, expected_bytes);
    @(negedge clk);
    completion_ready = 1'b1;
    @(negedge clk);
    completion_ready = 1'b0;
    score_enable = 1'b0;
  endtask

  task automatic wait_fault(input qbs_read_fault_e expected_kind,
                            input integer tag,
                            input logic [63:0] expected_vaddr);
    integer timeout;
    timeout = 0;
    while (!fault_valid && timeout < 20000) begin
      @(posedge clk);
      timeout++;
    end
    if (!fault_valid)
      $fatal(1, "timeout waiting for QBS fault");
    if (fault_kind != expected_kind || fault_tag != tag[7:0] ||
        fault_vaddr != expected_vaddr)
      $fatal(1, "fault mismatch kind=%0d tag=%0d vaddr=%h",
             fault_kind, fault_tag, fault_vaddr);
    @(negedge clk);
    fault_ready = 1'b1;
    @(negedge clk);
    fault_ready = 1'b0;
    score_enable = 1'b0;
  endtask

  task automatic stalled_ar_fault(input integer response_mode,
                                  input integer release_delay);
    integer ar_base;
    integer old_bytes;
    integer old_beats;
    integer timeout_cycles;
    qbs_read_fault_e expected_kind;
    old_bytes = response_mode == 2 ? 16 : 64;
    old_beats = response_mode == 0 ? 4 : response_mode == 1 ? 1 : 2;
    expected_kind = response_mode == 0 ? QBS_READ_FAULT_AXI_RESPONSE :
                                         QBS_READ_FAULT_AXI_PROTOCOL;
    clear_read_counters();
    hold_axi_responses = 1'b1;
    hold_axi_addresses = 1'b0;
    ar_base = ar_log_count;
    send_range(64'hf100, old_bytes, 31);
    timeout_cycles = 0;
    while (ar_log_count != ar_base + 1 && timeout_cycles < 100) begin
      @(negedge clk);
      timeout_cycles++;
    end
    if (ar_log_count != ar_base + 1)
      $fatal(1, "older AR was not accepted");
    hold_axi_addresses = 1'b1;
    send_range(64'hf200, 16, 32);
    send_range(64'hf300, 16, 33);
    timeout_cycles = 0;
    while (!axi_ar_valid && timeout_cycles < 100) begin
      @(negedge clk);
      timeout_cycles++;
    end
    if (!axi_ar_valid || axi_ar.addr != 64'hf200)
      $fatal(1, "younger AR did not reach the stalled interface");
    trace_ar_fault = 1'b1;
    repeat (2) @(negedge clk);
    response_error_beat = response_mode == 0 ? 0 : -1;
    last_mode = response_mode;
    hold_axi_responses = 1'b0;
    // Check both error + AR acceptance in one cycle, and an AR that remains
    // stalled even after the older response has completely drained.
    if (release_delay == 0)
      hold_axi_addresses = 1'b0;
    repeat (release_delay) begin
      @(negedge clk);
      if (fault_valid || completion_valid || data_valid || range_ready)
        $fatal(1, "fault escaped or work advanced before stalled AR drain");
    end
    hold_axi_addresses = 1'b0;
    timeout_cycles = 0;
    while (ar_log_count != ar_base + 2 && timeout_cycles < 100) begin
      @(negedge clk);
      timeout_cycles++;
    end
    if (ar_log_count != ar_base + 2)
      $fatal(1, "stalled younger AR was lost");
    timeout_cycles = 0;
    while (r_beat_count < old_beats && timeout_cycles < 100) begin
      @(negedge clk);
      timeout_cycles++;
    end
    if (r_beat_count < old_beats)
      $fatal(1, "older malformed response did not drain");
    // Only the older response is malformed; the accepted younger AR drains
    // normally without publishing data or completion for the failed command.
    response_error_beat = -1;
    last_mode = 0;
    wait_fault(expected_kind, 31, 64'hf100);
    if (ar_log_count != ar_base + 2 || ar_log_addr[ar_base+1] != 64'hf200 ||
        ar_count != 2 || r_beat_count != old_beats + 1 ||
        payload_byte_count != 0 || completion_valid || busy || response_count != 0)
      $fatal(1, "stalled-AR fault drain/accounting mismatch");
    trace_ar_fault = 1'b0;
    begin_score(64'hf400, 32, 34);
    send_range(64'hf400, 32, 34);
    wait_completion(34, 32);
    $display("QBS stalled-AR fault PASS mode=%0d delay=%0d", response_mode, release_delay);
  endtask

  initial begin : run_tests
    integer ar_base;

    clk = 1'b0;
    rst_n = 1'b0;
    range_valid = 1'b0;
    range_vaddr = '0;
    range_bytes = '0;
    range_tag = '0;
    range_cache = CACHE_MODIFIABLE;
    range_prot = '0;
    completion_ready = 1'b0;
    fault_ready = 1'b0;
    core_st_pending = 1'b0;
    translation_enable = 1'b0;
    inject_mmu_fault = 1'b0;
    mapped_mmu = 1'b0;
    second_page_fault = 1'b0;
    contract_active = 1'b0;
    contract_reset = 1'b0;
    contract_epoch = 0;
    combinational_mmu = $test$plusargs("COMBINATIONAL_MMU");
    physical_range_allowed = 1'b1;
    counters_clear = 1'b0;
    response_error_beat = -1;
    response_error_address_enable = 1'b0;
    response_error_address = '0;
    last_mode = 0;
    hold_axi_responses = 1'b0;
    hold_axi_addresses = 1'b0;
    trace_ar_fault = 1'b0;
    use_backpressure = 1'b0;
    score_enable = 1'b0;
    score_base = '0;
    score_expected_bytes = '0;
    score_tag = '0;
    score_reset = 1'b0;

    repeat (4) @(posedge clk);
    rst_n = 1'b1;
    repeat (2) @(posedge clk);

    // Aligned, untranslated single beat.
    clear_read_counters();
    ar_base = ar_log_count;
    begin_score(64'h1000, 16, 1);
    send_range(64'h1000, 16, 1);
    wait_completion(1, 16);
    if (ar_log_count != ar_base + 1 || ar_log_addr[ar_base] != 64'h1000 ||
        ar_log_len[ar_base] != 0 || range_count != 1 || ar_count != 1 ||
        r_beat_count != 1 || payload_byte_count != 16 ||
        translation_count != 0)
      $fatal(1, "aligned range accounting mismatch");

    // Unaligned range, translated, with downstream backpressure.
    clear_read_counters();
    translation_enable = 1'b1;
    use_backpressure = 1'b1;
    ar_base = ar_log_count;
    begin_score(64'h1203, 210, 2);
    send_range(64'h1203, 210, 2);
    wait_completion(2, 210);
    use_backpressure = 1'b0;
    if (ar_log_count != ar_base + 1 || ar_log_addr[ar_base] != 64'h1200 ||
        ar_log_len[ar_base] != 13 || translation_count != 1 ||
        r_beat_count != 14 || payload_byte_count != 210 ||
        r_backpressure_cycles == 0)
      $fatal(1, "unaligned translated range mismatch");

    // A logical range crossing 4 KiB must become two legal bursts and two
    // translations, without exposing alignment padding.
    clear_read_counters();
    ar_base = ar_log_count;
    begin_score(64'h1ff3, 40, 3);
    send_range(64'h1ff3, 40, 3);
    wait_completion(3, 40);
    if (ar_log_count != ar_base + 2 ||
        ar_log_addr[ar_base] != 64'h1ff0 || ar_log_len[ar_base] != 0 ||
        ar_log_addr[ar_base+1] != 64'h2000 || ar_log_len[ar_base+1] != 1 ||
        translation_count != 2 || ar_count != 2 || r_beat_count != 3 ||
        payload_byte_count != 40)
      $fatal(1, "4-KiB split mismatch");

    // A long page-tail range must issue its second same-ID burst before the
    // first response drains, while preserving one continuous logical payload.
    clear_read_counters();
    ar_base = ar_log_count;
    begin_score(64'ha003, 4096, 12);
    send_range(64'ha003, 4096, 12);
    wait_completion(12, 4096);
    if (ar_log_count != ar_base + 2 || outstanding_max != 2 ||
        outstanding_full_cycles == 0 || payload_byte_count != 4096)
      $fatal(1, "two-outstanding ordered read mismatch");

    // A full completion register must backpressure exactly the final beat of
    // the next range. Consuming the old completion and accepting the new final
    // beat in one cycle must refill the register without duplicating payload.
    clear_read_counters();
    ar_base = ar_log_count;
    begin_score(64'hab00, 16, 13);
    send_range(64'hab00, 16, 13);
    send_range(64'hac00, 16, 14);
    while (!completion_valid) @(posedge clk);
    if (completion_tag != 8'd13 || score_received_bytes != 16)
      $fatal(1, "first held completion mismatch");
    begin_score(64'hac00, 16, 14);
    repeat (4) begin
      @(posedge clk);
      if (!completion_valid || completion_tag != 8'd13 || data_valid)
        $fatal(1, "completion backpressure did not hold the next final beat");
    end
    @(negedge clk);
    completion_ready = 1'b1;
    @(negedge clk);
    completion_ready = 1'b0;
    wait_completion(14, 16);
    if (ar_log_count != ar_base + 2 || payload_byte_count != 32 ||
        r_beat_count != 2 || r_backpressure_cycles == 0)
      $fatal(1, "completion backpressure accounting mismatch");

    // Older scalar stores gate the first translation and AR request.
    clear_read_counters();
    core_st_pending = 1'b1;
    ar_base = ar_log_count;
    begin_score(64'h3000, 32, 4);
    send_range(64'h3000, 32, 4);
    repeat (5) @(posedge clk);
    if (ar_log_count != ar_base || mmu_req || store_wait_cycles == 0)
      $fatal(1, "core-store ordering gate was bypassed");
    core_st_pending = 1'b0;
    wait_completion(4, 32);

    // Translation faults must not issue AXI or expose data.
    clear_read_counters();
    inject_mmu_fault = 1'b1;
    ar_base = ar_log_count;
    begin_score(64'h4100, 32, 5);
    send_range(64'h4100, 32, 5);
    wait_fault(QBS_READ_FAULT_MMU, 5, 64'h4100);
    inject_mmu_fault = 1'b0;
    if (ar_log_count != ar_base || payload_byte_count != 0 ||
        translation_count != 1 || !fault_mmu_exception.valid ||
        fault_mmu_exception.cause != 13 ||
        fault_mmu_exception.tval != 64'h4100)
      $fatal(1, "MMU fault attribution mismatch");

    // AXI response error: preserve earlier bytes, discard the failing beat,
    // and drain the remaining response beats before reporting the fault.
    clear_read_counters();
    translation_enable = 1'b0;
    response_error_beat = 1;
    begin_score(64'h5000, 64, 6);
    send_range(64'h5000, 64, 6);
    wait_fault(QBS_READ_FAULT_AXI_RESPONSE, 6, 64'h5010);
    response_error_beat = -1;
    if (r_beat_count != 4 || payload_byte_count != 16)
      $fatal(1, "AXI response drain/accounting mismatch");

    // Early and late RLAST are protocol faults. A late-last case is drained
    // until the slave eventually terminates the malformed response.
    clear_read_counters();
    last_mode = 1;
    begin_score(64'h6000, 64, 7);
    send_range(64'h6000, 64, 7);
    wait_fault(QBS_READ_FAULT_AXI_PROTOCOL, 7, 64'h6000);
    if (r_beat_count != 1 || payload_byte_count != 0)
      $fatal(1, "early RLAST handling mismatch");

    clear_read_counters();
    last_mode = 2;
    begin_score(64'h7000, 16, 8);
    send_range(64'h7000, 16, 8);
    wait_fault(QBS_READ_FAULT_AXI_PROTOCOL, 8, 64'h7000);
    last_mode = 0;
    if (r_beat_count != 2 || payload_byte_count != 0)
      $fatal(1, "late RLAST drain mismatch");

    // Invalid empty ranges are rejected locally.
    clear_read_counters();
    ar_base = ar_log_count;
    begin_score(64'h8000, 0, 9);
    send_range(64'h8000, 0, 9);
    wait_fault(QBS_READ_FAULT_REQUEST, 9, 64'h8000);
    if (ar_log_count != ar_base || range_count != 1)
      $fatal(1, "empty range rejection mismatch");

    // PMA rejection covers the aligned transfer and must precede AR issue.
    clear_read_counters();
    ar_base = ar_log_count;
    physical_range_allowed = 1'b0;
    begin_score(64'h8103, 20, 11);
    send_range(64'h8103, 20, 11);
    wait (physical_check_valid);
    if (physical_check_addr != 64'h8100 || physical_check_bytes != 32)
      $fatal(1, "PMA check did not cover aligned AXI padding");
    wait_fault(QBS_READ_FAULT_PMA, 11, 64'h8103);
    physical_range_allowed = 1'b1;
    if (ar_log_count != ar_base || ar_count != 0 || payload_byte_count != 0)
      $fatal(1, "PMA-rejected range reached AXI");

    // Faults are reported in subrequest order, not discovery order. Hold the
    // older response, discover a younger PMA fault, then return an error on the
    // older AXI request. The older AXI fault must replace the pending PMA fault.
    clear_read_counters();
    translation_enable = 1'b0;
    hold_axi_responses = 1'b1;
    response_error_beat = -1;
    physical_range_allowed = 1'b1;
    ar_base = ar_log_count;
    begin_score(64'hb000, 16, 15);
    send_range(64'hb000, 16, 15);
    while (ar_log_count != ar_base + 1) @(posedge clk);
    physical_range_allowed = 1'b0;
    send_range(64'hc000, 16, 16);
    wait (physical_check_valid && physical_check_addr == 64'hc000);
    repeat (2) @(posedge clk);
    if (fault_valid)
      $fatal(1, "younger planner fault bypassed an older response");
    response_error_beat = 0;
    hold_axi_responses = 1'b0;
    wait_fault(QBS_READ_FAULT_AXI_RESPONSE, 15, 64'hb000);
    response_error_beat = -1;
    physical_range_allowed = 1'b1;
    if (ar_log_count != ar_base + 1 || ar_count != 1 ||
        payload_byte_count != 0)
      $fatal(1, "ordered fault arbitration accounting mismatch");

    // A younger planner fault waits for an older successful response. Draining
    // that response must keep burst metadata aligned and preserve the planner
    // fault instead of fabricating an AXI protocol fault at RLAST.
    clear_read_counters();
    hold_axi_responses = 1'b1;
    physical_range_allowed = 1'b1;
    ar_base = ar_log_count;
    begin_score(64'hd000, 256, 17);
    send_range(64'hd000, 256, 17);
    while (ar_log_count != ar_base + 1) @(posedge clk);
    physical_range_allowed = 1'b0;
    send_range(64'he000, 16, 18);
    wait (physical_check_valid && physical_check_addr == 64'he000);
    repeat (2) @(posedge clk);
    if (fault_valid)
      $fatal(1, "younger planner fault bypassed an older clean response");
    hold_axi_responses = 1'b0;
    wait_fault(QBS_READ_FAULT_PMA, 18, 64'he000);
    physical_range_allowed = 1'b1;
    if (ar_log_count != ar_base + 1 || ar_count != 1 ||
        payload_byte_count != 0)
      $fatal(1, "clean drain changed planner-fault attribution");

    // Exercise the AXI maximum burst length at a page boundary.
    clear_read_counters();
    ar_base = ar_log_count;
    begin_score(64'h9000, 4096, 10);
    send_range(64'h9000, 4096, 10);
    wait_completion(10, 4096);
    if (ar_log_count != ar_base + 1 || ar_log_addr[ar_base] != 64'h9000 ||
        ar_log_len[ar_base] != 8'hff || r_beat_count != 256 ||
        payload_byte_count != 4096)
      $fatal(1, "maximum AXI burst mismatch");

    if (mmu_is_store)
      $fatal(1, "QBS read engine requested a store translation");

    $display("QBS read legacy cases PASS t=%0t", $time);
    if (!$test$plusargs("QBS_SKIP_AR_FAULT_TESTS")) begin
      for (int mode = 0; mode < 3; mode++) begin
        stalled_ar_fault(mode, 0);
        stalled_ar_fault(mode, 6);
      end
    end
    nonidentity_pages_contract();
    // These independently checked contracts share one unaligned cross-page read.
    $display("[QBS_READ_CASE] nonidentity_unaligned PASS");
    $display("[QBS_READ_CASE] noncontiguous_pages PASS");
    second_page_fault_contract(1'b0);
    second_page_fault_contract(1'b1);
    $display("[QBS_READ_CASE] second_page_fault PASS");
    $display("[QBS_READ_CASE] post_fault_reuse PASS");
    $display("QBS read engine PASS");
    $finish;
  end

endmodule : qbs_read_engine_tb
