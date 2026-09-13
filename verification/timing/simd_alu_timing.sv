// SPDX-License-Identifier: SHL-0.51
// Local registered ALU boundary, not the full operand-queue/VALU path.
module simd_alu_timing import ara_pkg::*; import rvv_pkg::*; (
  input logic clk_i, rst_ni, valid_i, vm_i, narrowing_select_i,
  input elen_t operand_a_i, operand_b_i,
  input ara_op_e op_i,
  input vew_e vew_i,
  input vxrm_t vxrm_i,
  input logic [7:0] mask_i,
  output elen_t result_o,
  output vxsat_t vxsat_o
);
  elen_t a_q, b_q, result;
  ara_op_e op_q;
  vew_e vew_q;
  vxrm_t vxrm_q;
  logic [7:0] mask_q, rm;
  logic valid_q, vm_q, narrow_q;
  vxsat_t sat;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      a_q <= 0; b_q <= 0; op_q <= ara_op_e'(0); vew_q <= EW8;
      vxrm_q <= 0; mask_q <= 0; valid_q <= 0; vm_q <= 0; narrow_q <= 0;
      result_o <= 0; vxsat_o <= 0;
    end else begin
      a_q <= operand_a_i; b_q <= operand_b_i; op_q <= op_i; vew_q <= vew_i;
      vxrm_q <= vxrm_i; mask_q <= mask_i; valid_q <= valid_i;
      vm_q <= vm_i; narrow_q <= narrowing_select_i;
      if (valid_q) begin result_o <= result; vxsat_o <= sat; end
    end
  end
  fixed_p_rounding i_rounding (.operand_a_i(a_q), .operand_b_i(b_q),
      .op_i(op_q), .vew_i(vew_q), .vxrm_i(vxrm_q), .valid_i(valid_q), .r_o(rm));
  simd_alu i_alu (.operand_a_i(a_q), .operand_b_i(b_q), .op_i(op_q),
      .vew_i(vew_q), .vxrm_i(vxrm_q), .rm, .valid_i(valid_q), .vm_i(vm_q),
      .mask_i(mask_q), .narrowing_select_i(narrow_q), .result_o(result), .vxsat_o(sat));
endmodule
