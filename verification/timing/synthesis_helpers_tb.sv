// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module synthesis_helpers_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  int unsigned checks = 0;
  int lanes [5] = '{1, 2, 4, 8, 16};
  int unsigned rng = 32'h512867ab;

  task automatic check_word(input int unsigned value, log_bytes, ew);
    logic [31:0] divisor, quotient, remainder;
    divisor = (32'd1 << log_bytes) >> ew;
    quotient = value / divisor;
    remainder = value % divisor;
    assert (element_word_index(value, log_bytes, vew_e'(ew)) === quotient &&
            element_word_offset(value, log_bytes, vew_e'(ew)) === remainder)
      else $fatal(1, "word arithmetic value=%h log_bytes=%0d ew=%0d", value, log_bytes, ew);
    checks++;
  endtask

  initial begin
    for (int l = 0; l < 5; l++)
      for (int ew = 0; ew < 8; ew++)
        for (int b = 0; b < 1024; b++) begin
          assert (deshuffle_index(16'(b), lanes[l], vew_e'(ew)) ===
                  ara_pkg_reference::deshuffle_index(16'(b), lanes[l], vew_e'(ew)))
            else $fatal(1, "deshuffle lanes=%0d ew=%0d byte=%0d", lanes[l], ew, b);
          checks++;
        end
    for (int log_bytes = 0; log_bytes < 13; log_bytes++)
      for (int ew = 0; ew < 8; ew++) begin
        for (int v = 0; v < 8192; v++) check_word(v, log_bytes, ew);
        check_word(32'hffffffff, log_bytes, ew);
        check_word(32'h80000000, log_bytes, ew);
        for (int r = 0; r < 64; r++) begin
          rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
          check_word(rng, log_bytes, ew);
        end
      end
    for (int ew = 0; ew < 8; ew++)
      for (int b = 0; b < 128; b++) begin
        assert (((b % (1 << ew)) == 0) == ((b & ((1 << ew)-1)) == 0))
          else $fatal(1, "mask alignment");
        checks++;
      end
    for (int group_log = 0; group_log < 4; group_log++)
      for (int vd = 0; vd < 32; vd++) begin
        assert ((vd % (1 << group_log)) == (vd & ((1 << group_log)-1)))
          else $fatal(1, "destination alignment");
        checks++;
      end
    $display("Synthesis helpers PASS checks=%0d", checks);
    $finish;
  end
endmodule
