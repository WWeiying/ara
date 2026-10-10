`timescale 1ns/1ps
module upstream_20261009_mmu_tb;
  `include "upstream_20261009_common.svh"
  logic req = 0, store = 0, flush = 0;
  logic [63:0] va = 0;
  logic hit, valid;
  logic [CVA6Cfg.PPNW-1:0] early_ppn;
  logic [CVA6Cfg.PLEN-1:0] pa;
  exception_t ex;
  refill_t refill;
  cva6_mmu #(.CVA6Cfg(CVA6Cfg), .HYP_EXT(0), .exception_t(exception_t),
    .icache_areq_t(icache_areq_t), .icache_arsp_t(icache_arsp_t),
    .icache_dreq_t(icache_dreq_t), .icache_drsp_t(icache_drsp_t),
    .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(1'b0),
    .enable_translation_i(1'b0), .enable_g_translation_i(1'b0),
    .en_ld_st_translation_i(1'b1), .en_ld_st_g_translation_i(1'b0),
    .icache_areq_i('0), .icache_areq_o(), .misaligned_ex_i('0),
    .lsu_req_i(req), .lsu_vaddr_i(va), .lsu_tinst_i('0), .lsu_is_store_i(store),
    .csr_hs_ld_st_inst_o(), .lsu_dtlb_hit_o(hit), .lsu_dtlb_ppn_o(early_ppn),
    .lsu_valid_o(valid), .lsu_paddr_o(pa), .lsu_exception_o(ex),
    .priv_lvl_i(riscv::PRIV_LVL_S), .v_i(1'b0),
    .ld_st_priv_lvl_i(riscv::PRIV_LVL_S), .ld_st_v_i(1'b0),
    .sum_i(1'b0), .vs_sum_i(1'b0), .mxr_i(1'b0), .vmxr_i(1'b0),
    .hlvx_inst_i(1'b0), .hs_ld_st_inst_i(1'b0),
    .satp_ppn_i('0), .vsatp_ppn_i('0), .hgatp_ppn_i('0),
    .asid_i('0), .vs_asid_i('0), .asid_to_be_flushed_i('0),
    .vmid_i('0), .vmid_to_be_flushed_i('0), .vaddr_to_be_flushed_i('0),
    .gpaddr_to_be_flushed_i('0), .flush_tlb_i(flush),
    .flush_tlb_vvma_i(1'b0), .flush_tlb_gvma_i(1'b0),
    .itlb_miss_o(), .dtlb_miss_o(), .req_port_i('0), .req_port_o(),
    .pmpcfg_i('0), .pmpaddr_i('0));
  initial begin
    int rc, a_req, b_req, a_bad, b_bad, a_store, negative, mode;
    logic [63:0] a_va, b_va, base;
    open_files(); refill = '0;
    while (!$feof(input_file)) begin
      rc = $fscanf(input_file, "%d %d %d %d %d %d %d %d\n",
        id, a_req, b_req, a_bad, b_bad, a_store, negative, mode);
      if (rc != 8 || id != completed) $fatal(1, "Bad MMU case");
      req = 0; reset_dut();
      base = negative ? 64'hffffffc012345088 : 64'h12345088;
      a_va = base ^ (a_bad ? (64'd1 << 39) : 64'd0);
      b_va = (base + 8) ^ (b_bad ? (64'd1 << 39) : 64'd0);
      va = base; refill = '0; refill.valid = 1; refill.v_st_enbl = 1;
      refill.vpn = CVA6Cfg.VpnLen'(base >> 12);
      if (mode == 1) refill.is_page[1][0] = 1;
      if (mode == 2) refill.is_page[0][0] = 1;
      refill.content.ppn = 44'h80000;
      refill.content.v = 1; refill.content.r = 1; refill.content.w = 1;
      refill.content.x = 1; refill.content.a = 1; refill.content.d = 1;
      // Inject only a legal refill. No result, exception, or hit is forced.
      force dut.update_dtlb = refill;
      @(posedge clk); #1;
      @(negedge clk); release dut.update_dtlb; refill = '0;
      va = a_va; req = a_req; store = a_store;
      #1; observe("a_hit", hit);
      @(posedge clk); #1;
      // Change current request while the registered response still belongs to A.
      @(negedge clk); va = b_va; req = b_req; store = !a_store;
      #1;
      observe("a_valid", valid); observe("a_pa", pa);
      observe("a_exception", ex.valid);
      if (ex.valid) begin observe("a_cause", ex.cause); observe("a_tval", ex.tval); end
      else begin observe("a_cause", 0); observe("a_tval", 0); end
      observe("b_hit", hit); observe("b_early_ppn", early_ppn);
      @(posedge clk); #1;
      observe("b_valid", valid); observe("b_pa", pa);
      observe("b_exception", ex.valid);
      if (ex.valid) begin observe("b_cause", ex.cause); observe("b_tval", ex.tval); end
      else begin observe("b_cause", 0); observe("b_tval", 0); end
      @(negedge clk); req = 0;
      @(posedge clk); #1;
      observe("drain_valid", valid); observe("drain_exception", ex.valid);
      completed++;
    end
    finish_test();
  end
endmodule
