// SPDX-License-Identifier: SHL-0.51
module qbs_side_path_calibration_dut (
  input logic clk_i, enable, use_newer,
  output logic [7:0] value_o
);
  always_ff @(posedge clk_i)
    if (enable) value_o <= use_newer ? 8'h22 : 8'h11;
endmodule

module qbs_side_path_calibration;
  logic clk_i = 0;
  logic enable = 0, use_newer = 0;
  logic [7:0] value;
  int mode;
  qbs_side_path_calibration_dut dut (.clk_i, .enable, .use_newer, .value_o(value));
  always #5 clk_i = !clk_i;
  initial begin
    if (!$value$plusargs("MODE=%d", mode) || mode < 0 || mode > 2)
      $fatal(1, "MODE must be 0, 1 or 2");
    enable = mode != 0;
    use_newer = mode == 2;
    #11;
    if (mode == 1 && value !== 8'h11) $fatal(1, "Old path did not execute");
    if (mode == 2 && value !== 8'h22) $fatal(1, "New path did not execute");
    $display("CALIBRATION_PASS mode=%0d enable=%0d use_newer=%0d", mode, enable, use_newer);
    $finish;
  end
endmodule
