// Reproduce the Linux vector-restore fault with actual addrgen and MMU RTL.
// Only the DTLB hit/PTE is controlled; address-generation and fault logic are real.
`include "axi/typedef.svh"
`include "ara/intf_typedef.svh"
package probe_pkg;
  import ara_pkg::*;
  import rvv_pkg::*;
  localparam config_pkg::cva6_cfg_t Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef logic [10:0] vlen_t;
  `CVA6_TYPEDEF_EXCEPTION(exception_t, Cfg)
  `include "ara/ara_typedef.svh"
  typedef struct packed {logic fetch_req; logic [63:0] fetch_vaddr;} if_in_t;
  typedef struct packed {logic fetch_valid; logic [Cfg.PLEN-1:0] fetch_paddr; exception_t fetch_exception;} if_out_t;
  typedef struct packed {
    logic [Cfg.DCACHE_INDEX_WIDTH-1:0] address_index;
    logic [Cfg.DCACHE_TAG_WIDTH-1:0] address_tag;
    logic kill_req, tag_valid, data_req, data_we;
    logic [63:0] data_wdata;
    logic [7:0] data_be;
    logic [2:0] data_size;
    logic [3:0] data_id;
  } dc_req_t;
  typedef struct packed {logic data_gnt, data_rvalid; logic [63:0] data_rdata; logic [3:0] data_rid;} dc_rsp_t;
endpackage

