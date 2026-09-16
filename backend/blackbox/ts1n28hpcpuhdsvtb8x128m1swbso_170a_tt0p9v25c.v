`resetall
`celldefine
`timescale 1ns/1ps

(* black_box *)
module TS1N28HPCPUHDSVTB8X128M1SWBSO (
  input SLP, SD, CLK, CEB, WEB, CEBM, WEBM,
  input [2:0] A,
  input [127:0] D, BWEB,
  input [2:0] AM,
  input [127:0] DM, BWEBM,
  input BIST,
  input [1:0] RTSEL, WTSEL,
  output [127:0] Q
);
endmodule
`endcelldefine
