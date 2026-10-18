// Runtime-format differential test against real, unpipelined fpnew FMA ADDs.
module shared_scalar_fp_add_tb;
  import fpnew_pkg::*;
  logic [63:0] a, b, result;
  fp_format_e fmt;
  roundmode_e rm;
  status_t status;
  logic [2:0][63:0] reference;
  status_t [2:0] reference_status;
  logic [2:0] ready, valid;
  int unsigned count[3], random_pairs, seed;
  logic [63:0] rng;
  shared_scalar_fp_add dut (.clk_i(1'b0), .rst_ni(1'b1), .a_i(a), .b_i(b),
    .format_i(fmt), .rnd_mode_i(rm), .result_o(result), .status_o(status));
  for (genvar f=0; f<3; f++) begin : gen_oracle
    localparam fp_format_e Fmt = f==0 ? FP16 : f==1 ? FP32 : FP64;
    localparam int W=fp_width(Fmt);
    logic [2:0][W-1:0] operands;
    logic [W-1:0] res;
    assign operands = {b[W-1:0],a[W-1:0],{W{1'b0}}};
    assign reference[f] = {{(64-W){1'b1}},res};
    fpnew_fma #(.FpFormat(Fmt), .NumPipeRegs(0)) oracle (
      .clk_i(1'b0), .rst_ni(1'b1), .operands_i(operands), .is_boxed_i(3'b111),
      .rnd_mode_i(rm), .op_i(ADD), .op_mod_i(1'b0), .tag_i(1'b0),
      .mask_i(1'b1), .aux_i(1'b0), .in_valid_i(1'b1), .in_ready_o(ready[f]),
      .flush_i(1'b0), .result_o(res), .status_o(reference_status[f]),
      .extension_bit_o(), .tag_o(), .mask_o(), .aux_o(), .out_valid_o(valid[f]),
      .out_ready_i(1'b1), .busy_o());
  end
  function automatic fp_format_e format_of(int f);
    return f==0 ? FP16 : f==1 ? FP32 : FP64;
  endfunction
  function automatic logic [63:0] randword();
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    return rng;
  endfunction
  function automatic logic [63:0] mask(int f);
    return f==0 ? 64'hffff : f==1 ? 64'hffffffff : '1;
  endfunction
  function automatic logic [63:0] corner(int f, int i);
    int w,e,m;
    logic [63:0] s,frac,ex;
    w=fp_width(format_of(f)); e=exp_bits(format_of(f)); m=man_bits(format_of(f));
    s=64'(1)<<(w-1); frac=(64'(1)<<m)-1; ex=((64'(1)<<e)-1)<<m;
    case (i)
      0: return 0;
      1: return s;
      2: return ex;
      3: return s|ex;
      4: return ex|1;
      5: return s|ex|1;
      6: return ex|(64'(1)<<(m-1));
      7: return s|ex|frac;
      8: return 1;
      9: return s|1;
      10: return frac;
      11: return s|frac;
      12: return 64'(1)<<m;
      13: return s|(64'(1)<<m);
      14: return ex-1;
      15: return s|(ex-1);
      16: return 64'(bias(format_of(f)))<<m;
      17: return s|(64'(bias(format_of(f)))<<m);
      18: return (64'(bias(format_of(f)))<<m)|1;
      19: return 64'(bias(format_of(f))-m-1)<<m;
      default: return 64'(bias(format_of(f))-m)<<m;
    endcase
  endfunction
  task automatic check(int f, logic [63:0] x,y, int mode);
    // Random upper bits explicitly exercise unboxed input acceptance.
    a=(x&mask(f))|(randword()&~mask(f));
    b=(y&mask(f))|(randword()&~mask(f));
    fmt=format_of(f); rm=roundmode_e'(mode);
    #1;
    if (ready[f] !== 1'b1 || valid[f] !== 1'b1)
      $fatal(1,"SHARED_SCALAR_FP_ADD_FAIL oracle handshake format=%0d",fmt);
    if ({result,status} !== {reference[f],reference_status[f]})
      $fatal(1,"SHARED_SCALAR_FP_ADD_FAIL format=%0d width=%0d test=%0d rm=%0d a=%h b=%h got=%h flags=%b expected=%h flags=%b",
        fmt,fp_width(fmt),count[f],mode,a,b,result,status,reference[f],reference_status[f]);
    count[f]++;
  endtask
  task automatic all_formats_modes(logic [2:0][63:0] x,y);
    int rotation,f;
    for(int mode=0;mode<6;mode++) begin
      rotation=int'(randword()%3);
      for(int j=0;j<3;j++) begin
        f=(j+rotation)%3;
        check(f,x[f],y[f],mode);
      end
    end
  endtask
  initial begin : stimulus
    logic [2:0][63:0] x,y;
    logic [63:0] s,ex,frac;
    int e,m,exponent;
    a=0;b=0;fmt=FP64;rm=RNE;
    for(int f=0;f<3;f++) count[f]=0;
    random_pairs=100000;seed=32'h51ca1a;
    if ($value$plusargs("random_pairs=%d",random_pairs)) begin end
    if ($value$plusargs("seed=%d",seed)) begin end
    if(random_pairs<100000 && !$test$plusargs("smoke")) $fatal(1,"full requires >=100000 pairs");
    rng=64'hd1b54a32d192ed03 ^ (64'(seed)<<16);
    for(int i=0;i<21;i++) for(int j=0;j<21;j++) begin
      for(int f=0;f<3;f++) begin x[f]=corner(f,i);y[f]=corner(f,j);end
      all_formats_modes(x,y);
    end
    for(int i=0;i<($test$plusargs("smoke")?64:4096);i++) begin
      for(int kind=0;kind<7;kind++) begin
        for(int f=0;f<3;f++) begin
          e=exp_bits(format_of(f));m=man_bits(format_of(f));
          s=64'(1)<<(fp_width(format_of(f))-1);ex=((64'(1)<<e)-1)<<m;frac=(64'(1)<<m)-1;
          x[f]=randword()&mask(f);
          if((x[f]&ex)==ex) x[f]^=64'(1)<<m;
          y[f]=randword()&mask(f);
          exponent=i%((1<<e)-1);
          case(kind)
            0:y[f]=x[f]^s;
            1:y[f]=(x[f]^s)^64'(1);
            2:y[f]=(y[f]&~ex)|(64'(exponent)<<m);
            3:y[f]=(y[f]&~ex)|(x[f]&ex);
            4:y[f]=(y[f]&~ex)|(((x[f]&ex)+(64'(1)<<m))&ex);
            5:begin x[f]&=frac;y[f]&=frac;end
            6:begin x[f]=(ex-1)-64'(i);y[f]=x[f];end
          endcase
        end
        all_formats_modes(x,y);
      end
    end
    for(int i=0;i<random_pairs;i++) begin
      for(int f=0;f<3;f++) begin x[f]=randword();y[f]=randword();end
      all_formats_modes(x,y);
    end
    for(int f=0;f<3;f++)
      $display("SHARED_SCALAR_FP_ADD_CASE_PASS width=%0d checked=%0d random_pairs=%0d seed=%0d",fp_width(format_of(f)),count[f],random_pairs,seed);
    $display("SHARED_SCALAR_FP_ADD_PASS");$finish;
  end
  initial begin #1000000000;$fatal(1,"SHARED_SCALAR_FP_ADD_FAIL timeout");end
endmodule
