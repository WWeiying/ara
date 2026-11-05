// SPDX-License-Identifier: SHL-0.51
// Optional lane-local ADDMUL replacement. Other fpnew opgroups are unchanged.
module simd_fpnew #(
  parameter fpnew_pkg::fpu_features_t Features = fpnew_pkg::RV64D_Xsflt,
  parameter fpnew_pkg::fpu_implementation_t Implementation = fpnew_pkg::DEFAULT_NOREGS,
  parameter fpnew_pkg::divsqrt_unit_t DivSqrtSel = fpnew_pkg::THMULTI,
  parameter type TagType = logic,
  parameter TagType SharedFmaTagKeepMask = '1,
  parameter logic TrueSIMDClass = 1'b0,
  parameter logic EnableSIMDMask = 1'b0,
  parameter bit SharedFma = 1'b0,
  parameter int unsigned SharedFmaPipeRegs = 5,
  localparam int NumLanes = fpnew_pkg::max_num_lanes(
      Features.Width, Features.FpFmtMask, Features.EnableVectors),
  localparam type MaskType = logic [NumLanes-1:0]
) (
  input logic clk_i, rst_ni,
  input logic [31:0] hart_id_i,
  input logic [2:0][Features.Width-1:0] operands_i,
  input fpnew_pkg::roundmode_e rnd_mode_i,
  input fpnew_pkg::operation_e op_i,
  input logic op_mod_i,
  input fpnew_pkg::fp_format_e src_fmt_i, dst_fmt_i,
  input fpnew_pkg::int_format_e int_fmt_i,
  input logic vectorial_op_i,
  input TagType tag_i,
  input MaskType simd_mask_i,
  input logic in_valid_i,
  output logic in_ready_o,
  input logic flush_i,
  output logic [Features.Width-1:0] result_o,
  output fpnew_pkg::status_t status_o,
  output TagType tag_o,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic busy_o
);
  typedef struct packed {
    logic [Features.Width-1:0] result;
    fpnew_pkg::status_t status;
    TagType tag;
  } output_t;
  if (!SharedFma) begin : gen_original
    fpnew_top #(
      .Features(Features), .Implementation(Implementation), .DivSqrtSel(DivSqrtSel),
      .TagType(TagType), .TrueSIMDClass(TrueSIMDClass), .EnableSIMDMask(EnableSIMDMask)
    ) i_original (.*);
  end else begin : gen_shared
    import fpnew_pkg::*;
    logic [NUM_OPGROUPS-1:0] ready, valid, grant, busy;
    output_t [NUM_OPGROUPS-1:0] outputs;
    output_t selected;
    logic [NUM_FP_FORMATS-1:0][2:0] boxed;
    MaskType mask;

    assign in_ready_o = in_valid_i & ready[get_opgroup(op_i)];
    assign mask = simd_mask_i | {NumLanes{!EnableSIMDMask}};
    assign busy_o = |busy;
    for (genvar fmt = 0; fmt < NUM_FP_FORMATS; fmt++) begin : gen_boxing
      localparam int Width = fp_width(fp_format_e'(fmt));
      for (genvar k = 0; k < 3; k++) begin : gen_operand
        if (Features.EnableNanBox && Width < Features.Width) begin : gen_check
          assign boxed[fmt][k] = vectorial_op_i || (&operands_i[k][Features.Width-1:Width]);
        end else begin : gen_boxed
          assign boxed[fmt][k] = 1'b1;
        end
      end
    end

    for (genvar g = 0; g < NUM_OPGROUPS; g++) begin : gen_group
      localparam int NumOperands = num_operands(opgroup_e'(g));
      logic issue;
      assign issue = in_valid_i && get_opgroup(op_i) == opgroup_e'(g);
      if (g == int'(ADDMUL)) begin : gen_fma
        simd_fma_shared #(.NumPipeRegs(SharedFmaPipeRegs), .TagType(TagType),
                         .TagKeepMask(SharedFmaTagKeepMask)) i_fma (
          .clk_i, .rst_ni, .operands_i, .is_boxed_i(boxed), .rnd_mode_i,
          .op_i, .op_mod_i, .fmt_i(dst_fmt_i), .vectorial_op_i, .simd_mask_i(mask),
          .tag_i, .in_valid_i(issue), .in_ready_o(ready[g]), .flush_i,
          .result_o(outputs[g].result), .status_o(outputs[g].status),
          .tag_o(outputs[g].tag), .out_valid_o(valid[g]), .out_ready_i(grant[g]),
          .busy_o(busy[g])
        );
      end else begin : gen_original_group
        logic [NUM_FP_FORMATS-1:0][NumOperands-1:0] group_boxed;
        for (genvar fmt = 0; fmt < NUM_FP_FORMATS; fmt++)
          assign group_boxed[fmt] = boxed[fmt][NumOperands-1:0];
        fpnew_opgroup_block #(
          .OpGroup(opgroup_e'(g)), .Width(Features.Width),
          .EnableVectors(Features.EnableVectors), .DivSqrtSel(DivSqrtSel),
          .FpFmtMask(Features.FpFmtMask), .IntFmtMask(Features.IntFmtMask),
          .FmtPipeRegs(Implementation.PipeRegs[g]), .FmtUnitTypes(Implementation.UnitTypes[g]),
          .PipeConfig(Implementation.PipeConfig), .TagType(TagType), .TrueSIMDClass(TrueSIMDClass)
        ) i_group (
          .clk_i, .rst_ni, .hart_id_i, .operands_i(operands_i[NumOperands-1:0]),
          .is_boxed_i(group_boxed), .rnd_mode_i, .op_i, .op_mod_i,
          .src_fmt_i, .dst_fmt_i, .int_fmt_i, .vectorial_op_i, .tag_i,
          .simd_mask_i(mask), .in_valid_i(issue), .in_ready_o(ready[g]), .flush_i,
          .result_o(outputs[g].result), .status_o(outputs[g].status),
          .extension_bit_o(), .tag_o(outputs[g].tag), .out_valid_o(valid[g]),
          .out_ready_i(grant[g]), .busy_o(busy[g])
        );
      end
    end

    // Retain fpnew's single opgroup arbitration level and locked valid/ready behavior.
    rr_arb_tree #(.NumIn(NUM_OPGROUPS), .DataType(output_t), .AxiVldRdy(1'b1)) i_arbiter (
      .clk_i, .rst_ni, .flush_i, .rr_i('0), .req_i(valid), .gnt_o(grant),
      .data_i(outputs), .gnt_i(out_ready_i), .req_o(out_valid_o), .data_o(selected), .idx_o()
    );
    assign result_o = selected.result;
    assign status_o = selected.status;
    assign tag_o = selected.tag;
`ifndef SYNTHESIS
    initial begin
      assert (Features.Width == 64 && Features.EnableVectors &&
              Features.FpFmtMask == 6'b111000 && SharedFmaPipeRegs > 0)
        else $fatal(1, "Shared FMA requires the 64-bit FP16/32/64 vector configuration");
    end
`endif
  end
endmodule
