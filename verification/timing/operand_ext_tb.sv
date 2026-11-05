module operand_ext_case import ara_pkg::*; import rvv_pkg::*; import operand_ext_pkg::*;
  #(parameter int Support = 7, Depth = 5)(output bit done);
  localparam fpu_support_e FP = Support == 1 ? FPUSupportHalfSingleDouble : FPUSupportNone;
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, flush = 0, cmd_valid = 0, push = 0, issued = 0;
  logic [1:0] ready = 0;
  cmd_t cmd, forced_cmd;
  elen_t data = 0, actual, original, forced_data;
  logic [2:0] forced_select;
  logic valid, old_valid, credit, old_credit, pop, old_pop;
  target_fu_e target, old_target;
  int comb_checks = 0, transfers = 0, transactions = 0, aborted = 0;
  int random_state = 32'h5a35bf27 + Support;
  bit transaction_phase = 0;

  operand_queue #(.CmdBufDepth(4), .DataBufDepth(Depth), .NrSlaves(2), .NrLanes(4),
    .VLEN(1024), .AccessCmdPop(1), .FPUSupport(FP), .SupportIntExt2(Support&1),
    .SupportIntExt4((Support>>1)&1), .SupportIntExt8((Support>>2)&1),
    .SupportReduct(1), .SupportNtrVal(1), .operand_queue_cmd_t(cmd_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(flush), .lane_id_i(2'b0),
    .operand_queue_cmd_i(cmd), .operand_queue_cmd_valid_i(cmd_valid), .cmd_pop_o(pop),
    .operand_i(data), .operand_valid_i(push), .operand_issued_i(issued),
    .operand_queue_ready_o(credit), .operand_o(actual), .operand_target_fu_o(target),
    .operand_valid_o(valid), .operand_ready_i(ready));
  operand_queue_reference #(.CmdBufDepth(4), .DataBufDepth(Depth), .NrSlaves(2), .NrLanes(4),
    .VLEN(1024), .AccessCmdPop(1), .FPUSupport(FP), .SupportIntExt2(Support&1),
    .SupportIntExt4((Support>>1)&1), .SupportIntExt8((Support>>2)&1),
    .SupportReduct(1), .SupportNtrVal(1), .operand_queue_cmd_t(cmd_t)) ref_dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(flush), .lane_id_i(2'b0),
    .operand_queue_cmd_i(cmd), .operand_queue_cmd_valid_i(cmd_valid), .cmd_pop_o(old_pop),
    .operand_i(data), .operand_valid_i(push), .operand_issued_i(issued),
    .operand_queue_ready_o(old_credit), .operand_o(original), .operand_target_fu_o(old_target),
    .operand_valid_o(old_valid), .operand_ready_i(ready));

  function automatic int unsigned rng();
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return unsigned'(random_state);
  endfunction

  function automatic elen_t random_word();
    logic [31:0] lo, hi;
    lo=rng(); hi=rng();
    return {hi,lo};
  endfunction

  // Independent bit-index model; no calls into RTL shuffle/extension helpers.
  function automatic elen_t model(input elen_t raw, input cmd_t c, input int logical_byte);
    int factor, width, physical_byte, output_width, source_base;
    bit sign_mode, supported;
    elen_t result;
    factor = (int'(c.conv)+1)/2;
    factor = 1 << factor;
    width = 8 << int'(c.eew);
    sign_mode = int'(c.conv)%2 == 0;
    supported = (factor==2 && (Support&1)) || (factor==4 && (Support&2)) || (factor==8 && (Support&4));
    if (c.conv < OpQueueConversionZExt2 || c.conv > OpQueueConversionSExt8 ||
        !supported || width*factor > 64) return raw;
    case (c.eew)
      EW8: physical_byte = ((logical_byte&1)<<2) | (logical_byte&2) | ((logical_byte&4)>>2);
      EW16: physical_byte = (logical_byte&1) | ((logical_byte&2)<<1) | ((logical_byte&4)>>1);
      default: physical_byte = logical_byte;
    endcase
    output_width = width*factor;
    for (int bit_idx = 0; bit_idx < 64; bit_idx++) begin
      source_base = (bit_idx/output_width)*output_width + physical_byte*8;
      if (bit_idx%output_width < width) result[bit_idx] = raw[source_base+bit_idx%output_width];
      else result[bit_idx] = sign_mode ? raw[source_base+width-1] : 1'b0;
    end
    return result;
  endfunction

  always @(posedge clk) if (rst_n && transaction_phase) begin
    if ({valid,credit,pop} !== {old_valid,old_credit,old_pop}) $fatal(1,"EXT_HANDSHAKE_MISMATCH");
    if (valid && (actual !== original || target !== old_target)) $fatal(1,"EXT_STREAM_MISMATCH");
    if (dut.select_q !== ref_dut.select_q || dut.elem_count_q !== ref_dut.elem_count_q ||
        dut.ibuf_pop !== ref_dut.ibuf_pop || dut.ibuf_usage_q !== ref_dut.ibuf_usage_q)
      $fatal(1,"EXT_STATE_MISMATCH");
  end

  task automatic transact(input opqueue_conversion_e conv, input vew_e sew, input int count,
                          input bit cancel);
    elen_t words[128];
    int factor, elements_per_word, per_output, word_count, sent, consumed, age;
    bit pending, new_issue, finished;
    elen_t pending_data, expected;
    factor = conv == OpQueueConversionNone ? 1 : (1 << ((int'(conv)+1)/2));
    elements_per_word = 8 >> int'(sew); per_output = elements_per_word/factor;
    word_count = (count+elements_per_word-1)/elements_per_word;
    foreach (words[i]) words[i] = random_word();
    cmd = '{eew:sew, elem_count:11'(count), conv:conv, ntr_red:0, is_reduct:0, target_fu:ALU_SLDU};
    cmd_valid = 1; ready = 0; push = 0; issued = 0;
    @(negedge clk); cmd_valid = 0;
    sent=0; consumed=0; age=0; pending=0; finished=0;
    while (!finished) begin
      if (age > 2048) $fatal(1,"EXT_TRANSACTION_TIMEOUT support=%0d conv=%0d",Support,conv);
      ready = (age%7 < 3) ? 0 : (age%2 ? 2'b01 : 2'b10);
      push = pending; data = pending_data;
      new_issue = sent < word_count && credit && age%5 != 1;
      issued = new_issue;
      if (new_issue) begin pending_data = words[sent]; sent++; end
      pending = new_issue;
      @(posedge clk);
      if (valid) begin
        expected = model(words[consumed/elements_per_word], cmd,
          ((consumed%elements_per_word)/per_output)*(8/factor));
        // SupportNtrVal queues zero inactive tail bytes even for None/non-reduction.
        // Those bytes are compared too, rather than masked out of the checker.
        if (conv==OpQueueConversionNone && count-consumed<elements_per_word) begin
          for (int b=0;b<8;b++) if ((b>>int'(sew))>=count-consumed) begin
            int physical_byte;
            case(sew)
              EW8: physical_byte=((b&1)<<2)|(b&2)|((b&4)>>2);
              EW16: physical_byte=(b&1)|((b&2)<<1)|((b&4)>>1);
              default: physical_byte=b;
            endcase
            expected[8*physical_byte+:8]='0;
          end
        end
        if (actual !== expected) $fatal(1,"EXT_ORACLE_MISMATCH support=%0d conv=%0d sew=%0d index=%0d got=%h expected=%h cmd_in=%h cmd_dut=%h cmd_ref=%h buf=%h select=%0d elem=%0d",
          Support,conv,sew,consumed,actual,expected,cmd,dut.cmd,ref_dut.cmd,dut.ibuf_operand,dut.select_q,dut.elem_count_q);
        if (|ready) begin consumed+=per_output; transfers++; end
      end
      if (pop) begin
        if (consumed < count || pending || sent != word_count) $fatal(1,"EXT_EARLY_COMPLETION");
        finished=1;
      end
      @(negedge clk); age++;
      if (cancel && age==6) begin
        flush=1; push=0; issued=0; ready=0; pending=0;
        @(negedge clk); flush=0; aborted++; finished=1;
      end
    end
    push=0; issued=0; ready=0;
    @(negedge clk);
    if (valid || !credit) $fatal(1,"EXT_DRAIN_OR_FLUSH_FAILURE");
    transactions++;
  endtask

  initial begin
    done=0; cmd='0; forced_cmd='0; forced_select=0; forced_data=0;
    force dut.cmd = forced_cmd; force ref_dut.cmd = forced_cmd;
    force dut.select_q = forced_select; force ref_dut.select_q = forced_select;
    force dut.ibuf_operand = forced_data; force ref_dut.ibuf_operand = forced_data;
    for (int c=0;c<NumConversions;c++) for (int w=0;w<4;w++)
      for (int sel=0;sel<8;sel++) for (int n=0;n<128;n++) begin
        forced_cmd='{eew:vew_e'(w),elem_count:11'(1+n%33),conv:opqueue_conversion_e'(c),
          ntr_red:2'(n),is_reduct:1'(n),target_fu:target_fu_e'(n%2)};
        forced_select=3'(sel); forced_data=random_word();
        case(n%16)
          0: forced_data='0;
          1: forced_data='1;
          2: forced_data=64'h8000800080008000;
          3: forced_data=64'h7fff7fff7fff7fff;
          4: forced_data=64'h8080808080808080;
          5: forced_data=64'h7f7f7f7f7f7f7f7f;
          6: forced_data[31:24]='x;
          7: forced_data[63]='x;
          default:;
        endcase
        #1;
        if (dut.conv_operand !== ref_dut.conv_operand) $fatal(1,"EXT_COMB_MISMATCH support=%0d conv=%0d sew=%0d sel=%0d",Support,c,w,sel);
        if (c>=1 && c<=6 && dut.conv_operand !== model(forced_data,forced_cmd,sel))
          $fatal(1,"EXT_COMB_ORACLE_MISMATCH support=%0d conv=%0d sew=%0d sel=%0d",Support,c,w,sel);
        comb_checks++;
      end
    release dut.cmd; release ref_dut.cmd;
    release dut.select_q; release ref_dut.select_q;
    release dut.ibuf_operand; release ref_dut.ibuf_operand;
    repeat(2) @(negedge clk);
    rst_n=1; transaction_phase=1;
    for (int c=0;c<=6;c++) for (int w=0;w<4;w++) begin
      int factor, flag;
      factor=c==0 ? 1 : 1<<((c+1)/2); flag=c==0 ? 0 : ((c+1)/2)-1;
      if ((c==0 || (Support&(1<<flag))) && (8<<w)*factor<=64) begin
        for (int n=1;n<=33;n++) transact(opqueue_conversion_e'(c),vew_e'(w),n,0);
        transact(opqueue_conversion_e'(c),vew_e'(w),128,1);
        transact(opqueue_conversion_e'(c),vew_e'(w),17,0);
      end
    end
    $display("OPERAND_EXT_CASE_PASS support=%0d depth=%0d comb=%0d transactions=%0d transfers=%0d aborted=%0d",
      Support,Depth,comb_checks,transactions,transfers,aborted);
    done=1;
  end
endmodule

module operand_ext_tb;
  wire [7:0] done;
  for(genvar s=0;s<8;s++) begin : gen_cases
    operand_ext_case #(.Support(s),.Depth(s==0 ? 1 : s==1 ? 2 : 5)) i_case(done[s]);
  end
  initial begin wait(&done); $display("OPERAND_EXT_PASS"); $finish; end
  initial begin #5000000; $fatal(1,"OPERAND_EXT_WATCHDOG"); end
endmodule
