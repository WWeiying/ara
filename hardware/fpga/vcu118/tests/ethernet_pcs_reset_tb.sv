`timescale 1ns/1ps
module ethernet_pcs_reset_tb;
  reg clk = 0;
  always #5 clk = ~clk;
  reg reset = 1;
  reg phy_settled = 0;
  reg request = 0;
  wire mac_reset;
  eth_diag_pcs_reset dut (
    .clk(clk), .reset(reset), .phy_settled(phy_settled),
    .request(request), .mac_reset(mac_reset)
  );
  task expect_reset(input bit value);
    #1;
    if (mac_reset !== value) $fatal(1, "mac_reset=%b expected=%b", mac_reset, value);
  endtask
  initial begin
    expect_reset(1);
    @(negedge clk); reset = 0;
    @(negedge clk); phy_settled = 1;
    expect_reset(0);
    request = 1;
    expect_reset(0);
    @(posedge clk); #1;
    expect_reset(1);
    if (!phy_settled) $fatal(1, "PCS request disturbed PHY settle state");
    @(negedge clk); request = 0;
    @(posedge clk); #1;
    expect_reset(0);
    reset = 1;
    expect_reset(0);
    phy_settled = 0;
    expect_reset(1);
    $display("PCS_RESET_PASS");
    $finish;
  end
endmodule
