`timescale 1ns/1ps
// Force the ITLB result boundary only. This does not reproduce lookup/PTW.
module loader_ifetch_mapped_tb;
  logic [63:0] va;
  logic [43:0] ppn;
  logic user_page = 1;
  logic hit = 1;
  wire [55:0] pa;
  wire valid, exception_valid;
  int checks = 0;
  cva6_mmu dut (
    .clk_i(1'b0), .rst_ni(1'b1),
    .enable_translation_i(1'b1), .enable_g_translation_i(1'b0),
    .priv_lvl_i(2'b00),
    .\icache_areq_i[fetch_req] (1'b1),
    .\icache_areq_i[fetch_vaddr] (va),
    .\icache_areq_o[fetch_paddr] (pa),
    .\icache_areq_o[fetch_valid] (valid),
    .\icache_areq_o[fetch_exception][valid] (exception_valid)
  );
  task automatic check(input logic [55:0] expected,
                       input logic expected_valid, expected_exception);
    #1;
    // Export ties unused [11:0] to zero. ICache supplies its saved VA offset.
    if (pa[55:12] !== expected[55:12] || valid !== expected_valid ||
        exception_valid !== expected_exception)
      $fatal(1,"IFETCH va=%h pa=%h expected=%h valid=%b exception=%b",
             va, pa, expected, valid, exception_valid);
    checks++;
  endtask
  initial begin
    force dut.\itlb_content[ppn] = ppn;
    force dut.\itlb_content[u] = user_page;
    force dut.itlb_is_page = 2'b00;
    force dut.itlb_lu_hit = hit;
    force dut.ptw_active = 1'b0;
    #201;
    va=64'h3f93ee6b4a; ppn=44'h8016a;
    check(56'h8016ab4a,1,0);
    va=64'h3f93ee20dc; ppn=44'h80166;
    check(56'h801660dc,1,0);
    va=64'h3f93ee2104;
    check(56'h80166104,1,0);
    // Permission fault and miss must not masquerade as a successful hit.
    user_page=0; check(56'h80166104,1,1);
    user_page=1; hit=0; check(56'h80166104,0,0);
    hit=1; check(56'h80166104,1,0);
    $display("LOADER_IFETCH_MAPPED_PASS checks=%0d scope=itlb_result_boundary_only",checks);
    $finish;
  end
endmodule
