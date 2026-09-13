// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module qbs_dot_pipeline_tb;
  logic clk = 0;
  logic rst_n = 0;
  logic valid = 0;
  logic [2:0] m = 1, rows = 1;
  logic [15:0] mask = 0;
  logic signed [7:0] weight [4][8], activation [4][8];
  logic result_valid;
  logic [15:0] result_mask;
  logic signed [18:0] result_sum [16];
  logic [2:0] expected_valid;
  logic [15:0] expected_mask [3];
  logic signed [18:0] expected_sum [3][16];
  int checked_cycles = 0;
  int accepted = 0;
  int seed = 32'h6b514829;

  always #5 clk = ~clk;
  qbs_dot_array dut (.clk_i(clk), .rst_ni(rst_n), .valid_i(valid),
      .m_i(m), .row_count_i(rows), .stream_valid_i(mask),
      .weight_quant_i(weight), .activation_quant_i(activation),
      .valid_o(result_valid), .stream_valid_o(result_mask), .stream_sum_o(result_sum));

  // Independent scalar sums, delayed by the specified three-cycle interface.
  always @(posedge clk) begin
    if (!rst_n) begin
      expected_valid <= '0;
      for (int stage = 0; stage < 3; stage++) begin
        expected_mask[stage] <= '0;
        for (int stream = 0; stream < 16; stream++) expected_sum[stage][stream] <= '0;
      end
    end else begin
      expected_valid <= {expected_valid[1:0], valid};
      for (int stage = 1; stage < 3; stage++) begin
        expected_mask[stage] <= expected_mask[stage-1];
        for (int stream = 0; stream < 16; stream++)
          expected_sum[stage][stream] <= expected_sum[stage-1][stream];
      end
      expected_mask[0] <= valid ? mask : '0;
      for (int row = 0; row < 4; row++) begin
        for (int ctx = 0; ctx < 4; ctx++) begin
          automatic int total = 0;
          automatic int count = m == 1 ? 8 : m == 2 ? 4 : 2;
          if (valid && row < rows && ctx < m) begin
            for (int lane = 0; lane < count; lane++)
              total += int'(weight[row][lane]) * int'(activation[ctx][lane]);
          end
          expected_sum[0][row*4+ctx] <= 19'(total);
        end
      end
      if (valid) accepted++;
    end
    #1;
    if (result_valid !== expected_valid[2] || result_mask !== expected_mask[2])
      $fatal(1, "dot valid/mask alignment failure cycle=%0d", checked_cycles);
    for (int stream = 0; stream < 16; stream++) begin
      if (result_sum[stream] !== expected_sum[2][stream])
        $fatal(1, "dot arithmetic failure cycle=%0d stream=%0d got=%0d expected=%0d",
            checked_cycles, stream, result_sum[stream], expected_sum[2][stream]);
    end
    checked_cycles++;
  end

  initial begin
    void'($urandom(seed));
    weight = '{default: '0};
    activation = '{default: '0};
    repeat (3) @(negedge clk);
    for (int cycle = 0; cycle < 16000; cycle++) begin
      rst_n = cycle % 997 != 0;
      valid = cycle % 7 != 0;
      m = 3'(1 + cycle % 4);
      rows = 3'(1 + (cycle / 4) % 4);
      mask = '0;
      for (int row = 0; row < 4; row++) begin
        for (int ctx = 0; ctx < 4; ctx++) mask[row*4+ctx] = row < rows && ctx < m;
        for (int lane = 0; lane < 8; lane++) begin
          weight[row][lane] = 8'($urandom());
          activation[row][lane] = 8'($urandom());
          case (cycle % 8)
            0: begin weight[row][lane] = -128; activation[row][lane] = -128; end
            1: begin weight[row][lane] = 127; activation[row][lane] = 127; end
            2: begin weight[row][lane] = -128; activation[row][lane] = 127; end
            3: begin weight[row][lane] = lane % 2 ? -128 : 127;
                     activation[row][lane] = lane % 2 ? 127 : -128; end
            default: ;
          endcase
        end
      end
      @(negedge clk);
    end
    valid = 0;
    rst_n = 1;
    repeat (5) @(negedge clk);
    $display("QBS dot pipeline PASS: checked_cycles=%0d accepted=%0d", checked_cycles, accepted);
    $finish;
  end
endmodule
