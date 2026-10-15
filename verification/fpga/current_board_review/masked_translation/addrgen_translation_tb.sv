module addrgen_translation_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  localparam config_pkg::cva6_cfg_t Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef logic [10:0] vlen_t;
  typedef logic [63:0] address_t;
  typedef logic [3:0] id_t;
  typedef logic user_t;
  `include "ara/ara_typedef.svh"
  `include "ara/intf_typedef.svh"
  `include "axi/typedef.svh"
  `CVA6_TYPEDEF_EXCEPTION(exception_t, Cfg)
  `AXI_TYPEDEF_AR_CHAN_T(ar_t, address_t, id_t, user_t)
  `AXI_TYPEDEF_AW_CHAN_T(aw_t, address_t, id_t, user_t)

  localparam address_t Target = 64'h40001000;
  localparam address_t Physical = 64'h80010000;
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst, req_valid;
  pe_req_t req;
  logic [NrVInsn-1:0] parent_running;
  logic [3:0][7:0] mask_word;
  logic [3:0] mask_valid;
  logic mmu_req, mmu_valid, mmu_store;
  logic [Cfg.VLEN-1:0] mmu_vaddr;
  logic [Cfg.PLEN-1:0] mmu_paddr;
  exception_t mmu_exception, exception_out;
  logic ack, fof, illegal_load, illegal_store, idle;
  vlen_t exception_start;
  ar_t ar;
  aw_t aw;
  logic ar_valid, aw_valid, descriptor_valid, descriptor_ready;
  addrgen_axi_req_t descriptor;
  int variant, cycle, fd;
  int accepts, request_episodes, responses, pushes, pops, acks, ars;
  int accept_cycle, request_cycle, response_cycle, push_cycle, pop_cycle, ack_cycle;
  bit fault_page, predicate_active, request_seen, previous_request, response_seen;
  string case_name;

  assign descriptor_ready = descriptor_valid;
  addrgen #(.NrLanes(4), .VLEN(1024), .AxiDataWidth(256), .AxiAddrWidth(64),
    .axi_ar_t(ar_t), .axi_aw_t(aw_t), .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t),
    .CVA6Cfg(Cfg), .exception_t(exception_t)) dut (
    .clk_i(clk), .rst_ni(rst), .axi_ar_o(ar), .axi_ar_valid_o(ar_valid),
    .axi_ar_ready_i(1'b1), .axi_aw_o(aw), .axi_aw_valid_o(aw_valid),
    .axi_aw_ready_i(1'b1), .en_ld_st_translation_i(1'b1),
    .mmu_misaligned_ex_o(), .mmu_req_o(mmu_req), .mmu_vaddr_o(mmu_vaddr),
    .mmu_is_store_o(mmu_store), .mmu_dtlb_hit_i(1'b0), .mmu_dtlb_ppn_i('0),
    .mmu_valid_i(mmu_valid), .mmu_paddr_i(mmu_paddr), .mmu_exception_i(mmu_exception),
    .core_st_pending_i(1'b0), .pe_req_i(req), .pe_req_valid_i(req_valid),
    .pe_vinsn_running_i(parent_running), .addrgen_exception_o(exception_out), .addrgen_ack_o(ack),
    .addrgen_exception_vstart_o(exception_start), .addrgen_fof_exception_o(fof),
    .addrgen_illegal_load_o(illegal_load), .addrgen_illegal_store_o(illegal_store),
    .axi_addrgen_req_o(descriptor), .axi_addrgen_req_valid_o(descriptor_valid),
    .ldu_axi_addrgen_req_ready_i(descriptor_ready), .stu_axi_addrgen_req_ready_i(1'b0),
    .ldu_mask_word_i(mask_word), .ldu_mask_word_valid_i(mask_valid),
    .ldu_mask_owner_id_i(vid_t'(3)), .ldu_mask_first_element_i(vlen_t'(0)),
    .stu_mask_word_i('0), .stu_mask_word_valid_i('0), .stu_mask_owner_id_i('0),
    .stu_mask_first_element_i('0), .addrgen_operand_i('0),
    .addrgen_operand_valid_i('0), .addrgen_operand_ready_o(), .lsu_ex_flush_i(1'b0),
    .idle_o(idle));

  // A response exists only after the model observed a real request. Drive on
  // the opposite edge; the response is sampled exactly three clocks later.
  always @(negedge clk) begin
    mmu_valid = 0;
    mmu_exception = '0;
    mmu_paddr = '0;
    // Abstract consumer/sequencer retirement, not measured VLDU completion.
    // AddrGen idle includes its externally supplied running-ID lifetime.
    if (rst && acks == 1 && pops == 1 && parent_running != '0) begin
      parent_running = '0;
      $display("MODEL_RELEASE case=%s after_cycle=%0d parent_running=0", case_name, cycle);
    end
    if (rst && request_seen && !response_seen && cycle == request_cycle + 2) begin
      mmu_valid = 1;
      mmu_paddr = Physical;
      if (fault_page) begin
        mmu_exception.valid = 1;
        mmu_exception.cause = riscv::LOAD_PAGE_FAULT;
        mmu_exception.tval = Target;
      end
    end
  end

  // All rows sample pre-NBA values at the accepting edge, including FIFO
  // push data. No deposited/forced internal DUT values are used.
  always @(posedge clk) if (rst) begin
    cycle++;
    assert (!$isunknown({mmu_req, mmu_valid, ack, exception_out.valid,
                        ar_valid, aw_valid, descriptor_valid, idle}))
      else $fatal(1, "unknown interface output");
    assert (!aw_valid && !illegal_load && !illegal_store && !fof)
      else $fatal(1, "unexpected store/early exception/FOF");
    assert (!dut.axi_addrgen_queue_full && mask_valid == 4'hf)
      else $fatal(1, "fixture backpressure or invalid mask");
    if (req_valid && dut.state_q == 0 && !dut.vinsn_running_q[req.id]) begin
      accepts++;
      accept_cycle = cycle;
      $display("EVENT case=%s cycle=%0d kind=accept id=%0d vm=%b vl=%0d mask=%h",
               case_name, cycle, req.id, req.vm, req.vl, mask_word);
    end
    if (mmu_req) begin
      assert (accepts == 1 && mmu_vaddr == Target && !mmu_store)
        else $fatal(1, "unbound/wrong translation request");
      if (!previous_request) request_episodes++;
      if (!request_seen) begin
        request_seen = 1;
        request_cycle = cycle;
        $display("EVENT case=%s cycle=%0d kind=mmu_request vaddr=%h mask=%h state=%0d",
                 case_name, cycle, mmu_vaddr, mask_word, dut.state_q);
      end
      assert (!response_seen) else $fatal(1, "duplicate translation after response");
    end
    previous_request = mmu_req;
    if (mmu_valid) begin
      assert (request_seen && !response_seen && cycle == request_cycle + 3)
        else $fatal(1, "unsolicited/duplicate/wrong-latency MMU response");
      response_seen = 1;
      responses++;
      response_cycle = cycle;
      $display("EVENT case=%s cycle=%0d kind=mmu_response exception=%b cause=%0d tval=%h",
               case_name, cycle, mmu_exception.valid, mmu_exception.cause, mmu_exception.tval);
    end
    if (dut.axi_addrgen_queue_push) begin
      pushes++;
      push_cycle = cycle;
      assert (mmu_valid && dut.axi_addrgen_queue.is_exception == fault_page &&
              !dut.axi_addrgen_queue.is_skip && dut.axi_addrgen_queue.is_load)
        else $fatal(1, "wrong descriptor push or push before response");
      $display("EVENT case=%s cycle=%0d kind=descriptor_push exception=%b skip=%b",
               case_name, cycle, dut.axi_addrgen_queue.is_exception, dut.axi_addrgen_queue.is_skip);
    end
    if (descriptor_valid && descriptor_ready) begin
      pops++;
      pop_cycle = cycle;
      assert (descriptor.is_exception == fault_page && !descriptor.is_skip)
        else $fatal(1, "descriptor corrupted");
      $display("EVENT case=%s cycle=%0d kind=descriptor_pop exception=%b", case_name,
               cycle, descriptor.is_exception);
    end
    if (ar_valid) begin
      ars++;
      assert (!fault_page && mmu_valid && ar.addr == Physical && ar.len == 0 && ar.size == 5)
        else $fatal(1, "unexpected physical access");
      $display("EVENT case=%s cycle=%0d kind=axi_ar addr=%h len=%0d size=%0d",
               case_name, cycle, ar.addr, ar.len, ar.size);
    end
    if (ack) begin
      acks++;
      ack_cycle = cycle;
      assert (response_seen && exception_out.valid == fault_page && exception_start == 0)
        else $fatal(1, "wrong ack/exception ordering");
      if (fault_page) begin
        assert (exception_out.cause == 13 && exception_out.tval == Target &&
                cycle == response_cycle + 1) else $fatal(1, "wrong fault attribution");
      end else begin
        assert (cycle == response_cycle) else $fatal(1, "wrong success ack timing");
      end
      $display("EVENT case=%s cycle=%0d kind=addrgen_ack exception=%b cause=%0d tval=%h",
               case_name, cycle, exception_out.valid, exception_out.cause, exception_out.tval);
    end
    $fdisplay(fd, "%0d,%0d,%0d,%b,%b,%0d,%b,%h,%b,%b,%b,%h,%b,%b,%0d,%b,%b,%b,%b,%b,%b,%0d,%b,%b,%b,%b",
      cycle, dut.state_q, dut.axi_addrgen_state_q, req_valid, dut.addrgen_req_valid,
      dut.axi_addrgen_q.len, dut.pe_req_q.vm, mask_word, mask_valid == 4'hf,
      dut.mmu_req_d, mmu_req, mmu_vaddr, mmu_valid, mmu_exception.valid,
      mmu_exception.cause, dut.axi_addrgen_queue_push, dut.axi_addrgen_queue.is_exception,
      descriptor_valid, descriptor_ready, ar_valid, ack, exception_out.cause,
      exception_out.valid, dut.last_translation_completed, fof, idle);
    assert (cycle < 64) else $fatal(1, "bounded fixture timeout");
  end

  initial begin
    cycle = 0; accepts = 0; request_episodes = 0; responses = 0;
    pushes = 0; pops = 0; acks = 0; ars = 0;
    accept_cycle = 0; request_cycle = 0; response_cycle = 0;
    push_cycle = 0; pop_cycle = 0; ack_cycle = 0;
    request_seen = 0; previous_request = 0; response_seen = 0;
    assert (Cfg.XLEN == 64 && Cfg.VLEN == 64 && Cfg.PLEN == 56)
      else $fatal(1, "invalid expanded CVA6 configuration");
    variant = 0;
    void'($value$plusargs("CASE=%d", variant));
    assert (variant >= 0 && variant <= 2) else $fatal(1, "bad case");
    case_name = variant == 0 ? "alloff_fault" : variant == 1 ? "active_fault" : "alloff_valid";
    fault_page = variant != 2;
    predicate_active = variant == 1;
    fd = $fopen("cycles.csv", "w");
    assert (fd != 0) else $fatal(1, "cannot open probe");
    $fdisplay(fd, "cycle,state,axi_state,pe_valid,ag_valid,len,vm,mask,mask_valid,mmu_req_d,mmu_req,vaddr,mmu_valid,mmu_exception,mmu_cause,push,push_exception,desc_valid,desc_ready,ar_valid,ack,ack_cause,ack_exception,last_translation,fof,idle");
    $dumpfile("window.vcd");
    $dumpvars(0, addrgen_translation_tb);
    rst = 0; req_valid = 0; req = '0; mask_word = '0; mask_valid = '1;
    parent_running = '0;
    mmu_valid = 0; mmu_exception = '0; mmu_paddr = '0;
    repeat (4) @(negedge clk);
    req.id = 3; req.op = VLE; req.vfu = VFU_LoadUnit; req.vm = 0;
    req.vl = 8; req.vstart = 0; req.vtype.vsew = EW16;
    req.vtype.vlmul = LMUL_1; req.emul = LMUL_1;
    req.scalar_op = Target; req.vd = 24; req.use_vd = 1;
    if (predicate_active) mask_word[0][1:0] = 2'b11;
    parent_running[3] = 1;
    rst = 1; req_valid = 1;
    @(negedge clk);
    req_valid = 0;
    while (acks == 0 || pops == 0 || !idle) @(negedge clk);
    repeat (4) @(negedge clk);
    assert (accepts == 1 && request_episodes == 1 && responses == 1 &&
            pushes == 1 && pops == 1 && acks == 1 && ars == int'(!fault_page))
      else $fatal(1, "unexpected event counts");
    assert (request_cycle > accept_cycle && push_cycle == response_cycle &&
            pop_cycle == push_cycle + 1) else $fatal(1, "bad causal order");
    $display("DISCRIMINATOR_EXPECTATION_PASS case=%s accept=%0d request=%0d response=%0d push=%0d pop=%0d ack=%0d translations=%0d exceptions=%0d ar=%0d architectural_pass=NOT_CLAIMED",
      case_name, accept_cycle, request_cycle, response_cycle, push_cycle, pop_cycle,
      ack_cycle, request_episodes, int'(fault_page), ars);
    $fclose(fd);
    $finish;
  end
endmodule
