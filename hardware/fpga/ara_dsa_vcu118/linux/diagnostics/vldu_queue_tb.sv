// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module vldu_queue_tb;
  logic clk_i=0, rst_ni=0, req_i=0, ready_o;
  logic [10:0] vl_i;
  logic [1:0] sew_i;
`ifdef SLDU_PROBE
  localparam int InputBytes=32;
`else
  localparam int InputBytes=16;
`endif
  logic [InputBytes*8-1:0] rdata_i;
  logic rvalid_i=0, rready_o, addrvalid_i=0, addrready_o;
  logic [7:0] len_i;
  logic [3:0] grant_i=0, final_i=0, valid_o;
  logic [3:0][63:0] data_o;
  logic [3:0][7:0] be_o;
  logic [3:0][9:0] addr_o;
  logic [3:0][2:0] id_o;
  logic [7:0] done_o;
  int nbytes, sew=0, bytes_arg=128, pressure=1, seed=1;
  int sent=0, cycles=0, completed=0, writes[4]='{default:0};
  int held_cycles=0, fill_while_held=0, simultaneous=0;
  logic [3:0] held=0;
  logic [3:0][84:0] held_payload;
  always #5 clk_i=~clk_i;
`ifdef SLDU_PROBE
  sldu_queue_probe dut (
`else
  vldu_queue_probe dut (
`endif
`ifdef MAPPED_PROBE
    .\data_o[0] (data_o[0]), .\data_o[1] (data_o[1]),
    .\data_o[2] (data_o[2]), .\data_o[3] (data_o[3]),
    .\be_o[0] (be_o[0]), .\be_o[1] (be_o[1]),
    .\be_o[2] (be_o[2]), .\be_o[3] (be_o[3]),
    .\addr_o[0] (addr_o[0]), .\addr_o[1] (addr_o[1]),
    .\addr_o[2] (addr_o[2]), .\addr_o[3] (addr_o[3]),
    .\id_o[0] (id_o[0]), .\id_o[1] (id_o[1]),
    .\id_o[2] (id_o[2]), .\id_o[3] (id_o[3]),
`endif
    .*);
  function automatic byte pattern(input int index);
    return byte'((index*37) ^ (index>>3) ^ (seed*91));
  endfunction
  // Ara bit-reverses the element position within each lane word.
  function automatic int source_index(input int word, lane, b);
    int reversed=0;
    for(int k=0;k<3-sew;k++) reversed=(reversed<<1)|((b>>(sew+k))&1);
    return word*32+(reversed*4+lane)*(1<<sew)+(b% (1<<sew));
  endfunction
  always @(negedge clk_i) if (rst_ni) begin
    cycles++;
    final_i = grant_i;
    for (int lane=0; lane<4; lane++)
      grant_i[lane] = valid_o[lane] && (!pressure ||
        (cycles>20 && (cycles+lane*3)%13 < 4));
    rvalid_i = cycles>5 && sent*InputBytes<nbytes;
    addrvalid_i = cycles>5 && sent*InputBytes<nbytes;
`ifdef SLDU_PROBE
    // Let the first word traverse the operand spill before offering the second.
    // The output remains blocked until cycle 21, so this targets two live entries.
    if(pressure && sent==1 && cycles<12) rvalid_i=0;
    for (int lane=0;lane<4;lane++)
      for(int b=0;b<8;b++) rdata_i[lane*64+b*8+:8]=pattern(source_index(sent,lane,b));
`else
    for (int b=0;b<InputBytes;b++) rdata_i[b*8+:8]=pattern(sent*InputBytes+b);
`endif
    if (cycles>2000) $fatal(1,"TIMEOUT sent=%0d writes=%p done=%0d",sent,writes,completed);
  end
  always @(posedge clk_i) if (rst_ni) begin
    for (int lane=0; lane<4; lane++) begin
      if (held[lane]) begin
        held_cycles++;
        if (!valid_o[lane] || {id_o[lane],addr_o[lane],data_o[lane],be_o[lane]} !== held_payload[lane])
          $fatal(1,"HELD_CHANGED cycle=%0d lane=%0d got=%h expected=%h",cycles,lane,
            {id_o[lane],addr_o[lane],data_o[lane],be_o[lane]},held_payload[lane]);
      end
      held[lane]=valid_o[lane]&&!grant_i[lane];
      held_payload[lane]={id_o[lane],addr_o[lane],data_o[lane],be_o[lane]};
      if (valid_o[lane]) begin
        if (writes[lane]*32>=nbytes) $fatal(1,"EXTRA_RESULT lane=%0d",lane);
        if (id_o[lane]!==3 || addr_o[lane]!==10'(32+writes[lane]))
          $fatal(1,"METADATA lane=%0d id=%0d addr=%0d word=%0d",lane,id_o[lane],addr_o[lane],writes[lane]);
        for(int b=0;b<8;b++) begin
          automatic int index=source_index(writes[lane],lane,b);
          if(be_o[lane][b] !== (index<nbytes)) $fatal(1,"BYTE_ENABLE lane=%0d b=%0d index=%0d",lane,b,index);
          if(index<nbytes && data_o[lane][b*8+:8] !== pattern(index))
            $fatal(1,"DATA cycle=%0d lane=%0d index=%0d got=%h expected=%h",cycles,lane,index,data_o[lane][b*8+:8],pattern(index));
        end
      end
      if(valid_o[lane]&&grant_i[lane]) writes[lane]++;
    end
    if(rvalid_i&&rready_o) begin
      if (|held) fill_while_held++;
      if (|grant_i) simultaneous++;
      sent++;
    end
    if (|done_o) begin
      if(done_o!==8'h08 || completed) $fatal(1,"BAD_COMPLETION %h",done_o);
      foreach(writes[lane]) if(writes[lane]!=(nbytes+31)/32) $fatal(1,"EARLY_COMPLETION");
      if(sent!=(nbytes+InputBytes-1)/InputBytes) $fatal(1,"EARLY_R_COMPLETION");
      completed++;
    end
  end
  initial begin
    void'($value$plusargs("SEW=%d",sew));
    void'($value$plusargs("BYTES=%d",bytes_arg));
    void'($value$plusargs("PRESSURE=%d",pressure));
    void'($value$plusargs("SEED=%d",seed));
    nbytes=bytes_arg;
    if(nbytes<1 || nbytes>512 || nbytes%(1<<sew)) $fatal(1,"INVALID_CASE");
    vl_i=nbytes>>sew; sew_i=2'(sew); len_i=(nbytes+15)/16-1;
    repeat(15) @(negedge clk_i);
    rst_ni=1;
    @(negedge clk_i); req_i=1;
    do @(posedge clk_i); while(!ready_o);
    @(negedge clk_i); req_i=0;
    wait(completed==1);
    repeat(10) @(negedge clk_i);
    if(pressure && nbytes>32 && (!held_cycles || !fill_while_held)) $fatal(1,"COVERAGE_MISSING");
`ifdef SLDU_PROBE
    $write("SLDU_QUEUE_PASS ");
`else
    $write("VLDU_QUEUE_PASS ");
`endif
    $display("sew=%0d bytes=%0d pressure=%0d seed=%0d held=%0d fill_held=%0d simultaneous=%0d",sew,nbytes,pressure,seed,held_cycles,fill_while_held,simultaneous);
    $finish;
  end
endmodule
