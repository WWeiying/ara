`timescale 1ns/1ps
module ff1_case_calibration_tb;
  reg [51:0] frac_num = 52'b0;
  wire [51:0] fanc_shift_num;
  wire [12:0] frac_bin_val;
  integer selected;
  integer shift;
  reg [12:0] expected;
  ct_vfdsu_ff1 dut (.frac_num(frac_num), .fanc_shift_num(fanc_shift_num),
                    .frac_bin_val(frac_bin_val));
  initial begin
    if (!$value$plusargs("CASE=%d", selected)) $fatal(1, "Missing CASE");
    #2;
    if (selected >= 0 && selected < 52) begin
      frac_num = 52'b1 << selected;
      shift = 51 - selected;
      expected = -shift;
    end else if (selected == -1) begin
      frac_num = 52'b0;
      expected = 13'h1fcc;
    end else if (selected == -2) begin
      // Standalone mapping of the default arm only, not processor stimulus.
      frac_num = {52{1'bx}};
      expected = 13'b0;
    end else $fatal(1, "Invalid CASE");
    #2;
    if (frac_bin_val !== expected) $fatal(1, "Exponent mismatch");
    if (selected >= 0 && fanc_shift_num !== (52'b1 << 51)) $fatal(1, "Shift mismatch");
    if (selected < 0 && fanc_shift_num !== 52'b0) $fatal(1, "Special mismatch");
    $display("FF1_CALIBRATION_PASS case=%0d", selected);
    $finish;
  end
endmodule
