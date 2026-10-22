// SPDX-License-Identifier: SHL-0.51
module dispatcher_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import dispatcher_check_pkg::*;
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  accelerator_req_t acc_req_i;
  accelerator_resp_t acc_resp_o;
  ara_req_t ara_req_o, last_request;
  ara_resp_t ara_resp_i;
  logic ara_req_valid_o, ara_req_ready_i=1, ara_store_accepted_i=0;
  logic ara_resp_valid_i, ara_idle_i=1, sldu_idle_i=1, sldu_drain_o;
  logic lsu_ex_flush_o, lsu_ex_flush_done_i=1, core_st_pending_o;
  logic [NrLanes-1:0][4:0] fflags_ex_i='0;
  logic [NrLanes-1:0] fflags_ex_valid_i='0, vxsat_flag_i='0;
  vxrm_t [NrLanes-1:0] alu_vxrm_o;
  logic load_complete_i=0, store_complete_i=0, store_pending_i=0;
  int cycles=0, checks=0, failures=0, issued=0, maintenance=0;
  bit last_exception;
  logic [63:0] last_cause, last_result;
  string label;
  ara_req_t seq_request;
  logic seq_valid=0, seq_ready;
  pe_req_t seq_pe_request;
  logic seq_pe_valid;
  // Loads respond only when an actual registered request is accepted.
  assign ara_resp_valid_i=ara_req_valid_o && ara_req_ready_i && ara_req_o.op==VLE;
  ara_dispatcher #(.NrLanes(NrLanes), .VLEN(VLEN), .CVA6Cfg(CVA6Cfg),
    .ara_req_t(ara_req_t), .ara_resp_t(ara_resp_t),
    .accelerator_req_t(accelerator_req_t), .accelerator_resp_t(accelerator_resp_t)) dut (.*);
  // Replay the captured dispatcher request through the real hazard allocator.
  // Processing elements accept but do not retire it, so its footprint is observable.
  ara_sequencer #(.NrLanes(NrLanes), .VLEN(VLEN), .ara_req_t(ara_req_t),
    .ara_resp_t(ara_resp_t), .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t),
    .exception_t(exception_t)) seq (
    .clk_i, .rst_ni, .ara_req_i(seq_request), .ara_req_valid_i(seq_valid),
    .ara_req_ready_o(seq_ready), .ara_store_accepted_o(), .ara_resp_o(),
    .ara_resp_valid_o(), .ara_idle_o(), .pe_req_o(seq_pe_request),
    .pe_req_valid_o(seq_pe_valid), .pe_vinsn_running_o(),
    .pe_req_ready_i('1), .pe_resp_i('0), .alu_vinsn_done_i(1'b0),
    .mfpu_vinsn_done_i(1'b0), .global_hazard_table_o(), .pe_scalar_resp_i('0),
    .pe_scalar_resp_valid_i(1'b0), .pe_scalar_resp_ready_o(), .addrgen_ack_i(1'b0),
    .addrgen_exception_i('0), .addrgen_exception_vstart_i('0),
    .addrgen_fof_exception_i(1'b0), .lsu_current_burst_exception_i(1'b0),
    .qbs_fflags_i('0), .qbs_fflags_valid_i(1'b0));

  function automatic logic [31:0] vector_insn(
      int f6, bit vm, int vs2, int vs1, int f3, int vd);
    return {6'(f6), vm, 5'(vs2), 5'(vs1), 3'(f3), 5'(vd), 7'h57};
  endfunction

  task automatic check(bit condition, string detail);
    checks++;
    if (!condition) begin
      failures++;
      $display("FAIL %s %s cycle=%0d", label, detail, cycles);
    end
  endtask

  always @(posedge clk_i) begin
    cycles++;
    if (rst_ni && ara_req_valid_o && ara_req_ready_i) begin
      if (ara_req_o.scale_vl) maintenance++;
      else begin issued++; last_request=ara_req_o; end
      if ($test$plusargs("FOCUSED"))
        $display("TRACE cycle=%0d op=%0d emul=%0d sew=%0d vs1=%0d eew1=%0d vs2=%0d eew2=%0d vl=%0d start=%0d maintenance=%0b",
          cycles, ara_req_o.op, ara_req_o.emul, ara_req_o.vtype.vsew,
          ara_req_o.vs1, ara_req_o.eew_vs1, ara_req_o.vs2, ara_req_o.eew_vs2,
          ara_req_o.vl, ara_req_o.vstart, ara_req_o.scale_vl);
    end
  end

  task automatic reset_dut;
    @(negedge clk_i);
    rst_ni=0; acc_req_i='0; ara_resp_i='0; ara_req_ready_i=1;
    seq_valid=0; seq_request='0;
    repeat (3) @(negedge clk_i);
    rst_ni=1;
    repeat (2) @(negedge clk_i);
    issued=0; maintenance=0; last_request='0;
  endtask

  task automatic check_source_group;
    int nregs, wait_cycles;
    seq_request=last_request;
    seq_request.token=0;
    seq_valid=1;
    wait_cycles=0;
    #1;
    while (!seq_ready) begin
      @(negedge clk_i); #1;
      wait_cycles++;
      if (wait_cycles>20) $fatal(1,"sequencer acceptance timeout %s",label);
    end
    @(negedge clk_i);
    check(seq_pe_valid,"sequencer did not forward PE request");
    check(seq_pe_request.emul==last_request.emul &&
          seq_pe_request.vtype==last_request.vtype &&
          seq_pe_request.vl==last_request.vl &&
          seq_pe_request.eew_vs1==last_request.eew_vs1 &&
          seq_pe_request.eew_vs2==last_request.eew_vs2,
          "sequencer changed reduction geometry");
    seq_valid=0;
    nregs=last_request.vtype.vlmul inside {LMUL_2,LMUL_4,LMUL_8}
        ? 1<<int'(last_request.vtype.vlmul) : 1;
    for (int r=0;r<32;r++) begin
      check((|seq.read_mask_q[r]) ==
        (r==last_request.vs1 || (r>=last_request.vs2 && r<last_request.vs2+nregs) ||
         (!last_request.vm && r==0)), "sequencer source footprint differs");
      check(seq.write_list_q[r].valid == (r==last_request.vd),
            "sequencer destination is not one register");
    end
    $display("RESULT source_group op=%0d emul=%0d pe_emul=%0d data_lmul=%0d source_registers=%0d seed_registers=1 destination_registers=1",
      last_request.op,last_request.emul,seq_pe_request.emul,last_request.vtype.vlmul,nregs);
    @(negedge clk_i);
  endtask

  task automatic send(logic [31:0] insn, logic [63:0] rs1=0, int backpressure=0);
    int wait_cycles;
    acc_req_i='0;
    acc_req_i.insn=insn; acc_req_i.rs1=rs1;
    acc_req_i.req_valid=1; acc_req_i.resp_ready=1;
    acc_req_i.frm=fpnew_pkg::RNE;
    for (int i=0; i<backpressure; i++) begin
      ara_req_ready_i=0;
      #1;
      check(!acc_resp_o.req_ready, "accepted while backend blocked");
      @(negedge clk_i);
    end
    ara_req_ready_i=1;
    wait_cycles=0;
    #1;
    while (!acc_resp_o.req_ready) begin
      @(negedge clk_i); #1;
      wait_cycles++;
      if (wait_cycles>200) $fatal(1,"dispatcher timeout %s insn=%h state=%0d",label,insn,dut.state_q);
    end
    last_exception=acc_resp_o.exception.valid;
    last_cause=acc_resp_o.exception.cause;
    last_result=acc_resp_o.result;
    if ($test$plusargs("FOCUSED"))
      $display("DECODE %s cycle=%0d insn=%h sew=%0d lmul=%0d vl=%0d start=%0d eew8=%0d op=%0d emul=%0d lmul1=%0d lmul2=%0d illegal=%0b cause=%0d",
        label, cycles, insn, dut.csr_vtype_q.vsew, dut.csr_vtype_q.vlmul,
        dut.csr_vl_q, dut.csr_vstart_q, dut.eew_q[8], dut.ara_req.op,
        dut.ara_req.emul, dut.lmul_vs1, dut.lmul_vs2, last_exception,last_cause);
    @(negedge clk_i);
    acc_req_i.req_valid=0;
    repeat (3) @(negedge clk_i);
  endtask

  task automatic config_vl(int sew, int lmul, int vl);
    send({1'b0, 11'((sew<<3)|lmul), 5'd1, 3'b111, 5'd5, 7'h57}, 64'(vl));
    check(!last_exception, "configuration rejected");
  endtask

  task automatic set_start(int value);
    send(32'h00809073,64'(value)); // csrw vstart,x1
    check(!last_exception, "CSR write rejected");
  endtask

  task automatic initialize_group(int regno, int sew, int lmul);
    int before_issue;
    config_vl(sew,lmul,1024);
    before_issue=issued;
    send({3'b000,1'b0,2'b00,1'b1,5'b00000,5'd1,
          3'(sew==0 ? 0 : sew+4),5'(regno),7'h07});
    check(!last_exception, "preparation load rejected");
    check(issued==before_issue+1,"preparation load not accepted exactly once");
    for (int r=0;r<(1<<lmul);r++)
      check(dut.eew_valid_q[regno+r] && dut.eew_q[regno+r]==sew,
            "preparation layout metadata differs");
  endtask

  task automatic reduction(int sew, int lmul, int vl, bit ordered,
                            bit vm=0, int start=0, int vs2=8, int vd=24, int seed=16);
    int before_issue;
    bit illegal_expected;
    label=$sformatf("reduce_e%0d_lmul%0d_vl%0d_order%0b_vm%0b_start%0d_vs2%0d_vd%0d_seed%0d",
                    8<<sew,lmul,vl,ordered,vm,start,vs2,vd,seed);
    reset_dut();
    config_vl(sew,lmul,vl);
    set_start(start);
    before_issue=issued;
    send(vector_insn(ordered ? 'h33 : 'h31,vm,vs2,seed,1,vd),0,2);
    illegal_expected=(sew==3 || start!=0 || (lmul<=3 && (vs2 % (1<<lmul))!=0));
    check(last_exception==illegal_expected, "illegal response differs");
    if (illegal_expected) begin
      check(last_cause==2, "wrong illegal cause");
      check(issued==before_issue, "illegal reduction issued");
    end else begin
      check(issued-before_issue==(vl!=0), "legal reduction issue count");
      if (vl!=0 && issued>before_issue) begin
        check(last_request.op==(ordered ? VFWREDOSUM : VFWREDUSUM), "wrong reduction op");
        check(last_request.vtype.vsew==sew+1 && last_request.eew_vs1==sew+1 &&
              last_request.eew_vs2==sew, "wrong reduction widths");
        check(last_request.vtype.vlmul==lmul && last_request.vl==vl, "lost source LMUL/VL");
        check(last_request.conversion_vs1==OpQueueReductionZExt &&
              last_request.conversion_vs2==OpQueueConversionWideFP2, "wrong conversion contract");
        if (lmul==3) check(last_request.emul==LMUL_RSVD,"m8 widened EMUL representation changed");
        check_source_group();
      end
    end
    $display("RESULT %s exception=%0b cause=%0d issued=%0d",label,last_exception,last_cause,issued-before_issue);
  endtask

  task automatic whole(int sew, int stored, int group, int start, int vl=1, bit self_move=0);
    int before_issue, before_maintenance, evl;
    label=$sformatf("whole_e%0d_stored%0d_n%0d_start%0d_vl%0d_self%0b",8<<sew,8<<stored,1<<group,start,vl,self_move);
    reset_dut();
    initialize_group(8,stored,group);
    initialize_group(24,stored,group);
    config_vl(sew,0,vl);
    set_start(start);
    before_issue=issued; before_maintenance=maintenance;
    evl=((VLEN/8)<<group)>>sew;
    send(vector_insn('h27,1,8,(1<<group)-1,3,self_move ? 8 : 24),0,2);
    check(!last_exception, "whole move rejected");
    check(issued-before_issue==(start<evl), "whole move issue count / EVL no-op");
    if (start<evl && issued>before_issue) begin
      check(last_request.op==VMERGE && last_request.use_vs1 && !last_request.use_vs2,
            "whole move operand selection");
      check((int'(last_request.vstart)<<int'(last_request.vtype.vsew))==(start<<sew),
            "restart byte offset differs");
      check((int'(last_request.vl)<<int'(last_request.vtype.vsew))==((VLEN/8)<<group),
            "whole byte length differs");
      check(last_request.emul==group && last_request.eew_vs1==last_request.vtype.vsew,
            "group or source layout differs");
      if (start==0) begin
        check(last_request.vtype.vsew==stored,"zero-start stored-layout fast path changed");
        check(maintenance==before_maintenance,"zero-start fast path added reshuffles");
      end
    end else if (start>=evl) check(maintenance==before_maintenance,"no-op launched reshuffle");
    $display("RESULT %s issued=%0d maintenance=%0d request_sew=%0d request_start=%0d byte_start=%0d expected=%0d",
      label,issued-before_issue,maintenance-before_maintenance,last_request.vtype.vsew,
      last_request.vstart,int'(last_request.vstart)<<int'(last_request.vtype.vsew),start<<sew);
    send(32'h008022f3); // csrr x5,vstart
    check(last_result==0,"completion did not clear vstart");
  endtask

  task automatic negative_controls;
    int before_issue;
    label="negative_controls";
    reset_dut();
    config_vl(2,3,1);
    before_issue=issued;
    send(vector_insn('h30,1,8,16,1,24)); // vfwadd.vv, not a scalar reduction
    check(last_exception && last_cause==2 && issued==before_issue,
          "m8 widening vector arithmetic must remain illegal");
    config_vl(2,0,1);
    for (int bad=0;bad<3;bad++) begin
      before_issue=issued;
      case (bad)
        0: send(vector_insn('h27,1,9,1,3,24)); // vmv2r unaligned source
        1: send(vector_insn('h27,1,8,1,3,25)); // vmv2r unaligned destination
        2: send(vector_insn('h27,1,8,2,3,24)); // reserved register count
      endcase
      check(last_exception && last_cause==2 && issued==before_issue,
            "reserved whole-move encoding accepted");
    end
    label="integer_widen_m8_control";
    reset_dut();
    config_vl(2,3,7);
    send(vector_insn('h30,1,8,17,0,25)); // vwredsumu.vs
    check(!last_exception && issued==1,"integer m8 widening reduction regressed");
    if (!last_exception && issued==1) check_source_group();
  endtask

  initial begin
`ifdef TRACE_FSDB
    $fsdbDumpfile("dispatcher.fsdb");
    $fsdbDumpvars(1, dispatcher_tb);
    $fsdbDumpvars(1, dispatcher_tb.dut);
`endif
    if ($test$plusargs("FOCUSED")) begin
      reduction(2,3,0,1); // Original board opcode 0xcc881c57 at VL0.
      reduction(2,3,1,1); // Handoff VL1 counterpoint.
      reduction(2,2,1,1); // m4 legality control.
      whole(1,0,0,1);    // Original byte-loaded SEW16 restart.
      whole(0,0,0,1);    // Same-width control.
      whole(0,3,0,1);    // Reverse-EEW nonintegral offset.
      whole(1,0,0,64);   // EVL boundary must not issue.
    end else begin
      for (int sew=1;sew<=2;sew++)
        for (int lmul=0;lmul<8;lmul++)
          if (lmul!=4 && !(sew==2 && lmul inside {5,6}) && !(sew==1 && lmul==5))
            for (int ordered=0;ordered<2;ordered++) begin
              reduction(sew,lmul,0,ordered);
              reduction(sew,lmul,1,ordered,1,0,8,25,17);
              reduction(sew,lmul,7,ordered);
            end
      reduction(2,3,1,1,0,0,9);
      reduction(2,3,1,0,1,1);
      reduction(3,3,1,1);
      reduction(2,3,0,0,1,1);
      negative_controls();
      for (int sew=0;sew<4;sew++)
        for (int stored=0;stored<4;stored++)
          for (int group=0;group<4;group++) begin
            whole(sew,stored,group,0,0);
            whole(sew,stored,group,1);
            whole(sew,stored,group,(((VLEN/8)<<group)>>sew)-1);
            whole(sew,stored,group,((VLEN/8)<<group)>>sew);
            whole(sew,stored,group,(((VLEN/8)<<group)>>sew)+1);
            whole(sew,stored,group,1,0,1);
          end
    end
`ifdef TRACE_FSDB
    $fsdbDumpoff;
`endif
    if (failures) $fatal(1,"DISPATCHER_FAIL checks=%0d failures=%0d cycles=%0d",checks,failures,cycles);
    $display("DISPATCHER_PASS checks=%0d cycles=%0d",checks,cycles);
    $finish;
  end
endmodule
