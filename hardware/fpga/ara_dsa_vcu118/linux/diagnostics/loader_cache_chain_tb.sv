`timescale 1ns/1ps
`include "axi/typedef.svh"
// Captured target and PTEs; scheduling and initial cache state are controlled.
module loader_cache_chain_tb;
  import ariane_pkg::*;
  import wt_cache_pkg::*;
  function automatic config_pkg::cva6_cfg_t config_value();
    config_pkg::cva6_user_cfg_t c=cva6_config_pkg::cva6_cfg;
    c.AxiAddrWidth=48; c.AxiDataWidth=64; c.AxiIdWidth=4; c.AxiUserWidth=2;
    return build_config_pkg::build_config(c);
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg=config_value();
  typedef logic[47:0] addr_t;
  typedef logic[3:0] id_t;
  typedef logic[63:0] data_t;
  typedef logic[7:0] strb_t;
  typedef logic[1:0] user_t;
  `AXI_TYPEDEF_ALL(axi,addr_t,id_t,data_t,strb_t,user_t)
  `include "collision_types.svh"
  logic clk=0,rst=0,fetch=0;
  logic[63:0] va=64'h3f93ee20dc;
  logic[43:0] root_ppn=44'h82859;
  logic[55:0] expected_pa=56'h801660dc;
  logic[47:0] root_line=48'h828597e0, aw_address=48'h83299f88;
  logic[63:0] fixture[0:18];
  bit use_fixture=0;
  string fixture_file;
  wire valid,ex_valid;
  wire[55:0] pa;
  dcache_req_i_t ptw_req;
  dcache_req_i_t[3:0] ports;
  dcache_req_o_t[3:0] replies;
  dcache_req_t mem_req;
  dcache_rtrn_t mem_reply;
  wire mem_valid,mem_ack,mem_return;
  axi_req_t req,vreq,vout;
  axi_resp_t rsp,vrsp,vdown;
  wire inv,inv_ready;
  wire[47:0] inv_addr;
  logic pending=0,collision_sent=0;
  logic[47:0] line_addr;
  logic[3:0] rid;
  int beat=0,ar_count=0,r_count=0,ack_count=0,ptw_count=0,aw_count=0,inv_count=0;
  int collide=-1,filter_enable=1;
  always #5 clk=~clk;
  always_comb begin
    ports='0; ports[0]=ptw_req;
  end
  cva6_mmu mmu (
    .clk_i(clk),.rst_ni(rst),.flush_i(1'b0),
    .enable_translation_i(1'b1),.enable_g_translation_i(1'b0),
    .en_ld_st_translation_i(1'b1),.en_ld_st_g_translation_i(1'b0),
    .\icache_areq_i[fetch_req] (fetch),.\icache_areq_i[fetch_vaddr] (va),
    .\icache_areq_o[fetch_paddr] (pa),.\icache_areq_o[fetch_valid] (valid),
    .\icache_areq_o[fetch_exception][valid] (ex_valid),
    .\misaligned_ex_i[valid] (1'b0),.\misaligned_ex_i[cause] (64'b0),
    .\misaligned_ex_i[tval] (64'b0),.\misaligned_ex_i[tval2] (41'b0),
    .\misaligned_ex_i[tinst] (32'b0),.\misaligned_ex_i[gva] (1'b0),
    .lsu_req_i(1'b0),.lsu_vaddr_i(64'b0),.lsu_tinst_i(32'b0),.lsu_is_store_i(1'b0),
    .priv_lvl_i(2'b00),.v_i(1'b0),.ld_st_priv_lvl_i(2'b00),.ld_st_v_i(1'b0),
    .sum_i(1'b0),.vs_sum_i(1'b0),.mxr_i(1'b0),.vmxr_i(1'b0),
    .hlvx_inst_i(1'b0),.hs_ld_st_inst_i(1'b0),
    .satp_ppn_i(root_ppn),.vsatp_ppn_i(44'b0),.hgatp_ppn_i(44'b0),
    .asid_i(16'd1),.vs_asid_i(16'b0),.asid_to_be_flushed_i(16'b0),
    .vmid_i(14'b0),.vmid_to_be_flushed_i(14'b0),
    .vaddr_to_be_flushed_i(64'b0),.gpaddr_to_be_flushed_i(41'b0),
    .flush_tlb_i(1'b0),.flush_tlb_vvma_i(1'b0),.flush_tlb_gvma_i(1'b0),
    .\req_port_i[data_gnt] (replies[0].data_gnt),
    .\req_port_i[data_rvalid] (replies[0].data_rvalid),
    .\req_port_i[data_rdata] (replies[0].data_rdata),
    .\req_port_i[data_rid] (replies[0].data_rid),
    .\req_port_i[data_ruser] (replies[0].data_ruser),
    .\req_port_o[data_req] (ptw_req.data_req),
    .\req_port_o[address_index] (ptw_req.address_index),
    .\req_port_o[address_tag] (ptw_req.address_tag),
    .\req_port_o[data_we] (ptw_req.data_we),.\req_port_o[data_be] (ptw_req.data_be),
    .\req_port_o[data_size] (ptw_req.data_size),.\req_port_o[data_id] (ptw_req.data_id),
    .\req_port_o[kill_req] (ptw_req.kill_req),.\req_port_o[tag_valid] (ptw_req.tag_valid),
    .\req_port_o[data_wdata] (ptw_req.data_wdata),.\req_port_o[data_wuser] (ptw_req.data_wuser),
    .\pmpcfg_i[0][locked] (1'b0),.\pmpcfg_i[0][reserved] (2'b0),
    .\pmpcfg_i[0][addr_mode] (2'b11),.\pmpcfg_i[0][access_type][x] (1'b1),
    .\pmpcfg_i[0][access_type][w] (1'b1),.\pmpcfg_i[0][access_type][r] (1'b1),
    .\pmpaddr_i[0] (54'h3fffffffffffff)
  );
  wt_dcache #(.CVA6Cfg(CVA6Cfg),.dcache_req_i_t(dcache_req_i_t),.dcache_req_o_t(dcache_req_o_t),
    .dcache_req_t(dcache_req_t),.dcache_rtrn_t(dcache_rtrn_t)) cache (
    .clk_i(clk),.rst_ni(rst),.enable_i(1'b1),.flush_i(1'b0),.stall_i(1'b0),.init_ni(rst),
    .amo_req_i(amo_req_t'('0)),.req_ports_i(ports),.req_ports_o(replies),
    .mem_rtrn_vld_i(mem_return),.mem_rtrn_i(mem_reply),
    .mem_data_req_o(mem_valid),.mem_data_ack_i(mem_ack),.mem_data_o(mem_req));
  wt_axi_adapter #(.CVA6Cfg(CVA6Cfg),.axi_req_t(axi_req_t),.axi_rsp_t(axi_resp_t),
    .dcache_req_t(dcache_req_t),.dcache_rtrn_t(dcache_rtrn_t),.dcache_inval_t(dcache_inval_t),
    .icache_req_t(icache_req_t),.icache_rtrn_t(icache_rtrn_t)) adapter (
    .clk_i(clk),.rst_ni(rst),.icache_data_req_i(1'b0),.icache_data_i(icache_req_t'('0)),
    .dcache_data_req_i(mem_valid),.dcache_data_ack_o(mem_ack),.dcache_data_i(mem_req),
    .dcache_rtrn_vld_o(mem_return),.dcache_rtrn_o(mem_reply),.axi_req_o(req),.axi_resp_i(rsp),
    .inval_addr_i({16'b0,inv_addr}),.inval_valid_i(inv),.inval_ready_o(inv_ready));
  axi_inval_filter #(.MaxTxns(4),.AddrWidth(48),.L1LineWidth(32),
    .aw_chan_t(axi_aw_chan_t),.req_t(axi_req_t),.resp_t(axi_resp_t)) filter (
    .clk_i(clk),.rst_ni(rst),.en_i(filter_enable!=0),.slv_req_i(vreq),.slv_resp_o(vrsp),
    .mst_req_o(vout),.mst_resp_i(vdown),.inval_addr_o(inv_addr),.inval_valid_o(inv),.inval_ready_i(inv_ready));
  function automatic logic[63:0] memory_word(input logic[47:0] address);
    if(use_fixture) begin
      for(int line=0;line<3;line++)
        if((address & ~48'd31)==fixture[4+5*line])
          return fixture[5+5*line+int'(address[4:3])];
      $fatal(1,"Read outside captured page-table lines: %h",address);
    end
    case(address)
      48'h828597f0: return 64'h20b94801;
      48'h82e524f8: return 64'h20b7f401;
      48'h82dfd710: return 64'h2005985b;
      default: return 0; // Unused neighbours, not captured board contents.
    endcase
  endfunction
  always_comb begin
    rsp='0; rsp.ar_ready=!pending;
    rsp.r_valid=pending; rsp.r.id=rid;
    if(pending) rsp.r.data=memory_word(line_addr+8*beat);
    rsp.r.last=(beat==3);
    vreq='0; vdown='0; vdown.aw_ready=1;
    vreq.aw_valid=pending && line_addr==root_line && beat==collide && !collision_sent;
    vreq.aw.addr=aw_address; vreq.aw.size=3; vreq.aw.len=1; vreq.aw.burst=axi_pkg::BURST_INCR;
  end
  always @(posedge clk) if(rst) begin
    if(req.ar_valid && rsp.ar_ready) begin
      if(req.ar.len!=3 || req.ar.size!=3) $fatal(1,"Unexpected line request");
      if(use_fixture ? !(req.ar.addr inside {fixture[4],fixture[9],fixture[14]}) :
         !(req.ar.addr inside {48'h828597e0,48'h82e524e0,48'h82dfd700}))
        $fatal(1,"Unexpected page walk line %h",req.ar.addr);
      pending<=1; line_addr<=req.ar.addr; rid<=req.ar.id; beat<=0; ar_count++;
      $display("AR addr=%h",req.ar.addr);
    end
    if(rsp.r_valid) begin
      $display("R beat=%0d ready=%b inval=%b capture=%b",beat,req.r_ready,inv,adapter.dcache_rtrn_rd_en);
      if(req.r_ready) begin
        r_count++;
        if(rsp.r.last) pending<=0; else beat<=beat+1;
      end
    end
    if(vreq.aw_valid && vrsp.aw_ready) begin collision_sent<=1; aw_count++; end
    if(inv && inv_ready) inv_count++;
    if(mem_return && mem_reply.rtype==DCACHE_LOAD_ACK) ack_count++;
    if(replies[0].data_rvalid) begin
      ptw_count++; $display("PTW_REPLY %h",replies[0].data_rdata);
    end
  end
  initial begin
    if($value$plusargs("fixture=%s",fixture_file)) begin
      $readmemh(fixture_file,fixture);
      use_fixture=1; va=fixture[0]; root_ppn=fixture[1]; expected_pa=fixture[2];
      aw_address=fixture[3]; root_line=fixture[4];
      $display("CAPTURED_PTES va=%h root_ppn=%h expected_pa=%h",va,root_ppn,expected_pa);
    end
    if($value$plusargs("collide=%d",collide)) begin end
    if($value$plusargs("filter_enable=%d",filter_enable)) begin end
    if(use_fixture) $display("CONTROLLED_NOT_CAPTURED_AW address=%h collision_beat=%0d",aw_address,collide);
    #220; @(negedge clk); rst=1;
    repeat(200) @(negedge clk);
    fetch=1;
    for(int i=0;i<1000;i++) begin
      @(posedge clk);
      if(valid===1'b1) begin
        // This exported netlist ties unused fetch_paddr[11:0] to zero;
        // the I-cache takes its page offset from the virtual request.
        if(ex_valid!==0 || pa[55:12]!==expected_pa[55:12]) $fatal(1,"Wrong target translation pa=%h ex=%b",pa,ex_valid);
        if(ar_count!=3 || r_count!=12 || ptw_count!=3 || ack_count!=3)
          $fatal(1,"Unexpected translation accounting");
        if(aw_count!=(collide>=0) || inv_count!=((collide>=0) && filter_enable))
          $fatal(1,"Missing collision stimulus");
        $display("CACHE_CHAIN_PASS target=%h ar=%0d r=%0d ptw=%0d cycles=%0d",va,ar_count,r_count,ptw_count,i);
        $finish;
      end
    end
    $display("CACHE_CHAIN_STALL ar=%0d r=%0d ack=%0d ptw=%0d aw=%0d inval=%0d external_pending=%b mshr=%b adapter_pending=%b",
      ar_count,r_count,ack_count,ptw_count,aw_count,inv_count,pending,cache.i_wt_dcache_missunit.mshr_vld_q,!adapter.dcache_rd_empty);
    $fatal(1,"TRANSLATION_DID_NOT_COMPLETE");
  end
endmodule
