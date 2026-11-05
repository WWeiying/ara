// SPDX-License-Identifier: SHL-0.51
module shared_alu_observation_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  elen_t operand_a_i, operand_b_i, actual_result, expected_result;
  vxsat_t actual_sat, expected_sat;
  logic [7:0] rm, observed_be_i, inactive_x_bytes;
  logic narrowing_select_i, check_ok;
  ara_op_e op_i;
  vew_e vew_i;
  shared_alu_observation dut (.*);
  task automatic check(input bit want, input logic [7:0] bytes);
    #1;
    assert (check_ok === want && inactive_x_bytes === bytes)
      else $fatal(1,"OBSERVATION_RULE got=%b/%h expected=%b/%h",check_ok,inactive_x_bytes,want,bytes);
  endtask
  initial begin
    op_i = VNCLIP; vew_i = EW8; narrowing_select_i = 0; rm = 0;
    operand_a_i = 64'h00xx00xx00xx0007; operand_b_i = 64'h320;
    actual_result = 64'h6; expected_result = 64'h00xx00xx00xx0006;
    actual_sat = 0; expected_sat = 8'b0x0x0x00; observed_be_i = 8'h01;
    check(1,8'h54);
    // The same X on an observed byte must fail, not become a wildcard.
    observed_be_i = 8'h05; check(0,8'h50);
    // A known-bit mismatch remains an error even on an inactive byte.
    observed_be_i = 1; actual_result[16] = 1; expected_result[16] = 0;
    check(0,8'h54);
    // Defined inputs never qualify for an X exception.
    operand_a_i = 7; check(0,0);
    // Unknown byte enable cannot be interpreted as inactive.
    operand_a_i = 64'h00xx00xx00xx0007; actual_result = 6;
    expected_result = 64'h00xx00xx00xx0006; observed_be_i = 'x; check(0,0);
    // Original full-word rule remains in force outside the shift family.
    op_i = VADD; observed_be_i = 1; check(0,0);
    // Architectural byte may not carry an X even if both models agree on X.
    op_i = VNCLIP; actual_result = expected_result; actual_sat = expected_sat;
    observed_be_i = 8'h05; check(0,0);
    actual_result = 6; expected_result = 6; actual_sat = 0; expected_sat = 0;
    operand_a_i = 7; observed_be_i = 1; check(1,0);
    $display("SHARED_ALU_OBSERVATION_PASS checks=8");
    $finish;
  end
endmodule
