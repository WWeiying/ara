module alu_merge_probe;
  timeunit 1ns; timeprecision 100fs;
  reg [63:0] a=64'hff800000ff800000, b=64'hxxxxxxxxxxxxxxxx;
  wire [63:0] result;
  wire [7:0] sat;
  simd_alu_1_3_ara_soc dut (.operand_a_i(a), .operand_b_i(b), .valid_i(1'b1),
    .vm_i(1'b1), .mask_i(8'hff), .narrowing_select_i(1'b0), .op_i(8'd29),
    .vew_i(3'd2), .vxsat_o(sat), .rm(8'b0), .vxrm_i(2'b0), .result_o(result));
  initial begin
    #1;
    if (!$isunknown(result)) $fatal(1,"Captured unused-B X did not reproduce");
    $display("MERGE_UNUSED_B_X_REPRODUCED a=%h b=%h result=%h",a,b,result);
    for(int i=0;i<1024;i++) begin
      b=i==0 ? 64'b0 : i==1 ? 64'hffffffffffffffff : {$urandom,$urandom};
      #0.1;
      if(result !== a) $fatal(1,"Real Boolean mismatch: selected known A depends on B");
    end
    $display("ALU_UNUSED_B_X_PESSIMISM_PROBE_PASS known_B_vectors=1024 selected_A_exact=1");
    $finish;
  end
endmodule
