`timescale 1ns/1ps
module mmu_early_ppn_tb;
  import ariane_pkg::*;
  function automatic config_pkg::cva6_cfg_t configuration();
    config_pkg::cva6_cfg_t c;
    c = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
    c.NrPMPEntries = 0;
    c.NonIdemPotenceEn = 1;
    c.NrNonIdempotentRules = 2;
    c.NonIdempotentAddrBase = '0;
    c.NonIdempotentLength = '0;
    c.NonIdempotentAddrBase[0] = 64'hc0000000;
    c.NonIdempotentAddrBase[1] = 64'hd0000000;
    c.NonIdempotentLength[0] = 64'h1000;
    c.NonIdempotentLength[1] = 64'h1000;
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg = configuration();
  `include "mmu_early_ppn_types.svh"

  // Refill port representation only; translation is performed by the real TLB.
  typedef struct packed {
    logic [9:0] reserved;
    logic [CVA6Cfg.PPNW-1:0] ppn;
    logic [1:0] rsw;
    logic d, a, g, u, x, w, r, v;
  } refill_pte_t;
  typedef struct packed {
    logic valid;
    logic [CVA6Cfg.PtLevels-2:0][0:0] is_page;
    logic [CVA6Cfg.VpnLen-1:0] vpn;
    logic [CVA6Cfg.ASID_WIDTH-1:0] asid;
    logic [CVA6Cfg.VMID_WIDTH-1:0] vmid;
    logic [0:0] v_st_enbl;
    refill_pte_t content, g_content;
  } refill_t;

  logic clk = 0, rst_n = 0, flush_tlb = 0, req = 0, translate = 0;
  logic [CVA6Cfg.VLEN-1:0] va = 0;
  logic [CVA6Cfg.ASID_WIDTH-1:0] asid = 0;
  logic hit, valid;
  logic [CVA6Cfg.PPNW-1:0] early_ppn;
  logic [CVA6Cfg.PLEN-1:0] pa;
  exception_t ex;
  dcache_req_i_t ptw_req, load_req;
  refill_t refill;
  always #5 clk = ~clk;

  cva6_mmu #(
    .CVA6Cfg(CVA6Cfg), .HYP_EXT(0), .exception_t(exception_t),
    .icache_areq_t(icache_areq_t), .icache_arsp_t(icache_arsp_t),
    .icache_dreq_t(icache_dreq_t), .icache_drsp_t(icache_drsp_t),
    .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(1'b0),
    .enable_translation_i(1'b0), .enable_g_translation_i(1'b0),
    .en_ld_st_translation_i(translate), .en_ld_st_g_translation_i(1'b0),
    .icache_areq_i('0), .icache_areq_o(), .misaligned_ex_i('0),
    .lsu_req_i(req), .lsu_vaddr_i(va), .lsu_tinst_i('0), .lsu_is_store_i(1'b0),
    .csr_hs_ld_st_inst_o(), .lsu_dtlb_hit_o(hit), .lsu_dtlb_ppn_o(early_ppn),
    .lsu_valid_o(valid), .lsu_paddr_o(pa), .lsu_exception_o(ex),
    .priv_lvl_i(riscv::PRIV_LVL_S), .v_i(1'b0),
    .ld_st_priv_lvl_i(riscv::PRIV_LVL_S), .ld_st_v_i(1'b0),
    .sum_i(1'b0), .vs_sum_i(1'b0), .mxr_i(1'b0), .vmxr_i(1'b0),
    .hlvx_inst_i(1'b0), .hs_ld_st_inst_i(1'b0),
    .satp_ppn_i('0), .vsatp_ppn_i('0), .hgatp_ppn_i('0),
    .asid_i(asid), .vs_asid_i('0), .asid_to_be_flushed_i('0),
    .vmid_i('0), .vmid_to_be_flushed_i('0), .vaddr_to_be_flushed_i('0),
    .gpaddr_to_be_flushed_i('0), .flush_tlb_i(flush_tlb),
    .flush_tlb_vvma_i(1'b0), .flush_tlb_gvma_i(1'b0),
    .itlb_miss_o(), .dtlb_miss_o(), .req_port_i('0), .req_port_o(ptw_req),
    .pmpcfg_i('0), .pmpaddr_i('0)
  );

  // Observe the actual consumer's NI classification, without issuing cache work.
  load_unit #(
    .CVA6Cfg(CVA6Cfg), .exception_t(exception_t), .lsu_ctrl_t(lsu_ctrl_t),
    .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t)
  ) consumer (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(1'b0), .valid_i(1'b0), .lsu_ctrl_i('0),
    .pop_ld_o(), .valid_o(), .trans_id_o(), .result_o(), .ex_o(),
    .translation_req_o(), .vaddr_o(), .tinst_o(), .hs_ld_st_inst_o(), .hlvx_inst_o(),
    .paddr_i(pa), .ex_i(ex), .dtlb_hit_i(hit), .dtlb_ppn_i(early_ppn),
    .page_offset_o(), .page_offset_matches_i(1'b0), .store_buffer_empty_i(1'b1),
    .commit_tran_id_i('0), .req_port_i('0), .req_port_o(load_req),
    .dcache_wbuffer_not_ni_i(1'b1)
  );

  function automatic longint unsigned expected_pa(int mode, longint unsigned vaddr,
                                                  longint unsigned ppn);
    longint unsigned bytes_per_page;
    if (mode < 0) return vaddr % (64'd1 << CVA6Cfg.PLEN);
    bytes_per_page = 4096;
    repeat (mode) bytes_per_page *= 512;
    return (ppn * 4096 / bytes_per_page) * bytes_per_page + vaddr % bytes_per_page;
  endfunction
  function automatic bit expected_ni(longint unsigned addr);
    return (addr >= 64'hc0000000 && addr < 64'hc0001000) ||
           (addr >= 64'hd0000000 && addr < 64'hd0001000);
  endfunction

  task automatic install(int mode, int tag, longint unsigned vaddr, longint unsigned ppn);
    if (mode >= 0) begin
      @(negedge clk);
      req = 0;
      translate = 1;
      asid = CVA6Cfg.ASID_WIDTH'(tag);
      va = vaddr;
      refill = '0;
      refill.valid = 1;
      refill.v_st_enbl = '1;
      refill.vpn = CVA6Cfg.VpnLen'(vaddr / 4096);
      refill.asid = CVA6Cfg.ASID_WIDTH'(tag);
      if (mode == 1) refill.is_page[1][0] = 1;
      if (mode == 2) refill.is_page[0][0] = 1;
      refill.content.ppn = CVA6Cfg.PPNW'(ppn);
      refill.content.v = 1;
      refill.content.r = 1;
      refill.content.w = 1;
      refill.content.x = 1;
      refill.content.a = 1;
      refill.content.d = 1;
      // Only the PTW->DTLB refill port is injected for one sampling edge.
      force dut.update_dtlb = refill;
      @(posedge clk); #1;
      @(negedge clk);
      release dut.update_dtlb;
      refill = '0;
      // Real replacement state advances on an access, not on a refill. Touch
      // the installed entry so the next refill cannot replace the same slot.
      req = 1;
      #1;
      if (hit !== 1'b1) $fatal(1, "Refill did not install a real DTLB hit");
      @(posedge clk); #1;
      @(negedge clk); req = 0;
    end
  endtask

  int checks = 0, errors = 0, count = 0;
  task automatic check_value(string kind, logic [63:0] got, logic [63:0] expected);
    checks++;
    if (got !== expected) begin
      errors++;
      if (errors <= 8)
        $display("MISMATCH id=%0d kind=%s got=%016h expected=%016h time=%0t",
                 count, kind, got, expected, $time);
    end
  endtask

  initial begin : stimulus
    string case_path;
    int f, trace, rc, id, prev_mode, mode;
    longint unsigned vaddr, ppn, prev_va, prev_ppn, wanted, prev_wanted;
    longint unsigned page_bytes;
    logic [63:0] sampled_ppn, sampled_hit, sampled_ni, old_page, current_page;
    logic [63:0] measured_prev_pa, measured_prev_valid, measured_prev_exception;
    if (CVA6Cfg.RVH || CVA6Cfg.PtLevels != 3 || CVA6Cfg.PPNW != 44)
      $fatal(1, "Unsupported fixture configuration");
    if ($bits(refill) != $bits(dut.update_dtlb)) $fatal(1, "Refill type mismatch");
    if (!$value$plusargs("CASES=%s", case_path)) $fatal(1, "Missing CASES");
    f = $fopen(case_path, "r");
    trace = $fopen("observed.tsv", "w");
    if (!f || !trace) $fatal(1, "Cannot open evidence files");
    $fdisplay(trace, "id prev mode va ppn old_page current_page hit early ni valid pa exception prev_pa prev_valid prev_exception");
    refill = '0;
    repeat (3) @(posedge clk);
    @(negedge clk); rst_n = 1;
    while (!$feof(f)) begin
      rc = $fscanf(f, "%d %d %d %h %h\n", id, prev_mode, mode, vaddr, ppn);
      if (rc != 5) $fatal(1, "Malformed case row");
      if (id != count) $fatal(1, "Noncontiguous case id");
      if (mode < -1 || mode > 2 || prev_mode < -1 || prev_mode > 2)
        $fatal(1, "Invalid page mode");
      page_bytes = 4096;
      repeat (mode > 0 ? mode : 0) page_bytes *= 512;
      if (ppn >= (64'd1 << CVA6Cfg.PPNW) || (ppn * 4096) % page_bytes != 0)
        $fatal(1, "Illegal or misaligned PTE PPN");
      @(negedge clk); req = 0; translate = 0; flush_tlb = 1;
      @(posedge clk); #1;
      check_value("IDLE_VALID", valid, 0);
      check_value("IDLE_EXCEPTION", ex.valid, 0);
      @(negedge clk); flush_tlb = 0;
      // Disjoint VPN2 also avoids a bypass-mode internal multi-hit: with
      // translation off the real TLB ignores ASID when matching its tags.
      prev_va = 64'h1552345080;
      prev_ppn = 64'h80000;
      install(prev_mode, 1, prev_va, prev_ppn);
      install(mode, 2, vaddr, ppn);
      @(negedge clk); req = 1; translate = (prev_mode >= 0); asid = 1; va = prev_va;
      @(posedge clk); #1;
      prev_wanted = expected_pa(prev_mode, prev_va, prev_ppn);
      check_value("PREV_VALID", valid, 1);
      check_value("PREV_EXCEPTION", ex.valid, 0);
      check_value("PREV_PA", pa, prev_wanted);
      measured_prev_pa = pa;
      measured_prev_valid = valid;
      measured_prev_exception = ex.valid;
      // The new address arrives between edges. The registered page size still
      // describes the preceding request, but the lookup describes this request.
      @(negedge clk); translate = (mode >= 0); asid = 2; va = vaddr;
      #1;
      old_page = dut.dtlb_is_page_q;
      current_page = dut.dtlb_is_page;
      sampled_ppn = early_ppn;
      sampled_hit = hit;
      sampled_ni = consumer.paddr_ni;
      wanted = expected_pa(mode, vaddr, ppn);
      check_value("HIT", hit, 1);
      check_value("EARLY_PPN", early_ppn, wanted / 4096);
      check_value("NI_REGION", consumer.paddr_ni, expected_ni(wanted));
      @(posedge clk); #1;
      check_value("NEXT_VALID", valid, 1);
      check_value("NEXT_EXCEPTION", ex.valid, 0);
      check_value("NEXT_PA", pa, wanted);
      $fdisplay(trace, "%0d %0d %0d %016h %016h %h %h %h %h %h %h %h %h %h %h %h",
        count, prev_mode, mode, vaddr, ppn, old_page, current_page,
        sampled_hit, sampled_ppn, sampled_ni, 64'(valid), 64'(pa), 64'(ex.valid),
        measured_prev_pa, measured_prev_valid, measured_prev_exception);
      count++;
    end
    if (count == 0) $fatal(1, "Empty stimulus is not an experiment");
    @(negedge clk); req = 0;
    @(posedge clk); #1;
    check_value("DRAIN_VALID", valid, 0);
    check_value("DRAIN_EXCEPTION", ex.valid, 0);
    $fclose(f); $fclose(trace);
    $display("MMU_EARLY_PPN_COMPLETE cases=%0d checks=%0d errors=%0d", count, checks, errors);
    if (errors) $fatal(1, "EARLY_PPN_TEST_FAILED");
    $finish;
  end
  initial begin
    #2000000;
    $fatal(1, "MMU fixture cycle watchdog");
  end
endmodule
