// Matched runtime-format arithmetic experiment. All modes use identical
// input/output registers and expose only the selected boxed result/flags.
module shared_scalar_fp_add_ppa_top import fpnew_pkg::*; #(
  parameter int unsigned Mode = 0 // 0: FMA ADD, 1: scalar slices, 2: shared ADD
) (
  input logic clk_i, rst_ni,
  input logic [63:0] a_i, b_i,
  input fp_format_e format_i,
  input roundmode_e rnd_mode_i,
  output logic [63:0] result_o,
  output status_t status_o
);
  logic [63:0] a_q, b_q, result;
  fp_format_e format_q;
  roundmode_e rm_q;
  status_t status;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      a_q <= '0;
      b_q <= '0;
      format_q <= FP64;
      rm_q <= RNE;
      result_o <= '0;
      status_o <= '0;
    end else begin
      a_q <= a_i;
      b_q <= b_i;
      format_q <= format_i;
      rm_q <= rnd_mode_i;
      result_o <= result;
      status_o <= status;
    end
  end
  if (Mode == 2) begin : gen_shared
    shared_scalar_fp_add i_add (
      .clk_i, .rst_ni, .a_i(a_q), .b_i(b_q), .format_i(format_q),
      .rnd_mode_i(rm_q), .result_o(result), .status_o(status)
    );
  end else begin : gen_slices
    logic [2:0][63:0] format_result;
    status_t [2:0] format_status;
    for (genvar f = 0; f < 3; f++) begin : gen_format
      localparam fp_format_e Fmt = f == 0 ? FP16 : f == 1 ? FP32 : FP64;
      localparam int W = fp_width(Fmt);
      logic [W-1:0] raw_result;
      if (Mode == 1) begin : gen_scalar
        scalar_fp_add #(.FpFormat(Fmt)) i_add (
          .clk_i, .rst_ni, .a_i(a_q[W-1:0]), .b_i(b_q[W-1:0]),
          .rnd_mode_i(rm_q), .result_o(raw_result), .status_o(format_status[f])
        );
      end else begin : gen_fma
        logic [2:0][W-1:0] operands;
        assign operands = {b_q[W-1:0], a_q[W-1:0], {W{1'b0}}};
        fpnew_fma #(.FpFormat(Fmt), .NumPipeRegs(0)) i_add (
          .clk_i, .rst_ni, .operands_i(operands), .is_boxed_i('1),
          .rnd_mode_i(rm_q), .op_i(ADD), .op_mod_i(1'b0), .tag_i(1'b0),
          .mask_i(1'b1), .aux_i(1'b0), .in_valid_i(1'b1), .in_ready_o(),
          .flush_i(1'b0), .result_o(raw_result), .status_o(format_status[f]),
          .extension_bit_o(), .tag_o(), .mask_o(), .aux_o(), .out_valid_o(),
          .out_ready_i(1'b1), .busy_o()
        );
      end
      assign format_result[f] = {{(64-W){1'b1}}, raw_result};
    end
    always_comb begin
      case (format_q)
        FP16: begin result = format_result[0]; status = format_status[0]; end
        FP32: begin result = format_result[1]; status = format_status[1]; end
        default: begin result = format_result[2]; status = format_status[2]; end
      endcase
    end
  end
endmodule
