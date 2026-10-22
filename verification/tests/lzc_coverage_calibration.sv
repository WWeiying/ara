`timescale 1ns/1ps
module lzc_coverage_calibration;
  logic [9:0] in16;
  logic [22:0] in32;
  logic [3:0] count16;
  logic [4:0] count32;
  logic empty16, empty32;
  lzc #(.WIDTH(10), .MODE(1)) u16 (.in_i(in16), .cnt_o(count16), .empty_o(empty16));
  lzc #(.WIDTH(23), .MODE(1)) u32 (.in_i(in32), .cnt_o(count32), .empty_o(empty32));

  task automatic check(input logic [22:0] value);
    int expected16, expected32;
    in16 = value[9:0];
    in32 = value;
    #1;
    expected16 = 0;
    expected32 = 0;
    for (int i = 9; i >= 0; i--) begin
      if (in16[i]) break;
      expected16++;
    end
    for (int i = 22; i >= 0; i--) begin
      if (in32[i]) break;
      expected32++;
    end
    if (empty16 !== (in16 == 0) || empty32 !== (in32 == 0))
      $fatal(1, "LZC empty result mismatch");
    if (in16 != 0 && count16 != expected16)
      $fatal(1, "LZC16 count mismatch");
    if (in32 != 0 && count32 != expected32)
      $fatal(1, "LZC32 count mismatch");
  endtask

  initial begin
    check(0);
    check('1);
    for (int i = 0; i < 23; i++) begin
      check(23'b1 << i);
      for (int j = i + 1; j < 23; j++) check((23'b1 << i) | (23'b1 << j));
    end
    // Exhaust all ten-bit mantissas as an independent check of the FP16 tree.
    for (int value = 0; value < 1024; value++) check(value);
    $display("LZC_CALIBRATION_PASS");
    $finish;
  end
endmodule
