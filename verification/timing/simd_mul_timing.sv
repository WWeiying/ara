// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
// Registered input/output boundaries model the VMFPU operand and result
// registers. This is a local multiplier comparison, not a whole-lane PPA run.
module simd_mul_timing import ara_pkg::*; import rvv_pkg::*; #(
  parameter vew_e ElementWidth = EW32,
  parameter int NumPipeRegs = 1
) (
  input logic clk_i, rst_ni,
  input elen_t a_i, b_i, c_i,
  input ara_op_e op_i,
  input logic [7:0] mask_i,
  input vxrm_t vxrm_i,
  input logic valid_i, ready_i,
  output logic ready_o,
  output elen_t result_o,
  output logic [7:0] mask_o,
  output vxsat_t vxsat_o
);
  elen_t a_q, b_q, c_q, result;
  ara_op_e op_q;
  logic [7:0] mask_q, mask;
  vxrm_t vxrm_q;
  vxsat_t vxsat;
  logic valid_q, valid;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      a_q <= 0;
      b_q <= 0;
      c_q <= 0;
      op_q <= ara_op_e'(0);
      mask_q <= 0;
      valid_q <= 0;
      vxrm_q <= 0;
      result_o <= 0;
      mask_o <= 0;
      vxsat_o <= 0;
    end else begin
      vxrm_q <= vxrm_i;
      if (ready_o) begin
        a_q <= a_i;
        b_q <= b_i;
        c_q <= c_i;
        op_q <= op_i;
        mask_q <= mask_i;
        valid_q <= valid_i;
      end
      if (valid && ready_i) begin
        result_o <= result;
        mask_o <= mask;
        vxsat_o <= vxsat;
      end
    end
  end
  simd_mul #(.ElementWidth(ElementWidth), .NumPipeRegs(NumPipeRegs)) i_mul (
    .clk_i, .rst_ni, .operand_a_i(a_q), .operand_b_i(b_q), .operand_c_i(c_q),
    .mask_i(mask_q), .op_i(op_q), .vxrm_i(vxrm_q),
    .valid_i(valid_q), .ready_i, .ready_o, .valid_o(valid),
    .result_o(result), .mask_o(mask), .vxsat_o(vxsat)
  );
endmodule
