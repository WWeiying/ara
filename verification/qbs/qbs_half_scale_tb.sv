// Standalone top: qbs_half_scale_tb. Compile as SystemVerilog, assertions enabled.
// Set the default timescale to 1ns/1ps for dependencies without a timeunit.
// Minimal source order (relative to the repository root):
//   hardware/deps/common_cells/src/cf_math_pkg.sv
//   hardware/deps/fpnew/src/fpnew_pkg.sv
//   hardware/deps/common_cells/src/lzc.sv
//   hardware/deps/fpnew/src/lfsr_sr.sv
//   hardware/deps/fpnew/src/fpnew_classifier.sv
//   hardware/deps/fpnew/src/fpnew_rounding.sv
//   hardware/deps/fpnew/src/fpnew_fma.sv
//   hardware/src/vlsu/qbs/qbs_half_scale.sv
//   verification/qbs/qbs_half_scale_tb.sv
// Include: +incdir+hardware/deps/common_cells/include
// No qbs_pkg, accumulator, DPI, vectors, or waveform setup is required.
module qbs_half_scale_tb #(
  parameter int TagWidth = 4,
  parameter int unsigned RandomPairs = 100000
);
  timeunit 1ns;
  timeprecision 1ps;
  typedef logic [TagWidth-1:0] tag_t;
  localparam int NumCorners = 20;
  localparam logic [15:0] Corners [NumCorners] = '{
    16'h0000, 16'h8000, 16'h0001, 16'h8001, 16'h0002,
    16'h03ff, 16'h83ff, 16'h0400, 16'h8400, 16'h0401,
    16'h3bff, 16'h3c00, 16'hbc00, 16'h3c01, 16'h3fff,
    16'h4000, 16'hc000, 16'h7800, 16'h7bff, 16'hfbff
  };

  logic clk = 1'b0;
  always #5ns clk = ~clk;
  // reset_pipeline drives a real falling edge before the first clock edge.
  logic rst_n = 1'b1;
  logic valid_i = 1'b0;
  logic [15:0] a_i = '0, b_i = '0;
  tag_t tag_i = '0;
  logic valid_o, busy_o;
  logic [31:0] result_o;
  tag_t tag_o;
  logic [2:0][31:0] reference_operands;
  logic reference_ready, reference_valid;
  logic [31:0] reference_result;
  tag_t reference_tag;
  fpnew_pkg::status_t reference_flags;

  bit pending_valid = 1'b0;
  tag_t pending_tag;
  logic [15:0] pending_a, pending_b;
  longint unsigned issued = 0, checked = 0, cancelled = 0, cycles = 0;
  longint unsigned exhaustive_count = 0, subnormal_count = 0;
  int unsigned bubble_count = 0, reset_count = 0;
  logic [31:0] random_state = 32'h5a17c9e3;

  qbs_half_scale #(.TagWidth(TagWidth)) dut (
    .clk_i(clk), .rst_ni(rst_n), .valid_i(valid_i), .a_i(a_i), .b_i(b_i),
    .tag_i(tag_i), .valid_o(valid_o), .result_o(result_o), .tag_o(tag_o), .busy_o(busy_o)
  );

  // This is a format conversion, not a model of the DUT's product/exponent path.
  // Subnormals are expanded one half-mantissa bit at a time before FP32 MUL.
  function automatic logic [31:0] half_to_float(input logic [15:0] half_bits);
    logic [10:0] fraction;
    logic [7:0] exponent;
    assert (!$isunknown(half_bits) && half_bits[14:10] != 5'h1f)
      else $fatal(1, "Nonfinite half passed to reference conversion: %h", half_bits);
    if (half_bits[14:0] == '0) return {half_bits[15], 31'b0};
    if (half_bits[14:10] != '0) begin
      exponent = {3'b0, half_bits[14:10]} + 8'd112;
      return {half_bits[15], exponent, half_bits[9:0], 13'b0};
    end
    fraction = {1'b0, half_bits[9:0]};
    exponent = 8'd113;
    while (!fraction[10]) begin
      fraction = fraction << 1;
      exponent = exponent - 8'd1;
    end
    return {half_bits[15], exponent, fraction[9:0], 13'b0};
  endfunction

  always_comb begin
    reference_operands = '0;
    if (valid_i) begin
      reference_operands[0] = half_to_float(a_i);
      reference_operands[1] = half_to_float(b_i);
    end
  end

  fpnew_fma #(
    .FpFormat(fpnew_pkg::FP32), .NumPipeRegs(2), .PipeConfig(fpnew_pkg::AFTER),
    .TagType(tag_t), .AuxType(logic)
  ) i_reference_mul (
    .clk_i(clk), .rst_ni(rst_n), .operands_i(reference_operands), .is_boxed_i(3'b111),
    .rnd_mode_i(fpnew_pkg::RNE), .op_i(fpnew_pkg::MUL), .op_mod_i(1'b0),
    .tag_i(tag_i), .mask_i(1'b1), .aux_i(1'b0), .in_valid_i(valid_i),
    .in_ready_o(reference_ready), .flush_i(1'b0), .result_o(reference_result),
    .status_o(reference_flags), .extension_bit_o(), .tag_o(reference_tag),
    .mask_o(), .aux_o(), .out_valid_o(reference_valid), .out_ready_i(1'b1), .busy_o()
  );

  function automatic logic [31:0] next_random();
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
  endfunction

  function automatic logic [15:0] random_half();
    logic [15:0] value;
    do value = 16'(next_random()); while (value[14:10] == 5'h1f);
    return value;
  endfunction

  // One task owns stimulus and sampling, avoiding monitor/driver races.
  // pending_* models only transaction timing, never floating-point arithmetic.
  task automatic cycle(input bit valid, input logic [15:0] a, b, input tag_t tag);
    @(negedge clk);
    a_i = a;
    b_i = b;
    tag_i = tag;
    valid_i = valid;
    @(posedge clk);
    assert (reference_ready === 1'b1) else $fatal(1, "FPnew reference backpressured");
    #1ns;
    cycles++;
    assert (valid_o === pending_valid && reference_valid === pending_valid)
      else $fatal(1, "Latency/bubble mismatch cycle=%0d dut=%b ref=%b expected=%b",
                  cycles, valid_o, reference_valid, pending_valid);
    assert (busy_o === (pending_valid | valid))
      else $fatal(1, "Busy mismatch cycle=%0d got=%b expected=%b",
                  cycles, busy_o, pending_valid | valid);
    if (pending_valid) begin
      assert (tag_o === pending_tag && reference_tag === pending_tag)
        else $fatal(1, "Tag mismatch cycle=%0d dut=%h ref=%h expected=%h",
                    cycles, tag_o, reference_tag, pending_tag);
      assert (reference_flags === 5'b00000)
        else $fatal(1, "FPnew flags=%b for a=%h b=%h", reference_flags, pending_a, pending_b);
      assert (!$isunknown(reference_result) && result_o === reference_result)
        else $fatal(1, "Product mismatch a=%h b=%h dut=%h ref=%h tag=%h cycle=%0d",
                    pending_a, pending_b, result_o, reference_result, pending_tag, cycles);
      checked++;
    end
    pending_valid = valid;
    pending_a = a;
    pending_b = b;
    pending_tag = tag;
    if (valid) issued++;
    else bubble_count++;
  endtask

  task automatic send(input logic [15:0] a, b);
    cycle(1'b1, a, b, tag_t'(next_random()));
  endtask

  task automatic bubble();
    // Nonfinite payload and unknown tags on invalid cycles must be ignored.
    cycle(1'b0, 16'h7e00, 16'hfc00, 'x);
  endtask

  task automatic reset_pipeline();
    // Assert away from a clock edge and inspect asynchronous valid cancellation.
    #1ns;
    rst_n = 1'b0;
    valid_i = 1'b0;
    if (pending_valid) cancelled++;
    pending_valid = 1'b0;
    #1ns;
    assert (valid_o === 1'b0 && busy_o === 1'b0 && reference_valid === 1'b0)
      else $fatal(1, "Reset did not cancel valid/busy asynchronously");
    repeat (2) begin
      @(posedge clk);
      #1ns;
      assert (valid_o === 1'b0 && busy_o === 1'b0 && reference_valid === 1'b0)
        else $fatal(1, "Valid/busy escaped held reset");
    end
    @(negedge clk);
    rst_n = 1'b1;
    reset_count++;
    repeat (3) bubble();
  endtask

  task automatic check_conversion(input logic [15:0] h, input logic [31:0] f);
    assert (half_to_float(h) === f)
      else $fatal(1, "Reference conversion anchor failed half=%h expected=%h", h, f);
  endtask

  initial begin : run
    logic [15:0] random_a, random_b, boundary;
    logic [31:0] choice;
    reset_pipeline();
    check_conversion(16'h0000, 32'h00000000);
    check_conversion(16'h8000, 32'h80000000);
    check_conversion(16'h0001, 32'h33800000);
    check_conversion(16'h8001, 32'hb3800000);
    check_conversion(16'h0200, 32'h38000000);
    check_conversion(16'h03ff, 32'h387fc000);
    check_conversion(16'h0400, 32'h38800000);
    check_conversion(16'h0401, 32'h38802000);
    check_conversion(16'h3c00, 32'h3f800000);
    check_conversion(16'hbc00, 32'hbf800000);
    check_conversion(16'h7bff, 32'h477fe000);
    check_conversion(16'hfbff, 32'hc77fe000);

    // Reset with stage 1 only, both stages, and stage 2 only occupied.
    send(16'h0001, 16'hfbff);
    assert (busy_o && !valid_o) else $fatal(1, "Missing stage-1 reset setup");
    reset_pipeline();
    send(16'h3c01, 16'hbc01);
    send(16'h7bff, 16'h7bff);
    assert (busy_o && valid_o && pending_valid) else $fatal(1, "Missing full reset setup");
    reset_pipeline();
    send(16'h8000, 16'hbc00);
    bubble();
    assert (busy_o && valid_o && !pending_valid) else $fatal(1, "Missing stage-2 reset setup");
    reset_pipeline();

    // Alternating valids, bursts, and multiple bubble lengths.
    for (int i = 0; i < 128; i++) begin
      send(Corners[i % NumCorners], Corners[(i * 7 + 3) % NumCorners]);
      repeat (i % 5) bubble();
    end
    for (int exponent = 1; exponent <= 30; exponent++) begin
      boundary = {1'b0, 5'(exponent), 10'b0};
      for (int delta = -1; delta <= 1; delta++) begin
        send(16'(int'(boundary) + delta), boundary ^ 16'h8000);
        send(boundary ^ 16'h8000, 16'(int'(boundary) + delta));
      end
    end

    // All 63,488 finite encodings, each corner on BOTH operand ports.
    for (int h = 0; h < 65536; h++) begin
      if ((h & 'h7c00) == 'h7c00) continue;
      for (int c = 0; c < NumCorners; c++) begin
        send(16'(h), Corners[c]);
        send(Corners[c], 16'(h));
        exhaustive_count += 2;
      end
      if ((h & 'hff) == 0) bubble();
    end
    repeat (3) bubble();
    assert (exhaustive_count == 64'd63488 * NumCorners * 2)
      else $fatal(1, "Incomplete finite/corner sweep: %0d", exhaustive_count);
    $display("Half scale finite/corner sweep: %0d checked pairs", exhaustive_count);

    // Every nonnegative subnormal magnitude pair, including zero.
    // Signed subnormals and both signed zeros are also covered above.
    for (int a = 0; a < 1024; a++) begin
      for (int b = 0; b < 1024; b++) begin
        send(16'(a), 16'(b));
        subnormal_count++;
      end
    end
    repeat (3) bubble();
    assert (subnormal_count == 64'd1048576)
      else $fatal(1, "Incomplete subnormal matrix: %0d", subnormal_count);
    $display("Half scale subnormal matrix: %0d checked pairs", subnormal_count);

    for (int unsigned i = 0; i < RandomPairs; i++) begin
      random_a = random_half();
      random_b = random_half();
      choice = next_random();
      send(random_a, random_b);
      if (choice[2:0] == 0) repeat (1 + int'(choice[4:3])) bubble();
    end
    repeat (4) bubble();
    assert (checked + cancelled == issued && cancelled == 2 && reset_count == 4 &&
            bubble_count > 0 && !busy_o && !valid_o && !reference_valid)
      else $fatal(1, "Final accounting failed issued=%0d checked=%0d cancelled=%0d resets=%0d",
                  issued, checked, cancelled, reset_count);
    $display("QBS half scale PASS: checked=%0d cancelled=%0d corners=%0d subnormal=%0d random=%0d cycles=%0d",
             checked, cancelled, exhaustive_count, subnormal_count, RandomPairs, cycles);
    $finish;
  end

  initial begin
    #100ms;
    $fatal(1, "QBS half scale watchdog: issued=%0d checked=%0d", issued, checked);
  end
endmodule
