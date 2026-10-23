module akv_refill_order_guard_tb;
  timeunit 1ns; timeprecision 1ps;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic [3:0] live;
  logic alloc, eligible, pending, pending_eligible, waiting;
  logic [1:0] id, refill_id;
  logic admit, drained;
  int checks = 0;
  akv_refill_order_guard #(.NrSlots(4)) dut (
    .clk_i(clk), .rst_ni(rst_n), .live_i(live),
    .alloc_valid_i(alloc), .alloc_id_i(id), .alloc_eligible_i(eligible),
    .pending_valid_i(pending), .pending_eligible_i(pending_eligible),
    .refill_wait_i(waiting), .refill_id_i(refill_id),
    .admission_safe_o(admit), .older_drained_o(drained)
  );
  initial begin
    live = 0; alloc = 0; eligible = 0; pending = 0;
    pending_eligible = 0; waiting = 0; id = 0; refill_id = 0;
    repeat (2) @(negedge clk);
    rst_n = 1;
    for (int mask = 0; mask < 16; mask++) begin
      waiting = 0;
      for (int slot = 0; slot < 4; slot++) begin
        alloc = 1; id = 2'(slot); eligible = (mask >> slot) & 1;
        @(negedge clk);
      end
      alloc = 0;
      for (int membership = 0; membership < 16; membership++) begin
        live = 4'(membership);
        for (int p = 0; p < 4; p++) begin
          pending = p & 1; pending_eligible = (p >> 1) & 1;
          for (int current = 0; current < 4; current++) begin
            refill_id = 2'(current); waiting = 1;
            #1;
            assert (admit === (((membership & ~mask) == 0) &&
                              (!(p & 1) || (p & 2) != 0)))
              else $fatal(1, "Admission mismatch mask=%h live=%h pending=%d", mask, live, p);
            assert (drained === ((membership & ~(1 << current)) == 0))
              else $fatal(1, "Drain mismatch live=%h current=%d", live, current);
            checks++;
          end
        end
      end
      @(negedge clk);
    end
    // A terminal for the current refill does not retire an older arithmetic
    // VID. The consumer must keep its response held while that bit is live.
    waiting = 0; live = 0; pending = 0;
    alloc = 1; id = 0; eligible = 0;
    @(negedge clk);
    alloc = 0; waiting = 1; refill_id = 0; live = 4'b0011;
    #1;
    assert (!drained) else $fatal(1, "Released with older arithmetic live");
    checks++;
    @(negedge clk);
    live = 4'b0010;
    #1;
    assert (!drained) else $fatal(1, "Refill retirement hid older arithmetic");
    checks++;
    @(negedge clk);
    live = 0;
    #1;
    assert (drained) else $fatal(1, "Did not release after older retirement");
    checks++;
    live = 4'b0001;
    #1;
    assert (drained) else $fatal(1, "Self-deadlock on current refill VID");
    checks++;
    waiting = 0;
    #1;
    assert (!drained) else $fatal(1, "Drain authority outside refill WAIT");
    checks++;
    // Reusing an eligible VID for unsupported work must revoke admission.
    live = 0; alloc = 1; id = 1; eligible = 0;
    @(negedge clk);
    alloc = 0; live = 4'b0010;
    #1;
    assert (!admit) else $fatal(1, "Stale eligible classification survived reuse");
    checks++;
    live = 0; alloc = 1; eligible = 1;
    @(negedge clk);
    alloc = 0; live = 4'b0010;
    #1;
    assert (admit) else $fatal(1, "Safe VID reuse remained blocked");
    checks++;
    live = 0; pending = 1; pending_eligible = 0;
    #1;
    assert (!admit) else $fatal(1, "Ignored unallocated pending work");
    checks++;
    waiting = 0; live = '1; pending = 0; rst_n = 0;
    #1;
    assert (!admit && !drained) else $fatal(1, "Reset classification not cleared");
    $display("AKV_REFILL_GUARD_PASS checks=%0d", checks);
    $finish;
  end
endmodule
