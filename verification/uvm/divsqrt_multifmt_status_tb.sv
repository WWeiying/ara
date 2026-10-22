// Exercise the production DIVSQRT slice and C910 units, with Ara's configuration.
module divsqrt_multifmt_status_tb;
  timeunit 1ns;
  timeprecision 1ps;
  import fpnew_pkg::*;
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, in_valid = 0, in_ready, out_valid, out_ready = 0, busy;
  logic [1:0][63:0] operands = '0;
  logic [3:0] mask = '0;
  logic [7:0] tag = '0, result_tag;
  logic [63:0] result;
  logic extension_bit;
  status_t status;
  fp_format_e fmt = FP32;
  logic [3:0] result_format_active;
  status_t shadow_format_filtered;
  int unsigned cases = 0, checks = 0, arch_failures = 0, cycles = 0;

  fpnew_opgroup_multifmt_slice #(
    .OpGroup(DIVSQRT), .Width(64), .FpFmtConfig(6'b111000), .IntFmtConfig(4'b1111),
    .EnableVectors(1'b1), .DivSqrtSel(THMULTI), .NumPipeRegs(3),
    .PipeConfig(DISTRIBUTED), .TagType(logic [7:0])
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .hart_id_i(32'b0), .operands_i(operands),
    .is_boxed_i('1), .rnd_mode_i(RNE), .op_i(DIV), .op_mod_i(1'b0),
    .src_fmt_i(fmt), .dst_fmt_i(fmt), .int_fmt_i(INT32), .vectorial_op_i(1'b1),
    .tag_i(tag), .simd_mask_i(mask), .in_valid_i(in_valid), .in_ready_o(in_ready),
    .flush_i(1'b0), .result_o(result), .status_o(status), .extension_bit_o(extension_bit),
    .tag_o(result_tag), .out_valid_o(out_valid), .out_ready_i(out_ready), .busy_o(busy)
  );

  always @(posedge clk) if (rst_n) cycles++;
  for (genvar lane = 0; lane < 4; lane++) begin : probes
    assign result_format_active[lane] = dut.gen_num_lanes[lane].ACTIVE_FORMATS[dut.result_fmt];
    always @(posedge clk) if (rst_n) begin
      if (in_valid && in_ready)
        $display("LANE_INPUT cycle=%0d tag=%0d lane=%0d formats=%b used=%b valid=%b mask=%b operands=%h aux=%h",
          cycles, tag, lane, dut.gen_num_lanes[lane].ACTIVE_FORMATS,
          dut.gen_num_lanes[lane].active_lane.lane_is_used,
          dut.gen_num_lanes[lane].active_lane.in_valid, mask[lane],
          dut.gen_num_lanes[lane].active_lane.local_operands, dut.aux_data);
      if (out_valid && out_ready)
        $display("LANE_OUTPUT cycle=%0d tag=%0d lane=%0d valid=%b raw_status=%02h lane_status=%02h mask=%b aux=%h result_fmt=%0d format_active=%b local_result=%h",
          cycles, result_tag, lane, dut.lane_out_valid[lane],
          dut.gen_num_lanes[lane].active_lane.op_status, dut.lane_status[lane],
          dut.lane_masks[lane], dut.lane_aux[lane], dut.result_fmt,
          result_format_active[lane], dut.gen_num_lanes[lane].active_lane.op_result);
    end
  end

  // Observation only: no connection back to the DUT.
  always_comb begin
    shadow_format_filtered = '0;
    for (int i = 0; i < 4; i++)
      shadow_format_filtered |= dut.lane_status[i] & {5{dut.lane_masks[i] && result_format_active[i]}};
  end

  task automatic check(input logic condition, input string message);
    checks++;
    if (condition !== 1'b1) $fatal(1, "CHECK_FAIL case=%0d %s", cases, message);
  endtask

  task automatic run_case(input fp_format_e format, input logic [3:0] masks,
      input logic [63:0] numerator, input logic [63:0] expected_result,
      input logic [4:0] expected_flags, input logic [3:0] expected_masks);
    int wait_cycles;
    logic [4:0] observed;
    cases++;
    @(negedge clk);
    fmt = format;
    mask = masks;
    operands = {64'b0, numerator};
    tag = 8'(cases);
    in_valid = 1;
    wait_cycles = 0;
    do begin
      @(posedge clk);
      wait_cycles++;
      check(wait_cycles < 200, "input handshake timeout");
    end while (!in_ready);
    @(negedge clk);
    in_valid = 0;
    // Make sure output status selection uses the returned aux, not live inputs.
    fmt = FP64;
    mask = ~masks;
    operands = '1;
    wait_cycles = 0;
    while (!out_valid) begin
      @(negedge clk);
      wait_cycles++;
      check(wait_cycles < 200, "DIVSQRT synchronization/output timeout");
    end
    observed = status;
    check(result === expected_result, "numerical result mismatch");
    check(result_tag === 8'(cases), "tag mismatch");
    check(dut.lane_out_valid === 4'b1111, "all synchronization lanes must finish");
    check(dut.lane_masks === expected_masks, "returned masks mismatch");
    check(dut.result_fmt == format && dut.result_is_vector, "returned aux format mismatch");
    check(shadow_format_filtered === expected_flags, "format-filtered shadow does not match architecture");
    if (observed !== expected_flags) begin
      arch_failures++;
      $display("ARCH_FAIL case=%0d fmt=%0d mask=%b flags=%02h expected=%02h", cases, format, masks, observed, expected_flags);
    end
    $display("RESULT case=%0d fmt=%0d mask=%b data=%h flags=%02h expected=%02h shadow_filtered=%02h active=%b wait_cycles=%0d",
      cases, format, masks, result, observed, expected_flags, shadow_format_filtered,
      result_format_active, wait_cycles);
    repeat (2) begin
      @(negedge clk);
      check(out_valid && result === expected_result && status === observed &&
            result_tag === 8'(cases) && dut.lane_masks === expected_masks &&
            dut.result_fmt == format && dut.result_is_vector,
            "result/flags not stable under output backpressure");
    end
    out_ready = 1;
    @(posedge clk);
    @(negedge clk);
    out_ready = 0;
    check(!out_valid, "duplicate response");
  endtask

  initial begin
    if ($test$plusargs("EXPECT_OLD_BUG"))
      $fatal(1, "CHECK_FAIL historical bug reproduction is not supported");
    $display("CONFIG Width=64 FpFmtConfig=111000 DivSqrtSel=THMULTI NumPipeRegs=3 PipeConfig=DISTRIBUTED");
    repeat (4) @(posedge clk);
    @(negedge clk);
    rst_n = 1;
    // Physical masks are in FP16 positions: FP32 uses bits 0/2, FP64 bit 0.
    // Inactive synchronization lanes must return a zero mask.
    run_case(FP32, 4'b1111, 64'h40200000_3fc00000, 64'h7f800000_7f800000, 5'h08, 4'b0011);
    run_case(FP32, 4'b0011, 64'h40200000_3fc00000, 64'h7f800000_7f800000, 5'h08, 4'b0001);
    run_case(FP32, 4'b1100, 64'h40200000_3fc00000, 64'h7f800000_7f800000, 5'h08, 4'b0010);
    run_case(FP32, 4'b1010, 64'h40200000_3fc00000, 64'h7f800000_7f800000, 5'h00, 4'b0000);
    run_case(FP16, 4'b1111, 64'h4100_3e00_4100_3e00, 64'h7c00_7c00_7c00_7c00, 5'h08, 4'b1111);
    run_case(FP32, 4'b0011, 64'h00000000_3fc00000, 64'h7fc00000_7f800000, 5'h08, 4'b0001);
    run_case(FP32, 4'b1100, 64'h00000000_3fc00000, 64'h7fc00000_7f800000, 5'h10, 4'b0010);
    run_case(FP64, 4'b1111, 64'h3ff8000000000000, 64'h7ff0000000000000, 5'h08, 4'b0001);
    run_case(FP64, 4'b1110, 64'h3ff8000000000000, 64'h7ff0000000000000, 5'h00, 4'b0000);
    $display("SUMMARY cases=%0d checks=%0d cycles=%0d architectural_failures=%0d", cases, checks, cycles, arch_failures);
    check(arch_failures == 0, "architectural flags failed");
    $display("PASS divsqrt_multifmt_status");
    $finish;
  end
  initial begin
    #100000;
    $fatal(1, "CHECK_FAIL watchdog timeout");
  end
endmodule
