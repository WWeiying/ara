// SPDX-License-Identifier: SHL-0.51
// Check architectural publication timing, cached and simultaneous binding,
// stale register/version rejection, and ID reuse with a wrapped version.
module reduction_integer_seed_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import ara_rce_pkg::*;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  rce_command_t cmd;
  logic cmd_valid=0,cmd_ready;
  rce_partial_t [3:0] partial;
  logic [3:0] partial_valid='0,partial_ready;
  rce_seed_t seed;
  logic seed_valid=0,seed_ready;
  rce_result_t result;
  logic result_valid,result_ready=0;
  int checked=0;
  reduction_completion_engine #(.EnableExact(0)) dut (
    .clk_i(clk),.rst_ni(rst_n),.cmd_i(cmd),.cmd_valid_i(cmd_valid),.cmd_ready_o(cmd_ready),
    .partial_i(partial),.partial_valid_i(partial_valid),.partial_ready_o(partial_ready),
    .seed_i(seed),.seed_valid_i(seed_valid),.seed_ready_o(seed_ready),
    .result_o(result),.result_valid_o(result_valid),.result_ready_i(result_ready),.occupancy_o(),
    .exact_cmd_i('0),.exact_cmd_valid_i(0),.exact_cmd_ready_o(),
    .exact_operand_i('0),.exact_operand_valid_i('0),.exact_operand_ready_o(),
    .exact_seed_ready_i(0),.exact_seed_data_i('0),.exact_local_complete_o(),
    .exact_result_o(),.exact_result_valid_o(),.exact_result_ready_i(0),.exact_events_o()
  );
  function automatic rce_command_t descriptor(int id,int vd,int version,
      rce_seed_mode_e mode,elen_t value,int producer=0,int regnum=8,int epoch=1);
    return '{id:vid_t'(id),vd:5'(vd),vd_version:vreg_version_t'(version),
      op:VREDSUM,eew:EW64,seed_mode:mode,seed:value,seed_producer:vid_t'(producer),
      seed_register:5'(regnum),seed_version:vreg_version_t'(epoch),default:'0};
  endfunction
  task automatic command(input rce_command_t value);
    @(negedge clk);cmd=value;cmd_valid=1;
    do @(posedge clk); while(!cmd_ready);
    @(negedge clk);cmd_valid=0;
  endtask
  task automatic parts(int id,elen_t value);
    @(negedge clk);
    for(int l=0;l<4;l++) partial[l]='{id:vid_t'(id),data:value,source_active:1,default:'0};
    partial_valid='1;
    do @(posedge clk); while(partial_ready!='1);
    @(negedge clk);partial_valid='0;
  endtask
  task automatic take(int id,elen_t expected);
    while(!result_valid) @(negedge clk);
    if(result.id!=id || result.data!==expected || result.fflags || !result.write_enable)
      $fatal(1,"FAIL seed result id=%0d got=%h expected id=%0d data=%h",result.id,result.data,id,expected);
    result_ready=1;@(posedge clk);checked++;
    @(negedge clk);result_ready=0;
  endtask
  task automatic unpublished(int consumer);
    while(!result_valid) @(negedge clk);
    repeat(7) begin
      for(int s=0;s<2;s++)
        if(dut.valid_q[s] && dut.command_q[s].id==consumer && dut.seed_ready_q[s])
          $fatal(1,"FAIL seed published before actual producer result acceptance");
      @(negedge clk);
    end
  endtask
  task automatic no_result();
    repeat(15) begin
      @(negedge clk);
      if(result_valid) $fatal(1,"FAIL stale seed matched register/version");
    end
  endtask
  task automatic broadcast(int producer,int regnum,int epoch,elen_t data,bit accepted);
    @(negedge clk);seed='{producer:vid_t'(producer),vd:5'(regnum),
      version:vreg_version_t'(epoch),data:data};seed_valid=1;
    @(posedge clk);
    if(seed_ready!==accepted) $fatal(1,"FAIL external seed tag acceptance");
    @(negedge clk);seed_valid=0;
  endtask
  initial begin
    cmd='0;partial='0;seed='0;
    repeat(3) @(negedge clk);rst_n=1;
    if(!RceIntLateSeedEnable) $fatal(1,"FAIL integer late-seed feature not enabled");
    command(descriptor(0,8,1,RCE_SEED_READY,5));
    command(descriptor(1,9,1,RCE_SEED_WAIT,0));
    parts(1,2);parts(0,1);unpublished(1);take(0,9);take(1,17);
    // The producer retired before this command was even presented.
    command(descriptor(2,10,1,RCE_SEED_WAIT,0));parts(2,3);take(2,21);
    // Same ID and wrapped epoch: invalidate the old 9, then publish new 116.
    command(descriptor(0,8,1,RCE_SEED_READY,100));
    command(descriptor(3,11,1,RCE_SEED_WAIT,0));
    parts(3,5);parts(0,4);unpublished(3);take(0,116);take(3,136);
    command(descriptor(4,12,1,RCE_SEED_WAIT,0,0,8,2));parts(4,2);no_result();
    broadcast(0,8,1,500,0);no_result();broadcast(0,8,2,7,1);take(4,15);
    command(descriptor(5,13,1,RCE_SEED_WAIT,0,0,7,1));parts(5,1);no_result();
    broadcast(0,7,1,9,1);take(5,13);
    command(descriptor(6,8,3,RCE_SEED_READY,2));parts(6,1);
    while(!result_valid) @(negedge clk);
    cmd=descriptor(7,14,1,RCE_SEED_WAIT,0,6,8,3);cmd_valid=1;result_ready=1;
    @(posedge clk);
    if(!cmd_ready || result.id!=6 || result.data!=6) $fatal(1,"FAIL simultaneous handoff setup");
    checked++;@(negedge clk);cmd_valid=0;result_ready=0;
    parts(7,3);take(7,18);
    $display("PASS: integer seed protocol %0d results; commit backpressure/cache/tag rejection/ID wrap/simultaneous admission",checked);
    $finish;
  end
  initial begin #100000;$fatal(1,"FAIL seed protocol watchdog");end
endmodule
