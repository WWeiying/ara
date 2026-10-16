`timescale 1ns/1ps
// Real exported MMU netlist; force only the TLB response boundary.
// This tests address composition, not lookup/PTW or Linux execution.
module mmu_ppn_mapped_tb;
  logic [63:0] va;
  logic [43:0] pte;
  logic [1:0] page, previous_page;
  logic translated=1;
  wire [43:0] ppn;
  int checks=0;
  cva6_mmu dut (
    .clk_i(1'b0), .rst_ni(1'b1),
    .en_ld_st_translation_i(translated), .en_ld_st_g_translation_i(1'b0),
    .lsu_vaddr_i(va), .lsu_dtlb_ppn_o(ppn)
  );
  task automatic check_ppn(input logic [43:0] expected);
    #1;
    if (ppn !== expected)
      $fatal(1,"PPN va=%h page=%b previous=%b pte=%h actual=%h expected=%h",
             va,page,previous_page,pte,ppn,expected);
    checks++;
  endtask
  initial begin
    force dut.\dtlb_content[ppn] = pte;
    force dut.dtlb_is_page = page;
    force dut.dtlb_is_page_q = previous_page;
    force dut.\misaligned_ex_q_reg[valid_n_0_] = 1'b0;
    #201;
    page=2; previous_page=0; pte=44'h82800;
    va=64'hffffffd602803b80; check_ppn(44'h82803);
    va=64'hffffffd602804780; check_ppn(44'h82804);
    for(int size=0; size<3; size++) begin
      for(int previous=0; previous<3; previous++) begin
        for(int offset=0; offset<256; offset++) begin
          page=size; previous_page=previous;
          va=64'hffffffd600000000 | (64'(offset*104729)&64'h3fffffff);
          pte=44'h80000;
          case(size)
            0: check_ppn(pte);
            1: check_ppn(pte | ((va>>12)&44'h3ffff));
            2: check_ppn(pte | ((va>>12)&44'h1ff));
          endcase
        end
      end
    end
    // Every PTE bit must be preserved on a 4K translation.
    page=0;
    for(int bit_idx=0; bit_idx<44; bit_idx++) begin
      pte=44'b1<<bit_idx;
      check_ppn(pte);
    end
    translated=0; va=64'h82804780; check_ppn(44'h82804);
    $display("MMU_PPN_MAPPED_PASS checks=%0d scope=composition_not_ptw",checks);
    $finish;
  end
endmodule
