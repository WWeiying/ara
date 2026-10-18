// Identical register boundaries for the FMA-ADD and dedicated scalar ADD slices.
module scalar_fp_add_ppa_top #(
  parameter bit UseScalar = 0
)(
  input logic clk_i, rst_ni,
  input logic [111:0] a_i, b_i,
  input logic [8:0] rnd_mode_i,
  output logic [111:0] result_o,
  output logic [14:0] status_o
);
  import fpnew_pkg::*;
  logic [111:0] a_q, b_q, result_d;
  logic [8:0] rnd_mode_q;
  logic [14:0] status_d;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      a_q <= '0; b_q <= '0; rnd_mode_q <= '0;
      result_o <= '0; status_o <= '0;
    end else begin
      a_q <= a_i; b_q <= b_i; rnd_mode_q <= rnd_mode_i;
      result_o <= result_d; status_o <= status_d;
    end
  end
  for (genvar f=0; f<3; f++) begin : gen_format
    localparam fp_format_e Fmt = f==0 ? FP16 : f==1 ? FP32 : FP64;
    localparam int W = fp_width(Fmt);
    localparam int Offset = f==0 ? 0 : f==1 ? 16 : 48;
    status_t flags;
    assign status_d[f*5+:5] = flags;
    if (UseScalar) begin : gen_scalar
      scalar_fp_add #(.FpFormat(Fmt)) add (
        .clk_i, .rst_ni, .a_i(a_q[Offset+:W]), .b_i(b_q[Offset+:W]),
        .rnd_mode_i(roundmode_e'(rnd_mode_q[f*3+:3])),
        .result_o(result_d[Offset+:W]), .status_o(flags));
    end else begin : gen_fma
      logic [2:0][W-1:0] operands;
      assign operands = {b_q[Offset+:W],a_q[Offset+:W],{W{1'b0}}};
      fpnew_fma #(.FpFormat(Fmt),.NumPipeRegs(0)) add (
        .clk_i, .rst_ni, .operands_i(operands), .is_boxed_i(3'b111),
        .rnd_mode_i(roundmode_e'(rnd_mode_q[f*3+:3])),
        .op_i(ADD), .op_mod_i(1'b0), .tag_i(1'b0), .mask_i(1'b1), .aux_i(1'b0),
        .in_valid_i(1'b1), .in_ready_o(), .flush_i(1'b0),
        .result_o(result_d[Offset+:W]), .status_o(flags), .extension_bit_o(),
        .tag_o(), .mask_o(), .aux_o(), .out_valid_o(), .out_ready_i(1'b1), .busy_o());
    end
  end
endmodule
