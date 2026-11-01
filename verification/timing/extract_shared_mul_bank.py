#!/usr/bin/env python3
"""Wrap the actual VMFPU multiplier bank, without rewriting its connections."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("source", type=Path)
p.add_argument("output", type=Path)
a = p.parse_args()
source = a.source.read_text()
start = "  // The ingress valid tag travels with the operand registers."
end = "  // The outputs of the SIMD multipliers are read in order"
assert source.count(start) == source.count(end) == 1
bank = source.split(start)[1].split(end)[0]
header = """module extracted_shared_mul_bank import ara_pkg::*; import rvv_pkg::*; (
  input logic clk_i_gated, rst_ni,
  input elen_t vmul_simd_op_a_q, vmul_simd_op_b_q, vmul_simd_op_c_q,
  input logic [7:0] vmul_simd_mask_q,
  input ara_op_e vmul_simd_op_q,
  input vxrm_t mfpu_vxrm_i,
  input logic [3:0] vmul_simd_in_valid_q, vmul_simd_out_ready,
  output logic [3:0] vmul_simd_in_ready, vmul_simd_out_valid,
  output elen_t [3:0] vmul_simd_result,
  output logic [3:0][7:0] vmul_simd_mask, mfpu_vxsat
);
  localparam fixpt_support_e FixPtSupport = FixedPointEnable;
  typedef logic [7:0] strb_t;
  elen_t [3:0] vmul_simd_op_a_q_gated, vmul_simd_op_b_q_gated, vmul_simd_op_c_q_gated;
  logic [3:0][7:0] vmul_simd_mask_q_gated;
  ara_op_e [3:0] vmul_simd_op_q_gated;
  for (genvar s = 0; s < 4; s++) begin
    assign vmul_simd_op_a_q_gated[s] = vmul_simd_in_valid_q[s] ? vmul_simd_op_a_q : '0;
    assign vmul_simd_op_b_q_gated[s] = vmul_simd_in_valid_q[s] ? vmul_simd_op_b_q : '0;
    assign vmul_simd_op_c_q_gated[s] = vmul_simd_in_valid_q[s] ? vmul_simd_op_c_q : '0;
    assign vmul_simd_mask_q_gated[s] = vmul_simd_in_valid_q[s] ? vmul_simd_mask_q : '0;
    assign vmul_simd_op_q_gated[s] = vmul_simd_in_valid_q[s] ? vmul_simd_op_q : ara_op_e'('0);
  end
"""
a.output.mkdir(parents=True, exist_ok=False)
(a.output / "bank.sv").write_text(header + start + bank + "endmodule\n")
(a.output / "source-pins.json").write_text(json.dumps({
    str(a.source.resolve()): hashlib.sha256(a.source.read_bytes()).hexdigest()
}, indent=2) + "\n")
