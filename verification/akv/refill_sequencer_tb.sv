module refill_sequencer_tb;
  timeunit 1ns; timeprecision 1ps;
  import ara_pkg::*;
  import rvv_pkg::*;
  import dispatcher_check_pkg::*;
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  ara_req_t request;
  ara_resp_t response;
  pe_req_t pe_request;
  pe_resp_t [NrLanes+3:0] pe_response;
  logic valid=0, ready, response_valid, idle, safe, pe_valid, ack=0;
  exception_t exception;
  vid_t older_id, refill_id;
  int checks=0, responses=0;
  bit token=0, expected_fault=0;

  ara_sequencer #(.NrLanes(NrLanes),.VLEN(VLEN),.ara_req_t(ara_req_t),
    .ara_resp_t(ara_resp_t),.pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t),.exception_t(exception_t)) dut (
    .clk_i,.rst_ni,.ara_req_i(request),.ara_req_valid_i(valid),.ara_req_ready_o(ready),
    .ara_store_accepted_o(),.ara_resp_o(response),.ara_resp_valid_o(response_valid),
    .ara_idle_o(idle),.akv_refill_overlap_safe_o(safe),.pe_req_o(pe_request),.pe_req_valid_o(pe_valid),
    .pe_vinsn_running_o(),.pe_req_ready_i('1),.pe_resp_i(pe_response),
    .alu_vinsn_done_i(1'b0),.mfpu_vinsn_done_i(1'b0),.global_hazard_table_o(),
    .pe_scalar_resp_i('0),.pe_scalar_resp_valid_i(1'b0),.pe_scalar_resp_ready_o(),
    .addrgen_ack_i(ack),.addrgen_exception_i(exception),.addrgen_exception_vstart_i('0),
    .addrgen_fof_exception_i(1'b0),.lsu_current_burst_exception_i(1'b0),
    .qbs_fflags_i('0),.qbs_fflags_valid_i(1'b0));

  task automatic check(bit condition,string why);
    checks++;
    if (!condition) $fatal(1,"REFILL_SEQ_FAIL %s checks=%0d",why,checks);
  endtask

  always @(posedge clk_i) if (rst_ni && response_valid) begin
    responses++;
    assert (response.exception.valid==expected_fault)
      else $fatal(1,"Wrong response exception");
    if (expected_fault) assert (response.exception.cause==13 && response.exception.tval==64'hdead1000)
      else $fatal(1,"Lost latched exception identity");
    assert ((dut.vinsn_running_q & ~(NrVInsn'(1)<<pe_request.id))=='0)
      else $fatal(1,"Response escaped older work");
  end

  task automatic reset;
    @(negedge clk_i);rst_ni=0;valid=0;request='0;pe_response='0;ack=0;exception='0;
    token=0;expected_fault=0;responses=0;
    repeat(3) @(negedge clk_i);
    rst_ni=1;
    repeat(2) @(negedge clk_i);
  endtask

  function automatic ara_req_t fma;
    ara_req_t r='0;
    r.op=VFMACC;r.vm=1;r.use_vd=1;r.vd=8;r.use_vs1=1;r.vs1=1;r.use_vs2=1;r.vs2=2;
    r.use_vd_op=1;r.vl=32;r.emul=LMUL_1;r.vtype.vsew=EW32;r.vtype.vlmul=LMUL_1;
    r.eew_vs1=EW32;r.eew_vs2=EW32;r.eew_vd_op=EW32;r.cvt_resize=CVT_SAME;
    return r;
  endfunction

  task automatic finish_older(bit last_lane_only);
    @(negedge clk_i);
    if (!last_lane_only) for (int l=0;l<NrLanes;l++)pe_response[l].vinsn_done[older_id]=1;
    else pe_response[NrLanes-1].vinsn_done[older_id]=1;
    @(negedge clk_i);pe_response='0;
  endtask

  task automatic scenario(int order,bit fault);
    reset();expected_fault=fault;
    request=fma();token=~token;request.token=token;valid=1;
    #1;check(ready && safe,"safe pending FMA blocked");
    @(negedge clk_i);older_id=pe_request.id;valid=0;
    #1;check(!idle && safe,"allocated FMA classification missing");
    repeat(2) @(negedge clk_i);
    request='0;request.op=VAKVFILL;request.vm=1;request.akv_v2=1;request.akv_refill=1;
    request.vl=1;request.vtype.vsew=EW16;request.vtype.vlmul=LMUL_1;request.emul=LMUL_1;
    token=~token;request.token=token;valid=1;
    @(negedge clk_i);refill_id=pe_request.id;
    #1;check(dut.refill_wait && !response_valid,"REFILL did not enter blocking WAIT");
    if (order<0)finish_older(0);
    @(negedge clk_i);ack=1;exception.valid=fault;exception.cause=13;exception.tval=64'hdead1000;
    pe_response[NrLanes+OffsetLoad].vinsn_done[refill_id]=1;
    if (order==0)for (int l=0;l<NrLanes;l++)pe_response[l].vinsn_done[older_id]=1;
    @(negedge clk_i);ack=0;exception='0;pe_response='0;
    if(order>0)begin
      #1;check(!response_valid && !ready,"terminal escaped before older lanes");
      check(!dut.vinsn_running_q[refill_id],"REFILL VID retained and risks self-deadlock");
      for(int l=0;l<NrLanes-1;l++)pe_response[l].vinsn_done[older_id]=1;
      @(negedge clk_i);pe_response='0;
      #1;check(!response_valid,"lane zero completion released response");
      finish_older(1);
    end
    for(int n=0;n<10;n++)begin
      #1;
      if(response_valid || responses)begin valid=0;break;end
      @(negedge clk_i);
    end
    repeat(3) @(negedge clk_i);
    check(responses==1 && idle,"missing/duplicate response or leaked VID");
    $display("REFILL_SEQ_SCENARIO order=%0d fault=%0d PASS",order,fault);
  endtask

  initial begin
    request='0;pe_response='0;exception='0;
    reset();
    for(int mode=0;mode<8;mode++)begin
      @(negedge clk_i);request=fma();valid=1;
      case(mode)
        1:request.vm=0;
        2:request.op=VFREDUSUM;
        3:request.op=VLE;
        4:request.cvt_resize=CVT_WIDE;
        5:request.overlap_capture=1;
        6:request.source_snapshot_replay_vs2=1;
        7:request.op=VFADD;
        default:;
      endcase
      #1;check(safe==(mode==0),"pending opcode/repair whitelist mismatch");valid=0;
    end
    for(int order=-1;order<=1;order++)for(int fault=0;fault<2;fault++)scenario(order,1'(fault));
    $display("AKV_REFILL_SEQ_PASS checks=%0d scenarios=6",checks);$finish;
  end
  initial begin #100000;$fatal(1,"REFILL_SEQ_TIMEOUT");end
endmodule
