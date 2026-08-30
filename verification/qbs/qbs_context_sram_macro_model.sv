// Functional test model for the 64x256 single-port context SRAM macro.
module TS1N28HPCPUHDSVTB64X256M1SWBSO (
  input  logic         SLP,
  input  logic         SD,
  input  logic         CLK,
  input  logic         CEB,
  input  logic         WEB,
  input  logic         CEBM,
  input  logic         WEBM,
  input  logic [5:0]   A,
  input  logic [255:0] D,
  input  logic [255:0] BWEB,
  input  logic [5:0]   AM,
  input  logic [255:0] DM,
  input  logic [255:0] BWEBM,
  input  logic         BIST,
  input  logic [1:0]   RTSEL,
  input  logic [1:0]   WTSEL,
  output logic [255:0] Q
);

  logic [255:0] memory [64];

  always_ff @(posedge CLK) begin
    if (!CEB) begin
      if (!WEB)
        memory[A] <= (memory[A] & BWEB) | (D & ~BWEB);
      else
        Q <= memory[A];
    end
  end

  logic unused;
  assign unused = SLP ^ SD ^ CEBM ^ WEBM ^ ^AM ^ ^DM ^ ^BWEBM ^ BIST ^
                  ^RTSEL ^ ^WTSEL;

endmodule
