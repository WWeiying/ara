`timescale 1ns/1ps
module sequencer_fault_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  typedef struct packed {logic valid; logic [63:0] cause, tval;} exception_t;
  `include "ara/ara_typedef.svh"
  `include "sequencer_types.svh"
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  ara_req_t ara_req_i;
  ara_resp_t ara_resp_o;
  logic ara_req_valid_i, ara_req_ready_o, ara_resp_valid_o, ara_idle_o;
  pe_req_t pe_req_o;
  logic pe_req_valid_o;
  logic [7:0] pe_vinsn_running_o, pe_req_ready_i;
  pe_resp_t [7:0] pe_resp_i;
  logic addrgen_ack_i, addrgen_fof_exception_i, lsu_current_burst_exception_i;
  exception_t addrgen_exception_i;
  vlen_t addrgen_exception_vstart_i;
  ara_sequencer #(.NrLanes(4), .VLEN(1024), .ara_req_t(ara_req_t),
    .ara_resp_t(ara_resp_t), .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t),
    .exception_t(exception_t)) dut (
    .clk_i, .rst_ni, .ara_req_i, .ara_req_valid_i, .ara_req_ready_o,
    .ara_store_accepted_o(), .ara_resp_o, .ara_resp_valid_o, .ara_idle_o,
    .pe_req_o, .pe_req_valid_o, .pe_vinsn_running_o, .pe_req_ready_i, .pe_resp_i,
    .alu_vinsn_done_i(1'b0), .mfpu_vinsn_done_i(1'b0), .global_hazard_table_o(),
    .pe_scalar_resp_i('0), .pe_scalar_resp_valid_i(1'b0), .pe_scalar_resp_ready_o(),
    .addrgen_ack_i, .addrgen_exception_i, .addrgen_exception_vstart_i,
    .addrgen_fof_exception_i, .lsu_current_burst_exception_i,
    .qbs_fflags_i('0), .qbs_fflags_valid_i(1'b0));

  int variant, cycle_no, fd, slot;
  int pe_cycle[2], ack_cycle[2], done_cycle[2], response_cycle[2], response_count[2];
  vid_t owner[2];
  bit token=1, response_sample;

  function automatic bit faulting(int s);
    return s==1 && !(variant inside {0,6});
  endfunction
  function automatic bit fof(int s);
    return s==1 && variant!=0 && variant!=2;
  endfunction
  function automatic int ack_due(int s);
    if (pe_cycle[s]<0) return -1;
    if (s==0) return pe_cycle[s]+2;
    return pe_cycle[s]+(variant==4 ? 10 : 4);
  endfunction
  function automatic int done_due(int s);
    if (pe_cycle[s]<0) return -1;
    if (s==0) return pe_cycle[1]<0 ? -1 : pe_cycle[1]+7;
    if (variant==4) return pe_cycle[s]+2;
    if (variant==5) return pe_cycle[s]+4;
    return pe_cycle[s]+16;
  endfunction

  task automatic tick;
    addrgen_ack_i=0; addrgen_exception_i='0; addrgen_fof_exception_i=0;
    addrgen_exception_vstart_i=0; lsu_current_burst_exception_i=0;
    pe_resp_i='0; pe_req_ready_i='1;
    for (int s=0;s<2;s++) if (pe_cycle[s]>=0) begin
      if (cycle_no==ack_due(s)) begin
        addrgen_ack_i=1;
        addrgen_exception_i.valid=faulting(s);
        if (faulting(s)) begin
          addrgen_exception_i.cause=riscv::LOAD_PAGE_FAULT;
          addrgen_exception_i.tval=64'h81234006;
          addrgen_exception_vstart_i=3;
          addrgen_fof_exception_i=fof(s);
        end
      end
      if (cycle_no==done_due(s)) begin
        pe_resp_i[4+OffsetLoad].vinsn_done[owner[s]]=1;
        lsu_current_burst_exception_i=faulting(s);
      end
      if (faulting(s) && cycle_no>=ack_due(s) && cycle_no<done_due(s))
        pe_req_ready_i[4+OffsetLoad]=0;
    end
    @(posedge clk_i);
    response_sample=ara_resp_valid_o;
    if (rst_ni) begin
      if (pe_req_valid_o && pe_req_o.op==VLE) begin
        int s;
        s=pe_req_o.vd==8 ? 0 : 1;
        if (pe_cycle[s]<0) begin
          pe_cycle[s]=cycle_no; owner[s]=pe_req_o.id;
          if (!pe_req_ready_i[4+OffsetLoad]) $fatal(1,"FIRST_BROADCAST_NOT_ACCEPTED");
        end else if (owner[s]!=pe_req_o.id) $fatal(1,"REISSUED_DIFFERENT_VID");
      end
      for (int s=0;s<2;s++) if (pe_cycle[s]>=0) begin
        if (addrgen_ack_i && cycle_no==ack_due(s)) ack_cycle[s]=cycle_no;
        if (pe_resp_i[4+OffsetLoad].vinsn_done[owner[s]]) begin
          if (!pe_vinsn_running_o[owner[s]]) $fatal(1,"DONE_FOR_UNALLOCATED_VID");
          done_cycle[s]=cycle_no;
        end
      end
      if (ara_resp_valid_o) begin
        response_cycle[slot]=cycle_no; response_count[slot]++;
        if (!ara_req_ready_o || response_count[slot]>1) $fatal(1,"BAD_RESPONSE_HANDSHAKE");
        if (ara_resp_o.exception.valid!==faulting(slot) ||
            ara_resp_o.fof_exception!==(faulting(slot)&&fof(slot))) $fatal(1,"BAD_RESPONSE_FLAGS");
        if (faulting(slot) && (ara_resp_o.exception.cause!==riscv::LOAD_PAGE_FAULT ||
            ara_resp_o.exception.tval!==64'h81234006 || ara_resp_o.exception_vstart!==11'd3))
          $fatal(1,"FAULT_METADATA_NOT_RETAINED");
      end
      $fdisplay(fd,"%0d,%0d,%b,%b,%b,%0d,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%0d",
        cycle_no,slot,ara_req_valid_i,ara_req_ready_o,pe_req_valid_o,pe_req_o.id,
        pe_req_ready_i[4+OffsetLoad],addrgen_ack_i,addrgen_exception_i.valid,
        addrgen_fof_exception_i,pe_resp_i[4+OffsetLoad].vinsn_done,
        ara_resp_valid_o,ara_resp_o.exception.valid,ara_resp_o.fof_exception,
        ara_idle_o,pe_vinsn_running_o,ara_resp_o.exception_vstart);
    end
    #1; @(negedge clk_i); cycle_no++;
    if (response_sample) ara_req_valid_i=0;
    if (cycle_no>160) $fatal(1,"BOUNDED_WATCHDOG");
  endtask

  task automatic submit(int s);
    slot=s; token=~token; ara_req_i='0; ara_req_i.token=token;
    ara_req_i.op=VLE; ara_req_i.vm=1; ara_req_i.vd=s==0 ? 8 : 16;
    ara_req_i.use_vd=1; ara_req_i.vl=8; ara_req_i.vtype.vsew=EW16;
    ara_req_i.vtype.vlmul=LMUL_1; ara_req_i.emul=LMUL_1;
    ara_req_i.fault_only_first=fof(s); ara_req_i.scalar_op=64'h81234000;
    ara_req_valid_i=1;
    while (pe_cycle[s]<0) tick();
  endtask

  initial begin
    variant=0;
    if ($value$plusargs("CASE=%d",variant)) begin end
    fd=$fopen("cycles.csv","w");
    $fdisplay(fd,"cycle,slot,ara_valid,ara_ready,pe_valid,pe_id,ldu_ready,ack,exception,fof,ldu_done,resp_valid,resp_exception,resp_fof,idle,running,resp_vstart");
    $dumpfile("window.vcd"); $dumpvars(0,sequencer_fault_tb);
    ara_req_i='0; ara_req_valid_i=0;
    for (int s=0;s<2;s++) begin
      pe_cycle[s]=-1; ack_cycle[s]=-1; done_cycle[s]=-1; response_cycle[s]=-1;
    end
    repeat(3) tick(); rst_ni=1; tick();
    if (variant==3) begin
      submit(0);
      while (!response_count[0]) tick();
    end
    submit(1);
    repeat(40) tick();
    if (response_count[1]!=1 || ack_cycle[1]<0 || done_cycle[1]<0)
      $fatal(1,"MISSING_TERMINAL_EVENT");
    if (variant==3 && (owner[0]==owner[1] || done_cycle[0]<ack_cycle[1] ||
                      done_cycle[0]>=done_cycle[1])) $fatal(1,"OTHER_VID_CONTROL_NOT_DISTINCT");
    if (variant inside {0,6} && response_cycle[1]!=ack_cycle[1])
      $fatal(1,"NORMAL_RESPONSE_DELAYED");
    if (variant inside {4,5} && response_cycle[1]!=ack_cycle[1])
      $fatal(1,"EARLY_OR_SAME_DONE_LOST");
    $display("OBSERVATION case=%0d owner=%0d other_owner=%0d pe=%0d ack=%0d done=%0d other_done=%0d response=%0d fault=%0d fof=%0d early_fault_response=%0d idle=%0d",
      variant,owner[1],pe_cycle[0]<0 ? -1 : int'(owner[0]),pe_cycle[1],ack_cycle[1],done_cycle[1],done_cycle[0],
      response_cycle[1],faulting(1),fof(1),faulting(1)&&response_cycle[1]<done_cycle[1],ara_idle_o);
    $display("PROBE_COMPLETED case=%0d",variant);
    $fclose(fd); $finish;
  end
endmodule
