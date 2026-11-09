// SPDX-License-Identifier: Apache-2.0
// Private resident payload only: no architectural load/writeback acknowledgments.
module resident_payload_fanout #(
  parameter int unsigned NrLanes = 4,
  parameter int unsigned Width = 64
) (
  input logic clk_i, rst_ni, cancel_i,
  input logic valid_i,
  output logic ready_o,
  input logic [NrLanes-1:0] active_i,
  input logic is_value_i,
  input logic [NrLanes-1:0][Width-1:0] data_i,
  output logic [NrLanes-1:0] valid_o,
  input logic [NrLanes-1:0] ready_i,
  output logic is_value_o,
  output logic [NrLanes-1:0][Width-1:0] data_o,
  output logic empty_o
);
  logic [1:0] count_q;
  logic rd_q, wr_q;
  logic [NrLanes-1:0] pending_q [2];
  logic [NrLanes-1:0][Width-1:0] data_q [2];
  logic kind_q [2];
  logic push, pop;
  logic [NrLanes-1:0] accepted;

  // Two entries sustain one beat/cycle without a downstream-ready path upstream.
  assign ready_o = count_q < 2 && !cancel_i;
  assign valid_o = count_q != 0 && !cancel_i ? pending_q[rd_q] : '0;
  assign accepted = valid_o & ready_i;
  assign push = valid_i && ready_o;
  assign pop = count_q != 0 && !cancel_i &&
               (pending_q[rd_q] & ~accepted) == '0;
  assign data_o = data_q[rd_q];
  assign is_value_o = kind_q[rd_q];
  assign empty_o = count_q == 0;

  // Payload is initialized by push, not reset. Cancel invalidates private entries.
  always_ff @(posedge clk_i) begin
    if (push) begin
      data_q[wr_q] <= data_i;
      kind_q[wr_q] <= is_value_i;
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      count_q <= '0;
      rd_q <= 0;
      wr_q <= 0;
      pending_q[0] <= '0;
      pending_q[1] <= '0;
    end else if (cancel_i) begin
      count_q <= '0;
      rd_q <= 0;
      wr_q <= 0;
      pending_q[0] <= '0;
      pending_q[1] <= '0;
    end else begin
      if (count_q != 0) pending_q[rd_q] <= pending_q[rd_q] & ~accepted;
      if (pop) rd_q <= !rd_q;
      if (push) begin
        pending_q[wr_q] <= active_i;
        wr_q <= !wr_q;
      end
      case ({push, pop})
        2'b10: count_q <= count_q + 1'b1;
        2'b01: count_q <= count_q - 1'b1;
        default: ;
      endcase
    end
  end
`ifndef SYNTHESIS
  always_ff @(posedge clk_i) if (rst_ni) begin
    assert (count_q <= 2) else $fatal(1, "Resident payload FIFO overflow");
    assert (!(push && active_i == '0)) else $fatal(1, "Empty resident lane mask");
  end
`endif
endmodule
