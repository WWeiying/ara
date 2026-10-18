module shared_forward_capture_tb;
  localparam int NrOperandQueues = 9;
  typedef logic [63:0] elen_t;
  logic clk_i = 0;
  always #5 clk_i = !clk_i;
  logic rst_ni;
  logic [8:0] fire, cache_fire, cache_index, sldu_cache_fire, mfpu_fire;
  elen_t [1:0] cache_data;
  elen_t sldu_cache_data, mfpu_data, sldu_data;
  elen_t [8:0] expected_input, result;
  logic [8:0] valid;
  int hits[5];
  int multi_reader_cycles, reset_cycles;
  bit injected_mismatch_seen=0;
  logic [31:0] rng = 32'h637ac219;
  function automatic logic [31:0] next_random(input logic [31:0] value);
    logic [31:0] x;
    x = value ^ (value << 13);
    x ^= x >> 17;
    return x ^ (x << 5);
  endfunction
  shared_forward_capture_dut dut (
    .clk_i, .rst_ni, .operand_forward_fire(fire),
    .operand_forward_reduction_cache_fire(cache_fire),
    .operand_forward_reduction_cache_index(cache_index),
    .operand_forward_sldu_cache_fire(sldu_cache_fire),
    .operand_forward_mfpu_fire(mfpu_fire),
    .reduction_result_cache_wdata_q(cache_data),
    .recent_sldu_result_wdata_q(sldu_cache_data),
    .recent_mfpu_result_wdata_q(mfpu_data), .sldu_result_wdata(sldu_data),
    .operand_forward_data(expected_input),
    .forwarded_operand_o(result), .forwarded_operand_valid_o(valid)
  );
  initial begin
    rst_ni = 0; fire = 0; cache_fire = 0; cache_index = 0;
    sldu_cache_fire = 0; mfpu_fire = 0; cache_data = '0;
    sldu_cache_data = 0; mfpu_data = 0; sldu_data = 0; expected_input = '0;
    foreach(hits[i]) hits[i] = 0;
    multi_reader_cycles = 0; reset_cycles = 0;
    repeat (2) @(negedge clk_i);
    for (int cycle = 0; cycle < 6000; cycle++) begin
      // Every source changes on every cycle, including cache replacement.
      rng = next_random(rng); cache_data[0] = {rng, ~rng};
      rng = next_random(rng); cache_data[1] = {rng, ~rng};
      rng = next_random(rng); sldu_cache_data = {rng, ~rng};
      // Partial producer writes may leave unused bytes unknown. The capture
      // must preserve the original four-state payload, including those bytes.
      if (cycle%41==7) sldu_cache_data[63:8]='x;
      rng = next_random(rng); mfpu_data = {rng, ~rng};
      rng = next_random(rng); sldu_data = {rng, ~rng};
      rst_ni = (cycle % 257) != 0;
      if (!rst_ni) reset_cycles++;
      cache_fire = 0; cache_index = 0; sldu_cache_fire = 0; mfpu_fire = 0;
      for (int q = 0; q < 9; q++) begin
        int src;
        rng = next_random(rng);
        // Directed broadcasts, all five sources together, then sparse traffic.
        src = cycle < 10 ? cycle % 5 : (cycle < 20 ? q % 5 : int'(rng % 5));
        fire[q] = cycle < 20 || rng[12];
        case (src)
          0, 1: begin
            cache_fire[q] = fire[q]; cache_index[q] = 1'(src);
            mfpu_fire[q] = fire[q]; // Cache classification must take priority.
            expected_input[q] = cache_data[src];
          end
          2: begin sldu_cache_fire[q] = fire[q]; expected_input[q] = sldu_cache_data; end
          3: begin mfpu_fire[q] = fire[q]; expected_input[q] = mfpu_data; end
          4: expected_input[q] = sldu_data;
        endcase
        if (fire[q] && rst_ni) hits[src]++;
      end
      if ($countones(fire) > 1 && rst_ni) multi_reader_cycles++;
      if ($test$plusargs("INJECT_SOURCE_MISMATCH") && cycle==10)
        expected_input[0][0]=!expected_input[0][0];
      @(posedge clk_i); #1;
      if (valid !== (rst_ni ? fire : 9'b0)) $fatal(1,"valid mismatch");
      for (int q = 0; q < 9; q++)
        if (valid[q] && result[q] !== expected_input[q]) begin
          if ($test$plusargs("INJECT_SOURCE_MISMATCH")&&cycle==10&&q==0) begin
            injected_mismatch_seen=1;
            $display("payload mismatch (intentional negative control) q=0");
          end else $fatal(1,"payload mismatch q=%0d",q);
        end
      // Allow the next sampling edge to exercise the in-RTL assertion too.
      if (injected_mismatch_seen&&cycle==11) begin
        $display("NEGATIVE_CONTROL_COMPLETED");$finish;
      end
      @(negedge clk_i);
    end
    foreach(hits[i]) if (hits[i] < 100) $fatal(1,"source coverage missing");
    if (multi_reader_cycles < 100 || reset_cycles < 10) $fatal(1,"stress coverage missing");
    $display("SHARED_FORWARD_CAPTURE_PASS cycles=6000 hits=%p multireader=%0d resets=%0d",hits,multi_reader_cycles,reset_cycles);
    $finish;
  end
endmodule
