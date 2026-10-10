// Actual CVA6 FIFO with the dispatcher's one-cycle issue-to-push pipeline.
// This is a credit/order unit test, not a complete acc_dispatcher simulation.
module acc_queue_credit_check #(
  parameter int unsigned DEPTH = 4
) (
  input logic clk_i,
  output bit done_o
);
  timeunit 1ns;
  timeprecision 1ps;
  localparam int unsigned USAGE_WIDTH = $clog2(DEPTH);
  typedef logic [USAGE_WIDTH-1:0] usage_t;
  typedef logic [31:0] data_t;

  logic rst_ni = 0;
  logic flush_ex = 0, flush_unissued = 0;
  logic issue_want = 0, pop_want = 0;
  logic issue_hs, acc_valid_d, acc_valid_q;
  logic full, empty, pop, acc_ready, old_ready;
  usage_t usage;
  data_t issue_data = 0, pending_data_q, data_out;

  assign acc_ready = !full && usage < (DEPTH - 1);
  assign old_ready = usage < (DEPTH - 1);
  assign issue_hs = issue_want && acc_ready;
  assign acc_valid_d = issue_hs && !flush_unissued;
  assign pop = pop_want && !empty && !flush_unissued;

  // flush_ex clears the FIFO, not acc_valid_q; flush_unissued gates its D input.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      acc_valid_q <= 0;
      pending_data_q <= 0;
    end else begin
      acc_valid_q <= acc_valid_d;
      if (acc_valid_d) pending_data_q <= issue_data;
    end
  end

  cva6_fifo_v3 #(
    .DEPTH(DEPTH), .FALL_THROUGH(1'b1), .FPGA_EN(1'b0), .dtype(data_t)
  ) dut (
    .clk_i, .rst_ni, .flush_i(flush_ex), .testmode_i(1'b0),
    .full_o(full), .empty_o(empty), .usage_o(usage),
    .data_i(pending_data_q), .push_i(acc_valid_q), .data_o(data_out), .pop_i(pop)
  );

  data_t expected_fifo[$];
  bit expected_pending = 0;
  data_t expected_pending_data = 0;
  bit old_full_issue_q = 0;
  int unsigned cycles = 0, issued = 0, popped = 0, discarded = 0;
  int unsigned full_cycles = 0, both_cycles = 0, bypass_cycles = 0;
  int unsigned pipeline_cycles = 0, reserve_stalls = 0, full_pops = 0;
  int unsigned flush_pending = 0, flush_full = 0, flush_count = 0;
  int unsigned old_full_issues = 0, old_full_pushes = 0;

  task automatic check_state;
    int count;
    count = expected_fifo.size();
    assert (full === (count == DEPTH) &&
            empty === (count == 0 && !expected_pending) &&
            usage === usage_t'(count))
      else $fatal(1, "depth=%0d cycle=%0d count=%0d flags=%b/%b usage=%0d",
                  DEPTH, cycles, count, full, empty, usage);
    assert (acc_valid_q === expected_pending)
      else $fatal(1, "depth=%0d cycle=%0d pending pipeline mismatch", DEPTH, cycles);
    if (expected_pending)
      assert (pending_data_q === expected_pending_data)
        else $fatal(1, "depth=%0d cycle=%0d pending data mismatch", DEPTH, cycles);
    // Reference count is untruncated and independent of the FIFO's status bits.
    assert (acc_ready === (count < DEPTH - 1))
      else $fatal(1, "depth=%0d cycle=%0d incorrect ready", DEPTH, cycles);
    assert (count + int'(expected_pending) <= DEPTH)
      else $fatal(1, "depth=%0d cycle=%0d overcommitted credit", DEPTH, cycles);
    assert (issued == popped + discarded + count + int'(expected_pending))
      else $fatal(1, "depth=%0d cycle=%0d lost/duplicated issue", DEPTH, cycles);
  endtask

  task automatic step(input bit want_issue, input bit want_pop,
                      input bit do_flush = 0, input bit kill_issue = 0);
    bit accepted, old_full_issue;
    data_t expected_head;
    int count;
    @(negedge clk_i);
    issue_want = want_issue;
    pop_want = want_pop;
    flush_ex = do_flush;
    flush_unissued = kill_issue;
    issue_data = data_t'(issued + 1);
    #1;
    cycles++;
    check_state();
    count = expected_fifo.size();
    accepted = acc_valid_d;

    assert (!(full && acc_valid_q))
      else $fatal(1, "depth=%0d cycle=%0d push while full", DEPTH, cycles);
    assert (!(empty && pop))
      else $fatal(1, "depth=%0d cycle=%0d pop while empty", DEPTH, cycles);
    if (full) begin
      full_cycles++;
      assert (!accepted) else $fatal(1, "new rule issued at full");
      assert (old_ready === (DEPTH == 4))
        else $fatal(1, "unexpected full-state usage alias depth=%0d", DEPTH);
    end
    if (count == DEPTH - 1 && !expected_pending) reserve_stalls++;
    if (full && pop) full_pops++;
    if (acc_valid_q && accepted) pipeline_cycles++;
    if (acc_valid_q && pop && count != 0 && !do_flush) both_cycles++;
    if (acc_valid_q && pop && count == 0 && !do_flush) bypass_cycles++;

    // Shadow only: never connect the legacy decision to the actual FIFO push.
    old_full_issue = want_issue && old_ready && full && !kill_issue;
    if (old_full_issue) begin
      if (old_full_issues == 0)
        $display("OLD_WOULD_ISSUE_FULL depth=%0d cycle=%0d usage=%0d new_ready=%b",
                 DEPTH, cycles, usage, acc_ready);
      old_full_issues++;
    end
    if (old_full_issue_q && full && !do_flush) begin
      if (old_full_pushes == 0)
        $display("OLD_WOULD_PUSH_FULL depth=%0d cycle=%0d (shadow only)", DEPTH, cycles);
      old_full_pushes++;
    end
    old_full_issue_q = old_full_issue;

    // Append before pop to model the real FALL_THROUGH=1 empty-queue bypass.
    if (expected_pending) expected_fifo.push_back(expected_pending_data);
    if (pop) begin
      assert (expected_fifo.size() != 0) else $fatal(1, "reference underflow");
      expected_head = expected_fifo[0];
      assert (data_out === expected_head)
        else $fatal(1, "depth=%0d cycle=%0d order got=%h expected=%h",
                    DEPTH, cycles, data_out, expected_head);
    end
    if (do_flush) begin
      flush_count++;
      if (expected_pending) flush_pending++;
      if (full) flush_full++;
      discarded += expected_fifo.size();
      expected_fifo.delete();
    end else if (pop) begin
      expected_head = expected_fifo.pop_front();
      popped++;
    end
    expected_pending = accepted;
    if (accepted) begin
      expected_pending_data = issue_data;
      issued++;
    end
    @(posedge clk_i);
    #1;
    check_state();
  endtask

  task automatic drain;
    repeat (DEPTH + 2) step(0, 1);
    assert (expected_fifo.size() == 0 && !expected_pending)
      else $fatal(1, "depth=%0d drain failed", DEPTH);
  endtask

  initial begin
    done_o = 0;
    repeat (3) @(negedge clk_i);
    rst_ni = 1;
    // Continuous issue, delayed consumer: the reserved pending push fills the FIFO.
    // Repetition traverses both non-power-of-two and power-of-two pointer wraps.
    repeat (3) begin
      repeat (DEPTH + 5) step(1, 0);
      assert (full) else $fatal(1, "depth=%0d failed to reach full", DEPTH);
      repeat (2 * DEPTH + 3) step(1, 1);
      drain();
    end
    // Empty fall-through followed by a sustained one-per-cycle consumer.
    repeat (12) step(1, 1);
    drain();
    // Flush a nonempty queue while an accepted issue is still pending.
    step(1, 0);
    step(1, 0);
    step(1, 1, 1, 1);
    step(0, 0);
    assert (empty && acc_ready) else $fatal(1, "pending-flush recovery failed");
    repeat (DEPTH + 3) step(1, 0);
    step(1, 1, 1, 1);
    step(0, 0);
    assert (empty && acc_ready) else $fatal(1, "full-flush recovery failed");
    // Issue cancellation alone must not erase the previous cycle's pending push.
    step(1, 0);
    step(1, 0, 0, 1);
    drain();
    // Explicit flush_ex-only timing: a simultaneous new issue survives in Q.
    // This documents the upstream flush contract, rather than inventing a Q clear.
    step(1, 0, 1, 0);
    assert (acc_valid_q && usage == 0)
      else $fatal(1, "flush_ex-only pipeline timing changed");
    drain();
    // Deterministic mixed traffic and repeated paired-flush recovery.
    for (int i = 0; i < 128; i++)
      step((i % 7) != 0, (i % 11) >= 5, i % 31 == 30, i % 31 == 30);
    drain();

    assert (full_cycles > 0 && both_cycles > 0 && bypass_cycles > 0 &&
            pipeline_cycles > 0 && reserve_stalls > 0 && full_pops > 0 &&
            flush_pending > 0 && flush_full > 0 && popped > 2 * DEPTH)
      else $fatal(1, "depth=%0d missing directed coverage", DEPTH);
    assert ((DEPTH == 4 && old_full_issues > 0 && old_full_pushes > 0) ||
            (DEPTH == 3 && old_full_issues == 0 && old_full_pushes == 0))
      else $fatal(1, "depth=%0d legacy counterexample coverage failed", DEPTH);
    $display("PASS depth=%0d cycles=%0d issued=%0d popped=%0d discarded=%0d full=%0d both=%0d bypass=%0d pipeline=%0d reserve_stall=%0d full_pop=%0d flush=%0d flush_pending=%0d flush_full=%0d old_full_issue=%0d old_full_push=%0d",
             DEPTH, cycles, issued, popped, discarded, full_cycles, both_cycles,
             bypass_cycles, pipeline_cycles, reserve_stalls, full_pops, flush_count,
             flush_pending, flush_full, old_full_issues, old_full_pushes);
    done_o = 1;
  end
endmodule

module acc_queue_credit_tb;
  timeunit 1ns;
  timeprecision 1ps;
  logic clk = 0;
  wire [1:0] done;
  always #5 clk = ~clk;
  acc_queue_credit_check #(.DEPTH(3)) depth3 (.clk_i(clk), .done_o(done[0]));
  acc_queue_credit_check #(.DEPTH(4)) depth4 (.clk_i(clk), .done_o(done[1]));
  initial begin
    wait (&done);
    $display("PASS acc_queue_credit depths=3,4 actual_cva6_fifo_v3");
    $finish;
  end
  initial begin
    #100000;
    $fatal(1, "acc_queue_credit cycle watchdog");
  end
endmodule
