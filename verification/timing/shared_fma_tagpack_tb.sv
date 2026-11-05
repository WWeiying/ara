// SPDX-License-Identifier: SHL-0.51
// Exact old/new FPU comparison, with independent input-tag ownership tracking.
module shared_fma_tagpack_tb;
  import fpnew_pkg::*;
  typedef struct packed {
    logic [15:0] serial;
    opgroup_e group_id;
    logic [63:0] operand_a;
    logic [7:0] flag_mask, control;
  } tag_t;
  localparam tag_t Keep = '{default:'1, operand_a:'0};
  localparam fpu_features_t Features = '{64, 1'b1, 1'b1, 6'b111000, 4'b1111};
  localparam fpu_implementation_t Impl = '{
    PipeRegs:'{'{default:5},'{default:3},'{default:1},'{default:2},'{default:0}},
    UnitTypes:'{'{default:PARALLEL},'{default:MERGED},'{default:PARALLEL},
                '{default:MERGED},'{default:DISABLED}}, PipeConfig:DISTRIBUTED};
  logic clk=0, rst=0, flush=0, offer=0, ready=0;
  logic iv;
  always #5 clk=~clk;
  logic [2:0][63:0] operands='0;
  operation_e op=ADD;
  fp_format_e fmt=FP32;
  roundmode_e rm=RNE;
  logic mod=0, vec=1;
  logic [3:0] mask='1;
  tag_t tag='0, tags[3];
  logic [2:0] ir, ov, busy;
  logic [63:0] results[3];
  status_t flags[3];
  for (genvar v=0; v<2; v++) begin : gen_new
    simd_fpnew #(.Features(Features),.Implementation(Impl),.TagType(tag_t),
      .SharedFma(1'b1),.SharedFmaTagKeepMask(v == 0 ? Keep : tag_t'('1)),
      .TrueSIMDClass(1'b1),.EnableSIMDMask(1'b1),.DivSqrtSel(THMULTI)) dut (
      .clk_i(clk),.rst_ni(rst),.hart_id_i('0),.operands_i(operands),.rnd_mode_i(rm),
      .op_i(op),.op_mod_i(mod),.src_fmt_i(fmt),.dst_fmt_i(fmt),.int_fmt_i(INT32),
      .vectorial_op_i(vec),.tag_i(tag),.simd_mask_i(mask),.in_valid_i(iv),
      .in_ready_o(ir[v]),.flush_i(flush),.result_o(results[v]),.status_o(flags[v]),
      .tag_o(tags[v]),.out_valid_o(ov[v]),.out_ready_i(ready),.busy_o(busy[v]));
  end
  simd_fpnew_prior #(.Features(Features),.Implementation(Impl),.TagType(tag_t),
    .SharedFma(1'b1),.TrueSIMDClass(1'b1),.EnableSIMDMask(1'b1),.DivSqrtSel(THMULTI)) prior (
    .clk_i(clk),.rst_ni(rst),.hart_id_i('0),.operands_i(operands),.rnd_mode_i(rm),
    .op_i(op),.op_mod_i(mod),.src_fmt_i(fmt),.dst_fmt_i(fmt),.int_fmt_i(INT32),
    .vectorial_op_i(vec),.tag_i(tag),.simd_mask_i(mask),.in_valid_i(iv),
    .in_ready_o(ir[2]),.flush_i(flush),.result_o(results[2]),.status_o(flags[2]),
    .tag_o(tags[2]),.out_valid_o(ov[2]),.out_ready_i(ready),.busy_o(busy[2]));

  tag_t expected[16384];
  bit pending[16384];
  int accepted=0, checked=0, aborted=0, cycles=0, blocked=0, multi_group=0;
  int count[4], op_count[10];
  int live=0, div_live=0;
  bit fired=0;
  // VMFPU serializes distinct instructions when either side is DIV/SQRT.
  // Preserve that integration contract; other groups still overlap here.
  assign iv = offer && (get_opgroup(op)==DIVSQRT ? live==0 : div_live==0);
  always @(posedge clk) begin
    fired = rst && !flush && iv && ir[2];
    if (!rst || flush) begin
      foreach (pending[i]) if (pending[i]) begin aborted++; pending[i]=0; end
      live=0; div_live=0;
    end else begin
      cycles++;
      if ({ir[0],ov[0],busy[0]} !== {ir[2],ov[2],busy[2]} ||
          {ir[1],ov[1],busy[1]} !== {ir[2],ov[2],busy[2]})
        $fatal(1,"TAGPACK control differs cycle=%0d",cycles);
      if (fired) begin
        if (pending[tag.serial]) $fatal(1,"TAGPACK duplicate input identity");
        pending[tag.serial]=1; expected[tag.serial]=tag; accepted++;
        live++; if(tag.group_id==DIVSQRT) div_live++;
        if (tag.serial>=90 && tag.serial<=120)
          $display("TAGPACK_INPUT cycle=%0d id=%0d group=%0d fmt=%0d op=%0d tag=%h",cycles,tag.serial,tag.group_id,fmt,op,tag);
      end
      if (ov[2]) begin
        if (!pending[tags[2].serial] || tags[2] !== expected[tags[2].serial])
          $fatal(1,"TAGPACK input/output ownership error cycle=%0d id=%0d pending=%b got=%h want=%h new=%h fullnew=%h",cycles,tags[2].serial,pending[tags[2].serial],tags[2],expected[tags[2].serial],tags[0],tags[1]);
        if (tags[1] !== tags[2] || tags[0] !==
            (tags[2].group_id == ADDMUL ? tags[2] & Keep : tags[2]))
          $fatal(1,"TAGPACK metadata error id=%0d group=%0d",tags[2].serial,tags[2].group_id);
        for (int v=0; v<2; v++) if ({results[v],flags[v]} !== {results[2],flags[2]})
          $fatal(1,"TAGPACK numeric/flags difference id=%0d",tags[2].serial);
        if (ready) begin
          if (tags[2].serial>=90 && tags[2].serial<=120)
            $display("TAGPACK_OUTPUT cycle=%0d id=%0d group=%0d tag=%h",cycles,tags[2].serial,tags[2].group_id,tags[2]);
          pending[tags[2].serial]=0; checked++; count[tags[2].group_id]++;
          live--; if(tags[2].group_id==DIVSQRT) div_live--;
        end else blocked++;
      end
      if ($countones(prior.gen_shared.valid)>1) multi_group++;
    end
  end

  function automatic logic [63:0] bits(input fp_format_e f, input int which);
    case (f)
      FP16: case (which)
        0:return {4{16'h3c00}}; 1:return {4{16'h7c00}};
        2:return {4{16'h7e00}}; 3:return {4{16'h7c01}};
        4:return {4{16'h0001}}; default:return {$urandom,$urandom};
      endcase
      FP32: case (which)
        0:return {2{32'h3f800000}}; 1:return {2{32'h7f800000}};
        2:return {2{32'h7fc00000}}; 3:return {2{32'h7f800001}};
        4:return {2{32'h00000001}}; default:return {$urandom,$urandom};
      endcase
      default: case (which)
        0:return 64'h3ff0000000000000; 1:return 64'h7ff0000000000000;
        2:return 64'h7ff8000000000000; 3:return 64'h7ff0000000000001;
        4:return 64'h0000000000000001; default:return {$urandom,$urandom};
      endcase
    endcase
  endfunction
  int serial=0, selector;
  initial begin
    repeat(3) @(negedge clk);
    rst=1;
    for (int c=0; c<12000; c++) begin
      @(negedge clk);
      flush=(c%503==502);
      rst=(c%2003!=2002);
      ready=c%101<21 ? 1'b0 : ($urandom_range(0,3)!=0);
      if (!rst || flush) offer=0;
      else if (!offer || fired) begin
        offer=($urandom_range(0,9)!=0);
        if (offer) begin
          selector=serial%10;
          case (selector)
            0:op=ADD; 1:op=MUL; 2:op=FMADD; 3:op=FNMSUB;
            4:op=CMP; 5:op=CLASSIFY; 6:op=F2I; 7:op=I2F;
            8:op=DIV; 9:op=SQRT;
          endcase
          op_count[selector]++;
          fmt=fp_format_e'(serial%3);
          rm=op==CMP ? roundmode_e'(serial%3) : roundmode_e'(serial%5);
          vec=serial%7!=0; mod=serial%2;
          mask=4'($urandom);
          for(int k=0;k<3;k++) operands[k]=bits(fmt,(serial+k)%7);
          tag='{16'(serial),get_opgroup(op),64'({$urandom,$urandom}),8'($urandom),8'($urandom)};
          // X in a non-consumed payload must neither hide control X nor corrupt other groups.
          if (serial%17==0) tag.operand_a[63:56]='x;
          serial++;
        end
      end
    end
    @(negedge clk); offer=0; flush=0; rst=1; ready=1;
    repeat(300) @(negedge clk);
    if (|busy || |ov) $fatal(1,"TAGPACK drain failed");
    foreach(pending[i]) if(pending[i]) $fatal(1,"TAGPACK lost request id=%0d",i);
    if (accepted!=checked+aborted || checked<500 || blocked<100 || multi_group<10)
      $fatal(1,"TAGPACK insufficient or incomplete traffic");
    for(int g=0;g<4;g++) if(count[g]<30) $fatal(1,"TAGPACK group not exercised %0d",g);
    $display("TAGPACK_PASS cycles=%0d accepted=%0d checked=%0d aborted=%0d blocked=%0d multi_group=%0d groups=%0d,%0d,%0d,%0d",
      cycles,accepted,checked,aborted,blocked,multi_group,count[0],count[1],count[2],count[3]);
    $finish;
  end
  initial begin #200000; $fatal(1,"TAGPACK timeout"); end
endmodule
