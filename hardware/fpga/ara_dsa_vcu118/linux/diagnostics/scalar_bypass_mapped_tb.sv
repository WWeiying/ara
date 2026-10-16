`timescale 1ns/1ps
// Exercise the exported whole-design cell, not an independently synthesized proxy.
module scalar_bypass_mapped_tb;
  typedef struct packed {
    logic valid;
    logic [63:0] vaddr;
    logic [31:0] tinst;
    logic hs_ld_st_inst, hlvx_inst, overflow, g_overflow;
    logic [63:0] data;
    logic [7:0] be;
    logic [3:0] fu;
    logic [7:0] operation;
    logic [2:0] trans_id;
  } ctrl_t;
  reg clk=0;
  always #5 clk=~clk;
  reg rst=0, flush=0, push=0, ld=0, st=0;
  wire ready;
  ctrl_t req, resp, expected, pending[$];
  int cycles=0;
`ifdef SCALAR_BYPASS_RTL
  lsu_bypass #(.lsu_ctrl_t(ctrl_t)) dut (
    .clk_i(clk), .rst_ni(rst), .flush_i(flush),
    .lsu_req_i(req), .lsu_req_valid_i(push), .pop_ld_i(ld), .pop_st_i(st),
    .lsu_ctrl_o(resp), .ready_o(ready)
  );
`else
  lsu_bypass dut (
    .clk_i(clk), .rst_ni(rst), .flush_i(flush),
    .lsu_req_valid_i(push), .pop_ld_i(ld), .pop_st_i(st),
    .\lsu_req_i[valid] (req.valid),
    .\lsu_req_i[vaddr] (req.vaddr),
    .\lsu_req_i[tinst] (req.tinst),
    .\lsu_req_i[hs_ld_st_inst] (req.hs_ld_st_inst),
    .\lsu_req_i[hlvx_inst] (req.hlvx_inst),
    .\lsu_req_i[overflow] (req.overflow),
    .\lsu_req_i[g_overflow] (req.g_overflow),
    .\lsu_req_i[data] (req.data),
    .\lsu_req_i[be] (req.be),
    .\lsu_req_i[fu] (req.fu),
    .\lsu_req_i[operation] (req.operation),
    .\lsu_req_i[trans_id] (req.trans_id),
    .\lsu_ctrl_o[valid] (resp.valid),
    .\lsu_ctrl_o[vaddr] (resp.vaddr),
    .\lsu_ctrl_o[tinst] (resp.tinst),
    .\lsu_ctrl_o[hs_ld_st_inst] (resp.hs_ld_st_inst),
    .\lsu_ctrl_o[hlvx_inst] (resp.hlvx_inst),
    .\lsu_ctrl_o[overflow] (resp.overflow),
    .\lsu_ctrl_o[g_overflow] (resp.g_overflow),
    .\lsu_ctrl_o[data] (resp.data),
    .\lsu_ctrl_o[be] (resp.be),
    .\lsu_ctrl_o[fu] (resp.fu),
    .\lsu_ctrl_o[operation] (resp.operation),
    .\lsu_ctrl_o[trans_id] (resp.trans_id),
    .ready_o(ready)
  );
`endif
  task automatic tick(input bit p,l,s,f, input int tag);
    @(negedge clk);
    push=p; ld=l; st=s; flush=f;
    req='0;
    req.valid=p;
    req.vaddr=64'hffffffd602e10000 + 64'(tag*8);
    req.data={32'(tag),32'(~tag)};
    req.be=8'(tag ^ 8'ha5);
    req.fu=tag[0] ? 4'd2 : 4'd1;
    req.operation=8'(tag & 127);
    req.trans_id=3'(tag);
    req.overflow=tag[2];
    // Hypervisor fields and operation[7] are constant in this frozen design.
    #1;
    if (ready !== (pending.size()==0)) $fatal(1,"ready cycle=%0d",cycles);
    if (pending.size()!=0 || p) begin
      expected=pending.size()!=0 ? pending[0] : req;
      if (resp !== expected) begin
        $display("MISMATCH cycle=%0d count=%0d fu=%h/%h address=%h/%h valid=%b/%b",
          cycles,pending.size(),resp.fu,expected.fu,resp.vaddr,expected.vaddr,
          resp.valid,expected.valid);
        $fatal(1,"payload got=%h expected=%h",resp,expected);
      end
    end else if (resp.valid !== 1'b0) $fatal(1,"idle valid cycle=%0d",cycles);
    if (p) pending.push_back(req);
    if (l || s) begin
      if (!pending.size() || (l && s)) $fatal(1,"illegal stimulus");
      expected=pending.pop_front();
    end
    if (f) pending.delete();
    if (pending.size()>2) $fatal(1,"overflow stimulus");
    @(posedge clk); #1; cycles++;
  endtask
  initial begin
    req='0;
    #201; rst=1;
    for (int i=0;i<128;i++) begin
      tick(1,0,0,0,8*i);
      tick(0,0,0,0,0);
      tick(1,1,0,0,8*i+1);
      tick(0,0,1,0,0);
      tick(1,1,0,0,8*i+2);
      tick(0,0,0,0,0);
      tick(1,0,0,0,8*i+3);
      tick(1,0,0,0,8*i+4);
      tick(0,0,0,0,0);
      tick(0,1,0,0,0);
      tick(0,0,1,0,0);
      tick(1,0,0,0,8*i+5);
      tick(1,0,0,1,8*i+6);
      tick(0,0,0,0,0);
    end
    $display("SCALAR_BYPASS_MAPPED_PASS cycles=%0d",cycles);
    $finish;
  end
  initial begin #100000; $fatal(1,"timeout"); end
endmodule
