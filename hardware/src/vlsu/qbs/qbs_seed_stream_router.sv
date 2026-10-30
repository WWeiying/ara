// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// StA data is wired to both clients, but exactly one sees valid and returns
// ready. Ownership includes a pending QBACC before its VLSU handshake, so a
// lane that accepted earlier cannot leak its operand into VSTU's input cut.
module qbs_seed_stream_router #(
    parameter int unsigned NrLanes = 4
  ) (
    input  logic seed_owner_i,
    input  logic [NrLanes-1:0] lane_valid_i,
    output logic [NrLanes-1:0] lane_ready_o,
    output logic [NrLanes-1:0] store_valid_o,
    input  logic [NrLanes-1:0] store_ready_i,
    output logic [NrLanes-1:0] seed_valid_o,
    input  logic [NrLanes-1:0] seed_ready_i
  );
  assign store_valid_o = lane_valid_i & {NrLanes{!seed_owner_i}};
  assign seed_valid_o = lane_valid_i & {NrLanes{seed_owner_i}};
  assign lane_ready_o = seed_owner_i ? seed_ready_i : store_ready_i;
endmodule
