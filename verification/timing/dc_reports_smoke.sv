// SPDX-License-Identifier: SHL-0.51
module dc_reports_smoke (
  input logic clk_i, enable_i,
  input logic [15:0] data_i,
  output logic [15:0] data_o
);
  logic [15:0] first_q;
  always_ff @(posedge clk_i) begin
    if (enable_i) first_q <= data_i + 16'd1;
    data_o <= first_q + 16'd7;
  end
endmodule
