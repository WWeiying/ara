// SPDX-License-Identifier: SHL-0.51
// Check architectural publication timing, cached and simultaneous binding,
// stale register/version rejection, and ID reuse with a wrapped version.
module reduction_ordinary_seed_tb;
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
  logic [NrVInsn-1:0] live=0;
  rce_seed_write_t [1:0] writes;
  logic [1:0] write_valid=0;
  rce_seed_write_t [1:0] extra_writes;
  logic [1:0] extra_valid=0;
  logic use_external;
  initial use_external=$test$plusargs("EXTERNAL_SEED");
  reduction_completion_engine #(.EnableExact(0)) dut (
    .clk_i(clk),.rst_ni(rst_n),.cmd_i(cmd),.cmd_valid_i(cmd_valid),.cmd_ready_o(cmd_ready),
    .partial_i(partial),.partial_valid_i(partial_valid),.partial_ready_o(partial_ready),
    .seed_lifetime_i(live), .external_seed_i(use_external ? writes : extra_writes),
    .external_seed_valid_i(use_external ? write_valid : extra_valid),
    .ordinary_seed_i(use_external ? extra_writes : writes),
    .ordinary_seed_valid_i(use_external ? extra_valid : write_valid),
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
  task automatic write_pair(int epoch,logic [7:0] bytes,elen_t a,elen_t b);
    @(negedge clk);
    writes[0]='{seed:'{producer:vid_t'(6),vd:5'd8,version:vreg_version_t'(epoch),data:a},be:bytes};
    writes[1]='{seed:'{producer:vid_t'(7),vd:5'd9,version:vreg_version_t'(epoch),data:b},be:bytes};
    extra_writes[0]='{seed:'{producer:vid_t'(4),vd:5'd10,version:vreg_version_t'(1),data:64'd1000},be:8'hff};
    extra_writes[1]='{seed:'{producer:vid_t'(5),vd:5'd11,version:vreg_version_t'(1),data:64'd2000},be:8'hff};
    write_valid='1;extra_valid=RceExternalSeedEnable ? '1 : '0;
    @(posedge clk);@(negedge clk);write_valid='0;extra_valid='0;
  endtask
  initial begin
    cmd='0;partial='0;seed='0;writes='0;extra_writes='0;
    repeat(3) @(negedge clk);rst_n=1;
    if(!RceOrdinarySeedEnable) $fatal(1,"FAIL ordinary seed feature disabled");
    if(use_external && !RceExternalSeedEnable) $fatal(1,"FAIL external feature disabled");
    live[6]=1;live[7]=1;
    if(RceExternalSeedEnable) begin live[4]=1;live[5]=1;end
    command(descriptor(0,16,1,RCE_SEED_WAIT,0,6,8,1));
    command(descriptor(1,17,1,RCE_SEED_WAIT,0,7,9,1));
    parts(0,1);parts(1,1);
    write_pair(1,8'h0f,10,20);no_result(); // Too few written bytes for EW64.
    write_pair(2,8'hff,500,600);no_result(); // Wrong versions must not bind.
    write_pair(1,8'hff,10,20);take(0,14);take(1,24); // Both ports captured.
    command(descriptor(2,18,1,RCE_SEED_WAIT,0,6,8,1));parts(2,2);take(2,18);
    // Reallocate the ordinary producer ID, even with a wrapped version.
    @(negedge clk);live[6]=0;
    @(negedge clk);live[6]=1;
    @(negedge clk);
    command(descriptor(3,19,1,RCE_SEED_WAIT,0,6,8,1));parts(3,1);no_result();
    write_pair(1,8'hff,30,40);take(3,34);
    if(RceExternalSeedEnable) begin
      command(descriptor(0,20,1,RCE_SEED_WAIT,0,4,10,1));parts(0,1);take(0,1004);
      command(descriptor(1,21,1,RCE_SEED_WAIT,0,5,11,1));parts(1,1);take(1,2004);
    end
    $display("PASS: ordinary seed protocol %0d results; dual capture/byte coverage/version/lifetime/cache",checked);
    $finish;
  end
  initial begin #100000;$fatal(1,"FAIL seed protocol watchdog");end
endmodule
