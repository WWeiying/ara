`timescale 1ns/1ps
module bank_error_tb;
  import audit_types::*;
  import axi_pkg::*;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  audit_req_t s;
  audit_resp_t sr;
  logic [3:0] req, gnt, we, rv, err, ex;
  logic [3:0][31:0] addr;
  logic [3:0][15:0] wd, rd;
  logic [3:0][1:0] strb;
  logic [15:0] mem[4];
  logic [3:0] inject_error, inject_ex;
  int cycles=0, checks=0, test_id;
  data_t shadow;
  axi_to_detailed_mem #(.axi_req_t(audit_req_t), .axi_resp_t(audit_resp_t),
    .AddrWidth(32), .DataWidth(64), .IdWidth(2), .UserWidth(1),
    .NumBanks(4), .BufDepth(2)) dut (
    .clk_i(clk), .rst_ni(rst_n), .busy_o(), .axi_req_i(s), .axi_resp_o(sr),
    .mem_req_o(req), .mem_gnt_i(gnt), .mem_addr_o(addr), .mem_wdata_o(wd),
    .mem_strb_o(strb), .mem_we_o(we), .mem_atop_o(), .mem_lock_o(),
    .mem_id_o(), .mem_user_o(), .mem_cache_o(), .mem_prot_o(), .mem_qos_o(),
    .mem_region_o(), .mem_rvalid_i(rv), .mem_rdata_i(rd), .mem_err_i(err), .mem_exokay_i(ex));
  always_comb for(int i=0;i<4;i++) gnt[i]=(cycles+i)%4!=0;
  always @(posedge clk) begin
    cycles<=cycles+1;
    rv<=req & gnt;
    err<=inject_error & req & gnt;
    ex<=inject_ex & req & gnt;
    for(int i=0;i<4;i++) if(req[i] && gnt[i]) begin
      rd[i]<=mem[i];
      if(we[i]) for(int b=0;b<2;b++) if(strb[i][b]) mem[i][8*b+:8]<=wd[i][8*b+:8];
    end
  end
  task automatic ck(bit ok,string why);
    checks++; if(!ok) $fatal(1,"BANK case=%0d: %s",test_id,why);
  endtask
  task automatic read_word(int offset,int size,logic[3:0] e,logic[3:0] x,bit lock);
    bit accepted, done;
    int n;
    logic [3:0] active;
    resp_t want;
    audit_resp_t prior;
    bit held;
    active=0;
    // Byte membership reference, not the RTL's bank-range expression.
    for(int b=offset;b<offset+(1<<size);b++) active[b/2]=1;
    want=(|(active&e))?RESP_SLVERR:((lock&&((active&x)==active))?RESP_EXOKAY:RESP_OKAY);
    inject_error=e; inject_ex=x; accepted=0; done=0; held=0; n=0;
    s='0; s.ar.addr=32'h80+offset; s.ar.size=size; s.ar.id=1;
    s.ar.burst=BURST_INCR; s.ar.lock=lock; s.ar_valid=1;
    while(!done&&n<100) begin
      s.r_ready=n%7>=4;
      @(posedge clk);
      if(held) ck(sr.r_valid&&sr.r==prior.r,"R stability");
      held=sr.r_valid&&!s.r_ready; prior=sr;
      if(s.ar_valid&&sr.ar_ready) accepted=1;
      if(sr.r_valid&&s.r_ready) begin
        ck(sr.r.id==1&&sr.r.last&&sr.r.resp==want,
          $sformatf("read offset=%0d size=%0d err=%h ex=%h got=%h want=%h",offset,size,e,x,sr.r.resp,want));
        ck(sr.r.data==shadow,"read assembly/data"); done=1;
      end
      @(negedge clk); if(accepted) s.ar_valid=0; n++;
    end
    ck(done&&accepted,"read bounded completion"); s='0;
  endtask
  task automatic write_word(strb_t mask,data_t value);
    bit awdone,wdone,done; int n;
    awdone=0; wdone=0; done=0; n=0; inject_error=0; inject_ex=0;
    s='0; s.aw.addr=32'h80; s.aw.id=2; s.aw.size=3; s.aw.burst=BURST_INCR;
    s.aw_valid=1; s.w_valid=1; s.w.last=1; s.w.data=value; s.w.strb=mask;
    while(!done&&n<100) begin
      s.b_ready=n%7>=4;
      @(posedge clk);
      if(s.aw_valid&&sr.aw_ready) awdone=1;
      if(s.w_valid&&sr.w_ready) wdone=1;
      if(sr.b_valid&&s.b_ready) begin ck(sr.b.id==2&&sr.b.resp==RESP_OKAY,"normal B"); done=1; end
      @(negedge clk); s.aw_valid=!awdone; s.w_valid=!wdone; n++;
    end
    ck(done&&awdone&&wdone,"write bounded completion");
    for(int b=0;b<8;b++) if(mask[b]) shadow[b*8+:8]=value[b*8+:8]; s='0;
  endtask
  initial begin
    s='0; rv=0; err=0; ex=0; inject_error=0; inject_ex=0; shadow=64'h76543210fedcba98;
    for(int i=0;i<4;i++) mem[i]=shadow[i*16+:16];
    if(!$value$plusargs("CASE=%d",test_id)) test_id=0;
    repeat(4) @(negedge clk); rst_n=1; @(negedge clk);
    if(test_id==0) begin
      for(int size=0;size<=3;size++) for(int off=0;off<8;off+=(1<<size))
        read_word(off,size,0,0,0);
      write_word(8'hc0,64'h1122334455667788); read_word(0,3,0,0,0);
      write_word(8'h35,64'hcafebabedeadbeef); read_word(0,3,0,0,0);
      write_word(0,0); read_word(0,3,0,0,0);
    end else if(test_id==1) begin
      for(int size=0;size<=3;size++) for(int off=0;off<8;off+=(1<<size))
        for(int bank=0;bank<4;bank++) read_word(off,size,4'(1<<bank),0,0);
    end else if(test_id==2) begin
      for(int size=0;size<=3;size++) for(int off=0;off<8;off+=(1<<size))
        for(int mask=0;mask<16;mask++) read_word(off,size,0,4'(mask),1);
    end else $fatal(1,"unknown bank case");
    $display("AUDIT_PASS bank case=%0d checks=%0d cycles=%0d",test_id,checks,cycles); $finish;
  end
  initial begin #200000; $fatal(1,"bank watchdog"); end
endmodule
