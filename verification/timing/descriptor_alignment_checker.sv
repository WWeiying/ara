// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps

module descriptor_alignment_checker #(
  parameter int Bytes = 16,
  parameter int DataWidth = 128,
  parameter int OffsetWidth = 16
) (
  input logic clk_i, rst_ni,
  input logic [DataWidth-1:0] read_data,
  input logic [DataWidth/8-1:0] read_data_strb,
  input logic [OffsetWidth-1:0] read_data_offset,
  input logic [8*Bytes-1:0] descriptor_write_data,
  input logic [Bytes-1:0] descriptor_write_mask
);
  longint unsigned checks = 0;
  always @(posedge clk_i) begin
    if (rst_ni) begin
      logic [8*Bytes-1:0] expected_data;
      logic [Bytes-1:0] expected_mask;
      expected_data = '0;
      expected_mask = '0;
      // Original byte-lane scatter, independent of the alignment network.
      for (int lane = 0; lane < DataWidth/8; lane++) begin
        int offset;
        offset = unsigned'(read_data_offset) + lane;
        if (read_data_strb[lane] && offset < Bytes) begin
          expected_mask[offset] = 1'b1;
          expected_data[8*offset +: 8] = read_data[8*lane +: 8];
        end
      end
      assert (expected_mask === descriptor_write_mask)
        else $fatal(1, "descriptor mask mismatch bytes=%0d offset=%0d strb=%h",
                    Bytes, read_data_offset, read_data_strb);
      for (int b = 0; b < Bytes; b++)
        if (expected_mask[b])
          assert (descriptor_write_data[8*b +: 8] === expected_data[8*b +: 8])
            else $fatal(1, "descriptor data mismatch bytes=%0d offset=%0d byte=%0d",
                        Bytes, read_data_offset, b);
      checks++;
    end
  end
  final $display("Descriptor alignment checked bytes=%0d checks=%0d", Bytes, checks);
endmodule

`ifdef TIMING_BIND_QBS_DESCRIPTOR
bind qbs_engine descriptor_alignment_checker #(
  .Bytes(16), .DataWidth(AxiDataWidth), .OffsetWidth(RangeBytesWidth)
) i_descriptor_alignment_check (.*);
`endif

`ifdef TIMING_BIND_AKV_DESCRIPTOR
bind akv_engine descriptor_alignment_checker #(
  .Bytes(64), .DataWidth(AxiDataWidth), .OffsetWidth(RangeBytesWidth)
) i_descriptor_alignment_check (.*);
`endif
