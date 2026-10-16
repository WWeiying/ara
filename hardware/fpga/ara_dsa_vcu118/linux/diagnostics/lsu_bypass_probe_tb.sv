`timescale 1ns/1ps
module lsu_bypass_probe_tb;
  reg clk=0;
  always #5 clk=~clk;
  reg rst=0, flush=0, push=0, ld=0, st=0;
  reg [255:0] data=0;
  wire ready, valid;
  wire [255:0] result;
  reg [255:0] pending[$];
  reg [255:0] expected;
  int cycles=0;
  lsu_bypass_probe dut(clk,rst,flush,push,ld,st,data,ready,valid,result);
  task automatic tick(input bit p, l, s, f, input int tag);
    @(negedge clk);
    push=p; ld=l; st=s; flush=f;
    data={32'(tag),32'(~tag),64'(tag*97),64'h123456789abcdef0,64'(tag*65537)};
    #1;
    if (ready !== (pending.size()==0)) $fatal(1,"ready cycle=%0d",cycles);
    if (pending.size()!=0 || p) begin
      expected=pending.size()!=0 ? pending[0] : data;
      if (valid !== 1'b1 || result !== expected)
        $fatal(1,"payload cycle=%0d got=%h expected=%h valid=%b",cycles,result,expected,valid);
    end else if (valid !== 1'b0) $fatal(1,"idle valid cycle=%0d",cycles);
    if (p) pending.push_back(data);
    if (l || s) begin
      if (pending.size()==0 || (l && s)) $fatal(1,"illegal stimulus");
      expected=pending.pop_front();
    end
    if (f) pending.delete();
    if (pending.size()>2) $fatal(1,"overflow stimulus");
    @(posedge clk); #1; cycles++;
  endtask
  initial begin
    #101; rst=1;
    for (int i=0;i<64;i++) begin
      tick(1,0,0,0,4*i);
      tick(0,0,0,0,0);
      tick(1,1,0,0,4*i+1);
      tick(0,0,1,0,0);
      tick(1,1,0,0,4*i+2);
      tick(0,0,0,0,0);
      tick(1,0,0,0,4*i+3);
      tick(1,0,0,0,4*i+4);
      tick(0,0,0,0,0);
      tick(0,1,0,0,0);
      tick(0,0,1,0,0);
      tick(1,0,0,0,4*i+5);
      tick(0,0,0,1,0);
      tick(0,0,0,0,0);
    end
    $display("LSU_BYPASS_PASS cycles=%0d",cycles);
    $finish;
  end
  initial begin #100000; $fatal(1,"timeout"); end
endmodule
