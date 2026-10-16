`include "axi/typedef.svh"
module tb;
  timeunit 1ns; timeprecision 1ps;
`ifdef TEST_STATIC_IDS
  localparam bit StaticIds = 1;
`ifdef TEST_LOADER_SINGLE_ID
  localparam logic [7:0] TestId = 0;
`else
  localparam logic [7:0] TestId = 8'h7f;
`endif
`else
  localparam bit StaticIds = 0;
  localparam logic [7:0] TestId = 8'hb5;
`endif
  logic [7:0] active_id = TestId;
  `AXI_TYPEDEF_ALL(bus, logic[47:0], logic[7:0], logic[511:0], logic[63:0], logic[0:0])
  logic clk = 0, rst_n = 0, lock = 0, allow_b = 1, allow_r = 1, stop_clk = 0;
  always #5 if (!stop_clk) clk = ~clk;
  bus_req_t [1:0] req = '0;
  bus_resp_t [1:0] rsp;
  bus_req_t mem_req;
  bus_resp_t mem_rsp;
  logic [255:0] status;
  logic [511:0] memory [longint unsigned];
  logic writing = 0, reading = 0, bvalid = 0;
  logic [47:0] wa, ra;
  logic [7:0] wid, rid, wl, rl;
  int cycles = 0, writes = 0, reads = 0, checks = 0;
`ifdef TEST_LOADER_SINGLE_ID
  localparam bit SingleId = 1;
  bus_req_t ref_mem_req;
  bus_resp_t [1:0] ref_rsp;
  logic [255:0] ref_status;
  int equivalent_cycles = 0;
  ara_eth_shared_ddr #(.StaticIdPartition(StaticIds), .req_t(bus_req_t), .rsp_t(bus_resp_t)) reference (
    .clk_i(clk), .rst_ni(rst_n), .lock_i(lock),
    .ara_req_i(req[0]), .ara_rsp_o(ref_rsp[0]),
    .loader_req_i(req[1]), .loader_rsp_o(ref_rsp[1]),
    .mem_req_o(ref_mem_req), .mem_rsp_i(mem_rsp), .status_o(ref_status)
  );
  always @(negedge clk) begin
    #1;
    if (rst_n) begin
      assert ({rsp, mem_req, status} === {ref_rsp, ref_mem_req, ref_status})
        else $fatal(1, "Single-ID specialization differs cycle=%0d", equivalent_cycles);
      equivalent_cycles++;
    end
  end
`else
  localparam bit SingleId = 0;
