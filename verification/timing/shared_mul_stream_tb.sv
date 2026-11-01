// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module shared_mul_stream_tb;
  import ara_pkg::*; import rvv_pkg::*;
  logic clk=0, rst=0;
  always #5 clk=~clk;
  logic [63:0] a,b,c;
  logic [7:0] mask;
  ara_op_e op;
  vxrm_t rm;
  logic [1:0] sew;
  logic [3:0] valid,ready,consume,out_valid;
  logic [3:0][63:0] result;
  logic [3:0][7:0] masks,sat;
  extracted_shared_mul_bank dut (
    .clk_i_gated(clk),.rst_ni(rst),.vmul_simd_op_a_q(a),.vmul_simd_op_b_q(b),
    .vmul_simd_op_c_q(c),.vmul_simd_mask_q(mask),.vmul_simd_op_q(op),
    .mfpu_vxrm_i(rm),.vmul_simd_in_valid_q(valid),.vmul_simd_out_ready(consume),
    .vmul_simd_in_ready(ready),.vmul_simd_out_valid(out_valid),
    .vmul_simd_result(result),.vmul_simd_mask(masks),.mfpu_vxsat(sat)
  );
  typedef struct packed {
    logic [63:0] a,b,c;
    logic [7:0] mask;
    ara_op_e op;
    logic [1:0] sew;
  } tx_t;
  tx_t pending[$], golden;
  logic [63:0] ref_result [4];
  logic [7:0] ref_mask [4],ref_sat [4];
  for(genvar s=0;s<4;s++) begin
    simd_mul_reference #(.ElementWidth(vew_e'(s)),.NumPipeRegs(0)) reference (
      .clk_i(clk),.rst_ni(rst),.operand_a_i(golden.a),.operand_b_i(golden.b),
      .operand_c_i(golden.c),.op_i(golden.op),.mask_i(golden.mask),.vxrm_i(rm),
      .valid_i(1'b1),.ready_i(1'b1),.valid_o(),.ready_o(),
      .result_o(ref_result[s]),.mask_o(ref_mask[s]),.vxsat_o(ref_sat[s])
    );
  end
  int accepted,retired,flushed,by_sew[4];
  int unsigned rng=32'h96143102;
  logic fired;
  ara_op_e ops[9]='{VMUL,VMULH,VMULHU,VMULHSU,VMACC,VMADD,VNMSAC,VNMSUB,VSMUL};
  function automatic int unsigned randword();
    rng^=rng<<13; rng^=rng>>17; rng^=rng<<5; return rng;
  endfunction
  always @(posedge clk) begin
    logic [3:0] retire_snapshot;
    logic [3:0][63:0] result_snapshot;
    logic [3:0][7:0] mask_snapshot,sat_snapshot;
    // Freeze pre-edge outputs: the golden combinational model settles after
    // #1, by which time the pipeline may expose a different SEW transaction.
    retire_snapshot=out_valid&consume;
    result_snapshot=result;mask_snapshot=masks;sat_snapshot=sat;
    fired=0;
    if(!rst) begin flushed+=pending.size(); pending.delete(); end
    else begin
      assert($onehot0(out_valid)) else $fatal(1,"multiple shared results");
      fired=|(valid&ready);
      if(fired) begin pending.push_back('{a,b,c,mask,op,sew}); accepted++; end
      for(int s=0;s<4;s++) if(retire_snapshot[s]) begin
        logic [79:0] observed;
        assert(pending.size()>0) else $fatal(1,"unsolicited result");
        golden=pending.pop_front();
        assert(golden.sew==s) else $fatal(1,"out of order SEW");
        observed={sat_snapshot[s],mask_snapshot[s],result_snapshot[s]};
        #1;
        assert(observed==={ref_sat[s],ref_mask[s],ref_result[s]})
          else $fatal(1,"shared stream mismatch sew=%0d op=%0d got=%h expected=%h",s,golden.op,observed,{ref_sat[s],ref_mask[s],ref_result[s]});
        retired++; by_sew[s]++;
      end
    end
  end
  initial begin
    a=0;b=0;c=0;mask=0;op=VMUL;rm=0;sew=0;valid=0;consume=0;
    repeat(3) @(negedge clk); rst=1;
    // Each width must sustain one accepted operation per clock once running.
    for(int s=0;s<4;s++) begin
      int before_count;
      @(negedge clk); before_count=accepted; sew=2'(s);valid=4'b1<<s;consume='1;
      for(int n=0;n<256;n++) begin
        a={randword(),randword()};b={randword(),randword()};c={randword(),randword()};
        op=ops[n%9];rm=vxrm_t'(n%4);mask=8'(randword());
        @(negedge clk);
      end
      assert(accepted-before_count==256) else $fatal(1,"II=1 not sustained sew=%0d",s);
      valid=0;repeat(3) @(negedge clk);
    end
    for(int n=0;n<20000;n++) begin
      @(negedge clk);
      if(n==10000) begin rst=0;valid=0;end
      else if(n==10002) rst=1;
      if(rst && (valid==0 || fired)) begin
        sew=2'(randword());valid=randword()%5 ? 4'b1<<sew : 0;
        a={randword(),randword()};b={randword(),randword()};c={randword(),randword()};
        op=ops[randword()%9];mask=8'(randword());
      end
      rm=vxrm_t'(randword());consume=4'(randword());
    end
    @(negedge clk); consume='1;
    while(valid!=0 && !fired) @(negedge clk);
    valid=0;
    repeat(4) @(negedge clk);
    assert(pending.size()==0 && accepted==retired+flushed) else $fatal(1,"lost transaction");
    $display("Shared MUL stream PASS accepted=%0d retired=%0d flushed=%0d per_sew=%p",accepted,retired,flushed,by_sew);
    $finish;
  end
  initial begin #400000;$fatal(1,"watchdog");end
endmodule
