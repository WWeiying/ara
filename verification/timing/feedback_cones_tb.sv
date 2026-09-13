// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
module feedback_cones_tb;
  logic clk_i = 0;
  always #5 clk_i = ~clk_i;
  logic rst_ni = 0;
  logic [31:0] pending_i;
  logic [4:0] rr_i, first, second, first_ref, second_ref;
  logic [1:0] valid, valid_ref;
  logic [5:0] row_i;
  logic [2:0] index_i;
  logic [7:0] k_i;
  logic [8:0] blocks_i;
  logic [15:0] bytes_i;
  logic [63:0] base_i, address, address_ref;
  logic r4_i;
  int arb_checks = 0, address_checks = 0;
  qbs_correction_select_comb dut (.pending_i, .rr_i,
      .valid_o(valid), .first_o(first), .second_o(second));
  qbs_correction_select_comb_reference reference (.pending_i, .rr_i,
      .valid_o(valid_ref), .first_o(first_ref), .second_o(second_ref));
  qbs_address_timing address_dut (.clk_i, .rst_ni, .row_i, .index_i, .k_i,
      .blocks_i, .bytes_i, .base_i, .r4_i, .address_o(address));
  qbs_address_timing_reference address_reference (.clk_i, .rst_ni, .row_i,
      .index_i, .k_i, .blocks_i, .bytes_i, .base_i, .r4_i, .address_o(address_ref));

  task automatic check_arb(input logic [31:0] pending, input logic [4:0] rr);
    int first_expected, second_expected;
    pending_i = pending;
    rr_i = rr;
    #1;
    first_expected = -1;
    second_expected = -1;
    for (int offset = 0; offset < 32; offset++) begin
      if (pending[(int'(rr) + offset) % 32]) begin
        if (first_expected < 0) first_expected = (int'(rr) + offset) % 32;
        else if (second_expected < 0) second_expected = (int'(rr) + offset) % 32;
      end
    end
    assert ({valid, first, second} === {valid_ref, first_ref, second_ref})
      else $fatal(1, "Correction mismatch pending=%h rr=%0d", pending, rr);
    assert (valid == {1'(second_expected >= 0), 1'(first_expected >= 0)} &&
            (!valid[0] || first == 5'(first_expected)) &&
            (!valid[1] || second == 5'(second_expected)))
      else $fatal(1, "Correction disagrees with circular software scan");
    arb_checks++;
  endtask

  always @(negedge clk_i) if (rst_ni) begin
    assert (address === address_ref)
      else $fatal(1, "Address mismatch actual=%h expected=%h", address, address_ref);
    address_checks++;
  end

  initial begin
    pending_i = '0; rr_i = '0; row_i = '0; index_i = '0; k_i = '0;
    blocks_i = '0; bytes_i = '0; base_i = '0; r4_i = 0;
    repeat (3) @(negedge clk_i);
    #1 rst_ni = 1;
    // All circular positions and all masks with up to three distinct bits.
    for (int rr = 0; rr < 32; rr++) begin
      check_arb('0, 5'(rr));
      check_arb('1, 5'(rr));
      for (int a = 0; a < 32; a++) begin
        check_arb(32'd1 << a, 5'(rr));
        for (int b = a+1; b < 32; b++) begin
          check_arb((32'd1 << a) | (32'd1 << b), 5'(rr));
          for (int c = b+1; c < 32; c++)
            check_arb((32'd1 << a) | (32'd1 << b) | (32'd1 << c), 5'(rr));
        end
      end
    end
    for (int sample = 0; sample < 50000; sample++) begin
      @(negedge clk_i);
      #1;
      row_i = 6'($urandom); index_i = 3'($urandom); k_i = 8'($urandom);
      blocks_i = 9'($urandom); bytes_i = 16'($urandom);
      base_i = {$urandom, $urandom}; r4_i = 1'($urandom);
      if (sample < 1024) begin
        row_i = 63; index_i = 7; k_i = 255;
        blocks_i = 9'(sample >> 1); bytes_i = 65535; r4_i = sample[0];
        base_i = 64'hfffffffffff00000;
      end
      check_arb($urandom, 5'($urandom));
    end
    repeat (3) @(negedge clk_i);
    $display("Feedback cones PASS arb=%0d address_cycles=%0d", arb_checks, address_checks);
    $finish;
  end
endmodule
