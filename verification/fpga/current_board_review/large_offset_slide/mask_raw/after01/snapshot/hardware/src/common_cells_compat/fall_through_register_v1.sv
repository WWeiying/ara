// Copyright 2018 ETH Zurich and University of Bologna.
// Copyright and related rights are licensed under the Solderpad Hardware
// License, Version 0.51 (the "License"); you may not use this file except in
// compliance with the License. You may obtain a copy of the License at
// http://solderpad.org/licenses/SHL-0.51. Unless required by applicable law
// or agreed to in writing, software, hardware and materials distributed under
// this License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied. See the License for the
// specific language governing permissions and limitations under the License.

// Fall-through register with a ready/valid handshake. The output data and
// valid paths remain combinational; the FIFO cuts the ready path.
module fall_through_register_v1 #(
    parameter type         T     = logic,
    parameter int unsigned DEPTH = 1
) (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic clr_i,
    input  logic testmode_i,
    input  logic valid_i,
    output logic ready_o,
    input  T     data_i,
    output logic valid_o,
    input  logic ready_i,
    output T     data_o
);

  logic fifo_empty;
  logic fifo_full;

  fifo_v3 #(
    .FALL_THROUGH(1'b1),
    .DEPTH       (DEPTH),
    .dtype       (T)
  ) i_fifo (
    .clk_i,
    .rst_ni,
    .flush_i   (clr_i),
    .testmode_i,
    .full_o    (fifo_full),
    .empty_o   (fifo_empty),
    .usage_o   (),
    .data_i,
    .push_i    (valid_i && !fifo_full),
    .data_o,
    .pop_i     (ready_i && !fifo_empty)
  );

  assign ready_o = !fifo_full;
  assign valid_o = !fifo_empty;

endmodule
