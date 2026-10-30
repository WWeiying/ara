`timescale 1ns/1ps
`include "axi/typedef.svh"
`include "shared_reader_types.svh"

module shared_reader_tb;
  import axi_pkg::*;
  import qbs_pkg::*;
  typedef logic [63:0] addr_t;
  typedef logic [127:0] data_t;
  typedef logic [0:0] id_t;
  typedef logic [0:0] user_t;
  typedef struct packed {
    logic [63:0] cause, tval;
    logic valid;
  } exception_t;
  `AXI_TYPEDEF_AR_CHAN_T(ar_t, addr_t, id_t, user_t)
  `AXI_TYPEDEF_R_CHAN_T(r_t, data_t, id_t, user_t)
  `QBS_AKV_SHARED_READER_TYPEDEF_REQ_T(req_t, 64)
  `QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(rsp_t, 128, 64, exception_t)

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  logic [1:0] owner = 0, command_fire = 0;
  req_t request = '0, requests[2], reference_request;
  rsp_t responses[2], reference_response;
  logic clear_reference = 0;
  logic store_pending = 0, translation = 1;
  logic hold_mmu = 0, mmu_fault = 0, pma_allowed = 1;
  logic mmu_req, ref_mmu_req, mmu_store, ref_mmu_store;
  logic [63:0] mmu_va, ref_mmu_va;
  logic mmu_valid, mmu_exception_valid;
  logic [55:0] mmu_pa;
  exception_t mmu_exception;
  logic physical_valid, ref_physical_valid;
  logic [63:0] physical_addr, ref_physical_addr;
  logic [12:0] physical_bytes, ref_physical_bytes;
  ar_t ar, ref_ar;
  logic ar_valid, ref_ar_valid, ar_ready;
  r_t r;
  logic r_valid, r_ready, ref_r_ready;
  logic hold_ar = 0, hold_r = 0, error_enable = 0;
  logic [63:0] error_addr = 0;
  int error_beat = 0;
  int cycle = 0, compared = 0, cases = 0, payload_checks = 0;
  int completions = 0, faults = 0, clear_checks = 0;
  bit negative_test;

  // Poison the unselected endpoint, including its ready signals.
  always_comb begin
    requests[0] = '1;
    requests[1] = '1;
    reference_request = '0;
    if (owner == 1) begin
      requests[0] = request;
      reference_request = request;
    end else if (owner == 2) begin
      requests[1] = request;
      reference_request = request;
    end
    mmu_valid = mmu_req && !hold_mmu && !mmu_fault;
    mmu_pa = 56'(mmu_va + 64'h100000);
    mmu_exception_valid = mmu_req && !hold_mmu && mmu_fault;
    mmu_exception = '0;
    if (mmu_exception_valid)
      mmu_exception = '{cause:64'd13, tval:mmu_va, valid:1'b1};
  end

  qbs_akv_shared_reader #(
    .req_t(req_t), .rsp_t(rsp_t), .axi_ar_t(ar_t), .axi_r_t(r_t),
    .exception_t(exception_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .owner_i(owner), .command_fire_i(command_fire),
    .client_req_i(requests), .client_rsp_o(responses),
    .core_st_pending_i(store_pending), .en_ld_st_translation_i(translation),
    .mmu_req_o(mmu_req), .mmu_vaddr_o(mmu_va), .mmu_is_store_o(mmu_store),
    .mmu_valid_i(mmu_valid), .mmu_paddr_i(mmu_pa),
    .mmu_exception_valid_i(mmu_exception_valid), .mmu_exception_i(mmu_exception),
    .physical_check_valid_o(physical_valid), .physical_check_addr_o(physical_addr),
    .physical_check_bytes_o(physical_bytes), .physical_range_allowed_i(pma_allowed),
    .axi_ar_o(ar), .axi_ar_valid_o(ar_valid), .axi_ar_ready_i(ar_ready),
    .axi_r_i(r), .axi_r_valid_i(r_valid), .axi_r_ready_o(r_ready)
  );

  qbs_read_engine #(
    .AxiDataWidth(128), .AxiAddrWidth(64), .VAddrWidth(64), .PAddrWidth(56),
    .RangeBytesWidth(16), .ReadOutstanding(2), .tag_t(logic [15:0]),
    .axi_ar_t(ar_t), .axi_r_t(r_t), .exception_t(exception_t)
  ) reference_reader (
    .clk_i(clk), .rst_ni(rst_n),
    .range_valid_i(reference_request.range_valid),
    .range_ready_o(reference_response.range_ready),
    .range_vaddr_i(reference_request.range_vaddr),
    .range_bytes_i(reference_request.range_bytes), .range_tag_i(reference_request.range_tag),
    .range_cache_i(reference_request.range_cache), .range_prot_i(reference_request.range_prot),
    .data_valid_o(reference_response.data_valid), .data_ready_i(reference_request.data_ready),
    .data_o(reference_response.data), .data_strb_o(reference_response.data_strb),
    .data_offset_o(reference_response.data_offset), .data_tag_o(reference_response.data_tag),
    .completion_valid_o(reference_response.completion_valid),
    .completion_ready_i(reference_request.completion_ready),
    .completion_tag_o(reference_response.completion_tag),
    .fault_valid_o(reference_response.fault_valid), .fault_ready_i(reference_request.fault_ready),
    .fault_kind_o(reference_response.fault_kind), .fault_vaddr_o(reference_response.fault_vaddr),
    .fault_tag_o(reference_response.fault_tag),
    .fault_mmu_exception_o(reference_response.fault_mmu_exception),
    .core_st_pending_i(store_pending), .en_ld_st_translation_i(translation),
    .mmu_req_o(ref_mmu_req), .mmu_vaddr_o(ref_mmu_va), .mmu_is_store_o(ref_mmu_store),
    .mmu_valid_i(mmu_valid), .mmu_paddr_i(mmu_pa),
    .mmu_exception_valid_i(mmu_exception_valid), .mmu_exception_i(mmu_exception),
    .physical_check_valid_o(ref_physical_valid), .physical_check_addr_o(ref_physical_addr),
    .physical_check_bytes_o(ref_physical_bytes), .physical_range_allowed_i(pma_allowed),
    .axi_ar_o(ref_ar), .axi_ar_valid_o(ref_ar_valid), .axi_ar_ready_i(ar_ready),
    .axi_r_i(r), .axi_r_valid_i(r_valid), .axi_r_ready_o(ref_r_ready),
    .counters_clear_i(clear_reference),
    .range_count_o(reference_response.range_count),
    .translation_count_o(reference_response.translation_count),
    .ar_count_o(reference_response.ar_count), .r_beat_count_o(reference_response.r_beat_count),
    .payload_byte_count_o(reference_response.payload_byte_count),
    .store_wait_cycles_o(reference_response.store_wait_cycles),
    .r_backpressure_cycles_o(reference_response.r_backpressure_cycles),
    .outstanding_occupancy_sum_o(reference_response.outstanding_occupancy_sum),
    .outstanding_max_o(reference_response.outstanding_max),
    .outstanding_full_cycles_o(reference_response.outstanding_full_cycles),
    .busy_o(reference_response.busy)
  );

  function automatic logic [7:0] memory_byte(logic [63:0] address);
    return address[7:0] ^ address[15:8] ^ address[23:16] ^ 8'h5a;
  endfunction

  // In-order AXI memory, with stable responses while the consumer is stalled.
  ar_t queue[16];
  int wr = 0, rd = 0, beat = 0;
  always_comb begin
    ar_ready = !hold_ar && wr-rd < 16;
    r = '0;
    r_valid = wr != rd && !hold_r;
    if (wr != rd) begin
      for (int b=0; b<16; b++)
        r.data[b*8 +: 8] = memory_byte(queue[rd%16].addr + 64'(beat*16+b));
      r.last = beat == int'(queue[rd%16].len);
      r.resp = error_enable && queue[rd%16].addr == error_addr && beat == error_beat
          ? RESP_SLVERR : RESP_OKAY;
    end
  end
  always @(posedge clk) begin
    if (rst_n) begin
      cycle <= cycle + 1;
      if (ar_valid && ar_ready) begin
        assert (ar.cache == 4'b1011 && ar.prot == 3'b010 && ar.size == 4 &&
                ar.burst == BURST_INCR && ar.id == 0 && wr-rd < 2)
          else $fatal(1, "UNIT_AXI_METADATA");
        queue[wr%16] <= ar;
        wr <= wr+1;
      end
      if (r_valid && r_ready) begin
        if (r.last) begin rd <= rd+1; beat <= 0; end
        else beat <= beat+1;
      end
    end
  end

  // Independent logical payload scoreboard, not an equality-only oracle.
  int expected_count = 0;
  logic [63:0] expected_addr[8];
  logic [15:0] expected_tag[8];
  int expected_bytes[8], received[8];
  bit completed[8];
  always @(posedge clk) begin : compare_and_score
    int index_found, count;
    if (rst_n && !negative_test) begin
      assert ({ar, ar_valid, r_ready, mmu_req, mmu_va, mmu_store,
               physical_valid, physical_addr, physical_bytes} ===
              {ref_ar, ref_ar_valid, ref_r_ready, ref_mmu_req, ref_mmu_va, ref_mmu_store,
               ref_physical_valid, ref_physical_addr, ref_physical_bytes})
        else $fatal(1, "UNIT_COMMON_MISMATCH cycle=%0d", cycle);
      for (int c=0; c<2; c++) begin
        if (owner[c]) begin
          assert (responses[c] === reference_response)
            else $fatal(1, "UNIT_RESPONSE_MISMATCH client=%0d cycle=%0d", c, cycle);
        end else assert (responses[c] === rsp_t'('0))
          else $fatal(1, "UNIT_INACTIVE_NONZERO client=%0d", c);
      end
      compared++;
      if (reference_response.data_valid && reference_request.data_ready) begin
        index_found = -1;
        for (int i=0; i<expected_count; i++)
          if (expected_tag[i] == reference_response.data_tag) index_found = i;
        assert (index_found >= 0) else $fatal(1, "UNIT_UNKNOWN_DATA_TAG");
        assert (reference_response.data_offset == received[index_found])
          else $fatal(1, "UNIT_OFFSET");
        count = $countones(reference_response.data_strb);
        assert (count > 0 && reference_response.data_strb == 16'((1<<count)-1) &&
                received[index_found]+count <= expected_bytes[index_found])
          else $fatal(1, "UNIT_STRB");
        for (int b=0; b<count; b++) begin
          assert (reference_response.data[b*8 +: 8] ===
                  memory_byte(expected_addr[index_found]+64'(received[index_found]+b)))
            else $fatal(1, "UNIT_PAYLOAD");
          payload_checks++;
        end
        received[index_found] += count;
      end
      if (reference_response.completion_valid && reference_request.completion_ready) begin
        index_found = -1;
        for (int i=0; i<expected_count; i++)
          if (expected_tag[i] == reference_response.completion_tag) index_found = i;
        assert (index_found >= 0) else $fatal(1, "UNIT_UNKNOWN_COMPLETION_TAG");
        assert (!completed[index_found] && received[index_found] == expected_bytes[index_found])
          else $fatal(1, "UNIT_COMPLETION_BYTES");
        completed[index_found] = 1;
        completions++;
      end
      if (reference_response.fault_valid && reference_request.fault_ready) faults++;
    end
  end

  task automatic tick(input int n=1);
    repeat (n) @(negedge clk);
  endtask
  task automatic start_command(input int client);
    tick();
    assert (!reference_response.busy && owner == 0 && wr == rd)
      else $fatal(1, "UNIT_START_NOT_IDLE");
    request = '0;
    command_fire = 2'(1<<client);
    clear_reference = 1;
    expected_count = 0;
    tick();
    assert ({reference_response.range_count, reference_response.translation_count,
      reference_response.ar_count, reference_response.r_beat_count,
      reference_response.payload_byte_count, reference_response.store_wait_cycles,
      reference_response.r_backpressure_cycles, reference_response.outstanding_occupancy_sum,
      reference_response.outstanding_max, reference_response.outstanding_full_cycles} === '0)
      else $fatal(1, "UNIT_REFERENCE_CLEAR");
    // Observe internal counters while both external response records are zero.
    assert (dut.reader_rsp === reference_response)
      else $fatal(1, "UNIT_ZERO_OWNER_CLEAR");
    clear_checks++;
    command_fire = 0;
    clear_reference = 0;
    owner = 2'(1<<client);
    request.data_ready = 1;
    request.completion_ready = 1;
    request.range_cache = 4'b1011;
    request.range_prot = 3'b010;
    tick();
  endtask
  task automatic send_range(input logic [63:0] address, input int bytes,
                            input logic [15:0] tag);
    int i;
    i = expected_count++;
    assert (i < 8) else $fatal(1, "UNIT_SCOREBOARD_FULL");
    expected_addr[i] = address + (translation ? 64'h100000 : 0);
    expected_bytes[i] = bytes;
    expected_tag[i] = tag;
    received[i] = 0;
    completed[i] = 0;
    request.range_vaddr = address;
    request.range_bytes = 16'(bytes);
    request.range_tag = tag;
    request.range_valid = 1;
    do @(posedge clk); while (!reference_response.range_ready);
    tick();
    request.range_valid = 0;
  endtask
  task automatic finish_success(input int count, input int bytes);
    wait (!reference_response.busy);
    tick();
    assert (reference_response.range_count == count &&
            reference_response.payload_byte_count == bytes)
      else $fatal(1, "UNIT_SUCCESS_COUNTS");
    for (int i=0; i<expected_count; i++)
      assert (completed[i]) else $fatal(1, "UNIT_MISSING_COMPLETION");
    owner = 0;
    request = '0;
    cases++;
    tick(2);
  endtask
  task automatic consume_fault(input qbs_read_fault_e kind, input logic [63:0] va,
                               input logic [15:0] tag, input int bytes);
    wait (reference_response.fault_valid);
    tick(4);
    assert (reference_response.fault_kind == kind && reference_response.fault_vaddr == va &&
            reference_response.fault_tag == tag &&
            reference_response.payload_byte_count == bytes && wr == rd)
      else $fatal(1, "UNIT_FAULT_METADATA kind=%0d va=%h tag=%h bytes=%0d",
                  reference_response.fault_kind, reference_response.fault_vaddr,
                  reference_response.fault_tag, reference_response.payload_byte_count);
    if (kind == QBS_READ_FAULT_MMU)
      assert (reference_response.fault_mmu_exception ===
              exception_t'{cause:64'd13,tval:va,valid:1'b1})
        else $fatal(1, "UNIT_MMU_EXCEPTION");
    request.fault_ready = 1;
    tick();
    assert (!reference_response.busy) else $fatal(1, "UNIT_FAULT_NOT_CONSUMED");
    // Fault metadata is sticky, even though fault_valid clears. Compare it too.
    assert (reference_response.fault_kind == kind && dut.reader_rsp === reference_response)
      else $fatal(1, "UNIT_STICKY_FAULT");
    owner = 0;
    request = '0;
    cases++;
    tick(2);
  endtask

  initial begin
    negative_test = $test$plusargs("BAD_OWNER") || $test$plusargs("BAD_FIRE") ||
                    $test$plusargs("BAD_READMIT");
    tick(3); rst_n = 1; tick(2);
    start_command(0);
    if ($test$plusargs("BAD_READMIT")) begin
      owner = 0; tick(2); owner = 1; tick(2);
      $fatal(1, "UNIT_NEGATIVE_NOT_REJECTED");
    end
    store_pending = 1; hold_mmu = 1; hold_r = 1;
    send_range(64'h1ff3, 4096, 16'hba51);
    if ($test$plusargs("BAD_OWNER")) begin
      owner = 2; tick(2); $fatal(1, "UNIT_NEGATIVE_NOT_REJECTED");
    end
    if ($test$plusargs("BAD_FIRE")) begin
      command_fire = 1; tick(2); $fatal(1, "UNIT_NEGATIVE_NOT_REJECTED");
    end
    wait (reference_response.store_wait_cycles == 6);
    tick(); store_pending = 0;
    wait (mmu_req); tick(5); hold_mmu = 0;
    wait (reference_response.outstanding_max == 2);
    tick(3); hold_r = 0;
    request.data_ready = 0; tick(7); request.data_ready = 1;
    finish_success(1, 4096);
    assert (reference_response.outstanding_max == 2 &&
            reference_response.store_wait_cycles >= 6 &&
            reference_response.r_backpressure_cycles >= 7 &&
            reference_response.translation_count == 2)
      else $fatal(1, "UNIT_COVERAGE_COUNTERS");

    start_command(1);
    translation = 0;
    request.completion_ready = 0;
    send_range(64'h4003, 17, 16'h00e1);
    send_range(64'h5005, 31, 16'h00e2);
    wait (reference_response.completion_valid);
    tick(15); request.completion_ready = 1;
    finish_success(2, 48);
    translation = 1;

    start_command(0);
    error_enable = 1; error_addr = 64'h106000; error_beat = 1;
    send_range(64'h6000, 64, 16'hcd23);
    consume_fault(QBS_READ_FAULT_AXI_RESPONSE, 64'h6010, 16'hcd23, 16);
    error_enable = 0;
    start_command(1); send_range(64'h7001, 32, 16'h0037); finish_success(1,32);

    start_command(1); mmu_fault = 1;
    send_range(64'h8000, 32, 16'h0041);
    consume_fault(QBS_READ_FAULT_MMU, 64'h8000, 16'h0041, 0);
    mmu_fault = 0;
    start_command(0); send_range(64'h9000, 16, 16'hf123); finish_success(1,16);

    // An earlier failing burst must drain a later AR already offered under stall.
    start_command(0); hold_r = 1;
    error_enable = 1; error_addr = 64'h10a000; error_beat = 0;
    send_range(64'ha000, 32, 16'hc101);
    wait (reference_response.ar_count == 1); tick(); hold_ar = 1;
    send_range(64'hb000, 32, 16'hc102);
    wait (ar_valid); tick(2); hold_r = 0;
    tick(8);
    assert (ar_valid && !reference_response.fault_valid && reference_response.busy)
      else $fatal(1, "UNIT_STALLED_AR_DRAIN");
    hold_ar = 0;
    consume_fault(QBS_READ_FAULT_AXI_RESPONSE, 64'ha000, 16'hc101, 0);
    error_enable = 0;
    start_command(1); send_range(64'hc000, 23, 16'h00fe); finish_success(1,23);

    start_command(1); pma_allowed = 0;
    send_range(64'hd000, 16, 16'h0051);
    consume_fault(QBS_READ_FAULT_PMA, 64'hd000, 16'h0051, 0);
    pma_allowed = 1;
    start_command(0); send_range(64'he000, 16, 16'hf151); finish_success(1,16);
    assert (cases == 10 && faults == 4 && completions == 7 && clear_checks == 10 &&
            payload_checks == 4247)
      else $fatal(1, "UNIT_FINAL_COUNTS cases=%0d faults=%0d completions=%0d bytes=%0d",
                  cases, faults, completions, payload_checks);
    $display("SHARED_READER_UNIT_PASS cases=%0d faults=%0d completions=%0d bytes=%0d clears=%0d compared_cycles=%0d",
             cases, faults, completions, payload_checks, clear_checks, compared);
    $finish;
  end
  initial begin
    #100000;
    $fatal(1, "UNIT_TIMEOUT cycle=%0d cases=%0d", cycle, cases);
  end
endmodule
