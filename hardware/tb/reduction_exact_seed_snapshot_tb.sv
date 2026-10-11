// SPDX-License-Identifier: SHL-0.51
// Real SLDU acceptance queues; hold the transport head while seeds arrive,
// then overwrite producer cache lifetimes and check consumer-owned values.
module reduction_exact_seed_snapshot_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import ara_rce_pkg::*;
  localparam int VLEN=1024;
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef logic [9:0] vaddr_t;
  `include "ara/ara_typedef.svh"
  logic clk=0, rst_n=0, req_valid=0, req_ready;
  always #5 clk=~clk;
  pe_req_t req;
  pe_resp_t resp;
  logic [NrVInsn-1:0] running='0;
  rce_seed_write_t [1:0] writes;
  logic [1:0] write_valid='0;
  int checks=0;
  sldu #(.NrLanes(4),.VLEN(VLEN),.vaddr_t(vaddr_t),.pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t)) dut (
    .clk_i(clk),.rst_ni(rst_n),.pe_req_i(req),.pe_req_valid_i(req_valid),
    .pe_req_ready_o(req_ready),.pe_resp_o(resp),.pe_vinsn_running_i(running),
    .sldu_operand_i('0),.sldu_operand_valid_i('0),.sldu_operand_ready_o(),
    .sldu_result_req_o(),.sldu_result_id_o(),.sldu_result_addr_o(),
    .sldu_result_wdata_o(),.sldu_result_be_o(),.sldu_result_gnt_i('0),.sldu_result_final_gnt_i('0),
    .sldu_mux_sel_o(),.sldu_red_valid_o(),.mask_i('0),.mask_valid_i('0),.mask_ready_o(),
    .exact_external_seed_i(writes),.exact_external_seed_valid_i(write_valid),
    .rce_exact_cmd_o(),.rce_exact_cmd_valid_o(),.rce_exact_cmd_ready_i(1'b0),
    .rce_exact_operand_o(),.rce_exact_operand_valid_o(),.rce_exact_operand_ready_i('0),
    .rce_exact_seed_ready_o(),.rce_exact_seed_data_o(),.rce_exact_local_complete_i(1'b0),
    .rce_exact_lane_consumed_i('0),.rce_exact_result_i('0),.rce_exact_result_valid_i(1'b0),
    .rce_exact_result_ready_o(),.rce_exact_events_i('0),.rce_completion_o(),
    .rce_completion_valid_o(),.rce_completion_ready_i(1'b0)
  );
  function automatic rce_seed_write_t seed_write(vid_t id, int epoch, logic [31:0] value,
                                                 logic [7:0] bytes, logic [4:0] regno=4);
    return '{seed:'{producer:id,vd:regno,version:vreg_version_t'(epoch),data:{32'b0,value}},be:bytes};
  endfunction
  task automatic accept;
    int ticks=0;
    req_valid=1;running[req.id]=1;
    do begin @(posedge clk);if(++ticks>20)$fatal(1,"FAIL: descriptor accept blocked");end while(!req_ready);
    @(negedge clk);req_valid=0;write_valid='0;
  endtask
  task automatic hold_head;
    @(negedge clk);rst_n=0;req_valid=0;write_valid='0;running='0;req='0;writes='0;
    repeat(3)@(negedge clk);rst_n=1;
    req='0;req.id=vid_t'(7);req.op=VSLIDEDOWN;req.vfu=VFU_SlideUnit;
    req.vm=1;req.vl=4;req.vtype.vsew=EW64;req.eew_vs2=EW64;
    req.vd=28;req.use_vd=1;req.vs2=24;req.use_vs2=1;
    accept();
  endtask
  task automatic consumer(vid_t id,vid_t producer,int epoch,vew_e width);
    req='0;req.id=id;req.op=VFREDUSUM;req.vfu=VFU_MFpu;req.vm=1;req.vl=4;
    req.vtype.vsew=width;req.vtype.vlmul=LMUL_1;
    req.vd=5'(16+id);req.use_vd=1;req.vs1=4;req.use_vs1=1;req.vs2=8;req.use_vs2=1;
    req.late_seed=1;req.seed_producer_id=producer;req.seed_version=vreg_version_t'(epoch);
    accept();
  endtask
  task automatic publish(rce_seed_write_t first, rce_seed_write_t second='0,logic [1:0] ports=2'b01);
    @(negedge clk);writes[0]=first;writes[1]=second;write_valid=ports;
    @(posedge clk);@(negedge clk);write_valid='0;
  endtask
  task automatic expect_seed(int slot,logic valid,logic [31:0] value);
    if(dut.exact_seed_snapshot_valid_q[slot]!==valid ||
       (valid && dut.exact_seed_snapshot_data_q[slot]!==value))
      $fatal(1,"FAIL: snapshot slot=%0d valid=%b data=%h expected=%b/%h",
        slot,dut.exact_seed_snapshot_valid_q[slot],dut.exact_seed_snapshot_data_q[slot],valid,value);
    checks++;
  endtask
  initial begin
    int epoch,random_seed=32'h53454544;
    logic [31:0] a,b,c;
    if(!RceExactExternalSeedEnable || RceSlduQueueDepth<4)
      $fatal(1,"FAIL: requires external exact seed and four descriptors");
    void'($urandom(random_seed));
    for(int trial=0;trial<100;trial++) begin
      epoch=10*trial+1;a=$urandom;b=$urandom;c=$urandom;
      // A cache replacement in the consumer acceptance cycle must retain A.
      hold_head();publish(seed_write(5,epoch,a,8'h0f));
      writes[0]=seed_write(5,epoch+1,b,8'h0f);write_valid=1;
      consumer(0,5,epoch,EW32);expect_seed(1,1,a);
      consumer(1,5,epoch+1,EW32);expect_seed(2,1,b);
      publish(seed_write(5,epoch+2,c,8'h0f));expect_seed(1,1,a);expect_seed(2,1,b);
      consumer(2,5,epoch+2,EW32);expect_seed(3,1,c);
      expect_seed(1,1,a);expect_seed(2,1,b);
      if(req_ready || dut.vinsn_queue_q.commit_cnt!=4)
        $fatal(1,"FAIL: full descriptor queue did not apply backpressure");
      checks++;
      // Both producer ports publish to distinct queued consumers together.
      hold_head();consumer(0,5,epoch,EW16);consumer(1,6,epoch,EW32);
      expect_seed(1,0,0);expect_seed(2,0,0);
      publish(seed_write(5,epoch,a,8'h03),seed_write(6,epoch,b,8'h0f),2'b11);
      expect_seed(1,1,a);expect_seed(2,1,b);
      publish(seed_write(5,epoch+1,c,8'h0f));expect_seed(1,1,a);expect_seed(2,1,b);
      // Wrong register/version and insufficient bytes cannot bind.
      hold_head();consumer(0,5,epoch,EW32);
      publish(seed_write(5,epoch+1,a,8'h0f));expect_seed(1,0,0);
      publish(seed_write(5,epoch,a,8'h0f,5));expect_seed(1,0,0);
      publish(seed_write(5,epoch,a,8'h03));expect_seed(1,0,0);
      publish(seed_write(5,epoch,b,8'h0f));expect_seed(1,1,b);
      // First byte alone is insufficient even for an FP16 seed.
      hold_head();consumer(0,5,epoch,EW16);
      publish(seed_write(5,epoch,a,8'h01));expect_seed(1,0,0);
      publish(seed_write(5,epoch,b,8'h03));expect_seed(1,1,b);
    end
    $display("PASS: exact seed snapshots trials=100 checks=%0d; queued ID reuse, concurrent ports, byte/register/version rejection",checks);
    $finish;
  end
  initial begin #10000000;$fatal(1,"FAIL: snapshot watchdog");end
endmodule
