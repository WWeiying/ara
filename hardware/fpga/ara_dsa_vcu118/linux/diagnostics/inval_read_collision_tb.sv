`timescale 1ns/1ps
`include "axi/typedef.svh"
module inval_read_collision_tb;
  import ariane_pkg::*;
  import wt_cache_pkg::*;
  function automatic config_pkg::cva6_cfg_t config_value();
    config_pkg::cva6_user_cfg_t c = cva6_config_pkg::cva6_cfg;
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
  logic clk=0,rst=0,dc_req=0,inv=0;
  logic ic_req=0;
  wire ic_ack,ic_valid;
  icache_req_t ic;
  icache_rtrn_t ic_ret;
  int mode=0, hold_cycles=1, beats=4;
  wire dc_ack,inv_ready,ret_valid;
  int filter_mode=0;
  wire actual_inv,filter_inv;
  wire [47:0] filter_addr;
  axi_req_t vector_req,vector_out;
  axi_resp_t vector_rsp,vector_downstream;
  int vector_writes=0;
  assign actual_inv = filter_mode ? filter_inv : inv;
  always_comb begin
    vector_req='0;
    vector_req.aw_valid=inv && (filter_mode!=0);
    vector_req.aw.addr=48'h83299f88;
    vector_req.aw.len=1;
    vector_req.aw.size=3;
    vector_req.aw.burst=axi_pkg::BURST_INCR;
    vector_downstream='0;
    vector_downstream.aw_ready=1;
  end
  // Same AW FIFO depth and cache-line size as the frozen Cheshire integration.
  // Only AW participates in invalidation; W/B are outside this focused test.
  axi_inval_filter #(.MaxTxns(4),.AddrWidth(48),.L1LineWidth(32),
    .aw_chan_t(axi_aw_chan_t),.req_t(axi_req_t),.resp_t(axi_resp_t)) filter (
    .clk_i(clk),.rst_ni(rst),.en_i(filter_mode==1),
    .slv_req_i(vector_req),.slv_resp_o(vector_rsp),
    .mst_req_o(vector_out),.mst_resp_i(vector_downstream),
    .inval_addr_o(filter_addr),.inval_valid_o(filter_inv),.inval_ready_i(inv_ready));
  dcache_req_t dc;
  dcache_rtrn_t ret;
  axi_req_t req;
  axi_resp_t rsp;
  int reads=0,returns=0,invalidations=0;
  int collide=-1;
  logic[3:0] returned_id;
  logic[255:0] expected;
  always #5 clk=~clk;
  wt_axi_adapter #(.CVA6Cfg(CVA6Cfg),.axi_req_t(axi_req_t),.axi_rsp_t(axi_resp_t),
    .dcache_req_t(dcache_req_t),.dcache_rtrn_t(dcache_rtrn_t),
    .dcache_inval_t(dcache_inval_t),.icache_req_t(icache_req_t),
    .icache_rtrn_t(icache_rtrn_t)) dut (
    .clk_i(clk),.rst_ni(rst),.icache_data_req_i(ic_req),.icache_data_i(ic),
    .icache_data_ack_o(ic_ack),.icache_rtrn_vld_o(ic_valid),.icache_rtrn_o(ic_ret),
    .dcache_data_req_i(dc_req),.dcache_data_ack_o(dc_ack),.dcache_data_i(dc),
    .dcache_rtrn_vld_o(ret_valid),.dcache_rtrn_o(ret),
    .axi_req_o(req),.axi_resp_i(rsp),
    .inval_addr_i(filter_mode ? {16'b0,filter_addr} : 64'h83299f80),
    .inval_valid_i(actual_inv),.inval_ready_o(inv_ready)
  );
  always @(posedge clk) if(rst) begin
    if(vector_req.aw_valid && vector_rsp.aw_ready) vector_writes++;
    if(rsp.r_valid || actual_inv)
      $display("READ_CYCLE t=%0t rvalid=%b rready=%b rlast=%b inval=%b inval_ready=%b capture=%b pop=%b pending=%b",
        $time,rsp.r_valid,req.r_ready,rsp.r.last,actual_inv,inv_ready,
        dut.dcache_rtrn_rd_en,dut.dcache_rd_pop,!dut.dcache_rd_empty);
    if(rsp.r_valid && req.r_ready) reads++;
    if(ret_valid && ret.rtype==DCACHE_INV_REQ) invalidations++;
    if(ic_valid) begin
      returns++;
      if(mode!=1 || ic_ret.data!==expected[CVA6Cfg.ICACHE_LINE_WIDTH-1:0] || ic_ret.tid!=1)
        $fatal(1,"ICACHE_DATA_OR_ID_CORRUPT");
    end
    if(ret_valid && (ret.rtype==DCACHE_LOAD_ACK || ret.rtype==DCACHE_ATOMIC_ACK)) begin
      returns++;
      if(ret.tid!=1 || (mode==2 ? ret.data[63:0]!==expected[63:0] : ret.data!==expected))
        $fatal(1,"RETURN_DATA_CORRUPT collide=%0d data=%h expected=%h",collide,ret.data,expected);
      if((mode==2)!=(ret.rtype==DCACHE_ATOMIC_ACK)) $fatal(1,"WRONG_RETURN_TYPE");
    end
    if(req.ar_valid && rsp.ar_ready) begin
      if(req.ar.addr!==48'h828597e0 || req.ar.len!=beats-1 || req.ar.lock!=(mode==2))
        $fatal(1,"Wrong captured-line request");
      returned_id=req.ar.id;
    end
  end
  initial begin
    if($value$plusargs("collide=%d",collide)) begin end
    if($value$plusargs("filter=%d",filter_mode)) begin end
    if($value$plusargs("mode=%d",mode)) begin end
    if($value$plusargs("hold=%d",hold_cycles)) begin end
    beats=mode==2 ? 1 : mode==1 ? CVA6Cfg.ICACHE_LINE_WIDTH/64 : 4;
    dc='0; ic='0; rsp='0;
    expected={64'h4444444444444444,64'h20b94801,64'h2222222222222222,64'h1111111111111111};
    #220; @(negedge clk); rst=1;
    // The miss unit aligns the PTE address 0x828597f0 to a cache line.
    dc.rtype=DCACHE_LOAD_REQ; dc.paddr=56'h828597e0; dc.size=7; dc.tid=1;
    if(mode==2) begin dc.rtype=DCACHE_ATOMIC_REQ; dc.amo_op=AMO_LR; dc.size=3; end
    ic.paddr=56'h828597e0; ic.tid=1;
    dc_req=(mode!=1); ic_req=(mode==1);
    do @(posedge clk); while(!(mode==1 ? ic_ack : dc_ack));
    @(negedge clk); dc_req=0; ic_req=0; rsp.ar_ready=1;
    do @(posedge clk); while(!req.ar_valid);
    @(negedge clk); rsp.ar_ready=0;
    for(int beat=0;beat<beats;beat++) begin
      rsp.r_valid=1; rsp.r.id=returned_id; rsp.r.data=expected[64*beat+:64];
      rsp.r.last=(beat==beats-1); inv=(collide==beat);
      @(posedge clk);
      if(actual_inv && !inv_ready) $fatal(1,"Invalidation not accepted");
      if(!req.r_ready) begin
        // A repaired adapter must backpressure, then accept the held beat.
        repeat(hold_cycles-1) begin
          @(negedge clk);
          @(posedge clk);
          if(req.r_ready || !inv_ready) $fatal(1,"READ_ACCEPTED_DURING_INVALIDATION");
        end
        @(negedge clk); inv=0;
        do @(posedge clk); while(!req.r_ready);
      end
      @(negedge clk); inv=0; rsp.r_valid=0;
      repeat(2) @(negedge clk);
    end
    repeat(20) @(negedge clk);
    $display("COLLISION_RESULT collide=%0d axi_beats=%0d load_returns=%0d invalidations=%0d pending=%b",collide,reads,returns,invalidations,!dut.dcache_rd_empty);
    $display("FILTER_RESULT mode=%0d aw_handshakes=%0d",filter_mode,vector_writes);
    if(filter_mode && vector_writes!=((collide>=0) ? hold_cycles : 0)) $fatal(1,"AW_HANDSHAKE_MISMATCH");
    if(reads!=beats || returns!=1 || invalidations!=(((collide>=0) && filter_mode!=2) ? hold_cycles : 0)+(mode==2))
      $fatal(1,"READ_COMPLETION_LOST");
    $display("INVAL_READ_PASS collide=%0d",collide);
    $finish;
  end
  initial begin #20000; $fatal(1,"TEST_TIMEOUT"); end
endmodule
