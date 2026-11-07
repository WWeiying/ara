`timescale 1ns/1ps
module mmu_mxr_hit_tb;
  import ariane_pkg::*;
  function automatic config_pkg::cva6_cfg_t configuration();
    config_pkg::cva6_cfg_t c;
    c = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
    c.NrPMPEntries = 0;
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg = configuration();
  `include "mmu_mxr_hit_types.svh"

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

  localparam logic [63:0] ReadVA = 64'h40000108;
  localparam logic [63:0] ExecVA = 64'h40001108;
  localparam logic [63:0] ReadPA = 64'h80010108;
  localparam logic [63:0] ExecPA = 64'h80020108;
  logic clk = 0, rst_n = 0, req = 0, mxr = 0;
  logic [CVA6Cfg.VLEN-1:0] va = 0;
  logic hit, valid;
  logic [CVA6Cfg.PPNW-1:0] early_ppn;
  logic [CVA6Cfg.PLEN-1:0] pa;
  exception_t ex;
  dcache_req_i_t ptw_req;
  refill_t refill;
  int checks = 0, errors = 0, cases = 0, refills = 0;
  logic [31:0] ptw_requests;
  always #5 clk = ~clk;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) ptw_requests <= 0;
    else if (ptw_req.data_req) ptw_requests <= ptw_requests + 1;
  end

  cva6_mmu #(
    .CVA6Cfg(CVA6Cfg), .HYP_EXT(0), .exception_t(exception_t),
    .icache_areq_t(icache_areq_t), .icache_arsp_t(icache_arsp_t),
    .icache_dreq_t(icache_dreq_t), .icache_drsp_t(icache_drsp_t),
    .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(1'b0),
    .enable_translation_i(1'b0), .enable_g_translation_i(1'b0),
    .en_ld_st_translation_i(1'b1), .en_ld_st_g_translation_i(1'b0),
    .icache_areq_i('0), .icache_areq_o(), .misaligned_ex_i('0),
    .lsu_req_i(req), .lsu_vaddr_i(va), .lsu_tinst_i('0), .lsu_is_store_i(1'b0),
    .csr_hs_ld_st_inst_o(), .lsu_dtlb_hit_o(hit), .lsu_dtlb_ppn_o(early_ppn),
    .lsu_valid_o(valid), .lsu_paddr_o(pa), .lsu_exception_o(ex),
    .priv_lvl_i(riscv::PRIV_LVL_S), .v_i(1'b0),
    .ld_st_priv_lvl_i(riscv::PRIV_LVL_S), .ld_st_v_i(1'b0),
    .sum_i(1'b0), .vs_sum_i(1'b0), .mxr_i(mxr), .vmxr_i(1'b0),
    .hlvx_inst_i(1'b0), .hs_ld_st_inst_i(1'b0),
    .satp_ppn_i('0), .vsatp_ppn_i('0), .hgatp_ppn_i('0),
    .asid_i(CVA6Cfg.ASID_WIDTH'(7)), .vs_asid_i('0), .asid_to_be_flushed_i('0),
    .vmid_i('0), .vmid_to_be_flushed_i('0), .vaddr_to_be_flushed_i('0),
    .gpaddr_to_be_flushed_i('0), .flush_tlb_i(1'b0),
    .flush_tlb_vvma_i(1'b0), .flush_tlb_gvma_i(1'b0),
    .itlb_miss_o(), .dtlb_miss_o(), .req_port_i('0), .req_port_o(ptw_req),
    .pmpcfg_i('0), .pmpaddr_i('0)
  );

  function automatic refill_pte_t pte(logic [63:0] physical, bit readable);
    refill_pte_t value;
    value = '0;
    value.ppn = CVA6Cfg.PPNW'(physical >> 12);
    value.v = 1;
    value.a = 1;
    value.r = readable;
    value.x = !readable;
    return value;
  endfunction

  task automatic install(logic [63:0] address, logic [63:0] physical, bit readable);
    @(negedge clk);
    req = 0;
    va = address;
    refill = '0;
    refill.valid = 1;
    refill.v_st_enbl = '1;
    refill.vpn = CVA6Cfg.VpnLen'(address >> 12);
    refill.asid = CVA6Cfg.ASID_WIDTH'(7);
    refill.content = pte(physical, readable);
    // Only inject the refill input; lookup and registered permissions are real.
    force dut.update_dtlb = refill;
    @(posedge clk); #1;
    @(negedge clk);
    release dut.update_dtlb;
    refill = '0;
    refills++;
  endtask

  task automatic check_value(string field, logic [63:0] got, logic [63:0] expected);
    checks++;
    if (got !== expected) begin
      errors++;
      $display("MMU_MXR_MISMATCH case=%0d field=%s got=%016h expected=%016h",
               cases, field, got, expected);
    end
  endtask

  task automatic probe(logic [63:0] address, logic [63:0] physical,
                       bit readable, bit allow_execute_read, bit wanted_fault);
    logic sampled_hit;
    @(negedge clk);
    va = address;
    mxr = allow_execute_read;
    req = 1;
    #1;
    sampled_hit = hit;
    check_value("LOOKUP_HIT", hit, 1);
    @(posedge clk); #1;
    check_value("LATCHED_HIT", dut.dtlb_hit_q, 1);
    check_value("LATCHED_REQ", dut.lsu_req_q, 1);
    check_value("LATCHED_PTE", dut.dtlb_pte_q, pte(physical, readable));
    check_value("IS_STORE", dut.lsu_is_store_q, 0);
    check_value("VALID", valid, 1);
    check_value("PA", pa, physical);
    check_value("EXCEPTION", ex.valid, wanted_fault);
    check_value("CAUSE", ex.cause, wanted_fault ? 13 : 0);
    check_value("TVAL", ex.tval, wanted_fault ? address : 0);
    $display("MMU_MXR_HIT_OBS case=%0d mxr=%0d hit=%0d latched_hit=%0d req=%0d valid=%0d is_store=%0d va=%016h pa=%016h pte=%016h exc=%0d cause=%0d tval=%016h refills=%0d flush=%0d",
             cases, dut.mxr_i, sampled_hit, dut.dtlb_hit_q, dut.lsu_req_q, valid,
             dut.lsu_is_store_q, dut.lsu_vaddr_q, pa, dut.dtlb_pte_q,
             ex.valid, ex.cause, ex.tval, refills, dut.flush_tlb_i);
    cases++;
    @(negedge clk); req = 0;
    @(posedge clk); #1;
  endtask

  initial begin
    if (CVA6Cfg.RVH || CVA6Cfg.NrPMPEntries != 0 || CVA6Cfg.PtLevels != 3 ||
        CVA6Cfg.PPNW != 44 || CVA6Cfg.UseSharedTlb || !CVA6Cfg.MmuPresent || !CVA6Cfg.TvalEn)
      $fatal(1, "MXR_FIXTURE_CONFIGURATION");
    if ($bits(refill) != $bits(dut.update_dtlb)) $fatal(1, "MXR_REFILL_TYPE");
    $display("MMU_MXR_HIT_SCOPE pmp=0 rvh=0 sv=39 refill_only=1 cold_ptw=0 cases=5");
    refill = '0;
    repeat (3) @(posedge clk);
    @(negedge clk); rst_n = 1;
    install(ReadVA, ReadPA, 1);
    probe(ReadVA, ReadPA, 1, 0, 0);
    probe(ReadVA, ReadPA, 1, 1, 0);
    install(ExecVA, ExecPA, 0);
    probe(ExecVA, ExecPA, 0, 1, 0);
    probe(ExecVA, ExecPA, 0, 0, 1);
    probe(ExecVA, ExecPA, 0, 1, 0);
    @(posedge clk); #1;
    check_value("DRAIN_VALID", valid, 0);
    check_value("PTW_REQUESTS", ptw_requests, 0);
    $display("MMU_MXR_HIT_COMPLETE cases=%0d checks=%0d errors=%0d refills=%0d ptw_requests=%0d",
             cases, checks, errors, refills, ptw_requests);
    if (errors) $fatal(1, "MXR_HIT_CONTRACT_FAILED");
    $finish;
  end
  initial begin
    #10000;
    $fatal(1, "MXR_HIT_WATCHDOG");
  end
endmodule
