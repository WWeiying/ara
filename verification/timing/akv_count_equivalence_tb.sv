// SPDX-License-Identifier: SHL-0.51
module akv_count_equivalence_tb;
  import akv_pkg::*;
  logic [15:0] context_kv_length_q;
  logic [63:0] command_tile_start_i;
  akv_command_e command_i;
  logic valid;
  logic [6:0] count, reference_count;
  int checks = 0;
  int seed = 32'h376f5201;
  akv_count_cone dut (.*);

  task automatic check;
    #1;
    checks++;
    assert (valid === (command_tile_start_i < 64'(context_kv_length_q)))
      else $fatal(1, "AKV range guard was truncated");
    if (valid)
      assert (count === reference_count)
        else $fatal(1, "AKV count kv=%0d start=%0d mode=%0d got=%0d ref=%0d",
            context_kv_length_q, command_tile_start_i, command_i, count, reference_count);
  endtask

  initial begin
    seed = $urandom(seed);
    // Every representable remaining count, including 8/64 tails and 65535.
    context_kv_length_q = 16'hffff;
    for (int mode = 0; mode < 2; mode++) begin
      command_i = mode ? AKV_COMMAND_V2_REFILL : AKV_COMMAND_REFILL;
      for (int remaining = 0; remaining < 65536; remaining++) begin
        command_tile_start_i = 64'(65535 - remaining);
        check();
      end
      for (int bit_index = 16; bit_index < 64; bit_index++) begin
        command_tile_start_i = (64'd1 << bit_index) | 64'd1;
        check();
        assert (!valid) else $fatal(1, "AKV high address accepted");
      end
      for (int trial = 0; trial < 10000; trial++) begin
        context_kv_length_q = 16'($urandom);
        command_tile_start_i = 64'($urandom_range(0, 65535));
        check();
      end
      context_kv_length_q = 16'hffff;
    end
    $display("AKV count equivalence PASS checks=%0d", checks);
    $finish;
  end
endmodule
