// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Isolated building block; not yet connected to dispatcher/sequencer.
// live_i must OR the running membership of ALL PEs. Allocation is ordered;
// a blocking refill prevents younger allocation until its response retires.
module akv_refill_order_guard #(
  parameter int unsigned NrSlots = 8,
  parameter int unsigned IdWidth = $clog2(NrSlots)
) (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic [NrSlots-1:0] live_i,
  input  logic alloc_valid_i,
  input  logic [IdWidth-1:0] alloc_id_i,
  input  logic alloc_eligible_i,
  input  logic pending_valid_i,
  input  logic pending_eligible_i,
  input  logic refill_wait_i,
  input  logic [IdWidth-1:0] refill_id_i,
  output logic admission_safe_o,
  output logic older_drained_o
);
  logic [NrSlots-1:0] eligible_q;
  logic [NrSlots-1:0] current_refill;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) eligible_q <= '0;
    else if (alloc_valid_i) eligible_q[alloc_id_i] <= alloc_eligible_i;
  end

  // A stale classification cannot authorize an inactive slot; reuse overwrites
  // classification on the same edge as the sequencer publishes the new VID.
  assign admission_safe_o = !(|(live_i & ~eligible_q)) &&
                            (!pending_valid_i || pending_eligible_i);
  always_comb begin
    current_refill = '0;
    if (refill_wait_i && unsigned'(refill_id_i) < NrSlots)
      current_refill[refill_id_i] = 1'b1;
  end
  assign older_drained_o = refill_wait_i && !(|(live_i & ~current_refill));

  // synthesis translate_off
  initial assert (NrSlots > 1 && IdWidth >= $clog2(NrSlots))
    else $fatal(1, "Invalid refill guard geometry");
  always @(posedge clk_i) if (rst_ni) begin
    assert (!alloc_valid_i || unsigned'(alloc_id_i) < NrSlots)
      else $fatal(1, "Invalid allocated VID");
    assert (!refill_wait_i || unsigned'(refill_id_i) < NrSlots)
      else $fatal(1, "Invalid refill VID");
    assert (!(refill_wait_i && alloc_valid_i))
      else $fatal(1, "Younger allocation during blocking refill");
  end
  // synthesis translate_on
endmodule
