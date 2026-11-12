// SPDX-License-Identifier: SHL-0.51
// Experimental ADDMUL-only candidate; not enabled by the production build.
module simd_fma_shared #(
  parameter int unsigned NumPipeRegs = 5,
  parameter bit CompactPipeline = 1'b1,
  parameter type TagType = logic,
  // Opt-in contract: omitted tag bits are unused by this caller and return zero.
  parameter TagType TagKeepMask = '1
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
  localparam logic [$bits(TagType)-1:0] KeepMask = TagKeepMask;
  localparam int TagBits = $countones(KeepMask);
  typedef logic [(TagBits > 0 ? TagBits : 1)-1:0] pipe_tag_t;
  pipe_tag_t input_tag;
  typedef struct packed {
    logic [63:0] result;
    status_t status;
    pipe_tag_t tag;
  } output_t;
  // Preserve the total elastic capacity/latency; delay packed results rather
  // than repeating wide operand and intermediate-sum registers.
  localparam int CorePipeRegs = CompactPipeline && NumPipeRegs > 3 ? 3 : NumPipeRegs;
  localparam int OutputPipeRegs = NumPipeRegs - CorePipeRegs;
  output_t [OutputPipeRegs:0] output_data;
  logic [OutputPipeRegs:0] output_valid, output_ready;
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
  pipe_tag_t [3:0] tags;
  aux_t [3:0] aux;
  logic accept, retire, core_valid;
  assign in_ready_o = &ready;
  assign core_valid = &valid;
  assign accept = in_valid_i & in_ready_o;
  assign retire = core_valid & output_ready[0];
  assign busy_o = (|busy) | (|output_valid);
  assign output_valid[0] = core_valid;
  assign output_data[0].tag = tags[0];
  assign output_ready[OutputPipeRegs] = out_ready_i;
  assign out_valid_o = output_valid[OutputPipeRegs];
  assign result_o = output_data[OutputPipeRegs].result;
  assign status_o = output_data[OutputPipeRegs].status;
  // Constant ranks become wires, not a variable pack/unpack network.
  for (genvar b = 0; b < $bits(TagType); b++) begin : gen_tag_bits
    if (KeepMask[b]) begin : gen_keep
      localparam int Rank = $countones(KeepMask << ($bits(TagType)-b));
      assign input_tag[Rank] = tag_i[b];
      assign tag_o[b] = output_data[OutputPipeRegs].tag[Rank];
    end else begin : gen_drop
      assign tag_o[b] = 1'b0;
    end
  end
  if (TagBits == 0) assign input_tag = '0;
  for (genvar s = 0; s < OutputPipeRegs; s++) begin : gen_output_pipeline
    stream_register #(.T(output_t)) i_stage (
      .clk_i, .rst_ni, .clr_i(flush_i), .testmode_i(1'b0),
      .valid_i(output_valid[s]), .ready_o(output_ready[s]), .data_i(output_data[s]),
      .valid_o(output_valid[s+1]), .ready_i(output_ready[s+1]), .data_o(output_data[s+1])
    );
  end

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
      .FpFmtConfig(Formats), .NumPipeRegs(CorePipeRegs),
      .PipeConfig(DISTRIBUTED), .TagType(pipe_tag_t), .AuxType(aux_t)
    ) i_fma (
      .clk_i, .rst_ni, .operands_i(ops), .is_boxed_i(boxed),
      .rnd_mode_i, .op_i, .op_mod_i,
      .src_fmt_i(local_fmt), .dst_fmt_i(local_fmt), .tag_i(input_tag),
      .mask_i(mask), .aux_i(aux_t'({fmt_i, vectorial_op_i})),
      .in_valid_i(accept), .in_ready_o(ready[l]), .flush_i,
      .result_o(result), .status_o(flags[l]), .extension_bit_o(),
      .tag_o(tags[l]), .mask_o(masks[l]), .aux_o(aux[l]),
      .out_valid_o(valid[l]), .out_ready_i(retire), .busy_o(busy[l])
    );
    assign results[l] = 64'(result);
  end

  always_comb begin
    output_data[0].result = '1;
    output_data[0].status = '0;
    case (aux[0].fmt)
      FP16: for (int l = 0; l < 4; l++)
        if (l == 0 || aux[0].vectorial) output_data[0].result[16*l+:16] = results[l][15:0];
      FP32: for (int l = 0; l < 2; l++)
        if (l == 0 || aux[0].vectorial) output_data[0].result[32*l+:32] = results[l][31:0];
      FP64: output_data[0].result = results[0];
      default: ;
    endcase
    for (int l = 0; l < 4; l++) output_data[0].status |= flags[l] & {5{masks[l]}};
  end

`ifndef SYNTHESIS
  int unsigned x_tag_observations = 0;
  initial assert (NumPipeRegs > 0) else $fatal(1, "Shared FMA requires registered stages");
  always @(posedge clk_i) if (rst_ni && !flush_i) begin
    assert (ready == {4{ready[0]}} && valid == {4{valid[0]}})
      else $fatal(1, "Shared FMA sublane handshake divergence");
    if (accept) assert (fmt_i inside {FP16, FP32, FP64} &&
                       op_i inside {ADD, MUL, FMADD, FNMSUB})
      else $fatal(1, "Unsupported shared FMA operation");
    // Tags may carry an unused operand with X bits (e.g. operand A for ADD).
    // Require exact four-state preservation, not wildcard matching. Control
    // metadata must still be known and equal; real tag-bit differences fail.
    if (core_valid) begin
      for (int l = 1; l < 4; l++)
        assert (tags[l] === tags[0] && aux[l] == aux[0])
          else $fatal(1, "Shared FMA sublane metadata divergence lane=%0d tag0=%h tag=%h aux0=%h aux=%h",
                      l,tags[0],tags[l],aux[0],aux[l]);
      if ($isunknown(tags[0]) && x_tag_observations == 0) begin
        $display("FMA_IDENTICAL_X_TAG %m tag0=%h tag1=%h aux0=%h aux1=%h",
                 tags[0],tags[1],aux[0],aux[1]);
        x_tag_observations++;
      end
    end
  end
`endif
endmodule
