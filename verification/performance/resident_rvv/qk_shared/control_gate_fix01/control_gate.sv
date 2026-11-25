// SPDX-License-Identifier: Apache-2.0
// Protocol-only gate. Tagged lanes deliberately do not implement arithmetic.
module control_gate_tb;
  import ara_pkg::*;
  import akv_pkg::*;
  logic clk = 0, rst = 0;
  always #5 clk = !clk;
  logic cmd_valid, cmd_ready, cmd_qk, abort_req;
  vid_t cmd_id, response_id;
  logic [8:0] control;
  logic [2:0] rm, base;
  logic context_valid;
  logic [15:0] context_d;
  logic [6:0] context_t;
  logic [3:0] qrows;
  logic lease, acquire, start, release_owner, commit, terminal, error, fatal;
  logic [4:0] flags;
  logic [3:0] lane_abort, owned, ready, result_valid, done_valid, done_error, done_ready;
  logic [3:0][4:0] done_flags;
  logic [3:0] source_valid, source_ready, payload_valid, grant, final_grant;
  logic [3:0][63:0] source_data, payload_data, result_data;
  logic [3:0][3:0] result_slot;
  logic [3:0][7:0] result_be;
  logic payload_seed, payload_value, row_read, query_read, column_start;
  logic [5:0] row_token;
  logic [3:0] row_word, query_word;
  logic [2:0] query_row;
  logic [255:0] row_data, query_data, column_data;
  logic [6:0] column_dimension, column_tokens;
  logic column_busy, column_valid;
  logic [1:0] column_index, column_packet;

  akv_resident_pv_control dut (
    .clk_i(clk), .rst_ni(rst), .command_valid_i(cmd_valid), .command_ready_o(cmd_ready),
    .command_id_i(cmd_id), .command_control_i(control), .command_rm_i(rm),
    .context_valid_i(context_valid), .context_dimension_i(context_d), .context_tokens_i(context_t),
    .abort_i(abort_req), .lease_o(lease), .acquire_o(acquire), .start_o(start),
    .release_o(release_owner), .commit_o(commit), .lane_abort_o(lane_abort),
    .lane_owned_i(owned), .lane_ready_i(ready), .lane_result_valid_i(result_valid),
    .lane_done_valid_i(done_valid), .lane_done_error_i(done_error), .lane_done_flags_i(done_flags),
    .lane_done_ready_o(done_ready), .source_valid_i(source_valid), .source_ready_o(source_ready),
    .source_data_i(source_data), .row_read_o(row_read), .row_token_o(row_token), .row_word_o(row_word),
    .row_data_i(row_data), .payload_valid_o(payload_valid), .payload_data_o(payload_data),
    .payload_seed_o(payload_seed), .payload_value_o(payload_value), .lane_grant_i(grant),
    .lane_final_grant_i(final_grant), .terminal_o(terminal), .error_o(error), .fatal_o(fatal),
    .flags_o(flags), .id_o(response_id), .command_qk_i(cmd_qk), .command_query_base_i(base),
    .context_q_rows_i(qrows), .query_read_o(query_read), .query_row_o(query_row),
    .query_word_o(query_word), .query_data_i(query_data), .column_start_o(column_start),
    .column_dimension_o(column_dimension), .column_tokens_o(column_tokens),
    .column_busy_i(column_busy), .column_valid_i(column_valid), .column_index_o(column_index),
    .column_packet_o(column_packet), .column_data_i(column_data)
  );

  function automatic logic [15:0] qtag(int row, int dim);
    return 16'(16'h1000 + row*128 + dim);
  endfunction
  function automatic logic [15:0] ktag(int token, int dim);
    return 16'(16'h3000 + token*128 + dim);
  endfunction
  function automatic logic [15:0] vtag(int token, int dim);
    return 16'(16'h6000 + token*128 + dim);
  endfunction
  function automatic logic [15:0] ptag(int token, int head);
    return 16'(16'h2000 + 2*token + head);
  endfunction
  function automatic logic [63:0] srcword(int lane, int word_index);
    logic [63:0] value;
    if (word_index < 16) return 64'h5100000000000000 | (64'(lane)<<32) | 64'(word_index);
    for (int h=0; h<4; h++) begin
      automatic int element = lane + (h%2)*8 + (h/2)*4;
      value[16*h+:16] = ptag((word_index-16)*8 + element/2, element%2);
    end
    return value;
  endfunction

  // Q/V responses change only after the request edge. K is non-cancellable,
  // with ceil(T/8) issue cycles and one final capture cycle, as in v2_context.
  int gather_left, panel_dim, panel_t;
  always @(posedge clk) begin
    if (!rst) begin
      row_data <= 'x; query_data <= 'x;
      column_busy <= 0; column_valid <= 0;
      gather_left <= 0; panel_dim <= 0; panel_t <= 0;
    end else begin
      if (query_read)
        for (int e=0; e<16; e++) query_data[16*e+:16] <= qtag(int'(query_row),16*int'(query_word)+e);
      if (row_read)
        for (int e=0; e<16; e++) row_data[16*e+:16] <= vtag(int'(row_token),16*int'(row_word)+e);
      if (column_start) begin
        assert (!column_busy && !query_read && !row_read) else $fatal(1,"Memory ownership overlap");
        column_busy <= 1; column_valid <= 0;
        panel_dim <= int'(column_dimension); panel_t <= int'(column_tokens);
        gather_left <= (int'(column_tokens)+7)/8 + 1;
      end else if (column_busy) begin
        gather_left <= gather_left-1;
        if (gather_left == 1) begin column_busy <= 0; column_valid <= 1; end
      end
    end
  end
  always_comb begin
    column_data = '0;
    for (int e=0; e<16; e++)
      if (column_valid && !column_busy && 16*int'(column_packet)+e < panel_t)
        column_data[16*e+:16] = ktag(16*int'(column_packet)+e,panel_dim+int'(column_index));
  end

  int cycle, case_id, t, h, d, b, phase, age, launch_count;
  bit qk, live, launched, sent_abort, sampled_terminal, sampled_error;
  int source_n[4], seed_n[4], coeff_n[4], value_n[4], stream_n[4];
  int write_n[4], ack_n[4], done_n[4], finish_at[4], acquire_n[4], release_n[4];
  int ack_due[4][16];
  bit own_m[4], aborted[4];
  logic [3:0] stalled_payload;
  logic [3:0][63:0] held_payload;
  logic [3:0] stalled_result;
  logic [3:0][63:0] held_result;
  logic [3:0][3:0] held_slot;
  logic [3:0][7:0] held_be;
  logic [63:0] vrf[4][16];
  bit vrf_written[4][16];
  bit held_seed, held_value;
  int reads, queries, columns, seed_total, writes, acks, checks, stalled;
  int barrier_hold, debt_hold, busy_hold, aborted_busy, terminal_count;
  int suite_checks, suite_cases;

  function automatic int elems(int lane);
    return qk ? (t>lane ? (t+3-lane)/4 : 0) : d/4;
  endfunction
  function automatic int slots(int lane);
    return qk ? ((elems(lane)+1)/2)*h : (d/16)*h;
  endfunction
  function automatic int packets(int lane);
    return qk ? (elems(lane)+3)/4 : d/16;
  endfunction
  function automatic int payload_count(int lane);
    return slots(lane)==0 ? 0 : (qk ? d : t)*(1+packets(lane));
  endfunction
  function automatic bit active(int lane);
    return !qk || lane<t;
  endfunction
  function automatic int sum_done();
    return done_n[0]+done_n[1]+done_n[2]+done_n[3];
  endfunction
  function automatic bit all_payloads();
    bit complete;
    complete=1;
    for (int l=0; l<4; l++) complete &= stream_n[l]==payload_count(l) && seed_n[l]==slots(l);
    return complete;
  endfunction

  // Stub results are held private tags. They have real slot/BE/valid handshakes
  // at the local architectural write boundary, never an arithmetic meaning.
  task automatic drive_model();
    owned='0; ready='1; grant='0; final_grant='0;
    source_valid='0; source_data='0; result_valid='0; done_valid='0;
    done_error='0; done_flags='0; result_data='0; result_slot='0; result_be='0;
    for (int l=0; l<4; l++) begin
      owned[l]=own_m[l];
      grant[l]=live && ((cycle+2*l)%5 != 0);
      if (live && (qk || source_n[l]<24)) begin
        source_valid[l]=1;
        source_data[l]=qk ? 64'hbad0bad1bad2bad3 : srcword(l,source_n[l]);
      end
      if (launched && active(l) && !aborted[l] && finish_at[l]>=0 &&
          cycle>=finish_at[l]+((l==(qk && t<4 ? t-1 : 3)) ? 12 : 2) && write_n[l]<slots(l)) begin
        automatic int perhead = slots(l)/h;
        automatic int word_index = write_n[l]%perhead;
        result_valid[l]=1;
        result_data[l]={16'hc047,16'(case_id),16'(l),16'(write_n[l])};
        result_slot[l]=4'((write_n[l]/perhead)*8+word_index);
        result_be[l]=qk && elems(l)%2 && word_index==perhead-1 ? 8'h0f : 8'hff;
      end
      if (launched && active(l) && done_n[l]==0 &&
          (aborted[l] || write_n[l]==slots(l))) begin
        done_valid[l]=1;
        done_error[l]=aborted[l];
        done_flags[l]=aborted[l] ? 5'h1f : 5'(1<<l);
      end
      if (!active(l)) begin done_flags[l]='1; done_error[l]=1; end
      if (ack_n[l]<write_n[l] && cycle>=ack_due[l][ack_n[l]]) final_grant[l]=1;
    end
  endtask

  task automatic check_payload(int l);
    logic [63:0] expected;
    int outer_index, part, token, dim, physical, perhead;
    checks++;
    assert (launched && active(l) && !aborted[l] && !commit)
      else $fatal(1,"Payload outside private active lease case=%0d lane=%0d",case_id,l);
    if (payload_seed) begin
      assert (seed_n[l]<slots(l) && stream_n[l]==0) else $fatal(1,"Seed count/order");
      perhead=slots(l)/h;
      expected=qk ? 64'b0 : srcword(l,(seed_n[l]/perhead)*8+seed_n[l]%perhead);
      assert (payload_data[l]===expected) else $fatal(1,"Seed data case=%0d lane=%0d",case_id,l);
      seed_n[l]++; seed_total++;
    end else begin
      assert (seed_n[l]==slots(l) && stream_n[l]<payload_count(l)) else $fatal(1,"Stream count/order");
      outer_index=stream_n[l]/(1+packets(l));
      part=stream_n[l]%(1+packets(l));
      expected='0;
      if (part==0) begin
        assert (!payload_value) else $fatal(1,"Expected coefficient tag");
        expected[15:0]=qk ? qtag(b,outer_index) : ptag(outer_index,0);
        expected[31:16]=qk ? (h==2 ? qtag(b+1,outer_index) : 16'b0) : ptag(outer_index,1);
        coeff_n[l]++;
      end else begin
        assert (payload_value) else $fatal(1,"Expected value tag");
        for (int e=0; e<4; e++) begin
          // Independent natural EW16 lane positions: l,l+8,l+4,l+12.
          physical=l+(e%2)*8+(e/2)*4;
          token=qk ? 16*(part-1)+physical : outer_index;
          dim=qk ? outer_index : 16*(part-1)+physical;
          expected[16*e+:16]=qk ? (token<t ? ktag(token,dim) : 16'b0) : vtag(token,dim);
        end
        value_n[l]++;
      end
      assert (payload_data[l]===expected)
        else $fatal(1,"Payload tag mismatch case=%0d lane=%0d beat=%0d got=%h expected=%h",
                    case_id,l,stream_n[l],payload_data[l],expected);
      stream_n[l]++;
      if (stream_n[l]==payload_count(l)) finish_at[l]=cycle;
    end
  endtask

  task automatic sample_model();
    int debt, active_count;
    bit all_results;
    logic [4:0] expected_flags;
    sampled_terminal=terminal; sampled_error=error;
    if (!live) return;
    age++; active_count=qk && t<4 ? t : 4;
    debt=0; all_results=1; expected_flags='0;
    for (int l=0; l<4; l++) begin
      debt+=write_n[l]-ack_n[l];
      if (active(l)) begin all_results &= result_valid[l]; expected_flags |= 5'(1<<l); end
    end
    assert (!fatal) else $fatal(1,"Unexpected fatal");
    assert (!(lease && cmd_ready)) else $fatal(1,"Command readmitted during lease");
    if (column_busy) begin
      assert (lease && !release_owner && !terminal && !cmd_ready && !query_read && !row_read && !column_start)
        else $fatal(1,"K busy ownership released/overlapped");
      if (sum_done()==active_count && sent_abort) busy_hold++;
      if (sent_abort) aborted_busy++;
    end
    if (release_owner || terminal) begin
      assert (debt==0 && !column_busy) else $fatal(1,"Premature release with debt or K busy");
    end
    if (sum_done()==active_count && debt>0) begin
      assert (lease && !release_owner && !terminal) else $fatal(1,"Final ack debt not retained");
      debt_hold++;
    end
    if (!commit && |result_valid) barrier_hold++;
    if (commit) begin
      assert (launched && !sent_abort && all_payloads() &&
              (qk ? queries==(d/16)*h && columns==d/4 && reads==0 : reads==t*d/16))
        else $fatal(1,"Commit before private work drain");
      for (int l=0; l<4; l++) if (active(l))
        assert (finish_at[l]>=0) else $fatal(1,"Incomplete lane at commit");
    end
    if (start) begin
      assert (owned=='1 && ready=='1 && !sent_abort) else $fatal(1,"Nonatomic launch");
      launched=1; launch_count++;
    end
    if (query_read) begin
      assert (qk && int'(query_row)==b+queries%h && int'(query_word)==queries/h)
        else $fatal(1,"Query identity/order");
      queries++;
    end
    if (column_start) begin
      assert (qk && int'(column_tokens)==t && int'(column_dimension)==columns*4 &&
              queries>=((columns/4)+1)*h) else $fatal(1,"Column launch/order");
      columns++;
    end
    if (row_read) begin
      assert (!qk && int'(row_token)==reads/(d/16) && int'(row_word)==reads%(d/16))
        else $fatal(1,"V row identity/order");
      reads++;
    end
    for (int l=0; l<4; l++) begin
      if (acquire) begin
        acquire_n[l]++;
        if (acquire_n[l]>l+1 && !(phase==1 && l==3)) own_m[l]=1;
      end
      if (release_owner) begin
        release_n[l]++;
        if (release_n[l]>l+1) own_m[l]=0;
      end
      if (source_valid[l] && source_ready[l]) begin
        assert (!qk && source_n[l]<24) else $fatal(1,"QK source or excess PV import");
        source_n[l]++;
      end
      if (qk) assert (!source_ready[l]) else $fatal(1,"QK enabled source ready");
      if (!active(l)) assert (!payload_valid[l]) else $fatal(1,"Inactive payload lane");
      if (stalled_payload[l] && !sent_abort && !(|lane_abort)) begin
        assert (payload_valid[l] && payload_data[l]===held_payload[l] &&
                payload_seed==held_seed && (payload_seed || payload_value==held_value))
          else $fatal(1,"Stalled payload changed");
      end
      if (payload_valid[l] && grant[l]) check_payload(l);
      if (payload_valid[l] && !grant[l]) stalled++;
      if (stalled_result[l] && !sent_abort && !(|lane_abort))
        assert (result_valid[l] && result_data[l]===held_result[l] &&
                result_slot[l]==held_slot[l] && result_be[l]==held_be[l])
          else $fatal(1,"Held result changed before acceptance");
      // Architectural sink grants only when central commit authorizes results.
      if (commit && result_valid[l] && grant[l]) begin
        assert (active(l) && !aborted[l] && write_n[l]<slots(l) &&
                result_data[l]=={16'hc047,16'(case_id),16'(l),16'(write_n[l])} &&
                int'(result_slot[l])==(write_n[l]/(slots(l)/h))*8+write_n[l]%(slots(l)/h) &&
                result_be[l]==(qk && elems(l)%2 && write_n[l]%(slots(l)/h)==slots(l)/h-1 ? 8'h0f : 8'hff))
          else $fatal(1,"Architectural result tag/slot/BE mismatch");
        if (writes==0) assert (all_results) else $fatal(1,"First result escaped complete barrier");
        assert (!vrf_written[l][result_slot[l]]) else $fatal(1,"Duplicate architectural word");
        vrf_written[l][result_slot[l]]=1;
        for (int byte_index=0; byte_index<8; byte_index++)
          if (result_be[l][byte_index]) vrf[l][result_slot[l]][8*byte_index+:8]=result_data[l][8*byte_index+:8];
        ack_due[l][write_n[l]]=cycle+(write_n[l]==slots(l)-1 ? 28+l : 2+l);
        write_n[l]++; writes++; checks++;
      end
      if (final_grant[l]) begin
        assert (ack_n[l]<write_n[l] && commit) else $fatal(1,"Unowned final ack");
        ack_n[l]++; acks++;
      end
      if (done_valid[l] && done_ready[l]) begin
        assert (done_n[l]==0 && active(l) &&
                (aborted[l] || write_n[l]==slots(l))) else $fatal(1,"Premature/duplicate lane done");
        done_n[l]++;
      end
      if (lane_abort[l] && launched && active(l)) aborted[l]=1;
    end
    stalled_payload=payload_valid & ~grant;
    held_payload=payload_data; held_seed=payload_seed; held_value=payload_value;
    stalled_result=result_valid & ~({4{commit}} & grant);
    held_result=result_data; held_slot=result_slot; held_be=result_be;
    if (terminal) begin
      terminal_count++;
      assert (response_id==cmd_id && owned==0 && error==(phase!=0) &&
              flags==(phase==0 ? expected_flags : 5'b0)) else $fatal(1,"Terminal identity/status/flags");
      for (int l=0; l<4; l++) begin
        assert (source_n[l]==(qk ? 0 : 24)) else $fatal(1,"Source drain incomplete");
        if (phase==0) assert (seed_n[l]==slots(l) && stream_n[l]==payload_count(l) &&
                             write_n[l]==slots(l) && ack_n[l]==slots(l) && done_n[l]==int'(active(l)))
          else $fatal(1,"Successful terminal missing lane work");
      end
    end
  endtask

  task automatic tick();
    @(negedge clk);
    drive_model();
    @(posedge clk);
    sample_model();
    cycle++;
    #1;
  endtask

  task automatic run_case(bit is_qk, int tokens, int heads, int dims, int query_base, int scenario);
    bit trigger;
    int source_total, coeff_total, value_total;
    qk=is_qk; t=tokens; h=heads; d=dims; b=query_base; phase=scenario; case_id++;
    live=0; launched=0; sent_abort=0; sampled_terminal=0; sampled_error=0;
    age=0; launch_count=0; reads=0; queries=0; columns=0; seed_total=0; writes=0; acks=0;
    checks=0; stalled=0; barrier_hold=0; debt_hold=0; busy_hold=0; aborted_busy=0; terminal_count=0;
    stalled_payload='0; stalled_result='0;
    for (int l=0; l<4; l++) begin
      own_m[l]=0; aborted[l]=0; source_n[l]=0; seed_n[l]=0; coeff_n[l]=0; value_n[l]=0;
      stream_n[l]=0; write_n[l]=0; ack_n[l]=0; done_n[l]=0; finish_at[l]=-1;
      acquire_n[l]=0; release_n[l]=0;
      for (int w=0; w<16; w++) begin
        ack_due[l][w]=0; vrf[l][w]=64'ha5a5a5a5a5a5a5a5; vrf_written[l][w]=0;
      end
    end
    cmd_valid=0; abort_req=0;
    repeat (2) tick();
    assert (cmd_ready && !lease && !column_busy) else $fatal(1,"Recovery not ready");
    cmd_qk=qk; cmd_id=vid_t'(case_id); base=3'(b); qrows=phase==5 ? 4 : 8;
    rm=phase==9 ? 5 : 0; context_valid=!(phase inside {7,10}); context_t=64; context_d=16'(d);
    control={2'(d==64 ? AkvHeadDimCode64 : d==96 ? AkvHeadDimCode96 : AkvHeadDimCode128),
             1'(h-1),6'(t-1)};
    cmd_valid=1;
    tick();
    assert (lease) else $fatal(1,"Command not accepted");
    cmd_valid=0; live=1;
    for (int limit=0; limit<12000; limit++) begin
      trigger=0;
      if (!sent_abort) case (phase)
        1: trigger=age>=5 && !launched;
        2: trigger=seed_total>0 && !all_payloads();
        3: trigger=column_busy;
        4: trigger=all_payloads() && |result_valid && !commit;
        8: trigger=seed_total>0;
        default: ;
      endcase
      abort_req=trigger;
      if (trigger) begin
        assert (!commit) else $fatal(1,"Abort crossed irreversible commit");
        sent_abort=1;
      end
      tick();
      if (sampled_terminal) break;
    end
    assert (sampled_terminal && terminal_count==1) else $fatal(1,"Bounded case timeout case=%0d phase=%0d",case_id,phase);
    assert (launch_count==(phase inside {1,5,6,7,9,10} ? 0 : 1)) else $fatal(1,"Unexpected launch");
    if (phase!=0) assert (writes==0 && acks==0) else $fatal(1,"Failed command wrote architecturally");
    if (phase inside {1,2,3,4,8}) assert (sent_abort) else $fatal(1,"Abort phase not reached");
    if (phase inside {1,5,6,7,9,10})
      assert (seed_total==0 && reads==0 && queries==0 && columns==0) else $fatal(1,"Prelaunch mutation");
    if (phase==3) assert (busy_hold>0 && aborted_busy>=3 && sum_done()==4)
      else $fatal(1,"Did not finish fast abort lanes while K busy");
    if (phase==4) assert (barrier_hold>0 && all_payloads()) else $fatal(1,"Precommit phase missing");
    if (phase==0) assert (barrier_hold>=2 && debt_hold>=12 && stalled>0)
      else $fatal(1,"Missing barrier/debt/backpressure exercise");
    source_total=0; coeff_total=0; value_total=0;
    for (int l=0; l<4; l++) begin
      source_total+=source_n[l]; coeff_total+=coeff_n[l]; value_total+=value_n[l];
      for (int w=0; w<16; w++) begin
        automatic int perhead=slots(l)/h;
        automatic bit used=phase==0 && active(l) && w/8<h && w%8<perhead;
        automatic logic [63:0] expected=64'ha5a5a5a5a5a5a5a5;
        if (used) begin
          expected={16'hc047,16'(case_id),16'(l),16'((w/8)*perhead+w%8)};
          if (qk && elems(l)%2 && w%8==perhead-1) expected[63:32]=32'ha5a5a5a5;
        end
        assert (vrf_written[l][w]==used && vrf[l][w]===expected)
          else $fatal(1,"VRF image/mask mismatch lane=%0d slot=%0d",l,w);
      end
    end
    $display("CONTROL_GATE_CASE id=%0d phase=%0d qk=%0d tokens=%0d heads=%0d dimensions=%0d base=%0d error=%0d launches=%0d sources=%0d seeds=%0d coefficients=%0d values=%0d results=%0d acks=%0d queries=%0d columns=%0d reads=%0d barrier_hold=%0d debt_hold=%0d busy_hold=%0d abort_busy=%0d stalls=%0d checks=%0d cycles=%0d",
      case_id,phase,qk,t,h,d,b,sampled_error,launch_count,source_total,seed_total,coeff_total,value_total,
      writes,acks,queries,columns,reads,barrier_hold,debt_hold,busy_hold,aborted_busy,stalled,checks,age);
    suite_checks+=checks; suite_cases++;
    live=0; abort_req=0;
    repeat (3) tick();
    assert (cmd_ready && !lease && !fatal) else $fatal(1,"No clean recovery");
  endtask

  initial begin
    cycle=0; case_id=0; suite_checks=0; suite_cases=0; live=0; launched=0;
    cmd_valid=0; cmd_qk=0; cmd_id=0; control=0; rm=0; base=0; abort_req=0;
    context_valid=0; context_d=64; context_t=64; qrows=8;
    for (int l=0; l<4; l++) begin own_m[l]=0; source_n[l]=0; ack_n[l]=0; write_n[l]=0; end
    repeat (4) tick();
    rst=1;
    repeat (2) tick();
    run_case(0,3,2,64,0,0);
    for (int i=0; i<5; i++) begin
      automatic int n;
      case(i) 0:n=1; 1:n=2; 2:n=3; 3:n=17; default:n=64; endcase
      for (int heads=1; heads<=2; heads++) run_case(1,n,heads,64,i%2 ? 8-heads : 3,0);
    end
    run_case(1,17,2,96,3,0);
    run_case(1,64,2,128,6,0);
    for (int p=1; p<=10; p++) begin
      run_case(!(p inside {8,10}),p inside {2,3} ? 64 : 17,2,64,p==6 ? 7 : 3,p);
      run_case(1,1,1,64,7,0);
      run_case(0,3,1,64,0,0);
    end
    $display("CONTROL_GATE_PASS cases=%0d checks=%0d cycles=%0d",suite_cases,suite_checks,cycle);
    $finish;
  end
  initial begin
    repeat (500000) @(posedge clk);
    $fatal(1,"Global control gate cycle bound");
  end
endmodule
