// SPDX-License-Identifier: Apache-2.0
// The only arithmetic implementation is the frozen baseline FPNew SIMD slice.
module resident_pv_tb;
  import fpnew_pkg::*;
  parameter int PipeRegs = 3;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst = 0, abort_req = 0;
  logic cv = 0, cr, sh, sv = 0, sr, iv = 0, ir, kind;
  logic [5:0] ce;
  logic [6:0] ct;
  logic [2:0] crm;
  logic [63:0] sd, idata;
  logic fv, fr, rv = 0, rr, ov, ore = 0, dv, dr = 0, error, busy;
  logic [2:0][63:0] operands;
  logic [3:0] tag, mask, rtag, slot;
  logic [2:0] rm;
  logic [63:0] rdata, odata;
  logic [4:0] rflags, flags;
  logic [7:0] be;
  logic gate = 0, fi_ready, fo_valid, fo_ready = 0, fbusy;
  logic [63:0] fo_data;
  logic [3:0] fo_tag;
  status_t fo_flags;

  akv_resident_pv_lane dut (
    .clk_i(clk), .rst_ni(rst), .abort_i(abort_req),
    .cmd_valid_i(cv), .cmd_ready_o(cr), .cmd_elements_i(ce),
    .cmd_two_heads_i(sh), .cmd_tokens_i(ct), .cmd_rm_i(crm),
    .seed_valid_i(sv), .seed_ready_o(sr), .seed_data_i(sd),
    .stream_valid_i(iv), .stream_ready_o(ir), .stream_is_value_i(kind), .stream_data_i(idata),
    .fpu_valid_o(fv), .fpu_ready_i(fr), .fpu_operands_o(operands),
    .fpu_tag_o(tag), .fpu_mask_o(mask), .fpu_rm_o(rm),
    .fpu_result_valid_i(rv), .fpu_result_ready_o(rr), .fpu_result_i(rdata),
    .fpu_result_tag_i(rtag), .fpu_result_flags_i(rflags),
    .result_valid_o(ov), .result_ready_i(ore), .result_data_o(odata),
    .result_slot_o(slot), .result_be_o(be),
    .done_valid_o(dv), .done_ready_i(dr), .done_error_o(error), .done_flags_o(flags), .busy_o(busy)
  );
  assign fr = gate && fi_ready;
  fpnew_opgroup_fmt_slice #(
    .OpGroup(ADDMUL), .FpFormat(FP16), .Width(64), .EnableVectors(1),
    .NumPipeRegs(PipeRegs), .PipeConfig(DISTRIBUTED), .TagType(logic [3:0])
  ) borrowed_fpu (
    .clk_i(clk), .rst_ni(rst), .operands_i(operands), .is_boxed_i(3'b111),
    .rnd_mode_i(roundmode_e'(rm)), .op_i(FMADD), .op_mod_i(1'b0), .vectorial_op_i(1'b1),
    .tag_i(tag), .simd_mask_i(mask), .in_valid_i(fv && gate), .in_ready_o(fi_ready),
    .flush_i(1'b0), .result_o(fo_data), .status_o(fo_flags), .extension_bit_o(),
    .tag_o(fo_tag), .out_valid_o(fo_valid), .out_ready_i(fo_ready), .busy_o(fbusy)
  );

  typedef struct packed {
    logic [3:0] mask;
    logic [63:0] a, b, c, result;
    logic [4:0] flags;
  } op_t;
  typedef struct packed {
    logic [63:0] data;
    logic [4:0] flags;
    logic [3:0] tag;
    int index;
    int serial;
  } response_t;
  op_t expected[1024];
  bit present[1024];
  logic [63:0] seeds[16], packets[576], commits[16], sum[16];
  int seed_slot[16], commit_slot[16], packet_kind[576];
  logic [7:0] commit_be[16];
  int next_token[16], pending[16];
  int raw_pending[$];
  response_t responses[$];
  response_t delivery, raw_hold;
  int case_id, elements, heads, tokens, rounding, mode, phase, bad_at;
  int nseed, npacket, nop, ncommit, expected_flags, prepared_flags;
  int seed_count, packet_count, issued, returned, commit_count, commands, done_count;
  int case_cycles, done_age, result_age, accepted_flags, words;
  int total_cases = 0, total_done = 0, total_reset = 0, total_issue = 0;
  int total_return = 0, total_cancel = 0, total_commits = 0, total_cycles = 0;
  int request_stalls = 0, stream_stalls = 0, seed_stalls = 0, result_stalls = 0;
  int done_stalls = 0, raw_stalls = 0, reordered = 0, simultaneous = 0;
  int aborted_pending = 0, malformed_pending = 0, reset_pending = 0;
  bit cv_hold, sv_hold, iv_hold, fv_hold, ov_hold, dv_hold, rv_hold, raw_held, slice_held;
  bit trigger, abort_sent, command_sent, complete;
  logic [16:0] cmd_saved;
  logic [63:0] seed_saved;
  logic [64:0] packet_saved;
  logic [202:0] fpu_saved;
  logic [75:0] result_saved;
  logic [5:0] done_saved;
  logic [72:0] return_saved;
  logic [31:0] random_state = 32'h82c15a71;

  function automatic int unsigned random_word();
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
  endfunction

  function automatic logic [63:0] element_bits(logic [3:0] m);
    logic [63:0] value;
    for (int i=0; i<4; i++) value[i*16+:16] = {16{m[i]}};
    return value;
  endfunction

  function automatic logic [63:0] byte_bits(logic [7:0] m);
    logic [63:0] value;
    for (int i=0; i<8; i++) value[i*8+:8] = {8{m[i]}};
    return value;
  endfunction

  task automatic clear_holds;
    cv_hold=0; sv_hold=0; iv_hold=0; fv_hold=0; ov_hold=0; dv_hold=0;
    rv_hold=0; raw_held=0; slice_held=0;
  endtask

  task automatic reset_all;
    @(negedge clk);
    rst=0; abort_req=0; cv=0; sv=0; iv=0; gate=0; rv=0; ore=0; dr=0; fo_ready=0;
    raw_pending.delete(); responses.delete();
    for (int s=0; s<16; s++) pending[s]=-1;
    clear_holds();
    repeat (3) @(negedge clk);
    rst=1;
    @(posedge clk);
    if (cr !== 1 || busy !== 0 || dv !== 0 || ov !== 0 || fv !== 0 || fo_valid !== 0)
      $fatal(1,"Reset failed to revoke ownership case=%0d",case_id);
  endtask

  task automatic check_cycle;
    int index, s, t, minimum_serial;
    logic [63:0] enabled;
    op_t want;
    response_t response;
    if ($isunknown({cr,sr,ir,fv,rr,ov,dv,busy,error,flags,fi_ready,fo_valid}))
      $fatal(1,"Unknown handshake case=%0d cycle=%0d",case_id,case_cycles);
    // Abort legally withdraws unaccepted requests; reset clears all hold state.
    if (cv_hold && (!cv || {ce,sh,ct,crm} !== cmd_saved)) $fatal(1,"Command changed under stall");
    if (!abort_req) begin
      if (sv_hold && (!sv || sd !== seed_saved)) $fatal(1,"Seed changed under stall");
      if (iv_hold && (!iv || {kind,idata} !== packet_saved)) $fatal(1,"Packet changed under stall");
      if (fv_hold && (!fv || {operands,tag,mask,rm} !== fpu_saved))
        $fatal(1,"FPU request changed under stall case=%0d",case_id);
      if (ov_hold && (!ov || {odata,slot,be} !== result_saved)) $fatal(1,"Commit changed under stall");
    end
    if (dv_hold && (!dv || {error,flags} !== done_saved)) $fatal(1,"Done changed under stall");
    if (rv_hold && (!rv || {rdata,rtag,rflags} !== return_saved)) $fatal(1,"Return driver changed under stall");
    if (raw_held && (!fo_valid || {fo_data,fo_flags,fo_tag} !== {raw_hold.data,raw_hold.flags,raw_hold.tag}))
      $fatal(1,"FPNew output changed under stall");
    if (!dv && {error,flags} !== 6'b0) $fatal(1,"Completion flags leaked outside Done");
    if (commands && !done_count && busy !== 1) $fatal(1,"Ownership released before completion");
    if (commands && !done_count && cr) $fatal(1,"Command accepted while owned");
    if (abort_req && (sr || ir || fv || ov)) $fatal(1,"Transfer enabled during abort");
    if (cv && cr) begin
      commands++;
      if (commands != 1) $fatal(1,"Duplicate command");
      command_sent=1;
    end
    if (sv && sr) begin
      if (mode==1 || seed_count>=nseed || !commands) $fatal(1,"Unexpected seed handshake");
      sum[seed_slot[seed_count]]=sd;
      seed_count++;
    end
    if (iv && ir) begin
      if (mode==1 || seed_count!=nseed || packet_count>=npacket) $fatal(1,"Unexpected stream handshake");
      packet_count++;
    end
    // Check returns before same-cycle new issues, allowing a future bypassed recurrence.
    if (rv && rr) begin
      s=int'(rtag); index=delivery.index;
      if (pending[s] != index) $fatal(1,"Duplicate/unowned return slot=%0d",s);
      want=expected[index]; enabled=element_bits(want.mask);
      if ((rdata & enabled) !== (want.result & enabled) || rflags !== want.flags)
        $fatal(1,"Bad arithmetic return case=%0d index=%0d",case_id,index);
      sum[s]=(sum[s] & ~enabled) | (rdata & enabled);
      pending[s]=-1; returned++; total_return++;
    end
    if (fv && fr) begin
      s=int'(tag); t=next_token[s]; index=t*16+s;
      if (mode==1 || abort_sent || seed_count!=nseed || s/8>=heads || s%8>=words ||
          t>=tokens || !present[index] || pending[s]!=-1)
        $fatal(1,"Illegal issue case=%0d slot=%0d token=%0d",case_id,s,t);
      if (packet_count <= t*(words+1)+1+s%8)
        $fatal(1,"Issue used unaccepted stream packet case=%0d",case_id);
      if (mode==2 && t*(words+1)+1+s%8>=bad_at)
        $fatal(1,"Issue consumed malformed packet case=%0d",case_id);
      want=expected[index];
      if ({operands[0],operands[1],operands[2],mask,rm} !==
          {want.a,want.b,want.c,want.mask,3'(rounding)} || operands[2] !== sum[s]) begin
        $display("PV_MASK_DIAGNOSTIC words=%0d word=%0d tail=%h computed=%h presented=%h",
          dut.words_q,dut.word_q,dut.tail_mask_q,
          ({1'b0,dut.word_q} == dut.words_q-1'b1) ? dut.tail_mask_q : 4'hf,mask);
        $fatal(1,"Issue mismatch case=%0d slot=%0d token=%0d got=%h/%h/%h mask=%h rm=%h want=%h/%h/%h mask=%h rm=%h",
          case_id,s,t,operands[0],operands[1],operands[2],mask,rm,want.a,want.b,want.c,want.mask,rounding);
      end
      pending[s]=index; next_token[s]++; raw_pending.push_back(index);
      accepted_flags |= int'(want.flags); issued++; total_issue++;
    end
    if (fv && fr && rv && rr) simultaneous++;
    if (fo_valid && fo_ready) begin
      if (raw_pending.size()==0) $fatal(1,"Unsolicited FPNew output");
      index=raw_pending.pop_front(); want=expected[index]; enabled=element_bits(want.mask);
      if (int'(fo_tag)!=index%16 || (fo_data & enabled) !== (want.result & enabled) || fo_flags !== want.flags)
        $fatal(1,"FPNew/SoftFloat mismatch case=%0d index=%0d got=%h/%h want=%h/%h",
               case_id,index,fo_data,fo_flags,want.result,want.flags);
      response='{fo_data,fo_flags,fo_tag,index,total_issue-raw_pending.size()};
      responses.push_back(response);
    end
    if (ov) begin
      if (mode==1 || mode==2 || (mode==4 && abort_sent) || returned!=issued || issued!=nop ||
          seed_count!=nseed || packet_count!=npacket || raw_pending.size() || responses.size() || rv)
        $fatal(1,"Premature/forbidden commit case=%0d",case_id);
      if (commit_count>=ncommit || int'(slot)!=commit_slot[commit_count] || be !== commit_be[commit_count] ||
          (odata & byte_bits(be)) !== (commits[commit_count] & byte_bits(be)))
        $fatal(1,"Commit mismatch case=%0d commit=%0d slot=%0d data=%h expected=%h",
               case_id,commit_count,slot,odata,commits[commit_count]);
    end
    if (ov && ore) begin commit_count++; total_commits++; end
    if (dv) begin
      if (returned!=issued || raw_pending.size() || responses.size() || rv || ov || fv)
        $fatal(1,"Done before all accepted arithmetic drained case=%0d",case_id);
      if (flags !== 5'(accepted_flags) || error !== (mode==1 || mode==2 || mode==4))
        $fatal(1,"Completion mismatch case=%0d flags=%h accepted=%h error=%b mode=%0d",
               case_id,flags,accepted_flags,error,mode);
      if (mode==0 || mode==3) begin
        if (commit_count!=ncommit || issued!=nop || flags !== 5'(expected_flags))
          $fatal(1,"Missing normal transfers case=%0d",case_id);
      end else if (commit_count) $fatal(1,"Fault committed architectural data");
      if (mode==1 && (issued || seed_count || packet_count)) $fatal(1,"Invalid command transferred data");
      if (mode==2 && packet_count!=npacket) $fatal(1,"Malformed packet not accepted");
      if (mode==4 && !abort_sent) $fatal(1,"Abort test completed without abort");
    end
    if (dv && dr) begin done_count++; total_done++; complete=1; end
    if (fv && !fr) request_stalls++;
    if (iv && !ir) stream_stalls++;
    if (sv && !sr) seed_stalls++;
    if (ov && !ore) result_stalls++;
    if (dv && !dr) done_stalls++;
    if (fo_valid && !fo_ready) raw_stalls++;
    cv_hold=cv && !cr; cmd_saved={ce,sh,ct,crm};
    sv_hold=sv && !sr; seed_saved=sd;
    iv_hold=iv && !ir; packet_saved={kind,idata};
    fv_hold=fv && !fr; fpu_saved={operands,tag,mask,rm};
    ov_hold=ov && !ore; result_saved={odata,slot,be};
    dv_hold=dv && !dr; done_saved={error,flags};
    rv_hold=rv && !rr; return_saved={rdata,rtag,rflags};
    raw_held=fo_valid && !fo_ready; raw_hold='{fo_data,fo_flags,fo_tag,0,0};
    slice_held=fv && gate && !fi_ready;
    if (dv) done_age++;
    if (ov) result_age++;
    case_cycles++; total_cycles++;
  endtask

  task automatic execute_case;
    int selected, old_seed_count, old_packet_count;
    bit do_interrupt, hold_returns;
    seed_count=0; packet_count=0; issued=0; returned=0; commit_count=0;
    commands=0; done_count=0; accepted_flags=0; case_cycles=0; done_age=0; result_age=0;
    command_sent=0; complete=0; abort_sent=0; trigger=0;
    words=(elements+3)/4;
    for (int s=0;s<16;s++) begin next_token[s]=0; pending[s]=-1; sum[s]='x; end
    while (!complete) begin
      @(negedge clk);
      if (case_cycles>100000) $fatal(1,"Case watchdog case=%0d issued=%0d returned=%0d packets=%0d",case_id,issued,returned,packet_count);
      do_interrupt=0;
      if ((mode==3 || mode==4) && !trigger) begin
        case (phase)
          1: do_interrupt=seed_count==1;
          2: do_interrupt=seed_count==nseed && iv_hold;
          3: do_interrupt=issued>returned;
          4: do_interrupt=result_age>2 && commit_count==0;
          5: do_interrupt=done_age>2;
        endcase
      end
      if (do_interrupt) begin
        trigger=1;
        if (mode==3) begin
          total_cancel+=issued-returned;
          if (issued>returned) reset_pending++;
          reset_all();
          total_reset++; complete=1;
          break;
        end
        abort_req=1; abort_sent=1; sv=0; iv=0;
        if (issued>returned) aborted_pending++;
        // An abort cancels only unaccepted interface beats, never accepted arithmetic.
        sv_hold=0; iv_hold=0; fv_hold=0; ov_hold=0;
      end else abort_req=0;
      if (!cv_hold) begin
        cv=!command_sent;
        // Poison the command bus immediately after acceptance to check captured fields.
        ce=cv ? 6'(elements) : 6'd63;
        sh=cv ? (heads==2) : !(heads==2);
        ct=cv ? 7'(tokens) : 7'd127;
        crm=cv ? 3'(rounding) : 3'd7;
      end
      if (!sv_hold && !abort_sent) begin
        sv=command_sent && (mode==1 || (seed_count<nseed && (random_word()%4!=0)));
        sd=sv && mode!=1 ? seeds[seed_count] : 64'hfeedface7c017c01;
      end
      if (!iv_hold && !abort_sent) begin
        // Offer ingress early while seeds are still being accepted.
        iv=command_sent && (mode==1 || (packet_count<npacket && (random_word()%5!=0)));
        idata=iv && mode!=1 ? packets[packet_count] : 64'hdeadbeef7c017c01;
        kind=iv && mode!=1 ? 1'(packet_kind[packet_count]) : 1'b1;
      end
      if (!slice_held) gate=(random_word()%4!=0) && case_cycles%43>6;
      if (mode==3 && phase==2 && !trigger) gate=0;
      fo_ready=(responses.size()<16) && random_word()%4!=0 && case_cycles%37>5;
      hold_returns=((mode==3 || mode==4) && phase==3 && !trigger);
      if (!rv_hold) begin
        rv=0;
        // Delay and reorder actual FPNew results, never replace their arithmetic.
        if (!hold_returns && responses.size() && case_cycles%13>=6 && random_word()%4!=0) begin
          selected=(responses.size()>1 && case_cycles%2) ? responses.size()-1 : 0;
          if (selected!=0) reordered++;
          delivery=responses[selected]; responses.delete(selected);
          rv=1; rdata=delivery.data; rflags=delivery.flags; rtag=delivery.tag;
        end
      end
      ore=random_word()%3!=0 && case_cycles%29>7;
      if ((mode==3 || mode==4) && phase==4 && !trigger) ore=0;
      dr=done_age>=4 && random_word()%3!=0;
      if (mode==3 && phase==5 && !trigger) dr=0;
      old_seed_count=seed_count; old_packet_count=packet_count;
      @(posedge clk);
      check_cycle();
      if (mode==2 && old_packet_count<npacket && packet_count==npacket && issued>returned)
        malformed_pending++;
    end
    if (mode==3 && !trigger) $fatal(1,"Reset test did not interrupt");
    if (mode==4 && !trigger) $fatal(1,"Abort test did not interrupt");
    if (mode!=3 && (done_count!=1 || commands!=1)) $fatal(1,"Completion count mismatch");
    if (mode==0 && accepted_flags!=expected_flags) $fatal(1,"FMA-only flags mismatch");
    if (mode!=3) begin
      // Sample the post-ack state without inserting an extra clock between owners.
      #1;
      if (busy !== 0 || cr !== 1 || dv !== 0 || ov !== 0 || flags !== 0 || error !== 0)
        $fatal(1,"Completion acknowledgment did not release owner");
    end
    clear_holds();
    total_cases++;
    $display("PV_CASE_PASS id=%0d mode=%0d seeds=%0d packets=%0d issued=%0d returned=%0d commits=%0d flags=%0d cycles=%0d",
             case_id,mode,seed_count,packet_count,issued,returned,commit_count,accepted_flags,case_cycles);
  endtask

  initial begin
    string vector_file, trailing;
    int fd, magic, count, got, t, s, m, f, seen_ops;
    op_t value;
    logic [63:0] a,b,c,r;
    if (!$value$plusargs("VECTORS=%s",vector_file)) $fatal(1,"Missing vector file");
    fd=$fopen(vector_file,"r");
    if (!fd) $fatal(1,"Cannot open vector file");
    if ($fscanf(fd,"%h %d",magic,count)!=2 || magic!='h50565531 || count<1)
      $fatal(1,"Invalid vector header");
    reset_all();
    for (int number=0;number<count;number++) begin
      got=$fscanf(fd,"%d %d %d %d %d %d %d %d %d %d %d %d %h %h",
        case_id,elements,heads,tokens,rounding,mode,phase,bad_at,nseed,npacket,nop,ncommit,expected_flags,prepared_flags);
      if (got!=14 || case_id!=number || nseed>16 || npacket>576 || nop>1024 || ncommit>16 ||
          nseed<0 || npacket<0 || nop<0 || ncommit<0 || !(mode inside {[0:4]}))
        $fatal(1,"Invalid/truncated case header number=%0d",number);
      for (int i=0;i<1024;i++) present[i]=0;
      for (int i=0;i<nseed;i++)
        if ($fscanf(fd,"%h %h",seed_slot[i],seeds[i])!=2) $fatal(1,"Truncated seeds");
      for (int i=0;i<npacket;i++)
        if ($fscanf(fd,"%d %h",packet_kind[i],packets[i])!=2) $fatal(1,"Truncated packets");
      seen_ops=0;
      for (int i=0;i<nop;i++) begin
        if ($fscanf(fd,"%d %h %h %h %h %h %h %h",t,s,m,a,b,c,r,f)!=8 ||
            t<0 || t>=64 || s<0 || s>=16 || present[t*16+s]) $fatal(1,"Invalid FMA record");
        expected[t*16+s]='{4'(m),a,b,c,r,5'(f)};
        present[t*16+s]=1; seen_ops++;
      end
      for (int i=0;i<ncommit;i++)
        if ($fscanf(fd,"%h %h %h",commit_slot[i],commit_be[i],commits[i])!=3) $fatal(1,"Truncated commits");
      execute_case();
    end
    if ($fscanf(fd,"%s",trailing)!=-1) $fatal(1,"Trailing vector records");
    $fclose(fd);
    if (total_cases!=count || total_done+total_reset!=count || total_issue!=total_return+total_cancel ||
        request_stalls==0 || stream_stalls==0 || result_stalls==0 || done_stalls==0 || raw_stalls==0 ||
        reordered==0 || simultaneous==0 || reset_pending==0 || aborted_pending==0 || malformed_pending==0)
      $fatal(1,"Incomplete coverage or transaction accounting");
    $display("PV_UNIT_PASS cases=%0d done=%0d reset=%0d issued=%0d returned=%0d cancelled=%0d commits=%0d cycles=%0d pipe=%0d",
      total_cases,total_done,total_reset,total_issue,total_return,total_cancel,total_commits,total_cycles,PipeRegs);
    $display("PV_COVERAGE request_stalls=%0d stream_stalls=%0d seed_stalls=%0d result_stalls=%0d done_stalls=%0d raw_stalls=%0d reordered=%0d simultaneous=%0d reset_pending=%0d abort_pending=%0d malformed_pending=%0d",
      request_stalls,stream_stalls,seed_stalls,result_stalls,done_stalls,raw_stalls,reordered,simultaneous,reset_pending,aborted_pending,malformed_pending);
    $finish;
  end
  initial begin #100000000; $fatal(1,"Global watchdog"); end
endmodule
