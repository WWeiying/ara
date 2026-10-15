`timescale 1ns/1ps
module epoch_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import fpnew_pkg::*;
  parameter int N=4;
  localparam int VLEN=1024, Rounds=$clog2(N)+1;
  localparam config_pkg::cva6_cfg_t Cfg=build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef logic [15:0] vaddr_t;
  typedef struct packed {
    vid_t id; ara_op_e op;
    logic vm, use_vs1, use_vs2, use_vd_op, preserve_narrow_vd;
    elen_t scalar_op; logic use_scalar_op, skip_sldu_operand;
    vfu_e vfu; logic [4:0] vd; logic use_vd, swap_vs2_vd_op;
    roundmode_e fp_rm; logic wide_fp_imm; resize_e cvt_resize;
    vlen_t vl, vstart; vtype_t vtype;
  } operation_t;
  logic clk=0, rst_n=0, running=0;
  always #5 clk=~clk;
  operation_t [N-1:0] op;
  elen_t [N-1:0][2:0] operands;
  logic [N-1:0][2:0] operand_valid, operand_ready;
  logic [N-1:0] req, ready, result_req, result_gnt, red_valid, red_ready;
  logic [N-1:0] slide_valid, slide_ready, flags_valid, activity;
  logic [N-1:0][NrVInsn-1:0] done;
  elen_t [N-1:0] result, tx_data, response_data;
  logic [N-1:0] tx_valid, tx_ready, response_valid;
  vid_t [N-1:0] result_id, issue_id, process_id, flag_id;
  logic [N-1:0][7:0] mask, result_be;
  logic [N-1:0][4:0] flags, pending;
  logic [N-1:0][2:0] state, next_state;
  logic [N-1:0] issue_valid, first, in_valid, in_ready, rx_valid, rx_ready, snapshot;
  logic [N-1:0][3:0] rounds_left;
  vaddr_t [N-1:0] result_addr;
  int cycle=0, start_cycle, cid=0, width, kind, scenario, gap, seed_mode;
  int requested[N], sent[N][2], seed_sent[N][2], completed[N][2], flag_count[N][2];
  int stage, writes[2], snapshots[N][2], overlap, data_errors, flag_errors;
  int trace_fd, results_fd, failures=0;
  logic [4:0] sticky;
  logic active[2];
  elen_t observed[2];

  for (genvar l=0;l<N;l++) begin: lanes
    vmfpu #(.NrLanes(N),.VLEN(VLEN),.CVA6Cfg(Cfg),.vaddr_t(vaddr_t),
      .vfu_operation_t(operation_t)) dut (
      .clk_i(clk),.rst_ni(rst_n),.lane_id_i(cf_math_pkg::idx_width(N)'(l)),.mfpu_vxsat_o(),.mfpu_vxrm_i('0),
      .fflags_ex_o(flags[l]),.fflags_ex_valid_o(flags_valid[l]),
      .vfu_operation_i(op[l]),.vfu_operation_valid_i(req[l]),.mfpu_ready_o(ready[l]),
      .mfpu_vinsn_done_o(done[l]),.fpu_red_complete_o(),.reduction_any_active_o(activity[l]),
      .reduction_global_any_active_i(|activity),.mfpu_operand_i(operands[l]),
      .mfpu_operand_valid_i(operand_valid[l]),.mfpu_operand_ready_o(operand_ready[l]),
      .mfpu_result_req_o(result_req[l]),.mfpu_result_id_o(result_id[l]),
      .mfpu_result_addr_o(result_addr[l]),.mfpu_result_wdata_o(result[l]),
      .mfpu_result_be_o(result_be[l]),.mfpu_result_gnt_i(result_gnt[l]),
      .mfpu_red_valid_o(red_valid[l]),.mfpu_red_ready_i(red_ready[l]),
      .sldu_operand_i(response_data[l]),.sldu_mfpu_valid_i(slide_valid[l]),
      .sldu_mfpu_ready_o(slide_ready[l]),.mask_operand_o(),.mask_operand_valid_o(),
      .mask_operand_ready_i(1'b1),.mask_i(mask[l]),.mask_valid_i(1'b1),.mask_ready_o());
    spill_register #(.T(elen_t)) tx_buffer (.clk_i(clk),.rst_ni(rst_n),
      .data_i(result[l]),.valid_i(red_valid[l]),.ready_o(red_ready[l]),
      .data_o(tx_data[l]),.valid_o(tx_valid[l]),.ready_i(tx_ready[l]));
    assign state[l]=dut.mfpu_state_q;
    assign next_state[l]=dut.mfpu_state_d;
    assign issue_id[l]=dut.vinsn_issue_q.id;
    assign process_id[l]=dut.vinsn_processing_q.id;
    assign issue_valid[l]=dut.vinsn_issue_q_valid;
    assign first[l]=dut.first_op_q;
    assign in_valid[l]=dut.vfpu_in_valid;
    assign in_ready[l]=dut.vfpu_in_ready;
    assign rx_valid[l]=dut.sldu_mfpu_valid_q;
    assign rx_ready[l]=dut.sldu_mfpu_ready_d;
    assign rounds_left[l]=dut.sldu_transactions_cnt_q;
    assign pending[l]=dut.fpu_gen.reduction_fflags_q;
`ifdef EPOCH_SNAPSHOT
    assign snapshot[l]=dut.reduction_epoch_any_active_q;
