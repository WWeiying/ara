`timescale 1ns/1ps
module acc_request_pipeline_tb;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic valid_i = 0, ready_i = 0;
  logic ready_o, valid_o;
  logic [191:0] data_i = 0, data_o;
  logic [191:0] expected [0:20000];
  int wr = 0, rd = 0, transfers = 0;
  logic [31:0] rng = 32'h641890ab;

  spill_register #(.T(logic [191:0]), .Bypass(1'b0)) dut (
    .clk_i(clk), .rst_ni(rst_n), .valid_i, .ready_o, .data_i,
    .valid_o, .ready_i, .data_o
  );

  function automatic logic [191:0] payload(input int n);
    return {32'(n), ~32'(n), 32'hc0ffee55 ^ 32'(n),
            32'h12345678 + 32'(n), 32'(n * 17), 32'(n * 97)};
  endfunction

  // Compare before the edge: a newly accepted item must not bypass storage.
  task automatic step(input bit send, input bit consume);
    bit push, pop, prior_valid, prior_ready;
    logic [191:0] prior_data;
    @(negedge clk);
    prior_valid = valid_o;
    prior_ready = ready_o;
    prior_data = data_o;
    valid_i = send;
    data_i = payload(wr);
    ready_i = consume;
    #1;
    if (valid_o !== prior_valid || data_o !== prior_data || ready_o !== prior_ready)
      $fatal(1, "Combinational path through registered boundary");
    push = valid_i && ready_o;
    pop = valid_o && ready_i;
    if (valid_o && (rd == wr || data_o !== expected[rd]))
      $fatal(1, "Unexpected/reordered data rd=%0d wr=%0d", rd, wr);
    if (wr - rd == 2 && ready_o) $fatal(1, "Overfull admission");
    @(posedge clk);
    if (pop) begin rd++; transfers++; end
    if (push) begin expected[wr] = data_i; wr++; end
    #1;
    if (wr - rd < 0 || wr - rd > 2) $fatal(1, "Capacity mismatch");
    if (prior_valid && !consume && (!valid_o || data_o !== prior_data))
      $fatal(1, "Backpressure changed held request");
  endtask

  initial begin
    repeat (3) @(negedge clk);
    rst_n = 1;
    step(1, 0);
    if (!valid_o || wr != 1 || rd != 0) $fatal(1, "First request latency");
    step(1, 0);
    if (ready_o || wr != 2) $fatal(1, "Two-slot capacity");
    repeat (12) step(0, 0); // upstream cancellation cannot discard accepted work
    repeat (3) step(0, 1);
    if (rd != wr) $fatal(1, "Drain failure");
    step(1, 1);
    transfers = 0;
    repeat (1024) step(1, 1);
    if (transfers != 1024) $fatal(1, "Throughput below one request/cycle");
    repeat (10000) begin
      rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
      step(rng[0], rng[7]);
    end
    repeat (3) step(0, 1);
    if (rd != wr || valid_o) $fatal(1, "Final drain failure");
    step(1, 0);
    step(1, 0);
    @(negedge clk);
    rst_n = 0;
    #1;
    if (valid_o || !ready_o) $fatal(1, "Reset did not empty queue");
    $display("PASS: order, capacity, stall, cancellation, reset, no bypass; 1024/1024 sustained transfers; checked=%0d", rd);
    $finish;
  end
  initial begin
    #200000;
    $fatal(1, "Watchdog");
  end
endmodule
