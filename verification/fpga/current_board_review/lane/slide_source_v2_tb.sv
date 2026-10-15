module slide_source_v2_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  typedef logic [9:0] vaddr_t;
  `include "ara/ara_typedef.svh"
  `include "lane_types.svh"
  bit clk=0;
  always #5 clk=~clk;
  logic rst, valid;
  pe_req_t req;
  pe_resp_t resp;
  operand_request_cmd_t [3:0][NrOperandQueues-1:0] cmd;
  logic [3:0][NrOperandQueues-1:0] cv, cr;
  logic [3:0][7:0] vr, vw;
  vaddr_t [3:0][7:0] va;
  elen_t [3:0][7:0] wd;
  logic [3:0][7:0][7:0] wb;
  opqueue_e [3:0][7:0] tgt;
  elen_t [3:0] source_data, result_data;
  logic [3:0] source_valid, source_ready, result_req, result_gnt, final_gnt;
  vid_t [3:0] result_id;
  vaddr_t [3:0] result_addr;
  logic [3:0][7:0] result_be;
  elen_t fifo[4][128];
  int wp[4], rp[4], first_addr[4], origin[4], length[4];
  byte unsigned actual[2048], expected[2048];
  int baseline, case_id, cycle, done_cycle, sew, vl, start, stride, cap;
  int passed, reproduced;
  bit down, scalar, done;

  function automatic elen_t element_value(int index);
    return 64'h1000 + index;
  endfunction
  function automatic elen_t memory_word(int lane, int addr);
    elen_t data;
    int pos, element;
    for (int b=0; b<8; b++) begin
      pos = (addr-int'(vaddr(8,4,1024)))*32 + int'(deshuffle_index(lane*8+b,4,vew_e'(sew)));
      element = pos >> sew;
      data[b*8 +: 8] = element_value(element) >> ((pos % (1 << sew))*8);
    end
    return data;
  endfunction

  for (genvar l=0; l<4; l++) begin : lanes
    lane_sequencer #(.NrLanes(4), .VLEN(1024), .pe_req_t(pe_req_t),
      .pe_resp_t(pe_resp_t), .operand_request_cmd_t(operand_request_cmd_t),
      .vfu_operation_t(vfu_operation_t)) seq (
      .clk_i(clk), .rst_ni(rst), .lane_id_i(2'(l)), .pe_req_i(req),
      .pe_req_valid_i(valid), .pe_vinsn_running_i('1), .lsu_ex_flush_i(1'b0),
      .operand_request_o(cmd[l]), .operand_request_valid_o(cv[l]),
      .operand_request_ready_i(cr[l]), .mask_b_cmd_pop_i(1'b0),
      .alu_ready_i(1'b1), .alu_vinsn_done_i('0), .mfpu_ready_i(1'b1),
      .mfpu_vinsn_done_i('0), .masku_vrgat_req_valid_i(1'b0), .masku_vrgat_req_i('0));
    operand_requester #(.NrLanes(4), .VLEN(1024), .NrBanks(8), .vaddr_t(vaddr_t),
      .operand_request_cmd_t(operand_request_cmd_t), .operand_queue_cmd_t(operand_queue_cmd_t)) requester (
      .clk_i(clk), .rst_ni(rst), .global_hazard_table_i('0), .operand_request_i(cmd[l]),
      .operand_request_valid_i(cv[l]), .operand_request_ready_o(cr[l]),
      .lsu_ex_flush_i(1'b0), .vrf_req_o(vr[l]), .vrf_addr_o(va[l]),
      .vrf_wen_o(vw[l]), .vrf_wdata_o(wd[l]), .vrf_be_o(wb[l]),
      .vrf_tgt_opqueue_o(tgt[l]), .operand_queue_ready_i('1),
      .alu_result_req_i(1'b0), .alu_result_id_i('0), .alu_result_addr_i('0),
      .alu_result_wdata_i('0), .alu_result_be_i('0),
      .mfpu_result_req_i(1'b0), .mfpu_result_id_i('0), .mfpu_result_addr_i('0),
      .mfpu_result_wdata_i('0), .mfpu_result_be_i('0),
      .masku_result_req_i(1'b0), .masku_result_id_i('0), .masku_result_addr_i('0),
      .masku_result_wdata_i('0), .masku_result_be_i('0),
      .sldu_result_req_i(result_req[l]), .sldu_result_id_i(result_id[l]),
      .sldu_result_addr_i(result_addr[l]), .sldu_result_wdata_i(result_data[l]),
      .sldu_result_be_i(result_be[l]), .sldu_result_gnt_o(result_gnt[l]),
      .sldu_result_final_gnt_o(final_gnt[l]),
      .ldu_result_req_i(1'b0), .ldu_result_id_i('0), .ldu_result_addr_i('0),
      .ldu_result_wdata_i('0), .ldu_result_be_i('0));
    assign source_valid[l] = wp[l] > rp[l];
    assign source_data[l] = source_valid[l] ? fifo[l][rp[l]] : '0;
  end
  sldu #(.NrLanes(4), .VLEN(1024), .vaddr_t(vaddr_t),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) slide (
    .clk_i(clk), .rst_ni(rst), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('1), .pe_resp_o(resp), .maintenance_drain_i(1'b0),
    .sldu_operand_i(source_data), .sldu_operand_valid_i(source_valid),
    .sldu_operand_reduction_i('0), .sldu_operand_ready_o(source_ready),
    .sldu_result_req_o(result_req), .sldu_result_id_o(result_id),
    .sldu_result_addr_o(result_addr), .sldu_result_wdata_o(result_data),
    .sldu_result_be_o(result_be), .sldu_result_gnt_i(result_gnt),
    .sldu_result_final_gnt_i(final_gnt), .mask_i('1), .mask_valid_i('0));

  always @(posedge clk) begin
    if (!rst) begin
      for (int l=0; l<4; l++) begin
        wp[l] <= 0; rp[l] <= 0; first_addr[l] <= -1; origin[l] <= -1; length[l] <= -1;
      end
    end else begin
      cycle++;
      if (resp.vinsn_done[3]) begin done=1; done_cycle=cycle; end
      for (int l=0; l<4; l++) begin
        if (cv[l][SlideAddrGenA] && cr[l][SlideAddrGenA]) begin
          assert(origin[l] == -1) else $fatal(1,"Duplicate command");
          origin[l] <= cmd[l][SlideAddrGenA].vstart;
          length[l] <= cmd[l][SlideAddrGenA].vl;
          assert(cmd[l][SlideAddrGenA].eew == vew_e'(sew) && cmd[l][SlideAddrGenA].is_slide)
            else $fatal(1,"Wrong slide requester metadata");
          if (l==0) $display("COMMAND case=%0d cycle=%0d origin=%0d length=%0d eew=%0d scale=%0d",
            case_id,cycle,cmd[l][SlideAddrGenA].vstart,cmd[l][SlideAddrGenA].vl,
            cmd[l][SlideAddrGenA].eew,cmd[l][SlideAddrGenA].scale_vl);
        end
        if (source_valid[l] && source_ready[l]) rp[l] <= rp[l]+1;
        for (int bank=0; bank<8; bank++) if (vr[l][bank]) begin
          automatic int addr = int'(va[l][bank])*8+bank;
          if (!vw[l][bank]) begin
            assert(tgt[l][bank] == SlideAddrGenA && wp[l] < 128)
              else $fatal(1,"Unexpected read target or FIFO overflow");
            fifo[l][wp[l]] <= memory_word(l,addr);
            wp[l] <= wp[l]+1;
            if (first_addr[l] == -1) begin
              first_addr[l] <= addr;
              $display("FIRST_READ case=%0d cycle=%0d lane=%0d bank=%0d row=%0d word_addr=%0d data=%h",
                case_id,cycle,l,bank,va[l][bank],addr,memory_word(l,addr));
            end
          end else begin
            for (int b=0; b<8; b++) if (wb[l][bank][b]) begin
              automatic int pos = (addr-int'(vaddr(24,4,1024)))*32
                  + int'(deshuffle_index(l*8+b,4,vew_e'(sew)));
              assert(pos>=0 && pos<2048) else $fatal(1,"Write outside destination fixture");
              actual[pos] = wd[l][bank][b*8 +: 8];
            end
          end
        end
      end
    end
  end

  task automatic run_case(int width, int count, int restart, bit is_down, bit is_scalar, int offset);
    int errors, prefix_errors, expected_origin, expected_addr, target_element;
    int shifted_elements;
    elen_t gold, observed, target_gold;
    bit predict_bug;
    rst=0; valid=0; req='0;
    sew=width; vl=count; start=restart; down=is_down; scalar=is_scalar; stride=offset;
    cycle=0; done=0; done_cycle=-1;
    repeat(4) @(negedge clk);
    req.id=3; req.vfu=VFU_SlideUnit; req.op=down ? VSLIDEDOWN : VSLIDEUP;
    req.vm=1; req.vs2=8; req.use_vs2=1; req.vd=24; req.use_vd=1;
    req.vl=vl; req.vstart=start; req.eew_vs2=vew_e'(sew); req.vtype.vsew=vew_e'(sew);
    req.scale_vl=1; req.use_scalar_op=scalar; req.scalar_op=64'h1122334455667788;
    req.stride=stride; req.vtype.vlmul=LMUL_1; cap=128 >> sew;
    if (vl>cap) begin req.vtype.vlmul=LMUL_2; cap*=2; end
    if (vl>cap) begin req.vtype.vlmul=LMUL_4; cap*=2; end
    if (vl>cap) begin req.vtype.vlmul=LMUL_8; cap*=2; end
    req.emul=req.vtype.vlmul;
    for (int b=0; b<2048; b++) begin actual[b]=8'ha5; expected[b]=8'ha5; end
    for (int i=0; i<vl; i++) begin
      if (i<start || (!down && !scalar && i<stride)) continue;
      if (scalar && ((!down && i==0) || (down && i==vl-1))) gold=req.scalar_op;
      else if (down) gold=(i+stride < cap) ? element_value(i+stride) : '0;
      else gold=element_value(i-stride);
      for (int b=0; b<(1 << sew); b++) expected[(i << sew)+b]=gold >> (b*8);
    end
    rst=1;
    @(negedge clk); valid=1;
    @(negedge clk); valid=0;
    repeat(160) @(negedge clk);
    assert(done) else $fatal(1,"SLDU did not complete bounded case %0d",case_id);
    expected_origin = down ? stride/4 : baseline ? start/4 : 0;
    expected_addr = int'(vaddr(8,4,1024)) + (expected_origin >> (3-sew));
    for (int l=0; l<4; l++) begin
      assert(origin[l] == expected_origin && first_addr[l] == expected_addr)
        else $fatal(1,"Unexpected current request/address case=%0d lane=%0d origin=%0d address=%0d",case_id,l,origin[l],first_addr[l]);
    end
    errors=0; prefix_errors=0;
    for (int b=0; b<2048; b++) if (actual[b] !== expected[b]) begin
      errors++;
      if (b<(start << sew)) prefix_errors++;
    end
    assert(prefix_errors == 0) else $fatal(1,"Unexpected prestart write, outside source-origin hypothesis");
    shifted_elements = (start / (32 >> sew))*(32 >> sew);
    predict_bug = baseline && !down && shifted_elements != 0;
    target_element = down ? start : ((start>stride) ? start : stride);
    observed='0; target_gold='0;
    for (int b=0; b<(1 << sew); b++) begin
      observed[b*8 +: 8]=actual[(target_element << sew)+b];
      target_gold[b*8 +: 8]=expected[(target_element << sew)+b];
    end
    $display("RESULT case=%0d sew=%0d vl=%0d start=%0d down=%0d scalar=%0d stride=%0d origin=%0d length=%0d first_addr=%0d reads=%0d done_cycle=%0d errors=%0d target=%0d actual=%h expected=%h expected_bug=%0d",
      case_id,8 << sew,vl,start,down,scalar,stride,origin[0],length[0],first_addr[0],wp[0],done_cycle,
      errors,target_element,observed,target_gold,predict_bug);
    if (predict_bug) begin
      assert(errors>0 && observed == element_value(target_element-stride+shifted_elements))
        else $fatal(1,"Source shift prediction not reproduced");
      reproduced++;
    end else begin
      assert(errors == 0) else $fatal(1,"Unexpected result data mismatch");
      passed++;
    end
    if (case_id==0 && $test$plusargs("WAVE")) $fsdbDumpoff;
    case_id++;
  endtask

  initial begin
    baseline=0; case_id=0; passed=0; reproduced=0; rst=0; valid=0; req='0;
    void'($value$plusargs("BASELINE=%d",baseline));
    if ($test$plusargs("WAVE")) begin
      $fsdbDumpfile("source_origin.fsdb");
      $fsdbDumpvars(1,slide_source_v2_tb);
      $fsdbDumpvars(1,slide_source_v2_tb.lanes[0].seq);
      $fsdbDumpvars(1,slide_source_v2_tb.lanes[0].requester);
      $fsdbDumpvars(1,slide_source_v2_tb.slide);
    end
    run_case(2,16,8,0,1,1);
    for (int width=2; width<=3; width++) begin
      int n;
      n=width==2 ? 16 : 8;
      for (int r=0; r<4; r++) begin
        int restart;
        case(r)
          0: restart=0;
          1: restart=1;
          2: restart=n/2;
          3: restart=n-1;
        endcase
        run_case(width,n,restart,0,1,1);
        run_case(width,n,restart,0,0,1);
        run_case(width,n,restart,1,1,1);
        run_case(width,n,restart,1,0,n/2);
      end
      // Architectural restart indices 32 and 64, not just SEW32/SEW64.
      run_case(width,128,32,0,1,1);
      run_case(width,128,64,0,0,8);
      run_case(width,128,32,1,1,1);
      run_case(width,128,64,1,0,8);
    end
    assert(case_id==41) else $fatal(1,"Incomplete matrix");
    $display("SUMMARY cases=%0d passed=%0d reproduced=%0d baseline=%0d",case_id,passed,reproduced,baseline);
    $display("PASS slide_source_v2");
    $finish;
  end
endmodule