`endif
  ara_eth_shared_ddr #(.StaticIdPartition(StaticIds), .LoaderSingleId(SingleId), .req_t(bus_req_t), .rsp_t(bus_resp_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .lock_i(lock),
    .ara_req_i(req[0]), .ara_rsp_o(rsp[0]),
    .loader_req_i(req[1]), .loader_rsp_o(rsp[1]),
    .mem_req_o(mem_req), .mem_rsp_i(mem_rsp), .status_o(status)
  );
  always_comb begin
    mem_rsp = '0;
    mem_rsp.aw_ready = !writing && !bvalid && cycles % 3 != 0;
    mem_rsp.w_ready = writing && cycles % 4 != 0;
    mem_rsp.ar_ready = !reading && cycles % 5 != 0;
    mem_rsp.b_valid = bvalid && allow_b;
    mem_rsp.b.id = wid;
    mem_rsp.r_valid = reading && allow_r;
    mem_rsp.r.id = rid;
    mem_rsp.r.last = rl == 0;
    mem_rsp.r.data = memory.exists(longint'(ra >> 6)) ? memory[longint'(ra >> 6)] : '0;
  end
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      writing <= 0; reading <= 0; bvalid <= 0;
      wa <= 0; ra <= 0; wid <= 0; rid <= 0; wl <= 0; rl <= 0;
      cycles <= 0; writes <= 0; reads <= 0;
    end else begin
      cycles <= cycles + 1;
      if (mem_req.aw_valid && mem_rsp.aw_ready) begin
        if (mem_req.aw.addr < 48'h80000000 || mem_req.aw.addr >= 48'h100000000)
          $fatal(1, "Invalid write reached memory");
        writing <= 1; wa <= mem_req.aw.addr; wid <= mem_req.aw.id; wl <= mem_req.aw.len;
        writes <= writes + 1;
      end
      if (mem_req.w_valid && mem_rsp.w_ready) begin
        if (!memory.exists(longint'(wa >> 6))) memory[longint'(wa >> 6)] = '0;
        for (int i = 0; i < 64; i++)
          if (mem_req.w.strb[i]) memory[longint'(wa >> 6)][8*i+:8] = mem_req.w.data[8*i+:8];
        if (mem_req.w.last !== (wl == 0)) $fatal(1, "Write burst ownership lost");
        wa <= wa + 64; wl <= wl - 1;
        if (mem_req.w.last) begin writing <= 0; bvalid <= 1; end
      end
      if (mem_rsp.b_valid && mem_req.b_ready) bvalid <= 0;
      if (mem_req.ar_valid && mem_rsp.ar_ready) begin
        if (mem_req.ar.addr < 48'h80000000 || mem_req.ar.addr >= 48'h100000000)
          $fatal(1, "Invalid read reached memory");
        reading <= 1; ra <= mem_req.ar.addr; rid <= mem_req.ar.id; rl <= mem_req.ar.len;
        reads <= reads + 1;
      end
      if (mem_rsp.r_valid && mem_req.r_ready) begin
        ra <= ra + 64; rl <= rl - 1;
        if (rl == 0) reading <= 0;
      end
    end
  end
  task automatic aw(int p, logic[47:0] addr, int beats);
    @(negedge clk);
    req[p].aw = '0; req[p].aw.id = SingleId && p == 1 ? 0 : active_id; req[p].aw.addr = addr;
    req[p].aw.len = 8'(beats - 1); req[p].aw.size = 6; req[p].aw.burst = axi_pkg::BURST_INCR;
    req[p].aw_valid = 1;
    do @(posedge clk); while (!rsp[p].aw_ready);
    @(negedge clk); req[p].aw_valid = 0;
  endtask
  task automatic w(int p, logic[511:0] value, int beats, logic[63:0] strb = '1);
    for (int i = 0; i < beats; i++) begin
      @(negedge clk);
      req[p].w.data = value + 512'(i); req[p].w.strb = strb;
      req[p].w.last = i == beats-1; req[p].w_valid = 1;
      do @(posedge clk); while (!rsp[p].w_ready);
      @(negedge clk); req[p].w_valid = 0;
    end
  endtask
  task automatic b(int p, axi_pkg::resp_t response = axi_pkg::RESP_OKAY);
    repeat (4) @(negedge clk); req[p].b_ready = 1;
    do @(posedge clk); while (!rsp[p].b_valid);
    if (rsp[p].b.id !== (SingleId && p == 1 ? 8'd0 : active_id) || rsp[p].b.resp !== response) $fatal(1, "B id/response port %0d", p);
    checks++;
    @(negedge clk); req[p].b_ready = 0;
  endtask
  task automatic ar(int p, logic[47:0] addr, int beats);
    @(negedge clk);
    req[p].ar = '0; req[p].ar.id = SingleId && p == 1 ? 0 : active_id; req[p].ar.addr = addr;
    req[p].ar.len = 8'(beats - 1); req[p].ar.size = 6; req[p].ar.burst = axi_pkg::BURST_INCR;
    req[p].ar_valid = 1;
    do @(posedge clk); while (!rsp[p].ar_ready);
    @(negedge clk); req[p].ar_valid = 0;
  endtask
  task automatic r(int p, logic[511:0] value, int beats, axi_pkg::resp_t response = axi_pkg::RESP_OKAY);
    for (int i = 0; i < beats; i++) begin
      repeat (3) @(negedge clk); req[p].r_ready = 1;
      do @(posedge clk); while (!rsp[p].r_valid);
      if (rsp[p].r.id !== (SingleId && p == 1 ? 8'd0 : active_id) || rsp[p].r.resp !== response || rsp[p].r.last !== (i == beats-1))
        $fatal(1, "R identity/length port %0d", p);
      if (response == axi_pkg::RESP_OKAY && rsp[p].r.data !== value + 512'(i))
        $fatal(1, "R data port %0d got=%h expected=%h", p, rsp[p].r.data, value + 512'(i));
      checks++;
      @(negedge clk); req[p].r_ready = 0;
    end
  endtask
  task automatic write_read(int p, logic[47:0] addr, logic[511:0] value, int beats);
    fork aw(p, addr, beats); w(p, value, beats); b(p); join
    fork ar(p, addr, beats); r(p, value, beats); join
  endtask
  initial begin
    int old_reads, old_writes;
    repeat (4) @(negedge clk); rst_n = 1;
    // Exercise every ID in each partition, including collisions between sources.
    if (StaticIds) begin
      for (int id = 0; id < 128; id++) begin
        active_id = 8'(id);
        fork
          write_read(0, 48'h80008000, 512'(id), 1);
          write_read(1, 48'h80009000, 512'(id + 128), 1);
        join
      end
      active_id = TestId;
    end
    // Same IDs from both masters must remain distinct through the shared bridge.
    fork
      write_read(0, 48'h80000000, 512'h1234, 8);
      write_read(1, 48'h80001000, 512'habcd, 8);
    join
    write_read(1, 48'hffffffc0, '1, 1);
    write_read(1, 48'h80002000, '1, 1);
    fork aw(1, 48'h80002000, 1); w(1, '0, 1, 64'hff); b(1); join
    fork ar(1, 48'h80002000, 1); r(1, {448'hffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff, 64'b0}, 1); join
    old_reads = reads; old_writes = writes;
    for (int i = 0; i < 4; i++) begin
      logic[47:0] address;
      case (i)
        0: address = 48'h7fffffc0;
        1: address = 48'h100000000;
        2: address = 48'h80000fc0; // Two beats cross 4 KiB.
        3: address = 48'hffffffc0; // Two beats escape the DDR aperture.
      endcase
      fork aw(1, address, 2); w(1, '1, 2); b(1, axi_pkg::RESP_DECERR); join
      fork ar(1, address, 2); r(1, '0, 2, axi_pkg::RESP_DECERR); join
    end
    if (reads != old_reads || writes != old_writes || !status[34] || status[223:192] != 12)
      $fatal(1, "Firewall/counter mismatch");
    // Same ID changes target from DDR to error slave while its response stalls.
    // A reduced lookup must not let the error overtake the DDR completion.
    @(negedge clk); allow_r = 0;
    ar(1, 48'h80000000, 1);
    fork
      ar(1, 48'h7fffffc0, 1);
      begin
        repeat (10) @(negedge clk);
        // The AW/AR spill registers may accept the address; it must not
        // reach the error slave until the same-ID DDR response drains.
        if (dut.decoded_req[1].ar_valid || rsp[1].r_valid)
          $fatal(1, "Error read overtook outstanding DDR read");
        allow_r = 1;
        r(1, 512'h1234, 1);
        r(1, '0, 1, axi_pkg::RESP_DECERR);
      end
    join
    @(negedge clk); allow_b = 0;
    fork aw(1, 48'h80002200, 1); w(1, 512'h8899, 1); join
    fork
      begin aw(1, 48'h7fffffc0, 1); w(1, '0, 1); end
      begin
        repeat (10) @(negedge clk);
        if (dut.decoded_req[1].aw_valid || rsp[1].b_valid)
          $fatal(1, "Error write overtook outstanding DDR write");
        allow_b = 1;
        b(1);
        b(1, axi_pkg::RESP_DECERR);
      end
    join
    // Accepted W and R must drain before isolated; blocking B/R discriminates an early ACK.
    @(negedge clk); allow_b = 0; allow_r = 0;
    fork aw(1, 48'h80003000, 8); ar(1, 48'h80000000, 8); join
    @(negedge clk); lock = 1;
    w(1, 512'h4567, 8);
    repeat (20) @(negedge clk);
    if (status[33]) $fatal(1, "Isolation completed before B/R drained");
    allow_b = 1; allow_r = 1;
    fork b(1); r(1, 512'h1234, 8); join
    wait (status[33]); @(negedge clk); lock = 0;
    repeat (5) @(negedge clk);
    if (!status[32] || !status[33] || status[95:64] != status[127:96] || status[159:128] != status[191:160])
      $fatal(1, "Sticky lock/counters mismatch");
    old_reads = reads; old_writes = writes;
    req[1].aw_valid = 1; req[1].ar_valid = 1;
    repeat (20) begin
      @(posedge clk);
      if (rsp[1].aw_ready || rsp[1].ar_ready) $fatal(1, "Locked loader accepted traffic");
    end
    @(negedge clk); req[1].aw_valid = 0; req[1].ar_valid = 0;
    if (reads != old_reads || writes != old_writes) $fatal(1, "Locked loader reached DDR");
    write_read(0, 48'h80004000, 512'h6789, 8);
    // A shared UI reset is the only way back to load mode, even with stopped clock.
    @(negedge clk); stop_clk = 1; rst_n = 0; req = '0;
    #1;
    if (status[32] || status[223:64] != 0) $fatal(1, "Lock/counters failed async reset");
    #20; stop_clk = 0;
    repeat (4) @(negedge clk); rst_n = 1;
    write_read(1, 48'h80005000, 512'h89ab, 8);
    // Reset both endpoint and bridge while an accepted write awaits its data.
    aw(1, 48'h80006000, 8);
    @(negedge clk); rst_n = 0; req = '0;
    repeat (4) @(negedge clk); rst_n = 1;
    write_read(1, 48'h80007000, 512'hcdef, 8);
`ifdef TEST_LOADER_SINGLE_ID
    assert (equivalent_cycles > 1000) else $fatal(1, "Insufficient cycle equivalence coverage");
    $display("Single-ID cycle equivalence checks=%0d", equivalent_cycles);
`endif
    $display("PASS: shared DDR IDs, strobes, bursts, firewall, isolation, shared reset, Ara after lock; checks=%0d", checks);
    $finish;
  end
  initial begin #100000; $fatal(1, "Shared DDR watchdog"); end
endmodule
