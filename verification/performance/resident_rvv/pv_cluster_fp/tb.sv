// SPDX-License-Identifier: Apache-2.0
// Numerical integration only: production VMFPU arithmetic, independent golden records.
module resident_pv_cluster_fp_tb;
  import fpnew_pkg::*;
  logic clk_i = 0;
  always #5 clk_i = !clk_i;
  logic rst_ni = 0, start_valid_i = 0, start_ready_o;
  logic [3:0] start_active_i = 0, active_o;
  logic [5:0] cmd_elements_i;
  logic cmd_two_heads_i;
  logic [6:0] cmd_tokens_i;
  logic [2:0] cmd_rm_i;
  logic abort_i = 0, abort_rejected_o, busy_o, commit_authorized_o, fatal_error_o;
  logic [3:0] seed_valid_i = 0, seed_ready_o;
  logic [3:0][63:0] seed_data_i;
  logic stream_valid_i = 0, stream_ready_o, stream_is_value_i;
  logic [3:0][63:0] stream_data_i;
  logic [3:0] fpu_valid_o, fpu_ready_i, fpu_result_valid_i, fpu_result_ready_o;
  logic [3:0][2:0][63:0] fpu_operands_o;
  logic [3:0][3:0] fpu_tag_o, fpu_mask_o, fpu_result_tag_i;
  logic [3:0][2:0] fpu_rm_o;
  logic [3:0][63:0] fpu_result_i;
  logic [3:0][4:0] fpu_result_flags_i;
  logic [3:0] result_valid_o, result_ready_i = 0, final_ack_i = 0, ack_rejected_o;
  logic [3:0][63:0] result_data_o;
  logic [3:0][3:0] result_slot_o;
  logic [3:0][7:0] result_be_o;
  logic [3:0][4:0] outstanding_o;
  logic done_valid_o, done_ready_i = 0, done_error_o;
  logic [4:0] done_flags_o;
  logic [3:0] gate = 0, adapter_ready, adapter_held = 0;
  akv_resident_pv_cluster dut (.*);
  for (genvar l=0; l<4; l++) begin : gen_fpu
    status_t status;
    assign fpu_ready_i[l] = gate[l] && adapter_ready[l];
    assign fpu_result_flags_i[l] = status;
    resident_vmfpu_adapter adapter (
      .clk_i, .rst_ni, .borrow_busy_i(busy_o), .operands_i(fpu_operands_o[l]),
      .is_boxed_i(3'b111), .rnd_mode_i(roundmode_e'(fpu_rm_o[l])),
      .op_i(FMADD), .op_mod_i(1'b0), .vectorial_op_i(1'b1),
      .tag_i(fpu_tag_o[l]), .simd_mask_i(fpu_mask_o[l]),
      .in_valid_i(fpu_valid_o[l] && gate[l]), .in_ready_o(adapter_ready[l]),
      .flush_i(1'b0), .result_o(fpu_result_i[l]), .status_o(status),
      .extension_bit_o(), .tag_o(fpu_result_tag_i[l]),
      .out_valid_o(fpu_result_valid_i[l]), .out_ready_i(fpu_result_ready_o[l]), .busy_o()
    );
  end

  typedef struct packed {
    logic [3:0] mask;
    logic [63:0] a, b, c, result;
    logic [4:0] flags;
  } op_t;
  op_t expected[4][1024];
  bit present[4][1024];
  logic [63:0] seeds[4][16], packets[4][576], commits[4][16], accum[4][16];
  int seed_slot[4][16], packet_kind[4][576], commit_slot[4][16];
  logic [7:0] commit_be[4][16];
  int nseed[4], npacket[4], nop[4], ncommit[4], expected_flags[4];
  int fd[4], count[4], id, elements, heads, tokens, rounding, words, cyc;
  int seeded[4], delivered[4], issued[4], returned[4], written[4], acked[4];
  int next_token[4][16], pending[4][16], ack_due[4][16], accepted_flags[4];
  int packets_in, terminal_age, group_flags, total_issue=0, total_writes=0;
  int cov_request[4], cov_write[4], cov_late=0, cov_same=0, cov_excess=0;
  int cov_max=0, cov_skew=0, cov_done=0, cov_debt_terminal=0;
  bit seed_held[4], fpu_held[4], write_held[4], lane_finished[4], stream_held;
  logic [202:0] fpu_saved[4];
  logic [75:0] write_saved[4];

  function automatic logic [63:0] enabled_bits(input logic [3:0] mask);
    for (int k=0;k<4;k++) enabled_bits[k*16+:16] = {16{mask[k]}};
  endfunction

  task automatic read_case(input int number);
    int got, cid, e, h, t, rm, mode, phase, bad, prepared, tok, slot, mask, flags;
    logic [63:0] a,b,c,r;
    group_flags=0;
    for (int l=0;l<4;l++) begin
      got=$fscanf(fd[l], "%d %d %d %d %d %d %d %d %d %d %d %d %h %h",
        cid,e,h,t,rm,mode,phase,bad,nseed[l],npacket[l],nop[l],ncommit[l],expected_flags[l],prepared);
      if (got!=14 || cid!=number || e<1 || e>32 || !(h inside {1,2}) ||
          t<1 || t>64 || rm<0 || rm>4 || mode!=0 || expected_flags[l]>31 ||
          nseed[l]!=((e+3)/4)*h || ncommit[l]!=nseed[l] ||
          npacket[l]!=t*((e+3)/4+1) || nop[l]!=nseed[l]*t)
        $fatal(1,"Invalid normal case header lane=%0d case=%0d",l,number);
      if (l==0) begin id=cid; elements=e; heads=h; tokens=t; rounding=rm; words=(e+3)/4; end
      else if ({cid,e,h,t,rm} !== {id,elements,heads,tokens,rounding})
        $fatal(1,"Lane case order/common shape mismatch");
      group_flags |= expected_flags[l];
      for (int i=0;i<1024;i++) present[l][i]=0;
      for (int i=0;i<nseed[l];i++)
        if ($fscanf(fd[l],"%h %h",seed_slot[l][i],seeds[l][i])!=2 ||
            seed_slot[l][i]!=(i/words)*8+i%words) $fatal(1,"Invalid seed record");
      for (int i=0;i<npacket[l];i++)
        if ($fscanf(fd[l],"%d %h",packet_kind[l][i],packets[l][i])!=2 ||
            packet_kind[l][i]!=(i%(words+1)!=0)) $fatal(1,"Invalid packet record");
      for (int i=0;i<nop[l];i++) begin
        if ($fscanf(fd[l],"%d %h %h %h %h %h %h %h",tok,slot,mask,a,b,c,r,flags)!=8 ||
            tok<0 || tok>=tokens || slot<0 || slot>=16 || slot/8>=heads ||
            slot%8>=words || flags<0 || flags>31 || mask<1 || mask>15)
          $fatal(1,"Invalid FMA record");
        if (present[l][tok*16+slot]) $fatal(1,"Duplicate FMA record");
        expected[l][tok*16+slot]='{4'(mask),a,b,c,r,5'(flags)};
        present[l][tok*16+slot]=1;
      end
      for (int i=0;i<ncommit[l];i++)
        if ($fscanf(fd[l],"%h %h %h",commit_slot[l][i],commit_be[l][i],commits[l][i])!=3 ||
            commit_slot[l][i]!=(i/words)*8+i%words) $fatal(1,"Invalid commit record");
    end
  endtask

  task automatic finish_adapters;
    gen_fpu[0].adapter.finish_gate();
    gen_fpu[1].adapter.finish_gate();
    gen_fpu[2].adapter.finish_gate();
    gen_fpu[3].adapter.finish_gate();
  endtask

  task automatic run_case;
    int s,t,index,balance,old_balance[4];
    logic [63:0] enabled;
    op_t want;
    bit terminal_fire;
    packets_in=0; terminal_age=0; stream_held=0;
    for (int l=0;l<4;l++) begin
      seeded[l]=0; delivered[l]=0; issued[l]=0; returned[l]=0; written[l]=0; acked[l]=0;
      accepted_flags[l]=0; seed_held[l]=0; fpu_held[l]=0; write_held[l]=0; lane_finished[l]=0;
      for (int k=0;k<16;k++) begin pending[l][k]=-1; next_token[l][k]=0; accum[l][k]='x; end
    end
    @(negedge clk_i);
    start_valid_i=1; start_active_i=4'hf;
    cmd_elements_i=6'(elements); cmd_two_heads_i=heads==2;
    cmd_tokens_i=7'(tokens); cmd_rm_i=3'(rounding);
    @(posedge clk_i);
    if (start_ready_o !== 1 || dut.lane_cmd_valid !== 4'hf || dut.lane_cmd_ready !== 4'hf)
      $fatal(1,"Non-atomic four-lane launch");
    #1;
    for (cyc=0;cyc<100000;cyc++) begin
      @(negedge clk_i);
      start_valid_i=0; start_active_i=0;
      // Poison live command fields after capture.
      cmd_elements_i=63; cmd_two_heads_i=!(heads==2); cmd_tokens_i=127; cmd_rm_i=7;
      for (int l=0;l<4;l++) begin
        if (!seed_held[l]) seed_valid_i[l]=seeded[l]<nseed[l] && cyc>=4*l && cyc%(l+2)==0;
        seed_data_i[l]=seeded[l]<nseed[l] ? seeds[l][seeded[l]] : 64'hdeadbeefdeadbeef;
        if (!adapter_held[l]) gate[l]=(cyc+l)%(l+3)!=0 && cyc%(17+3*l)>l+2;
        result_ready_i[l]=(cyc+l)%4!=0 && (l!=3 || cyc%7<2);
        final_ack_i[l]=l==0 ? result_valid_o[l] && result_ready_i[l] :
          acked[l]<written[l] && ack_due[l][acked[l]]<=cyc;
      end
      if (!stream_held) stream_valid_i=packets_in<npacket[0] && cyc%5!=0;
      stream_is_value_i=packets_in%(words+1)!=0;
      for (int l=0;l<4;l++) stream_data_i[l]=packets_in<npacket[l] ? packets[l][packets_in] : 0;
      if (cyc==0 || terminal_age==1) final_ack_i='1;
      done_ready_i=terminal_age>=4;
      @(posedge clk_i);
      if ($isunknown({active_o,busy_o,start_ready_o,fatal_error_o,seed_ready_o,stream_ready_o,
          fpu_valid_o,fpu_ready_i,fpu_result_valid_i,fpu_result_ready_o,result_valid_o,
          done_valid_o,done_error_o,done_flags_o,outstanding_o,ack_rejected_o}))
        $fatal(1,"Unknown cluster handshake");
      if (active_o!==4'hf || busy_o!==1 || start_ready_o || fatal_error_o || abort_rejected_o)
        $fatal(1,"Cluster ownership/error mismatch case=%0d",id);
      for (int l=0;l<4;l++) begin
        balance=written[l]-acked[l]; old_balance[l]=balance;
        if (outstanding_o[l]!==5'(balance)) $fatal(1,"Final ack ledger mismatch lane=%0d",l);
        if (balance==16) cov_max++;
        if (fpu_held[l] && (!fpu_valid_o[l] ||
            {fpu_operands_o[l],fpu_tag_o[l],fpu_mask_o[l],fpu_rm_o[l]}!==fpu_saved[l]))
          $fatal(1,"FPU request changed under stall");
        if (write_held[l] && (!result_valid_o[l] ||
            {result_data_o[l],result_slot_o[l],result_be_o[l]}!==write_saved[l]))
          $fatal(1,"Write changed under stall");
        fpu_held[l]=fpu_valid_o[l] && !fpu_ready_i[l];
        fpu_saved[l]={fpu_operands_o[l],fpu_tag_o[l],fpu_mask_o[l],fpu_rm_o[l]};
        adapter_held[l]=fpu_valid_o[l] && gate[l] && !adapter_ready[l];
        write_held[l]=result_valid_o[l] && !result_ready_i[l];
        write_saved[l]={result_data_o[l],result_slot_o[l],result_be_o[l]};
        seed_held[l]=seed_valid_i[l] && !seed_ready_o[l];
        if (fpu_held[l]) cov_request[l]++;
        if (write_held[l]) cov_write[l]++;
        if (seed_valid_i[l] && seed_ready_o[l]) begin
          if (seeded[l]>=nseed[l]) $fatal(1,"Excess seed");
          accum[l][seed_slot[l][seeded[l]]]=seed_data_i[l]; seeded[l]++;
        end
        // Observe real fanout transfers, not merely the parent ingress count.
        if (dut.payload_valid[l] && dut.payload_ready[l]) begin
          if (delivered[l]>=packets_in || delivered[l]>=npacket[l] ||
              dut.payload_data[l]!==packets[l][delivered[l]] ||
              dut.payload_kind!==1'(packet_kind[l][delivered[l]]))
            $fatal(1,"Misdirected/duplicate payload lane=%0d",l);
          delivered[l]++;
        end
        if (fpu_result_valid_i[l]) begin
          s=int'(fpu_result_tag_i[l]); index=pending[l][s];
          if (index<0) $fatal(1,"Unowned/duplicate return lane=%0d slot=%0d",l,s);
          want=expected[l][index]; enabled=enabled_bits(want.mask);
          if ((fpu_result_i[l]&enabled)!==(want.result&enabled) || fpu_result_flags_i[l]!==want.flags)
            $fatal(1,"SoftFloat return mismatch case=%0d lane=%0d index=%0d got=%h/%h want=%h/%h",
              id,l,index,fpu_result_i[l],fpu_result_flags_i[l],want.result,want.flags);
          if (fpu_result_ready_o[l]) begin
            accum[l][s]=(accum[l][s]&~enabled)|(fpu_result_i[l]&enabled);
            pending[l][s]=-1; returned[l]++;
          end
        end
        if (fpu_valid_o[l] && fpu_ready_i[l]) begin
          s=int'(fpu_tag_o[l]); t=next_token[l][s]; index=t*16+s;
          if (s/8>=heads || s%8>=words || t>=tokens || seeded[l]!=nseed[l] ||
              pending[l][s]!=-1 || !present[l][index] ||
              delivered[l]<=t*(words+1)+s%8+1 ||
              s!=(issued[l]%heads)*8+(issued[l]/heads)%words)
            $fatal(1,"Illegal accepted FMA case=%0d lane=%0d slot=%0d",id,l,s);
          want=expected[l][index];
          if ({fpu_operands_o[l][0],fpu_operands_o[l][1],fpu_operands_o[l][2],fpu_mask_o[l],fpu_rm_o[l]} !==
              {want.a,want.b,want.c,want.mask,3'(rounding)} || fpu_operands_o[l][2]!==accum[l][s])
            $fatal(1,"Accepted operand/mask/rm mismatch case=%0d lane=%0d index=%0d",id,l,index);
          pending[l][s]=index; next_token[l][s]++; issued[l]++; total_issue++;
          accepted_flags[l] |= int'(want.flags);
        end
        if (result_valid_o[l]) begin
          if (!commit_authorized_o || issued[l]!=nop[l] || returned[l]!=nop[l] ||
              seeded[l]!=nseed[l] || delivered[l]!=npacket[l] || written[l]>=ncommit[l])
            $fatal(1,"Premature/excess commit");
          s=commit_slot[l][written[l]];
          // Full data comparison also checks disabled bytes retain their seeds.
          if (result_slot_o[l]!==4'(s) || result_be_o[l]!==commit_be[l][written[l]] ||
              result_data_o[l]!==commits[l][written[l]] || result_data_o[l]!==accum[l][s])
            $fatal(1,"Final slot/data/be mismatch case=%0d lane=%0d commit=%0d",id,l,written[l]);
          if (result_ready_i[l]) begin
            ack_due[l][written[l]]=cyc+40+20*l; written[l]++; total_writes++;
          end
        end
        if (final_ack_i[l]) begin
          if (acked[l]==written[l]) begin
            if (ack_rejected_o[l]!==1) $fatal(1,"Excess ack not rejected");
            cov_excess++;
          end else begin
            if (ack_rejected_o[l]!==0) $fatal(1,"Owned ack rejected");
            if (lane_finished[l]) cov_late++;
            if (result_valid_o[l] && result_ready_i[l]) cov_same++;
            acked[l]++;
          end
        end else if (ack_rejected_o[l]) $fatal(1,"Spurious ack rejection");
        if (dut.lane_done[l] && dut.lane_done_ready[l]) lane_finished[l]=1;
      end
      if (delivered[0]!=delivered[3]) cov_skew++;
      if (stream_valid_i && stream_ready_o) packets_in++;
      stream_held=stream_valid_i && !stream_ready_o;
      if (dut.group_done && outstanding_o!='0) begin
        if (done_valid_o || dut.group_done_ready) $fatal(1,"Completion bypassed final ack debt");
        cov_debt_terminal++;
      end
      if (!done_valid_o && {done_error_o,done_flags_o}!==6'b0) $fatal(1,"Flags leaked without done");
      if (done_valid_o) begin
        if (done_error_o!==0 || done_flags_o!==5'(group_flags) || packets_in!=npacket[0])
          $fatal(1,"Group FMA-only flags/completion mismatch");
        for (int l=0;l<4;l++) begin
          if (old_balance[l]!=0 || written[l]!=ncommit[l] || acked[l]!=written[l] ||
              issued[l]!=nop[l] || returned[l]!=issued[l] || accepted_flags[l]!=expected_flags[l] ||
              seeded[l]!=nseed[l] || delivered[l]!=npacket[l] || !lane_finished[l])
            $fatal(1,"Incomplete lane at terminal");
          for (int k=0;k<16;k++) if (pending[l][k]!=-1) $fatal(1,"Unretired arithmetic");
        end
        terminal_age++;
        if (!done_ready_i) cov_done++;
      end else if (terminal_age) $fatal(1,"Done withdrawn under stall");
      terminal_fire=done_valid_o && done_ready_i;
      #1;
      for (int l=0;l<4;l++)
        if (outstanding_o[l]!==5'(written[l]-acked[l])) $fatal(1,"Post-edge final ack counter mismatch");
      if (terminal_fire) begin
        if (busy_o!==0 || active_o!==0 || done_valid_o!==0) $fatal(1,"Terminal release mismatch");
        @(negedge clk_i);
        seed_valid_i=0; stream_valid_i=0; gate=0; result_ready_i=0; final_ack_i=0; done_ready_i=0;
        finish_adapters();
        for (int l=0;l<4;l++)
          $display("PV_CLUSTER_FP_LANE id=%0d lane=%0d seeds=%0d packets=%0d issued=%0d returned=%0d writes=%0d acks=%0d flags=%0d",
            id,l,seeded[l],delivered[l],issued[l],returned[l],written[l],acked[l],accepted_flags[l]);
        $display("PV_CLUSTER_FP_CASE id=%0d flags=%0d",id,group_flags);
        return;
      end
    end
    $fatal(1,"Numerical case watchdog id=%0d",id);
  endtask

  initial begin
    string directory, trailing;
    int magic;
    if (!$value$plusargs("CORPUS=%s",directory)) $fatal(1,"Missing corpus");
    for (int l=0;l<4;l++) begin
      fd[l]=$fopen($sformatf("%s/lane%0d.txt",directory,l),"r");
      if (!fd[l] || $fscanf(fd[l],"%h %d",magic,count[l])!=2 || magic!='h50565531 ||
          count[l]<1 || count[l]>1000) $fatal(1,"Invalid corpus header");
      if (l && count[l]!=count[0]) $fatal(1,"Unequal lane case counts");
    end
    repeat (3) @(negedge clk_i);
    rst_ni=1;
    for (int number=0;number<count[0];number++) begin read_case(number); run_case(); end
    for (int l=0;l<4;l++) begin
      if ($fscanf(fd[l],"%s",trailing)!=-1) $fatal(1,"Trailing corpus records");
      $fclose(fd[l]);
      if (!cov_request[l] || !cov_write[l]) $fatal(1,"Missing lane-specific stalls");
      $display("PV_CLUSTER_FP_STALL lane=%0d request=%0d write=%0d",l,cov_request[l],cov_write[l]);
    end
    finish_adapters();
    if (!(cov_late && cov_same && cov_excess && cov_max && cov_skew && cov_done && cov_debt_terminal))
      $fatal(1,"Missing final ack/skew coverage");
    $display("PV_CLUSTER_FP_PASS cases=%0d issued=%0d writes=%0d late=%0d same=%0d excess=%0d max16=%0d skew=%0d done_stall=%0d debt_terminal=%0d",
      count[0],total_issue,total_writes,cov_late,cov_same,cov_excess,cov_max,cov_skew,cov_done,cov_debt_terminal);
    $finish;
  end
endmodule
