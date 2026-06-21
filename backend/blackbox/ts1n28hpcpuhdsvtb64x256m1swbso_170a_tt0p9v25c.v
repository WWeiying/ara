`resetall

`celldefine

`timescale 1ns/1ps
(* black_box *)
module TS1N28HPCPUHDSVTB64X256M1SWBSO (
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
input [5:0] A;
input [255:0] D;
input [255:0] BWEB;

// BIST Mode Input
input CEBM;
input WEBM;
input [5:0] AM;
input [255:0] DM;
input [255:0] BWEBM;

// Data Output
output [255:0] Q;

// Test Mode
input [1:0] RTSEL;
input [1:0] WTSEL;

endmodule
`endcelldefine
