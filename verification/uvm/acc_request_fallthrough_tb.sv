// Buffer contract only: commit authorization is assumed upstream of valid_i.
// Instantiate the production module; upstream flush must never clear the buffer.
module acc_request_fallthrough_tb;
  timeunit 1ns;
  timeprecision 1ps;

  typedef struct packed {
    logic [31:0] insn;
    logic [63:0] rs1;
    logic [63:0] rs2;
    logic [2:0] frm;
    logic [7:0] trans_id;
  } request_t;

  bit clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic upstream_valid = 0, upstream_flush = 0, downstream_ready = 0;
  logic input_valid, input_ready, output_valid;
  request_t input_data = '0, output_data;
  assign input_valid = upstream_valid && !upstream_flush;

  fall_through_register_v1 #(.T(request_t), .DEPTH(2)) dut (
    .clk_i(clk), .rst_ni(rst_n), .clr_i(1'b0), .testmode_i(1'b0),
    .valid_i(input_valid), .ready_o(input_ready), .data_i(input_data),
    .valid_o(output_valid), .ready_i(downstream_ready), .data_o(output_data)
  );

  request_t expected[$];
  request_t held_output, held_input;
  bit output_stalled = 0, input_stalled = 0, last_accepted = 0;
  int unsigned cases = 0, cycles = 0, checks = 0, accepted = 0, emitted = 0;
  int unsigned bypass = 0, captured = 0, simultaneous = 0, full_cycles = 0;
  int unsigned full_recovery = 0, stable_cycles = 0, max_occupancy = 0;
  int unsigned flush_empty = 0, flush_one = 0, flush_two = 0, flush_emitted = 0;
  string case_name;

  function automatic request_t payload(input int unsigned id);
    request_t value;
    value.insn = 32'ha531_0000 ^ (id * 32'h0101_0101);
    value.rs1 = {id ^ 32'hdead_beef, ~id};
    value.rs2 = {id * 32'h9e37_79b9, id ^ 32'h0123_4567};
    value.frm = 3'(id);
    value.trans_id = 8'(id ^ (id >> 8));
    return value;
  endfunction

  task automatic check(input logic condition, input string message);
    checks++;
    if (condition !== 1'b1)
      $fatal(1, "FAIL case=%0d (%s) cycle=%0d: %s", cases, case_name, cycles, message);
  endtask

  task automatic start_case(input string name);
    cases++;
    case_name = name;
    check(expected.size() == 0, "case starts with outstanding requests");
    $display("CASE %0d %s", cases, name);
  endtask

  task automatic step(input bit want_valid, input bit want_ready,
                      input int unsigned id = 0, input bit do_flush = 0);
    int count;
    bit push, pop;
    request_t head, discarded;
    @(negedge clk);
    upstream_valid = want_valid;
    upstream_flush = do_flush;
    downstream_ready = want_ready;
    input_data = payload(id);
    #1;
    cycles++;
    count = expected.size();
    check(input_ready === (count < 2), "ready must depend only on stored occupancy");
    check(output_valid === ((count != 0) || (want_valid && !do_flush)),
          "wrong output valid / missing empty fall-through");
    if (output_valid) begin
      if (count != 0) head = expected[0];
      else head = payload(id);
      check(output_data === head,
            $sformatf("payload/order got=%h expected=%h", output_data, head));
    end
    if (output_stalled) begin
      check(output_valid && output_data === held_output,
            "stalled output changed, including across upstream flush");
      stable_cycles++;
    end
    if (input_stalled && !do_flush)
      check(input_valid && input_data === held_input, "TB producer violated input backpressure");

    push = input_valid && input_ready;
    pop = output_valid && downstream_ready;
    last_accepted = push;
    if (count == 0 && push && pop) bypass++;
    if (count == 0 && push && !pop) captured++;
    if (count != 0 && push && pop) simultaneous++;
    if (count == 2) full_cycles++;
    if (count == 2 && want_valid && !do_flush && pop) begin
      full_recovery++;
      check(!push, "full buffer must not accept a replacement on its drain cycle");
    end
    if (do_flush) begin
      case (count)
        0: flush_empty++;
        1: flush_one++;
        2: flush_two++;
      endcase
      if (pop) flush_emitted++;
      check(!push, "upstream flush must suppress new input handshakes");
    end
    output_stalled = output_valid && !downstream_ready;
    held_output = output_data;
    input_stalled = input_valid && !input_ready;
    held_input = input_data;

    @(posedge clk);
    // Enqueue before dequeue also models an empty-buffer same-cycle transfer.
    if (push) begin
      expected.push_back(input_data);
      accepted++;
    end
    if (pop) begin
      check(expected.size() != 0, "unexpected output handshake");
      discarded = expected.pop_front();
      check(output_data === discarded, "output handshake payload mismatch");
      emitted++;
    end
    #1;
    if (expected.size() > max_occupancy) max_occupancy = expected.size();
    check(expected.size() <= 2, "capacity exceeded");
    check(accepted == emitted + expected.size(), "request loss or duplication");
  endtask

  // Cancel only unaccepted source work; accepted requests must still drain.
  task automatic drain;
    step(0, 1, 32'hffff_0001, 1);
    step(0, 1, 32'hffff_0002, 1);
    step(0, 1, 32'hffff_0003, 1);
    check(expected.size() == 0 && !output_valid, "buffer failed to drain");
  endtask

  initial begin : test
    int unsigned id;
    bit pending, want, flush_now;
    logic [31:0] rng;
    repeat (3) @(posedge clk);
    @(negedge clk);
    rst_n = 1;
    #1;
    check(input_ready === 1'b1 && output_valid === 1'b0, "reset state");

    start_case("empty bypass and idle ready toggles");
    step(0, 0);
    step(0, 1);
    for (int i = 0; i < 8; i++) step(1, 1, i);
    step(0, 0);

    start_case("capture one then hold with changing invalid input data");
    step(1, 0, 10);
    for (int i = 0; i < 16; i++) step(0, 0, 100 + i);
    step(0, 1);
    step(0, 1);

    start_case("two-entry capacity full backpressure and retry after drain");
    step(1, 0, 20);
    step(1, 0, 21);
    check(expected.size() == 2, "second request was not retained");
    repeat (5) step(1, 0, 22);
    step(1, 1, 22);
    step(1, 1, 22);
    step(0, 1);
    step(0, 1);

    start_case("occupied simultaneous push/pop with pointer wrap");
    step(1, 0, 30);
    for (int i = 31; i < 47; i++) step(1, 1, i);
    step(0, 1);
    step(0, 1);

    start_case("capture survives upstream flush while stalled and while draining");
    step(1, 0, 50);
    for (int i = 0; i < 5; i++) step(1, 0, 500 + i, 1);
    step(1, 1, 599, 1);
    step(0, 1);

    start_case("full buffer survives upstream flush including blocked third request");
    step(1, 0, 60);
    step(1, 0, 61);
    step(1, 0, 62);
    for (int i = 0; i < 5; i++) step(1, 0, 600 + i, 1);
    step(1, 1, 699, 1);
    step(1, 1, 698, 1);
    step(0, 1);

    start_case("flush suppresses empty bypass and next request recovers");
    step(1, 0, 70, 1);
    step(1, 1, 71, 1);
    step(1, 1, 72);
    step(0, 1);

    for (int depth = 0; depth <= 2; depth++) begin
      for (int controls = 0; controls < 8; controls++) begin
        start_case($sformatf("matrix occupancy=%0d valid/ready/flush=%03b", depth, controls[2:0]));
        for (int i = 0; i < depth; i++) step(1, 0, 1000 + cases * 4 + i);
        step(controls[2], controls[1], 1000 + cases * 4 + 2, controls[0]);
        drain();
      end
    end

    start_case("deterministic mixed traffic with protocol-compliant producer");
    rng = 32'h1bad_f00d;
    pending = 0;
    id = 2000;
    for (int i = 0; i < 256; i++) begin
      rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
      want = pending || rng[0];
      flush_now = rng[7:4] == 4'ha;
      step(want, rng[2], id, flush_now);
      pending = want && !flush_now && !last_accepted;
      if (flush_now || last_accepted) id++;
    end
    drain();
    check(cases == 32, "missing directed case");
    check(max_occupancy == 2 && full_cycles > 0 && full_recovery > 0, "missing capacity coverage");
    check(bypass > 0 && captured > 0 && simultaneous > 0 && stable_cycles > 0,
          "missing handshake coverage");
    check(flush_empty > 0 && flush_one > 0 && flush_two > 0 && flush_emitted > 0,
          "missing nonflushable coverage");
    check(accepted == emitted, "final transfer count mismatch");
    $display("SUMMARY cases=%0d cycles=%0d checks=%0d accepted=%0d emitted=%0d max_occupancy=%0d",
             cases, cycles, checks, accepted, emitted, max_occupancy);
    $display("COVER bypass=%0d captured=%0d simultaneous=%0d full=%0d full_recovery=%0d stable=%0d flush_empty=%0d flush_one=%0d flush_two=%0d flush_emitted=%0d",
             bypass, captured, simultaneous, full_cycles, full_recovery, stable_cycles,
             flush_empty, flush_one, flush_two, flush_emitted);
    $display("PASS acc_request_fallthrough actual_module=fall_through_register_v1 depth=2 nonflushable=1");
    $finish;
  end

  initial begin
    #100000;
    $fatal(1, "FAIL watchdog timeout");
  end
endmodule
