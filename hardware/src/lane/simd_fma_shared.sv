// SPDX-License-Identifier: SHL-0.51
// Experimental ADDMUL-only candidate; not enabled by the production build.
module simd_fma_shared #(
  parameter int unsigned NumPipeRegs = 5,
  parameter type TagType = logic
) (
  input logic clk_i, rst_ni,
  input logic [2:0][63:0] operands_i,
  input logic [fpnew_pkg::NUM_FP_FORMATS-1:0][2:0] is_boxed_i,
  input fpnew_pkg::roundmode_e rnd_mode_i,
  input fpnew_pkg::operation_e op_i,
  input logic op_mod_i,
  input fpnew_pkg::fp_format_e fmt_i,
  input logic vectorial_op_i,
  input logic [3:0] simd_mask_i,
  input TagType tag_i,
  input logic in_valid_i,
  output logic in_ready_o,
  input logic flush_i,
  output logic [63:0] result_o,
  output fpnew_pkg::status_t status_o,
  output TagType tag_o,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic busy_o
);
  import fpnew_pkg::*;
  typedef struct packed {
    fp_format_e fmt;
    logic vectorial;
  } aux_t;
  function automatic fmt_logic_t formats(int lane);
    fmt_logic_t mask;
    mask = '0;
    mask[FP16] = 1'b1;
    mask[FP32] = lane < 2;
    mask[FP64] = lane == 0;
    return mask;
  endfunction

  logic [3:0] ready, valid, busy, masks;
  logic [3:0][63:0] results;
  status_t [3:0] flags;
  TagType [3:0] tags;
  aux_t [3:0] aux;
  logic accept, retire;
  assign in_ready_o = &ready;
  assign out_valid_o = &valid;
  assign accept = in_valid_i & in_ready_o;
  assign retire = out_valid_o & out_ready_i;
  assign busy_o = |busy;
  assign tag_o = tags[0];

  for (genvar l = 0; l < 4; l++) begin : gen_lane
    localparam fmt_logic_t Formats = formats(l);
    localparam int Width = max_fp_width(Formats);
    localparam int Fp32MaskIndex = l < 2 ? 2*l : 0;
    logic [2:0][Width-1:0] ops;
    logic [NUM_FP_FORMATS-1:0][2:0] boxed;
    logic [Width-1:0] result;
    logic participating, mask;
    fp_format_e local_fmt;

    // Constant slices avoid a variable barrel shifter on the input datapath.
    always_comb begin
      ops = '0;
      mask = 1'b0;
      local_fmt = FP16;
      participating = (l == 0 || vectorial_op_i) && Formats[fmt_i];
      if (participating) begin
        local_fmt = fmt_i;
        case (fmt_i)
          FP16: begin
            for (int k = 0; k < 3; k++) ops[k] = Width'(operands_i[k][16*l+:16]);
            mask = simd_mask_i[l];
          end
          FP32: if (l < 2) begin
            for (int k = 0; k < 3; k++) ops[k] = Width'(operands_i[k] >> (32*l));
            mask = simd_mask_i[Fp32MaskIndex];
          end
          FP64: if (l == 0) begin
            for (int k = 0; k < 3; k++) ops[k] = Width'(operands_i[k]);
            mask = simd_mask_i[0];
          end
          default: ;
        endcase
      end
      boxed = (vectorial_op_i || !participating) ? '1 : is_boxed_i;
    end

    // All sublanes carry all tokens, including legal, masked-off FP16 dummies.
    // Identical stage counts plus atomic acceptance/retirement preserve alignment.
    fpnew_fma_multi #(
      .FpFmtConfig(Formats), .NumPipeRegs(NumPipeRegs),
      .PipeConfig(DISTRIBUTED), .TagType(TagType), .AuxType(aux_t)
    ) i_fma (
      .clk_i, .rst_ni, .operands_i(ops), .is_boxed_i(boxed),
      .rnd_mode_i, .op_i, .op_mod_i,
      .src_fmt_i(local_fmt), .dst_fmt_i(local_fmt), .tag_i,
      .mask_i(mask), .aux_i(aux_t'({fmt_i, vectorial_op_i})),
      .in_valid_i(accept), .in_ready_o(ready[l]), .flush_i,
      .result_o(result), .status_o(flags[l]), .extension_bit_o(),
      .tag_o(tags[l]), .mask_o(masks[l]), .aux_o(aux[l]),
      .out_valid_o(valid[l]), .out_ready_i(retire), .busy_o(busy[l])
    );
    assign results[l] = 64'(result);
  end

  always_comb begin
    result_o = '1;
    status_o = '0;
    case (aux[0].fmt)
      FP16: for (int l = 0; l < 4; l++)
        if (l == 0 || aux[0].vectorial) result_o[16*l+:16] = results[l][15:0];
      FP32: for (int l = 0; l < 2; l++)
        if (l == 0 || aux[0].vectorial) result_o[32*l+:32] = results[l][31:0];
      FP64: result_o = results[0];
      default: ;
    endcase
    for (int l = 0; l < 4; l++) status_o |= flags[l] & {5{masks[l]}};
  end

`ifndef SYNTHESIS
  initial assert (NumPipeRegs > 0) else $fatal(1, "Shared FMA requires registered stages");
  always @(posedge clk_i) if (rst_ni && !flush_i) begin
    assert (ready == {4{ready[0]}} && valid == {4{valid[0]}})
      else $fatal(1, "Shared FMA sublane handshake divergence");
    if (accept) assert (fmt_i inside {FP16, FP32, FP64} &&
                       op_i inside {ADD, MUL, FMADD, FNMSUB})
      else $fatal(1, "Unsupported shared FMA operation");
    if (out_valid_o) for (int l = 1; l < 4; l++)
      assert (tags[l] == tags[0] && aux[l] == aux[0])
        else $fatal(1, "Shared FMA sublane metadata divergence");
  end
`endif
endmodule
