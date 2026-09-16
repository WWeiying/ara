// SPDX-License-Identifier: SHL-0.51
package vstu_check_pkg;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  typedef struct packed {
    logic [127:0] data;
    logic [15:0] strb;
    logic last, user;
  } axi_w_t;
  typedef struct packed {
    logic [4:0] id;
    axi_pkg::resp_t resp;
    logic user;
  } axi_b_t;
endpackage

module vstu_equivalence_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import vstu_check_pkg::*;
  localparam int NrLanes=4, Depth=VstuInsnQueueDepth, PW=cf_math_pkg::idx_width(Depth);
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  axi_w_t axi_w_o, ref_w;
  axi_b_t axi_b_i;
  pe_req_t pe_req_i;
  pe_resp_t pe_resp_o, ref_resp;
  logic axi_w_valid_o, ref_w_valid, axi_w_ready_i;
  logic axi_b_valid_i, axi_b_ready_o, ref_b_ready;
  logic store_pending_o, ref_pending, store_complete_o, ref_complete;
  logic pe_req_valid_i, pe_req_ready_o, ref_req_ready;
  logic [NrVInsn-1:0] pe_vinsn_running_i;
  logic stu_current_burst_exception_o, ref_exception;
  addrgen_axi_req_t axi_addrgen_req_i;
  logic axi_addrgen_req_valid_i, axi_addrgen_req_ready_o, ref_addr_ready;
  logic addrgen_illegal_store_i;
  elen_t [NrLanes-1:0] stu_operand_i;
  logic [NrLanes-1:0] stu_operand_valid_i, stu_operand_ready_o, ref_operand_ready;
  logic lsu_ex_flush_i;
  logic [NrLanes-1:0][7:0] mask_i;
  logic [NrLanes-1:0] mask_valid_i;
  logic mask_ready_o, ref_mask_ready, idle_o, ref_idle;
  struct packed {
    pe_req_t [Depth-1:0] vinsn;
    logic [PW-1:0] accept_pnt, issue_pnt, commit_pnt;
    logic [PW:0] issue_cnt, commit_cnt;
  } forced_queue;
  int checks=0, handoffs=0, same_cycle_accepts=0, seed=32'h56535455;

  vstu #(.NrLanes(NrLanes), .VLEN(1024), .vaddr_t(logic[6:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t), .AxiDataWidth(128), .AxiAddrWidth(64),
    .axi_w_t(axi_w_t), .axi_b_t(axi_b_t)) dut (.*);
  vstu_reference #(.NrLanes(NrLanes), .VLEN(1024), .vaddr_t(logic[6:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t), .AxiDataWidth(128), .AxiAddrWidth(64),
    .axi_w_t(axi_w_t), .axi_b_t(axi_b_t)) reference (
    .axi_w_o(ref_w), .axi_w_valid_o(ref_w_valid), .axi_b_ready_o(ref_b_ready),
    .store_pending_o(ref_pending), .store_complete_o(ref_complete),
    .pe_req_ready_o(ref_req_ready), .pe_resp_o(ref_resp),
    .stu_current_burst_exception_o(ref_exception), .axi_addrgen_req_ready_o(ref_addr_ready),
    .stu_operand_ready_o(ref_operand_ready), .mask_ready_o(ref_mask_ready), .idle_o(ref_idle), .*);

  task automatic compare;
    assert ({axi_w_valid_o,axi_b_ready_o,store_pending_o,store_complete_o,pe_req_ready_o,
             pe_resp_o,stu_current_burst_exception_o,axi_addrgen_req_ready_o,
             stu_operand_ready_o,mask_ready_o,idle_o} ===
            {ref_w_valid,ref_b_ready,ref_pending,ref_complete,ref_req_ready,ref_resp,
             ref_exception,ref_addr_ready,ref_operand_ready,ref_mask_ready,ref_idle})
      else $fatal(1,"VSTU output mismatch check=%0d",checks);
    if (axi_w_valid_o) assert (axi_w_o === ref_w)
      else $fatal(1,"VSTU W payload mismatch check=%0d",checks);
    `include "vstu_state_check.svh"
  endtask

  task automatic cycle;
    if (dut.lsu_ex_flush_q) begin
      mask_valid_i='0;
      stu_operand_valid_i='0;
    end
    #2; compare();
    if (dut.vinsn_issue_valid && dut.issue_cnt_bytes_d == 0) handoffs++;
    if (dut.vinsn_issue_valid && dut.issue_cnt_bytes_q == 0 &&
        pe_req_valid_i && pe_req_ready_o) same_cycle_accepts++;
    @(posedge clk_i); #2; compare(); checks++;
    @(negedge clk_i);
  endtask

  task automatic random_inputs(input int trial);
    pe_req_i='0;
    pe_req_i.vfu=VFU_StoreUnit; pe_req_i.op=VSE;
    pe_req_i.id=vid_t'(trial); pe_req_i.vm=1'(trial/4);
    pe_req_i.vtype.vsew=vew_e'(trial%4); pe_req_i.old_eew_vs1=vew_e'((trial/4)%4);
    pe_req_i.vl=11'($urandom_range(1,256));
    pe_req_i.vstart=11'($urandom_range(0,pe_req_i.vl));
    pe_req_valid_i=1'(trial); pe_vinsn_running_i='0;
    axi_w_ready_i=trial%3!=0; axi_b_i='0; axi_b_valid_i=trial%7==0;
    axi_addrgen_req_i='0;
    axi_addrgen_req_i.addr=64'h80000000+64'(trial%33);
    axi_addrgen_req_i.size=axi_pkg::size_t'(trial%4);
    axi_addrgen_req_i.len=axi_pkg::len_t'(trial%8);
    axi_addrgen_req_valid_i=trial%5!=0;
    addrgen_illegal_store_i=trial%127==0;
    lsu_ex_flush_i=trial%251==0;
    stu_operand_valid_i=trial%4==0 ? '0 : '1;
    foreach (stu_operand_i[i]) stu_operand_i[i]={$urandom,$urandom};
    mask_i=32'($urandom); mask_valid_i='1;
  endtask

  initial begin
    seed=$urandom(seed); random_inputs(0);
    repeat(3) @(negedge clk_i); rst_ni=1;
    // State cofactors isolate queued handoff, pointer wrap, nonzero vstart,
    // simultaneous accept/commit, and the final-beat geometry.
    for (int trial=0;trial<2048;trial++) begin
      rst_ni=0; repeat(2) @(negedge clk_i); rst_ni=1;
      random_inputs(trial);
      forced_queue='0;
      foreach (forced_queue.vinsn[i]) begin
        forced_queue.vinsn[i]=pe_req_i;
        forced_queue.vinsn[i].vl=11'(128+trial%128);
        forced_queue.vinsn[i].vstart=11'((trial+i)%128);
        forced_queue.vinsn[i].vtype.vsew=vew_e'((trial+i)%4);
      end
      forced_queue.issue_pnt=PW'((trial/4)%Depth);
      forced_queue.commit_pnt=forced_queue.issue_pnt;
      forced_queue.issue_cnt=(PW+1)'(1+trial%Depth);
      forced_queue.commit_cnt=forced_queue.issue_cnt;
      forced_queue.accept_pnt=PW'(forced_queue.issue_pnt+forced_queue.issue_cnt);
      force dut.vinsn_queue_q=forced_queue;
      force reference.vinsn_queue_q=forced_queue;
      force dut.issue_cnt_bytes_q='0; force reference.issue_cnt_bytes_q='0;
      #1;
      release dut.vinsn_queue_q; release reference.vinsn_queue_q;
      release dut.issue_cnt_bytes_q; release reference.issue_cnt_bytes_q;
      cycle();
      repeat(3) cycle();
    end
    rst_ni=0; repeat(2) @(negedge clk_i); rst_ni=1;
    for (int trial=0;trial<16000;trial++) begin random_inputs(trial); cycle(); end
    assert (handoffs>100 && same_cycle_accepts>100)
      else $fatal(1,"insufficient VSTU handoff coverage: %0d/%0d",handoffs,same_cycle_accepts);
    $display("VSTU equivalence PASS cycles=%0d handoffs=%0d concurrent_accepts=%0d",
             checks,handoffs,same_cycle_accepts);
    $finish;
  end
endmodule
