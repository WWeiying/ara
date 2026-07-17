// Directed differential checks for fp32_exact_reduction_accum.

module fp32_exact_reduction_accum_tb;
  logic clk;
  logic rst_n;
  logic start;
  logic [2:0] rnd_mode;
  logic seed_valid;
  logic [31:0] seed;
  logic [63:0] data;
  logic [1:0] active;
  logic last;
  logic in_valid;
  logic in_ready;
  logic [31:0] result;
  logic [4:0] status;
  logic out_valid;
  logic out_ready;
  logic busy;

  int unsigned checks;

  fp32_exact_reduction_accum i_dut (
    .clk_i        (clk),
    .rst_ni       (rst_n),
    .start_i      (start),
    .rnd_mode_i   (rnd_mode),
    .seed_valid_i (seed_valid),
    .seed_i       (seed),
    .data_i       (data),
    .active_i     (active),
    .last_i       (last),
    .in_valid_i   (in_valid),
    .in_ready_o   (in_ready),
    .result_o     (result),
    .status_o     (status),
    .out_valid_o  (out_valid),
    .out_ready_i  (out_ready),
    .busy_o       (busy)
  );

  always #5 clk = ~clk;

  task automatic start_case(
    input logic seed_is_valid,
    input logic [31:0] seed_value,
    input logic [2:0] mode
  );
    begin
      wait (!busy);
      @(negedge clk);
      seed_valid = seed_is_valid;
      seed       = seed_value;
      rnd_mode   = mode;
      start      = 1'b1;
      @(negedge clk);
      start      = 1'b0;
      seed_valid = 1'b0;
      seed       = '0;
    end
  endtask

  task automatic push_beat(
    input logic [31:0] high,
    input logic [31:0] low,
    input logic [1:0] element_active,
    input logic is_last
  );
    begin
      wait (in_ready);
      @(negedge clk);
      data     = {high, low};
      active   = element_active;
      last     = is_last;
      in_valid = 1'b1;
      @(negedge clk);
      in_valid = 1'b0;
      data     = '0;
      active   = '0;
      last     = 1'b0;
    end
  endtask

  task automatic expect_result(
    input logic [31:0] expected_result,
    input logic [4:0] expected_status,
    input string case_name
  );
    begin
      wait (out_valid);
      #1;
      checks++;
      if (result !== expected_result || status !== expected_status) begin
        $error("%s: result=%08x status=%02x, expected=%08x/%02x",
               case_name, result, status, expected_result, expected_status);
        $fatal(1);
      end
      @(posedge clk);
    end
  endtask

  initial begin
    clk        = 1'b0;
    rst_n      = 1'b0;
    start      = 1'b0;
    rnd_mode   = '0;
    seed_valid = 1'b0;
    seed       = '0;
    data       = '0;
    active     = '0;
    last       = 1'b0;
    in_valid   = 1'b0;
    out_ready  = 1'b1;
    checks     = 0;

    repeat (3) @(posedge clk);
    rst_n = 1'b1;

    // Basic exact arithmetic and use of both FP32 elements in one source beat.
    start_case(1'b1, 32'h00000000, 3'b000);
    push_beat(32'h40000000, 32'h3f800000, 2'b11, 1'b1);
    expect_result(32'h40400000, 5'b00000, "1 + 2");

    // The exact backend retains the unit term that a sequential FP32 chain
    // loses: 1e20 + 1 - 1e20 = 1.
    start_case(1'b1, 32'h00000000, 3'b000);
    push_beat(32'h3f800000, 32'h60ad78ec, 2'b11, 1'b0);
    push_beat(32'h00000000, 32'he0ad78ec, 2'b01, 1'b1);
    expect_result(32'h3f800000, 5'b00000, "catastrophic cancellation");

    // 1 + 2^-24 is exactly halfway between adjacent binary32 values.
    start_case(1'b1, 32'h00000000, 3'b000);
    push_beat(32'h33800000, 32'h3f800000, 2'b11, 1'b1);
    expect_result(32'h3f800000, 5'b00001, "RNE tie-to-even");

    start_case(1'b1, 32'h00000000, 3'b100);
    push_beat(32'h33800000, 32'h3f800000, 2'b11, 1'b1);
    expect_result(32'h3f800001, 5'b00001, "RMM tie-away");

    start_case(1'b1, 32'h00000000, 3'b011);
    push_beat(32'h33800000, 32'h3f800000, 2'b11, 1'b1);
    expect_result(32'h3f800001, 5'b00001, "RUP positive");

    start_case(1'b1, 32'h00000000, 3'b010);
    push_beat(32'hb3800000, 32'hbf800000, 2'b11, 1'b1);
    expect_result(32'hbf800001, 5'b00001, "RDN negative");

    // Overflow direction and exception flags.
    start_case(1'b1, 32'h00000000, 3'b000);
    push_beat(32'h7f7fffff, 32'h7f7fffff, 2'b11, 1'b1);
    expect_result(32'h7f800000, 5'b00101, "RNE overflow");

    start_case(1'b1, 32'h00000000, 3'b001);
    push_beat(32'h7f7fffff, 32'h7f7fffff, 2'b11, 1'b1);
    expect_result(32'h7f7fffff, 5'b00101, "RTZ overflow");

    // Special-value behavior follows an exact IEEE addition tree.
    start_case(1'b1, 32'h00000000, 3'b000);
    push_beat(32'h3f800000, 32'h7f800001, 2'b11, 1'b1);
    expect_result(32'h7fc00000, 5'b10000, "signalling NaN");

    start_case(1'b1, 32'h00000000, 3'b000);
    push_beat(32'hff800000, 32'h7f800000, 2'b11, 1'b1);
    expect_result(32'h7fc00000, 5'b10000, "opposite infinities");

    start_case(1'b1, 32'h00000000, 3'b000);
    push_beat(32'h3f800000, 32'h7fc12345, 2'b11, 1'b1);
    expect_result(32'h7fc00000, 5'b00000, "quiet NaN");

    // A qNaN already present in the fixed tree suppresses a later
    // +Inf/-Inf invalid operation; this checks node-order-accurate flags.
    start_case(1'b1, 32'h7fc12345, 3'b000);
    push_beat(32'hff800000, 32'h7f800000, 2'b11, 1'b1);
    expect_result(32'h7fc00000, 5'b00000, "quiet NaN dominates infinity conflict");

    // Signed-zero selection, including an empty subtree identity.
    start_case(1'b1, 32'h80000000, 3'b000);
    push_beat(32'h80000000, 32'h80000000, 2'b11, 1'b1);
    expect_result(32'h80000000, 5'b00000, "same-sign negative zero");

    start_case(1'b1, 32'h00000000, 3'b010);
    push_beat(32'h80000000, 32'h00000000, 2'b11, 1'b1);
    expect_result(32'h80000000, 5'b00000, "mixed zero under RDN");

    start_case(1'b0, 32'h00000000, 3'b010);
    push_beat(32'h00000000, 32'h00000000, 2'b00, 1'b1);
    expect_result(32'h00000000, 5'b00000, "empty RDN identity");

    // With no active vector source, RVV copies the scalar seed without
    // canonicalizing it and without generating NV.
    start_case(1'b1, 32'h7f800001, 3'b000);
    push_beat(32'h00000000, 32'h00000000, 2'b00, 1'b1);
    expect_result(32'h7f800001, 5'b00000, "inactive seed copy");

    // Exercise all four interleaved banks and output backpressure.
    start_case(1'b1, 32'h00000000, 3'b000);
    push_beat(32'h3f800000, 32'h3f800000, 2'b11, 1'b0);
    push_beat(32'h3f800000, 32'h3f800000, 2'b11, 1'b0);
    push_beat(32'h3f800000, 32'h3f800000, 2'b11, 1'b0);
    out_ready = 1'b0;
    push_beat(32'h3f800000, 32'h3f800000, 2'b11, 1'b1);
    wait (out_valid);
    repeat (3) @(posedge clk);
    if (result !== 32'h41000000 || status !== 5'b00000)
      $fatal(1, "backpressured result was not stable");
    out_ready = 1'b1;
    expect_result(32'h41000000, 5'b00000, "four-bank merge");

    $display("PASS: fp32 exact reduction accumulator (%0d checks)", checks);
    $finish;
  end

endmodule
