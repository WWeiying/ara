`timescale 1ns/1ps
`include "axi/typedef.svh"

// Run from a scratch build directory (no generated files in the source tree):
// vcs -full64 -sverilog -assert svaext -top store_load_lookahead_tb \
//   +incdir+$ROOT/hardware/deps/axi/include \
//   $ROOT/hardware/deps/axi/src/axi_pkg.sv \
//   $ROOT/hardware/src/vlsu/store_load_lookahead.sv \
//   $ROOT/verification/uvm/store_load_lookahead_tb.sv -o simv
// ./simv
module store_load_lookahead_tb;
  typedef logic [63:0] addr_t;
  typedef logic [127:0] data_t;
  typedef logic [3:0] id_t;
  typedef logic [15:0] strb_t;
  typedef logic user_t;
  `AXI_TYPEDEF_ALL(axi, addr_t, id_t, data_t, strb_t, user_t)

  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, prepare = 0, invalidate = 0;
  logic allow_disjoint_writes = 0;
  axi_ar_chan_t prepare_ar;
  axi_req_t cpu_req, bus_req;
  axi_resp_t cpu_resp, bus_resp;
  logic inflight, prepare_fire, hit;

  store_load_lookahead #(
    .Bytes(128), .DataWidth(128), .ar_t(axi_ar_chan_t),
    .r_t(axi_r_chan_t), .req_t(axi_req_t), .resp_t(axi_resp_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .prepare_i(prepare),
    .prepare_ready_o(), .allow_disjoint_writes_i(allow_disjoint_writes),
    .prepare_ar_i(prepare_ar), .invalidate_i(invalidate),
    .req_i(cpu_req), .resp_o(cpu_resp), .req_o(bus_req),
    .resp_i(bus_resp), .inflight_o(inflight),
    .prepare_fire_o(prepare_fire), .hit_o(hit)
  );

  axi_ar_chan_t expected_ar[$];
  axi_r_chan_t expected_r[$];
  axi_ar_chan_t held_ar;
  axi_r_chan_t held_r;
  bit ar_stalled = 0, r_stalled = 0;
  int remaining[16];
  int pf_remaining = 0;
  int cycles = 0, cases = 0;
  int pf_ar_count = 0, normal_ar_count = 0, cpu_ar_count = 0;
  int pf_r_count = 0, normal_r_count = 0, replay_r_count = 0;
  int hit_count = 0, replay_remaining = 0;
  int wanted_pf_ar = 0, wanted_normal_ar = 0, wanted_cpu_ar = 0;
  int wanted_pf_r = 0, wanted_normal_r = 0, wanted_replay_r = 0;
  int wanted_hits = 0;
  string scenario = "initialization";

  task automatic check(input logic ok, input string message);
    if (ok !== 1'b1)
      $fatal(1, "[%0t] case=%s cycle=%0d: %s", $time, scenario, cycles, message);
  endtask

  function automatic axi_ar_chan_t request(input addr_t addr, input id_t id = 0);
    axi_ar_chan_t ar;
    ar = '0;
    ar.addr = addr;
    ar.id = id;
    ar.len = 7;
    ar.size = 4;
    ar.burst = axi_pkg::BURST_INCR;
    ar.cache = 4'b0011;
    ar.prot = 3'b010;
    ar.qos = 4'h5;
    ar.region = 4'ha;
    ar.user = 1;
    return ar;
  endfunction

  function automatic data_t payload(input int tag, input int beat);
    return {32'hc0010000 ^ tag, 32'ha55a0000 ^ beat,
            32'h13570000 ^ (tag << 8) ^ beat, 32'hfedc0000 ^ (beat << 8) ^ tag};
  endfunction

  // All stimulus changes occur after a sampling edge. Monitors sample before NBA;
  // step returns after NBA, so both handshake counters and DUT state have settled.
  task automatic step;
    @(posedge clk);
    #1;
  endtask

  always @(posedge clk) begin : scoreboard
    axi_ar_chan_t ar;
    axi_r_chan_t r;
    if (!rst_n) begin
      ar_stalled = 0;
      r_stalled = 0;
    end else begin
      cycles++;
      check(cycles < 3000, "cycle watchdog expired");
      if (ar_stalled)
        check(bus_req.ar_valid === 1'b1 && bus_req.ar === held_ar,
              "external AR was withdrawn or changed while stalled");
      if (r_stalled)
        check(cpu_resp.r_valid === 1'b1 && cpu_resp.r === held_r,
              "architectural R changed while backpressured");
      ar_stalled = bus_req.ar_valid && !bus_resp.ar_ready;
      held_ar = bus_req.ar;
      r_stalled = cpu_resp.r_valid && !cpu_req.r_ready;
      held_r = cpu_resp.r;

      check(bus_req.aw === cpu_req.aw && bus_req.aw_valid === cpu_req.aw_valid &&
            bus_req.w === cpu_req.w && bus_req.w_valid === cpu_req.w_valid &&
            bus_req.b_ready === cpu_req.b_ready &&
            cpu_resp.aw_ready === bus_resp.aw_ready &&
            cpu_resp.w_ready === bus_resp.w_ready &&
            cpu_resp.b === bus_resp.b && cpu_resp.b_valid === bus_resp.b_valid,
            "write channel pass-through changed");
      check(prepare_fire === (bus_req.ar_valid && bus_resp.ar_ready &&
                             bus_req.ar.id == 4'hf), "prepare_fire semantics");

      if (bus_req.ar_valid && bus_resp.ar_ready) begin
        check(expected_ar.size() != 0, "unexpected external AR handshake");
        ar = expected_ar.pop_front();
        check(bus_req.ar === ar, $sformatf("external AR mismatch expected=%h got=%h",
                                          ar, bus_req.ar));
        if (ar.id == 4'hf) begin
          check(pf_remaining == 0, "overlapping private bursts");
          pf_remaining = 8;
          pf_ar_count++;
        end else begin
          check(remaining[ar.id] == 0, "test driver reused an outstanding ID");
          remaining[ar.id] = int'(ar.len) + 1;
          normal_ar_count++;
        end
      end
      if (hit) begin
        check(cpu_req.ar_valid && cpu_resp.ar_ready && !bus_req.ar_valid,
              "hit must accept CPU AR without external AR");
        check(replay_remaining == 0, "overlapping replay");
        replay_remaining = 8;
        hit_count++;
      end
      if (cpu_req.ar_valid && cpu_resp.ar_ready) cpu_ar_count++;
      if (bus_resp.r_valid && bus_resp.r.id == 4'hf) begin
        check(bus_req.r_ready === 1'b1 && cpu_resp.r_valid === 1'b0,
              "private R not drained or leaked to CPU");
        check(pf_remaining > 0, "private R without a private AR");
        check(bus_resp.r.last === (pf_remaining == 1), "private RLAST mismatch");
        pf_remaining--;
        pf_r_count++;
      end
      if (cpu_resp.r_valid) begin
        check(expected_r.size() != 0, "unexpected architectural RVALID");
        r = expected_r[0];
        check(cpu_resp.r === r, $sformatf("R mismatch expected=%h got=%h", r, cpu_resp.r));
        if (cpu_req.r_ready) begin
          r = expected_r.pop_front();
          if (replay_remaining != 0) begin
            check(!bus_req.r_ready, "replay must not consume external R");
            check(r.last === (replay_remaining == 1), "replay RLAST mismatch");
            replay_remaining--;
            replay_r_count++;
          end else begin
            check(bus_resp.r_valid && bus_req.r_ready && cpu_resp.r === bus_resp.r,
                  "ordinary R routing mismatch");
            check(remaining[r.id] > 0, "ordinary R without an outstanding AR");
            check(r.last === (remaining[r.id] == 1), "ordinary RLAST mismatch");
            remaining[r.id]--;
            normal_r_count++;
          end
        end
      end
    end
  end

  task automatic counts;
    check(expected_ar.size() == 0 && expected_r.size() == 0, "scoreboard not empty");
    check(pf_remaining == 0 && replay_remaining == 0, "unfinished private/replay burst");
    for (int i = 0; i < 16; i++) check(remaining[i] == 0, "unfinished ordinary burst");
    check(pf_ar_count == wanted_pf_ar && normal_ar_count == wanted_normal_ar &&
          cpu_ar_count == wanted_cpu_ar && pf_r_count == wanted_pf_r &&
          normal_r_count == wanted_normal_r && replay_r_count == wanted_replay_r &&
          hit_count == wanted_hits, "handshake/hit counter mismatch");
  endtask

  task automatic begin_case(input string name);
    counts();
    scenario = name;
    cases++;
    $display("CASE %0d: %s", cases, scenario);
    rst_n = 0;
    prepare = 0;
    invalidate = 0;
    allow_disjoint_writes = 0;
    prepare_ar = '0;
    cpu_req = '0;
    bus_resp = '0;
    repeat (2) step();
    rst_n = 1;
    step();
    check(!inflight && !hit, "reset did not empty buffer");
  endtask

  task automatic arm(input axi_ar_chan_t ar);
    prepare_ar = ar;
    prepare = 1;
    step();
    prepare = 0;
    #1;
    check(inflight, "prepare did not enter inflight state");
  endtask

  task automatic expect_private_ar(input axi_ar_chan_t ar);
    ar.id = 4'hf;
    expected_ar.push_back(ar);
    wanted_pf_ar++;
  endtask

  task automatic launch(input axi_ar_chan_t ar);
    bus_resp.ar_ready = 1;
    arm(ar);
    expect_private_ar(ar);
    #1;
    check(prepare_fire && !cpu_resp.ar_ready, "private AR arbitration");
    step();
    check(inflight, "private AR did not enter fill");
  endtask

  task automatic private_beat(input int tag, input int beat,
                              input axi_pkg::resp_t status = axi_pkg::RESP_OKAY);
    cpu_req.r_ready = 0;
    bus_resp.r = '0;
    bus_resp.r.id = 4'hf;
    bus_resp.r.data = payload(tag, beat);
    bus_resp.r.resp = status;
    bus_resp.r.last = beat == 7;
    bus_resp.r_valid = 1;
    wanted_pf_r++;
    #1;
    check(inflight && bus_req.r_ready && !cpu_resp.r_valid, "private fill routing");
    step();
    bus_resp.r_valid = 0;
  endtask

  task automatic fill(input int tag, input int error_beat = -1,
                      input int invalidate_beat = -1, input int aw_beat = -1);
    for (int i = 0; i < 8; i++) begin
      invalidate = i == invalidate_beat;
      cpu_req.aw_valid = i == aw_beat;
      cpu_req.aw.addr = 64'h9000;
      bus_resp.aw_ready = 1;
      private_beat(tag, i, (i == error_beat) ? axi_pkg::RESP_SLVERR : axi_pkg::RESP_OKAY);
      invalidate = 0;
      cpu_req.aw_valid = 0;
      // Deterministic gaps exercise a fill with no incoming RVALID.
      if (i == 2 || i == 5) step();
    end
    #1;
    check(!inflight && !cpu_resp.r_valid, "fill did not finish silently");
  endtask

  task automatic fill_with_aw(input int tag, input axi_aw_chan_t aw);
    cpu_req.aw = aw;
    bus_resp.aw_ready = 1;
    for (int i = 0; i < 8; i++) begin
      cpu_req.aw_valid = i == 3;
      if (i == 3) begin
        #1;
        check(inflight && bus_req.aw_valid && bus_req.aw === aw && cpu_resp.aw_ready,
              "directed AW must be accepted during private fill");
      end
      private_beat(tag, i);
      cpu_req.aw_valid = 0;
    end
    #1;
    check(!inflight && !cpu_resp.r_valid, "AW-affected fill did not finish silently");
  endtask

  task automatic normal_ar(input axi_ar_chan_t ar);
    expected_ar.push_back(ar);
    wanted_normal_ar++;
    wanted_cpu_ar++;
    cpu_req.ar = ar;
    cpu_req.ar_valid = 1;
    bus_resp.ar_ready = 1;
    #1;
    check(!hit && bus_req.ar_valid && bus_req.ar === ar && cpu_resp.ar_ready,
          "request should fall back to ordinary AR");
    step();
    cpu_req.ar_valid = 0;
  endtask

  task automatic normal_beat(input axi_ar_chan_t ar, input int tag, input int beat,
                             input bit stall = 0);
    axi_r_chan_t r;
    r = '0;
    r.id = ar.id;
    r.data = payload(tag, beat);
    r.last = beat == int'(ar.len);
    r.user = beat[0];
    // An ordinary error must pass through, not be mistaken for a private error.
    r.resp = (ar.id == 4'h9 && beat == 1) ? axi_pkg::RESP_DECERR : axi_pkg::RESP_OKAY;
    expected_r.push_back(r);
    wanted_normal_r++;
    bus_resp.r = r;
    bus_resp.r_valid = 1;
    cpu_req.r_ready = !stall;
    #1;
    check(cpu_resp.r_valid && cpu_resp.r === r && bus_req.r_ready === cpu_req.r_ready,
          "ordinary read ID/data/ready was not passed through");
    if (stall) begin
      repeat (2) step();
      cpu_req.r_ready = 1;
    end
    step();
    bus_resp.r_valid = 0;
  endtask

  task automatic normal_response(input axi_ar_chan_t ar, input int tag);
    for (int i = 0; i <= int'(ar.len); i++) normal_beat(ar, tag, i, i % 2 == 0);
    #1;
  endtask

  task automatic fallback(input axi_ar_chan_t ar, input int tag);
    normal_ar(ar);
    normal_response(ar, tag);
    check(!inflight, "fallback left speculative work inflight");
  endtask

  task automatic replay(input axi_ar_chan_t ar, input int tag);
    axi_r_chan_t r;
    for (int i = 0; i < 8; i++) begin
      r = '0;
      r.id = ar.id;
      r.data = payload(tag, i);
      r.last = i == 7;
      r.resp = axi_pkg::RESP_OKAY;
      expected_r.push_back(r);
    end
    wanted_hits++;
    wanted_cpu_ar++;
    wanted_replay_r += 8;
    cpu_req.ar = ar;
    cpu_req.ar_valid = 1;
    cpu_req.r_ready = 0;
    // A hit must not depend on downstream ARREADY.
    bus_resp.ar_ready = 0;
    #1;
    check(hit && cpu_resp.ar_ready && !bus_req.ar_valid, "exact request failed to hit");
    step();
    cpu_req.ar_valid = 0;
    for (int i = 0; i < 8; i++) begin
      cpu_req.r_ready = 0;
      repeat (1 + i % 3) begin
        #1;
        check(inflight && cpu_resp.r_valid && !bus_req.r_ready && !bus_req.ar_valid,
              "replay not isolated from downstream bus");
        step();
      end
      cpu_req.r_ready = 1;
      step();
    end
    #1;
    check(!inflight && !cpu_resp.r_valid, "replay did not stop after eight beats");
  endtask

  initial begin : tests
    axi_ar_chan_t base, other, saved;
    axi_aw_chan_t write_ar;
    int before_count;
    foreach (remaining[i]) remaining[i] = 0;
    prepare_ar = '0;
    cpu_req = '0;
    bus_resp = '0;
    base = request(64'h0000_0001_8000_1000);

    begin_case("exact eight-beat hit, backpressure, single consumption");
    launch(base);
    fill(11);
    replay(base, 11);
    fallback(base, 12);

    for (int variant = 0; variant < 3; variant++) begin
      begin_case($sformatf("mismatch fallback variant %0d (addr/size/len)", variant));
      launch(base);
      fill(20 + variant);
      other = base;
      case (variant)
        0: other.addr += 128;
        1: other.size = 3;
        2: other.len = 3;
      endcase
      fallback(other, 30 + variant);
      fallback(base, 40 + variant);
    end

    begin_case("cancel in Send before any private AR sampling edge");
    bus_resp.ar_ready = 0;
    arm(base);
    invalidate = 1;
    #1;
    check(!bus_req.ar_valid && !prepare_fire, "unlocked cancellation issued private AR");
    step();
    invalidate = 0;
    check(!inflight, "unlocked cancellation failed");
    fallback(base, 51);

    begin_case("stalled private AR survives flush, then drains without replay");
    bus_resp.ar_ready = 0;
    arm(base);
    expect_private_ar(base);
    saved = base;
    saved.id = 4'hf;
    step(); // Private AR is now locked by an observed stall.
    invalidate = 1;
    repeat (3) begin
      #1;
      check(bus_req.ar_valid && bus_req.ar === saved && inflight,
            "flush changed a locked private AR");
      step();
    end
    invalidate = 0;
    prepare_ar = request(64'h7770);
    step();
    bus_resp.ar_ready = 1;
    step();
    fill(60);
    fallback(base, 61);

    for (int variant = 0; variant < 2; variant++) begin
      begin_case($sformatf("private R error discarded (%s)", variant ? "last" : "middle"));
      launch(base);
      fill(70 + variant, variant ? 7 : 3);
      fallback(base, 72 + variant);
    end

    for (int variant = 0; variant < 2; variant++) begin
      begin_case($sformatf("invalidation during fill (%s)", variant ? "last" : "middle"));
      launch(base);
      fill(80 + variant, -1, variant ? 7 : 2);
      fallback(base, 82 + variant);
    end

    begin_case("AW invalidation during fill");
    launch(base);
    fill(90, -1, -1, 4);
    fallback(base, 91);

    begin_case("AWVALID invalidates Ready even without AWREADY");
    launch(base);
    fill(92);
    cpu_req.aw = '0;
    cpu_req.aw.addr = base.addr;
    cpu_req.aw_valid = 1;
    bus_resp.aw_ready = 0;
    fallback(base, 93);
    bus_resp.aw_ready = 1;
    step();
    cpu_req.aw_valid = 0;

    begin_case("ordinary outstanding read prevents exact replay");
    other = request(64'h8000_2000, 4'h3);
    normal_ar(other);
    launch(base);
    fill(100);
    normal_ar(base);
    normal_response(base, 101);
    normal_response(other, 102);

    begin_case("late private completion cannot withdraw held ordinary AR");
    launch(base);
    for (int i = 0; i < 7; i++) private_beat(110, i);
    cpu_req.ar = base;
    cpu_req.ar_valid = 1;
    bus_resp.ar_ready = 0;
    expected_ar.push_back(base);
    wanted_normal_ar++;
    wanted_cpu_ar++;
    before_count = normal_ar_count;
    step(); // Ordinary exact AR is observed stalled while Fill is active.
    private_beat(110, 7);
    repeat (3) begin
      #1;
      check(!hit && !cpu_resp.ar_ready && bus_req.ar_valid && bus_req.ar === base,
            "late completion withdrew/changed already-held ordinary AR");
      step();
    end
    check(normal_ar_count == before_count, "stalled ordinary AR counted as accepted");
    bus_resp.ar_ready = 1;
    #1;
    check(!hit && bus_req.ar_valid && bus_req.ar === base, "held AR converted into hit");
    step();
    cpu_req.ar_valid = 0;
    normal_response(base, 111);

    begin_case("interleaved private and ordinary read ID routing");
    other = request(64'h8000_3000, 4'h9);
    normal_ar(other);
    launch(base);
    for (int i = 0; i < 8; i++) begin
      private_beat(120, i);
      normal_beat(other, 121, i, 1);
    end
    replay(base, 120);

    begin_case("matching address with nonzero read ID cannot replay");
    launch(base);
    fill(130);
    other = base;
    other.id = 4'h6;
    fallback(other, 131);

    begin_case("allowed disjoint INCR AW during Fill retains exact replay");
    allow_disjoint_writes = 1;
    launch(base);
    write_ar = '0;
    // Alignment makes the exclusive end exactly base.addr, not base.addr + 7.
    write_ar.addr = base.addr - 128 + 7;
    write_ar.len = 7;
    write_ar.size = 4;
    write_ar.burst = axi_pkg::BURST_INCR;
    fill_with_aw(140, write_ar);
    replay(base, 140);

    begin_case("overlapping INCR AW invalidates Fill even with allow enabled");
    allow_disjoint_writes = 1;
    launch(base);
    // One extra beat reaches [base.addr, base.addr + 16).
    write_ar.len = 8;
    fill_with_aw(150, write_ar);
    fallback(base, 151);

    begin_case("disjoint WRAP AW conservatively invalidates Fill");
    allow_disjoint_writes = 1;
    launch(base);
    write_ar.addr = base.addr + 128;
    write_ar.len = 7;
    write_ar.burst = axi_pkg::BURST_WRAP;
    fill_with_aw(160, write_ar);
    fallback(base, 161);

    repeat (3) step();
    counts();
    check(cases == 19, "directed case count mismatch");
    check(!inflight && !cpu_resp.r_valid && !bus_req.ar_valid, "not quiescent at finish");
    $display("PASS cases=%0d cycles=%0d pf_ar=%0d normal_ar=%0d cpu_ar=%0d hits=%0d pf_r=%0d normal_r=%0d replay_r=%0d",
             cases, cycles, pf_ar_count, normal_ar_count, cpu_ar_count, hit_count,
             pf_r_count, normal_r_count, replay_r_count);
    $finish;
  end

  initial begin
    #50000;
    $fatal(1, "wall-time watchdog expired in case %s", scenario);
  end
endmodule
