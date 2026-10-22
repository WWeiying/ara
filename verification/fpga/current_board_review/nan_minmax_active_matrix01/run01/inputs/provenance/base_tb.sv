`timescale 1ns/1ps
module reduction_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import fpnew_pkg::*;
  localparam int N=4, VLEN=1024;
  localparam config_pkg::cva6_cfg_t Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
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
  typedef struct packed {
    vew_e eew; vlen_t elem_count; opqueue_conversion_e conv;
    logic [1:0] ntr_red; logic is_reduct; target_fu_e target_fu;
  } queue_cmd_t;
  logic clk=0, rst_n=0, running=0;
  always #5 clk=~clk;
  operation_t [N-1:0] op;
  queue_cmd_t [N-1:0][1:0] qcmd;
  elen_t [N-1:0][1:0] qin, qout;
  logic [N-1:0][1:0] qpush, qvalid, qready, qconsume, qcmd_valid, qpop;
  elen_t [N-1:0][2:0] operand;
  logic [N-1:0][2:0] operand_valid, operand_ready;
  logic [N-1:0] req, ready, result_req, result_gnt, red_valid, red_ready;
  logic [N-1:0] slide_valid, slide_ready, flags_valid, any_active;
  logic [N-1:0][NrVInsn-1:0] done;
  logic [N-1:0][7:0] mask, result_be;
  logic [N-1:0][4:0] flags;
  elen_t [N-1:0] result, slide_data;
  vaddr_t [N-1:0] result_addr;
  vid_t [N-1:0] result_id;
  elen_t [N-1:0] tx_data, response_data;
  logic [N-1:0] tx_valid, tx_ready, response_valid;
  int cycle=0, cid=-1, trace_fd, results_fd, count=0;
  int vl, sw, dw, kind, pattern, gap, rm, prior, pos_idx, neg_idx;
  int fed[N], consumed[N], seeds[N], accepts[N], dones[N], cmdpops[N][2];
  int fpins[N], fpouts[N], flag_events[N], masks[N];
  int stage, tokens, captured, writes, start_cycle;
  logic [4:0] accrued;
  elen_t seed_bits, observed, expected_bits;
  logic [N-1:0] done_seen;
  logic [N-1:0] next_queued, next_done, next_push, ordinary_out_q;
  int next_mode, next_writes, next_flags, next_accepts[N];
  logic [4:0] at_reduction_done, ordinary_accrued;
  bit captured_done_flags;
  logic [511:0] predicate;
  bit ordered, vm, wide;
  vew_e sew, dew;

  // This profile exposes only the relevant conversion, scheduling and flag path.
  logic [N-1:0][2:0] state;
  logic [N-1:0] source_enable, first, filling, in_valid, in_ready, out_valid, out_ready;
  logic [N-1:0][7:0] issue_be, tag_in, tag_out, control_in, control_out;
  logic [N-1:0][4:0] raw, collapsed, gated;
  logic [N-1:0][3:0][4:0] raw_slots;
  logic [N-1:0][10:0] source_count, issue_count, process_count;
  elen_t [N-1:0] a, b, c, fp_result;
  for (genvar l=0; l<N; l++) begin: lanes
    for (genvar q=0; q<2; q++) begin: queues
      operand_queue #(.NrLanes(N), .VLEN(VLEN), .DataBufDepth(4),
        .SupportIntExt2(1), .SupportReduct(1), .SupportNtrVal(1), .AccessCmdPop(1),
        .operand_queue_cmd_t(queue_cmd_t)) oq (
        .clk_i(clk), .rst_ni(rst_n), .flush_i(1'b0), .lane_id_i(2'(l)),
        .operand_queue_cmd_i(qcmd[l][q]), .operand_queue_cmd_valid_i(qcmd_valid[l][q]),
        .cmd_pop_o(qpop[l][q]), .operand_i(qin[l][q]), .operand_valid_i(qpush[l][q]),
        .operand_issued_i(qpush[l][q]), .operand_queue_ready_o(qready[l][q]),
        .operand_o(qout[l][q]), .operand_target_fu_o(), .operand_valid_o(qvalid[l][q]),
        .operand_ready_i(qconsume[l][q]));
    end
    assign operand[l] = kind>=2 ? {64'b0, qout[l][1], qout[l][0]} :
                                 {qout[l][1], 64'b0, qout[l][0]};
    assign operand_valid[l] = kind>=2 ? {1'b0, qvalid[l][1], qvalid[l][0]} :
                                       {qvalid[l][1], 1'b0, qvalid[l][0]};
    assign qconsume[l] = {operand_ready[l][kind>=2 ? 1 : 2], operand_ready[l][0]};
    vmfpu #(.NrLanes(N), .VLEN(VLEN), .CVA6Cfg(Cfg), .vaddr_t(vaddr_t),
      .vfu_operation_t(operation_t)) dut (
      .clk_i(clk), .rst_ni(rst_n), .lane_id_i(2'(l)), .mfpu_vxsat_o(), .mfpu_vxrm_i('0),
      .fflags_ex_o(flags[l]), .fflags_ex_valid_o(flags_valid[l]),
      .vfu_operation_i(op[l]), .vfu_operation_valid_i(req[l]), .mfpu_ready_o(ready[l]),
      .mfpu_vinsn_done_o(done[l]), .fpu_red_complete_o(), .reduction_any_active_o(any_active[l]),
      .reduction_global_any_active_i(|any_active), .mfpu_operand_i(operand[l]),
      .mfpu_operand_valid_i(operand_valid[l]), .mfpu_operand_ready_o(operand_ready[l]),
      .mfpu_result_req_o(result_req[l]), .mfpu_result_id_o(result_id[l]),
      .mfpu_result_addr_o(result_addr[l]), .mfpu_result_wdata_o(result[l]),
      .mfpu_result_be_o(result_be[l]), .mfpu_result_gnt_i(result_gnt[l]),
      .mfpu_red_valid_o(red_valid[l]), .mfpu_red_ready_i(red_ready[l]),
      .sldu_operand_i(slide_data[l]), .sldu_mfpu_valid_i(slide_valid[l]),
      .sldu_mfpu_ready_o(slide_ready[l]), .mask_operand_o(), .mask_operand_valid_o(),
      .mask_operand_ready_i(1'b1), .mask_i(mask[l]), .mask_valid_i(qvalid[l][1]), .mask_ready_o());
    spill_register #(.T(elen_t)) tx_buffer (.clk_i(clk), .rst_ni(rst_n),
      .data_i(result[l]), .valid_i(red_valid[l]), .ready_o(red_ready[l]),
      .data_o(tx_data[l]), .valid_o(tx_valid[l]), .ready_i(tx_ready[l]));
    assign state[l]=dut.mfpu_state_q;
    assign source_enable[l]=dut.intra_op_rx_cnt_en;
    assign source_count[l]=dut.intra_op_rx_cnt_q;
    assign issue_count[l]=dut.issue_cnt_q;
    assign process_count[l]=dut.to_process_cnt_q;
    assign first[l]=dut.first_op_q;
    assign filling[l]=dut.ntr_filling_q;
    assign issue_be[l]=dut.issue_be;
    assign tag_in[l]=dut.vfpu_tag_in.flag_mask;
    assign tag_out[l]=dut.vfpu_tag_out.flag_mask;
    assign control_in[l]=dut.vfpu_tag_in.control;
    assign control_out[l]=dut.vfpu_tag_out.control;
    assign in_valid[l]=dut.vfpu_in_valid;
    assign in_ready[l]=dut.vfpu_in_ready;
    assign out_valid[l]=dut.vfpu_out_valid;
    assign out_ready[l]=dut.vfpu_out_ready;
    assign a[l]=dut.operand_a;
    assign b[l]=dut.operand_b;
    assign c[l]=dut.operand_c;
    assign fp_result[l]=dut.vfpu_result;
    assign collapsed[l]=dut.vfpu_ex_flag_fn;
    assign gated[l]=dut.vfpu_ex_flag;
    always_ff @(posedge clk or negedge rst_n) begin
      if (!rst_n) ordinary_out_q[l]<=0;
      else ordinary_out_q[l]<=dut.vinsn_processing_q.op==VFADD && out_valid[l] && out_ready[l];
    end
    wire [4:0] add64 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[1].active_format.i_fmt_slice.lane_status[0];
    wire [4:0] add32 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.lane_status[0];
    wire [4:0] add16 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.lane_status[0];
    wire [4:0] non64 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[1].active_format.i_fmt_slice.lane_status[0];
    wire [4:0] non32 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.lane_status[0];
    wire [4:0] non16 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.lane_status[0];
    assign raw[l] = kind >= 2 ? (dw==64 ? non64 : dw==32 ? non32 : non16) :
                               (dw==64 ? add64 : dw==32 ? add32 : add16);
    for (genvar s=0;s<4;s++) begin: raw_probe
      wire [4:0] a16 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.lane_status[s];
      wire [4:0] n16 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.lane_status[s];
      if (s<2) begin
        wire [4:0] a32 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.lane_status[s];
        wire [4:0] n32 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.lane_status[s];
        assign raw_slots[l][s] = dw==16 ? (kind>=2 ? n16 : a16) :
                                dw==32 ? (kind>=2 ? n32 : a32) : s==0 ? raw[l] : 5'b0;
      end else assign raw_slots[l][s] = dw==16 ? (kind>=2 ? n16 : a16) : 5'b0;
    end
  end

  function automatic elen_t integer_bits(int number, int width);
    int exponent, fraction, bias;
    exponent=0; fraction=width==64 ? 52 : width==32 ? 23 : 10;
    bias=width==64 ? 1023 : width==32 ? 127 : 15;
    if (!number) return 0;
    while ((1 << (exponent+1)) <= number) exponent++;
    return (64'(bias+exponent) << fraction) | (64'(number-(1<<exponent)) << (fraction-exponent));
  endfunction
  function automatic elen_t source_bits(int index);
    elen_t inf;
    inf=sw==32 ? 64'h7f800000 : sw==16 ? 64'h7c00 : 64'h7ff0000000000000;
    if (pattern==1 && index==pos_idx) return inf;
    if (pattern==1 && index==neg_idx) return inf | (64'h1 << (sw-1));
    if (pattern==2 || (pattern==3 && index!=pos_idx)) return inf | 1;
    return integer_bits(1+index%7, sw);
  endfunction
  task automatic drive;
    int index, offset;
    elen_t value;
    qpush='0; qin='0; mask='0; next_push='0; req='0; qcmd_valid='0;
    for (int l=0;l<N;l++) begin
      if (seeds[l]==0 && qready[l][0]) begin qpush[l][0]=1; qin[l][0]=seed_bits; end
      if (fed[l] < (((vl+N-1-l)/N)+(64/sw)-1)/(64/sw) && qready[l][1] &&
          (gap==0 || cycle%7==0)) begin
        qpush[l][1]=1;
        for (int e=0;e<64/sw;e++) begin
          index=(fed[l]*(64/sw)+e)*N+l;
          value=source_bits(index);
          for (int j=0;j<sw/8;j++) begin
            offset=shuffle_index(16'(e*sw/8+j),1,sew);
            qin[l][1][8*offset +: 8]=value[8*j +: 8];
          end
        end
      end
      for (int e=0;e<64/dw;e++) begin
        index=(consumed[l]+e)*N+l;
        for (int j=0;j<dw/8;j++) begin
          offset=shuffle_index(16'(e*dw/8+j),1,dew);
          mask[l][offset]=index<vl && predicate[index];
        end
      end
      if (next_mode && !next_queued[l] && consumed[l]==(vl+N-1-l)/N &&
          qready[l][0] && qready[l][1] && ready[l]) begin
        // Queue an ordinary instruction while the reduction still owns FPnew.
        op[l].id=1; op[l].op=VFADD; op[l].vm=1; op[l].vl=1; op[l].vd=25;
        op[l].vtype.vsew=EW64; op[l].cvt_resize=CVT_SAME;
        op[l].swap_vs2_vd_op=1;
        req[l]=1; qcmd_valid[l]='1; qpush[l]='1; next_push[l]=1;
        qcmd[l][0]='{eew:EW64,elem_count:1,conv:OpQueueConversionNone,
          ntr_red:0,is_reduct:0,target_fu:MFPU_ADDRGEN};
        qcmd[l][1]=qcmd[l][0];
        qin[l][0]=next_mode==2 ? 64'h7ff0000000000000 : 64'h4000000000000000;
        qin[l][1]=next_mode==2 && l==1 ? 64'hfff0000000000000 : 64'h3ff0000000000000;
      end
    end
  endtask

  // Buffered rotation tree: strides 1,2,1; final lane-3 aggregate returns to lane 0.
  always_comb begin
    tx_ready='0; slide_valid='0; slide_data='0;
    result_gnt=running ? result_req : '0;
    if (running) begin
      if (ordered && tokens<vl) begin
        slide_data[tokens==vl-1 ? 0 : (tokens+1)%N]=tx_data[tokens%N];
        slide_valid[tokens==vl-1 ? 0 : (tokens+1)%N]=tx_valid[tokens%N];
        tx_ready[tokens%N]=slide_ready[tokens==vl-1 ? 0 : (tokens+1)%N];
      end else if (!ordered) begin
        slide_valid=response_valid;
        slide_data=response_data;
        if (stage<3 && !(|response_valid) && &tx_valid) tx_ready='1;
      end
    end
  end
  always @(posedge clk) begin
    cycle<=cycle+1;
    if (!rst_n) begin response_valid<='0; response_data<='0; end
    else if (running) begin
      // Match ara_dispatcher: valid is ORed, but data is ORed without lane gating.
      if (|flags_valid) begin
        accrued |= flags[0] | flags[1] | flags[2] | flags[3];
        if (|(flags_valid & ordinary_out_q))
          ordinary_accrued |= flags[0] | flags[1] | flags[2] | flags[3];
      end
      response_valid<=response_valid & ~slide_ready;
      if (!ordered && &tx_ready) begin
        for (int l=0;l<N;l++) response_data[l]<=tx_data[(l+N-(stage==1 ? 2 : 1))%N];
        response_valid<='1; stage<=stage+1;
      end
      tokens<=tokens+$countones(tx_valid & tx_ready);
      captured+=$countones(red_valid & red_ready);
      for (int l=0;l<N;l++) begin
        if (next_push[l]) next_queued[l]=1;
        if (qpush[l][0] && !next_push[l]) seeds[l]++;
        if (qpush[l][1] && !next_push[l]) fed[l]++;
        if (qvalid[l][1] && qconsume[l][1]) begin
          consumed[l]+= (64/dw < (vl+N-1-l)/N-consumed[l]) ? 64/dw : (vl+N-1-l)/N-consumed[l];
        end
        for (int q=0;q<2;q++) if (qpop[l][q]) cmdpops[l][q]++;
        if (req[l] && ready[l]) begin
          if (op[l].id==0) accepts[l]++;
          else begin
            if (done_seen[l]) $fatal(1,"HARNESS ordinary request was not queued before reduction done");
            next_accepts[l]++;
          end
        end
        if (in_valid[l] && in_ready[l]) fpins[l]++;
        if (out_valid[l] && out_ready[l]) fpouts[l]++;
        if (flags_valid[l]) begin
          if ($test$plusargs("DEFERRED_FLAGS") && done_seen[l] && !ordinary_out_q[l])
            $fatal(1,"HARNESS late flag pulse after local done lane=%0d",l);
          if (ordinary_out_q[l]) next_flags++;
          else flag_events[l]++;
        end
        if (done[l][0]) begin dones[l]++; done_seen[l]=1; end
        if (done[l][1]) next_done[l]=1;
        if (result_req[l] && result_gnt[l]) begin
          if (result_id[l]==1 && next_mode) begin
            if (result_addr[l]!=vaddr(25,N,VLEN) || result_be[l]!=8'hff ||
                result[l] !== (next_mode==1 ? 64'h4008000000000000 :
                               l==1 ? 64'h7ff8000000000000 : 64'h7ff0000000000000))
              $fatal(1,"HARNESS queued ordinary write mismatch lane=%0d",l);
            next_writes++;
          end else begin
          if (l!=0 || result_id[l]!=0 || result_addr[l]!=vaddr(24,N,VLEN) || result_be[l]!=be(1,dew))
            $fatal(1,"HARNESS wrong write target lane=%0d",l);
          observed=result[l]; writes++;
          end
        end
        $fdisplay(trace_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%02h,%016h,%016h,%016h,%016h,%02h,%02h,%02h,%0d,%0d,%0d,%0d,%02h,%02h,%02h,%02h,%02h,%016h,%0d,%02h,%0d,%0d,%0d,%0d,%05h",
          cid,cycle,l,state[l],source_enable[l],source_count[l],issue_count[l],process_count[l],first[l],filling[l],mask[l],qout[l][1],a[l],b[l],c[l],issue_be[l],tag_in[l],control_in[l],in_valid[l],in_ready[l],out_valid[l],out_ready[l],tag_out[l],control_out[l],raw[l],collapsed[l],gated[l],fp_result[l],flags_valid[l],flags[l],any_active[l],red_valid[l]&&red_ready[l],slide_valid[l]&&slide_ready[l],|done[l],raw_slots[l]);
      end
      if (&done_seen && !captured_done_flags) begin
        at_reduction_done=accrued; captured_done_flags=1;
      end
    end
  end

  task automatic run_case(input int id, input string name, input int srcwidth, dstwidth,
      length, opcode, data_pattern, positive_index, negative_index, input logic [511:0] pred,
      input bit unmasked, input elen_t initial_seed, input int delay_source, roundmode, sticky,
      input elen_t expected, input logic [4:0] expected_flags, input int queued_mode=0);
    int steps, expected_events;
    elen_t bitmask;
    @(negedge clk); running=0; rst_n=id==0 ? 0 : rst_n; req='0; qcmd_valid='0; qpush='0;
    cid=id; sw=srcwidth; dw=dstwidth; vl=length; kind=opcode; pattern=data_pattern;
    pos_idx=positive_index; neg_idx=negative_index; predicate=pred; vm=unmasked;
    seed_bits=initial_seed; gap=delay_source; rm=roundmode; prior=sticky;
    sew=sw==32 ? EW32 : sw==16 ? EW16 : EW64;
    dew=dw==32 ? EW32 : dw==16 ? EW16 : EW64;
    wide=sw!=dw; ordered=kind==1; observed='x; accrued=5'(sticky);
    next_mode=queued_mode; next_queued='0; next_done='0; next_push='0;
    next_writes=0; next_flags=0; ordinary_accrued=0; captured_done_flags=0;
    writes=0; tokens=0; captured=0; stage=0; done_seen=0;
    op='0; qcmd='0;
    for (int l=0;l<N;l++) begin
      fed[l]=0; consumed[l]=0; seeds[l]=0; accepts[l]=0; dones[l]=0;
      next_accepts[l]=0;
      fpins[l]=0; fpouts[l]=0; flag_events[l]=0;
      for (int q=0;q<2;q++) cmdpops[l][q]=0;
      op[l].op=kind==2 ? VFREDMIN : kind==3 ? VFREDMAX : ordered ?
        (wide ? VFWREDOSUM : VFREDOSUM) : (wide ? VFWREDUSUM : VFREDUSUM);
      op[l].vm=vm; op[l].use_vs1=1; op[l].use_vs2=1; op[l].swap_vs2_vd_op=kind<2;
      op[l].cvt_resize=resize_e'(kind==2 ? 1 : kind==3 ? 2 : 0);
      op[l].use_vd=1; op[l].vd=24; op[l].vfu=VFU_MFpu;
      op[l].fp_rm=roundmode_e'(rm); op[l].vtype.vsew=dew; op[l].vtype.vlmul=LMUL_8;
      op[l].vl=vlen_t'((vl+N-1-l)/N);
      qcmd[l][0]='{eew:dew, elem_count:1, conv:OpQueueReductionZExt,
        ntr_red:2'(kind==2 ? 1 : kind==3 ? 2 : 0), is_reduct:1, target_fu:MFPU_ADDRGEN};
      qcmd[l][1]='{eew:sew, elem_count:vlen_t'((vl+N-1-l)/N),
        conv:wide ? OpQueueConversionWideFP2 : OpQueueConversionNone,
        ntr_red:2'(kind==2 ? 1 : kind==3 ? 2 : 0), is_reduct:1, target_fu:MFPU_ADDRGEN};
    end
    repeat (4) @(negedge clk);
    rst_n=1; running=1; start_cycle=cycle; req='1; qcmd_valid='1;
    @(negedge clk); req='0; qcmd_valid='0;
    for (steps=0;steps<2000 && (done_seen!='1 || (next_mode && next_done!='1));steps++) begin drive(); @(negedge clk); end
    if (done_seen!='1) $fatal(1,"HARNESS timeout case=%s stage=%0d tokens=%0d",name,stage,tokens);
    repeat (12) begin drive(); @(negedge clk); end
    if (writes!=1 || tokens!=(ordered ? vl : 12) || captured!=tokens || |tx_valid || |response_valid)
      $fatal(1,"HARNESS transport count case=%s writes=%0d tokens=%0d captured=%0d",name,writes,tokens,captured);
    for (int l=0;l<N;l++) begin
      expected_events=$test$plusargs("DEFERRED_FLAGS") && !ordered ? 1 : fpouts[l]-(next_mode!=0);
      if (accepts[l]!=1 || dones[l]!=1 || seeds[l]!=1 || cmdpops[l][0]!=1+(next_mode!=0) || cmdpops[l][1]!=1+(next_mode!=0) ||
          consumed[l]!=(vl+N-1-l)/N || fpins[l]!=fpouts[l] || expected_events!=flag_events[l])
        $fatal(1,"HARNESS lane accounting case=%s lane=%0d consumed=%0d fp=%0d/%0d flags=%0d",name,l,consumed[l],fpins[l],fpouts[l],flag_events[l]);
    end
    if (next_mode) begin
      if (next_done!='1 || next_writes!=N || next_flags!=N ||
          ordinary_accrued !== (next_mode==2 ? 5'h10 : 5'h00))
        $fatal(1,"HARNESS queued ordinary flags/counts case=%s flags=%02h writes=%0d events=%0d",name,ordinary_accrued,next_writes,next_flags);
      for (int l=0;l<N;l++) if (next_accepts[l]!=1) $fatal(1,"HARNESS missing queued request");
      accrued=at_reduction_done;
    end
    bitmask=dw==64 ? '1 : (64'h1<<dw)-1;
    $fdisplay(results_fd,"%0d,%s,%016h,%02h,%016h,%02h,%0d,%0d,%0d",id,name,observed&bitmask,accrued,expected,expected_flags,(observed&bitmask)===expected,accrued===expected_flags,cycle-start_cycle);
    $display("RESULT %s result=%016h flags=%02h expected=%016h/%02h match=%0d/%0d cycles=%0d",name,observed&bitmask,accrued,expected,expected_flags,(observed&bitmask)===expected,accrued===expected_flags,cycle-start_cycle);
    count++; running=0;
  endtask
  initial begin
    trace_fd=$fopen("trace.csv","w"); results_fd=$fopen("results.csv","w");
    $fdisplay(trace_fd,"case_id,cycle,lane,state,source_enable,source_count,issue_count,process_count,first,filling,mask,converted,a,b,c,issue_be,in_tag,in_control,in_valid,in_ready,out_valid,out_ready,out_tag,out_control,raw_status,collapsed_status,gated_status,result,flags_valid,flags,any_active,red_fire,slide_fire,done,raw_slots");
    $fdisplay(results_fd,"id,name,result,flags,expected_result,expected_flags,result_match,flags_match,cycles");
    if ($test$plusargs("FSDB")) begin $fsdbDumpfile("reduction.fsdb"); $fsdbDumpvars(1,reduction_tb); end
    `include "cases.svh"
    $display("REDUCTION_COMPLETE cases=%0d",count);
    $fclose(trace_fd); $fclose(results_fd); $finish;
  end
  initial begin #20000000; $fatal(1,"HARNESS global timeout"); end
endmodule