module canonical_case #(
  parameter int Width=48,
  parameter bit OldMmu=0,
  parameter bit High=1
) (output logic done=0);
  import ara_pkg::*;
  import rvv_pkg::*;
  import probe_pkg::*;
  `AXI_TYPEDEF_ALL(bus, logic[Width-1:0], logic[4:0], logic[127:0], logic[15:0], logic[1:0])
  logic clk=0, rst=0, valid=0;
  always #5 clk=~clk;
  pe_req_t req;
  logic mmu_req, mmu_valid, hit, is_store;
  logic [63:0] va;
  logic [Cfg.PLEN-1:0] pa;
  logic [Cfg.PPNW-1:0] ppn;
  exception_t ex, addr_ex;
  logic ack, arvalid, awvalid;
  bus_ar_chan_t ar;
  bus_aw_chan_t aw;
  addrgen_axi_req_t descriptor;
  logic descriptor_valid;
  logic [63:0] input_address;
  int cycles=0, requests=0;
  bit saw_bad_va=0, saw_ex=0, saw_ar=0;
  addrgen #(.NrLanes(4), .VLEN(1024), .AxiDataWidth(128), .AxiAddrWidth(Width),
    .axi_ar_t(bus_ar_chan_t), .axi_aw_t(bus_aw_chan_t), .pe_req_t(pe_req_t),
    .pe_resp_t(pe_resp_t), .CVA6Cfg(Cfg), .exception_t(exception_t)) ag (
    .clk_i(clk), .rst_ni(rst), .axi_ar_o(ar), .axi_ar_valid_o(arvalid), .axi_ar_ready_i(1'b1),
    .axi_aw_o(aw), .axi_aw_valid_o(awvalid), .axi_aw_ready_i(1'b1),
    .en_ld_st_translation_i(1'b1), .mmu_req_o(mmu_req), .mmu_vaddr_o(va),
    .mmu_is_store_o(is_store), .mmu_dtlb_hit_i(hit), .mmu_dtlb_ppn_i(ppn),
    .mmu_valid_i(mmu_valid), .mmu_paddr_i(pa), .mmu_exception_i(ex),
    .core_st_pending_i(1'b0), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('0), .addrgen_exception_o(addr_ex), .addrgen_ack_o(ack),
    .axi_addrgen_req_o(descriptor), .axi_addrgen_req_valid_o(descriptor_valid),
    .ldu_axi_addrgen_req_ready_i(1'b1), .stu_axi_addrgen_req_ready_i(1'b0),
    .ldu_mask_word_i('1), .ldu_mask_word_valid_i('1), .ldu_mask_owner_id_i('0),
    .ldu_mask_first_element_i('0), .stu_mask_word_i('1), .stu_mask_word_valid_i('1),
    .stu_mask_owner_id_i('0), .stu_mask_first_element_i('0), .addrgen_operand_i('0),
    .addrgen_operand_valid_i('0), .lsu_ex_flush_i(1'b0)
  );
  if (OldMmu) begin : old
    old_cva6_mmu #(.CVA6Cfg(Cfg), .icache_areq_t(if_out_t), .icache_arsp_t(if_in_t),
      .dcache_req_i_t(dc_req_t), .dcache_req_o_t(dc_rsp_t), .exception_t(exception_t)) mmu (
      .clk_i(clk), .rst_ni(rst), .flush_i(1'b0), .enable_translation_i(1'b0),
      .enable_g_translation_i(1'b0), .en_ld_st_translation_i(1'b1), .en_ld_st_g_translation_i(1'b0),
      .icache_areq_i('0), .misaligned_ex_i('0), .lsu_req_i(mmu_req), .lsu_vaddr_i(va),
      .lsu_tinst_i('0), .lsu_is_store_i(is_store), .lsu_dtlb_hit_o(hit),
      .lsu_dtlb_ppn_o(ppn), .lsu_valid_o(mmu_valid), .lsu_paddr_o(pa), .lsu_exception_o(ex),
      .priv_lvl_i(riscv::PRIV_LVL_S), .ld_st_priv_lvl_i(riscv::PRIV_LVL_S),
      .v_i(1'b0), .ld_st_v_i(1'b0), .sum_i(1'b0), .vs_sum_i(1'b0),
      .mxr_i(1'b0), .vmxr_i(1'b0), .hlvx_inst_i(1'b0), .hs_ld_st_inst_i(1'b0),
      .satp_ppn_i('0), .vsatp_ppn_i('0), .hgatp_ppn_i('0), .asid_i('0), .vs_asid_i('0),
      .asid_to_be_flushed_i('0), .vmid_i('0), .vmid_to_be_flushed_i('0),
      .vaddr_to_be_flushed_i('0), .gpaddr_to_be_flushed_i('0), .flush_tlb_i(1'b0),
      .flush_tlb_vvma_i(1'b0), .flush_tlb_gvma_i(1'b0), .req_port_i('0), .pmpcfg_i('0), .pmpaddr_i('0)
    );
    initial begin
      force mmu.dtlb_lu_hit=1'b1;
      force mmu.dtlb_content='0;
      force mmu.dtlb_content.ppn=44'h100846;
      force mmu.dtlb_content.r=1;
      force mmu.dtlb_content.w=1;
      force mmu.dtlb_content.v=1;
      force mmu.dtlb_content.a=1;
      force mmu.dtlb_content.d=1;
      force mmu.dtlb_is_page='0;
    end
  end else begin : current
    cva6_mmu #(.CVA6Cfg(Cfg), .icache_areq_t(if_out_t), .icache_arsp_t(if_in_t),
      .dcache_req_i_t(dc_req_t), .dcache_req_o_t(dc_rsp_t), .exception_t(exception_t)) mmu (
      .clk_i(clk), .rst_ni(rst), .flush_i(1'b0), .enable_translation_i(1'b0),
      .enable_g_translation_i(1'b0), .en_ld_st_translation_i(1'b1), .en_ld_st_g_translation_i(1'b0),
      .icache_areq_i('0), .misaligned_ex_i('0), .lsu_req_i(mmu_req), .lsu_vaddr_i(va),
      .lsu_tinst_i('0), .lsu_is_store_i(is_store), .lsu_dtlb_hit_o(hit),
      .lsu_dtlb_ppn_o(ppn), .lsu_valid_o(mmu_valid), .lsu_paddr_o(pa), .lsu_exception_o(ex),
      .priv_lvl_i(riscv::PRIV_LVL_S), .ld_st_priv_lvl_i(riscv::PRIV_LVL_S),
      .v_i(1'b0), .ld_st_v_i(1'b0), .sum_i(1'b0), .vs_sum_i(1'b0),
      .mxr_i(1'b0), .vmxr_i(1'b0), .hlvx_inst_i(1'b0), .hs_ld_st_inst_i(1'b0),
      .satp_ppn_i('0), .vsatp_ppn_i('0), .hgatp_ppn_i('0), .asid_i('0), .vs_asid_i('0),
      .asid_to_be_flushed_i('0), .vmid_i('0), .vmid_to_be_flushed_i('0),
      .vaddr_to_be_flushed_i('0), .gpaddr_to_be_flushed_i('0), .flush_tlb_i(1'b0),
      .flush_tlb_vvma_i(1'b0), .flush_tlb_gvma_i(1'b0), .req_port_i('0), .pmpcfg_i('0), .pmpaddr_i('0)
    );
    initial begin
      force mmu.dtlb_lu_hit=1'b1;
      force mmu.dtlb_content='0;
      force mmu.dtlb_content.ppn=44'h100846;
      force mmu.dtlb_content.r=1;
      force mmu.dtlb_content.w=1;
      force mmu.dtlb_content.v=1;
      force mmu.dtlb_content.a=1;
      force mmu.dtlb_content.d=1;
      force mmu.dtlb_is_page='0;
    end
  end
  always @(negedge clk) if(rst && !done) begin
    cycles++;
    if(mmu_req) begin
      requests++;
      $display("REQ width=%0d old=%0d high=%0d cycle=%0d scalar=%h held=%h mmu=%h",Width,OldMmu,High,cycles,input_address,ag.axi_addrgen_q.addr,va);
      if(High && va==64'h0000ffd680846000) saw_bad_va=1;
      if(Width==64 && va!==input_address) $fatal(1,"Unexpected full-width address");
    end
    if(addr_ex.valid) begin
      saw_ex=1;
      $display("EX width=%0d old=%0d high=%0d cycle=%0d cause=%h tval=%h",Width,OldMmu,High,cycles,addr_ex.cause,addr_ex.tval);
      if(addr_ex.cause != 13 || addr_ex.tval != 64'h0000ffd680846000) $fatal(1,"Different fault from board");
    end
    if(arvalid) begin saw_ar=1; $display("AR width=%0d old=%0d high=%0d addr=%h",Width,OldMmu,High,ar.addr); end
  end
  initial begin
    input_address=High?64'hffffffd680846000:64'h0000000080846000;
    req='0;
    repeat(3) @(posedge clk);
    @(negedge clk); rst=1;
    @(negedge clk);
    req.op=VLE; req.vm=1; req.vfu=VFU_LoadUnit; req.vl=128;
    req.scalar_op=input_address; req.vtype.vsew=EW8; req.vtype.vlmul=LMUL_1;
    valid=1;
    @(negedge clk); valid=0;
    repeat(25) @(negedge clk);
    if(requests==0) $fatal(1,"No translation request");
    if(Width==48 && High && !OldMmu) begin
      if(!saw_bad_va || !saw_ex || saw_ar) $fatal(1,"Failed to reproduce board fault");
    end else if(saw_ex || !saw_ar) $fatal(1,"Control case failed");
    $display("CASE_PASS width=%0d old=%0d high=%0d badva=%0d fault=%0d ar=%0d",Width,OldMmu,High,saw_bad_va,saw_ex,saw_ar);
    done=1;
  end
endmodule

module canonical_tb;
  wire [3:0] done;
  canonical_case #(.Width(48),.OldMmu(0),.High(1)) failing(.done(done[0]));
  canonical_case #(.Width(64),.OldMmu(0),.High(1)) wide_control(.done(done[1]));
  canonical_case #(.Width(48),.OldMmu(0),.High(0)) low_control(.done(done[2]));
  canonical_case #(.Width(48),.OldMmu(1),.High(1)) old_control(.done(done[3]));
  initial begin wait(&done); $display("CANONICAL_ROOTCAUSE_REPRO_PASS"); $finish; end
  initial begin #10000; $fatal(1,"Watchdog"); end
endmodule
