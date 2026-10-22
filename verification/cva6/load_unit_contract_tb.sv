`timescale 1ns/1ps

// Real bypass/load/WT-control RTL; translation and cache storage are controlled
// boundary models. This test does not instantiate the MMU, scoreboard or CPU.
module load_unit_contract_tb;
  import ariane_pkg::*;
  function automatic config_pkg::cva6_cfg_t configuration();
    config_pkg::cva6_cfg_t c;
    c = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
    c.NonIdemPotenceEn = 1;
    c.NrNonIdempotentRules = 1;
    c.NonIdempotentAddrBase = '0;
    c.NonIdempotentLength = '0;
    c.NonIdempotentLength[0] = 64'h1000_0000;
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg = configuration();
  `include "load_contract_types.svh"
  localparam logic [63:0] MemoryWord = 64'h1122334455667788;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  lsu_ctrl_t incoming, head;
  dcache_req_i_t request;
  dcache_req_o_t response;
  exception_t fault, result_exception;
  logic flush, input_valid, bypass_ready, pop, result_valid, translation_req;
  logic [CVA6Cfg.TRANS_ID_BITS-1:0] result_id, commit_id;
  logic [63:0] result;
  logic [CVA6Cfg.VLEN-1:0] virtual_address;
  logic [CVA6Cfg.PLEN-1:0] physical_address;
  logic [CVA6Cfg.PLEN-1:0] miss_address;
  logic conflict, dtlb_hit, stores_empty, write_buffer_clear;
  logic cache_stall, cache_busy, rd_req, rd_allow, cache_hit;
  logic miss_req, miss_allow, miss_return, miss_ack;
  logic [CVA6Cfg.DCACHE_SET_ASSOC-1:0] hit_oh;
  logic fault_enable, fault_q;
  logic [63:0] fault_cause, fault_cause_q, fault_address_q;
  int cycle = 0, epoch = 0, seq = 0, cases = 0, errors = 0, checks = 0;
  int trace_fd, config_fd;
  string label;
  int active[8], issued_epoch[256], expected_cause[256];
  logic [63:0] address[256];
  int pops[256], completions[256], allocations[256], returns[256];
  bit canceled[256];
  int slots[2];
  int mem_pending = 0;
  int result_seq, return_seq, head_seq;

  assign hit_oh = cache_hit ? CVA6Cfg.DCACHE_SET_ASSOC'(1) : '0;
  assign miss_ack = miss_req && miss_allow;
  always_comb begin
    fault = '0;
    fault.valid = fault_q;
    fault.cause = fault_cause_q;
    fault.tval = fault_address_q;
  end
  // A one-cycle, request-qualified translation response. With request held,
  // repeatable faults recur; WAIT_PAGE_OFFSET gets only the initial pulse.
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      fault_q <= 0;
      fault_cause_q <= 0;
      fault_address_q <= 0;
      physical_address <= 0;
    end else begin
      fault_q <= translation_req && head.valid && fault_enable;
      fault_cause_q <= fault_cause;
      fault_address_q <= 64'(virtual_address);
      if (translation_req && head.valid) physical_address <= CVA6Cfg.PLEN'(virtual_address);
    end
  end

  lsu_bypass #(.CVA6Cfg(CVA6Cfg), .lsu_ctrl_t(lsu_ctrl_t)) bypass (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(flush), .lsu_req_i(incoming),
    .lsu_req_valid_i(input_valid), .pop_ld_i(pop), .pop_st_i(1'b0),
    .lsu_ctrl_o(head), .ready_o(bypass_ready)
  );
  load_unit #(.CVA6Cfg(CVA6Cfg), .lsu_ctrl_t(lsu_ctrl_t), .exception_t(exception_t),
    .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(flush), .valid_i(head.valid), .lsu_ctrl_i(head),
    .pop_ld_o(pop), .valid_o(result_valid), .trans_id_o(result_id), .result_o(result),
    .ex_o(result_exception), .translation_req_o(translation_req), .vaddr_o(virtual_address),
    .tinst_o(), .hs_ld_st_inst_o(), .hlvx_inst_o(), .paddr_i(physical_address), .ex_i(fault),
    .dtlb_hit_i(dtlb_hit), .dtlb_ppn_i(virtual_address[CVA6Cfg.PLEN-1:12]),
    .page_offset_o(), .page_offset_matches_i(conflict), .store_buffer_empty_i(stores_empty),
    .commit_tran_id_i(commit_id), .req_port_i(response), .req_port_o(request),
    .dcache_wbuffer_not_ni_i(write_buffer_clear)
  );
  wt_dcache_ctrl #(.CVA6Cfg(CVA6Cfg),
    .DCACHE_CL_IDX_WIDTH(CVA6Cfg.DCACHE_INDEX_WIDTH-CVA6Cfg.DCACHE_OFFSET_WIDTH),
    .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t)) cache (
    .clk_i(clk), .rst_ni(rst_n), .cache_en_i(1'b1), .busy_o(cache_busy), .stall_i(cache_stall),
    .req_port_i(request), .req_port_o(response), .miss_req_o(miss_req), .miss_ack_i(miss_ack),
    .miss_we_o(), .miss_wdata_o(), .miss_wuser_o(), .miss_vld_bits_o(), .miss_paddr_o(miss_address),
    .miss_nc_o(), .miss_size_o(), .miss_id_o(), .miss_replay_i(1'b0),
    .miss_rtrn_vld_i(miss_return), .wr_cl_vld_i(1'b0), .rd_tag_o(), .rd_idx_o(), .rd_off_o(),
    .rd_req_o(rd_req), .rd_tag_only_o(), .rd_ack_i(rd_req && rd_allow),
    .rd_data_i(MemoryWord), .rd_user_i('0), .rd_vld_bits_i('1), .rd_hit_oh_i(hit_oh)
  );

  task automatic check(bit ok, string what);
    checks++;
    if (!ok) begin
      errors++;
      $display("LOAD_CHECK_FAIL cycle=%0d case=%s %s", cycle, label, what);
    end
  endtask
  task automatic field(string name, logic [63:0] value);
    if ($isunknown(value)) $fatal(1, "LOAD_ENV_FAIL unknown %s cycle=%0d", name, cycle);
    $fwrite(trace_fd, ",\"%s\":%0d", name, value);
  endtask
  task automatic pre_trace;
    $fwrite(trace_fd, "{\"phase\":\"pre\",\"case\":\"%s\"", label);
    field("cycle", cycle); field("epoch", epoch);
    field("in_valid", input_valid); field("in_seq", incoming.data);
    field("in_id", incoming.trans_id); field("in_addr", incoming.vaddr);
    field("in_expected_cause", input_valid ? expected_cause[incoming.data] : 0);
    field("head_valid", head.valid); field("head_seq", head.data); field("head_id", head.trans_id);
    field("head_addr", head.vaddr); field("bypass_count", bypass.status_cnt_q);
    field("bypass_next", bypass.status_cnt_n); field("bypass_ready", bypass_ready);
    field("state", dut.state_q); field("next_state", dut.state_d); field("pop", pop);
    field("translation_req", translation_req); field("fault_enable", fault_enable);
    field("fault", fault.valid); field("cause", fault.cause); field("tval", fault.tval);
    field("dtlb_hit", dtlb_hit); field("conflict", conflict); field("stall_ni", dut.stall_ni);
    field("stores_empty", stores_empty); field("wb_clear", write_buffer_clear); field("commit_id", commit_id);
    field("flush", flush); field("req", request.data_req); field("gnt", response.data_gnt);
    field("req_id", request.data_id); field("tag", request.tag_valid); field("kill", request.kill_req);
    field("rvalid", response.data_rvalid); field("rid", response.data_rid);
    field("rdata", response.data_rdata); field("return_seq", return_seq);
    field("valid", result_valid); field("result_id", result_id); field("result_seq", result_seq);
    field("result", result); field("ex_valid", result_exception.valid);
    field("ex_cause", result_exception.cause); field("ex_tval", result_exception.tval);
    field("ldbuf_valid", dut.ldbuf_valid_q); field("ldbuf_next", dut.ldbuf_valid_d);
    field("ldbuf_flushed", dut.ldbuf_flushed_q); field("ldbuf_flushed_next", dut.ldbuf_flushed_d);
    field("ldbuf_w", dut.ldbuf_w); field("ldbuf_r", dut.ldbuf_r);
    field("last_id", dut.ldbuf_last_id_q); field("slot0_id", dut.ldbuf_q[0].trans_id);
    field("slot1_id", dut.ldbuf_q[1].trans_id);
    field("cache_state", cache.state_q); field("cache_next", cache.state_d);
    field("cache_busy", cache_busy); field("cache_stall", cache_stall);
    field("rd_req", rd_req); field("rd_allow", rd_allow); field("cache_hit", cache_hit);
    field("miss_req", miss_req); field("miss_ack", miss_ack);
    field("miss_return", miss_return); field("mem_pending", mem_pending);
    field("paddr", physical_address); field("miss_addr", miss_address);
    $fwrite(trace_fd, "}\n");
  endtask
  task automatic tick;
    @(posedge clk);
    if (rst_n) begin
      cycle++;
      if (input_valid) begin
        check(active[incoming.trans_id] == 0, "ID allocated while still active");
        active[incoming.trans_id] = int'(incoming.data);
        issued_epoch[incoming.data] = epoch;
      end
      head_seq = int'(head.data);
      return_seq = response.data_rvalid ? slots[response.data_rid] : 0;
      result_seq = result_valid ? active[result_id] : 0;
      pre_trace();
      if (head.valid && dut.stall_ni && !fault.valid)
        check(!pop, "NI request popped before ordering conditions were satisfied");
      if (miss_return) begin
        check(mem_pending == 1, "memory response without an accepted miss");
        mem_pending--;
      end
      if (miss_ack) begin
        check(mem_pending == 0, "second miss accepted before drain");
        mem_pending++;
      end
      if (pop) begin
        check(head.valid && head_seq > 0, "pop without valid logical request");
        pops[head_seq]++;
        check(pops[head_seq] == 1, "duplicate logical pop");
      end
      if (result_valid && !flush) begin
        check(result_seq > 0, "result without active instruction");
        check(!canceled[result_seq], "result from canceled epoch");
        completions[result_seq]++;
        check(completions[result_seq] == 1, "duplicate completion");
        check(result_exception.valid == (expected_cause[result_seq] != 0), "wrong exception status");
        if (result_exception.valid) begin
          check(result_exception.cause == expected_cause[result_seq], "wrong exception cause");
          check(result_exception.tval == address[result_seq], "exception belongs to wrong address");
        end else check(result == MemoryWord, "normal load result incorrect");
        active[result_id] = 0;
      end
      if (response.data_rvalid) begin
        check(return_seq > 0, "cache return without accepted attempt");
        returns[return_seq]++;
        slots[response.data_rid] = 0;
      end
      if (request.data_req && response.data_gnt) begin
        check(head.valid && head_seq > 0, "cache accepts invalid head");
        check(slots[request.data_id] == 0, "load buffer slot overwritten");
        slots[request.data_id] = head_seq;
        allocations[head_seq]++;
      end
      if (flush) begin
        for (int i = 0; i < 8; i++) begin
          if (active[i] != 0) canceled[active[i]] = 1;
          active[i] = 0;
        end
        epoch++;
      end
      #1;
      $fwrite(trace_fd, "{\"phase\":\"post\",\"case\":\"%s\"", label);
      field("cycle", cycle); field("epoch", epoch);
      field("state", dut.state_q); field("bypass_count", bypass.status_cnt_q);
      field("ldbuf_valid", dut.ldbuf_valid_q); field("ldbuf_flushed", dut.ldbuf_flushed_q);
      field("cache_state", cache.state_q); field("fault", fault.valid);
      $fwrite(trace_fd, "}\n");
    end else #1;
    @(negedge clk);
  endtask
  task automatic defaults;
    incoming = '0; input_valid = 0; flush = 0;
    conflict = 0; dtlb_hit = 1; stores_empty = 1; write_buffer_clear = 1;
    commit_id = 0; cache_stall = 0; rd_allow = 1; cache_hit = 1;
    miss_allow = 1; miss_return = 0; fault_enable = 0; fault_cause = 0;
  endtask
  task automatic begin_case(string name);
    defaults();
    label = name;
    cases++;
    check(dut.ldbuf_valid_q == 0 && bypass.status_cnt_q == 0 && !cache_busy && mem_pending == 0,
          "previous case did not drain");
  endtask
  task automatic issue(int id, logic [63:0] addr, int cause = 0);
    check(bypass_ready, "test driver ignored bypass readiness");
    seq++;
    if (seq >= 256) $fatal(1, "LOAD_ENV_FAIL transaction table exhausted");
    incoming = '0;
    incoming.valid = 1; incoming.operation = LD; incoming.fu = LOAD;
    incoming.vaddr = CVA6Cfg.VLEN'(addr); incoming.be = '1;
    incoming.trans_id = CVA6Cfg.TRANS_ID_BITS'(id); incoming.data = seq;
    expected_cause[seq] = cause; address[seq] = addr;
    input_valid = 1;
    tick();
    input_valid = 0; incoming = '0;
  endtask
  task automatic idle(int n);
    repeat (n) tick();
  endtask
  task automatic end_case;
    idle(3);
    check(dut.ldbuf_valid_q == 0 && bypass.status_cnt_q == 0 && !cache_busy && mem_pending == 0,
          "case has outstanding cache/queue state");
    for (int i = 0; i < 8; i++) check(active[i] == 0, "logical request has no completion");
    $display("LOAD_CASE_END name=%s cycle=%0d errors=%0d", label, cycle, errors);
  endtask
  task automatic old_miss;
    cache_hit = 0;
    issue(0, 64'h8000_0100);
    tick(); // SEND_TAG / READ -> MISS_REQ
    tick(); // Accept the miss -> MISS_WAIT
    check(cache.state_q == 3 && mem_pending == 1, "old miss setup failed");
    cache_stall = 1;
  endtask
  task automatic repeatable_fault(int cause);
    cache_stall = 1; fault_enable = 1; fault_cause = cause;
    issue(1, cause == 4 ? 64'h8000_0201 : 64'h8000_0200, cause);
    check(dut.state_q == 1 && fault.valid, "missing WAIT_GNT fault stimulus");
    tick();
    check(completions[seq] == 1 && pops[seq] == 1 && allocations[seq] == 0,
          "waiting fault must finish without cache acceptance");
    fault_enable = 0; cache_stall = 0;
  endtask

  initial begin
    foreach (active[i]) active[i] = 0;
    foreach (slots[i]) slots[i] = 0;
    foreach (pops[i]) begin
      pops[i] = 0; completions[i] = 0; allocations[i] = 0; returns[i] = 0;
      issued_epoch[i] = 0; expected_cause[i] = 0; address[i] = 0; canceled[i] = 0;
    end
    trace_fd = $fopen("load_trace.jsonl", "w");
    config_fd = $fopen("load_config.json", "w");
    if (!trace_fd || !config_fd) $fatal(1, "LOAD_ENV_FAIL cannot open evidence");
    $fwrite(config_fd, {"{\"schema\":1,\"scope\":\"load_bypass_wt_control_boundary_contract\",",
      "\"mmu\":%0d,\"ni\":%0d,\"load_entries\":%0d,\"xlen\":%0d,",
      "\"real_mmu\":false,\"real_scoreboard\":false,\"real_cache_array\":false}\n"},
      CVA6Cfg.MmuPresent, CVA6Cfg.NonIdemPotenceEn, CVA6Cfg.NrLoadBufEntries, CVA6Cfg.XLEN);
    $fclose(config_fd);
    defaults();
    label = "reset";
    repeat (3) tick();
    rst_n = 1;
    tick();
    check(CVA6Cfg.MmuPresent && CVA6Cfg.NrLoadBufEntries == 2 && CVA6Cfg.XLEN == 64,
          "unexpected test configuration");

    begin_case("back_to_back_hit");
    issue(0, 64'h8000_0100);
    issue(1, 64'h8000_0200);
    end_case();

    begin_case("wait_grant_misaligned"); repeatable_fault(4); end_case();
    begin_case("wait_grant_access_fault"); repeatable_fault(5); end_case();
    begin_case("wait_grant_page_fault"); repeatable_fault(13); end_case();

    begin_case("page_conflict_fault");
    conflict = 1; fault_enable = 1; fault_cause = 4;
    issue(2, 64'h8000_0301, 4);
    check(dut.state_q == 3 && fault.valid, "missing WAIT_PAGE_OFFSET fault stimulus");
    tick();
    check(completions[seq] == 1 && allocations[seq] == 0, "fault blocked on store conflict");
    conflict = 0; fault_enable = 0;
    end_case();

    begin_case("wait_grant_return_collision");
    old_miss();
    fault_enable = 1; fault_cause = 13;
    issue(1, 64'h8000_0200, 13);
    miss_return = 1;
    tick();
    check(completions[seq-1] == 1 && completions[seq] == 0 && pops[seq] == 0,
          "old response must win without removing faulty head");
    miss_return = 0;
    tick();
    check(completions[seq] == 1 && allocations[seq] == 0, "fault did not finish after collision");
    defaults(); end_case();

    begin_case("page_conflict_pulse_collision");
    old_miss();
    conflict = 1; fault_enable = 1; fault_cause = 4;
    issue(1, 64'h8000_0201, 4);
    miss_return = 1;
    tick();
    miss_return = 0;
    check(!fault.valid && pops[seq] == 0, "expected pulse to expire while head stays queued");
    idle(2);
    check(completions[seq] == 0 && head.valid, "lost pulse must not falsely complete or drop head");
    conflict = 0;
    tick(); // Return to WAIT_GNT, still no cache grant.
    tick(); // Reissue the translation.
    tick(); // Complete the regenerated fault.
    check(completions[seq] == 1 && allocations[seq] == 0, "queued fault did not recover");
    defaults(); end_case();

    begin_case("tlb_miss_fault");
    dtlb_hit = 0; fault_enable = 1; fault_cause = 13;
    issue(2, 64'h8000_0300, 13);
    tick(); // Abort accepted cache attempt and consume its kill response.
    check(completions[seq] == 0 && allocations[seq] == 1 && returns[seq] == 1,
          "kill acknowledgement is not a logical completion");
    tick(); tick(); // WAIT_TRANSLATION regenerates the fault, then completes.
    check(completions[seq] == 1 && pops[seq] == 1, "TLB fault did not complete once");
    defaults(); end_case();

    begin_case("tlb_miss_retry");
    dtlb_hit = 0;
    issue(2, 64'h8000_0300);
    tick(); tick();
    dtlb_hit = 1;
    idle(3);
    check(completions[seq] == 1 && allocations[seq] == 2 && returns[seq] == 2 && pops[seq] == 1,
          "retry attempts confused with logical instructions");
    defaults(); end_case();

    begin_case("nonidempotent_retry");
    stores_empty = 0; write_buffer_clear = 0; commit_id = 3; cache_hit = 0;
    issue(3, 64'h1000);
    tick();
    check(dut.state_q == 8, "NI abort did not enter the write-buffer check");
    tick();
    // The default FSM arm may retry via IDLE while the WB remains blocked.
    // The architectural requirement is retained ownership and no early pop.
    check(head.valid && head.data == seq && completions[seq] == 0 && pops[seq] == 0,
          "nonidempotent request bypassed store ordering");
    stores_empty = 1; write_buffer_clear = 1;
    idle(4);
    tick(); // Accept the retried uncached access at the miss boundary.
    miss_return = 1; tick();
    miss_return = 0;
    check(completions[seq] == 1 && allocations[seq] == 2, "NI retry did not finish");
    defaults(); end_case();

    begin_case("accepted_tag_fault");
    fault_enable = 1; fault_cause = 5;
    issue(2, 64'h8000_0300, 5);
    tick();
    check(completions[seq] == 1 && allocations[seq] == 1 && returns[seq] == 1,
          "accepted fault must complete through the kill/tag response");
    defaults(); end_case();

    begin_case("flush_old_miss_and_queued_head");
    old_miss();
    issue(1, 64'h8000_0200);
    flush = 1; tick();
    flush = 0; tick();
    check(completions[seq] == 0 && completions[seq-1] == 0 && canceled[seq] && canceled[seq-1],
          "flush must cancel both logical requests");
    miss_return = 1; tick();
    defaults();
    issue(0, 64'h8000_0400); // Reuse the canceled architectural ID after cache drain.
    end_case();

    begin_case("flush_same_accept");
    flush = 1;
    issue(0, 64'h8000_0500);
    flush = 0; tick();
    check(canceled[seq] && completions[seq] == 0 && allocations[seq] == 1 && returns[seq] == 1,
          "same-cycle flush/grant was not canceled and reclaimed");
    end_case();

    begin_case("flush_same_fault");
    cache_stall = 1; fault_enable = 1; fault_cause = 13;
    issue(1, 64'h8000_0600, 13);
    flush = 1; tick();
    defaults(); tick();
    check(canceled[seq] && completions[seq] == 0, "fault result at flush must not be counted as committed");
    issue(1, 64'h8000_0700);
    end_case();

    begin_case("fault_then_same_id");
    repeatable_fault(4);
    idle(2);
    issue(1, 64'h8000_0800);
    end_case();

    for (int i = 1; i <= seq; i++) begin
      check(allocations[i] == returns[i], "accepted cache attempt leaked");
      if (!canceled[i]) check(pops[i] == 1 && completions[i] == 1, "incomplete logical lifecycle");
      else check(completions[i] == 0 && pops[i] <= 1, "canceled lifecycle completed");
    end
    $display("LOAD_CONTRACT_END cases=%0d transactions=%0d cycles=%0d checks=%0d errors=%0d",
             cases, seq, cycle, checks, errors);
    $fclose(trace_fd);
    if (errors) $fatal(1, "LOAD_CONTRACT_FAIL");
    $finish;
  end
  initial begin
    #20000;
    $fatal(1, "LOAD_ENV_FAIL bounded 2000-cycle watchdog");
  end
endmodule
