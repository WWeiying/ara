module ordered_add_equivalence_tb;
  import fpnew_pkg::*;
  logic clk=0; always #5 clk=~clk;
  logic rst_n=0;
  localparam fpu_features_t Features = '{Width:64, EnableVectors:1, EnableNanBox:1,
      FpFmtMask:6'b111000, IntFmtMask:4'b1111};
  localparam fpu_implementation_t Impl = '{
      PipeRegs:'{'{default:1},'{default:0},'{default:0},'{default:0},'{default:0}},
      UnitTypes:'{'{default:PARALLEL},'{default:DISABLED},'{default:DISABLED},'{default:DISABLED},'{default:DISABLED}},
      PipeConfig:BEFORE};
  logic [2:0][63:0] operands;
  logic [7:0] tag, tag_out[4];
  logic [3:0] mask;
  fp_format_e fmt;
  roundmode_e rm;
  operation_e op;
  logic valid, ready[4], out_valid[4], out_ready, busy[4];
  logic [63:0] result[4];
  status_t flags[4];
  for(genvar i=0;i<4;i++) begin:g
    localparam fpu_features_t ScalarFeatures = '{Width:64, EnableVectors:0, EnableNanBox:0,
        FpFmtMask:6'b111000, IntFmtMask:4'b1111};
    localparam fpu_implementation_t AfterImpl = '{PipeRegs:Impl.PipeRegs,
        UnitTypes:Impl.UnitTypes, PipeConfig:AFTER};
    localparam int MaskWidth = i>=2 ? 1 : 4;
    fpnew_top #(.Features(i>=2?ScalarFeatures:Features),.Implementation(i==3?AfterImpl:Impl),.TagType(logic[7:0]),
        .TrueSIMDClass(1),.EnableSIMDMask(1)) dut (
        .clk_i(clk),.rst_ni(rst_n),.hart_id_i('0),.flush_i(1'b0),
        .rnd_mode_i(rm),.op_i(i==0?op:ADD),.op_mod_i(1'b0),
        .vectorial_op_i(i<2),.operands_i(operands),.tag_i(tag),.simd_mask_i(MaskWidth'(mask)),
        .src_fmt_i(fmt),.dst_fmt_i(fmt),.int_fmt_i(INT64),
        .in_valid_i(valid),.in_ready_o(ready[i]),.result_o(result[i]),
        .status_o(flags[i]),.tag_o(tag_out[i]),.out_valid_o(out_valid[i]),
        .out_ready_i(out_ready),.busy_o(busy[i]));
  end
  function automatic logic [63:0] corner(fp_format_e f, int k);
    int w,e,m;
    logic [63:0] sign, expmask, fracmask;
    w=fp_width(f); e=exp_bits(f); m=man_bits(f);
    sign=64'b1<<(w-1); expmask=((64'b1<<e)-1)<<m; fracmask=(64'b1<<m)-1;
    case(k)
      0:return 0;
      1:return sign;
      2:return expmask;
      3:return expmask|sign;
      4:return expmask|1; // sNaN
      5:return expmask|(64'b1<<(m-1)); // qNaN
      6:return 1; // smallest subnormal
      7:return fracmask;
      8:return 64'b1<<m; // smallest normal
      9:return (expmask-(64'b1<<m))|fracmask; // max finite
      10:return ((64'b1<<(e-1))-1)<<m; // one
      default:return sign|(((64'b1<<(e-1))-1)<<m);
    endcase
  endfunction
  int accepted=0, retired=0, directed=0;
  always @(posedge clk) if(rst_n) begin
    if(valid && ready[0] !== ready[1]) $fatal(1,"input handshake mismatch");
    if(out_valid[0] !== out_valid[1]) $fatal(1,"latency/valid mismatch");
    for(int candidate=2; candidate<4; candidate++) begin
      if(valid && ready[0] !== ready[candidate]) $fatal(1,"candidate %0d input handshake mismatch",candidate);
      if(out_valid[0] !== out_valid[candidate]) $fatal(1,"candidate %0d latency mismatch",candidate);
      if(out_valid[0]) begin
        case(fp_format_e'(tag_out[0][7:5]))
          FP16: if(result[0][15:0] !== result[candidate][15:0]) $fatal(1,"candidate %0d FP16 mismatch",candidate);
          FP32: if(result[0][31:0] !== result[candidate][31:0]) $fatal(1,"candidate %0d FP32 mismatch",candidate);
          FP64: if(result[0] !== result[candidate]) $fatal(1,"candidate %0d FP64 mismatch",candidate);
        endcase
        if({flags[0],tag_out[0]} !== {flags[candidate],tag_out[candidate]})
          $fatal(1,"candidate %0d flags/tag mismatch",candidate);
      end
    end
    if(out_valid[0] && {result[0],flags[0],tag_out[0]} !== {result[1],flags[1],tag_out[1]})
      $fatal(1,"result/flags/tag mismatch");
    if(valid && ready[0]) accepted++;
    if(out_valid[0] && out_ready) retired++;
  end
  initial begin
    valid=0;out_ready=0;operands='0;mask='1;tag=0;fmt=FP32;rm=RNE;op=ADD;
    repeat(3) @(negedge clk); rst_n=1;
    for(int n=0;n<20000;n++) begin
      @(negedge clk);
      // Hold the entire request under backpressure.
      if(!valid || ready[0]) begin
        valid=directed<2160 ? 1 : ($urandom_range(0,7)!=0);
        op=valid?ADD:operation_e'($urandom_range(0,15));
        case($urandom_range(0,2))
          0:fmt=FP16;1:fmt=FP32;2:fmt=FP64;
        endcase
        rm=roundmode_e'($urandom_range(0,4));mask=$urandom_range(0,1) ? ((1 << (fp_width(fmt)/16))-1) : 0;tag={fmt,5'(n)};
        foreach(operands[j]) operands[j]={$urandom,$urandom};
        if(n%8==0) operands[1]='0;
        if(n%8==1) operands[2]=operands[1];
        if(n%8==2) operands[2]=~operands[1];
        if(n%8==3) operands[1]='1;
        if(directed<2160) begin
          case(directed/720) 0:fmt=FP16;1:fmt=FP32;2:fmt=FP64;endcase
          rm=roundmode_e'((directed/144)%5); tag={fmt,5'(directed)};
          operands[1]=corner(fmt,(directed/12)%12);
          operands[2]=corner(fmt,directed%12);
          mask=(1 << (fp_width(fmt)/16))-1;
          directed++;
        end
      end
      out_ready=($urandom_range(0,3)!=0);
    end
    @(negedge clk);out_ready=1;
    while(valid && !ready[0]) @(negedge clk);
    @(negedge clk);valid=0;
    repeat(10) @(negedge clk);
    if(accepted!=retired || accepted<1000) $fatal(1,"lost responses %0d %0d",accepted,retired);
    $display("PASS ordered ADD equivalence: %0d requests",accepted);$finish;
  end
  initial begin #1000000;$fatal(1,"timeout");end
endmodule
