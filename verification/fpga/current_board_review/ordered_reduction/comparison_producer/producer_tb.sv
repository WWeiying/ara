`timescale 1ns/1ps
module producer_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import fpnew_pkg::*;
  localparam int N=4, VLEN=1024, Words=12;
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
  logic clk=0, rst_n=0, running=0;
  always #5 clk=~clk;
  operation_t op;
  elen_t [2:0] operands;
  logic [2:0] operand_valid, operand_ready;
  logic request, ready, result_req, result_gnt, payload_valid, payload_ready;
  logic [NrVInsn-1:0] done;
  elen_t result, payload;
  logic [7:0] result_be;
  vid_t result_id;
  vaddr_t result_addr;
  logic [4:0] flags;
  logic flags_valid;
  int cycle=0, cid, width, kind, scalar, stalls, start_cycle;
  int sent_a, sent_b, accepted, completed, flag_events, fp_in, fp_out, received;
  int data_errors, nv_errors, raw_errors, tag_errors, flag_data_errors, stall_cycles, total=0;
  int case_fd, result_fd, trace_fd, parsed;
  logic [4:0] expected_flags, accrued;
  logic [63:0] scalar_bits, word_a[Words], word_b[Words], expected[Words];
  logic [7:0] expected_nv[Words];
  logic [63:0] held_payload;
  logic held_valid;
  bit cmp, reciprocal;

  vmfpu #(.NrLanes(N), .VLEN(VLEN), .CVA6Cfg(Cfg), .FPUSupport(FPUSupportAll),
    .vaddr_t(vaddr_t), .vfu_operation_t(operation_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .lane_id_i(2'd1), .mfpu_vxsat_o(), .mfpu_vxrm_i('0),
    .fflags_ex_o(flags), .fflags_ex_valid_o(flags_valid),
    .vfu_operation_i(op), .vfu_operation_valid_i(request), .mfpu_ready_o(ready),
    .mfpu_vinsn_done_o(done), .fpu_red_complete_o(), .reduction_any_active_o(),
    .reduction_global_any_active_i(1'b0), .mfpu_operand_i(operands),
    .mfpu_operand_valid_i(operand_valid), .mfpu_operand_ready_o(operand_ready),
    .mfpu_result_req_o(result_req), .mfpu_result_id_o(result_id),
    .mfpu_result_addr_o(result_addr), .mfpu_result_wdata_o(result),
    .mfpu_result_be_o(result_be), .mfpu_result_gnt_i(result_gnt),
    .mfpu_red_valid_o(), .mfpu_red_ready_i(1'b0), .sldu_operand_i('0),
    .sldu_mfpu_valid_i(1'b0), .sldu_mfpu_ready_o(),
    .mask_operand_o(payload), .mask_operand_valid_o(payload_valid),
    .mask_operand_ready_i(payload_ready), .mask_i(8'h00), .mask_valid_i(1'b0), .mask_ready_o());

  wire [7:0] issue_be = dut.issue_be;
  wire [7:0] tag_in = dut.vfpu_tag_in.flag_mask;
  wire [7:0] tag_out = dut.vfpu_tag_out.flag_mask;
  wire [63:0] tag_a_in = dut.vfpu_tag_in.operand_a;
  wire [63:0] tag_a_out = dut.vfpu_tag_out.operand_a;
  wire [63:0] fp_a = dut.operand_a, fp_b = dut.operand_b;
  wire [63:0] fp_result = dut.vfpu_result;
  wire [4:0] raw_flags = dut.vfpu_ex_flag_fn, processed_flags = dut.vfpu_ex_flag;
  wire [39:0] raw8 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[3].active_format.i_fmt_slice.lane_status;
  wire [19:0] raw16 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.lane_status;
  wire [9:0] raw32 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.lane_status;
  wire [4:0] raw64 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[2].i_opgroup_block.gen_parallel_slices[1].active_format.i_fmt_slice.lane_status;
  wire [39:0] raw_slots = width==8 ? raw8 : width==16 ? {20'b0,raw16} :
                         width==32 ? {30'b0,raw32} : {35'b0,raw64};

  function automatic ara_op_e opcode(int k);
    case(k)
      0:return VMFEQ; 1:return VMFNE; 2:return VMFLT; 3:return VMFLE;
      4:return VMFGT; 5:return VMFGE; 6:return VFADD; 7:return VFMIN;
      8:return VFREC7; default:return VFRSQRT7;
    endcase
  endfunction

  task automatic drive;
    operands='0; operand_valid='0;
    if (sent_a<Words) begin
      operands[kind==6 ? 2 : 1]=word_a[sent_a];
      operand_valid[kind==6 ? 2 : 1]=!stalls || cycle%5!=1;
    end
    if (!scalar && !reciprocal && sent_b<Words) begin
      operands[0]=word_b[sent_b];
      operand_valid[0]=!stalls || cycle%3!=1;
    end
    payload_ready=!stalls || (cycle-start_cycle>30 && cycle%7<3);
    result_gnt=result_req && (!stalls || (cycle-start_cycle>30 && cycle%7<3));
  endtask

  always @(posedge clk) begin
    cycle<=cycle+1;
    if (running && rst_n) begin
      if (request && ready) accepted++;
      if (operand_valid[kind==6 ? 2 : 1] && operand_ready[kind==6 ? 2 : 1]) sent_a++;
      if (operand_valid[0] && operand_ready[0]) sent_b++;
      if (dut.vfpu_in_valid && dut.vfpu_in_ready) begin
        if (!cmp && tag_a_in !== fp_a) tag_errors++;
`ifdef COMPARE_METADATA
        if (cmp && tag_a_in !== {56'b0,expected_nv[fp_in]}) tag_errors++;
`endif
        fp_in++;
      end
      if (dut.vfpu_out_valid && dut.vfpu_out_ready) begin
        if (cmp)
          for (int e=0;e<64/width;e++)
            if (raw_slots[e*5+4] !== expected_nv[fp_out][e]) raw_errors++;
        fp_out++;
      end
      if (dut.vfpu_out_valid && !dut.vfpu_out_ready) stall_cycles++;
      if (flags_valid) begin accrued|=flags; flag_events++; end
      if (cmp && flags !== 0) flag_data_errors++;
      if (|done) completed++;
      if (held_valid && (!payload_valid || payload!==held_payload))
        $fatal(1,"Payload changed while stalled case=%0d",cid);
      held_valid=payload_valid && !payload_ready;
      held_payload=payload;
      if ((cmp && payload_valid && payload_ready) || (!cmp && result_req && result_gnt)) begin
        if (received>=Words) $fatal(1,"Extra output case=%0d",cid);
        if (cmp) begin
          for (int e=0;e<64/width;e++) begin
            if (payload[e*width] !== expected[received][e*width]) data_errors++;
            if (payload[e*width+2] !== expected_nv[received][e]) nv_errors++;
          end
        end else if (result!==expected[received] || result_id!=op.id || result_be!=8'hff ||
                     result_addr!=vaddr(24,N,VLEN)+received) data_errors++;
        received++;
      end
      $fdisplay(trace_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%016h,%016h,%02h,%02h,%016h,%0d,%0d,%02h,%016h,%010h,%02h,%02h,%016h,%0d,%02h,%0d,%0d,%016h,%0d",
        cid,cycle,width,kind,dut.vfpu_in_valid,dut.vfpu_in_ready,dut.fpnew_group_transition_stall,
        fp_a,fp_b,issue_be,tag_in,tag_a_in,dut.vfpu_out_valid,dut.vfpu_out_ready,tag_out,tag_a_out,
        raw_slots,raw_flags,processed_flags,fp_result,flags_valid,flags,payload_valid,payload_ready,payload,|done);
    end
  end

  task automatic run_case;
    int steps;
    sent_a=0; sent_b=0; accepted=0; completed=0; received=0; flag_events=0;
    fp_in=0; fp_out=0; data_errors=0; nv_errors=0; raw_errors=0; tag_errors=0;
    flag_data_errors=0; stall_cycles=0;
    accrued=0; held_valid=0; cmp=kind<6; reciprocal=kind>=8;
    op='0; op.id=vid_t'(cid%NrVInsn); op.op=opcode(kind);
    op.vm=!cmp; op.use_vs1=!scalar && !reciprocal; op.use_vs2=1;
    op.use_scalar_op=scalar; op.scalar_op=scalar_bits;
    op.swap_vs2_vd_op=kind==6; op.vfu=cmp ? VFU_MaskUnit : VFU_MFpu;
    op.use_vd=1; op.vd=24; op.fp_rm=RNE; op.cvt_resize=CVT_SAME;
    op.vtype.vsew=width==8 ? EW8 : width==16 ? EW16 : width==32 ? EW32 : EW64;
    op.vtype.vlmul=LMUL_8; op.vl=vlen_t'(Words*(64/width));
    @(negedge clk); running=1; start_cycle=cycle; request=1;
    do @(negedge clk); while (accepted==0);
    request=0;
    for (steps=0;steps<1000 && (received<Words || completed==0);steps++) begin
      drive(); @(negedge clk);
    end
    operand_valid=0; result_gnt=0; repeat(5) @(negedge clk);
    if (accepted!=1 || completed!=1 || received!=Words || sent_a!=Words ||
        (!scalar && !reciprocal && sent_b!=Words) || fp_in!=Words || fp_out!=Words)
      $fatal(1,"Accounting case=%0d accept=%0d done=%0d outputs=%0d sent=%0d/%0d FP=%0d/%0d",
        cid,accepted,completed,received,sent_a,sent_b,fp_in,fp_out);
    if (stalls && stall_cycles==0) $fatal(1,"No actual FP backpressure case=%0d",cid);
    $fdisplay(result_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%02h,%02h,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
      cid,width,kind,scalar,stalls,data_errors,nv_errors,accrued,expected_flags,
      flag_events,cmp ? 0 : Words,stall_cycles,cycle-start_cycle,raw_errors,tag_errors,flag_data_errors);
    $display("PRODUCER_CASE id=%0d data_errors=%0d nv_errors=%0d flags=%02h/%02h events=%0d/%0d",
      cid,data_errors,nv_errors,accrued,expected_flags,flag_events,cmp ? 0 : Words);
    running=0; total++;
  endtask

`ifdef COMPARE_METADATA
  logic [63:0] bank_a, bank_b;
  ara_op_e bank_op;
  task automatic check_banks;
    int w, m, eb, checks;
    logic [63:0] nan_bits;
    logic [7:0] want;
    checks=0;
    force dut.operand_a=bank_a;
    force dut.operand_b=bank_b;
    force dut.vinsn_issue_q.op=bank_op;
    for (int f=0;f<NUM_FP_FORMATS;f++) begin
      w=fp_width(fp_format_e'(f)); m=man_bits(fp_format_e'(f)); eb=exp_bits(fp_format_e'(f));
      for (int k=0;k<6;k++)
        for (int e=0;e<64/w;e++)
          for (int pattern=0;pattern<4;pattern++) begin
            bank_op=opcode(k); bank_a=0; bank_b=0;
            nan_bits=(((64'b1<<eb)-1)<<m) | (pattern%2 ? 64'b1<<(m-1) : 64'b1);
            if (pattern<2) bank_a=nan_bits<<(e*w); else bank_b=nan_bits<<(e*w);
            want=(k<2 && pattern%2) ? 0 : 8'b1<<e;
            #1;
            if (dut.fpu_gen.comparison_nv_by_fmt[f] !== want)
              $fatal(1,"Classification bank fmt=%0d op=%0d element=%0d pattern=%0d",f,k,e,pattern);
            checks++;
          end
    end
    release dut.operand_a; release dut.operand_b; release dut.vinsn_issue_q.op;
    $display("CLASSIFICATION_BANK_PASS checks=%0d (ALT bank only, no legal ALT issue selector)",checks);
  endtask

  function automatic logic [63:0] mixed_a(int id, int word_index);
    case (id)
      0: return word_index%2 ? 64'h7f8000013f800000 : 64'h3f8000007f800001;
      1: return word_index%2 ? 64'h3f8000003f800000 : 64'h3f8000007f800001;
      2: return word_index%2 ? 64'h7fc000003f800000 : 64'h3f8000007fc00000;
      3: return word_index%2 ? 64'h7f8000013f800000 : 64'h3f8000003f800000;
    endcase
  endfunction

  task automatic check_queued_mixed;
    localparam int W=6;
    int requested, sent[4], returned[4], stored[4], issue_id, process_id;
    int steps, cmp_received, id, word_index, overlap, blocked;
    logic [3:0] finished;
    logic prev_valid, prev_cmp;
    logic [4:0] prev_flags;
    logic [63:0] want_result;
    logic [63:0] held;
    logic held_stalled;
    requested=0; sent='{default:0}; returned='{default:0}; stored='{default:0};
    cmp_received=0; finished=0; overlap=0; blocked=0;
    prev_valid=0; prev_cmp=0; prev_flags=0; held_stalled=0;
    @(negedge clk);
    for (steps=0;steps<2000 && finished!=4'hf;steps++) begin
      request=requested<4;
      op='0; op.id=vid_t'(requested); op.vm=1;
      op.vtype.vsew=EW32; op.vtype.vlmul=LMUL_8; op.vl=2*W;
      op.use_vd=1; op.vd=24; op.use_vs2=1; op.fp_rm=RNE;
      op.vfu=VFU_MFpu; op.cvt_resize=CVT_SAME;
      case (requested)
        0: begin op.op=VMFLT; op.vm=0; op.vfu=VFU_MaskUnit; op.use_vs1=1; end
        1: begin op.op=VFADD; op.use_vs1=1; op.swap_vs2_vd_op=1; end
        2: begin op.op=VMFEQ; op.vm=0; op.vfu=VFU_MaskUnit; op.use_vs1=1; end
        default: op.op=VFREC7;
      endcase
      operands=0; operand_valid=0;
      issue_id=int'(dut.vinsn_issue_q.id);
      if (dut.vinsn_issue_q_valid && issue_id<4 && sent[issue_id]<W) begin
        operands[issue_id==1 ? 2 : 1]=mixed_a(issue_id,sent[issue_id]);
        operand_valid[issue_id==1 ? 2 : 1]=steps%5!=1;
        if (issue_id!=3) begin
          operands[0]=issue_id==2 ? 64'h3f8000003f800000 : 64'h4000000040000000;
          operand_valid[0]=steps%5!=1;
        end
      end
      payload_ready=steps>40 && steps%7<3;
      result_gnt=result_req && steps>40 && steps%7<3;
      @(posedge clk);
      if (flags_valid !== prev_valid || ((prev_valid || prev_cmp) && flags !== prev_flags))
        $fatal(1,"Queued flag ownership step=%0d flags=%b/%02h expected=%b/%02h",
               steps,flags_valid,flags,prev_valid,prev_flags);
      prev_cmp=dut.vinsn_processing_q.op inside {[VMFEQ:VMFGE]};
      prev_valid=dut.vfpu_out_valid && dut.vfpu_out_ready && !prev_cmp;
      prev_flags=0;
      process_id=int'(dut.vinsn_processing_q.id);
      if (dut.vfpu_out_valid && dut.vfpu_out_ready) begin
        if (process_id>=4 || returned[process_id]>=W) $fatal(1,"Queued extra FP output");
        if (prev_valid && ((process_id==1 && returned[process_id]%2==0) ||
                           (process_id==3 && returned[process_id]%2==1))) prev_flags=16;
        returned[process_id]++;
      end
      if (request && ready) begin
        if (requested>0 && !finished[requested-1]) overlap++;
        requested++;
      end
      if (|done) begin
        if (|(finished & done[3:0])) $fatal(1,"Queued duplicate completion");
        finished|=done[3:0];
      end
      if (dut.vfpu_in_valid && dut.vfpu_in_ready) sent[issue_id]++;
      if (dut.vfpu_out_valid && !dut.vfpu_out_ready) blocked++;
      if (held_stalled && (!payload_valid || payload!==held)) $fatal(1,"Queued stalled payload changed");
      held_stalled=payload_valid && !payload_ready; held=payload;
      if (payload_valid && payload_ready) begin
        id=cmp_received<W ? 0 : 2; word_index=cmp_received%W;
        if (cmp_received>=2*W) $fatal(1,"Queued extra comparison output");
        for (int e=0;e<2;e++) begin
          if (payload[e*32] !== (e!=word_index%2) ||
              payload[e*32+2] !== (id==0 && e==word_index%2))
            $fatal(1,"Queued comparison payload word=%0d data=%h",cmp_received,payload);
        end
        stored[id]++; cmp_received++;
      end
      if (result_req && result_gnt) begin
        id=int'(result_id); word_index=stored[id];
        if (!(id inside {1,3}) || word_index>=W) $fatal(1,"Queued extra VRF output");
        if (id==1) want_result=word_index%2 ? 64'h4040000040400000 : 64'h404000007fc00000;
        else want_result=word_index%2 ? 64'h7fc000003f7f0000 : 64'h3f7f00003f7f0000;
        if (result !== want_result || result_be!=8'hff || result_addr!=vaddr(24,N,VLEN)+word_index)
          $fatal(1,"Queued ordinary output id=%0d word=%0d actual=%h expected=%h",id,word_index,result,want_result);
        stored[id]++;
      end
      @(negedge clk);
    end
    request=0; operand_valid=0; result_gnt=0;
    if (finished!=4'hf || requested!=4 || overlap==0 || blocked==0)
      $fatal(1,"Queued completion/overlap/backpressure failed");
    for (int i=0;i<4;i++)
      if (sent[i]!=W || returned[i]!=W || stored[i]!=W) $fatal(1,"Queued accounting id=%0d",i);
    repeat(5) @(negedge clk);
    $display("QUEUED_MIXED_PASS operations=4 FP_outputs=24 overlap=%0d blocked_cycles=%0d cycles=%0d",overlap,blocked,steps);
  endtask
`endif

  initial begin
    request=0; operand_valid=0; payload_ready=0; result_gnt=0;
    case_fd=$fopen("cases.txt","r"); result_fd=$fopen("results.csv","w"); trace_fd=$fopen("trace.csv","w");
    $fdisplay(result_fd,"id,width,kind,scalar,stalls,data_errors,nv_errors,flags,expected_flags,flag_events,expected_events,stall_cycles,cycles,raw_errors,tag_errors,flag_data_errors");
    $fdisplay(trace_fd,"case_id,cycle,width,kind,in_valid,in_ready,group_stall,a,b,issue_be,in_tag,in_tag_operand_a,out_valid,out_ready,out_tag,out_tag_operand_a,raw_slots,raw_status,processed_status,result,flags_valid,flags,payload_valid,payload_ready,payload,done");
    if ($test$plusargs("FSDB")) begin $fsdbDumpfile("producer.fsdb"); $fsdbDumpvars(1,producer_tb); end
    repeat(4) @(negedge clk); rst_n=1;
`ifdef COMPARE_METADATA
    check_banks();
    repeat(4) @(negedge clk);
`endif
    while (!$feof(case_fd)) begin
      parsed=$fscanf(case_fd,"%d %d %d %d %d %h %h\n",cid,width,kind,scalar,stalls,scalar_bits,expected_flags);
      if (parsed==7) begin
        for (int i=0;i<Words;i++) begin
          parsed=$fscanf(case_fd,"%h %h %h %h\n",word_a[i],word_b[i],expected[i],expected_nv[i]);
          if (parsed!=4) $fatal(1,"Bad case input");
        end
        run_case();
      end else if (!$feof(case_fd)) $fatal(1,"Bad case header");
    end
`ifdef COMPARE_METADATA
    check_queued_mixed();
`endif
    $display("PRODUCER_COMPLETE cases=%0d",total);
    $fclose(case_fd); $fclose(result_fd); $fclose(trace_fd); $finish;
  end
  initial begin #20000000; $fatal(1,"Global timeout"); end
endmodule
