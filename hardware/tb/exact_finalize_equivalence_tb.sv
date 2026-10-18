`timescale 1ns/1ps
module exact_finalize_equivalence_tb;
  logic signed [287:0] exact_value_i;
  logic [3:0] special_i;
  logic source_seen_i, finite_nonzero_seen_i, pos_zero_seen_i, neg_zero_seen_i;
  logic seed_valid_i, seed_in_exact_i, format_fp16_i;
  logic [31:0] seed_i;
  logic [2:0] rnd_mode_i;
  logic [31:0] result[5];
  logic [4:0] status[5];
  int checked=0;
  fp32_exact_reduction_finalize_reference original (
    .result_o(result[0]), .status_o(status[0]), .*);
  for (genvar i=0;i<2;i++) begin:g
    fp32_exact_reduction_finalize #(.SharedExtract(i==1)) candidate (
      .result_o(result[i+1]), .status_o(status[i+1]), .*);
  end
  // Exercise the new seed/root timing boundary as a separate combinational
  // composition. Forward seed_in_exact_i so pre-inserted seeds stay untouched.
  logic signed [287:0] seeded_exact;
  logic [3:0] seeded_special;
  logic seeded_nonzero, seeded_pos_zero, seeded_neg_zero;
  fp32_exact_reduction_seed seed_stage (
    .seed_fixed_o(),
    .exact_value_o(seeded_exact), .special_o(seeded_special),
    .finite_nonzero_seen_o(seeded_nonzero), .pos_zero_seen_o(seeded_pos_zero),
    .neg_zero_seen_o(seeded_neg_zero), .*);
  for (genvar i=0;i<2;i++) begin:seeded
    fp32_exact_reduction_finalize #(.SharedExtract(i==1)) candidate (
      .exact_value_i(seeded_exact), .special_i(seeded_special),
      .finite_nonzero_seen_i(seeded_nonzero), .pos_zero_seen_i(seeded_pos_zero),
      .neg_zero_seen_i(seeded_neg_zero), .seed_in_exact_i(1'b1),
      .result_o(result[i+3]), .status_o(status[i+3]), .*);
  end
  task automatic check;
    #1;
    for (int i=1;i<5;i++)
      if ({result[i],status[i]} !== {result[0],status[0]})
        $fatal(1,"case=%0d candidate=%0d exact=%h fmt=%b rm=%b seed=%h seedvalid=%b inexact=%b special=%h got=%h/%h ref=%h/%h",checked,i,exact_value_i,format_fp16_i,rnd_mode_i,seed_i,seed_valid_i,seed_in_exact_i,special_i,result[i],status[i],result[0],status[0]);
    checked++;
  endtask
  initial begin
    exact_value_i=0; special_i=0; source_seen_i=1; finite_nonzero_seen_i=1;
    pos_zero_seen_i=0; neg_zero_seen_i=0; seed_valid_i=0; seed_in_exact_i=0; seed_i=0;
    // Every leading-bit position, both signs, rounding carry and sticky patterns.
    for (int f=0;f<2;f++) begin
      format_fp16_i=1'(f);
      for (int rm=0;rm<8;rm++) begin
        rnd_mode_i=3'(rm);
        for (int bitpos=0;bitpos<287;bitpos++) begin
          for (int pattern=0;pattern<4;pattern++) begin
            exact_value_i=288'b1 << bitpos;
            case(pattern)
              1: exact_value_i-=1;
              2: exact_value_i+=1;
              3: if(bitpos>1) exact_value_i|=(288'b1<<(bitpos-1))|1;
            endcase
            check(); exact_value_i=-exact_value_i; check();
          end
        end
      end
    end
    // Arbitrary internal states deliberately include more than reachable FP16 sums.
    for (int n=0;n<20000;n++) begin
      for(int w=0;w<9;w++) exact_value_i[w*32+:32]=$urandom;
      if(n%4==0) exact_value_i=0;
      special_i=4'($urandom);source_seen_i=1'($urandom);
      finite_nonzero_seen_i=1'($urandom);pos_zero_seen_i=1'($urandom);neg_zero_seen_i=1'($urandom);
      seed_valid_i=1'($urandom);seed_in_exact_i=1'($urandom);
      format_fp16_i=1'($urandom);rnd_mode_i=3'($urandom);seed_i=$urandom;
      case(n%8)
        0:seed_i=format_fp16_i?32'h7c00:32'h7f800000;
        1:seed_i=format_fp16_i?32'hfc00:32'hff800000;
        2:seed_i=format_fp16_i?32'h7c01:32'h7f800001;
        3:seed_i=format_fp16_i?32'h7e00:32'h7fc00000;
        4:seed_i=0;
        5:seed_i=format_fp16_i?32'h8000:32'h80000000;
      endcase
      check();
    end
    $display("EXACT_FINALIZE_EQUIVALENCE_PASS cases=%0d",checked);$finish;
  end
endmodule
