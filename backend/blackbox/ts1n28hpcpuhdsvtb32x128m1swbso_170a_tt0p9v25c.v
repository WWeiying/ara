`resetall

`celldefine

`timescale 1ns/1ps
(* black_box *)
module TS1N28HPCPUHDSVTB32X128M1SWBSO (
            SLP,
            SD,
            CLK, CEB, WEB,
            CEBM, WEBM,
            A, D,
            BWEB,
            AM, DM,
            BWEBM,
            BIST,
            RTSEL,
            WTSEL,
            Q);

//=== IO Ports ===//

// Mode Control
input BIST;
// Normal Mode Input
input SLP;
input SD;
input CLK;
input CEB;
input WEB;
input [4:0] A;
input [127:0] D;
input [127:0] BWEB;

// BIST Mode Input
input CEBM;
input WEBM;
input [4:0] AM;
input [127:0] DM;
input [127:0] BWEBM;

// Data Output
output [127:0] Q;

// Test Mode
input [1:0] RTSEL;
input [1:0] WTSEL;

endmodule
`endcelldefine
