// SPDX-License-Identifier: SHL-0.51
// Control-path fixture only: backend acceptance/completion, no VRF or numerical execution.
module dispatcher_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import dispatcher_check_pkg::*;
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  accelerator_req_t acc_req_i;
  accelerator_resp_t acc_resp_o;
  ara_req_t ara_req_o;
  ara_resp_t ara_resp_i;
  logic ara_req_valid_o, ara_req_ready_i=1, ara_store_accepted_i=0;
  logic ara_resp_valid_i, ara_idle_i=1, sldu_idle_i=1, sldu_drain_o;
  logic lsu_ex_flush_o, lsu_ex_flush_done_i=1, core_st_pending_o;
  logic [NrLanes-1:0][4:0] fflags_ex_i='0;
  logic [NrLanes-1:0] fflags_ex_valid_i='0, vxsat_flag_i='0;
  vxrm_t [NrLanes-1:0] alu_vxrm_o;
  logic load_complete_i, store_complete_i=0, store_pending_i=0;
  int cycles=0, checks=0, captures=0, reshapes=0, originals=0, responses=0;
  int pending=0;
  bit last_exception=0;
  bit token_seen=0, last_token=0;
  bit expect_fixed=0, expect_normalized=0, partial_case=0;
  int capture_cycle=0, vd_reshape_cycle=0;
  int source_normalizations=0;
  bit uniform_case=0;
  int source_normalization_cycle=0;
  logic [1:0] uniform_normalized_regs=0;
  string label="reset";
  logic [63:0] last_cause;
  ara_req_t first_original;

  // Match the reference fixture: a load responds in its registered acceptance
  // cycle. This is a control-path injection, not a cycle-accurate VLSU model.
  assign ara_resp_valid_i=ara_req_valid_o && ara_req_ready_i &&
      (ara_req_o.op inside {VLE,VLXE});
  assign load_complete_i=ara_resp_valid_i;
  always_comb begin
    ara_resp_i='0;
    if (ara_resp_valid_i && ara_req_o.op==VLXE) begin
      ara_resp_i.exception.valid=1;
      ara_resp_i.exception.cause=13;
      ara_resp_i.exception.tval=64'h3fb12ec000;
      ara_resp_i.exception_vstart=0;
    end
  end

  ara_dispatcher #(.NrLanes(NrLanes), .VLEN(VLEN), .CVA6Cfg(CVA6Cfg),
    .ara_req_t(ara_req_t), .ara_resp_t(ara_resp_t),
    .accelerator_req_t(accelerator_req_t), .accelerator_resp_t(accelerator_resp_t)) dut (.*);

  task automatic check(bit condition, string detail);
    checks++;
    if (!condition) $fatal(1,"FAIL %s cycle=%0d %s",label,cycles,detail);
  endtask

  always @(posedge clk_i) if (rst_ni) begin
    cycles++;
    $display("CYCLE case=%s cycle=%0d state=%0d flush_state=%0d valid=%b ready=%b op=%0d capture=%b replay=%b scale_vl=%b tag2=%0d next2=%0d tag3=%0d snapshot_valid=%b snapshot_eew=%0d csr_vstart=%0d response=%b exception=%b exception_start=%0d",
      label,cycles,dut.state_q,dut.lsu_ex_state_q,ara_req_valid_o,ara_req_ready_i,
      ara_req_o.op,ara_req_o.source_snapshot_capture,ara_req_o.source_snapshot_replay_vs2,
      ara_req_o.scale_vl,dut.eew_q[2],dut.eew_d[2],dut.eew_q[3],
      dut.source_snapshot_valid_q,dut.source_snapshot_eew_q,dut.csr_vstart_q,
      ara_resp_valid_i,ara_resp_i.exception.valid,ara_resp_i.exception_vstart);
    if (ara_req_valid_o && ara_req_ready_i &&
        (!token_seen || ara_req_o.token!=last_token)) begin
      token_seen<=1; last_token<=ara_req_o.token;
      check(pending==0 || ara_req_o.op==VSLIDEDOWN,
            "original load accepted before modeled maintenance drained");
      if (ara_req_o.source_snapshot_capture) begin
        captures++;
        capture_cycle=cycles;
        if (uniform_case) begin
          if (expect_normalized) begin
            check(source_normalizations==captures+1,
                  "fix2 must normalize two initial registers, then one on retry");
            check(uniform_normalized_regs==2'b11 && source_normalization_cycle<cycles,
                  "both uniform source registers must normalize before capture");
            check(dut.eew_q[2]==EW64 && dut.eew_q[3]==EW64,
                  "fix2 source tags must be EW64 at capture");
          end else begin
            check(source_normalizations==0,"fix1 uniform source unexpectedly normalized");
            check(dut.eew_q[2]==EW8 && dut.eew_q[3]==EW8,
                  "uniform source tags must still be EW8 at capture");
          end
          check(ara_req_o.eew_vs2==EW64 && ara_req_o.vtype.vsew==EW64,
                "snapshot descriptor must use requested EW64");
          $display("RESULT case=uniform_eew8 phase=capture cycle=%0d tag2=%0d tag3=%0d capture_eew=%0d source_normalizations=%0d",
            cycles,dut.eew_q[2],dut.eew_q[3],ara_req_o.eew_vs2,source_normalizations);
        end
      end
      if (ara_req_o.op==VSLIDEDOWN && ara_req_o.scale_vl && ara_req_o.use_vd) begin
        reshapes++;
        if (ara_req_o.vtype.vsew==EW64) begin
          source_normalizations++;
          source_normalization_cycle=cycles;
          if (uniform_case && expect_normalized) begin
            check(captures==originals,"source normalization must precede fresh capture");
            if (captures==0) begin
              check(ara_req_o.eew_vs2==EW8 && ara_req_o.vd inside {2,3},
                    "initial normalization must convert v2/v3 from EW8");
              uniform_normalized_regs[ara_req_o.vd-2]=1'b1;
            end else
              check(ara_req_o.eew_vs2==EW32 && ara_req_o.vd==2,
                    "retry normalization must convert v2 from EW32");
          end
        end
        if (ara_req_o.vtype.vsew==EW32) begin
          check(captures==originals+1 && capture_cycle<cycles,
                "vd normalization must follow this attempt's source capture");
          vd_reshape_cycle=cycles;
        end
      end
      if (ara_req_o.op==VLXE) begin
        originals++;
        if (originals==1) first_original=ara_req_o;
        check(ara_req_o.source_snapshot_replay_vs2,"original lacks snapshot replay");
        check(ara_req_o.eew_vs2==EW64 && ara_req_o.old_eew_vs2==EW64,
              "original index descriptor must retain snapshot EW64");
        check(captures==originals && capture_cycle<cycles,
              "each original must follow a fresh source capture");
        if (partial_case || expect_fixed)
          check(vd_reshape_cycle>capture_cycle && vd_reshape_cycle<cycles,
                "original must follow capture then vd normalization");
      end
      $display("ACCEPT case=%s cycle=%0d op=%0d capture=%b scale_vl=%b replay=%b vd=%0d vs2=%0d emul=%0d vsew=%0d eew2=%0d old_eew2=%0d vl=%0d vstart=%0d tag2=%0d snapshot=%b",
        label,cycles,ara_req_o.op,ara_req_o.source_snapshot_capture,ara_req_o.scale_vl,
        ara_req_o.source_snapshot_replay_vs2,ara_req_o.vd,ara_req_o.vs2,ara_req_o.emul,
        ara_req_o.vtype.vsew,ara_req_o.eew_vs2,ara_req_o.old_eew_vs2,
        ara_req_o.vl,ara_req_o.vstart,dut.eew_q[2],dut.source_snapshot_valid_q);
      if (ara_req_o.op==VSLIDEDOWN) pending+=3;
    end
    if (ara_resp_valid_i) responses++;
  end

  // Maintenance completion is modeled only through idle, never VRF writes.
  always @(negedge clk_i) if (rst_ni) begin
    if (pending>0) begin
      pending--;
      ara_idle_i=0; sldu_idle_i=0;
      if (pending==0) begin
        ara_idle_i=1; sldu_idle_i=1;
      end
    end
  end

  task automatic send(logic [31:0] insn, logic [63:0] rs1=0);
    int waited;
    @(negedge clk_i); #1;
    acc_req_i='0; acc_req_i.insn=insn; acc_req_i.rs1=rs1;
    acc_req_i.req_valid=1; acc_req_i.resp_ready=1;
    acc_req_i.frm=fpnew_pkg::RNE;
    waited=0;
    #1;
    while (!acc_resp_o.req_ready) begin
      @(negedge clk_i); #1;
      waited++;
      if (waited>120) $fatal(1,"Timeout case=%s insn=%h state=%0d",label,insn,dut.state_q);
    end
    last_exception=acc_resp_o.exception.valid;
    last_cause=acc_resp_o.exception.cause;
    $display("RESPONSE case=%s cycle=%0d insn=%h exception=%b cause=%0d csr_vstart=%0d next_start=%0d tag2=%0d snapshot=%b",
      label,cycles,insn,last_exception,last_cause,dut.csr_vstart_q,dut.csr_vstart_d,
      dut.eew_q[2],dut.source_snapshot_valid_q);
    @(negedge clk_i); #1; acc_req_i.req_valid=0;
    repeat(15) @(negedge clk_i);
    #1;
  endtask

  task automatic uniform_source;
    int before_reshape, before_normalize;
    @(negedge clk_i); #1;
    rst_ni=0; acc_req_i='0; pending=0; token_seen=0; last_token=0;
    ara_req_ready_i=1; ara_idle_i=1; sldu_idle_i=1;
    repeat(3) @(negedge clk_i);
    #1; rst_ni=1;
    label="uniform_eew8"; uniform_case=1; partial_case=0;
    captures=0; reshapes=0; originals=0; responses=0;
    source_normalizations=0; capture_cycle=0; vd_reshape_cycle=0;
    source_normalization_cycle=0; uniform_normalized_regs=0;
    // A regular byte load of two complete registers models restored EW8 tags.
    // It does not model the memory bytes or context-save numerical semantics.
    configure(EW8,LMUL_2,256);
    send(32'h02008107); // vle8.v v2,(x1)
    check(!last_exception && dut.eew_valid_q[2] && dut.eew_valid_q[3] &&
          dut.eew_q[2]==EW8 && dut.eew_q[3]==EW8,"uniform EW8 preparation failed");
    configure(EW32,LMUL_1,32);
    send(32'h0625f107,64'h3fb12e5000);
    check(last_exception && last_cause==13,"uniform-source injected fault0 response");
    check(captures==1 && originals==1 && source_normalizations==(expect_normalized ? 2 : 0),
          "uniform-source capture ordering/count mismatch");
    check(reshapes==(expect_normalized ? 3 : (expect_fixed ? 1 : 0)),
          "uniform-source normalization/reshape count mismatch");
    check(dut.eew_q[2]==EW32 && dut.eew_q[3]==(expect_normalized ? EW64 : EW8) && dut.csr_vstart_q==0,
          "uniform-source post-fault tags/vstart mismatch");
    $display("RESULT case=uniform_eew8 phase=fault0 captures=%0d reshapes=%0d source_normalizations=%0d originals=%0d tag2=%0d tag3=%0d vstart=%0d",
      captures,reshapes,source_normalizations,originals,dut.eew_q[2],dut.eew_q[3],dut.csr_vstart_q);
    if (expect_normalized) begin
      before_reshape=reshapes; before_normalize=source_normalizations;
      send(32'h0625f107,64'h3fb12e5000);
      check(last_exception && last_cause==13,"uniform-source retry fault0 response");
      check(captures==2 && originals==2 && source_normalizations-before_normalize==1,
            "uniform-source retry must normalize once and recapture once");
      check(reshapes-before_reshape==2,"uniform-source retry needs source and vd normalization");
      check(dut.eew_q[2]==EW32 && dut.eew_q[3]==EW64 && dut.csr_vstart_q==0 &&
            !dut.source_snapshot_valid_q,"uniform-source retry tags/CSR/snapshot mismatch");
      $display("RESULT case=uniform_eew8 phase=retry captures=%0d reshapes=%0d source_normalizations=%0d retry_reshapes=%0d retry_source_normalizations=%0d originals=%0d vstart=%0d",
        captures,reshapes,source_normalizations,reshapes-before_reshape,
        source_normalizations-before_normalize,originals,dut.csr_vstart_q);
    end
    uniform_case=0;
  endtask

  task automatic configure(int sew, int lmul, int vl);
    send({1'b0,11'((sew<<3)|lmul),5'd1,3'b111,5'd5,7'h57},64'(vl));
    check(!last_exception,"vsetvli rejected");
    check(dut.csr_vl_q==vl,"unexpected configured VL");
  endtask

  task automatic scenario(bit partial);
    int initial_reshape, before_capture, before_reshape;
    @(negedge clk_i); #1;
    rst_ni=0; acc_req_i='0; pending=0; token_seen=0; last_token=0;
    ara_req_ready_i=1;
    ara_idle_i=1; sldu_idle_i=1;
    repeat(3) @(negedge clk_i);
    #1; rst_ni=1;
    label=partial ? "m1_partial_vl16" : "m1_full";
    partial_case=partial;
    capture_cycle=0; vd_reshape_cycle=0;
    captures=0; reshapes=0; originals=0; responses=0;
    configure(EW64,LMUL_2,32);
    send(32'h0200f107); // vle64.v v2,(x1)
    check(!last_exception && dut.eew_q[2]==EW64 && dut.eew_q[3]==EW64,
          "preparation must tag v2-v3 EW64");
    configure(EW32,LMUL_1,partial ? 16 : 32);
    check(dut.eew_q[2]==EW64,"vsetvli must not change register layout");
    check(captures==0 && reshapes==0,"unexpected preparation maintenance");
    send(32'h0625f107,64'h3fb12e5000); // vluxei64.v v2,(a1),v2
    check(last_exception && last_cause==13,"fault0 must return cause13");
    check(originals==1 && captures==1,"first attempt capture/original count");
    initial_reshape=reshapes;
    check(initial_reshape==((partial || expect_fixed) ? 1 : 0),
          "initial reshape count differs from selected baseline/fixed expectation");
    check(dut.eew_q[2]==EW32 && dut.eew_q[3]==EW64,"fault0 retains narrow vd tag, wide v3 tag");
    check(dut.csr_vstart_q==0,"fault0 vstart must be zero");
    check(!dut.source_snapshot_valid_q,"issue consumes dispatcher snapshot validity");
    $display("RESULT case=%s phase=fault0 captures=%0d reshapes=%0d originals=%0d tag2=%0d tag3=%0d vstart=%0d snapshot=%b",
      label,captures,reshapes,originals,dut.eew_q[2],dut.eew_q[3],dut.csr_vstart_q,dut.source_snapshot_valid_q);
    before_capture=captures; before_reshape=reshapes;
    send(32'h0625f107,64'h3fb12e5000);
    check(last_exception && last_cause==13,"retry fault0 response");
    check(originals==2 && captures==before_capture+1,"retry recaptures source");
    // VL16 touches only v2: fix2 also normalizes a uniformly narrow active
    // source. VL32 touches both registers and already takes the mixed path.
    check(reshapes-before_reshape==(partial ? (expect_normalized ? 2 : 0) :
                                  (expect_fixed ? 2 : 1)),
          "retry source/vd normalization count differs from expectation");
    check(dut.csr_vstart_q==0,"retry fault0 vstart");
    $display("RESULT case=%s phase=retry captures=%0d reshapes=%0d retry_reshapes=%0d originals=%0d tag2=%0d tag3=%0d vstart=%0d snapshot=%b",
      label,captures,reshapes,reshapes-before_reshape,originals,dut.eew_q[2],dut.eew_q[3],dut.csr_vstart_q,dut.source_snapshot_valid_q);
  endtask

  initial begin
    acc_req_i='0;
    expect_fixed=$test$plusargs("EXPECT_FIXED");
    expect_normalized=$test$plusargs("EXPECT_NORMALIZED");
    $display("MODE expect_fixed=%b expect_normalized=%b partial_control=e32_m1_vl16_vs2_v2_index_emul2_legal",expect_fixed,expect_normalized);
    scenario(0);
    scenario(1);
    if ($test$plusargs("UNIFORM_INDEX_EEW8")) uniform_source();
    $display("DISPATCHER_PASS checks=%0d cycles=%0d scope=control_path_only_no_VRF_numerical_claim",checks,cycles);
    $finish;
  end
  initial begin #50000; $fatal(1,"Bounded fixture watchdog"); end
endmodule
