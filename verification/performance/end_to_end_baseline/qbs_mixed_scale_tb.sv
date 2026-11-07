module qbs_mixed_scale_tb;
  timeunit 1ns;
  timeprecision 1ps;
  typedef logic [19:0] tag_t;
  logic clk=0;
  always #5ns clk=~clk;
  logic rst_n=1, clear=0, valid=0;
  logic [31:0] a=0, w=0, result;
  logic eligible, result_valid, busy, ref_ready, ref_valid;
  logic [4:0] flags;
  tag_t tag=0, result_tag, ref_tag;
  logic [2:0][31:0] operands;
  logic [31:0] ref_result;
  fpnew_pkg::status_t ref_flags;
  bit pvalid[2]='{default:0};
  logic [31:0] expected[2];
  logic [4:0] expected_flags[2];
  tag_t expected_tag[2];
  int unsigned cases=0, admitted=0, rejected=0, checked=0, cancelled=0;
  int unsigned bubbles=0, resets=0, clears=0, streak=0, longest=0;

  qbs_mixed_scale #(.TagWidth(20)) dut (
    .clk_i(clk), .rst_ni(rst_n), .clear_i(clear), .valid_i(valid),
    .activation_i(a), .weight_i(w), .tag_i(tag), .eligible_o(eligible),
    .valid_o(result_valid), .result_o(result), .fflags_o(flags), .tag_o(result_tag), .busy_o(busy)
  );
  assign operands={32'b0,w,a};
  fpnew_fma #(
    .FpFormat(fpnew_pkg::FP32), .NumPipeRegs(3), .PipeConfig(fpnew_pkg::AFTER),
    .TagType(tag_t), .AuxType(logic)
  ) reference_mul (
    .clk_i(clk), .rst_ni(rst_n), .operands_i(operands), .is_boxed_i(3'b111),
    .rnd_mode_i(fpnew_pkg::RNE), .op_i(fpnew_pkg::MUL), .op_mod_i(1'b0),
    .tag_i(tag), .mask_i(1'b1), .aux_i(1'b0), .in_valid_i(valid), .in_ready_o(ref_ready),
    .flush_i(clear), .result_o(ref_result), .status_o(ref_flags), .extension_bit_o(),
    .tag_o(ref_tag), .mask_o(), .aux_o(), .out_valid_o(ref_valid), .out_ready_i(1'b1), .busy_o()
  );

  task automatic cycle(input bit present, input logic [31:0] av,wv,
                       input bit accepted, input logic [31:0] golden,
                       input logic [4:0] golden_flags, input tag_t identity);
    @(negedge clk);
    a=av; w=wv; tag=identity; valid=present && accepted;
    #1ns;
    if (present)
      assert (eligible === accepted)
        else $fatal(1,"MIXED_SCALE_GATE_FAIL a=%h w=%h expected=%b actual=%b",a,w,accepted,eligible);
    @(posedge clk);
    assert (ref_ready === 1'b1) else $fatal(1,"Reference unexpectedly backpressured");
    #1ns;
    assert (result_valid === pvalid[1] && ref_valid === pvalid[1])
      else $fatal(1,"MIXED_SCALE_LATENCY_FAIL case=%0d dut=%b ref=%b expected=%b",cases,result_valid,ref_valid,pvalid[1]);
    assert (busy === (valid | pvalid[0] | pvalid[1])) else $fatal(1,"Mixed scale busy mismatch");
    if (pvalid[1]) begin
      assert (result_tag === expected_tag[1] && ref_tag === expected_tag[1])
        else $fatal(1,"Mixed scale tag mismatch");
      assert (result === expected[1] && ref_result === expected[1] &&
              flags === expected_flags[1] && ref_flags === expected_flags[1])
        else $fatal(1,"MIXED_SCALE_VALUE_FAIL tag=%0d result=%h ref=%h host=%h flags=%b ref_flags=%b expected=%b",
                    result_tag,result,ref_result,expected[1],flags,ref_flags,expected_flags[1]);
      checked++;
    end
    pvalid[1]=pvalid[0]; expected[1]=expected[0]; expected_flags[1]=expected_flags[0]; expected_tag[1]=expected_tag[0];
    pvalid[0]=valid; expected[0]=golden; expected_flags[0]=golden_flags; expected_tag[0]=identity;
    if (present) begin
      cases++;
      if (accepted) admitted++; else rejected++;
    end else bubbles++;
    streak=valid ? streak+1 : 0;
    if (streak>longest) longest=streak;
  endtask

  task automatic cancel(input bit async_reset);
    @(negedge clk);
    valid=0; cancelled+=int'(pvalid[0])+int'(pvalid[1]);
    if (async_reset) begin rst_n=0; resets++; end
    else begin clear=1; clears++; end
    @(posedge clk); #1ns;
    assert (result_valid === 1'b0 && busy === 1'b0 && ref_valid === 1'b0)
      else $fatal(1,"Mixed scale reset/clear failed");
    pvalid[0]=0; pvalid[1]=0; streak=0;
    @(negedge clk); rst_n=1; clear=0;
  endtask

  initial begin
    string filename;
    int file, count, allow;
    logic [31:0] av,wv,golden,golden_flags;
    assert ($value$plusargs("VECTORS=%s",filename)) else $fatal(1,"Missing vectors");
    file=$fopen(filename,"r"); assert(file) else $fatal(1,"Cannot open vectors");
    cancel(1);
    while (!$feof(file)) begin
      count=$fscanf(file,"%h %h %d %h %h\n",av,wv,allow,golden,golden_flags);
      assert (count==5 && allow inside {0,1}) else $fatal(1,"Malformed independent vector");
      cycle(1,av,wv,1'(allow),golden,golden_flags[4:0],tag_t'(cases));
      if (cases%4096==0) cancel(1);
      else if (cases%1024==0) cancel(0);
      else if (cases%127==0) cycle(0,32'h7fc00000,32'hff800000,0,'x,'x,'x);
    end
    $fclose(file);
    repeat (4) cycle(0,32'h7fc00000,32'hff800000,0,'x,'x,'x);
    assert (cases==110025 && admitted>50000 && rejected>0 && admitted==checked+cancelled &&
            longest>=16 && resets>1 && clears>1 && !busy)
      else $fatal(1,"Mixed scale work/cancellation/II1 coverage incomplete");
    $display("MIXED_SCALE_RTL_PASS total=%0d admitted=%0d rejected=%0d checked=%0d cancelled=%0d bubbles=%0d resets=%0d clears=%0d longest_ii1=%0d latency=3 host_bits=1 fpnew_bits=1 flags=1",
             cases,admitted,rejected,checked,cancelled,bubbles,resets,clears,longest);
    $finish;
  end
  initial begin #20ms; $fatal(1,"Mixed scale component watchdog"); end
endmodule
