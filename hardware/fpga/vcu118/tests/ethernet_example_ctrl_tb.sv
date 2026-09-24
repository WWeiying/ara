`timescale 1ns/1ps

// Characterize the unmodified generated example, not the protected MAC/PHY.
module ethernet_example_ctrl_tb;
  reg clk = 0;
  always #5 clk = ~clk;
  reg resetn = 0;
  reg start_config = 0;
  integer mode = 0;
  integer cycle = 0;
  integer aw_count = 0;
  integer w_count = 0;
  integer b_count = 0;
  integer dropped_aw = 0;
  integer mode0_w;
  reg previous_aw_stalled = 0;
  reg [17:0] previous_awaddr;
  wire [17:0] awaddr, araddr;
  wire [31:0] wdata;
  wire awvalid, wvalid, arvalid, bready, rready;
  wire [3:0] wstrb;
  reg awready = 0, wready = 0;
  reg bvalid = 0, rvalid = 0;
  reg [17:0] aw_queue [0:63];
  reg [31:0] w_queue [0:63];
  integer aw_head = 0, aw_tail = 0, w_head = 0, w_tail = 0;
  wire [17:0] held_aw = aw_queue[aw_head % 64];
  wire [31:0] held_w = w_queue[w_head % 64];
  reg [15:0] mdio_data = 0;
  wire [1:0] response = mode == 3 ? 2'b10 : 2'b00;
  integer mdio_commands = 0;
  integer bad_responses = 0;
  reg [15:0] external_bmcr = 0, internal_bmcr = 0;

  eth_j10_axi_lite_ctrl dut (
    .axi_lite_clk(clk), .axi_lite_resetn(resetn),
    .m_axi_awaddr(awaddr), .m_axi_awvalid(awvalid), .m_axi_awready(awready),
    .m_axi_wdata(wdata), .m_axi_wstrb(wstrb), .m_axi_wvalid(wvalid), .m_axi_wready(wready),
    .m_axi_bvalid(bvalid), .m_axi_bready(bready), .m_axi_bresp(response),
    .m_axi_araddr(araddr), .m_axi_arvalid(arvalid), .m_axi_arready(1'b1),
    .m_axi_rdata(32'h80), .m_axi_rvalid(rvalid), .m_axi_rready(rready), .m_axi_rresp(response),
    .start_config(start_config), .cmnd_data(8'b0), .cmnd_data_valid(1'b0)
  );

  // Independent AW/W queues model a legal AXI-Lite subordinate.
  // MDIO management reads always return ready; no PHY or link is modeled.
  always @* begin
    awready = (aw_tail - aw_head < 64) && (mode != 1 || cycle >= 40);
    wready = (w_tail - w_head < 64) && (mode != 2 || cycle >= 40);
  end

  always @(posedge clk) begin
    if (!resetn) begin
      cycle <= 0;
      aw_head <= 0;
      aw_tail <= 0;
      w_head <= 0;
      w_tail <= 0;
      bvalid <= 0;
      rvalid <= 0;
      previous_aw_stalled <= 0;
      aw_count <= 0;
      w_count <= 0;
      b_count <= 0;
      dropped_aw <= 0;
      mdio_commands <= 0;
      bad_responses <= 0;
      external_bmcr <= 0;
      internal_bmcr <= 0;
    end else begin
      cycle <= cycle + 1;
      if (previous_aw_stalled && (!awvalid || awaddr !== previous_awaddr)) begin
        dropped_aw <= dropped_aw + 1;
        $display("DROPPED_AW mode=%0d cycle=%0d awvalid=%b old=%h new=%h", mode, cycle, awvalid, previous_awaddr, awaddr);
      end
      previous_aw_stalled <= awvalid && !awready;
      previous_awaddr <= awaddr;
      if (awvalid && awready) begin
        aw_queue[aw_tail % 64] <= awaddr;
        aw_tail <= aw_tail + 1;
        aw_count <= aw_count + 1;
      end
      if (wvalid && wready) begin
        w_queue[w_tail % 64] <= wdata;
        w_tail <= w_tail + 1;
        w_count <= w_count + 1;
      end
      if (aw_head != aw_tail && w_head != w_tail && !bvalid) begin
        aw_head <= aw_head + 1;
        w_head <= w_head + 1;
        bvalid <= 1;
        if (mode == 0) $display("WRITE address=%h data=%h", held_aw, held_w);
        if (held_aw == 'h508) mdio_data <= held_w[15:0];
        if (held_aw == 'h504) begin
          mdio_commands <= mdio_commands + 1;
          if (mode == 0) $display("MDIO phy=%0d reg=%0d data=%h", held_w[28:24], held_w[20:16], mdio_data);
          if (held_w[20:16] == 0 && held_w[28:24] == 3) external_bmcr <= mdio_data;
          if (held_w[20:16] == 0 && held_w[28:24] == 1) internal_bmcr <= mdio_data;
        end
      end
      if (bvalid && bready) begin
        bvalid <= 0;
        b_count <= b_count + 1;
        if (response != 0) bad_responses <= bad_responses + 1;
      end
      if (rvalid && rready) rvalid <= 0;
      if (arvalid) rvalid <= 1;
    end
  end

  task run_case(input integer selected_mode);
    begin
      @(negedge clk);
      resetn = 0;
      start_config = 0;
      mode = selected_mode;
      repeat (8) @(negedge clk);
      resetn = 1;
      start_config = 1;
      repeat (10) @(negedge clk);
      start_config = 0;
      repeat (1500) @(negedge clk);
      $display("CASE mode=%0d aw=%0d w=%0d b=%0d dropped_aw=%0d state=%0d mdio=%0d bad_b=%0d external_bmcr=%h internal_bmcr=%h",
               mode, aw_count, w_count, b_count, dropped_aw, dut.axi_config_cs,
               mdio_commands, bad_responses, external_bmcr, internal_bmcr);
    end
  endtask

  initial begin
    run_case(0);
    if (dut.axi_config_cs != 61 || external_bmcr != 16'h4140 || internal_bmcr != 16'h0140 ||
        mdio_commands != 8 || dropped_aw != 0 || aw_count != w_count || w_count != b_count)
      $fatal(1, "Baseline differs from reviewed generated controller");
    mode0_w = w_count;
    run_case(1);
    if (dropped_aw == 0) $fatal(1, "Expected AW withdrawal with W accepted before AW");
    run_case(2);
    if (aw_count <= w_count) $fatal(1, "Expected unpaired AW after early address acceptance");
    run_case(3);
    if (bad_responses == 0 || dut.axi_config_cs != 61 || w_count != mode0_w)
      $fatal(1, "Expected controller to continue initialization despite error responses");
    $display("CHARACTERIZED: default PHY loopback/AN-off, early-W AW withdrawal, early-AW duplication, ignored SLVERR");
    $finish;
  end

  initial begin
    #100000;
    $fatal(1, "Bounded controller test timed out");
  end
endmodule

// Behavioral FDRE model for the generated five-stage start_config synchronizer.
module FDRE #(parameter INIT = 1'b0)(input C, CE, R, D, output reg Q = INIT);
  always @(posedge C) if (R) Q <= 0; else if (CE) Q <= D;
endmodule
