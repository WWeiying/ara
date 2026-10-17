`timescale 1ns/1ps
`include "axi/typedef.svh"
`include "ara/intf_typedef.svh"
package va_test_pkg;
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

// Host-only shared-TLB storage. DTLB hits are controlled, not the MMU response.
module sram #(
  parameter DATA_WIDTH=64, USER_WIDTH=1, USER_EN=0, NUM_WORDS=1024,
  parameter SIM_INIT="none", OUT_REGS=0
)(input logic clk_i, rst_ni, req_i, we_i,
  input logic [$clog2(NUM_WORDS)-1:0] addr_i,
  input logic [USER_WIDTH-1:0] wuser_i,
  input logic [DATA_WIDTH-1:0] wdata_i,
  input logic [(DATA_WIDTH+7)/8-1:0] be_i,
  output logic [USER_WIDTH-1:0] ruser_o,
  output logic [DATA_WIDTH-1:0] rdata_o);
  logic [DATA_WIDTH-1:0] mem [NUM_WORDS];
  assign ruser_o='0;
  always @(posedge clk_i) begin
    if (!rst_ni) rdata_o <= '0;
    else if (req_i) begin
      if (we_i) begin
        for (int b=0; b<DATA_WIDTH; b++)
          if (be_i[b/8]) mem[addr_i][b] <= wdata_i[b];
      end else rdata_o <= mem[addr_i];
    end
  end
endmodule

module va_case #(
  parameter int Width=48, Kind=0, CaseId=Kind,
  parameter bit OverrideBase=0, Translate=1, Store=0,
  parameter logic [63:0] BaseAddress=0
)(output bit done=0);
  import ara_pkg::*;
  import rvv_pkg::*;
  import va_test_pkg::*;
  `AXI_TYPEDEF_ALL(bus, logic[Width-1:0], logic[4:0], logic[127:0], logic[15:0], logic[1:0])
  logic clk=0, rst=0, valid=0;
  always #5 clk=~clk;
  pe_req_t req;
  logic mmu_req, mmu_valid, hit, is_store, ack, arvalid, awvalid;
  logic [63:0] va, base, expected[4], observed[4];
  logic [Cfg.PLEN-1:0] pa;
  logic [Cfg.PPNW-1:0] ppn;
  exception_t ex, addr_ex;
  bus_ar_chan_t ar;
  bus_aw_chan_t aw;
  addrgen_axi_req_t descriptor;
  logic descriptor_valid;
  dc_req_t ptw_req;
  elen_t [3:0] operands;
  logic [3:0] operand_valid=0;
  logic [63:0] stalled_index;
  bit index_stalled=0;
  int cycles=0, requests=0, responses=0, transactions=0, descriptors=0, faults=0;
  int first_axi=0, ack_cycle=0, expected_count;
  wire axi_ready = Kind!=6 || cycles>=7;
  bit expect_fault, checking=0, ack_seen=0;
  logic [63:0] fault_va;

  function automatic logic [63:0] physical(logic [63:0] address);
    if (!Translate) return address;
    return (address[12] ? 64'h200abc000 : 64'h100846000) | (address & 64'hfff);
  endfunction

  addrgen #(.NrLanes(4), .VLEN(1024), .AxiDataWidth(128), .AxiAddrWidth(Width),
    .axi_ar_t(bus_ar_chan_t), .axi_aw_t(bus_aw_chan_t), .pe_req_t(pe_req_t),
    .pe_resp_t(pe_resp_t), .CVA6Cfg(Cfg), .exception_t(exception_t)) ag (
    .clk_i(clk), .rst_ni(rst), .axi_ar_o(ar), .axi_ar_valid_o(arvalid), .axi_ar_ready_i(axi_ready),
    .axi_aw_o(aw), .axi_aw_valid_o(awvalid), .axi_aw_ready_i(axi_ready),
    .en_ld_st_translation_i(Translate), .mmu_req_o(mmu_req), .mmu_vaddr_o(va),
    .mmu_is_store_o(is_store), .mmu_dtlb_hit_i(hit), .mmu_dtlb_ppn_i(ppn),
    .mmu_valid_i(mmu_valid), .mmu_paddr_i(pa), .mmu_exception_i(ex),
    .core_st_pending_i(1'b0), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('0), .addrgen_exception_o(addr_ex), .addrgen_ack_o(ack),
    .axi_addrgen_req_o(descriptor), .axi_addrgen_req_valid_o(descriptor_valid),
    .ldu_axi_addrgen_req_ready_i(descriptor_valid && req.op!=VSE),
    .stu_axi_addrgen_req_ready_i(descriptor_valid && req.op==VSE),
    .ldu_mask_word_i('1), .ldu_mask_word_valid_i('1), .ldu_mask_owner_id_i('0),
    .ldu_mask_first_element_i('0), .stu_mask_word_i('1), .stu_mask_word_valid_i('1),
    .stu_mask_owner_id_i('0), .stu_mask_first_element_i('0), .addrgen_operand_i(operands),
    .addrgen_operand_valid_i(operand_valid), .lsu_ex_flush_i(1'b0)
  );
  cva6_mmu #(.CVA6Cfg(Cfg), .icache_areq_t(if_out_t), .icache_arsp_t(if_in_t),
    .dcache_req_i_t(dc_req_t), .dcache_req_o_t(dc_rsp_t), .exception_t(exception_t)) mmu (
    .clk_i(clk), .rst_ni(rst), .flush_i(1'b0), .enable_translation_i(1'b0),
    .enable_g_translation_i(1'b0), .en_ld_st_translation_i(Translate), .en_ld_st_g_translation_i(1'b0),
    .icache_areq_i('0), .misaligned_ex_i('0), .lsu_req_i(mmu_req), .lsu_vaddr_i(va),
    .lsu_tinst_i('0), .lsu_is_store_i(is_store), .lsu_dtlb_hit_o(hit),
    .lsu_dtlb_ppn_o(ppn), .lsu_valid_o(mmu_valid), .lsu_paddr_o(pa), .lsu_exception_o(ex),
    .priv_lvl_i(riscv::PRIV_LVL_S), .ld_st_priv_lvl_i(riscv::PRIV_LVL_S),
    .v_i(1'b0), .ld_st_v_i(1'b0), .sum_i(1'b0), .vs_sum_i(1'b0),
    .mxr_i(1'b0), .vmxr_i(1'b0), .hlvx_inst_i(1'b0), .hs_ld_st_inst_i(1'b0),
    .satp_ppn_i('0), .vsatp_ppn_i('0), .hgatp_ppn_i('0), .asid_i('0), .vs_asid_i('0),
    .asid_to_be_flushed_i('0), .vmid_i('0), .vmid_to_be_flushed_i('0),
    .vaddr_to_be_flushed_i('0), .gpaddr_to_be_flushed_i('0), .flush_tlb_i(1'b0),
    .flush_tlb_vvma_i(1'b0), .flush_tlb_gvma_i(1'b0), .req_port_i('0),
    .req_port_o(ptw_req), .pmpcfg_i('0), .pmpaddr_i('0)
  );
  initial begin
    force mmu.dtlb_lu_hit=1'b1;
    force mmu.dtlb_content='0;
    force mmu.dtlb_content.ppn=va[12] ? 44'h200abc : 44'h100846;
    force mmu.dtlb_content.r=1;
    force mmu.dtlb_content.w=1;
    force mmu.dtlb_content.v=1;
    force mmu.dtlb_content.a=1;
    force mmu.dtlb_content.d=1;
    force mmu.dtlb_is_page='0;
  end

  // Sample before the active edge: each row is an actual handshake cycle.
  always @(posedge clk) if (rst && checking) begin
    cycles++;
    $display("CYCLE kind=%0d width=%0d cycle=%0d req=%b va=%016h held=%h response=%b registered_va=%016h fault=%b cause=%0d tval=%016h ar=%b physical=%h ack=%b", CaseId,Width,cycles,mmu_req,va,ag.axi_addrgen_q.addr,mmu_valid,mmu.lsu_vaddr_q,ex.valid,ex.cause,ex.tval,arvalid,ar.addr,ack);
    if (ptw_req.data_req) $fatal(1,"Unexpected PTW request");
    if (awvalid && req.op!=VSE) $fatal(1,"Unexpected write");
    if (Kind==6 && !axi_ready && ag.idx_vaddr_valid_q) begin
      if (index_stalled && stalled_index !== ag.idx_final_vaddr_q) $fatal(1,"Index spill changed under backpressure");
      stalled_index=ag.idx_final_vaddr_q; index_stalled=1;
    end
    if (mmu_req) begin
      if (!Translate) $fatal(1,"Translation request while translation disabled");
      if (requests >= expected_count) $fatal(1,"Extra translation");
      observed[requests]=va;
      if (va !== (expect_fault ? fault_va : expected[requests])) $fatal(1,"Wrong request VA kind=%0d got=%h expected=%h",Kind,va,expected[requests]);
      requests++;
    end
    if (mmu_valid) begin
      if (responses >= requests || mmu.lsu_vaddr_q !== observed[responses]) $fatal(1,"Response VA mismatch");
      if (ex.valid !== expect_fault) $fatal(1,"Wrong MMU fault status");
      if (ex.valid && (ex.cause != (req.op==VSE ? 15 : 13) || ex.tval !== fault_va)) $fatal(1,"Wrong MMU fault metadata");
      responses++;
    end
    if ((arvalid || awvalid) && axi_ready) begin
      if (expect_fault || transactions >= expected_count) $fatal(1,"Unexpected AXI");
      if ((arvalid ? 64'(ar.addr) : 64'(aw.addr)) !== physical(expected[transactions])) $fatal(1,"Wrong physical AXI");
      if ((arvalid ? ar.len : aw.len) != ((Kind==4) ? (transactions==0 ? 0 : 2) : (Kind==0 || Kind==1 ? 7 : 0))) $fatal(1,"Wrong burst length");
      if (!first_axi) first_axi=cycles;
      transactions++;
    end
    if (descriptor_valid) begin
      if (descriptor.is_exception !== expect_fault) $fatal(1,"Descriptor exception mismatch");
      if (!expect_fault) begin
        if (descriptors >= expected_count || descriptor.vaddr !== expected[descriptors] ||
            descriptor.addr !== physical(expected[descriptors])) $fatal(1,"Descriptor address mismatch");
      end
      descriptors++;
    end
    if (addr_ex.valid) begin
      faults++;
      if (!expect_fault || addr_ex.cause != (req.op==VSE ? 15 : 13) || addr_ex.tval !== fault_va) $fatal(1,"Wrong addrgen fault metadata");
    end
    if (ack) begin ack_seen=1; ack_cycle=cycles; end
  end

  initial begin
    base=64'hffffffd680846000;
    if (Kind==1) base=64'h0000000080846000;
    if (Kind==2) base=64'h0000ffd680846000;
    if (Kind==3) base=64'h1234000080846000;
    if (Kind==7) base=64'h1234000080846000;
    if (Kind==8) base=64'h0000ffd680846000;
    if (Kind==4) base=64'hffffffd680846ff0;
    if (OverrideBase) base=BaseAddress;
    req='0; operands='0;
    req.op=VLE; req.vm=1; req.vfu=VFU_LoadUnit; req.vl=128;
    req.scalar_op=base; req.vtype.vsew=EW8; req.vtype.vlmul=LMUL_1;
    expected_count=1; expected[0]=base;
    if (Kind==2 || Kind==3 || Kind==7 || Kind==8) req.vl=16;
    if (Kind==7 || Kind==8) begin req.op=VSE; req.vfu=VFU_StoreUnit; end
    if (Store) begin req.op=VSE; req.vfu=VFU_StoreUnit; end
    if (Kind==4) begin req.vl=64; expected_count=2; expected[1]=base+16; end
    if (Kind==5) begin
      req.op=VLSE; req.vl=4; req.vstart=1; req.stride=-16;
      expected_count=3;
      for (int i=0;i<3;i++) expected[i]=base-16*(i+1);
    end
    if (Kind==6) begin
      req.op=VLXE; req.vl=4; req.vstart=1;
      req.eew_vs2=EW64; req.old_eew_vs2=EW64;
      operands[0]=0; operands[1]=16; operands[2]=32; operands[3]=48;
      operand_valid='1; expected_count=3;
      for (int i=0;i<3;i++) expected[i]=base+16*(i+1);
    end
    expect_fault=(Kind==2 || Kind==3 || Kind==7 || Kind==8);
`ifdef BASELINE
    // The baseline must expose truncation, including an invalid VA becoming low/canonical.
    for (int i=0;i<expected_count;i++) expected[i]=Width'(expected[i]);
    expect_fault=(Width==48 && Kind!=1 && Kind!=3 && Kind!=7) || Kind==2 || Kind==8 || (Width==64 && Kind==3);
`endif
    fault_va=expected[0];
    if (expect_fault) expected_count=1;
    repeat(3) @(negedge clk);
    rst=1;
    @(negedge clk); checking=1; valid=1;
    @(negedge clk); valid=0;
    repeat(60) @(negedge clk);
    checking=0;
    if (Kind==6 && !index_stalled) $fatal(1,"No index spill backpressure exercised");
    if (!ack_seen || requests!=(Translate ? expected_count : 0) || responses!=(Translate ? expected_count : 0) ||
        transactions!=(expect_fault ? 0 : expected_count) ||
        descriptors!=expected_count || faults!=(expect_fault ? 1 : 0))
      $fatal(1,"Incomplete kind=%0d req=%0d rsp=%0d ar=%0d desc=%0d fault=%0d ack=%b",Kind,requests,responses,transactions,descriptors,faults,ack_seen);
    $display("CASE_PASS kind=%0d width=%0d requests=%0d axi=%0d faults=%0d first_axi=%0d ack_cycle=%0d cycles=%0d",CaseId,Width,requests,transactions,faults,first_axi,ack_cycle,cycles);
    done=1;
  end
endmodule

module addrgen_virtual_address_tb;
`ifdef NEIGHBORS
  wire [7:0] done;
  va_case #(.Kind(0),.CaseId(10),.Store(1)) high_store(.done(done[0]));
  va_case #(.Kind(4),.CaseId(11),.Store(1)) page_store(.done(done[1]));
  va_case #(.Kind(4),.CaseId(12),.OverrideBase(1),.BaseAddress(64'hffffffd6fffffff0)) carry32(.done(done[2]));
  va_case #(.Kind(5),.CaseId(13),.OverrideBase(1),.BaseAddress(64'hffffffd700000000)) borrow32(.done(done[3]));
  va_case #(.Kind(6),.CaseId(14),.OverrideBase(1),.BaseAddress(64'hffffffd6fffffff0)) index_carry(.done(done[4]));
  va_case #(.Kind(4),.CaseId(15),.OverrideBase(1),.BaseAddress(64'h0000003fffffeff0)) low_sv39_edge(.done(done[5]));
  va_case #(.Kind(0),.CaseId(16),.Translate(0),.OverrideBase(1),.BaseAddress(64'h0000001080846000)) bare_load(.done(done[6]));
  va_case #(.Kind(0),.CaseId(17),.Translate(0),.Store(1),.OverrideBase(1),.BaseAddress(64'h0000001080846000)) bare_store(.done(done[7]));
`else
  wire [9:0] done;
  for (genvar k=0;k<9;k++) begin : cases
    va_case #(.Width(48),.Kind(k)) test_case(.done(done[k]));
  end
  va_case #(.Width(64),.Kind(0)) wide_control(.done(done[9]));
`endif
  initial begin wait (&done); $display("ADDRGEN_VIRTUAL_ADDRESS_PASS"); $finish; end
  initial begin #2000; $fatal(1,"Bounded watchdog"); end
endmodule
