// Independent management-clock reset sequence. No PHY clock is required.
module eth_diag_reset #(
  parameter integer HOLD_CYCLES = 2000000,
  parameter integer SETTLE_CYCLES = 20000000
) (
  input wire clk,
  input wire reset,
  input wire request,
  output reg phy_reset_n = 1'b0,
  output reg settled = 1'b0
);
  localparam integer TOTAL = HOLD_CYCLES + SETTLE_CYCLES;
  localparam integer WIDTH = $clog2(TOTAL + 1);
  reg [WIDTH-1:0] elapsed = 0;
  always @(posedge clk or posedge reset) begin
    if (reset) begin
      elapsed <= 0;
      phy_reset_n <= 0;
      settled <= 0;
    end else if (request) begin
      elapsed <= 0;
      phy_reset_n <= 0;
      settled <= 0;
    end else begin
      if (elapsed < TOTAL) elapsed <= elapsed + 1'b1;
      if (elapsed == HOLD_CYCLES - 1) phy_reset_n <= 1;
      if (elapsed == TOTAL - 1) settled <= 1;
    end
  end
endmodule

module eth_diag_reset_sync (
  input wire clk,
  input wire reset,
  output wire reset_out
);
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) reg [2:0] stages = 3'b111;
  always @(posedge clk or posedge reset) begin
    if (reset) stages <= 3'b111;
    else stages <= {stages[1:0], 1'b0};
  end
  assign reset_out = stages[2];
endmodule
