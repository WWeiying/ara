// Isolated, matched synthesis harness for the existing ordered recurrence slice.
module ordered_add_ppa_top #(parameter int Mode=0) (
 input logic clk_i, rst_ni,
 input logic [2:0][63:0] operands_i,
 input fpnew_pkg::roundmode_e rnd_mode_i,
 input fpnew_pkg::operation_e op_i,
 input logic op_mod_i,
 input fpnew_pkg::fp_format_e fmt_i,
 input logic [7:0] tag_i,
 input logic [3:0] mask_i,
 input logic valid_i, ready_i,
 output logic ready_o, valid_o,
 output logic [63:0] result_o,
 output fpnew_pkg::status_t flags_o,
 output logic [7:0] tag_o,
 output logic busy_o
);
 import fpnew_pkg::*;
  localparam fpu_features_t Features = '{Width:64, EnableVectors:1, EnableNanBox:1,
      FpFmtMask:6'b111000, IntFmtMask:4'b1111};
  localparam fpu_implementation_t Impl = '{
      PipeRegs:'{'{default:1},'{default:0},'{default:0},'{default:0},'{default:0}},
      UnitTypes:'{'{default:PARALLEL},'{default:DISABLED},'{default:DISABLED},'{default:DISABLED},'{default:DISABLED}},
      PipeConfig:Mode==3 ? AFTER : BEFORE};

 localparam fpu_features_t ScalarFeatures = '{Width:64, EnableVectors:0,
     EnableNanBox:0, FpFmtMask:6'b111000, IntFmtMask:4'b1111};
 localparam int MaskWidth = Mode>=2 ? 1 : 4;
 fpnew_top #(.Features(Mode>=2?ScalarFeatures:Features),.Implementation(Impl),
     .TagType(logic[7:0]),.TrueSIMDClass(1),.EnableSIMDMask(1)) dut (
     .clk_i,.rst_ni,.hart_id_i('0),.flush_i(1'b0),.rnd_mode_i,
     .op_i(Mode==0?op_i:ADD),.op_mod_i(Mode==0?op_mod_i:1'b0),
     .vectorial_op_i(Mode<2),.operands_i,.tag_i,.simd_mask_i(MaskWidth'(mask_i)),
     .src_fmt_i(fmt_i),.dst_fmt_i(fmt_i),.int_fmt_i(INT64),
     .in_valid_i(valid_i),.in_ready_o(ready_o),.result_o,.status_o(flags_o),
     .tag_o,.out_valid_o(valid_o),.out_ready_i(ready_i),.busy_o);
endmodule
