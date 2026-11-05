// SPDX-License-Identifier: SHL-0.51
// Matched lane ADDMUL boundary, including the real 80-bit synthesis tag.
module shared_fma_timing (
  input logic clk_i, rst_ni,
  input logic [2:0][63:0] operands_i,
  input fpnew_pkg::roundmode_e rnd_mode_i,
  input fpnew_pkg::operation_e op_i,
  input logic op_mod_i,
  input fpnew_pkg::fp_format_e fmt_i,
  input logic [79:0] tag_i,
  input logic [3:0] mask_i,
  input logic in_valid_i,
  output logic in_ready_o,
  output logic [63:0] result_o,
  output fpnew_pkg::status_t status_o,
  output logic [79:0] tag_o,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic busy_o
);
  import fpnew_pkg::*;
  localparam fmt_unsigned_t BaselinePipeRegs = '{4,5,3,2,3,2};
  localparam fmt_unit_types_t BaselineUnitTypes = '{default:PARALLEL};
`ifdef SHARED_FMA_PPA
  simd_fma_shared #(.NumPipeRegs(5),.TagType(logic [79:0])) i_addmul (
    .clk_i,.rst_ni,.operands_i,.is_boxed_i('1),.rnd_mode_i,.op_i,.op_mod_i,.fmt_i,
    .vectorial_op_i(1'b1),.simd_mask_i(mask_i),.tag_i,.in_valid_i,.in_ready_o,
    .flush_i(1'b0),.result_o,.status_o,.tag_o,.out_valid_o,.out_ready_i,.busy_o
  );
`else
  fpnew_opgroup_block #(
    .OpGroup(ADDMUL),.Width(64),.EnableVectors(1'b1),.FpFmtMask(6'b111000),
    .IntFmtMask('1),.FmtPipeRegs(BaselinePipeRegs),
    .FmtUnitTypes(BaselineUnitTypes),.PipeConfig(DISTRIBUTED),.TagType(logic [79:0])
  ) i_addmul (
    .clk_i,.rst_ni,.hart_id_i('0),.operands_i,.is_boxed_i('1),.rnd_mode_i,
    .op_i,.op_mod_i,.src_fmt_i(fmt_i),.dst_fmt_i(fmt_i),.int_fmt_i(INT64),
    .vectorial_op_i(1'b1),.simd_mask_i(mask_i),.tag_i,.in_valid_i,.in_ready_o,
    .flush_i(1'b0),.result_o,.status_o,.extension_bit_o(),.tag_o,
    .out_valid_o,.out_ready_i,.busy_o
  );
`endif
endmodule
