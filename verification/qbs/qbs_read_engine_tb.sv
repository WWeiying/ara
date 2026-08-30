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

  // One-cycle MMU response model. The page offset is deliberately preserved.
  logic mmu_pending;
  logic [63:0] mmu_pending_vaddr;
  logic mmu_pending_fault;
  logic inject_mmu_fault;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mmu_pending <= 1'b0;
      mmu_pending_vaddr <= '0;
      mmu_pending_fault <= 1'b0;
      mmu_valid <= 1'b0;
      mmu_paddr <= '0;
      mmu_exception <= '0;
    end else begin
      mmu_valid <= 1'b0;
      mmu_exception <= '0;
      if (!mmu_pending && mmu_req) begin
        mmu_pending <= 1'b1;
        mmu_pending_vaddr <= mmu_vaddr;
        mmu_pending_fault <= inject_mmu_fault;
      end else if (mmu_pending) begin
        mmu_pending <= 1'b0;
        mmu_valid <= 1'b1;
        mmu_paddr <= mmu_pending_vaddr;
        if (mmu_pending_fault) begin
          mmu_exception.valid <= 1'b1;
          mmu_exception.cause <= 64'd13;
          mmu_exception.tval <= mmu_pending_vaddr;
        end
      end
    end
  end

  assign mmu_exception_valid = mmu_exception.valid;

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
  integer last_mode;
  logic hold_axi_responses;
  integer ar_log_count;
  logic [63:0] ar_log_addr [0:31];
  logic [7:0] ar_log_len [0:31];

  assign axi_ar_ready = response_count < 2;
  assign axi_r_valid = response_count != 0 && !hold_axi_responses;

  always_comb begin
    axi_r = '0;
    for (int unsigned byte_lane = 0; byte_lane < BeatBytes; byte_lane++) begin
      axi_r.data[byte_lane*8 +: 8] =
          memory_byte(response_addr[response_rd] +
                      response_beat * BeatBytes + byte_lane);
    end
    axi_r.resp = integer'(response_beat) == response_error_beat ?
                 RESP_SLVERR : RESP_OKAY;
    unique case (last_mode)
      1: axi_r.last = response_beat == 0;
      2: axi_r.last = response_beat ==
                      {1'b0, response_len[response_rd]} + 1'b1;
      default: axi_r.last = response_beat ==
                            {1'b0, response_len[response_rd]};
    endcase
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
  always_ff @(posedge clk or negedge rst_n) begin
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
    end else if (data_valid && data_ready) begin
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
    physical_range_allowed = 1'b1;
    counters_clear = 1'b0;
    response_error_beat = -1;
    last_mode = 0;
    hold_axi_responses = 1'b0;
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

    $display("QBS read engine PASS");
    $finish;
  end

endmodule : qbs_read_engine_tb
