`timescale 1ns/1ps
`include "axi/typedef.svh"
package audit_types;
  typedef logic [31:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [1:0] id_t;
  typedef logic user_t;
  `AXI_TYPEDEF_ALL(audit, addr_t, id_t, data_t, strb_t, user_t)
  function automatic data_t pattern(addr_t a);
    return 64'hac01234500000000 ^ data_t'(a);
  endfunction
endpackage

// One original burst at a time. Independent expected addresses/data are
// generated from its AXI attributes, never from the DUT's counters/state.
module splitter_check(input logic clk, rst_n);
  import audit_types::*;
  import axi_pkg::*;
  audit_req_t s, m, ds, filtered;
  audit_resp_t sr, mr, dsr, filtered_resp;
  int test_id, beats, ac, wc, bc, rc, dac, dwc, dbc, drac, drc, ticks;
  bit wr, supported;
  burst_t burst;
  cache_t cache;
  atop_t atop;
  addr_t base;
  audit_req_t prev_m;
  audit_resp_t prev_s;
  bit prev_aw, prev_ar, prev_w, prev_b, prev_r;
  axi_atop_filter #(.AxiIdWidth(2), .AxiMaxWriteTxns(4),
    .axi_req_t(audit_req_t), .axi_resp_t(audit_resp_t)) filter (
    .clk_i(clk), .rst_ni(rst_n), .slv_req_i(test_id==13 ? s : audit_req_t'('0)),
    .slv_resp_o(filtered_resp), .mst_req_o(filtered), .mst_resp_i(dsr));
  assign ds = test_id==13 ? filtered : s;
  assign sr = test_id==13 ? filtered_resp : dsr;
  axi_burst_splitter #(.MaxReadTxns(4), .MaxWriteTxns(4),
    .AddrWidth(32), .DataWidth(64), .IdWidth(2), .UserWidth(1),
    .axi_req_t(audit_req_t), .axi_resp_t(audit_resp_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .slv_req_i(ds), .slv_resp_o(dsr),
    .mst_req_o(m), .mst_resp_i(mr));

  function automatic addr_t address(int n);
    return base + (burst == BURST_FIXED ? 0 : n*8);
  endfunction
  task automatic ck(bit ok, string why);
    if (!ok) $fatal(1, "SPLITTER case=%0d tick=%0d: %s", test_id, ticks, why);
  endtask
  initial begin
    s='0; mr='0;
    ac=0; wc=0; bc=0; rc=0; dac=0; dwc=0; dbc=0; drac=0; drc=0; ticks=0;
    if (!$value$plusargs("CASE=%d", test_id)) test_id=-1;
    if (test_id >= 0 && test_id < 16) begin
      wr=test_id[0]; base=32'h1800; beats=4; burst=BURST_INCR;
      cache=4'b0010; atop=0; supported=1;
      case (test_id/2)
        0: begin beats=1; cache=0; end
        1: begin burst=BURST_INCR; end
        2: begin burst=BURST_FIXED; end
        3: begin burst=BURST_WRAP; supported=0; end
        4: begin cache=0; supported=0; end
        5: begin cache=0; burst=BURST_FIXED; supported=0; end
        6: begin if (wr) begin atop=6'h10; beats=1; supported=0; end end
        7: begin beats=1; burst=BURST_FIXED; cache=0; end
      endcase
      wait(rst_n); @(negedge clk);
      while ((wr ? bc<1 : rc<beats) && ticks<1000) begin
        s.aw='0; s.aw.id=2; s.aw.addr=base; s.aw.len=beats-1;
        s.aw.size=3; s.aw.burst=burst; s.aw.cache=cache; s.aw.atop=atop;
        s.aw_valid=wr && ac==0;
        s.ar='0; s.ar.id=2; s.ar.addr=base; s.ar.len=beats-1;
        s.ar.size=3; s.ar.burst=burst; s.ar.cache=cache;
        s.ar_valid=!wr && ac==0;
        s.w='0; s.w.data=pattern(base + wc*8); s.w.strb=8'hff;
        s.w.last=wc==beats-1; s.w_valid=wr && wc<beats;
        s.b_ready=ticks%7>=3; s.r_ready=ticks%9>=4;
        mr='0; mr.aw_ready=ticks%5>=2; mr.ar_ready=ticks%4>=1;
        mr.w_ready=ticks%6>=3;
        mr.b_valid=dbc<dac && dbc<dwc; mr.b.id=2; mr.b.resp=RESP_OKAY;
        mr.r_valid=drc<drac; mr.r.id=2; mr.r.resp=RESP_OKAY;
        mr.r.last=1; mr.r.data=pattern(address(drc));
        @(posedge clk);
        if (prev_aw) ck(m.aw_valid && m.aw==prev_m.aw,"AW changed under backpressure");
        if (prev_ar) ck(m.ar_valid && m.ar==prev_m.ar,"AR changed under backpressure");
        if (prev_w) ck(m.w_valid && m.w==prev_m.w,"W changed under backpressure");
        if (prev_b) ck(sr.b_valid && sr.b==prev_s.b,"B changed under backpressure");
        if (prev_r) ck(sr.r_valid && sr.r==prev_s.r,"R changed under backpressure");
        prev_aw=m.aw_valid&&!mr.aw_ready; prev_ar=m.ar_valid&&!mr.ar_ready;
        prev_w=m.w_valid&&!mr.w_ready; prev_b=sr.b_valid&&!s.b_ready;
        prev_r=sr.r_valid&&!s.r_ready; prev_m=m; prev_s=sr;
        if (m.aw_valid && mr.aw_ready) begin
          ck(supported,"unsupported AW escaped to peripheral");
          ck(m.aw.id==2 && m.aw.addr==address(dac) && m.aw.len==0 &&
             m.aw.size==3 && m.aw.burst==burst,"wrong split AW"); dac++;
        end
        if (m.ar_valid && mr.ar_ready) begin
          ck(supported,"unsupported AR escaped to peripheral");
          ck(m.ar.id==2 && m.ar.addr==address(drac) && m.ar.len==0 &&
             m.ar.size==3 && m.ar.burst==burst,"wrong split AR"); drac++;
        end
        if (m.w_valid && mr.w_ready) begin
          ck(supported && m.w.last && m.w.strb==8'hff &&
             m.w.data==pattern(base+dwc*8),"wrong split W"); dwc++;
        end
        if (m.b_ready && mr.b_valid) dbc++;
        if (m.r_ready && mr.r_valid) drc++;
        if ((s.aw_valid && sr.aw_ready) || (s.ar_valid && sr.ar_ready)) ac++;
        if (s.w_valid && sr.w_ready) wc++;
        if (sr.b_valid && s.b_ready) begin
          ck(sr.b.id==2 && sr.b.resp==(supported?RESP_OKAY:RESP_SLVERR),"wrong B response"); bc++;
        end
        if (sr.r_valid && s.r_ready) begin
          ck(sr.r.id==2 && sr.r.resp==(supported?RESP_OKAY:RESP_SLVERR) &&
             sr.r.last==(rc==beats-1),"wrong R status/last");
          if (supported) ck(sr.r.data==pattern(address(rc)),"wrong reassembled R data"); rc++;
        end
        ticks++; @(negedge clk);
      end
      ck(ticks<1000 && ac==1,"bounded completion");
      ck(wr ? wc==beats && bc==1 : rc==beats,"upstream response count");
      ck(wr ? dac==(supported?beats:0) && dwc==dac && dbc==dac :
              drac==(supported?beats:0) && drc==drac,"downstream count");
      $display("AUDIT_PASS splitter case=%0d beats=%0d write=%0d supported=%0d cycles=%0d",
               test_id,beats,wr,supported,ticks); $finish;
    end
  end
endmodule

module demux_check #(parameter int Limit=4)(input logic clk, rst_n);
  import audit_types::*;
  import axi_pkg::*;
  audit_req_t s;
  audit_resp_t sr;
  audit_req_t [1:0] m;
  audit_resp_t [1:0] mr;
  logic awsel, arsel;
  int test_id, mode, awn, arn, wn, bn, rn, checks;
  int aw_pending[4], r_pending[4], completed_w[4], aw_port[4], r_port[4];
  typedef struct packed {int port_id; id_t id; addr_t addr;} write_item;
  write_item writes[$], item;
  data_t r_gold[4][$];
  audit_req_t [1:0] pm;
  audit_resp_t ps;
  bit [1:0] paw, par, pw;
  bit pb, pr;
  axi_demux_simple #(.AxiIdWidth(2), .AtopSupport(1),
    .axi_req_t(audit_req_t), .axi_resp_t(audit_resp_t),
    .NoMstPorts(2), .MaxTrans(Limit), .AxiLookBits(1)) dut (
    .clk_i(clk), .rst_ni(rst_n), .test_i(1'b0), .slv_req_i(s),
    .slv_aw_select_i(awsel), .slv_ar_select_i(arsel), .slv_resp_o(sr),
    .mst_reqs_o(m), .mst_resps_i(mr));
  task automatic ck(bit ok, string why);
    checks++;
    if (!ok) $fatal(1,"DEMUX limit=%0d case=%0d: %s",Limit,test_id,why);
  endtask
  // Scoreboard sees only public handshakes, complete payloads and response order.
  always @(posedge clk) if (rst_n) begin
    for (int p=0;p<2;p++) begin
      if (paw[p]) ck(m[p].aw_valid && m[p].aw==pm[p].aw,"AW stability");
      if (par[p]) ck(m[p].ar_valid && m[p].ar==pm[p].ar,"AR stability");
      if (pw[p]) ck(m[p].w_valid && m[p].w==pm[p].w,"W stability");
      paw[p]=m[p].aw_valid&&!mr[p].aw_ready;
      par[p]=m[p].ar_valid&&!mr[p].ar_ready;
      pw[p]=m[p].w_valid&&!mr[p].w_ready; pm[p]=m[p];
      if (m[p].aw_valid && mr[p].aw_ready)
        ck(s.aw_valid&&sr.aw_ready&&awsel==p&&m[p].aw==s.aw,"AW route/payload");
      if (m[p].ar_valid && mr[p].ar_ready)
        ck(s.ar_valid&&sr.ar_ready&&arsel==p&&m[p].ar==s.ar,"AR route/payload");
      if (m[p].w_valid && mr[p].w_ready)
        ck(s.w_valid&&sr.w_ready&&writes.size()>0&&writes[0].port_id==p,
           "unexpected downstream W handshake");
    end
    if (pb) ck(sr.b_valid&&sr.b==ps.b,"B stability");
    if (pr) ck(sr.r_valid&&sr.r==ps.r,"R stability");
    pb=sr.b_valid&&!s.b_ready; pr=sr.r_valid&&!s.r_ready; ps=sr;
    if (s.ar_valid&&sr.ar_ready) begin
      ck(m[arsel].ar_valid&&mr[arsel].ar_ready,"AR not forwarded");
      ck(!r_pending[s.ar.id]||r_port[s.ar.id]==arsel,"same-ID R destination order");
      r_port[s.ar.id]=arsel; r_pending[s.ar.id]++;
      r_gold[s.ar.id].push_back(pattern(s.ar.addr)); arn++;
    end
    if (s.aw_valid&&sr.aw_ready) begin
      ck(m[awsel].aw_valid&&mr[awsel].aw_ready,"AW not forwarded");
      ck(!aw_pending[s.aw.id]||aw_port[s.aw.id]==awsel,"same-ID B destination order");
      aw_port[s.aw.id]=awsel; aw_pending[s.aw.id]++;
      item='{int'(awsel),s.aw.id,s.aw.addr}; writes.push_back(item); awn++;
      if (s.aw.atop[5]) begin
        ck(!r_pending[s.aw.id]||r_port[s.aw.id]==awsel,"ATOP R destination order");
        r_port[s.aw.id]=awsel; r_pending[s.aw.id]++;
        r_gold[s.aw.id].push_back(pattern(s.aw.addr));
      end
    end
    if (s.w_valid&&sr.w_ready) begin
      ck(writes.size()!=0,"W without AW"); item=writes.pop_front();
      ck(m[item.port_id].w_valid&&mr[item.port_id].w_ready&&
         m[item.port_id].w==s.w&&s.w.last&&s.w.strb==8'hff&&
         s.w.data==pattern(item.addr),"W routing/data/order");
      completed_w[item.id]++; wn++;
    end
    if (sr.b_valid&&s.b_ready) begin
      ck(aw_pending[sr.b.id]>0&&completed_w[sr.b.id]>0,"B lost/duplicated or early");
      ck(mr[aw_port[sr.b.id]].b_valid&&m[aw_port[sr.b.id]].b_ready&&
         sr.b==mr[aw_port[sr.b.id]].b,"B route/payload");
      aw_pending[sr.b.id]--; completed_w[sr.b.id]--; bn++;
    end
    if (sr.r_valid&&s.r_ready) begin
      ck(r_pending[sr.r.id]>0&&r_gold[sr.r.id].size()>0,"R lost/duplicated");
      ck(mr[r_port[sr.r.id]].r_valid&&m[r_port[sr.r.id]].r_ready&&
         sr.r==mr[r_port[sr.r.id]].r&&sr.r.last,"R route/payload");
      ck(sr.r.data==r_gold[sr.r.id].pop_front(),"R independent data/order");
      r_pending[sr.r.id]--; rn++;
    end
  end
  task automatic tick; @(posedge clk); @(negedge clk); endtask
  task automatic drain_wait(ref int counter, input int prior, input string label);
    int n; n=0;
    while(counter==prior&&n<30) begin tick(); n++; end
    ck(counter==prior+1,{label," acceptance/completion timeout"});
  endtask
  task automatic set_ar(int id,int port_id,addr_t addr);
    s.ar='0; s.ar.id=id; s.ar.addr=addr; s.ar.size=3; s.ar.burst=BURST_INCR;
    arsel=port_id; s.ar_valid=1;
  endtask
  task automatic ar(int id,int port_id,addr_t addr);
    int n; n=arn; set_ar(id,port_id,addr); drain_wait(arn,n,"AR"); s.ar_valid=0;
  endtask
  task automatic set_aw(int id,int port_id,addr_t addr,atop_t op=0);
    s.aw='0; s.aw.id=id; s.aw.addr=addr; s.aw.size=3; s.aw.burst=BURST_INCR;
    s.aw.atop=op; awsel=port_id; s.aw_valid=1;
  endtask
  task automatic aw(int id,int port_id,addr_t addr);
    int n; n=awn; set_aw(id,port_id,addr); drain_wait(awn,n,"AW"); s.aw_valid=0;
  endtask
  task automatic w(addr_t addr, int port_id=0);
    int n; n=wn; s.w='0; s.w.data=pattern(addr); s.w.strb='1; s.w.last=1; s.w_valid=1;
    mr[port_id].w_ready=0; repeat(3) tick(); ck(wn==n,"W ignored backpressure");
    mr[port_id].w_ready=1; drain_wait(wn,n,"W"); s.w_valid=0;
  endtask
  task automatic r(int id,int port_id,addr_t addr);
    int n; n=rn; mr[port_id].r='0; mr[port_id].r.id=id;
    mr[port_id].r.data=pattern(addr); mr[port_id].r.last=1; mr[port_id].r_valid=1;
    s.r_ready=0; repeat(3) tick(); ck(rn==n,"R ignored backpressure");
    s.r_ready=1; drain_wait(rn,n,"R"); mr[port_id].r_valid=0;
  endtask
  task automatic b(int id,int port_id);
    int n; n=bn; mr[port_id].b='0; mr[port_id].b.id=id; mr[port_id].b_valid=1;
    s.b_ready=0; repeat(3) tick(); ck(bn==n,"B ignored backpressure");
    s.b_ready=1; drain_wait(bn,n,"B"); mr[port_id].b_valid=0;
  endtask
  initial begin
    s='0; mr='0; awsel=0; arsel=0;
    awn=0; arn=0; wn=0; bn=0; rn=0; checks=0;
    for(int i=0;i<4;i++) begin
      aw_pending[i]=0; r_pending[i]=0; completed_w[i]=0; aw_port[i]=0; r_port[i]=0;
    end
    if (!$value$plusargs("CASE=%d",test_id)) test_id=-1;
    if (test_id>=100 && test_id%10==Limit) begin
      mode=(test_id-100)/10;
      wait(rst_n); @(negedge clk);
      for (int p=0;p<2;p++) begin mr[p].aw_ready=1; mr[p].ar_ready=1; mr[p].w_ready=1; end
      if (mode==0) begin
        for (int i=0;i<Limit;i++) ar(0,0,32'h1000+i*8);
        set_ar(0,0,32'h1000+Limit*8);
        repeat(3) tick(); ck(arn==Limit,"AR accepted above configured limit");
        r(0,0,32'h1000); drain_wait(arn,Limit,"AR unblock"); s.ar_valid=0;
        for (int i=1;i<=Limit;i++) r(0,0,32'h1000+i*8);
      end else if (mode==1) begin
        for (int i=0;i<Limit;i++) aw(0,0,32'h2000+i*8);
        set_aw(0,0,32'h2000+Limit*8);
        repeat(3) tick(); ck(awn==Limit,"AW accepted above limit/W capacity");
        w(32'h2000); repeat(2) tick(); ck(awn==Limit,"AW forgot outstanding B");
        b(0,0); drain_wait(awn,Limit,"AW unblock"); s.aw_valid=0;
        for(int i=1;i<=Limit;i++) begin w(32'h2000+i*8); b(0,0); end
      end else if (mode==2) begin
        ar(0,0,32'h3000);
        if (Limit>1) begin ar(1,1,32'h3100); r(1,1,32'h3100); end
        set_ar(0,1,32'h3200); repeat(3) tick(); ck(arn==(Limit>1?2:1),"R order bypass");
        r(0,0,32'h3000); drain_wait(arn,(Limit>1?2:1),"R destination unblock");
        s.ar_valid=0; r(0,1,32'h3200);
        aw(0,0,32'h4000); w(32'h4000);
        set_aw(0,1,32'h4100); repeat(3) tick(); ck(awn==1,"B order bypass");
        b(0,0); drain_wait(awn,1,"B destination unblock"); s.aw_valid=0;
        w(32'h4100,1); b(0,1);
      end else if (mode==3) begin
        // Two independent channels may accept on the same edge. MaxTrans is
        // a backpressure threshold, not permission to discard either response.
        for(int i=0;i<Limit-1;i++) ar(0,0,32'h5000+i*8);
        // Distinct complete IDs satisfy the ATOP protocol; their low lookup
        // bit aliases, exercising the actual per-index +2 counter update.
        set_ar(0,0,32'h5000+(Limit-1)*8); set_aw(2,0,32'h6000,6'h20);
        tick(); ck(arn==Limit&&awn==1,"AR/ATOP not accepted together");
        s.aw_valid=0; s.ar_valid=0; w(32'h6000); b(2,0);
        set_ar(0,0,32'h7000); repeat(3) tick(); ck(arn==Limit,"AR/ATOP count lost or over-limit");
        r(0,0,32'h5000); repeat(2) tick(); ck(arn==Limit,"threshold must retain both increments");
        if (Limit==1) r(2,0,32'h6000); else r(0,0,32'h5008);
        drain_wait(arn,Limit,"simultaneous accounting recovery"); s.ar_valid=0;
        for(int i=2;i<Limit;i++) r(0,0,32'h5000+i*8);
        if(Limit>1) r(2,0,32'h6000);
        r(0,0,32'h7000);
      end else if (mode==4) begin
        aw(0,0,32'h8000); set_aw(1,1,32'h8100);
        repeat(3) tick(); ck(awn==1,"W route changed before last beat");
        w(32'h8000);
        if(Limit==1) b(0,0);
        drain_wait(awn,1,"W route release"); s.aw_valid=0;
        w(32'h8100,1); b(1,1);
        if(Limit>1) b(0,0);
      end else if (mode==5) begin
        // AW/AR payload must remain stable while a selected target stalls.
        mr[0].ar_ready=0; set_ar(0,0,32'h9000);
        repeat(4) tick(); ck(arn==0,"AR ready ignored");
        mr[0].ar_ready=1; drain_wait(arn,0,"AR downstream release"); s.ar_valid=0;
        r(0,0,32'h9000);
        mr[1].aw_ready=0; set_aw(1,1,32'h9100);
        repeat(4) tick(); ck(awn==0,"AW ready ignored");
        mr[1].aw_ready=1; drain_wait(awn,0,"AW downstream release"); s.aw_valid=0;
        w(32'h9100,1); b(1,1);
      end else $fatal(1,"unknown mode");
      repeat(3) tick();
      for(int id=0;id<4;id++) ck(aw_pending[id]==0 && r_pending[id]==0 &&
        completed_w[id]==0 && r_gold[id].size()==0,"scoreboard not drained");
      ck(writes.size()==0 && awn==wn && wn==bn,"write conservation");
      $display("AUDIT_PASS demux limit=%0d mode=%0d checks=%0d AR=%0d AW=%0d W=%0d R=%0d B=%0d",
               Limit,mode,checks,arn,awn,wn,rn,bn); $finish;
    end
  end
endmodule

module axi_audit_tb;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  initial begin repeat(4) @(negedge clk); rst_n=1; end
  initial begin #200000; $fatal(1,"global bounded watchdog"); end
  splitter_check split(clk,rst_n);
  for(genvar n=1;n<=4;n++) begin: limits
    demux_check #(.Limit(n)) demux(clk,rst_n);
  end
endmodule
