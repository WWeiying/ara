// SPDX-License-Identifier: SHL-0.51
// Two frames share one merger while an independently owned result is stalled.
module reduction_exact_overlap_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import ara_rce_pkg::*;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  rce_exact_command_t cmd;
  logic cmd_valid=0, cmd_ready;
  elen_t [3:0] data;
  logic [3:0] valid='0, ready, consumed;
  logic local_complete, result_valid, result_ready=0;
  rce_exact_result_t result, held;
  rce_exact_events_t events;
  logic [287:0] partial[4], expected_root;
  logic [31:0] seed, answer;
  logic [4:0] flags;
  int count[4], cursor[4], fp16, rm, cases=0, overlaps=0;
  bit heterogeneous, late_mode, transient_seed;
  logic late_seed_ready=1;
  logic [31:0] late_seed_bus;
  int before_seed_beats=0;
  int changed_format=0, changed_rounding=0;
  reduction_completion_engine #(.EnableExact(1'b1)) dut (
    .clk_i(clk), .rst_ni(rst_n), .cmd_i('0), .cmd_valid_i(1'b0), .cmd_ready_o(),
    .partial_i('0), .partial_valid_i('0), .partial_ready_o(),
    .seed_lifetime_i('0), .external_seed_i('0), .external_seed_valid_i('0), .ordinary_seed_i('0), .ordinary_seed_valid_i('0),
    .seed_i('0), .seed_valid_i(1'b0), .seed_ready_o(),
    .result_o(), .result_valid_o(), .result_ready_i(1'b0), .occupancy_o(),
    .exact_cmd_i(cmd), .exact_cmd_valid_i(cmd_valid), .exact_cmd_ready_o(cmd_ready),
    .exact_operand_i(data), .exact_operand_valid_i(valid), .exact_operand_ready_o(ready),
    .exact_seed_ready_i(late_seed_ready), .exact_seed_data_i(late_seed_bus), .exact_local_complete_o(local_complete),
    .exact_lane_consumed_o(consumed), .exact_result_o(result),
    .exact_result_valid_o(result_valid), .exact_result_ready_i(result_ready), .exact_events_o(events)
  );
  function automatic elen_t word(int lane,int beat,vid_t id);
    elen_t w='0;
    if(beat==0) begin
      w[63:32]=lane==0 ? seed : 0;
      w[31:28]=4'he; w[27:26]=2'(lane); w[21]=1;
      w[20]=partial[lane]!=0; w[19]=partial[lane]==0; w[17]=lane==0 && !late_mode;
      w[16:14]=3'(rm); w[13:11]=3'(count[lane]); w[10]=1'(fp16);
      w[8]=partial[lane][287]; w[7:0]=8'(id);
    end else if(beat==5) w={{32{partial[lane][287]}},partial[lane][287:256]};
    else w=64'(partial[lane]>>(64*(beat-1)));
    return w;
  endfunction
  task automatic send_frame(vid_t id, bit behind_held);
    int ticks;
    logic [3:0] fire;
    bit seed_bound;
    @(negedge clk);
    cmd='{id:id,vd:5'(id+8),version:vreg_version_t'(cases+1),late_seed:late_mode};
    ticks=0;
    while(!cmd_ready) begin
      @(negedge clk);
      if(++ticks>100) $fatal(1,"FAIL: next frame blocked by held result");
    end
    seed_bound=0;
    late_seed_bus=seed;
    late_seed_ready=!late_mode;
    cmd_valid=1;
    @(posedge clk);
    if(behind_held && (!result_valid || result!==held)) $fatal(1,"FAIL: old result lost at next command");
    @(negedge clk); cmd_valid=0;
    for(int l=0;l<4;l++) cursor[l]=0;
    ticks=0;
    while(cursor[0]<=count[0] || cursor[1]<=count[1] || cursor[2]<=count[2] || cursor[3]<=count[3]) begin
      for(int l=0;l<4;l++) if(!valid[l] && cursor[l]<=count[l] && $urandom_range(0,3)!=0) begin
        data[l]=word(l,cursor[l],id);valid[l]=1;
      end
      late_seed_ready = !late_mode ||
        ((!transient_seed || !seed_bound) && ticks >= (cases%3 == 0 ? 0 : cases%3 == 1 ? 3 : 24));
      late_seed_bus = transient_seed && seed_bound ? ~seed : seed;
      @(posedge clk);fire=valid & ready;
      if (events.seed_bind) seed_bound=1;
      if (!late_seed_ready && !seed_bound) before_seed_beats += $countones(fire);
      if(behind_held && (!result_valid || result!==held)) $fatal(1,"FAIL: second frame changed first result");
      for(int l=0;l<4;l++) if(fire[l]) cursor[l]++;
      if(++ticks>200) $fatal(1,"FAIL: second frame receive timeout");
      @(negedge clk);valid &= ~fire;
    end
    while (late_mode && !seed_bound) begin
      if (!behind_held && result_valid) $fatal(1,"FAIL: result before seed");
      if (local_complete) $fatal(1,"FAIL: adapter released before seed snapshot");
      if (consumed != 4'hf) $fatal(1,"FAIL: finished lanes not released during seed wait");
      ticks++;
      late_seed_ready = ticks >= (cases%3 == 0 ? 0 : cases%3 == 1 ? 3 : 24);
      late_seed_bus=seed;
      @(posedge clk);
      if (events.seed_bind) seed_bound=1;
      @(negedge clk);
    end
    if (transient_seed && late_mode) begin
      late_seed_ready=0;
      late_seed_bus=~seed;
    end
  endtask
  task automatic take_result(vid_t id,logic [31:0] expected_data,logic [4:0] expected_flags,bit expected_fp16);
    int ticks=0;
    while(!result_valid) begin
      @(negedge clk);
      if(++ticks>100) $fatal(1,"FAIL: missing completed frame");
    end
    if(result !== rce_exact_result_t'{id:id,vd:5'(id+8),version:vreg_version_t'(cases+1),
         be:expected_fp16 ? 8'h03 : 8'h0f,data:expected_data,fflags:expected_flags})
      $fatal(1,"FAIL: exact result value/owner case=%0d id=%0d got=%h expected=%h",cases,id,result.data,answer);
    result_ready=1;
    @(posedge clk);
    @(negedge clk);result_ready=0;
  endtask
  initial begin
    string path;
    int fd, scanned, random_seed=32'h51554555;
    logic [31:0] first_answer;
    logic [4:0] first_flags;
    int first_format,first_rm;
    if(!RceExactDecoupleEnable) $fatal(1,"FAIL: requires exact completion buffer");
    heterogeneous=$test$plusargs("HETERO_PAIR");
    late_mode=$test$plusargs("LATE_SEED");
    transient_seed=$test$plusargs("TRANSIENT_SEED");
    void'($value$plusargs("VECTOR_FILE=%s",path));
    void'($urandom(random_seed));
    fd=$fopen(path,"r");if(!fd)$fatal(1,"FAIL: missing vectors");
    cmd='0;data='0;
    repeat(3) @(negedge clk);rst_n=1;
    scanned=$fscanf(fd,"%d %d %h %h %h %h",fp16,rm,seed,expected_root,answer,flags);
    while(scanned==6) begin
      for(int l=0;l<4;l++) if($fscanf(fd,"%h %d",partial[l],count[l])!=2)$fatal(1,"FAIL: malformed vector");
      send_frame(vid_t'(2*cases%NrVInsn),0);
      repeat(4) @(negedge clk);
      if(!result_valid)$fatal(1,"FAIL: first result not buffered");
      held=result;
      first_answer=answer;first_flags=flags;first_format=fp16;first_rm=rm;
      if(heterogeneous) begin
        if($fscanf(fd,"%d %d %h %h %h %h",fp16,rm,seed,expected_root,answer,flags)!=6)
          $fatal(1,"FAIL: missing second heterogeneous record");
        for(int l=0;l<4;l++) if($fscanf(fd,"%h %d",partial[l],count[l])!=2)
          $fatal(1,"FAIL: malformed second record");
        changed_format += fp16 != first_format;
        changed_rounding += rm != first_rm;
      end
      send_frame(vid_t'((2*cases+1)%NrVInsn),1);
      repeat(128) begin
        @(negedge clk);
        if(!result_valid || result!==held)$fatal(1,"FAIL: stalled result overwritten");
      end
      overlaps++;
      take_result(vid_t'(2*cases%NrVInsn),first_answer,first_flags,1'(first_format));
      take_result(vid_t'((2*cases+1)%NrVInsn),answer,flags,1'(fp16));
      cases++;
      scanned=$fscanf(fd,"%d %d %h %h %h %h",fp16,rm,seed,expected_root,answer,flags);
    end
    if(!$feof(fd) || cases==0)$fatal(1,"FAIL: malformed input");
    $display("PASS: %0d exact paired frames; completed=%0d held-overlaps=%0d",cases,2*cases,overlaps);
    if(heterogeneous && (changed_format==0 || changed_rounding==0))
      $fatal(1,"FAIL: missing heterogeneous frame coverage");
    $display("HETERO: format_changes=%0d rounding_changes=%0d",changed_format,changed_rounding);
    if (late_mode && RceExactSeedReceiveEnable && before_seed_beats==0)
      $fatal(1,"FAIL: missing receive-before-seed coverage");
    if (late_mode && !RceExactSeedReceiveEnable && before_seed_beats!=0)
      $fatal(1,"FAIL: disabled feature accepted packets before seed");
    $display("SEED_RECEIVE: enabled=%0d before_seed_beats=%0d",RceExactSeedReceiveEnable,before_seed_beats);
    $finish;
  end
  initial begin #100000000; $fatal(1,"FAIL: watchdog"); end
endmodule
