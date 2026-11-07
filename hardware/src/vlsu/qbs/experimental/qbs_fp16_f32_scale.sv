// Extend the proven normal mixed-scale core to expanded FP16 subnormals.
// Exact inverse power-of-two recoding changes neither product nor rounding.
module qbs_fp16_f32_scale #(
  parameter int unsigned TagWidth = 4
) (
  input logic clk_i, rst_ni, clear_i, valid_i,
  input logic [31:0] activation_i, weight_i,
  input logic [TagWidth-1:0] tag_i,
  output logic eligible_o, valid_o,
  output logic [31:0] result_o,
  output logic [4:0] fflags_o,
  output logic [TagWidth-1:0] tag_o,
  output logic busy_o
);
  logic [31:0] activation_recoded, weight_recoded;
  logic core_eligible;
  wire small_weight = weight_i[30:23] >= 8'd103 && weight_i[30:23] <= 8'd112;
  wire can_recode = small_weight && activation_i[30:23] > 8'd10 &&
                   activation_i[30:23] < 8'hff;

  always_comb begin
    activation_recoded = activation_i;
    weight_recoded = weight_i;
    if (can_recode) begin
      activation_recoded[30:23] = activation_i[30:23] - 8'd10;
      weight_recoded[30:23] = weight_i[30:23] + 8'd10;
    end
  end
  assign eligible_o = core_eligible && (!small_weight || can_recode);

  qbs_mixed_scale #(.TagWidth(TagWidth)) i_normal (
    .clk_i, .rst_ni, .clear_i, .valid_i,
    .activation_i(activation_recoded), .weight_i(weight_recoded), .tag_i,
    .eligible_o(core_eligible), .valid_o, .result_o, .fflags_o, .tag_o, .busy_o
  );

  // synthesis translate_off
  always @(posedge clk_i)
    if (rst_ni && !clear_i && valid_i)
      assert (eligible_o) else $fatal(1,"Non-admitted expanded FP16 scale request");
  // synthesis translate_on
endmodule
