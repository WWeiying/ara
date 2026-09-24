`timescale 1ns/1ps
// Real reviewed RX/TX FIFOs, behavioral MAC stream and FDRE, no encrypted MAC/PCS.
module FDRE #(parameter INIT = 0)(input C, CE, D, R, output reg Q = INIT);
  always @(posedge C) if (R) Q <= 0; else if (CE) Q <= D;
endmodule

module ethernet_diag_tb;
  reg clk = 0, rx_clk = 0, reset = 1, enable = 0;
  always #4 clk = !clk;
  always #4.1 rx_clk = !rx_clk;
  reg [7:0] rx_data = 0;
  reg rx_valid = 0, rx_last = 0, rx_bad = 0;
  wire [7:0] fifo_data, tx_data, output_data;
  wire fifo_valid, fifo_last, fifo_ready, tx_valid, tx_last, tx_ready;
  wire output_valid, output_last, output_bad;
  reg output_ready = 0;
  wire seen, sent, rejected;
  reg [7:0] frame [0:8191];
  reg [7:0] expected [0:2047];
  integer expected_length = 0, observed = 0, frames = 0, cycle = 0;
  reg checking = 0, stalled = 0;
  reg [8:0] stalled_word;
  eth_j10_ten_100_1g_eth_fifo fifo (
    .rx_mac_aclk(rx_clk), .rx_mac_resetn(!reset), .rx_axis_mac_tdata(rx_data),
    .rx_axis_mac_tvalid(rx_valid), .rx_axis_mac_tlast(rx_last), .rx_axis_mac_tuser(rx_bad),
    .rx_fifo_aclk(clk), .rx_fifo_resetn(!reset), .rx_axis_fifo_tdata(fifo_data),
    .rx_axis_fifo_tvalid(fifo_valid), .rx_axis_fifo_tlast(fifo_last), .rx_axis_fifo_tready(fifo_ready),
    .tx_fifo_aclk(clk), .tx_fifo_resetn(!reset), .tx_axis_fifo_tdata(tx_data),
    .tx_axis_fifo_tvalid(tx_valid), .tx_axis_fifo_tlast(tx_last), .tx_axis_fifo_tready(tx_ready),
    .tx_mac_aclk(clk), .tx_mac_resetn(!reset), .tx_axis_mac_tdata(output_data),
    .tx_axis_mac_tvalid(output_valid), .tx_axis_mac_tlast(output_last),
    .tx_axis_mac_tuser(output_bad), .tx_axis_mac_tready(output_ready)
  );
  eth_diag_echo echo (
    .clk(clk), .reset(reset), .enable(enable), .s_data(fifo_data), .s_valid(fifo_valid),
    .s_last(fifo_last), .s_ready(fifo_ready), .m_data(tx_data), .m_valid(tx_valid),
    .m_last(tx_last), .m_ready(tx_ready), .seen_frame(seen), .sent_frame(sent), .rejected_frame(rejected)
  );
  always @(negedge clk) begin
    cycle = cycle + 1;
    output_ready = cycle % 7 >= 3;
  end
  always @(posedge clk) begin
    if (reset) stalled <= 0;
    else begin
      if (stalled && (!output_valid || {output_last, output_data} !== stalled_word))
        $fatal(1, "TX changed while stalled");
      stalled <= output_valid && !output_ready;
      stalled_word <= {output_last, output_data};
      if (output_valid && output_ready) begin
        if (!checking || observed >= expected_length) $fatal(1, "Unexpected transmitted byte");
        if (output_data !== expected[observed] || output_bad || output_last !== (observed == expected_length-1))
          $fatal(1, "Incorrect echo index=%0d got=%h expected=%h last=%b", observed, output_data, expected[observed], output_last);
        observed = observed + 1;
        if (output_last) frames = frames + 1;
      end
    end
  end
  task make_frame(input integer length);
    for (integer i = 0; i < length; i = i+1) frame[i] = (i ^ (i >> 8) ^ 8'ha5);
    {frame[0],frame[1],frame[2],frame[3],frame[4],frame[5]} = 48'h020000000118;
    {frame[6],frame[7],frame[8],frame[9],frame[10],frame[11]} = 48'h02123456789a;
    frame[12] = 8'h88; frame[13] = 8'hb5;
  endtask
  task send_frame(input integer length, input integer bad);
    for (integer i = 0; i < length; i = i+1) begin
      @(negedge rx_clk);
      rx_valid = 1; rx_data = frame[i]; rx_last = i == length-1; rx_bad = bad && rx_last;
    end
    @(negedge rx_clk);
    rx_valid = 0; rx_last = 0; rx_bad = 0;
  endtask
  task accepted(input integer length);
    make_frame(length);
    for (integer i = 0; i < length; i = i+1) expected[i] = frame[i < 6 ? i+6 : i < 12 ? i-6 : i];
    expected_length = length; observed = 0; checking = 1;
    send_frame(length, 0);
    wait (observed == length);
    repeat (80) @(posedge clk);
    checking = 0;
  endtask
  task rejected_case(input integer length, input integer bad);
    checking = 0;
    send_frame(length, bad);
    repeat (6000) @(posedge clk);
  endtask

  reg phy_request = 0;
  wire phy_reset_n, settled;
  eth_diag_reset #(.HOLD_CYCLES(5), .SETTLE_CYCLES(11)) phy_reset (
    .clk(clk), .reset(reset), .request(phy_request), .phy_reset_n(phy_reset_n), .settled(settled)
  );
  initial begin
    #200;
    @(negedge clk); reset = 0;
    for (integer i=1; i<=16; i=i+1) begin
      @(posedge clk); #1;
      if (phy_reset_n !== (i>=5) || settled !== (i==16)) $fatal(1, "PHY timer off by one: %0d", i);
    end
    @(negedge clk); phy_request = 1;
    #1;
    if (!phy_reset_n || !settled) $fatal(1, "PHY request changed outputs before clock edge");
    @(posedge clk); #1;
    if (phy_reset_n || settled) $fatal(1, "PHY reset request not applied");
    repeat (5) @(negedge clk);
    phy_request = 0;
    repeat (100) @(posedge clk);
    if (!settled) $fatal(1, "PHY reset did not release");
    @(negedge clk); reset = 1;
    #1; if (phy_reset_n || settled) $fatal(1, "Asynchronous reset did not assert");
    @(negedge clk); reset = 0;
    repeat (20) @(posedge clk);
    if (!settled) $fatal(1, "PHY reset did not recover");
    make_frame(60); rejected_case(60, 0); // disabled by default
    enable = 1;
    accepted(60); accepted(64); accepted(1514); accepted(60);
    make_frame(60); frame[0] = 8'hff; rejected_case(60, 0);
    make_frame(60); frame[6] = 8'h01; rejected_case(60, 0);
    make_frame(60); frame[13] = 8'h00; rejected_case(60, 0);
    make_frame(1515); rejected_case(1515, 0);
    make_frame(5000); rejected_case(5000, 0); // overflow the real 4K RX FIFO
    make_frame(40); rejected_case(40, 0);
    make_frame(64); rejected_case(64, 1); // real RX FIFO must discard MAC-marked bad frame
    accepted(64); // recovery after rejected/bad/oversize frames
    if (frames != 5 || !seen || !sent || !rejected) $fatal(1, "Missing coverage/status");
    fork
      accepted(64);
      begin wait (tx_valid); @(negedge clk); enable = 0; end
    join
    if (frames != 6) $fatal(1, "Disable truncated an accepted transmission");
    enable = 1;
    make_frame(64);
    checking = 0;
    fork
      send_frame(64, 0);
      begin repeat (20) @(negedge rx_clk); reset = 1; end
    join
    repeat (100) @(negedge clk);
    reset = 0;
    repeat (100) @(negedge clk);
    if (seen || sent || rejected) $fatal(1, "Reset left a ghost frame or sticky packet state");
    accepted(64);
    if (frames != 7) $fatal(1, "Did not recover from mid-frame reset");
    $display("PASS: PHY timer, reviewed dual-clock RX/TX FIFO, L2 filtering, 60/64/1514, stalls, bad/oversize/overflow recovery, disable, mid-frame reset");
    $finish;
  end
  initial begin #2000000; $fatal(1, "Bounded simulation timed out"); end
endmodule