`else
    assign snapshot[l]=1'b0;
`endif
    always_ff @(posedge clk) flag_id[l]<=process_id[l];
  end

  function automatic int global_vl(int id);
    return id==1 && !active[1] ? 1 : 4*N;
  endfunction
  function automatic int local_vl(int id, int lane);
    return (global_vl(id)+N-1-lane)/N;
  endfunction
  function automatic elen_t one();
    return width==16 ? 64'h3c00 : width==32 ? 64'h3f800000 : 64'h3ff0000000000000;
  endfunction
  function automatic elen_t snan();
    return width==16 ? 64'h7c01 : width==32 ? 64'h7f800001 : 64'h7ff0000000000001;
  endfunction
  function automatic elen_t qnan();
    return width==16 ? 64'h7e00 : width==32 ? 64'h7fc00000 : 64'h7ff8000000000000;
  endfunction
  function automatic elen_t expected(int id);
    bit invalid_seed;
    invalid_seed=id==0 || seed_mode;
    if (!active[id]) return invalid_seed ? snan() : one();
    if (invalid_seed) return kind==0 ? qnan() : one();
    if (kind!=0) return one();
    return width==16 ? 64'h4000 : width==32 ? 64'h40000000 : 64'h4000000000000000;
  endfunction
  function automatic logic [4:0] expected_flags(int id, int lane);
    return lane==0 && active[id] && (id==0 || seed_mode) ? 5'h10 : 5'h00;
  endfunction

  task automatic drive;
    int id, index, slots, beats, off;
    elen_t seed_word, source_word, neutral;
    slots=64/width; req=0; operands=0; operand_valid=0; mask=0;
    for (int l=0;l<N;l++) begin
      id=requested[l];
      if (id<2) begin
        req[l]=1; op[l]='0; op[l].id=vid_t'(id);
        op[l].op=kind==0 ? VFREDUSUM : kind==1 ? VFREDMIN : VFREDMAX;
        op[l].use_vs1=1; op[l].use_vs2=1; op[l].swap_vs2_vd_op=kind==0;
        op[l].use_vd=1; op[l].vd=24+id; op[l].vfu=VFU_MFpu;
        op[l].cvt_resize=resize_e'(kind); op[l].fp_rm=RNE;
        op[l].vtype.vsew=width==16 ? EW16 : width==32 ? EW32 : EW64;
        op[l].vtype.vlmul=LMUL_1; op[l].vl=vlen_t'(local_vl(id,l));
      end
      id=int'(issue_id[l]);
      if (issue_valid[l] && id<2) begin
        beats=(local_vl(id,l)+slots-1)/slots;
        if (beats==0) beats=1;
        neutral=kind==0 ? 0 : qnan(); seed_word=0; source_word=0;
        for (int e=0;e<slots;e++) begin
          seed_word|=(e==0 && l==0 ? (id==0 || seed_mode ? snan() : one()) : neutral)<<(e*width);
          source_word|=one()<<(e*width);
          index=(sent[l][id]*slots+e)*N+l;
          for (int b=0;b<width/8;b++) begin
            off=shuffle_index(e*width/8+b,1,width==16 ? EW16 : width==32 ? EW32 : EW64);
            mask[l][off]=index==1 && index<global_vl(id) && (active[id] || id==1);
          end
        end
        operands[l][0]=seed_word;
        operand_valid[l][0]=!seed_sent[l][id];
        operands[l][kind==0 ? 2 : 1]=source_word;
        operand_valid[l][kind==0 ? 2 : 1]=sent[l][id]<beats &&
          !(gap && l==(N==1 ? 0 : 1) && id==0 && cycle-start_cycle<35);
      end
    end
  endtask

  // Every round consumes a complete lane aggregate. Independent TX cuts and
  // independent RX consumption match the SLDU barrier, without an added fence.
  always_comb begin
    tx_ready=0; slide_valid=running ? response_valid : '0;
    result_gnt=running && (!gap || cycle%7==0) ? result_req : '0;
    if (running && stage<2*Rounds && !(|response_valid) && &tx_valid) tx_ready='1;
  end
  always @(posedge clk) begin
    cycle<=cycle+1;
    if (!rst_n) begin response_valid<=0; response_data<=0; end
    else if (running) begin
      logic [4:0] flag_bus;
      flag_bus=0;
      for (int l=0;l<N;l++) flag_bus|=flags[l];
      if (|flags_valid) sticky|=flag_bus;
      response_valid<=response_valid & ~slide_ready;
      if (&tx_ready) begin
        for (int l=0;l<N;l++)
          response_data[l]<=tx_data[(l+N-((stage%Rounds==Rounds-1 ? 1 : 1<<(stage%Rounds))%N))%N];
        response_valid<='1; stage<=stage+1;
      end
      for (int l=0;l<N;l++) begin
        int id;
        if (req[l] && ready[l]) begin
          if (requested[l]==1 && completed[l][0]==0) overlap++;
          requested[l]++;
        end
        id=int'(issue_id[l]);
        if (id<2) begin
          if (operand_valid[l][0] && operand_ready[l][0]) seed_sent[l][id]++;
          if (operand_valid[l][kind==0 ? 2 : 1] && operand_ready[l][kind==0 ? 2 : 1]) sent[l][id]++;
          if (state[l]==3 && rounds_left[l]==Rounds && rx_valid[l] && rx_ready[l]) begin
            snapshots[l][id]++;
            if ((|activity)!==active[id]) $fatal(1,"First RX barrier incomplete case=%0d lane=%0d",cid,l);
          end
        end
        for (int i=0;i<2;i++) if (done[l][i]) completed[l][i]++;
        if (flags_valid[l]) begin
          id=int'(flag_id[l]);
          if (id>=2) $fatal(1,"Flag ownership outside pair");
          flag_count[l][id]++;
          if (flags[l]!==expected_flags(id,l)) flag_errors++;
        end
        if (result_req[l] && result_gnt[l]) begin
          id=int'(result_id[l]);
          if (l!=0 || id>=2 || result_addr[l]!=vaddr(24+id,N,VLEN) ||
              result_be[l]!=be(1,width==16 ? EW16 : width==32 ? EW32 : EW64))
            $fatal(1,"Unexpected result target");
          observed[id]=width==64 ? result[l] : result[l]&((64'b1<<width)-1);
          if (observed[id]!==expected(id)) data_errors++;
          writes[id]++;
        end
        $fdisplay(trace_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%02h,%0d,%02h,%0d,%0d,%016h,%0d",
          cid,cycle,l,state[l],next_state[l],issue_id[l],first[l],in_valid[l],in_ready[l],
          activity[l],|activity,rounds_left[l],rx_valid[l],rx_ready[l],snapshot[l],pending[l],
          flags_valid[l],flags[l],result_req[l],result_gnt[l],result[l],|done[l]);
      end
    end
  end

  task automatic run_pair;
    int steps;
    bit all_done;
    @(negedge clk); running=0; req=0; operand_valid=0;
    requested='{default:0}; sent='{default:'{default:0}}; seed_sent='{default:'{default:0}};
    completed='{default:'{default:0}}; flag_count='{default:'{default:0}};
    snapshots='{default:'{default:0}}; writes='{default:0}; observed='{default:0};
    stage=0; overlap=0; data_errors=0; flag_errors=0; sticky=0;
    active[0]=scenario[1]; active[1]=scenario[0];
    start_cycle=cycle; running=1; all_done=0;
    for (steps=0;steps<2000 && !all_done;steps++) begin
      drive(); @(negedge clk); all_done=1;
      for (int l=0;l<N;l++) if (completed[l][1]!=1) all_done=0;
    end
    req=0; operand_valid=0; repeat(6) @(negedge clk);
    if (!all_done || stage!=2*Rounds || |tx_valid || |response_valid || overlap!=N)
      $fatal(1,"Pair transport/completion case=%0d stage=%0d overlap=%0d",cid,stage,overlap);
    for (int l=0;l<N;l++)
      for (int i=0;i<2;i++)
        if (requested[l]!=2 || completed[l][i]!=1 || flag_count[l][i]!=1 ||
            seed_sent[l][i]!=1 || snapshots[l][i]!=1)
          $fatal(1,"Pair accounting case=%0d lane=%0d op=%0d",cid,l,i);
    if (writes[0]!=1 || writes[1]!=1) $fatal(1,"Pair write count");
    if (sticky!==(expected_flags(0,0)|expected_flags(1,0))) flag_errors++;
    $fdisplay(results_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%016h,%016h,%02h,%0d,%0d,%0d",
      cid,N,width,kind,scenario,gap,seed_mode,overlap,observed[0],observed[1],sticky,data_errors,flag_errors,cycle-start_cycle);
    if (data_errors || flag_errors) failures++;
    running=0; cid++;
  endtask
  initial begin
    req=0; operand_valid=0;
    trace_fd=$fopen("trace.csv","w"); results_fd=$fopen("results.csv","w");
    $fdisplay(trace_fd,"case,cycle,lane,state,next_state,id,first,in_valid,in_ready,activity,global,rounds,rx_valid,rx_ready,snapshot,pending,flag_valid,flags,result_req,result_gnt,result,done");
    $fdisplay(results_fd,"id,lanes,width,kind,scenario,gap,seed_mode,overlap,result0,result1,flags,data_errors,flag_errors,cycles");
    if ($test$plusargs("FSDB")) begin $fsdbDumpfile("epoch.fsdb"); $fsdbDumpvars(1,epoch_tb); end
    repeat(4) @(negedge clk); rst_n=1;
    for (width=16;width<=64;width*=2)
      for (kind=0;kind<3;kind++)
        for (scenario=0;scenario<4;scenario++)
          for (gap=0;gap<2;gap++)
            for (seed_mode=0;seed_mode<2;seed_mode++) run_pair();
    $display("EPOCH_COMPLETE N=%0d cases=%0d failed=%0d",N,cid,failures);
    $fclose(trace_fd); $fclose(results_fd); $finish;
  end
  initial begin #20000000; $fatal(1,"Timeout"); end
endmodule
