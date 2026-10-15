module lane_mask_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  `include "lane_types.svh"
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst, valid;
  pe_req_t req;
  pe_resp_t mr;
  operand_request_cmd_t [3:0][NrOperandQueues-1:0] cmd;
  logic [3:0][NrOperandQueues-1:0] cv;
  vfu_operation_t [3:0] vo;
  logic [3:0] vv, lr, ar, av, amr, mv, result_req;
  logic [3:0][NrVInsn-1:0] adone;
  elen_t [3:0] ao, result_data;
  logic [3:0][7:0] masks, result_be;
  logic [3:0][9:0] result_addr;
  elen_t [3:0][NrMaskFUnits+1:0] operands;
  logic [3:0][NrMaskFUnits+1:0] ov, ordy;
  logic [3:0] final_gnt;
  vfu_e target;
  int remaining[4][2], address[4][2], raw_count[4][2];
  int case_kind, start, vl, sew, mode, cycle, finish_cycle, beats;
  int expected_failure, errors, mask_origin, mask_length, old_origin;
  bit done, request_only;
  logic [1023:0] actual, expected;
  logic [3:0] sink_ready;
  elen_t data_elements[1024];
  elen_t [3:0][1:0] alu_data;
  logic [3:0][1:0] alu_data_ready;
  int alu_word[4];
  logic [63:0] rng, elem_mask;

  // The finite VRF stand-in honors the issued EW64 origin and word count.
  // The first old-vd word is the archived 0x5b pattern. Later words differ
  // deliberately to make an incorrect packed-mask address observable.
  function automatic logic old_bit(int bit_index);
    return ((bit_index / 256) % 2) ? 1'b0 : ((8'h5b >> (bit_index % 8)) & 1);
  endfunction
  function automatic logic pred_bit(int bit_index);
    case (mode)
      0: return 1;
      1: return 0;
      default: return ((8'h24 >> (bit_index % 8)) & 1);
    endcase
  endfunction
  function automatic elen_t raw_word(int lane, int stream, int word_index);
    elen_t data;
    int seq_byte, idx;
    for (int b=0; b<8; b++) begin
      seq_byte = deshuffle_index(lane*8+b, 4,
          stream == 1 ? req.eew_vd_op : req.eew_vmask);
      for (int k=0; k<8; k++) begin
        idx = word_index*256 + seq_byte*8+k;
        data[b*8+k] = stream == 1 ? old_bit(idx) : pred_bit(idx);
      end
    end
    return data;
  endfunction

  for (genvar l=0; l<4; l++) begin : lanes
    lane_sequencer #(.NrLanes(4), .VLEN(1024), .pe_req_t(pe_req_t),
      .pe_resp_t(pe_resp_t), .operand_request_cmd_t(operand_request_cmd_t),
      .vfu_operation_t(vfu_operation_t)) seq (
      .clk_i(clk), .rst_ni(rst), .lane_id_i(2'(l)), .pe_req_i(req),
      .pe_req_valid_i(valid), .pe_vinsn_running_i('1), .pe_req_ready_o(lr[l]),
      .lsu_ex_flush_i(1'b0), .operand_request_o(cmd[l]),
      .operand_request_valid_o(cv[l]), .operand_request_ready_i('1),
      .mask_b_cmd_pop_i(1'b0), .vfu_operation_o(vo[l]),
      .vfu_operation_valid_o(vv[l]), .alu_ready_i(ar[l]),
      .alu_vinsn_done_i(adone[l]), .mfpu_ready_i(1'b1), .mfpu_vinsn_done_i('0),
      .masku_vrgat_req_valid_i(1'b0), .masku_vrgat_req_i('0));
    valu #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic[9:0]),
      .vfu_operation_t(vfu_operation_t)) alu (
      .clk_i(clk), .rst_ni(rst), .lane_id_i(2'(l)), .alu_vxrm_i('0),
      .vfu_operation_i(vo[l]),
      .vfu_operation_valid_i(vv[l] && !request_only),
      .alu_ready_o(ar[l]), .alu_vinsn_done_o(adone[l]),
      .alu_operand_i(alu_data[l]), .alu_operand_valid_i('1),
      .alu_operand_ready_o(alu_data_ready[l]), .alu_result_gnt_i(1'b1),
      .alu_red_ready_i(1'b1), .sldu_operand_i('0), .sldu_alu_valid_i(1'b0),
      .mask_operand_o(ao[l]), .mask_operand_valid_o(av[l]),
      .mask_operand_ready_i(ordy[l][2]), .mask_i(masks[l]),
      .mask_valid_i(mv[l]), .mask_ready_o(amr[l]));
  end
  assign sink_ready = request_only ? '1 : amr;
  masku #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic[9:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) m (
    .clk_i(clk), .rst_ni(rst), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('1), .pe_resp_o(mr),
    .masku_operand_i(operands), .masku_operand_valid_i(ov),
    .masku_operand_ready_o(ordy), .masku_result_req_o(result_req),
    .masku_result_wdata_o(result_data), .masku_result_be_o(result_be),
    .masku_result_addr_o(result_addr), .masku_result_gnt_i(result_req),
    .masku_result_final_gnt_i(final_gnt), .masku_vrgat_req_ready_i('1),
    .mask_o(masks), .mask_valid_o(mv), .mask_target_fu_o(target),
    .lane_mask_ready_i(sink_ready), .vldu_mask_ready_i(target == VFU_LoadUnit),
    .vstu_mask_ready_i(target == VFU_StoreUnit), .sldu_mask_ready_i(target == VFU_SlideUnit));

  always_comb begin
    operands = '0;
    ov = '0;
    alu_data = '0;
    for (int l=0; l<4; l++) begin
      // Abstract zero-based post-queue data stream; data requester/VRF layout
      // and alias lifetime are deliberately outside this contract test.
      for (int b=0; b<8; b++) begin
        automatic int linear = int'(deshuffle_index(l*8+b,4,vew_e'(sew)));
        automatic int element = alu_word[l]*(32 >> sew) + (linear >> sew);
        if (element < 1024)
          alu_data[l][1][b*8 +: 8] = data_elements[element] >> ((linear % (1 << sew))*8);
      end
      for (int q=0; q<2; q++) begin
        operands[l][q] = raw_word(l, q, address[l][q]);
        ov[l][q] = remaining[l][q] > 0;
      end
      operands[l][2] = ao[l];
      ov[l][2] = av[l];
    end
  end
  always @(posedge clk) begin
    final_gnt <= rst ? result_req : '0;
    if (rst) begin
      cycle = cycle + 1;
      if (mr.vinsn_done[3]) begin done = 1; finish_cycle = cycle; end
      if (mv[0] && sink_ready[0] && target != VFU_None) beats = beats + 1;
      for (int l=0; l<4; l++) begin
        if (alu_data_ready[l][1]) alu_word[l] <= alu_word[l]+1;
        for (int q=0; q<2; q++) begin
          if (ov[l][q] && ordy[l][q]) begin
            remaining[l][q] <= remaining[l][q]-1;
            address[l][q] <= address[l][q]+1;
            raw_count[l][q] = raw_count[l][q]+1;
          end
          if (cv[l][q == 0 ? MaskM : MaskB]) begin
            remaining[l][q] <= cmd[l][q == 0 ? MaskM : MaskB].vl;
            address[l][q] <= cmd[l][q == 0 ? MaskM : MaskB].vstart;
            if (l == 0) begin
              $display("REQUEST cycle=%0d stream=%0d vs=%0d eew=%0d origin=%0d length=%0d",
                cycle,q,cmd[l][q == 0 ? MaskM : MaskB].vs,
                cmd[l][q == 0 ? MaskM : MaskB].eew,
                cmd[l][q == 0 ? MaskM : MaskB].vstart,
                cmd[l][q == 0 ? MaskM : MaskB].vl);
              if (q == 0) begin
                mask_origin = cmd[l][MaskM].vstart;
                mask_length = cmd[l][MaskM].vl;
              end else old_origin = cmd[l][MaskB].vstart;
            end
          end
        end
        if (result_req[l]) begin
          for (int b=0; b<8; b++) if (result_be[l][b]) begin
            automatic int idx = (int'(result_addr[l])-int'(vaddr(req.vd,4,1024)))*256
              + int'(deshuffle_index(l*8+b,4,req.vtype.vsew))*8;
            actual[idx +: 8] = result_data[l][b*8 +: 8];
          end
        end
      end
    end
  end
  initial begin
    rst=0; valid=0; req='0; cycle=0; beats=0; done=0; finish_cycle=-1;
    mask_origin=-1; mask_length=-1; old_origin=-1; errors=0;
    case_kind=0; start=256; vl=512; sew=0; mode=0; expected_failure=0;
    void'($value$plusargs("KIND=%d",case_kind));
    void'($value$plusargs("START=%d",start));
    void'($value$plusargs("VL=%d",vl));
    void'($value$plusargs("SEW=%d",sew));
    void'($value$plusargs("MODE=%d",mode));
    void'($value$plusargs("EXPECT_FAIL=%d",expected_failure));
    request_only = case_kind != 0;
    elem_mask = sew == 3 ? '1 : (64'd1 << (8 << sew))-1;
    rng = 64'hc274caf34727a125;
    for (int i=0; i<1024; i++) begin
      rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
      data_elements[i] = rng & elem_mask;
      if (i%2 == 0) begin
        case ((i/2)%7)
          0: data_elements[i] = -64'd3 & elem_mask;
          1: data_elements[i] = -64'd4 & elem_mask;
          2: data_elements[i] = -64'd2 & elem_mask;
          3: data_elements[i] = 0;
          4: data_elements[i] = elem_mask;
          5: data_elements[i] = 64'd1 << ((8 << sew)-1);
          6: data_elements[i] = (64'd1 << ((8 << sew)-1))-1;
        endcase
      end
    end
    for (int l=0; l<4; l++) alu_word[l]=0;
    for (int l=0; l<4; l++) for (int q=0; q<2; q++) begin
      remaining[l][q]=0; address[l][q]=0; raw_count[l][q]=0;
    end
    for (int i=0; i<1024; i++) begin
      actual[i]=old_bit(i); expected[i]=old_bit(i);
      if (i>=start && i<vl && pred_bit(i)) expected[i]=(data_elements[i] == (-64'd3 & elem_mask));
    end
    if ($test$plusargs("WAVE")) begin
      $fsdbDumpfile("focused.fsdb");
      $fsdbDumpvars(1,lane_mask_tb);
      $fsdbDumpvars(1,lane_mask_tb.m);
      $fsdbDumpvars(1,lane_mask_tb.lanes[0].seq);
      $fsdbDumpvars(1,lane_mask_tb.lanes[0].alu);
    end
    repeat (4) @(negedge clk);
    rst=1;
    req.id=3; req.op=VMSEQ; req.vfu=VFU_MaskUnit;
    req.vm=0; req.vd=24; req.use_vd=1; req.use_vd_op=1;
    req.vs2=8; req.use_vs2=1; req.use_scalar_op=1; req.scalar_op=-64'd3;
    req.eew_vs2=vew_e'(sew); req.eew_vs1=vew_e'(sew);
    req.eew_vd_op=EW8; req.eew_vmask=EW8;
    req.vl=vl; req.vstart=start; req.vtype.vsew=vew_e'(sew);
    req.vtype.vlmul=vl <= (128 >> sew) ? LMUL_1 : sew == 0 ? LMUL_4 : LMUL_8;
    req.emul=req.vtype.vlmul;
    case (case_kind)
      1: begin req.op=VMACC; req.vfu=VFU_MFpu; end
      2: begin req.op=VADD; req.vfu=VFU_Alu; end
      3: begin req.op=VLE; req.vfu=VFU_LoadUnit; end
      4: begin req.op=VSE; req.vfu=VFU_StoreUnit; end
      5: begin req.op=VMAND; req.vm=1; req.vs1=16; req.use_vs1=1; end
      6: begin req.op=VMFEQ; req.use_vs1=1; req.use_scalar_op=0; end
      7: begin req.op=VSLIDEUP; req.vfu=VFU_SlideUnit; req.stride=1; end
      8: begin req.op=VSLIDEDOWN; req.vfu=VFU_SlideUnit; req.stride=0; end
      default:;
    endcase
    @(negedge clk); valid=1;
    @(negedge clk); valid=0;
    repeat (220) @(negedge clk);
    if ($test$plusargs("WAVE")) $fsdbDumpoff;
    $display("RESULT kind=%0d vl=%0d start=%0d sew=%0d mode=%0d done=%0d finish=%0d mask_origin=%0d mask_length=%0d old_origin=%0d raw_m=%0d raw_b=%0d read=%0d issue=%0d commit=%0d beats=%0d",
      case_kind,vl,start,sew,mode,done,finish_cycle,mask_origin,mask_length,old_origin,
      raw_count[0][0],raw_count[0][1],m.read_cnt_q,m.issue_cnt_q,m.commit_cnt_q,beats);
    if (expected_failure == 2) begin
      assert(case_kind == 8 && mask_origin == start/4 && mask_length == (vl+255)/256)
        else $fatal(1,"Predicted slidedown address error absent");
      $display("EXPECTED_CURRENT_FAILURE");
    end else if (expected_failure) begin
      assert(mask_origin == 1 && mask_length == 1 && raw_count[0][0] == 1 &&
        !done && m.commit_cnt_q != 0 && remaining[0][0] == 0)
        else $fatal(1,"Predicted starvation signature absent");
      if (case_kind == 0) assert(m.issue_cnt_q == 256)
        else $fatal(1,"Compare did not stop at missing second word");
      $display("EXPECTED_CURRENT_FAILURE");
    end else begin
      if (case_kind inside {0,1,2,3,4})
        assert(done) else $fatal(1,"No MASKU completion within 220 cycles");
      if (case_kind == 0) begin
        assert(old_origin == 0) else $fatal(1,"Wrong packed old-vd origin");
        for (int i=0; i<vl; i++) if (actual[i] !== expected[i]) begin
          if (errors < 8) $display("MISMATCH bit=%0d actual=%b expected=%b",i,actual[i],expected[i]);
          errors++;
        end
        assert(errors == 0) else $fatal(1,"Compare merge data errors=%0d",errors);
      end
      if (case_kind inside {0,1,2,5,6})
        assert(mask_origin == 0 && mask_length == (vl+255)/256)
          else $fatal(1,"Wrong zero-origin mask stream");
      if (case_kind inside {3,4})
        assert(mask_origin == start/256 && mask_length == (vl-(start/256)*256+255)/256)
          else $fatal(1,"Memory restart contract changed");
      if (case_kind inside {7,8})
        assert(mask_origin == 0 && mask_length == (vl+255)/256)
          else $fatal(1,"Slide stride contract changed");
      $display("PASS lane_mask");
    end
    $finish;
  end
endmodule
