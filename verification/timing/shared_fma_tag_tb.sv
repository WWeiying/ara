// SPDX-License-Identifier: SHL-0.51
module shared_fma_tag_tb;
  import fpnew_pkg::*;
  logic clk=0;
  always #5 clk=~clk;
  logic rst=0, iv=0, ir, ov, busy;
  logic [63:0] result;
  logic [31:0] tag;
  status_t flags;
  simd_fma_shared #(.TagType(logic[31:0])) dut (
    .clk_i(clk),.rst_ni(rst),
    .operands_i({{4{16'h3c00}}, {4{16'h3c00}}, 64'hxxxxxxxxxxxxxxxx}),
    .is_boxed_i('1),.rnd_mode_i(RNE),.op_i(ADD),.op_mod_i(1'b0),.fmt_i(FP16),
    .vectorial_op_i(1'b1),.simd_mask_i(4'b1111),.tag_i(32'hxx00000f),
    .in_valid_i(iv),.in_ready_o(ir),.flush_i(1'b0),
    .result_o(result),.status_o(flags),.tag_o(tag),.out_valid_o(ov),
    .out_ready_i(1'b1),.busy_o(busy)
  );
  initial begin
    repeat(3) @(negedge clk);
    rst=1; iv=1;
    do @(posedge clk); while(!ir);
    @(negedge clk); iv=0;
    wait(dut.core_valid);
    @(negedge clk);
    $display("TAG_OBSERVATION t=%0t tag0=%h tag1=%h logical_equal=%b case_equal=%b aux_equal=%b",
      $time,dut.tags[0],dut.tags[1],dut.tags[0]==dut.tags[1],
      dut.tags[0]===dut.tags[1],dut.aux[0]==dut.aux[1]);
    if ($test$plusargs("CORRUPT")) force dut.tags[1]=32'h1100000e;
    @(posedge clk);
    #1;
    if ($test$plusargs("CORRUPT")) $fatal(1,"Checker missed a real tag mismatch");
    wait(ov);
    @(negedge clk);
    if (result !== {4{16'h4000}} || flags !== '0 || tag !== 32'hxx00000f)
      $fatal(1,"Tag or arithmetic changed");
    $display("SHARED_FMA_TAG_PASS");
    $finish;
  end
  initial begin #2000; $fatal(1,"Tag test timeout"); end
endmodule
