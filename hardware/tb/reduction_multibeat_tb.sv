// SPDX-License-Identifier: SHL-0.51
// Exercise both numeric representations, seed arrival choices, input bubbles,
// start with/without input, and sustained output backpressure. The expected
// source sum and final rounding come from Python arbitrary-precision integers.
module reduction_multibeat_tb;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, start = 0, in_valid = 0, last = 0, out_ready = 0;
  logic fp16;
  logic [2:0] rm;
  logic [31:0] seed;
  logic [63:0] data;
  logic [3:0] active;
  logic [2:0] busy, ready, valid;
  logic [287:0] exact [3];
  logic [31:0] result [3];
  logic [4:0] status [3];

  for (genvar impl = 0; impl < 3; impl++) begin : gen_impl
    logic [3:0] special;
    logic source_seen, nonzero, pos_zero, neg_zero;
    logic [2:0] state_rm;
    logic state_fp16;
    fp32_exact_reduction_accum #(
      .ExponentSegmented(impl != 1), .EmitRoundedResult(0), .DeferSeed(1)
    ) dut (
      .clk_i(clk), .rst_ni(rst_n), .start_i(start), .rnd_mode_i(rm),
      .format_fp16_i(fp16), .seed_valid_i(impl != 2), .seed_i(seed),
      .data_i(data), .active_i(active), .last_i(last),
      .in_valid_i(in_valid), .in_ready_o(ready[impl]),
      .result_o(), .status_o(), .out_valid_o(valid[impl]),
      .out_ready_i(out_ready), .busy_o(busy[impl]),
      .exact_value_o(exact[impl]), .special_o(special),
      .source_seen_o(source_seen), .finite_nonzero_seen_o(nonzero),
      .pos_zero_seen_o(pos_zero), .neg_zero_seen_o(neg_zero),
      .seed_valid_o(), .seed_o(), .rnd_mode_o(state_rm),
      .format_fp16_o(state_fp16)
    );
    fp32_exact_reduction_finalize finish_sum (
      .exact_value_i(exact[impl]), .special_i(special),
      .source_seen_i(source_seen), .finite_nonzero_seen_i(nonzero),
      .pos_zero_seen_i(pos_zero), .neg_zero_seen_i(neg_zero),
      .seed_valid_i(1'b1), .seed_i(seed), .seed_in_exact_i(1'b0),
      .rnd_mode_i(state_rm), .format_fp16_i(state_fp16),
      .result_o(result[impl]), .status_o(status[impl])
    );
  end

  initial begin
    #10000000;
    $fatal(1, "FAIL: multi-beat watchdog");
  end

  initial begin
    string path;
    integer fd, scanned, tests, beats, fp16_int, rm_int, random_seed;
    logic [287:0] expected_exact;
    logic [31:0] expected_result;
    logic [4:0] expected_status;
    path = "";
    void'($value$plusargs("VECTOR_FILE=%s", path));
    fd = $fopen(path, "r");
    if (!fd) $fatal(1, "FAIL: missing multi-beat vector file");
    random_seed = 32'h20261007;
    void'($urandom(random_seed));
    repeat (3) @(negedge clk);
    rst_n = 1;
    tests = 0;
    scanned = $fscanf(fd, "%d %d %h %d %h %h %h", fp16_int, rm_int,
                       seed, beats, expected_exact, expected_result, expected_status);
    while (scanned == 7) begin
      fp16 = 1'(fp16_int);
      rm = 3'(rm_int);
      if (|busy) $fatal(1, "FAIL: owner not idle between cases");
      if (tests % 2) begin
        @(negedge clk);
        start = 1;
        @(negedge clk);
        start = 0;
      end
      for (int beat = 0; beat < beats; beat++) begin
        repeat ($urandom_range(0, 3)) @(negedge clk);
        @(negedge clk);
        scanned = $fscanf(fd, "%h %h", data, active);
        if (scanned != 2) $fatal(1, "FAIL: truncated beat data");
        start = (beat == 0) && !(tests % 2);
        in_valid = 1;
        last = (beat == beats - 1);
        #1;
        if (!(&ready)) $fatal(1, "FAIL: input not ready test=%0d beat=%0d", tests, beat);
        @(negedge clk);
        start = 0;
        in_valid = 0;
      end
      wait (&valid);
      // Hold the complete packet for several cycles. Check the exact state,
      // result and flags on every cycle, rather than only their final values.
      repeat (5) begin
        @(negedge clk);
        for (int impl = 0; impl < 3; impl++) begin
          if (!valid[impl] || exact[impl] !== expected_exact ||
              {status[impl], result[impl]} !== {expected_status, expected_result})
            $fatal(1, "FAIL: case=%0d impl=%0d fp16=%0d rm=%0d beats=%0d exact=%072x expected=%072x result=%02x/%08x expected=%02x/%08x",
                   tests, impl, fp16, rm, beats, exact[impl], expected_exact,
                   status[impl], result[impl], expected_status, expected_result);
        end
      end
      out_ready = 1;
      @(negedge clk);
      out_ready = 0;
      tests++;
      scanned = $fscanf(fd, "%d %d %h %d %h %h %h", fp16_int, rm_int,
                         seed, beats, expected_exact, expected_result, expected_status);
    end
    if (!$feof(fd) || tests == 0) $fatal(1, "FAIL: malformed or empty cases");
    $fclose(fd);
    $display("PASS: multi-beat exact audit (%0d cases, 3 implementations)", tests);
    $finish;
  end
endmodule
