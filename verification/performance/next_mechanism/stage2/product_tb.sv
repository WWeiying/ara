`timescale 1ns/1ps
module product_case import ara_pkg::*; import rvv_pkg::*; #(
  parameter int Sew=0, Pipes=0, Shared=0, Bypass=1, Id=0
)(input logic clk, output logic done);
  localparam int W=8<<Sew;
  localparam logic [63:0] EMask=64'hffffffffffffffff>>(64-W);
  logic rst=0, valid=0, ready=0;
  logic [63:0] a=0,b=0,c=0,result,old_result;
  logic [127:0] product;
  logic [7:0] mask=0,out_mask,sat,old_mask,old_sat;
  logic in_ready,out_valid,old_ready,old_valid;
  logic [1:0] out_sew,old_sew;
  ara_op_e op=VMUL;
  vxrm_t rm=0;
  typedef struct packed {
    ara_op_e op;
    logic [63:0] a,b,c;
    logic [7:0] mask;
  } tx_t;
  typedef struct packed {
    logic [127:0] product;
    logic [63:0] result;
    logic [7:0] sat;
  } gold_t;
  tx_t pending[$];
  ara_op_e ops[9]='{VMUL,VMULH,VMULHU,VMULHSU,VMACC,VMADD,VNMSAC,VNMSUB,VSMUL};
  int accepted=0,retired=0,flushed=0,stalled=0,checks=0,cycles=0;
  int by_op[9]='{default:0};
  int unsigned rng=32'h5319ac87 ^ (Id*32'h10204081);
  bit fired=0, held=0, random_ready=0, force_stall=0;
  logic [127:0] held_product;
  logic [7:0] held_mask;
  if (Shared) begin : gen_shared
    simd_mul_shared #(.NumPipeRegs(Pipes),.Bypass8(Bypass)) dut (
      .clk_i(clk),.rst_ni(rst),.operand_a_i(a),.operand_b_i(b),.operand_c_i(c),
      .mask_i(mask),.op_i(op),.sew_i(2'(Sew)),.vxrm_i(rm),
      .valid_i(valid),.ready_o(in_ready),.ready_i(ready),.valid_o(out_valid),
      .result_o(result),.product_o(product),.mask_o(out_mask),.vxsat_o(sat),.sew_o(out_sew));
    simd_mul_shared_before #(.NumPipeRegs(Pipes),.Bypass8(Bypass)) before_dut (
      .clk_i(clk),.rst_ni(rst),.operand_a_i(a),.operand_b_i(b),.operand_c_i(c),
      .mask_i(mask),.op_i(op),.sew_i(2'(Sew)),.vxrm_i(rm),
      .valid_i(valid),.ready_o(old_ready),.ready_i(ready),.valid_o(old_valid),
      .result_o(old_result),.mask_o(old_mask),.vxsat_o(old_sat),.sew_o(old_sew));
  end else begin : gen_standard
    simd_mul #(.ElementWidth(vew_e'(Sew)),.NumPipeRegs(Pipes)) dut (
      .clk_i(clk),.rst_ni(rst),.operand_a_i(a),.operand_b_i(b),.operand_c_i(c),
      .product_i('0),.mask_i(mask),.op_i(op),.vxrm_i(rm),
      .valid_i(valid),.ready_o(in_ready),.ready_i(ready),.valid_o(out_valid),
      .result_o(result),.product_o(product),.mask_o(out_mask),.vxsat_o(sat));
    simd_mul_before #(.ElementWidth(vew_e'(Sew)),.NumPipeRegs(Pipes)) before_dut (
      .clk_i(clk),.rst_ni(rst),.operand_a_i(a),.operand_b_i(b),.operand_c_i(c),
      .product_i('0),.mask_i(mask),.op_i(op),.vxrm_i(rm),
      .valid_i(valid),.ready_o(old_ready),.ready_i(ready),.valid_o(old_valid),
      .result_o(old_result),.mask_o(old_mask),.vxsat_o(old_sat));
    assign out_sew=2'(Sew);
    assign old_sew=2'(Sew);
  end

  // Integer model only: no DUT helper, product output or old RTL is used here.
  // VMULHSU has unsigned A / signed B on these physical operand ports.
  function automatic gold_t model(tx_t t, vxrm_t rounding);
    gold_t g;
    logic [63:0] av,bv,cv,v;
    logic signed [65:0] ax,bx;
    logic signed [131:0] p;
    bit inc;
    g='0;
    for (int e=0;e<64/W;e++) begin
      av=(t.a>>(e*W))&EMask; bv=(t.b>>(e*W))&EMask; cv=(t.c>>(e*W))&EMask;
      ax=$signed({2'b0,av}); bx=$signed({2'b0,bv});
      if ((t.op inside {VMULH,VSMUL}) && av[W-1]) ax-=66'sd1<<W;
      if ((t.op inside {VMULH,VMULHSU,VSMUL}) && bv[W-1]) bx-=66'sd1<<W;
      p=ax*bx;
      for (int k=0;k<2*W;k++) g.product[e*2*W+k]=p[k];
      v=0;
      case(t.op)
        VMUL: v=64'(p);
        VMULH,VMULHU,VMULHSU: v=64'(p>>>W);
        VMACC,VMADD: v=64'(p)+cv;
        VNMSAC,VNMSUB: v=cv-64'(p);
        VSMUL: begin
          case(rounding)
            0: inc=p[W-2];
            1: inc=p[W-2] && (p[W-1] || |p[W-3:0]);
            2: inc=0;
            3: inc=!p[W-1] && |p[W-2:0];
          endcase
          if (av==(64'h1<<(W-1)) && bv==av) begin
            v=(64'h1<<(W-1))-1;
            for(int j=0;j<W/8;j++) g.sat[e*(W/8)+j]=1;
          end else v=64'(p>>>(W-1))+64'(inc);
        end
        default: $fatal(1,"unsupported model op");
      endcase
      g.result|=(v&EMask)<<(e*W);
    end
    return g;
  endfunction

  function automatic int unsigned randword();
    rng^=rng<<13; rng^=rng>>17; rng^=rng<<5; return rng;
  endfunction
  function automatic logic [63:0] edge_value(int n);
    case(n)
      0:return 0; 1:return 1; 2:return EMask; 3:return EMask-1;
      4:return 64'h1<<(W-1); 5:return (64'h1<<(W-1))-1;
      6:return (64'h1<<(W-1))+1; default:return 64'h55aa55aa55aa55aa&EMask;
    endcase
  endfunction
  function automatic logic [63:0] replicate(logic [63:0] x);
    logic [63:0] value;
    value=0;
    for(int e=0;e<64/W;e++) value|=(x&EMask)<<(e*W);
    return value;
  endfunction

  always @(posedge clk) begin
    tx_t t;
    gold_t g;
    cycles++;
    fired=0;
    if(!rst) begin
      flushed+=pending.size(); pending.delete(); held=0;
    end else begin
      assert({in_ready,out_valid}==={old_ready,old_valid})
        else $fatal(1,"legacy handshake id=%0d",Id);
      if(out_valid) begin
        assert({result,out_mask,sat,out_sew}==={old_result,old_mask,old_sat,old_sew})
          else $fatal(1,"legacy output id=%0d",Id);
      end
      if(held) assert(out_valid && product===held_product && out_mask===held_mask)
        else $fatal(1,"unstable product under backpressure id=%0d",Id);
      fired=valid && in_ready;
      if(fired) begin pending.push_back('{op,a,b,c,mask}); accepted++; end
      if(out_valid) begin
        if(pending.size()) t=pending[0];
        else begin
          assert(valid && !ready) else $fatal(1,"unsolicited product id=%0d",Id);
          t='{op,a,b,c,mask};
        end
        g=model(t,rm);
        assert(product===g.product && result===g.result && sat===g.sat && out_mask===t.mask)
          else $fatal(1,"integer model id=%0d sew=%0d pipes=%0d op=%0d a=%h b=%h product=%h gold=%h result=%h gold=%h sat=%h gold=%h",
            Id,W,Pipes,t.op,t.a,t.b,product,g.product,result,g.result,sat,g.sat);
        checks++;
        if(ready) begin
          assert(pending.size()>0) else $fatal(1,"empty retire");
          t=pending.pop_front(); retired++;
          for(int o=0;o<9;o++) if(t.op==ops[o]) by_op[o]++;
        end
      end
      held=out_valid && !ready;
      if(held) begin held_product=product;held_mask=out_mask;stalled++;end
    end
  end

  task automatic step;
    @(negedge clk);
    ready=force_stall ? 0 : random_ready ? (cycles%41>=9 && randword()%4!=0) : 1;
  endtask
  task automatic send(tx_t t);
    while(valid && !fired) step();
    {op,a,b,c,mask}=t;valid=1;
    step();
  endtask
  task automatic drain;
    random_ready=0;force_stall=0;ready=1;
    while(valid && !fired) step();
    valid=0;
    repeat(Pipes+4) step();
    assert(pending.size()==0) else $fatal(1,"not drained id=%0d",Id);
  endtask

  initial begin
    tx_t t;
    int before_count;
    done=0;
    repeat(3) step();rst=1;
    // A signed 0x80 byte is deliberately distinct from unsigned 0x80.
    for(int o=0;o<9;o++)
      for(int r=0;r<4;r++) begin
        drain();rm=vxrm_t'(r);
        for(int x=0;x<8;x++) for(int y=0;y<8;y++)
          send('{ops[o],replicate(edge_value(x)),replicate(edge_value(y)),
                 replicate(edge_value((x+y)%8)),8'(randword())});
      end
    drain();
    if(Sew==0) begin
      for(int o=0;o<3;o++) begin
        // Exhaust all byte pairs in unsigned, signed and mixed product modes.
        for(int x=0;x<256;x++) for(int y=0;y<256;y++) begin
          t.op=o==0 ? VMUL : o==1 ? VMULH : VMULHSU;
          for(int e=0;e<8;e++) begin
            t.a[e*8+:8]=8'(x+37*e);t.b[e*8+:8]=8'(y+53*e);
          end
          t.c=64'h96a51234cafe0bad;t.mask=8'(x^y);
          send(t);
        end
      end
    end
    drain();
    before_count=accepted;
    for(int n=0;n<256;n++)
      send('{ops[n%9],{randword(),randword()},{randword(),randword()},
             {randword(),randword()},8'(randword())});
    assert(accepted-before_count==256) else $fatal(1,"II1 not sustained id=%0d",Id);
    drain();
    // Force a reset while backpressured: registered configurations lose only
    // accepted work; combinational configurations cannot retain an old result.
    force_stall=1;ready=0;valid=1;op=VMULH;a='1;b=64'h8080808080808080;
    repeat(Pipes+3) step();
    rst=0;valid=0;repeat(2) step();rst=1;force_stall=0;
    random_ready=1;
    for(int n=0;n<12000;n++) begin
      if(!valid || fired) begin
        valid=randword()%5!=0;op=ops[randword()%9];
        a={randword(),randword()};b={randword(),randword()};c={randword(),randword()};mask=8'(randword());
      end
      if(n==6000) begin rst=0;valid=0;end
      if(n==6002) rst=1;
      step();
    end
    drain();
    assert(accepted==retired+flushed && checks>2000 && stalled>0)
      else $fatal(1,"accounting/coverage id=%0d",Id);
    if(Pipes>0 && (!Shared || !Bypass || Sew!=0))
      assert(flushed>0) else $fatal(1,"reset did not flush registered work id=%0d",Id);
    for(int o=0;o<9;o++) assert(by_op[o]>0) else $fatal(1,"missing op id=%0d",Id);
    $display("PRODUCT_CASE id=%0d shared=%0d sew=%0d pipes=%0d bypass=%0d accepted=%0d retired=%0d flushed=%0d checks=%0d stalled=%0d",
       Id,Shared,W,Pipes,Bypass,accepted,retired,flushed,checks,stalled);
    done=1;
  end
endmodule

module stage2_product_tb;
  logic clk=0;
  always #5 clk=~clk;
  logic [26:0] done;
  for(genvar shared=0;shared<2;shared++)
    for(genvar sew=0;sew<4;sew++)
      for(genvar pipe=0;pipe<3;pipe++) begin : gen_case
        localparam int Id=shared*12+sew*3+pipe;
        product_case #(.Shared(shared),.Sew(sew),.Pipes(pipe),.Id(Id)) dut(.clk,.done(done[Id]));
      end
  for(genvar pipe=0;pipe<3;pipe++) begin : gen_shared_no_bypass
    product_case #(.Shared(1),.Sew(0),.Pipes(pipe),.Bypass(0),.Id(24+pipe)) dut(.clk,.done(done[24+pipe]));
  end
  initial begin
    wait(&done);
    $display("STAGE2_PRODUCT_PASS configurations=24 shared_no_bypass=3");
    $finish;
  end
  initial begin #3000000;$fatal(1,"product watchdog");end
endmodule
