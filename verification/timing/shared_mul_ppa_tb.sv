// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module shared_mul_ppa_tb;
  import ara_pkg::*; import rvv_pkg::*;
  logic clk_i=0,rst_ni=0;
  always #5 clk_i=~clk_i;
  elen_t a_i,b_i,c_i,result_o;
  logic [7:0] mask_i,mask_o,sat_o;
  ara_op_e op_i;
  vxrm_t rm_i;
  logic [1:0] sew_i;
  logic valid_i,ready_i,ready_o,valid_o;
  elen_t golden[4];
  logic [7:0] golden_mask[4],golden_sat[4];
  shared_mul_ppa dut(.*);
  for(genvar s=0;s<4;s++) begin
    simd_mul #(.ElementWidth(vew_e'(s)),.NumPipeRegs(0)) reference (
      .clk_i,.rst_ni,.operand_a_i(a_i),.operand_b_i(b_i),.operand_c_i(c_i),
      .product_i('0),.mask_i,.op_i,.vxrm_i(rm_i),.valid_i(1'b1),.ready_i(1'b1),
      .ready_o(),.valid_o(),.result_o(golden[s]),.mask_o(golden_mask[s]),.vxsat_o(golden_sat[s])
    );
  end
  int received=0;
  always @(posedge clk_i) if(rst_ni && valid_o && ready_i) begin
    assert({sat_o,mask_o,result_o}==={golden_sat[sew_i],golden_mask[sew_i],golden[sew_i]})
      else $fatal(1,"PPA wrapper arithmetic/identity mismatch");
    received++;
  end
  initial begin
    ara_op_e ops[9]='{VMUL,VMULH,VMULHU,VMULHSU,VMACC,VMADD,VNMSAC,VNMSUB,VSMUL};
    a_i=0;b_i=0;c_i=0;mask_i=0;op_i=VMUL;rm_i=0;sew_i=0;valid_i=0;ready_i=1;
    repeat(3) @(negedge clk_i);rst_ni=1;
    for(int n=0;n<2048;n++) begin
      int target_count;
      @(negedge clk_i);
      a_i={$urandom,$urandom};b_i={$urandom,$urandom};c_i={$urandom,$urandom};
      mask_i=8'($urandom);op_i=ops[n%9];rm_i=vxrm_t'(n%4);sew_i=2'(n%4);
      valid_i=1;target_count=received+1;
      do @(posedge clk_i); while(!ready_o);
      @(negedge clk_i);valid_i=0;
      wait(received==target_count);
      repeat(3) @(negedge clk_i);
    end
    assert(received==2048) else $fatal(1,"PPA wrapper accounting");
    $display("PPA wrapper PASS transactions=%0d",received);$finish;
  end
  initial begin #500000;$fatal(1,"PPA wrapper watchdog");end
endmodule
