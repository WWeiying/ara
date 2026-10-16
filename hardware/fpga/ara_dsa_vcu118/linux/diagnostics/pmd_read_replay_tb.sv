`timescale 1ns/1ps
`include "axi/typedef.svh"
// Controlled mechanism replay, NOT a reconstruction of historical board timing.
// Prime the real adapter with the leaf-shaped value printed by the board, then
// read a valid PMD in lane zero with/without one invalidation collision.
module inval_read_collision_tb;
  import ariane_pkg::*;
  import wt_cache_pkg::*;
  function automatic config_pkg::cva6_cfg_t config_value();
    config_pkg::cva6_user_cfg_t c = cva6_config_pkg::cva6_cfg;
    c.AxiAddrWidth=48; c.AxiDataWidth=64; c.AxiIdWidth=4; c.AxiUserWidth=2;
    return build_config_pkg::build_config(c);
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg=config_value();
  typedef logic [47:0] addr_t;
  typedef logic [3:0] id_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [1:0] user_t;
  `AXI_TYPEDEF_ALL(axi,addr_t,id_t,data_t,strb_t,user_t)
  `include "collision_types.svh"
  logic clk=0, rst=0, request=0, inv=0;
  wire ack, ret_valid, inv_ready;
  dcache_req_t dc;
  dcache_rtrn_t ret;
  icache_req_t ic;
  axi_req_t req;
  axi_resp_t rsp;
  logic [3:0] rid;
  int collide=-1, transaction=0, captures=0, accepted=0, lost=0, returns=0;
  logic [255:0] observed[2];
`ifdef PMD_FSDB
  struct packed {
    logic clk, rst, valid, ready, last, inval, capture;
    logic [31:0] transaction;
    logic [63:0] data;
    logic [255:0] shift;
  } trace;
  always_comb trace = {clk,rst,rsp.r_valid,req.r_ready,rsp.r.last,inv,
                      dut.dcache_rtrn_rd_en,32'(transaction),rsp.r.data,dut.dcache_rd_shift_q};
  initial begin
    string wave;
    if(!$value$plusargs("wave=%s",wave)) $fatal(1,"Missing waveform path");
    $fsdbDumpfile(wave);
    $fsdbDumpvars(0,inval_read_collision_tb.trace);
    $fsdbDumpoff;
    #220; $fsdbDumpon;
    #1000; $fsdbDumpoff;
  end
`endif
  always #5 clk=~clk;
  wt_axi_adapter #(.CVA6Cfg(CVA6Cfg), .axi_req_t(axi_req_t), .axi_rsp_t(axi_resp_t),
    .dcache_req_t(dcache_req_t), .dcache_rtrn_t(dcache_rtrn_t),
    .dcache_inval_t(dcache_inval_t), .icache_req_t(icache_req_t),
    .icache_rtrn_t(icache_rtrn_t)) dut (
    .clk_i(clk), .rst_ni(rst), .icache_data_req_i(1'b0), .icache_data_i(ic),
    .icache_data_ack_o(), .icache_rtrn_vld_o(), .icache_rtrn_o(),
    .dcache_data_req_i(request), .dcache_data_ack_o(ack), .dcache_data_i(dc),
    .dcache_rtrn_vld_o(ret_valid), .dcache_rtrn_o(ret),
    .axi_req_o(req), .axi_resp_i(rsp), .inval_addr_i(64'h81049000),
    .inval_valid_i(inv), .inval_ready_o(inv_ready));
  always @(posedge clk) if (rst) begin
    if (req.ar_valid && rsp.ar_ready) rid=req.ar.id;
    if (rsp.r_valid && req.r_ready) begin
      accepted++;
      if (!dut.dcache_rtrn_rd_en) lost++;
    end
    if (dut.dcache_rtrn_rd_en) captures++;
    if (rsp.r_valid || inv)
      $display("PMD_CYCLE t=%0t tx=%0d data=%h valid=%b ready=%b capture=%b inv=%b last=%b",
        $time,transaction,rsp.r.data,rsp.r_valid,req.r_ready,dut.dcache_rtrn_rd_en,inv,rsp.r.last);
    if (ret_valid && ret.rtype==DCACHE_LOAD_ACK) begin
      if (ret.tid!=transaction+1) $fatal(1,"Wrong response ID");
      observed[transaction]=ret.data; returns++;
    end
  end
  task automatic load_line(input logic [47:0] address,input logic [255:0] line_data);
    dc='0; dc.rtype=DCACHE_LOAD_REQ; dc.paddr=address; dc.size=7; dc.tid=transaction+1;
    request=1;
    do @(posedge clk); while(!ack);
    @(negedge clk); request=0; rsp.ar_ready=1;
    do @(posedge clk); while(!req.ar_valid);
    if(req.ar.addr!=address || req.ar.len!=3) $fatal(1,"Wrong read transaction");
    @(negedge clk); rsp.ar_ready=0;
    for(int beat=0;beat<4;beat++) begin
      rsp.r_valid=1; rsp.r.id=rid; rsp.r.data=line_data[beat*64+:64]; rsp.r.last=(beat==3);
      inv=transaction==1 && beat==collide;
      @(posedge clk);
      if(!req.r_ready) begin
        if(!inv || !inv_ready) $fatal(1,"Unexpected backpressure");
        @(negedge clk); inv=0;
        do @(posedge clk); while(!req.r_ready);
      end
      @(negedge clk); inv=0; rsp.r_valid=0;
      repeat(2) @(negedge clk);
    end
    repeat(5) @(negedge clk);
  endtask
  initial begin
    if($value$plusargs("collide=%d",collide)) begin end
    dc='0; ic='0; rsp='0;
    #220; @(negedge clk); rst=1;
    load_line(48'h82e64de0,{64'h2005ac5b,64'h2005a85b,64'h2005a45b,64'h2005a05b});
    if(returns!=1 || observed[0][255:192]!=64'h2005ac5b) $fatal(1,"Seed read failed");
    transaction=1;
    load_line(48'h82e699a0,{192'b0,64'h20b99001});
    $display("PMD_REPLAY observed=%h expected=0000000020b99001 accepted=%0d captured=%0d lost=%0d returns=%0d",
      observed[1][63:0],accepted,captures,lost,returns);
    if(accepted!=8 || returns!=2) $fatal(1,"Read completion lost");
    if(observed[1][63:0]!=64'h20b99001) $fatal(1,"STALE_LEAF_AS_PMD");
    $display("INVAL_READ_PASS collide=%0d",collide); $finish;
  end
  initial begin #20000; $fatal(1,"TEST_TIMEOUT"); end
endmodule
