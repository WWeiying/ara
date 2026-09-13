// SPDX-License-Identifier: SHL-0.51
module dispatcher_equivalence_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import dispatcher_check_pkg::*;
  logic clk_i = 0, rst_ni = 0;
  always #5 clk_i = ~clk_i;
  accelerator_req_t acc_req_i;
  accelerator_resp_t acc_resp_o, ref_acc_resp;
  ara_req_t ara_req_o, ref_ara_req;
  ara_resp_t ara_resp_i;
  logic ara_req_valid_o, ref_ara_req_valid;
  logic ara_req_ready_i, ara_resp_valid_i, ara_idle_i, sldu_idle_i;
  logic sldu_drain_o, ref_sldu_drain;
  logic lsu_ex_flush_o, ref_lsu_ex_flush, lsu_ex_flush_done_i;
  logic core_st_pending_o, ref_core_st_pending;
  logic [NrLanes-1:0][4:0] fflags_ex_i;
  logic [NrLanes-1:0] fflags_ex_valid_i, vxsat_flag_i;
  vxrm_t [NrLanes-1:0] alu_vxrm_o, ref_alu_vxrm;
  logic load_complete_i, store_complete_i, store_pending_i;
  int checks=0, stalled=0, accepted=0, state_visits[16];
  int seed=32'h43692210;
  logic [2:0] forced_pending;

  ara_dispatcher #(.NrLanes(NrLanes), .VLEN(VLEN), .CVA6Cfg(CVA6Cfg), .ara_req_t(ara_req_t),
      .ara_resp_t(ara_resp_t), .accelerator_req_t(accelerator_req_t),
      .accelerator_resp_t(accelerator_resp_t)) dut (.*);
  ara_dispatcher_reference #(.NrLanes(NrLanes), .VLEN(VLEN), .CVA6Cfg(CVA6Cfg), .ara_req_t(ara_req_t),
      .ara_resp_t(ara_resp_t), .accelerator_req_t(accelerator_req_t),
      .accelerator_resp_t(accelerator_resp_t)) reference (
      .acc_resp_o(ref_acc_resp), .ara_req_o(ref_ara_req),
      .ara_req_valid_o(ref_ara_req_valid), .sldu_drain_o(ref_sldu_drain),
      .lsu_ex_flush_o(ref_lsu_ex_flush), .core_st_pending_o(ref_core_st_pending),
      .alu_vxrm_o(ref_alu_vxrm), .*);

  function automatic logic[31:0] vector_insn(
      logic[5:0] f6, logic vm, logic[4:0] vs2, vs1, logic[2:0] f3, logic[4:0] vd);
    return {f6, vm, vs2, vs1, f3, vd, 7'h57};
  endfunction

  task automatic compare_outputs;
    assert (!$isunknown({acc_resp_o.req_ready, acc_resp_o.resp_valid, ara_req_valid_o}))
      else $fatal(1, "unknown dispatcher handshake cycle=%0d", checks);
    assert ({acc_resp_o, ara_req_o, ara_req_valid_o, sldu_drain_o,
             lsu_ex_flush_o, core_st_pending_o, alu_vxrm_o} ===
            {ref_acc_resp, ref_ara_req, ref_ara_req_valid, ref_sldu_drain,
             ref_lsu_ex_flush, ref_core_st_pending, ref_alu_vxrm})
      else $fatal(1, "dispatcher output cycle=%0d state=%0d ready=%b insn=%h acc=%h ref=%h",
          checks, dut.state_q, ara_req_ready_i, acc_req_i.insn, acc_resp_o, ref_acc_resp);
  endtask

  task automatic cycle;
    #2;
    compare_outputs();
    if (dut.decode_blocked) stalled++;
    if (acc_req_i.req_valid && acc_resp_o.req_ready) accepted++;
    state_visits[int'(dut.state_q)]++;
    @(posedge clk_i); #2;
    checks++;
    `include "dispatcher_state_check.svh"
    compare_outputs();
    @(negedge clk_i);
  endtask

  task automatic config_vl(input logic [10:0] vtype, input logic [63:0] avl);
    acc_req_i = '0;
    acc_req_i.req_valid=1; acc_req_i.resp_ready=1; acc_req_i.rs1=avl;
    acc_req_i.insn={1'b0, vtype, 5'd1, 3'b111, 5'd5, 7'h57};
    ara_req_ready_i=1; ara_resp_valid_i=1; ara_idle_i=1;
    repeat (8) cycle();
    acc_req_i.req_valid=0;
    repeat (8) cycle();
  endtask

  initial begin
    seed=$urandom(seed);
    acc_req_i='0; ara_resp_i='0;
    ara_req_ready_i=0; ara_resp_valid_i=0; ara_idle_i=1; sldu_idle_i=1;
    fflags_ex_i='0; fflags_ex_valid_i='0; vxsat_flag_i='0;
    lsu_ex_flush_done_i=1; load_complete_i=0; store_complete_i=0; store_pending_i=0;
    foreach (state_visits[i]) state_visits[i]=0;
    repeat (3) @(negedge clk_i);
    rst_ni=1;
    for (int batch=0; batch<64; batch++) begin
      config_vl(11'(((batch%4)<<3) | ((batch/4)%8) | ((batch/32)<<6)),
                batch%9 == 0 ? 64'd0 : 64'(1+batch*3));
      for (int trial=0; trial<1024; trial++) begin
        logic[4:0] vs1, vs2, vd;
        vs1=5'($urandom); vs2=5'($urandom); vd=5'($urandom);
        if (trial%4==0 || (acc_resp_o.req_ready && acc_req_i.req_valid)) begin
          acc_req_i='0;
          acc_req_i.req_valid=1; acc_req_i.resp_ready=1; acc_req_i.acc_cons_en=1;
          acc_req_i.frm=fpnew_pkg::roundmode_e'(trial%5);
          acc_req_i.trans_id=CVA6Cfg.TRANS_ID_BITS'($urandom);
          acc_req_i.rs1=64'($urandom_range(0,255));
          acc_req_i.rs2=64'($urandom_range(0,127));
          case (trial%16)
            0: acc_req_i.insn=vector_insn(6'h00,1,vs2,vs1,0,vd);
            1: acc_req_i.insn=vector_insn(6'h30,1,vs2,vs1,2,vd);
            2: acc_req_i.insn=vector_insn(6'h2c,1,vs2,vs1,0,vd);
            3: acc_req_i.insn=vector_insn(6'h3d,0,vs2,vs1,2,vd);
            4: acc_req_i.insn=vector_insn(6'h0c,1,vs2,vs1,0,vd);
            5: acc_req_i.insn=vector_insn(6'h17,1,vs2,vs1,2,vd);
            6: acc_req_i.insn=vector_insn(6'h00,1,vs2,vs1,2,vd);
            7: acc_req_i.insn={3'(batch%4),1'b0,2'b00,1'(batch%2),5'd0,vs1,3'b110,vd,7'h07};
            8: acc_req_i.insn={3'(batch%4),1'b0,2'b10,1'b1,vs2,vs1,3'b101,vd,7'h27};
            9: acc_req_i.insn={3'd0,1'b0,2'b00,1'b1,5'b10000,vs1,3'b110,vd,7'h07};
            10: acc_req_i.insn={12'h008,vs1,3'b001,vd,7'h73};
            11: acc_req_i.insn=vector_insn(6'h10,1,vs2,5'd0,2,vd);
            12: acc_req_i.insn=vector_insn(6'h00,1,vs2,vs1,1,vd);
            13: acc_req_i.insn={7'd0,vs2,vs1,3'b000,vd,7'h0b};
            14: acc_req_i.insn={7'd0,vs2,vs1,3'b110,vd,7'h5b};
            default: acc_req_i.insn=$urandom;
          endcase
        end
        ara_req_ready_i=(trial%17>=5);
        ara_resp_valid_i=trial%7==3;
        ara_idle_i=trial%5!=0;
        sldu_idle_i=trial%3!=0;
        ara_resp_i='0;
        ara_resp_i.resp={$urandom,$urandom};
        ara_resp_i.exception.valid=trial%37==0;
        ara_resp_i.exception.cause=64'd5;
        ara_resp_i.exception_vstart=11'(trial%9);
        ara_resp_i.fof_exception=trial%41==0;
        fflags_ex_i=20'($urandom); fflags_ex_valid_i=4'($urandom);
        vxsat_flag_i=4'($urandom);
        load_complete_i=trial%13==0; store_complete_i=trial%19==0;
        store_pending_i=trial%11==0;
        cycle();
      end
    end

    // Sweep the state cofactors directly, including a queued reshuffle while
    // normal decoding is blocked. This checks equivalence even for states
    // that random legal instructions rarely reach; it is not ISA stimulus.
    for (int state_code=0; state_code<15; state_code++) begin
      for (int pending=0; pending<8; pending++) begin
        for (int ready=0; ready<2; ready++) begin
          for (int valid=0; valid<2; valid++) begin
            rst_ni=0;
            repeat (2) @(negedge clk_i);
            rst_ni=1;
            case (state_code)
              0: begin
                force dut.state_q=dut.NORMAL_OPERATION;
                force reference.state_q=reference.NORMAL_OPERATION;
              end
              1: begin
                force dut.state_q=dut.WAIT_IDLE;
                force reference.state_q=reference.WAIT_IDLE;
              end
              2: begin
                force dut.state_q=dut.WAIT_IDLE_FLUSH;
                force reference.state_q=reference.WAIT_IDLE_FLUSH;
              end
              3: begin
                force dut.state_q=dut.RESHUFFLE;
                force reference.state_q=reference.RESHUFFLE;
              end
              4: begin
                force dut.state_q=dut.OVERLAP_PREFIX_FIXUP;
                force reference.state_q=reference.OVERLAP_PREFIX_FIXUP;
              end
              5: begin
                force dut.state_q=dut.OVERLAP_WAIT_PREFIX_FIXUP;
                force reference.state_q=reference.OVERLAP_WAIT_PREFIX_FIXUP;
              end
              6: begin
                force dut.state_q=dut.OVERLAP_CAPTURE;
                force reference.state_q=reference.OVERLAP_CAPTURE;
              end
              7: begin
                force dut.state_q=dut.OVERLAP_WAIT_CAPTURE;
                force reference.state_q=reference.OVERLAP_WAIT_CAPTURE;
              end
              8: begin
                force dut.state_q=dut.OVERLAP_ISSUE_ORIGINAL;
                force reference.state_q=reference.OVERLAP_ISSUE_ORIGINAL;
              end
              9: begin
                force dut.state_q=dut.OVERLAP_WAIT_ORIGINAL;
                force reference.state_q=reference.OVERLAP_WAIT_ORIGINAL;
              end
              10: begin
                force dut.state_q=dut.OVERLAP_FIXUP;
                force reference.state_q=reference.OVERLAP_FIXUP;
              end
              11: begin
                force dut.state_q=dut.OVERLAP_WAIT_FIXUP;
                force reference.state_q=reference.OVERLAP_WAIT_FIXUP;
              end
              12: begin
                force dut.state_q=dut.OVERLAP_RESPOND;
                force reference.state_q=reference.OVERLAP_RESPOND;
              end
              13: begin
                force dut.state_q=dut.SOURCE_SNAPSHOT_CAPTURE;
                force reference.state_q=reference.SOURCE_SNAPSHOT_CAPTURE;
              end
              14: begin
                force dut.state_q=dut.SOURCE_SNAPSHOT_WAIT;
                force reference.state_q=reference.SOURCE_SNAPSHOT_WAIT;
              end
            endcase
            forced_pending=3'(pending);
            force dut.reshuffle_req_q=forced_pending;
            force reference.reshuffle_req_q=forced_pending;
            force dut.csr_vl_q=11'd19; force reference.csr_vl_q=11'd19;
            force dut.csr_vstart_q=11'd3; force reference.csr_vstart_q=11'd3;
            force dut.csr_vtype_q=vtype_t'{vsew:EW32,vlmul:LMUL_2,default:'0};
            force reference.csr_vtype_q=vtype_t'{vsew:EW32,vlmul:LMUL_2,default:'0};
            acc_req_i='0; acc_req_i.req_valid=1'(valid); acc_req_i.resp_ready=1;
            acc_req_i.insn=vector_insn(6'h30,1,5'd4,5'd8,2,5'd8);
            ara_req_ready_i=1'(ready); ara_idle_i=1; sldu_idle_i=1;
            ara_resp_i='0; ara_resp_valid_i=1;
            lsu_ex_flush_done_i=1;
            #1;
            release dut.state_q; release reference.state_q;
            release dut.reshuffle_req_q; release reference.reshuffle_req_q;
            release dut.csr_vl_q; release reference.csr_vl_q;
            release dut.csr_vstart_q; release reference.csr_vstart_q;
            release dut.csr_vtype_q; release reference.csr_vtype_q;
            cycle();
          end
        end
      end
    end
    foreach (state_visits[i])
      $display("dispatcher state=%0d visits=%0d",i,state_visits[i]);
    for (int i=0; i<15; i++)
      assert (state_visits[i]>0) else $fatal(1,"uncovered dispatcher state=%0d",i);
    assert (stalled>100 && accepted>100) else $fatal(1,"insufficient handshake coverage");
    $display("Dispatcher equivalence PASS checks=%0d blocked=%0d accepted=%0d",checks,stalled,accepted);
    $finish;
  end
endmodule
