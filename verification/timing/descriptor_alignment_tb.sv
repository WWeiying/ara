// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps

module descriptor_alignment_tb;
  logic clk_i = 0;
  logic rst_ni = 1;
  logic [127:0] read_data;
  logic [15:0] read_data_strb, read_data_offset;
  logic [127:0] qbs_data;
  logic [15:0] qbs_mask;
  logic [511:0] akv_data;
  logic [63:0] akv_mask;
  int offsets [10] = '{0, 1, 15, 16, 31, 48, 49, 63, 64, 65535};

  // These modules are generated from the actual RTL declarations/assignments.
  qbs_descriptor_alignment_dut qbs (
    .descriptor_write_data(qbs_data), .descriptor_write_mask(qbs_mask), .*);
  akv_descriptor_alignment_dut akv (
    .descriptor_write_data(akv_data), .descriptor_write_mask(akv_mask), .*);
  descriptor_alignment_checker #(.Bytes(16)) qbs_check (
    .descriptor_write_data(qbs_data), .descriptor_write_mask(qbs_mask), .*);
  descriptor_alignment_checker #(.Bytes(64)) akv_check (
    .descriptor_write_data(akv_data), .descriptor_write_mask(akv_mask), .*);

  task automatic tick;
    read_data = {$urandom, $urandom, $urandom, $urandom};
    #1;
    clk_i = 1;
    #1;
    clk_i = 0;
  endtask

  initial begin
    // Exercise every 16-bit offset, including high bits which must not wrap.
    for (int offset = 0; offset < 65536; offset++) begin
      read_data_offset = 16'(offset);
      read_data_strb = 16'hffff;
      tick();
      read_data_strb = 16'($urandom);
      tick();
    end
    foreach (offsets[i]) begin
      read_data_offset = 16'(offsets[i]);
      for (int strobe = 0; strobe < 65536; strobe++) begin
        read_data_strb = 16'(strobe);
        tick();
      end
    end
    $display("Descriptor alignment PASS cases=786432 per descriptor");
    $finish;
  end
endmodule
