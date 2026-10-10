module fp_div_flags_tb;
  import fpnew_pkg::*;
  logic clk = 0;
  always #5 clk = !clk;
  logic rst_n = 0;
  logic [1:0][63:0] operands;
  fp_format_e fmt = FP32;
  logic [3:0] mask;
  logic valid = 0, ready, out_valid, busy;
  logic [63:0] result;
  status_t status;
  logic [7:0] tag, out_tag;
  int cases = 0, failures = 0;

  fpnew_opgroup_multifmt_slice #(
    .OpGroup(DIVSQRT), .Width(64), .FpFmtConfig(6'b111000),
    .IntFmtConfig('1), .EnableVectors(1), .DivSqrtSel(THMULTI),
    .NumPipeRegs(0), .TagType(logic [7:0])
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .hart_id_i('0),
    .operands_i(operands), .is_boxed_i('1), .rnd_mode_i(RNE),
    .op_i(DIV), .op_mod_i(1'b0), .src_fmt_i(fmt), .dst_fmt_i(fmt),
    .int_fmt_i(INT32), .vectorial_op_i(1'b1), .tag_i(tag),
    .simd_mask_i(mask), .in_valid_i(valid), .in_ready_o(ready),
    .flush_i(1'b0), .result_o(result), .status_o(status),
    .extension_bit_o(), .tag_o(out_tag), .out_valid_o(out_valid),
    .out_ready_i(1'b1), .busy_o(busy)
  );

  task automatic run_case(input fp_format_e f, input logic [3:0] m,
                          input logic [63:0] numerator,
                          input logic [4:0] expected_flags,
                          input logic [63:0] expected_result);
    int waited;
    @(negedge clk);
    fmt = f;
    mask = m;
    operands[0] = numerator;
    operands[1] = 0;
    tag = 8'(cases);
    valid = 1;
    waited = 0;
    do begin
      @(posedge clk);
      if (++waited > 1000) $fatal(1, "input timeout");
    end while (!ready);
    @(negedge clk);
    valid = 0;
    waited = 0;
    do begin
      @(posedge clk);
      if (++waited > 1000) $fatal(1, "output timeout");
    end while (!out_valid);
    $display("DIV_PROBE case=%0d fmt=%0d mask=%b latency=%0d result=%h flags=%02h expected=%02h lane_flags=%h lane_masks=%b returned_fmt=%0d",
             cases, f, m, waited, result, status, expected_flags,
             dut.lane_status, dut.lane_masks, dut.result_fmt);
    if (status !== status_t'(expected_flags) || result !== expected_result || out_tag !== tag) begin
      failures++;
      $display("DIV_FAILURE case=%0d", cases);
    end
    cases++;
    repeat (2) @(negedge clk);
  endtask

  initial begin
    operands = '0;
    mask = '0;
    tag = '0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    run_case(FP32, 4'b1111, 64'h402000003fc00000, 5'h08, 64'h7f8000007f800000);
    run_case(FP64, 4'b1111, 64'h3ff8000000000000, 5'h08, 64'h7ff0000000000000);
    run_case(FP16, 4'b1111, 64'h3e003e003e003e00, 5'h08, 64'h7c007c007c007c00);
    run_case(FP32, 4'b0001, 64'h402000003fc00000, 5'h08, 64'h7f8000007f800000);
    run_case(FP32, 4'b0011, 64'h402000003fc00000, 5'h08, 64'h7f8000007f800000);
    run_case(FP32, 4'b1100, 64'h402000003fc00000, 5'h08, 64'h7f8000007f800000);
    run_case(FP32, 4'b0000, 64'h402000003fc00000, 5'h00, 64'h7f8000007f800000);
    run_case(FP64, 4'b1110, 64'h3ff8000000000000, 5'h00, 64'h7ff0000000000000);
    // Masks use positions in the finest supported (FP16) format. Each FP32
    // element occupies two positions; its architectural mask is the low one.
    run_case(FP32, 4'b0011, 64'h000000003fc00000, 5'h08, 64'h7fc000007f800000);
    run_case(FP32, 4'b1100, 64'h000000003fc00000, 5'h10, 64'h7fc000007f800000);
    $display("DIV_SUMMARY cases=%0d failures=%0d", cases, failures);
    if (failures) $fatal(1, "DIV flags mismatch");
    $display("PASS fp_div_flags");
    $finish;
  end
endmodule
