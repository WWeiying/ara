// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module id_queue_probe_tb;
  logic clk_i=0,rst_ni=0;
  logic [1:0] inp_id_i=0,oup_id_i=0;
  logic [31:0] inp_data_i=0;
  logic inp_req_i=0,oup_req_i=0,oup_pop_i=0;
  logic [1:0] inp_gnt_o,oup_gnt_o,oup_data_valid_o,full_o,empty_o;
  logic [1:0][31:0] oup_data_o;
  logic [31:0] model[2][4][8192];
  int rd[2][4]='{default:'{default:0}},wr[2][4]='{default:'{default:0}};
  int count[2]='{default:0},pushes[2]='{default:0},pops[2]='{default:0};
  int reuse=0,dual=0,cycle=0;
  int seed=12345;
  logic [31:0] rng;
  always #5 clk_i=~clk_i;
  id_queue_probe dut(
`ifdef MAPPED_PROBE
    .\oup_data_o[0] (oup_data_o[0]), .\oup_data_o[1] (oup_data_o[1]),
`endif
    .*);
  always @(posedge clk_i) if(rst_ni) begin
    for(int mode=0;mode<2;mode++) begin
      automatic bit has_data=wr[mode][oup_id_i]>rd[mode][oup_id_i];
      automatic bit egout=oup_req_i && (mode || !(inp_req_i && count[mode]<4));
      automatic bit pop=egout && has_data && oup_pop_i;
      automatic bit egin=count[mode]<4 || (mode && pop);
      if(full_o[mode] !== (count[mode]==4) || empty_o[mode] !== (count[mode]==0) ||
         inp_gnt_o[mode] !== egin || oup_gnt_o[mode] !== egout)
        $fatal(1,"HANDSHAKE mode=%0d cycle=%0d count=%0d",mode,cycle,count[mode]);
      if(egout) begin
        if(oup_data_valid_o[mode] !== has_data) $fatal(1,"VALID mode=%0d cycle=%0d",mode,cycle);
        if(has_data && oup_data_o[mode] !== model[mode][oup_id_i][rd[mode][oup_id_i]])
          $fatal(1,"DATA mode=%0d cycle=%0d id=%0d got=%h expected=%h",mode,cycle,oup_id_i,
            oup_data_o[mode],model[mode][oup_id_i][rd[mode][oup_id_i]]);
      end
      if(mode && pop && inp_req_i && egin) begin
        dual++;
        if(count[mode]==4) reuse++;
      end
      if(pop) begin rd[mode][oup_id_i]++; count[mode]--; pops[mode]++; end
      if(inp_req_i && egin) begin
        model[mode][inp_id_i][wr[mode][inp_id_i]]=inp_data_i;
        wr[mode][inp_id_i]++; count[mode]++; pushes[mode]++;
      end
    end
  end
  initial begin
    void'($value$plusargs("SEED=%d",seed)); rng=seed;
    repeat(15) @(negedge clk_i);
    rst_ni=1;
    for(cycle=0;cycle<4096;cycle++) begin
      @(negedge clk_i);
      rng=rng^(rng<<13); rng=rng^(rng>>17); rng=rng^(rng<<5);
      inp_data_i=rng^32'(cycle);
      inp_id_i=rng[1:0]; oup_id_i=rng[3:2];
      inp_req_i=rng[4]; oup_req_i=rng[5]; oup_pop_i=rng[6];
      // Deterministic full-queue reuse before random traffic.
      if(cycle<4) begin inp_req_i=1; inp_id_i=0; oup_req_i=0; end
      if(cycle>=4 && cycle<12) begin inp_req_i=1; inp_id_i=0; oup_req_i=1; oup_id_i=0; oup_pop_i=1; end
    end
    @(negedge clk_i); inp_req_i=0; oup_req_i=1; oup_pop_i=1;
    for(int id=0;id<4;id++) begin
      oup_id_i=2'(id);
      repeat(5) @(negedge clk_i);
    end
    oup_req_i=0;
    repeat(5) @(negedge clk_i);
    if(count[0] || count[1] || !dual || !reuse) $fatal(1,"COVERAGE_OR_DRAIN");
    $display("ID_QUEUE_PASS seed=%0d pushes=%p pops=%p simultaneous=%0d full_reuse=%0d",seed,pushes,pops,dual,reuse);
    $finish;
  end
endmodule
