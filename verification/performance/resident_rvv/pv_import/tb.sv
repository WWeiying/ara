// SPDX-License-Identifier: Apache-2.0
module resident_pv_import_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [$clog2(1024+1)-1:0] vlen_t;
  // Exact packed command declaration from the pinned lane.sv.
  typedef struct packed {
    rvv_pkg::vew_e eew;
    vlen_t elem_count;
    opqueue_conversion_e conv;
    logic [1:0] ntr_red;
    logic is_reduct;
    target_fu_e target_fu;
  } operand_queue_cmd_t;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  logic start_valid, start_ready, cancel, done_valid, done_ready, done_error, busy;
  logic [3:0] words, source_valid, source_ready, seed_valid, seed_ready;
  logic heads;
  logic [6:0] tokens;
  logic [3:0][63:0] source_data, seed_data, operand, pending_data;
  logic coefficient_valid, coefficient_ready;
  logic [31:0] coefficient;
  logic [3:0] cmd_valid, issued, returned, queue_ready, cmd_pop, queue_take, pending;
  target_fu_e target[4];
  operand_queue_cmd_t cmd;
  logic ordinary, feeding, checking, invalid_case, cancelled;
  int case_id, cw, ch, ct, mode, phase, cycle;
  int sent[4], received[4], popped[4], pops[4], seeds[4], sentinel[4];
  int issue_cycle[4];
  int coefficient_count, held_cycles;
  int total_good, total_invalid, total_cancel, total_source, total_pops, total_sentinel;
  int total_latency, total_held, seed_stalls, coefficient_stalls, full_credit, unequal;
  logic held;
  logic [31:0] held_pair;
  logic [3:0][63:0] held_heads;
  int unsigned rng = 32'h51ab930d;

  akv_resident_pv_import dut (
    .clk_i(clk), .rst_ni(rst_n), .start_valid_i(start_valid), .start_ready_o(start_ready),
    .words_i(words), .two_heads_i(heads), .tokens_i(tokens), .cancel_i(cancel),
    .source_valid_i(source_valid), .source_ready_o(source_ready), .source_data_i(source_data),
    .seed_valid_o(seed_valid), .seed_ready_i(seed_ready), .seed_data_o(seed_data),
    .coefficient_valid_o(coefficient_valid), .coefficient_ready_i(coefficient_ready),
    .coefficient_o(coefficient), .done_valid_o(done_valid), .done_ready_i(done_ready),
    .done_error_o(done_error), .busy_o(busy)
  );
  assign queue_take = ordinary ? 4'hf : source_ready;
  for (genvar l = 0; l < 4; l++) begin : gen_queue
    operand_queue #(
      .CmdBufDepth(VstuInsnQueueDepth+MaskuInsnQueueDepth), .DataBufDepth(2),
      .NrSlaves(1), .NrLanes(4), .VLEN(1024),
      .FPUSupport(FPUSupportNone), .AccessCmdPop(1),
      .operand_queue_cmd_t(operand_queue_cmd_t)
    ) queue_i (
      .clk_i(clk), .rst_ni(rst_n), .flush_i(1'b0), .lane_id_i(2'(l)),
      .operand_queue_cmd_i(cmd), .operand_queue_cmd_valid_i(cmd_valid[l]),
      .cmd_pop_o(cmd_pop[l]), .operand_i(operand[l]), .operand_valid_i(returned[l]),
      .operand_issued_i(issued[l]), .operand_queue_ready_o(queue_ready[l]),
      .operand_o(source_data[l]), .operand_target_fu_o(target[l]),
      .operand_valid_o(source_valid[l]), .operand_ready_i(queue_take[l])
    );
  end

  function automatic logic [15:0] natural_half(input int index);
    return 16'((case_id*997 + index*37) ^ (index<<9) ^ 16'ha56c);
  endfunction

  // Independent explicit natural EW16 ordering, not a DUT shuffle helper.
  function automatic logic [63:0] physical_word(input int lane, word_index);
    return {natural_half(word_index*16+lane+12), natural_half(word_index*16+lane+4),
            natural_half(word_index*16+lane+8), natural_half(word_index*16+lane)};
  endfunction

  function automatic logic [31:0] expected_pair(input int token_index);
    return {natural_half(256+2*token_index+1), natural_half(256+2*token_index)};
  endfunction

  function automatic logic [63:0] sentinel_word(input int lane);
    return 64'hdead0000beef0000 ^ (64'(case_id)<<20) ^ 64'(lane*177);
  endfunction

  function automatic int minimum_popped();
    int n;
    n = popped[0];
    for (int l = 1; l < 4; l++) if (popped[l] < n) n = popped[l];
    return n;
  endfunction

  task automatic tick();
    // Calls begin/end on the falling edge. Return the previous edge's issue.
    returned = pending;
    operand = pending_data;
    issued = '0;
    for (int l = 0; l < 4; l++) begin
      if (feeding && sent[l] < 25 && queue_ready[l] && (cycle+l*2)%(l+2) == 0)
        issued[l] = 1;
    end
    #1;
    @(posedge clk);
    if (checking) begin
      if (cycle > 4000) $fatal(1,"case timeout id=%0d phase=%0d",case_id,phase);
      if (invalid_case && (source_ready != 0 || seed_valid != 0 || coefficient_valid ||
                           cmd_valid != 0 || issued != 0 || returned != 0 || source_valid != 0))
        $fatal(1,"invalid configuration requested source");
      if ((cancel || cancelled) && (seed_valid != 0 || coefficient_valid))
        $fatal(1,"cancel leaked computation");
      if (held && !cancel) begin
        if (!coefficient_valid || coefficient !== held_pair || source_data !== held_heads)
          $fatal(1,"coefficient or real queue heads changed under hold");
      end
      held = coefficient_valid && !coefficient_ready && !cancel;
      if (held) begin
        held_pair = coefficient;
        held_heads = source_data;
        coefficient_stalls++;
        held_cycles++;
      end
      if (coefficient_valid) begin
        if (coefficient !== expected_pair(coefficient_count))
          $fatal(1,"pair raw bits id=%0d token=%0d actual=%h expected=%h",
                 case_id,coefficient_count,coefficient,expected_pair(coefficient_count));
        for (int l = 0; l < 4; l++) begin
          if (seeds[l] != cw*ch || popped[l] != 16+coefficient_count/8)
            $fatal(1,"coefficient before seeds/group alignment");
        end
        if (!(coefficient_ready && (coefficient_count%8 == 7 || coefficient_count == ct-1))
            && source_ready != 0) $fatal(1,"coefficient group popped before last pair");
        if (coefficient_ready) coefficient_count++;
      end
      if (source_valid != 0 && source_valid != 15) unequal++;
      for (int l = 0; l < 4; l++) begin
        if (queue_ready[l] !== (sent[l]-popped[l] < 2)) $fatal(1,"credit disagreement");
        if (!queue_ready[l]) full_credit++;
        if (returned[l] !== pending[l]) $fatal(1,"return latency not one cycle");
        if (returned[l]) begin
          if (received[l] >= sent[l]) $fatal(1,"return without prior issue");
          if (cycle != issue_cycle[l]+1 ||
              operand[l] !== (received[l]==24 ? sentinel_word(l) : physical_word(l,received[l])))
            $fatal(1,"return timing/order mismatch");
          received[l]++;
          total_latency++;
        end
        if (seed_valid[l]) begin
          int index;
          index = (seeds[l]/cw)*8 + seeds[l]%cw;
          if (seeds[l] >= cw*ch || popped[l] != index || seed_data[l] !== physical_word(l,index))
            $fatal(1,"seed ordering/inactive leak id=%0d lane=%0d index=%0d popped=%0d",
                   case_id,l,index,popped[l]);
          if (seed_ready[l]) seeds[l]++;
          else seed_stalls++;
        end
        if (cmd_pop[l] !== (source_valid[l] && queue_take[l] && (popped[l] == 23 || ordinary)))
          $fatal(1,"command pop not exactly last source/sentinel word");
        if (source_valid[l] && queue_take[l]) begin
          if (popped[l] >= received[l]) $fatal(1,"consumed unreturned word");
          if (ordinary) begin
            if (popped[l] != 24 || source_data[l] !== sentinel_word(l) || target[l] != ALU_SLDU)
              $fatal(1,"ordinary following command corrupted id=%0d lane=%0d",case_id,l);
            sentinel[l]++;
            total_sentinel++;
          end else begin
            if (popped[l] >= 24 || source_data[l] !== physical_word(l,popped[l]))
              $fatal(1,"source overpop/stale data");
            total_source++;
            if (cmd_pop[l]) begin pops[l]++; total_pops++; end
          end
          popped[l]++;
        end
        if (issued[l]) begin
          if (!queue_ready[l]) $fatal(1,"issued without credit");
          issue_cycle[l] = cycle;
          pending_data[l] = sent[l] == 24 ? sentinel_word(l) : physical_word(l,sent[l]);
          sent[l]++;
        end
        if (sent[l]-popped[l] > 2 || sent[l] < popped[l]) $fatal(1,"credit bounds");
      end
      if (cancel) cancelled = 1;
    end
    pending = issued;
    cycle++;
    #1;
    @(negedge clk);
  endtask

  task automatic run_case(input int w,h,t,m,p);
    int observed_seeds;
    case_id++;
    cw=w; ch=h; ct=t; mode=m; phase=p; cycle=0;
    words=4'(w); heads=h==2; tokens=7'(t);
    invalid_case=!(w inside {4,6,8} && t inside {[1:64]});
    cancelled=0; cancel=0; ordinary=0; feeding=0; held=0; held_cycles=0;
    coefficient_count=0; pending=0; checking=1;
    for (int l=0;l<4;l++) begin
      sent[l]=0; received[l]=0; popped[l]=0; pops[l]=0; seeds[l]=0; sentinel[l]=0;
    end
    if (!start_ready || source_valid != 0) $fatal(1,"reuse not immediately clean");
    start_valid=1; done_ready=0; seed_ready=0; coefficient_ready=0;
    cmd='0; cmd.eew=EW16; cmd.elem_count=96; cmd.conv=OpQueueConversionNone; cmd.target_fu=ALU_SLDU;
    cmd_valid=invalid_case ? 0 : 15;
    tick();
    start_valid=0;
    // Both commands reside in the real StA command FIFO from the outset.
    cmd.elem_count=4;
    feeding=!invalid_case;
    tick();
    cmd_valid=0;
    while (!done_valid) begin
      rng = rng ^ (rng<<13); rng = rng ^ (rng>>17); rng = rng ^ (rng<<5);
      for (int l=0;l<4;l++)
        seed_ready[l] = mode==0 || (mode==1 ? (cycle+l)%5==0 : rng[l+:2]!=0);
      coefficient_ready = mode==0 || (mode==1 ? cycle%7==0 : rng[20+:2]!=0);
      // A long, deterministic hold inside a group, in addition to randomized stalls.
      if (mode!=0 && coefficient_count==0 && held_cycles<12) coefficient_ready=0;
      if (!cancelled && phase==1 && seeds[0]>=1) begin
        if (popped[0]>=16 || coefficient_count!=0) $fatal(1,"seed cancel missed phase");
        cancel=1;
      end
      if (!cancelled && phase==2 && coefficient_count==3) begin
        coefficient_ready=0; cancel=1;
      end
      if (!cancelled && phase==3 && coefficient_count==ct && minimum_popped()>=17) begin
        if (minimum_popped()>=24) $fatal(1,"drain cancel has no owned source remaining");
        cancel=1;
      end
      tick();
      cancel=0;
    end
    if (done_error !== (invalid_case || phase!=0)) $fatal(1,"completion status");
    if (phase!=0 && !cancelled) $fatal(1,"cancel phase not exercised");
    if (!invalid_case) begin
      for (int l=0;l<4;l++) begin
        if (popped[l]!=24 || pops[l]!=1) $fatal(1,"incomplete owned-source drain");
        if (phase==0 && seeds[l]!=cw*ch) $fatal(1,"seed count");
      end
      if (phase==0 && coefficient_count!=ct) $fatal(1,"coefficient count");
    end
    repeat (6) begin
      if (!done_valid || done_error !== (invalid_case || phase!=0) || !busy || start_ready ||
          source_ready!=0 || seed_valid!=0 || coefficient_valid) $fatal(1,"held done changed");
      start_valid=1;
      tick();
      total_held++;
    end
    start_valid=0;
    // Consume the following ordinary command before releasing completion; no reset/flush.
    if (!invalid_case) begin
      ordinary=1;
      while (sentinel[0]+sentinel[1]+sentinel[2]+sentinel[3]!=4) tick();
      ordinary=0;
      for (int l=0;l<4;l++)
        if (sent[l]!=25 || received[l]!=25 || popped[l]!=25 || sentinel[l]!=1)
          $fatal(1,"following command counts");
    end
    feeding=0;
    done_ready=1; tick(); done_ready=0;
    if (!start_ready || busy || done_valid || source_valid!=0 || queue_ready!=15)
      $fatal(1,"reuse failed");
    observed_seeds=seeds[0]+seeds[1]+seeds[2]+seeds[3];
    if (invalid_case) begin
      total_invalid++;
      $display("IMPORT_INVALID_PASS words=%0d heads=%0d tokens=%0d",w,h,t);
    end else begin
      if (phase==0) total_good++; else total_cancel++;
      $display("IMPORT_CASE_PASS words=%0d heads=%0d tokens=%0d mode=%0d cancel=%0d seeds=%0d coefficients=%0d sourcewords=96 cmdpops=4 sentinels=4",w,h,t,m,p,observed_seeds,coefficient_count);
    end
  endtask

  initial begin
    int ts[5] = '{1,8,9,63,64};
    start_valid=0; cancel=0; done_ready=0; words=0; heads=0; tokens=0;
    seed_ready=0; coefficient_ready=0; cmd_valid=0; cmd='0;
    issued=0; returned=0; pending=0; operand=0; ordinary=0; feeding=0; checking=0;
    repeat (3) @(negedge clk);
    rst_n=1;
    @(negedge clk);
    for (int w=4;w<=8;w+=2)
      for (int h=1;h<=2;h++)
        foreach (ts[i])
          for (int m=0;m<3;m++) run_case(w,h,ts[i],m,0);
    for (int w=4;w<=8;w+=2)
      for (int h=1;h<=2;h++)
        for (int p=1;p<=3;p++) begin
          run_case(w,h,p==3 ? 1 : 9,2,p);
          run_case(w,h,9,1,0);
        end
    for (int w=0;w<16;w++)
      if (!(w inside {4,6,8}))
        for (int h=1;h<=2;h++) run_case(w,h,9,0,0);
    for (int w=4;w<=8;w+=2)
      for (int h=1;h<=2;h++) begin
        run_case(w,h,0,0,0); run_case(w,h,65,0,0); run_case(w,h,127,0,0);
      end
    $display("IMPORT_PASS cases=%0d good=%0d invalid=%0d cancelled=%0d sourcewords=%0d cmdpops=%0d sentinels=%0d latency=%0d held_done=%0d seed_stalls=%0d coefficient_stalls=%0d full_credit=%0d unequal=%0d",
             case_id,total_good,total_invalid,total_cancel,total_source,total_pops,total_sentinel,
             total_latency,total_held,seed_stalls,coefficient_stalls,full_credit,unequal);
    $finish;
  end
  initial begin #20000000; $fatal(1,"global bounded timeout"); end
endmodule
