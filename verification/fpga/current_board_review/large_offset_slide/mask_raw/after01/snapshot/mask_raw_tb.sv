module mask_raw_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  typedef logic [9:0] vaddr_t;
  typedef struct packed { logic valid; logic [63:0] cause, tval; } exception_t;
  `include "ara/ara_typedef.svh"
  `include "local_types.svh"

  bit clk = 0;
  always #5 clk = ~clk;
  logic rst, av, ar, pv, ack;
  ara_req_t arch;
  pe_req_t pe;
  pe_resp_t [7:0] responses;
  pe_resp_t [3:0] lane_response;
  logic [7:0] ready, running, producer_done;
  logic [7:0][7:0] hazards;
  logic [3:0] lane_ready, ldu_req, ldu_gnt, ldu_final;
  vid_t producer_id;
  vaddr_t producer_addr;
  operand_request_cmd_t [3:0][NrOperandQueues-1:0] cmd;
  logic [3:0][NrOperandQueues-1:0] cv, cr;
  logic [3:0][7:0] vr, vw;
  vaddr_t [3:0][7:0] va;
  elen_t [3:0][7:0] wd;
  logic [3:0][7:0][7:0] wb;
  opqueue_e [3:0][7:0] tgt;
  elen_t memory [4][128];
  elen_t observed [4];
  int write_cycle [4][4], read_cycle [4], read_count [4], read_addr [4];
  int command_origin [4], command_length [4];
  bit seen_load, seen_slide, seen_reader, seen_war, token, data_check;
  vid_t reader_id;
  logic [7:0] classified_vm, classified_wait, classified_lifetime;
  int cycle, case_id, errors_total, classification_total, data_cases;
  int width, offset, mode, origin, producer_retire_cycle;

  assign ack = pv && pe.vfu == VFU_LoadUnit && !seen_load;
  always_comb begin
    ready = '1;
    ready[3:0] = lane_ready;
    responses = '0;
    for (int l=0; l<4; l++) responses[l] = lane_response[l];
    responses[4+OffsetLoad].vinsn_done = producer_done;
  end

  ara_sequencer #(.NrLanes(4), .VLEN(1024), .ara_req_t(ara_req_t),
    .ara_resp_t(ara_resp_t), .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t),
    .exception_t(exception_t)) main_seq (
    .clk_i(clk), .rst_ni(rst), .ara_req_i(arch), .ara_req_valid_i(av),
    .ara_req_ready_o(ar), .pe_req_o(pe), .pe_req_valid_o(pv),
    .pe_vinsn_running_o(running), .pe_req_ready_i(ready), .pe_resp_i(responses),
    .alu_vinsn_done_i(1'b0), .mfpu_vinsn_done_i(1'b0),
    .global_hazard_table_o(hazards), .pe_scalar_resp_i('0),
    .pe_scalar_resp_valid_i(1'b0), .addrgen_ack_i(ack),
    .addrgen_exception_i('0), .addrgen_exception_vstart_i('0),
    .addrgen_fof_exception_i(1'b0), .lsu_current_burst_exception_i(1'b0),
    .qbs_fflags_i('0), .qbs_fflags_valid_i(1'b0));

  for (genvar l=0; l<4; l++) begin : lanes
    lane_sequencer #(.NrLanes(4), .VLEN(1024), .pe_req_t(pe_req_t),
      .pe_resp_t(pe_resp_t), .operand_request_cmd_t(operand_request_cmd_t),
      .vfu_operation_t(vfu_operation_t)) seq (
      .clk_i(clk), .rst_ni(rst), .lane_id_i(2'(l)), .pe_req_i(pe),
      .pe_req_valid_i(pv), .pe_vinsn_running_i(running),
      .pe_req_ready_o(lane_ready[l]), .pe_resp_o(lane_response[l]),
      .lsu_ex_flush_i(1'b0), .operand_request_o(cmd[l]),
      .operand_request_valid_o(cv[l]), .operand_request_ready_i(cr[l]),
      .mask_b_cmd_pop_i(1'b0), .alu_ready_i(1'b1), .alu_vinsn_done_i('0),
      .mfpu_ready_i(1'b1), .mfpu_vinsn_done_i('0),
      .masku_vrgat_req_valid_i(1'b0), .masku_vrgat_req_i('0));
    operand_requester #(.NrLanes(4), .VLEN(1024), .NrBanks(8), .vaddr_t(vaddr_t),
      .operand_request_cmd_t(operand_request_cmd_t),
      .operand_queue_cmd_t(operand_queue_cmd_t)) requester (
      .clk_i(clk), .rst_ni(rst), .global_hazard_table_i(hazards),
      .operand_request_i(cmd[l]), .operand_request_valid_i(cv[l]),
      .operand_request_ready_o(cr[l]), .lsu_ex_flush_i(1'b0),
      .vrf_req_o(vr[l]), .vrf_addr_o(va[l]), .vrf_wen_o(vw[l]),
      .vrf_wdata_o(wd[l]), .vrf_be_o(wb[l]), .vrf_tgt_opqueue_o(tgt[l]),
      .operand_queue_ready_i('1),
      .alu_result_req_i(1'b0), .alu_result_id_i('0), .alu_result_addr_i('0),
      .alu_result_wdata_i('0), .alu_result_be_i('0),
      .mfpu_result_req_i(1'b0), .mfpu_result_id_i('0), .mfpu_result_addr_i('0),
      .mfpu_result_wdata_i('0), .mfpu_result_be_i('0),
      .masku_result_req_i(1'b0), .masku_result_id_i('0), .masku_result_addr_i('0),
      .masku_result_wdata_i('0), .masku_result_be_i('0),
      .sldu_result_req_i(1'b0), .sldu_result_id_i('0), .sldu_result_addr_i('0),
      .sldu_result_wdata_i('0), .sldu_result_be_i('0),
      .ldu_result_req_i(ldu_req[l]), .ldu_result_id_i(producer_id),
      .ldu_result_addr_i(producer_addr), .ldu_result_wdata_i('1),
      .ldu_result_be_i('1), .ldu_result_gnt_o(ldu_gnt[l]),
      .ldu_result_final_gnt_o(ldu_final[l]));
  end

  // Only public VRF request/write ports mutate the memory model. Sampling a
  // read before its producer writes the same word intentionally returns X.
  always @(posedge clk) if (rst) begin
    cycle++;
    if (pv && &ready[3:0]) begin
      if (pe.op == VLE && !seen_load) begin
        producer_id = pe.id;
        seen_load = 1;
        $display("PRODUCER case=%0d cycle=%0d vid=%0d vl=%0d vd=%0d",case_id,cycle,pe.id,pe.vl,pe.vd);
      end
      if (pe.op == VSLIDEUP && !seen_slide) begin
        seen_slide = 1;
        classified_vm = pe.hazard_vm;
        classified_wait = pe.hazard_wait_complete;
        classified_lifetime = pe.hazard_source_lifetime;
        $display("CLASS case=%0d cycle=%0d vid=%0d producer=%0d vm=%h wait=%h lifetime=%h global=%h",
          case_id,cycle,pe.id,producer_id,pe.hazard_vm,pe.hazard_wait_complete,
          pe.hazard_source_lifetime,hazards[pe.id]);
      end
      if (!data_check && pe.op == VADD) begin
        if (pe.vm && !seen_reader) begin reader_id=pe.id; seen_reader=1; end
        if (!pe.vm && !seen_war) begin
          seen_war=1;
          classified_vm=pe.hazard_vm;
          classified_wait=pe.hazard_wait_complete;
          classified_lifetime=pe.hazard_source_lifetime;
        end
      end
    end
    for (int l=0; l<4; l++) begin
      if (cv[l][MaskM] && cr[l][MaskM] && data_check) begin
        assert(command_origin[l] == -1) else $fatal(1,"duplicate MaskM command");
        command_origin[l]=cmd[l][MaskM].vstart;
        command_length[l]=cmd[l][MaskM].vl;
        $display("COMMAND case=%0d cycle=%0d lane=%0d origin=%0d length=%0d eew=%0d hazard=%h wait=%h",
          case_id,cycle,l,cmd[l][MaskM].vstart,cmd[l][MaskM].vl,
          cmd[l][MaskM].eew,cmd[l][MaskM].hazard,cmd[l][MaskM].hazard_wait_complete);
      end
      for (int bank=0; bank<8; bank++) if (vr[l][bank]) begin
        automatic int addr = int'(va[l][bank])*8+bank;
        assert(addr<128) else $fatal(1,"VRF address out of fixture bounds");
        if (vw[l][bank]) begin
          assert(addr<4 && wb[l][bank]==8'hff) else $fatal(1,"unexpected modeled producer write");
          for (int b=0; b<8; b++) if(wb[l][bank][b]) memory[l][addr][8*b+:8]=wd[l][bank][8*b+:8];
          write_cycle[l][addr]=cycle;
          $display("WRITE case=%0d cycle=%0d lane=%0d vid=%0d word=%0d data=%h",case_id,cycle,l,producer_id,addr,wd[l][bank]);
        end else if (tgt[l][bank]==MaskM && data_check) begin
          read_count[l]++;
          read_cycle[l]=cycle;
          read_addr[l]=addr;
          observed[l]=memory[l][addr];
          $display("READ case=%0d cycle=%0d lane=%0d word=%0d target_write_cycle=%0d data=%h",
            case_id,cycle,l,addr,write_cycle[l][addr],memory[l][addr]);
        end
      end
    end
  end

  task automatic reset_case;
    @(negedge clk);
    rst=0; av=0; arch='0; ldu_req='0; producer_done='0; producer_id='0;
    seen_load=0; seen_slide=0; seen_reader=0; seen_war=0; token=0;
    classified_vm='0; classified_wait='0; classified_lifetime='0;
    cycle=0; producer_retire_cycle=-1;
    for(int l=0;l<4;l++) begin
      read_cycle[l]=-1; read_count[l]=0; read_addr[l]=-1;
      command_origin[l]=-1; command_length[l]=-1; observed[l]='x;
      for(int w=0;w<128;w++) memory[l][w]='x;
      for(int w=0;w<4;w++) write_cycle[l][w]=-1;
    end
    repeat(4) @(negedge clk);
    rst=1;
  endtask

  task automatic submit(ara_req_t request);
    bit accepted;
    accepted=0;
    @(negedge clk); token=~token; arch=request; arch.token=token; av=1;
    for(int n=0;n<100;n++) begin
      @(posedge clk);
      if(ar) begin accepted=1; break; end
    end
    assert(accepted) else $fatal(1,"architectural request timeout case=%0d",case_id);
    @(negedge clk); av=0;
  endtask

  task automatic write_producer(bit tracked);
    logic [3:0] accepted;
    for(int w=0;w<4;w++) begin
      repeat(8) @(negedge clk);
      producer_addr=vaddr_t'(w); ldu_req='1;
      for(int n=0;n<30;n++) begin
        @(posedge clk); accepted=ldu_req & ldu_gnt;
        @(negedge clk); ldu_req &= ~accepted;
        if(ldu_req=='0) break;
      end
      assert(ldu_req=='0) else $fatal(1,"producer input grant timeout");
    end
    for(int n=0;n<30;n++) begin
      @(negedge clk);
      if(write_cycle[0][3]>=0 && write_cycle[1][3]>=0 &&
         write_cycle[2][3]>=0 && write_cycle[3][3]>=0) break;
    end
    for(int l=0;l<4;l++) assert(write_cycle[l][3]>=0) else $fatal(1,"missing final producer write");
    if(tracked) begin
      producer_done[producer_id]=1;
      producer_retire_cycle=cycle;
      $display("PRODUCER_DONE case=%0d cycle=%0d vid=%0d",case_id,cycle,producer_id);
      @(negedge clk); producer_done='0;
    end
  endtask

  task automatic run_case(int sew, int stride, int producer_mode);
    ara_req_t load, slide;
    int data_errors, class_errors;
    bit expected_wait;
    width=sew; offset=stride; mode=producer_mode; origin=stride/256; data_check=1;
    reset_case();
    load='0; load.op=VLE; load.vm=1; load.vd=0; load.use_vd=1;
    load.vl=128; load.emul=LMUL_1; load.vtype.vlmul=LMUL_1; load.vtype.vsew=EW8;
    slide='0; slide.op=VSLIDEUP; slide.vm=0; slide.vd=24; slide.use_vd=1;
    slide.vs2=8; slide.use_vs2=1; slide.eew_vs2=vew_e'(sew); slide.eew_vmask=EW8;
    slide.scale_vl=1; slide.stride=stride; slide.vl=stride+1;
    slide.vtype.vsew=vew_e'(sew); slide.vtype.vlmul=LMUL_8; slide.emul=LMUL_8;
    assert(stride+1 <= (1024>>sew)) else $fatal(1,"illegal fixture VL");
    if(mode!=1) begin
      submit(load);
      assert(seen_load) else $fatal(1,"load not broadcast");
    end
    if(mode==0) begin
      fork
        submit(slide);
        write_producer(1);
      join
    end else begin
      write_producer(mode==2);
      repeat(6) @(negedge clk);
      submit(slide);
    end
    repeat(16) @(negedge clk);
    assert(seen_slide) else $fatal(1,"slide not broadcast");
    data_errors=0; class_errors=0;
    for(int l=0;l<4;l++) begin
      assert(command_origin[l]==origin && command_length[l]==1 && read_count[l]==1 && read_addr[l]==origin)
        else $fatal(1,"unexpected command/read geometry case=%0d lane=%0d origin=%0d length=%0d reads=%0d address=%0d",case_id,l,command_origin[l],command_length[l],read_count[l],read_addr[l]);
      if(observed[l] !== 64'hffffffffffffffff || read_cycle[l]<=write_cycle[l][origin]) data_errors++;
    end
    expected_wait=mode==0 && origin!=0;
    if((|(classified_wait & (8'b1<<producer_id))) != expected_wait) class_errors++;
    if(mode==0 && !(classified_vm & (8'b1<<producer_id))) class_errors++;
    if(mode!=0 && classified_vm!='0) class_errors++;
    $display("RESULT case=%0d sew=%0d offset=%0d origin=%0d mode=%0d errors=%0d class_errors=%0d read_cycle=%0d target_write_cycle=%0d producer_done_cycle=%0d actual=%h expected=ffffffffffffffff wait=%h",
      case_id,8<<sew,stride,origin,mode,data_errors,class_errors,
      read_cycle[0],write_cycle[0][origin],producer_retire_cycle,observed[0],classified_wait);
    errors_total+=data_errors; classification_total+=class_errors; data_cases++; case_id++;
  endtask

  task automatic war_control;
    ara_req_t older, younger;
    data_check=0; reset_case();
    older='0; older.op=VADD; older.vm=1; older.vs2=24; older.use_vs2=1;
    older.vd=16; older.use_vd=1; older.vl=4; older.emul=LMUL_1;
    older.vtype.vlmul=LMUL_1; older.vtype.vsew=EW8; older.eew_vs2=EW8;
    younger=older; younger.vm=0; younger.vd=24; younger.vs2=8;
    younger.vl=1024; younger.vstart=768; younger.emul=LMUL_8; younger.vtype.vlmul=LMUL_8;
    submit(older); submit(younger); repeat(6) @(negedge clk);
    assert(seen_reader && seen_war && classified_vm[reader_id] &&
           classified_lifetime[reader_id] && !classified_wait[reader_id])
      else $fatal(1,"pure WAR incorrectly classified reader=%0d vm=%h life=%h wait=%h",reader_id,classified_vm,classified_lifetime,classified_wait);
    $display("WAR_CONTROL PASS reader=%0d vm=%h lifetime=%h wait=%h",reader_id,classified_vm,classified_lifetime,classified_wait);
  endtask

  initial begin
    rst=0; av=0; arch='0; ldu_req='0; producer_done='0;
    case_id=0; errors_total=0; classification_total=0; data_cases=0;
    for(int m=0;m<3;m++) for(int word=0;word<4;word++) run_case(0,word*256,m);
    run_case(0,31,0); run_case(0,255,0); run_case(0,257,0);
    run_case(0,511,0); run_case(0,1023,0);
    run_case(1,255,0); run_case(1,256,0); run_case(1,511,0);
    run_case(2,255,0); run_case(3,127,0);
    war_control();
    $display("SUMMARY cases=%0d data_errors=%0d class_errors=%0d",data_cases,errors_total,classification_total);
    $display("HARNESS_COMPLETE mask_raw");
    $finish;
  end
  initial begin #200000; $fatal(1,"bounded watchdog"); end
endmodule
