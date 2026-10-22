module gather_prestart_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst, valid, ready;
  pe_req_t req;
  pe_resp_t resp;
  elen_t [3:0][NrMaskFUnits+1:0] operands;
  logic [3:0][NrMaskFUnits+1:0] operand_valid, operand_ready;
  logic [3:0] result_req, final_gnt, gather_valid;
  logic [3:0][9:0] result_addr;
  logic [3:0][63:0] result_data;
  logic [3:0][7:0] result_be;
  vrgat_req_t gather_req;
  vrgat_req_t pending[4][$];
  byte unsigned source_bytes[128], actual[128], golden[128];
  int writes[128];
  int sew, start, vl, mode, masked, pattern, scalar_index;
  int cycle, requests, last_requests, prefix_bytes, mismatches, idx_word;
  int index_seen[4];
  bit done, active;

  // Independent inverse of the four-lane bit-reversed subword VRF layout.
  function automatic int seq_byte(int lane, int offset, int ew);
    int reversed;
    reversed = 0;
    for (int k=0; k<3-ew; k++)
      reversed = (reversed << 1) | (((offset >> ew) >> k) & 1);
    return ((reversed * 4 + lane) << ew) + (offset & ((1 << ew)-1));
  endfunction

  function automatic int index_at(int element);
    if (mode == 0) return scalar_index;
    return (element * 7 + 3) % (128 >> sew);
  endfunction

  function automatic bit predicate_at(int element);
    return pattern == 0 || (pattern == 1 && element % 2 == 1);
  endfunction

  masku #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic[9:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) dut (
    .clk_i(clk), .rst_ni(rst), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('1), .pe_req_ready_o(ready), .pe_resp_o(resp),
    .masku_operand_i(operands), .masku_operand_valid_i(operand_valid),
    .masku_operand_ready_o(operand_ready), .masku_result_req_o(result_req),
    .masku_result_addr_o(result_addr), .masku_result_wdata_o(result_data),
    .masku_result_be_o(result_be), .masku_result_gnt_i(result_req),
    .masku_result_final_gnt_i(final_gnt), .masku_vrgat_req_valid_o(gather_valid),
    .masku_vrgat_req_ready_i('1), .masku_vrgat_req_o(gather_req),
    .lane_mask_ready_i('0), .vldu_mask_ready_i(1'b0),
    .vstu_mask_ready_i(1'b0), .sldu_mask_ready_i(1'b0));

  always @(posedge clk) begin
    final_gnt <= rst ? result_req : '0;
    if (rst && active) begin
      cycle++;
      for (int lane=0; lane<4; lane++) begin
        if (operand_valid[lane][2+MaskFUAlu] && operand_ready[lane][2+MaskFUAlu])
          index_seen[lane]++;
        if (operand_valid[lane][0] && operand_ready[lane][0])
          operand_valid[lane][0] <= 0;
        if (operand_valid[lane][1] && operand_ready[lane][1]) begin
          automatic vrgat_req_t retired;
          retired = pending[lane].pop_front();
        end
        if (gather_valid[lane]) begin
          assert(gather_req.vs == 8 && gather_req.eew == vew_e'(sew) && gather_req.id == 3)
            else $fatal(1, "Bad source request");
          if (!gather_req.no_data) pending[lane].push_back(gather_req);
          if (lane == 0) begin
            requests++;
            if (gather_req.is_last_req) last_requests++;
            $display("FETCH cycle=%0d idx_per_lane=%0d no_data=%b last=%b", cycle,
              gather_req.idx, gather_req.no_data, gather_req.is_last_req);
          end
        end
        if (result_req[lane]) begin
          $display("WRITE cycle=%0d lane=%0d addr=%0d be=%02h data=%016h", cycle,
            lane, result_addr[lane], result_be[lane], result_data[lane]);
          for (int b=0; b<8; b++) if (result_be[lane][b]) begin
            automatic int byte_index;
            byte_index = (int'(result_addr[lane])-96)*32 + seq_byte(lane,b,sew);
            assert(byte_index >= 0 && byte_index < 128) else $fatal(1,"Bad destination");
            actual[byte_index] = result_data[lane][8*b +: 8];
            writes[byte_index]++;
            if (byte_index < (start << sew)) prefix_bytes++;
          end
        end
      end
      if (resp.vinsn_done[3]) done = 1;
    end
  end

  // Respond only to external gather requests, using the addressed source word.
  // MaskB carries fetched vs2 data, never old destination or expected results.
  always @(negedge clk) if (rst && active) begin
    for (int lane=0; lane<4; lane++) begin
      operand_valid[lane][1] = pending[lane].size() != 0;
      if (pending[lane].size() != 0) begin
        automatic int base;
        base = (int'(pending[lane][0].idx) / (8 >> sew)) * 32;
        for (int b=0; b<8; b++)
          operands[lane][1][8*b +: 8] = source_bytes[base + seq_byte(lane,b,sew)];
      end
      operand_valid[lane][2+MaskFUAlu] = index_seen[lane] < ((vl+(32 >> idx_word)-1)/(32 >> idx_word));
      for (int b=0; b<8; b++) begin
        automatic int pos, element, value;
        pos = index_seen[lane]*32 + seq_byte(lane,b,idx_word);
        element = pos >> idx_word;
        value = index_at(element);
        operands[lane][2+MaskFUAlu][8*b +: 8] = value >> (8*(pos % (1 << idx_word)));
      end
    end
  end

  initial begin
    sew=1; start=1; vl=2; mode=0; masked=1; pattern=0; scalar_index=0;
    void'($value$plusargs("SEW=%d",sew));
    void'($value$plusargs("START=%d",start));
    void'($value$plusargs("VL=%d",vl));
    void'($value$plusargs("MODE=%d",mode));
    void'($value$plusargs("MASKED=%d",masked));
    void'($value$plusargs("PATTERN=%d",pattern));
    void'($value$plusargs("INDEX=%d",scalar_index));
    idx_word = mode == 2 ? 1 : sew;
    rst=0; valid=0; active=0; done=0; final_gnt=0; req='0;
    operands='0; operand_valid='0;
    cycle=0; requests=0; last_requests=0; prefix_bytes=0; mismatches=0;
    for (int lane=0; lane<4; lane++) index_seen[lane]=0;
    for (int b=0; b<128; b++) begin
      source_bytes[b] = (64'(1000 + (b >> sew))) >> (8*(b % (1 << sew)));
      actual[b] = 64'd91 >> (8*(b % (1 << sew)));
      golden[b] = actual[b]; writes[b]=0;
    end
    // Architectural oracle uses stimulus indices, independently of DUT requests.
    for (int i=start; i<vl; i++) if (!masked || predicate_at(i))
      for (int b=0; b<(1 << sew); b++)
        golden[(i << sew)+b] = index_at(i) < (128 >> sew)
          ? source_bytes[(index_at(i) << sew)+b] : 0;
    repeat(5) @(negedge clk);
    rst=1;
    req.id=3; req.op=mode == 2 ? VRGATHEREI16 : VRGATHER;
    req.vfu=VFU_MaskUnit; req.vm=!masked; req.vd=24; req.use_vd=1;
    req.vs2=8; req.use_vs2=1; req.vs1=16; req.use_vs1=mode != 0;
    req.use_scalar_op=mode == 0; req.scalar_op=scalar_index;
    req.vl=vl; req.vstart=start; req.vtype.vsew=vew_e'(sew);
    req.vtype.vlmul=LMUL_1; req.emul=LMUL_1;
    req.eew_vs2=vew_e'(idx_word); req.eew_vs1=vew_e'(idx_word);
    req.eew_vd_op=vew_e'(sew); req.eew_vmask=EW8;
    @(negedge clk); valid=1;
    @(negedge clk); valid=0;
    for (int lane=0; lane<4; lane++) begin
      operand_valid[lane][0]=masked;
      for (int b=0; b<8; b++)
        for (int k=0; k<8; k++)
          operands[lane][0][8*b+k]=predicate_at(seq_byte(lane,b,0)*8+k);
    end
    active=1;
    for (int n=0; n<600 && !done; n++) @(negedge clk);
    active=0;
    assert(done && last_requests == 1) else $fatal(1,"Completion failed");
    for (int b=0; b<128; b++) begin
      automatic bit should_write;
      should_write = (b >> sew) >= start && (b >> sew) < vl &&
                     (!masked || predicate_at(b >> sew));
      if (actual[b] !== golden[b]) begin
        mismatches++;
        $display("MISMATCH byte=%0d expected=%0d actual=%0d",b,golden[b],actual[b]);
      end
      if (!$test$plusargs("EXPECT_BUG"))
        assert(writes[b] == int'(should_write)) else $fatal(1,"Wrong BE footprint byte=%0d writes=%0d",b,writes[b]);
    end
    for (int lane=0; lane<4; lane++)
      assert(pending[lane].size() == 0) else $fatal(1,"Undrained response");
    $display("RESULT sew=%0d start=%0d vl=%0d mode=%0d masked=%0d pattern=%0d cycles=%0d requests=%0d prefix_bytes=%0d mismatches=%0d first16=%0d second16=%0d",
      sew,start,vl,mode,masked,pattern,cycle,requests,prefix_bytes,mismatches,
      {actual[1],actual[0]},{actual[3],actual[2]});
    if ($test$plusargs("EXPECT_BUG")) begin
      assert(sew==1 && start==1 && vl==2 && mode==0 && masked==1 && pattern==0 &&
        prefix_bytes==2 && mismatches==2 && {actual[1],actual[0]}==1000 &&
        {actual[3],actual[2]}==1000) else $fatal(1,"Wrong failure signature");
      $display("GATHER_EXPECTED_BUG_REPRODUCED");
    end else begin
      assert(prefix_bytes==0 && mismatches==0) else $fatal(1,"Architectural mismatch");
      $display("GATHER_PRESTART_PASS");
    end
    $finish;
  end
endmodule
