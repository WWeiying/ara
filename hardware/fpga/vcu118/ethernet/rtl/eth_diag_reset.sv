// Independent management-clock reset sequence. No PHY clock is required.
module eth_diag_reset #(
  parameter integer HOLD_CYCLES = 2000000,
  parameter integer SETTLE_CYCLES = 20000000
) (
  input wire clk,
  input wire reset,
  input wire request,
  output wire phy_reset_n,
  output wire settled
);
  localparam integer TOTAL = HOLD_CYCLES + SETTLE_CYCLES;
  localparam integer WIDTH = $clog2(TOTAL + 1);
  reg [WIDTH-1:0] elapsed = 0;
  always @(posedge clk or posedge reset) begin
    if (reset) elapsed <= 0;
    else if (request) elapsed <= 0;
    else if (elapsed < TOTAL) elapsed <= elapsed + 1'b1;
  end
  assign phy_reset_n = !reset && !request && elapsed >= HOLD_CYCLES;
  assign settled = !reset && !request && elapsed == TOTAL;
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
