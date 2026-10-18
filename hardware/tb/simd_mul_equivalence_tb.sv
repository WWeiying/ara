`timescale 1ns/1ps
module simd_mul_equivalence_case import ara_pkg::*; import rvv_pkg::*; #(
  parameter int Width=0, Pipe=0, Fixed=1
)(output logic done_o);
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  elen_t operand_a_i, operand_b_i, operand_c_i;
  logic [7:0] mask_i;
  ara_op_e op_i;
  vxrm_t vxrm_i;
  logic valid_i, ready_i;
  elen_t result[2];
  logic [7:0] masks[2];
  vxsat_t sat[2];
  logic ready[2], valid[2];
  int checked=0, stalls=0, accepted=0;
  int op_count[9];
  simd_mul_reference #(.ElementWidth(vew_e'(Width)), .NumPipeRegs(Pipe),
    .FixPtSupport(fixpt_support_e'(Fixed))) reference_dut (
    .result_o(result[0]), .mask_o(masks[0]), .vxsat_o(sat[0]),
    .ready_o(ready[0]), .valid_o(valid[0]), .*);
  simd_mul #(.ElementWidth(vew_e'(Width)), .NumPipeRegs(Pipe),
    .FixPtSupport(fixpt_support_e'(Fixed))) candidate (
    .result_o(result[1]), .mask_o(masks[1]), .vxsat_o(sat[1]),
    .ready_o(ready[1]), .valid_o(valid[1]), .*);
  task automatic check;
    if ({result[0],masks[0],sat[0],ready[0],valid[0]} !==
        {result[1],masks[1],sat[1],ready[1],valid[1]})
      $fatal(1,"SIMD_MUL_FAIL width=%0d pipe=%0d fixed=%0d check=%0d op=%0d",Width,Pipe,Fixed,checked,op_i);
    checked++;
  endtask
  task automatic drive(input int n, input bit directed);
    int which;
    which=directed ? (n/32)%9 : $urandom_range(0,8);
    op_i=ara_op_e'(int'(VMUL)+which);
    vxrm_i=2'(directed ? (n/8)%4 : $urandom);
    mask_i=8'(directed ? n : $urandom);
    operand_a_i={$urandom,$urandom};
    operand_b_i={$urandom,$urandom};
    operand_c_i={$urandom,$urandom};
    if (directed) begin
      case(n%8)
        0: begin operand_a_i=0; operand_b_i='1; operand_c_i='1; end
        1: begin operand_a_i='1; operand_b_i='1; operand_c_i=0; end
        2: begin operand_a_i=64'h8080808080808080; operand_b_i=operand_a_i; operand_c_i=operand_a_i; end
        3: begin operand_a_i=64'h8000800080008000; operand_b_i=operand_a_i; operand_c_i=0; end
        4: begin operand_a_i=64'h8000000080000000; operand_b_i=operand_a_i; operand_c_i='1; end
        5: begin operand_a_i=64'h8000000000000000; operand_b_i=operand_a_i; operand_c_i=1; end
        6: begin operand_a_i=64'h7f7fff7fffffff7f; operand_b_i='1; operand_c_i=operand_a_i; end
        7: begin operand_a_i=64'h0123456789abcdef; operand_b_i=64'hfedcba9876543210; operand_c_i=64'haaaaaaaaaaaaaaaa; end
      endcase
    end
  endtask
  initial begin
    done_o=0; operand_a_i=0; operand_b_i=0; operand_c_i=0;
    op_i=VMUL; vxrm_i=0; mask_i=0; valid_i=0; ready_i=0;
    for(int o=0;o<9;o++) op_count[o]=0;
    repeat(3) @(negedge clk_i);
    rst_ni=1;
    // Every op and rounding mode with zero, extrema and wraparound patterns.
    for(int n=0;n<288;n++) begin
      @(negedge clk_i); ready_i=1; valid_i=1; drive(n,1);
      #1; check(); @(posedge clk_i); #1; check();
    end
    // Hold the producer payload during stalls; vary sink readiness, bubbles,
    // reset during traffic, masks, operands, operation and rounding mode.
    for(int n=0;n<20000;n++) begin
      @(negedge clk_i);
      if(!(valid_i && !ready[0])) begin
        valid_i=($urandom_range(0,4)!=0); drive(n,0);
      end
      ready_i=(n%113<12) ? 0 : ($urandom_range(0,3)!=0);
      rst_ni=(n%997!=0);
      #1; check();
      if(valid_i && ready[0]) begin accepted++; op_count[int'(op_i)-int'(VMUL)]++; end
      if(valid[0] && !ready_i) stalls++;
      @(posedge clk_i); #1; check();
    end
    @(negedge clk_i); rst_ni=1; valid_i=0; ready_i=1;
    repeat(5) begin @(posedge clk_i); #1; check(); end
    for(int o=0;o<9;o++) if(op_count[o]==0) $fatal(1,"Missing op coverage %0d",o);
    if(stalls==0 || accepted==0) $fatal(1,"Missing handshake coverage");
    $display("SIMD_MUL_CASE_PASS width=%0d pipe=%0d fixed=%0d checked=%0d accepted=%0d stalls=%0d",Width,Pipe,Fixed,checked,accepted,stalls);
    done_o=1;
  end
endmodule
module simd_mul_equivalence_tb;
  logic [23:0] done;
  for(genvar w=0;w<4;w++) begin:g_w
    for(genvar p=0;p<3;p++) begin:g_p
      for(genvar f=0;f<2;f++) begin:g_f
        simd_mul_equivalence_case #(.Width(w),.Pipe(p),.Fixed(f)) test_case(.done_o(done[w*6+p*2+f]));
      end
    end
  end
  initial begin
    wait(&done); $display("SIMD_MUL_EQUIVALENCE_PASS configs=24 cycles_per_config=20288"); $finish;
  end
  initial begin #1000000; $fatal(1,"SIMD_MUL_TIMEOUT"); end
endmodule
