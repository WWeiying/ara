// Differential combinational arithmetic test against the frozen real fpnew FMA.
module scalar_fp_add_case #(
  parameter fpnew_pkg::fp_format_e FpFormat = fpnew_pkg::FP32
)(output logic done_o);
  import fpnew_pkg::*;
  localparam int W = fp_width(FpFormat);
  localparam int E = exp_bits(FpFormat);
  localparam int M = man_bits(FpFormat);
  localparam logic [W-1:0] Sign = W'(1) << (W-1);
  localparam logic [W-1:0] Frac = (W'(1) << M)-1;
  localparam logic [W-1:0] Exp = ((W'(1) << E)-1) << M;
  logic [W-1:0] a, b, result, reference;
  logic [2:0][W-1:0] operands;
  roundmode_e rm;
  status_t status, reference_status;
  logic ready, valid;
  int unsigned count, random_pairs, seed;
  logic [63:0] rng;
  scalar_fp_add #(.FpFormat(FpFormat)) dut (
    .clk_i(1'b0), .rst_ni(1'b1), .a_i(a), .b_i(b), .rnd_mode_i(rm),
    .result_o(result), .status_o(status));
  assign operands = {b, a, {W{1'b0}}};
  fpnew_fma #(.FpFormat(FpFormat), .NumPipeRegs(0)) oracle (
    .clk_i(1'b0), .rst_ni(1'b1), .operands_i(operands), .is_boxed_i(3'b111),
    .rnd_mode_i(rm), .op_i(ADD), .op_mod_i(1'b0), .tag_i(1'b0),
    .mask_i(1'b1), .aux_i(1'b0), .in_valid_i(1'b1), .in_ready_o(ready),
    .flush_i(1'b0), .result_o(reference), .status_o(reference_status),
    .extension_bit_o(), .tag_o(), .mask_o(), .aux_o(), .out_valid_o(valid),
    .out_ready_i(1'b1), .busy_o());

  // Independent reproducible PRNG streams avoid scheduling-dependent $urandom state.
  function automatic logic [W-1:0] randword();
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    return W'(rng);
  endfunction
  function automatic logic [W-1:0] corner(int i);
    case (i)
      0: return '0;
      1: return Sign;
      2: return Exp;
      3: return Sign|Exp;
      4: return Exp|1; // signaling NaN
      5: return Sign|Exp|1;
      6: return Exp|(W'(1)<<(M-1));
      7: return Sign|Exp|Frac;
      8: return 1;
      9: return Sign|1;
      10: return Frac;
      11: return Sign|Frac;
      12: return W'(1)<<M;
      13: return Sign|(W'(1)<<M);
      14: return Exp-1; // maximum finite
      15: return Sign|(Exp-1);
      16: return W'(bias(FpFormat))<<M; // one
      17: return Sign|(W'(bias(FpFormat))<<M);
      18: return (W'(bias(FpFormat))<<M)|1;
      19: return W'(bias(FpFormat)-M-1)<<M; // half an ulp at one
      default: return W'(bias(FpFormat)-M)<<M;
    endcase
  endfunction
  task automatic check(input logic [W-1:0] x, y, input int mode);
    a=x; b=y; rm=roundmode_e'(mode);
    #1; // Allow the complete combinational oracle and candidate to settle.
    if (ready !== 1'b1 || valid !== 1'b1)
      $fatal(1,"SCALAR_FP_ADD_FAIL oracle handshake format=%0d", FpFormat);
    if ({result,status} !== {reference,reference_status})
      $fatal(1,"SCALAR_FP_ADD_FAIL format=%0d width=%0d test=%0d rm=%0d a=%h b=%h got=%h flags=%b expected=%h flags=%b",
        FpFormat,W,count,mode,x,y,result,status,reference,reference_status);
    count++;
  endtask
  task automatic all_modes(input logic [W-1:0] x, y);
    for(int mode=0;mode<6;mode++) check(x,y,mode);
  endtask
  initial begin : stimulus
    logic [W-1:0] x, y;
    int exponent;
    done_o=0; a=0; b=0; rm=RNE; count=0;
    random_pairs=100000; seed=32'h51ca1a;
    if ($value$plusargs("random_pairs=%d",random_pairs)) begin end
    if ($value$plusargs("seed=%d",seed)) begin end
    if (random_pairs<100000 && !$test$plusargs("smoke"))
      $fatal(1,"random_pairs must be >=100000 outside smoke runs");
    rng=64'hd1b54a32d192ed03 ^ (64'(seed)<<16) ^ W;
    // Full special-value Cartesian product in every supported rounding mode.
    for(int i=0;i<21;i++)
      for(int j=0;j<21;j++) all_modes(corner(i),corner(j));
    // Explicit cancellation, near cancellation, all exponent distances, and boundary sums.
    for(int i=0;i<($test$plusargs("smoke") ? 64 : 4096);i++) begin
      x=randword();
      if ((x&Exp)==Exp) x ^= W'(1)<<M;
      all_modes(x,x^Sign);
      all_modes(x,(x^Sign)^W'(1));
      exponent=i%((1<<E)-1);
      y=randword(); y=(y&~Exp)|(W'(exponent)<<M);
      all_modes(x,y);
      all_modes(x,(y&~Exp)|(x&Exp));
      all_modes(x,(y&~Exp)|(((x&Exp)+(W'(1)<<M))&Exp));
      all_modes(randword()&Frac,randword()&Frac);
      all_modes((Exp-1)-W'(i), (Exp-1)-W'(i));
    end
    // At least 100k arbitrary operand pairs per format, each in all six modes.
    for(int i=0;i<random_pairs;i++) begin
      x=randword(); y=randword(); all_modes(x,y);
    end
    $display("SCALAR_FP_ADD_CASE_PASS width=%0d checked=%0d random_pairs=%0d seed=%0d",W,count,random_pairs,seed);
    done_o=1;
  end
endmodule

module scalar_fp_add_tb;
  logic [2:0] done;
  scalar_fp_add_case #(.FpFormat(fpnew_pkg::FP16)) fp16(done[0]);
  scalar_fp_add_case #(.FpFormat(fpnew_pkg::FP32)) fp32(done[1]);
  scalar_fp_add_case #(.FpFormat(fpnew_pkg::FP64)) fp64(done[2]);
  initial begin
    wait (&done);
    $display("SCALAR_FP_ADD_PASS");
    $finish;
  end
  initial begin #1000000000; $fatal(1,"SCALAR_FP_ADD_FAIL timeout"); end
endmodule
