`resetall
`celldefine
`timescale 1ns/1ps

(* black_box *)
module TS1N28HPCPUHDSVTB96X256M1SWBSO (
  input SLP, SD, CLK, CEB, WEB, CEBM, WEBM,
  input [6:0] A,
  input [255:0] D, BWEB,
  input [6:0] AM,
  input [255:0] DM, BWEBM,
  input BIST,
  input [1:0] RTSEL, WTSEL,
  output [255:0] Q
);
endmodule
`endcelldefine
