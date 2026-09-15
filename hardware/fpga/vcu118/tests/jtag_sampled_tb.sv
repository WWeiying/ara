// Protocol comparison against the pinned upstream TAP and clearable DMI CDC.
// This is digital verification; it does not simulate analog metastability.
module tb;
  timeunit 1ns; timeprecision 1ps;
  logic clk = 0;
  always #10 clk = ~clk;
  logic rst_n = 0, trst_n = 0, tck = 0, tms = 1, tdi = 0;
  wire [1:0] tdo, oe, dmi_rst_n, req_valid, req_ready, resp_valid, resp_ready;
  dm::dmi_req_t req[2];
  dm::dmi_resp_t resp[2];
  logic allow_req = 1, allow_resp = 1;
  int accepted[2] = '{0, 0};
  logic [31:0] memory[2][128];
  logic [31:0] readback[2];
  int checks = 0;
  logic [15:0] visited = 0;
  always @(negedge clk) if (rst_n && trst_n)
    visited[candidate.i_dmi_jtag_tap.tap_state_q] = 1'b1;
  int low_ns = 400, high_ns = 600;
  logic [63:0] scan_out[2];
  wire reset_done;
  reset_checker resets(reset_done);

  dmi_jtag #(.IdcodeValue(32'h12345001)) candidate (
    .clk_i(clk), .rst_ni(rst_n), .testmode_i(1'b0), .dmi_rst_no(dmi_rst_n[0]),
    .dmi_req_o(req[0]), .dmi_req_valid_o(req_valid[0]), .dmi_req_ready_i(req_ready[0]),
    .dmi_resp_i(resp[0]), .dmi_resp_ready_o(resp_ready[0]), .dmi_resp_valid_i(resp_valid[0]),
    .tck_i(tck), .tms_i(tms), .trst_ni(trst_n), .td_i(tdi), .td_o(tdo[0]), .tdo_oe_o(oe[0])
  );
  reference_dmi_jtag #(.IdcodeValue(32'h12345001)) reference_dut (
    .clk_i(clk), .rst_ni(rst_n), .testmode_i(1'b0), .dmi_rst_no(dmi_rst_n[1]),
    .dmi_req_o(req[1]), .dmi_req_valid_o(req_valid[1]), .dmi_req_ready_i(req_ready[1]),
    .dmi_resp_i(resp[1]), .dmi_resp_ready_o(resp_ready[1]), .dmi_resp_valid_i(resp_valid[1]),
    .tck_i(tck), .tms_i(tms), .trst_ni(trst_n), .td_i(tdi), .td_o(tdo[1]), .tdo_oe_o(oe[1])
  );
  // Like dm_csrs: accepting a DMI request queues its result on that edge,
  // while dmi_rst_n synchronously flushes the response queue, not the DM.
  for (genvar i = 0; i < 2; i++) begin : gen_dm
    logic pending = 0;
    dm::dmi_resp_t result;
    assign req_ready[i] = allow_req && !pending;
    assign resp_valid[i] = pending && allow_resp;
    assign resp[i] = result;
    always @(posedge clk) begin
      if (!rst_n) begin
        pending <= 0;
        result <= '0;
      end else if (!dmi_rst_n[i]) begin
        pending <= 0;
      end else begin
        if (pending && allow_resp && resp_ready[i]) pending <= 0;
        if (req_valid[i] && req_ready[i]) begin
          accepted[i]++;
          pending <= 1;
          result.resp <= req[i].addr == 7'h7e ? 2'b10 : 2'b00;
          result.data <= memory[i][req[i].addr];
          if (req[i].op == dm::DTM_WRITE) memory[i][req[i].addr] <= req[i].data;
          else if (req[i].op != dm::DTM_READ) $fatal(1, "Invalid core DMI operation");
        end
      end
    end
  end

  // One full TCK cycle. The debugger changes TMS/TDI at the falling edge
  // and samples TDO at the next rising edge, after the specified low phase.
  task automatic step(input logic mode, data, output logic [1:0] sampled);
    tck = 0; tms = mode; tdi = data;
    #(low_ns);
    sampled = tdo;
    if (rst_n && trst_n && $isunknown({tdo, oe})) $fatal(1, "Unknown JTAG outputs");
    tck = 1;
    #(high_ns);
  endtask
  task automatic tick(input logic mode = 0, data = 0);
    logic [1:0] ignored;
    step(mode, data, ignored);
  endtask
  task automatic idle(input int cycles = 64);
    repeat (cycles) tick();
  endtask
  task automatic tap_reset;
    repeat (6) tick(1);
    idle();
  endtask
  task automatic ir(input logic [4:0] value);
    tick(1); tick(1); tick(0); tick(0);
    for (int bitno = 0; bitno < 5; bitno++) begin
      tick(bitno == 4 || bitno == 2, value[bitno]);
      if (bitno == 2) begin tick(0); tick(0); tick(1); tick(0); end
    end
    tick(1); tick(0);
  endtask
  task automatic dr(input int width, input logic [63:0] value);
    logic [1:0] sampled;
    scan_out[0] = 0; scan_out[1] = 0;
    tick(1); tick(0); tick(0);
    for (int bitno = 0; bitno < width; bitno++) begin
      step(bitno == width-1 || (width > 16 && bitno == 11), value[bitno], sampled);
      for (int i = 0; i < 2; i++) scan_out[i][bitno] = sampled[i];
      if (width > 16 && bitno == 11) begin tick(0); tick(0); tick(1); tick(0); end
    end
    tick(1); tick(0);
  endtask
  task automatic expect_scan(input logic [63:0] value, mask);
    for (int i = 0; i < 2; i++)
      if ((scan_out[i] & mask) !== value)
        $fatal(1, "Scan mismatch dut=%0d got=%h expected=%h", i, scan_out[i] & mask, value);
    checks++;
  endtask
  task automatic dmi_access(input logic [6:0] address, input logic [31:0] value,
                            input logic [1:0] op);
    ir(5'h11); dr(41, {address, value, op}); idle();
  endtask
  task automatic check_csr(input logic [1:0] status);
    ir(5'h10); dr(32, 0);
    expect_scan(64'h1071 | (64'(status) << 10), 64'hffffffff);
  endtask
  task automatic soft_reset;
    ir(5'h10); dr(32, 32'h00010000); idle();
  endtask
  task automatic hard_reset;
    ir(5'h10); dr(32, 32'h00020000); idle();
  endtask
  task automatic core_ready(input logic value);
    @(negedge clk);
    #1; allow_req = value;
  endtask
  initial begin
    for (int i = 0; i < 2; i++)
      for (int addr = 0; addr < 128; addr++) memory[i][addr] = 32'h76543210 ^ addr;
    #37; rst_n = 1; trst_n = 1;
    #203; tap_reset();
    for (int phase = 0; phase < 20; phase++) begin
      // Sweep every relative SoC phase and both 40/60% TCK duty cycles.
      low_ns = (phase % 2) ? 600 : 400;
      high_ns = 1000 - low_ns;
      @(negedge clk); #(phase + 1);
      ir(5'h01); dr(32, 0); expect_scan(64'h12345001, 64'hffffffff);
      check_csr(0);
      dmi_access(7'(phase+1), 32'hb0a00000 + phase, 2'b10);
      dmi_access(7'(phase+1), 0, 2'b01);
      dr(41, 0);
      expect_scan((64'(phase+1) << 34) | ((64'hb0a00000 + phase) << 2), 64'h1ffffffffff);
    end
    // Unknown IR is a one-bit bypass register.
    ir(5'h1f); dr(8, 8'h55); expect_scan(64'haa, 64'hff);

    // A blocked request stays stable, a second request sets sticky BUSY.
    core_ready(0);
    dmi_access(7'h31, 32'hfeed0031, 2'b10);
    dmi_access(7'h32, 32'hfeed0032, 2'b10);
    check_csr(3);
    soft_reset(); // This clears status, not the outstanding first request.
    check_csr(0);
    core_ready(1);
    idle();
    if (memory[0][49] !== 32'hfeed0031 || memory[1][49] !== 32'hfeed0031 ||
        memory[0][50] !== (32'h76543210 ^ 50) || memory[1][50] !== (32'h76543210 ^ 50))
      $fatal(1, "Backpressure/soft reset lost or duplicated a request");

    // Hard reset cancels a request that has not handshaken.
    core_ready(0);
    dmi_access(7'h33, 32'hdead0033, 2'b10);
    hard_reset();
    core_ready(1); idle(); check_csr(0);
    if (memory[0][51] !== (32'h76543210 ^ 51) || memory[1][51] !== (32'h76543210 ^ 51))
      $fatal(1, "Hard-reset request leaked to DM");

    dmi_access(7'h7e, 0, 2'b01); check_csr(2); soft_reset(); check_csr(0);

    // A consumed write is not undone by DTM hard reset; its queued response
    // is flushed, and must never be mistaken for the next read response.
    @(negedge clk); #1; allow_resp = 0;
    dmi_access(7'h36, 32'hface0036, 2'b10);
    hard_reset();
    @(negedge clk); #1; allow_resp = 1;
    idle(); check_csr(0);
    dmi_access(7'h36, 0, 2'b01); dr(41, 0);
    expect_scan((64'h36 << 34) | (64'hface0036 << 2), 64'h1ffffffffff);

    // No TCK edges while core accepts and responds: the sampled TAP must
    // make progress on clk_i, and retain the result until the next scan.
    core_ready(0);
    dmi_access(7'h35, 0, 2'b01);
    tck = 0; #500;
    core_ready(1); #1000;
    if (candidate.state_q !== candidate.Idle || candidate.data_q !== (32'h76543210 ^ 53))
      $fatal(1, "DMI completion incorrectly depends on external TCK");
    idle(); dr(41, 0);
    expect_scan((64'h35 << 34) | ((64'h76543210 ^ 53) << 2), 64'h1ffffffffff);

    // Stop TCK in each polarity and reset the SoC. The FPGA TAP also resets
    // even though the board's external TRST is tied high.
    for (int polarity = 0; polarity < 2; polarity++) begin
      tck = 1'(polarity); #503; rst_n = 0; #97;
      if (tdo[0] !== 0 || oe[0] !== 0) $fatal(1, "SoC reset failed to reset TAP");
      rst_n = 1; #803;
      tap_reset(); check_csr(0);
      ir(1); dr(32, 0); expect_scan(64'h12345001, 64'hffffffff);
    end
    tck = 0; #503; trst_n = 0; #101;
    if (tdo !== 0 || oe !== 0) $fatal(1, "External TRST did not assert asynchronously");
    trst_n = 1; #803; tap_reset(); check_csr(0);
    if (visited !== 16'hffff) $fatal(1, "Not all 16 TAP states were checked: %h", visited);
    if (accepted[0] != 45 || accepted[1] != 45)
      $fatal(1, "Missing/duplicate DMI acceptance: %0d %0d", accepted[0], accepted[1]);
    if (!reset_done) $fatal(1, "Board reset checks did not complete");
    $display("PASS: sampled JTAG, %0d scan checks, %0d/%0d DMI acceptances, 20 phases, stopped TCK and resets", checks, accepted[0], accepted[1]);
    $finish;
  end
  initial begin
    #20000000;
    $fatal(1, "JTAG test watchdog");
  end
endmodule
