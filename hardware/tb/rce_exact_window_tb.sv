// SPDX-License-Identifier: SHL-0.51
// Focused registered exact-completion boundary test. Fixed-point lane inputs
// encode 1.0 + 2.0 independently (bits 149 and 150), plus a header seed.
module rce_exact_window_tb;
  import ara_pkg::*;
  import ara_rce_pkg::*;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  rce_exact_command_t command;
  logic command_valid=0, command_ready;
  elen_t [3:0] operand='0;
  logic [3:0] operand_valid='0, operand_ready;
  rce_exact_result_t result, held;
  logic result_valid, result_ready=0;
  logic local_complete;
  logic seed_ready=0;
  logic [31:0] seed_data=0;
  rce_exact_events_t events;
  int serial, fmt, rm, late;
  int expected_cases=80, root_checks=0, seed_fold_test=0;
  int expected_fold, header_ready, folded_cases=0, fallback_cases=0;
  int want_special, want_nonzero, want_poszero, want_negzero;
  logic [287:0] fixed_seed, total_root;
  logic [287:0] expected_root;
  logic [31:0] seed_bits, expected_data;
  logic [4:0] expected_flags;
  int skips[4], ends[4];
  logic [287:0] values[4];
  rce_exact_result_t expected;
  int checked=0, stale_checks=0, header_only=0, tokens=0;
  logic [3:0] lane_consumed;
  // Match SLDU's spill-to-RCE adapter: consumed lanes retain queued raw
  // headers while masking their valid until the next frame starts.
  logic [3:0] rce_operand_valid;
  assign rce_operand_valid=operand_valid & ~lane_consumed;
  logic future_held=0;
  elen_t future_header;
  int future_blocked=0;
  always @(posedge clk) if (rst_n && future_held && dut.gen_exact.owner_q.id!=vid_t'(1)) begin
    if (operand_ready[3]) $fatal(1,"FAIL: old frame consumed next-context header");
    if (operand_valid[3] && operand[3]!==future_header)
      $fatal(1,"FAIL: queued next-context header changed");
    future_blocked++;
  end

  int simultaneous=0, accepted=0, popped=0;
  int header_seed_wait_cases=0, header_seed_wait_cycles=0, postbody_seed_wait_cases=0;
  logic was_stalled=0;
  rce_exact_result_t stalled_result;
  reduction_completion_engine #(.EnableExact(1'b1)) dut (
    .clk_i(clk),.rst_ni(rst_n),
    .cmd_i('0),.cmd_valid_i(1'b0),.cmd_ready_o(),
    .partial_i('0),.partial_valid_i('0),.partial_ready_o(),
    .seed_i('0),.seed_valid_i(1'b0),.seed_ready_o(),
    .seed_lifetime_i('0),.external_seed_i('0),.external_seed_valid_i('0),
    .ordinary_seed_i('0),.ordinary_seed_valid_i('0),
    .result_o(),.result_valid_o(),.result_ready_i(1'b0),.occupancy_o(),
    .shared_add_ready_i(1'b0),.shared_add_response_i('0),.shared_add_response_valid_i(1'b0),
    .exact_cmd_i(command),.exact_cmd_valid_i(command_valid),.exact_cmd_ready_o(command_ready),
    .exact_operand_i(operand),.exact_operand_valid_i(rce_operand_valid),.exact_operand_ready_o(operand_ready),
    .exact_seed_ready_i(seed_ready),.exact_seed_data_i(seed_data),.exact_local_complete_o(local_complete),
    .exact_lane_consumed_o(lane_consumed),.exact_result_o(result),.exact_result_valid_o(result_valid),
    .exact_result_ready_i(result_ready),.exact_events_o(events)
  );
  always @(posedge clk) begin
    if (!rst_n) was_stalled=0;
    else begin
      if (was_stalled && (!result_valid || result !== stalled_result))
        $fatal(1,"FAIL: result changed across a stalled cycle");
      was_stalled=result_valid && !result_ready;
      stalled_result=result;
    end
  end
  always @(posedge clk) if (rst_n) begin
    if (command.late_seed && !seed_ready && !dut.gen_exact.exact_seed_valid_q && local_complete)
      $fatal(1,"FAIL: exact frame completed locally before late seed arrived");
    if (!RceExactSeedReceiveEnable && dut.gen_exact.state_q.name()=="EXACT_SEED_WAIT")
      $fatal(1,"FAIL: production mode0 entered postbody seed wait");
    if (command_valid && command_ready) accepted++;
    if (result_valid && result_ready) popped++;
    if (dut.gen_exact.completed_push && result_valid && result_ready) simultaneous++;
  end
  task automatic tick;
    @(posedge clk); #1;
  endtask
  task automatic read_case(input int fd,output bit available);
    int count, start, last;
    count=$fscanf(fd,"%d %d %d %d %h %h %h",serial,fmt,rm,late,seed_bits,expected_data,expected_flags);
    if (count!=7 && !$feof(fd)) $fatal(1,"FAIL: malformed case record count=%0d",count);
    available=count==7;
    if (available) begin
      for (int lane=0;lane<4;lane++) begin
        count=$fscanf(fd,"%d %d %h",skips[lane],ends[lane],values[lane]);
        if (count!=3) $fatal(1,"FAIL: malformed lane vector");
      end
      expected_root=values[0]+values[1]+values[2]+values[3];
      if(seed_fold_test) begin
        count=$fscanf(fd,"%h %d %d %h %d %d %d",fixed_seed,expected_fold,header_ready,
                      want_special,want_nonzero,want_poszero,want_negzero);
        if(count!=7) $fatal(1,"FAIL: malformed seed oracle record");
      end else begin
        // Legacy vectors use only +0 and +1 seeds; preserve their byte format.
        fixed_seed=(seed_bits==0)?288'b0:(288'b1<<149);
        start=6;last=0;
        for(int lane=0;lane<4;lane++) begin
          if(skips[lane]+1<start) start=skips[lane]+1;
          if(ends[lane]>last) last=ends[lane];
        end
        expected_fold=(!late || !RceExactSeedReceiveEnable) && start<=last &&
          ((fixed_seed & ((288'b1<<((start-1)*64))-1))==0) &&
          ((fixed_seed >> (last*64))==0);
        header_ready=0;want_special=0;want_nonzero=|fixed_seed;
        want_poszero=seed_bits==0;want_negzero=0;
        for(int lane=0;lane<4;lane++) begin
          want_nonzero|=values[lane]!=0;want_poszero|=values[lane]==0;
        end
      end
      total_root=expected_root+fixed_seed;
      expected='{id:vid_t'(serial),vd:5'(serial+4),version:vreg_version_t'(serial+2),
        be:fmt?8'h03:8'h0f,data:expected_data,fflags:expected_flags};
    end
  endtask
  task automatic check_result(input rce_exact_result_t want);
    if (!result_valid || result !== want)
      $fatal(1,"FAIL: case=%0d expected=%h actual=%h valid=%b",serial,want,result,result_valid);
  endtask
  task automatic issue;
    @(negedge clk);
    command='{id:vid_t'(serial),vd:5'(serial+4),version:vreg_version_t'(serial+2),late_seed:1'(late)};
    command_valid=1; seed_ready=0; seed_data=seed_bits;
    #1; if (!command_ready) $fatal(1,"FAIL: next command blocked");
    tick(); @(negedge clk); command_valid=0;
  endtask
  task automatic frame;
    elen_t [3:0] headers;
    int cursor[4];
    int left, cycles, implicit_cycles;
    for (int lane=0;lane<4;lane++) begin
      headers[lane]='0;
      headers[lane][31:28]=4'he;
      headers[lane][27:26]=2'(lane);
      headers[lane][21]=1'b1;
      headers[lane][20]=values[lane]!=0;
      headers[lane][19]=values[lane]==0;
      headers[lane][17]=(lane==0 && !late);
      headers[lane][16:14]=3'(rm);
      headers[lane][13:11]=3'(ends[lane]);
      headers[lane][10]=1'(fmt);
      headers[lane][8]=values[lane][287];
      headers[lane][7:5]=3'(skips[lane]);
      headers[lane][4:0]=5'(vid_t'(serial));
      cursor[lane]=skips[lane]+1;
    end
    if (!late) headers[0][63:32]=seed_bits;
    // A stale lane-zero token must be discarded without consuming the other
    // matching headers, even when the skip field is nonzero.
    @(negedge clk); seed_ready=1'(header_ready); operand=headers; operand_valid='1;
    operand[0][4:0]=5'(vid_t'(serial)^vid_t'(1));
    @(posedge clk);
    if (operand_ready!==4'b0001 || events.stale_token_drop!==4'b0001)
      $fatal(1,"FAIL: stale ID was not isolated");
    stale_checks++;
    @(negedge clk); operand=headers;
    if (!RceExactSeedReceiveEnable && late && !header_ready) begin
      header_seed_wait_cases++;
      repeat(2) begin
        @(posedge clk);
        if (operand_ready!==4'b0000 || local_complete || !events.seed_wait || events.header_fire)
          $fatal(1,"FAIL: mode0 header seed rendezvous case=%0d ready=%b complete=%b seed_wait=%b",serial,operand_ready,local_complete,events.seed_wait);
        header_seed_wait_cycles++;
        @(negedge clk);
      end
      seed_ready=1;
    end
    @(posedge clk);
    if (operand_ready!==4'hf || !events.header_fire)
      $fatal(1,"FAIL: legal window headers rejected case=%0d",serial);
    #1;
    if (serial==1) future_held=0;
    if (serial==0) begin
      // Lane three has a header-only zero window. Its producer is already
      // allowed to queue context one while lanes zero/one still send payload.
      future_header=headers[3];
      future_header[4:0]=5'd1;
      future_header[16:14]=3'd1;
      future_held=1;
    end
    left=0;
    for (int lane=0;lane<4;lane++) if (cursor[lane]<=ends[lane]) left++;
    if (!left) header_only++;
    cycles=0;
    while (left) begin
      @(negedge clk);
      for (int lane=0;lane<4;lane++) begin
        operand_valid[lane]=(cursor[lane]<=ends[lane]) && ((cycles+lane)%5!=0);
        operand[lane]=64'($signed(values[lane]) >>> ((cursor[lane]-1)*64));
      end
      if (future_held) begin operand_valid[3]=1;operand[3]=future_header;end
      @(posedge clk);
      for (int lane=0;lane<4;lane++) if (cursor[lane]<=ends[lane] && operand_valid[lane] && operand_ready[lane]) begin
        cursor[lane]++; tokens++;
      end
      #1; cycles++;
      if (cycles>80) $fatal(1,"FAIL: frame deadlock case=%0d",serial);
      left=0;
      for (int lane=0;lane<4;lane++) if(cursor[lane]<=ends[lane]) left++;
    end
    @(negedge clk); operand_valid='0;
    if(future_held) begin operand_valid[3]=1;operand[3]=future_header;end
    // Header-only lanes with different endpoints can require implicit
    // zero/sign merge cycles even though every physical token is consumed.
    implicit_cycles=0;
    while(dut.gen_exact.state_q.name()=="EXACT_RECEIVE") begin
      tick(); implicit_cycles++;
      if(implicit_cycles>5) $fatal(1,"FAIL: implicit suffix did not finish");
    end
    if (RceExactSeedReceiveEnable && late && !header_ready) begin
      postbody_seed_wait_cases++;
      if (dut.gen_exact.state_q.name()!="EXACT_SEED_WAIT")
        $fatal(1,"FAIL: late seed not awaited");
      repeat(2) tick();
      @(negedge clk); seed_ready=1;
      tick();
      @(negedge clk); seed_ready=0;
    end
    // The root register remains before normalization on both legal paths.
    if(dut.gen_exact.exact_seed_folded_q !== 1'(expected_fold))
      $fatal(1,"FAIL: fold choice case=%0d expected=%0d actual=%b",serial,expected_fold,dut.gen_exact.exact_seed_folded_q);
    if(expected_fold) begin
      folded_cases++;
      if(dut.gen_exact.state_q.name()!="EXACT_RESULT" || dut.gen_exact.exact_root_q!==total_root)
        $fatal(1,"FAIL: folded root case=%0d expected=%h actual=%h state=%s",serial,total_root,dut.gen_exact.exact_root_q,dut.gen_exact.state_q.name());
    end else begin
      fallback_cases++;
      if(dut.gen_exact.state_q.name()!="EXACT_SEED_ADD" || dut.gen_exact.exact_root_q!==expected_root)
        $fatal(1,"FAIL: fallback source root case=%0d expected=%h actual=%h state=%s",serial,expected_root,dut.gen_exact.exact_root_q,dut.gen_exact.state_q.name());
      tick();
    end
    root_checks++;
    if(dut.gen_exact.state_q.name()!="EXACT_RESULT" || dut.gen_exact.exact_root_q!==total_root)
      $fatal(1,"FAIL: seed not merged exactly once case=%0d expected=%h actual=%h",serial,total_root,dut.gen_exact.exact_root_q);
    if(dut.gen_exact.exact_special_q!==4'(want_special) ||
       dut.gen_exact.exact_finite_nonzero_seen_q!==1'(want_nonzero) ||
       dut.gen_exact.exact_pos_zero_seen_q!==1'(want_poszero) ||
       dut.gen_exact.exact_neg_zero_seen_q!==1'(want_negzero))
      $fatal(1,"FAIL: seed metadata case=%0d special=%h/%h nonzero=%b/%b pos=%b/%b neg=%b/%b",serial,dut.gen_exact.exact_special_q,4'(want_special),dut.gen_exact.exact_finite_nonzero_seen_q,1'(want_nonzero),dut.gen_exact.exact_pos_zero_seen_q,1'(want_poszero),dut.gen_exact.exact_neg_zero_seen_q,1'(want_negzero));
  endtask
  initial begin
    string path;
    int fd;
    bit available;
    rce_exact_result_t first, second;
    if (!RceExactDecoupleEnable)
      $fatal(1,"FAIL: required exact buffer disabled");
    if (!$value$plusargs("VECTOR_FILE=%s",path)) $fatal(1,"FAIL: missing vectors");
    void'($value$plusargs("EXPECT_CASES=%d",expected_cases));
    void'($value$plusargs("SEED_FOLD=%d",seed_fold_test));
    fd=$fopen(path,"r");
    if (!fd) $fatal(1,"FAIL: cannot read vectors");
    repeat(2) tick(); @(negedge clk); rst_n=1;
    read_case(fd,available);
    while(available) begin
      first=expected;
      issue(); frame();
      if(result_valid) $fatal(1,"FAIL: first result transparent before completion capture");
      tick(); check_result(first); checked++;
      repeat(2) begin tick();check_result(first);end
      read_case(fd,available);
      if(!available) $fatal(1,"FAIL: expected paired test vectors");
      second=expected;
      issue(); frame();check_result(first);
      repeat(2) begin tick();check_result(first);end
      @(negedge clk);result_ready=1;
      #1;if(!dut.gen_exact.completed_push) $fatal(1,"FAIL: no same-cycle replacement");
      tick();check_result(second);checked++;
      @(negedge clk);result_ready=0;
      repeat(2) begin tick();check_result(second);end
      read_case(fd,available);
      if (!available) begin
        @(negedge clk);rst_n=0;
        tick();if(result_valid || !command_ready) $fatal(1,"FAIL: reset retained exact frame");
        @(negedge clk);rst_n=1;
        repeat(2) begin tick();if(result_valid) $fatal(1,"FAIL: reset result reappeared");end
      end else begin
        @(negedge clk);result_ready=1;
        tick();if(result_valid) $fatal(1,"FAIL: result did not pop");
        @(negedge clk);result_ready=0;
      end
    end
    if (checked!=expected_cases || root_checks!=expected_cases || simultaneous!=expected_cases/2 || header_only==0 || stale_checks!=expected_cases || future_blocked==0)
      $fatal(1,"FAIL: coverage checked=%0d simultaneous=%0d headeronly=%0d stale=%0d",checked,simultaneous,header_only,stale_checks);
    if (!RceExactSeedReceiveEnable && (header_seed_wait_cases==0 || postbody_seed_wait_cases!=0))
      $fatal(1,"FAIL: missing production header seed wait coverage");
    $display("RCE_EXACT_SEED_PROTOCOL seed_receive=%0d header_wait_cases=%0d header_wait_cycles=%0d postbody_wait_cases=%0d",RceExactSeedReceiveEnable,header_seed_wait_cases,header_seed_wait_cycles,postbody_seed_wait_cases);
    $display("RCE_EXACT_WINDOW_PASS cases=%0d simultaneous=%0d headeronly=%0d stale=%0d tokens=%0d future_blocked=%0d roots=%0d folded=%0d fallback=%0d",checked,simultaneous,header_only,stale_checks,tokens,future_blocked,root_checks,folded_cases,fallback_cases);
    $finish;
  end
  initial begin #200000; $fatal(1,"FAIL: window timeout"); end
endmodule
