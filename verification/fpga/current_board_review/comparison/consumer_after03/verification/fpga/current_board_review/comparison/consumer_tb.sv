module consumer_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  bit clk=0;
  always #5 clk=~clk;
  logic rst, valid, ready;
  pe_req_t req;
  pe_resp_t resp;
  elen_t [3:0][NrMaskFUnits+1:0] operands;
  logic [3:0][NrMaskFUnits+1:0] operand_valid, operand_ready;
  logic [3:0] result_req, grant, final_grant;
  logic [3:0][9:0] result_addr;
  logic [3:0][63:0] result_data;
  logic [3:0][7:0] result_be;
  logic [4:0] flags;
  logic flags_valid;
  int sew, vl, start, nv_index, pattern, integer_op, stalls, unmasked;
  int cycle, slices, accepted, pulses, nv_pulses, output_stalls, input_stalls;
  int alu_seen[4], mask_seen[4], vd_seen[4];
  int writes[1024];
  bit actual[1024];
  bit active, done;

  function automatic int seq_byte(int lane, int offset, int ew);
    int reversed;
    reversed=0;
    for(int k=0;k<3-ew;k++) reversed=(reversed<<1)|(((offset>>ew)>>k)&1);
    return ((reversed*4+lane)<<ew)+(offset&((1<<ew)-1));
  endfunction
  function automatic bit pred(int e);
    return pattern==0 || (pattern==1 && e%2==1) || (pattern==3 && e==nv_index);
  endfunction
  function automatic bit result_bit(int e);
    return e%3==1;
  endfunction
  function automatic bit nv_bit(int e);
    return nv_index==-2 || e==nv_index;
  endfunction

  masku #(.NrLanes(4),.VLEN(1024),.vaddr_t(logic[9:0]),
    .pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t)) dut (
    .clk_i(clk),.rst_ni(rst),.pe_req_i(req),.pe_req_valid_i(valid),
    .pe_vinsn_running_i('1),.pe_req_ready_o(ready),.pe_resp_o(resp),
    .fflags_o(flags),.fflags_valid_o(flags_valid),
    .masku_operand_i(operands),.masku_operand_valid_i(operand_valid),
    .masku_operand_ready_o(operand_ready),.masku_result_req_o(result_req),
    .masku_result_addr_o(result_addr),.masku_result_wdata_o(result_data),
    .masku_result_be_o(result_be),.masku_result_gnt_i(grant),
    .masku_result_final_gnt_i(final_grant),.masku_vrgat_req_ready_i('1),
    .lane_mask_ready_i('0),.vldu_mask_ready_i(1'b0),
    .vstu_mask_ready_i(1'b0),.sldu_mask_ready_i(1'b0));

  always @(negedge clk) if(rst && active) begin
    grant=(stalls && cycle<90)?'0:result_req;
    for(int lane=0;lane<4;lane++) begin
      operand_valid[lane]='0;
      // The unselected functional-unit stream deliberately carries NV poison.
      operands[lane][2+MaskFUAlu]='1;
      operands[lane][2+MaskFUMFpu]='1;
      operand_valid[lane][2+(integer_op?MaskFUMFpu:MaskFUAlu)]=1;
      operand_valid[lane][2+(integer_op?MaskFUAlu:MaskFUMFpu)]=
        alu_seen[lane]<slices && (!stalls || cycle>=25+lane);
      operands[lane][2+(integer_op?MaskFUAlu:MaskFUMFpu)]='0;
      for(int b=0;b<8;b++) if((b% (1<<sew))==0) begin
        automatic int e;
        e=alu_seen[lane]*(32>>sew)+(seq_byte(lane,b,sew)>>sew);
        operands[lane][2+(integer_op?MaskFUAlu:MaskFUMFpu)][8*b]=result_bit(e);
        operands[lane][2+(integer_op?MaskFUAlu:MaskFUMFpu)][8*b+2]=nv_bit(e);
      end
      operand_valid[lane][0]=!unmasked && mask_seen[lane]<(vl+255)/256 && (!stalls || cycle>=12+lane);
      operand_valid[lane][1]=vd_seen[lane]<(vl+255)/256 && (!stalls || cycle>=18+lane);
      for(int b=0;b<8;b++) for(int k=0;k<8;k++) begin
        operands[lane][0][8*b+k]=pred(mask_seen[lane]*256+seq_byte(lane,b,0)*8+k);
        operands[lane][1][8*b+k]=(8'h5b>>k)&1;
      end
    end
  end

  always @(posedge clk) begin
    bit accept, want_nv;
    int channel, base;
    final_grant<=rst?(result_req&grant):'0;
    accept=0; want_nv=0;
    if(rst && active) begin
      cycle++;
      channel=2+(integer_op?MaskFUAlu:MaskFUMFpu);
      accept=1;
      for(int lane=0;lane<4;lane++) accept &= operand_valid[lane][channel] && operand_ready[lane][channel];
      if(accept) begin
        base=accepted*(32>>sew);
        for(int e=base;e<base+(32>>sew);e++)
          want_nv |= nv_bit(e) && e>=start && e<vl && (unmasked || pred(e));
        $display("ACCEPT cycle=%0d slice=%0d base=%0d want_nv=%b payload1=%h",cycle,accepted,base,want_nv,operands[1][channel]);
        accepted++;
      end
      for(int lane=0;lane<4;lane++) begin
        if(operand_valid[lane][channel] && operand_ready[lane][channel]) begin
          assert(accept) else $fatal(1,"partial result-slice accept");
          alu_seen[lane]++;
        end
        if(operand_valid[lane][channel] && !operand_ready[lane][channel]) input_stalls++;
        if(operand_valid[lane][0] && operand_ready[lane][0]) mask_seen[lane]++;
        if(operand_valid[lane][1] && operand_ready[lane][1]) vd_seen[lane]++;
        if(result_req[lane] && !grant[lane]) output_stalls++;
        if(result_req[lane] && grant[lane]) begin
          $display("WRITE cycle=%0d lane=%0d addr=%0d be=%h data=%h",cycle,lane,result_addr[lane],result_be[lane],result_data[lane]);
          for(int b=0;b<8;b++) if(result_be[lane][b]) for(int k=0;k<8;k++) begin
            automatic int e;
            e=(int'(result_addr[lane])-96)*256+seq_byte(lane,b,0)*8+k;
            assert(e>=0 && e<1024) else $fatal(1,"bad result address");
            actual[e]=result_data[lane][8*b+k]; writes[e]++;
          end
        end
      end
      if(resp.vinsn_done[3]) done=1;
    end
    #1;
    if(rst && active) begin
      assert(flags_valid === (accept && !integer_op)) else
        $fatal(1,"flag pulse is not exact accepted-slice event cycle=%0d got=%b accept=%b integer=%0d",cycle,flags_valid,accept,integer_op);
      assert(flags === ((accept && !integer_op && want_nv)?5'h10:5'h00)) else
        $fatal(1,"flags mismatch cycle=%0d got=%h want_nv=%b",cycle,flags,want_nv);
      if(flags_valid) begin pulses++; if(flags[4]) nv_pulses++; end
    end
  end

  initial begin
    sew=1; vl=8; start=0; nv_index=5; pattern=2; integer_op=0; stalls=0; unmasked=0;
    void'($value$plusargs("SEW=%d",sew)); void'($value$plusargs("VL=%d",vl));
    void'($value$plusargs("START=%d",start)); void'($value$plusargs("NV=%d",nv_index));
    void'($value$plusargs("PATTERN=%d",pattern)); void'($value$plusargs("INTEGER=%d",integer_op));
    void'($value$plusargs("STALLS=%d",stalls)); void'($value$plusargs("UNMASKED=%d",unmasked));
    rst=0;valid=0;active=0;done=0;final_grant=0;grant=0;req='0;operands='0;operand_valid='0;
    cycle=0;accepted=0;pulses=0;nv_pulses=0;input_stalls=0;output_stalls=0;
    slices=(vl+(32>>sew)-1)/(32>>sew);
    for(int l=0;l<4;l++) begin alu_seen[l]=0;mask_seen[l]=0;vd_seen[l]=0; end
    for(int e=0;e<1024;e++) begin actual[e]=(8'h5b>>(e%8))&1;writes[e]=0; end
    repeat(5) @(negedge clk);
    rst=1;req.id=3;req.op=integer_op?VMSEQ:VMFEQ;req.vfu=VFU_MaskUnit;
    req.vm=unmasked;req.vd=24;req.use_vd=1;req.use_vd_op=1;
    req.vs1=16;req.vs2=8;req.use_vs1=1;req.use_vs2=1;
    req.vl=vl;req.vstart=start;req.vtype.vsew=vew_e'(sew);
    req.vtype.vlmul=LMUL_8;req.emul=LMUL_8;
    req.eew_vs1=vew_e'(sew);req.eew_vs2=vew_e'(sew);
    req.eew_vd_op=EW8;req.eew_vmask=EW8;
    @(negedge clk);valid=1;
    @(negedge clk);valid=0;active=1;
    for(int n=0;n<500 && !done;n++) @(negedge clk);
    assert(done && accepted==slices) else $fatal(1,"completion/slice count done=%b accepted=%0d expected=%0d",done,accepted,slices);
    repeat(6) @(negedge clk);
    for(int e=0;e<1024;e++) begin
      automatic bit wanted;
      wanted=(e>=start && e<vl && (unmasked || pred(e)))?result_bit(e):((8'h5b>>(e%8))&1);
      assert(actual[e]===wanted) else $fatal(1,"mask data mismatch e=%0d got=%b expected=%b",e,actual[e],wanted);
      assert(writes[e]==int'(e<((vl+255)/256)*256)) else $fatal(1,"wrong write footprint e=%0d count=%0d",e,writes[e]);
    end
    if(stalls) assert(input_stalls>0 && output_stalls>0) else $fatal(1,"stall coverage missing");
    $display("CONSUMER_PASS sew=%0d vl=%0d start=%0d nv=%0d pattern=%0d integer=%0d unmasked=%0d slices=%0d pulses=%0d nv_pulses=%0d input_stalls=%0d output_stalls=%0d",
      sew,vl,start,nv_index,pattern,integer_op,unmasked,accepted,pulses,nv_pulses,input_stalls,output_stalls);
    $finish;
  end
endmodule
