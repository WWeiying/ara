`timescale 1ns/1ps
// Real MMU netlist, no internal force. External cache replies use captured PTEs.
// Cache state, ASID and response latency are controlled, not measured on board.
module loader_ptw_mapped_tb;
  logic clk=0, rst=0, fetch=0;
  logic [63:0] va=0;
  wire valid, ex_valid;
  wire [55:0] pa;
  wire mem_req;
  wire [10:0] idx;
  wire [44:0] tag_addr;
  logic rvalid=0;
  logic [63:0] rdata=0, pending_data=0;
  int ticks=0, pending=0, requests=0, checks=0;
  wire grant = mem_req && pending==0 && (ticks%3 != 0);
  always #5 clk=~clk;
  cva6_mmu dut (
    .clk_i(clk), .rst_ni(rst), .flush_i(1'b0),
    .enable_translation_i(1'b1), .enable_g_translation_i(1'b0),
    .en_ld_st_translation_i(1'b1), .en_ld_st_g_translation_i(1'b0),
    .\icache_areq_i[fetch_req] (fetch),
    .\icache_areq_i[fetch_vaddr] (va),
    .\icache_areq_o[fetch_paddr] (pa),
    .\icache_areq_o[fetch_valid] (valid),
    .\icache_areq_o[fetch_exception][valid] (ex_valid),
    .\misaligned_ex_i[valid] (1'b0),
    .\misaligned_ex_i[cause] (64'b0),
    .\misaligned_ex_i[tval] (64'b0),
    .\misaligned_ex_i[tval2] (41'b0),
    .\misaligned_ex_i[tinst] (32'b0),
    .\misaligned_ex_i[gva] (1'b0),
    .lsu_req_i(1'b0), .lsu_vaddr_i(64'b0), .lsu_tinst_i(32'b0),
    .lsu_is_store_i(1'b0), .priv_lvl_i(2'b00), .v_i(1'b0),
    .ld_st_priv_lvl_i(2'b00), .ld_st_v_i(1'b0), .sum_i(1'b0),
    .vs_sum_i(1'b0), .mxr_i(1'b0), .vmxr_i(1'b0),
    .hlvx_inst_i(1'b0), .hs_ld_st_inst_i(1'b0),
    .satp_ppn_i(44'h82859), .vsatp_ppn_i(44'b0), .hgatp_ppn_i(44'b0),
    .asid_i(16'd1), .vs_asid_i(16'b0), .asid_to_be_flushed_i(16'b0),
    .vmid_i(14'b0), .vmid_to_be_flushed_i(14'b0),
    .vaddr_to_be_flushed_i(64'b0), .gpaddr_to_be_flushed_i(41'b0),
    .flush_tlb_i(1'b0), .flush_tlb_vvma_i(1'b0), .flush_tlb_gvma_i(1'b0),
    .\req_port_i[data_gnt] (grant), .\req_port_i[data_rvalid] (rvalid),
    .\req_port_i[data_rdata] (rdata), .\req_port_i[data_rid] (1'b0),
    .\req_port_i[data_ruser] (2'b0), .\req_port_o[data_req] (mem_req),
    .\req_port_o[address_index] (idx), .\req_port_o[address_tag] (tag_addr),
    .\pmpcfg_i[0][locked] (1'b0), .\pmpcfg_i[0][reserved] (2'b0),
    .\pmpcfg_i[0][addr_mode] (2'b11),
    .\pmpcfg_i[0][access_type][x] (1'b1),
    .\pmpcfg_i[0][access_type][w] (1'b1),
    .\pmpcfg_i[0][access_type][r] (1'b1), .\pmpaddr_i[0] (54'h3fffffffffffff)
  );
  function automatic logic[63:0] pte(input logic[55:0] addr);
    case(addr)
      56'h828597f0: return 64'h20b94801;
      56'h82e524f8: return 64'h20b7f401;
      56'h82dfd730: return 64'h2005a85b;
      56'h82dfd710: return 64'h2005985b;
      default: begin
        $fatal(1,"Uncaptured PTE address %h",addr);
        return 0;
      end
    endcase
  endfunction
  always @(posedge clk) begin
    ticks <= ticks+1;
    rvalid <= 0;
    if (pending>0) begin
      pending <= pending-1;
      if(pending==1) begin rvalid<=1; rdata<=pending_data; end
    end
    if(rst && grant) begin
      pending_data <= pte({tag_addr,idx});
      pending <= 3;
      requests <= requests+1;
      $display("PTE_REQUEST cycle=%0d addr=%h",ticks,{tag_addr,idx});
    end
  end
  task automatic translate(input logic[63:0] address,
                           input logic[43:0] expected_ppn,
                           input int expected_reads);
    int start_reads;
    @(negedge clk); va=address; fetch=1; start_reads=requests;
    for(int i=0;i<120;i++) begin
      // Sample the response at the accepting edge, before NBA TLB updates.
      // Sampling after NBA and dropping fetch before the next edge would
      // skip the real request's hit/PLRU handshake.
      @(posedge clk);
      if(valid===1'b1) begin
        if(ex_valid!==0 || pa[55:12]!==expected_ppn)
          $fatal(1,"Translation mismatch va=%h pa=%h ex=%b",va,pa,ex_valid);
        if(requests-start_reads != expected_reads)
          $fatal(1,"Unexpected walk count: %0d",requests-start_reads);
        $display("TRANSLATION va=%h ppn=%h cycles=%0d reads=%0d",
                 va,pa[55:12],i+1,requests-start_reads);
        checks++;
        @(negedge clk); fetch=0;
        repeat(4) @(negedge clk);
        return;
      end
    end
    $fatal(1,"Translation stuck va=%h requests=%0d",va,requests-start_reads);
  endtask
  initial begin
    #220; @(negedge clk); rst=1;
    translate(64'h3f93ee6b4a,44'h8016a,3);
    translate(64'h3f93ee20dc,44'h80166,3);
    translate(64'h3f93ee2104,44'h80166,0);
    translate(64'h3f93ee6b4e,44'h8016a,0);
    $display("LOADER_PTW_MAPPED_PASS checks=%0d no_internal_force=1",checks);
    $finish;
  end
endmodule
