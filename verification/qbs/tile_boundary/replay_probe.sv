`timescale 1ns/1ps
// Test-only receiver pressure. The original suite and its assertions are intact.
module qbs_replay_fault_probe;
  bit enabled, trace_enabled, holding, armed;
  bit previous_busy, previous_error, previous_fault;
  integer cycle, holds, overlaps;
  initial begin
    enabled = $test$plusargs("QBS_FAULT_REPLAY_HOLD");
    trace_enabled = $test$plusargs("QBS_FAULT_REPLAY_TRACE");
    holding = 0;
    armed = 1;
    cycle = 0;
    holds = 0;
    overlaps = 0;
  end

  always @(negedge qbs_engine_tb.clk) begin
    if (holding && (!qbs_engine_tb.rst_n ||
        qbs_engine_tb.dut.i_engine.read_fault_valid)) begin
      release qbs_engine_tb.dut.i_engine.i_compute_engine.activation_write_ready_o;
      holding = 0;
    end
    if (!qbs_engine_tb.inject_axi_fault) armed = 1;
    if (enabled && armed && qbs_engine_tb.rst_n &&
        qbs_engine_tb.inject_axi_fault &&
        qbs_engine_tb.dut.i_engine.context_replay_busy &&
        qbs_engine_tb.activation_access inside {2, 3}) begin
      force qbs_engine_tb.dut.i_engine.i_compute_engine.activation_write_ready_o = 1'b0;
      holding = 1;
      armed = 0;
      holds++;
      $display("QBS_REPLAY_HOLD cycle=%0d access=%0d", cycle,
          qbs_engine_tb.activation_access);
    end
  end

  always @(posedge qbs_engine_tb.clk) begin
    cycle++;
    if (holding) begin
      assert (!qbs_engine_tb.dut.i_engine.context_replay_data_ready &&
          !qbs_engine_tb.dut.i_engine.i_compute_engine.i_block_adapter_bank0.activation_write_valid_i &&
          !qbs_engine_tb.dut.i_engine.i_compute_engine.i_block_adapter_bank1.activation_write_valid_i)
        else $fatal(1, "replay hold did not stop both activation receivers");
    end
    if (qbs_engine_tb.rst_n && qbs_engine_tb.inject_axi_fault &&
        qbs_engine_tb.activation_access inside {2, 3}) begin
      if (trace_enabled &&
          (previous_busy != qbs_engine_tb.dut.i_engine.context_replay_busy ||
           (!previous_error && qbs_engine_tb.axi_r_valid && qbs_engine_tb.axi_r.resp != 0) ||
           (!previous_fault && qbs_engine_tb.dut.i_engine.read_fault_valid)))
        $display("QBS_REPLAY_TIMING cycle=%0d busy=%b offset=%0d last=%b r_valid=%b r_ready=%b r_resp=%0d r_last=%b fault=%b hold=%b access=%0d",
            cycle, qbs_engine_tb.dut.i_engine.context_replay_busy,
            qbs_engine_tb.dut.i_engine.context_replay_offset,
            qbs_engine_tb.dut.i_engine.context_replay_last,
            qbs_engine_tb.axi_r_valid, qbs_engine_tb.axi_r_ready,
            qbs_engine_tb.axi_r.resp, qbs_engine_tb.axi_r.last,
            qbs_engine_tb.dut.i_engine.read_fault_valid, holding,
            qbs_engine_tb.activation_access);
      if (!previous_fault && qbs_engine_tb.dut.i_engine.read_fault_valid &&
          qbs_engine_tb.dut.i_engine.context_replay_busy) overlaps++;
    end
    previous_busy = qbs_engine_tb.dut.i_engine.context_replay_busy;
    previous_error = qbs_engine_tb.axi_r_valid && qbs_engine_tb.axi_r.resp != 0;
    previous_fault = qbs_engine_tb.dut.i_engine.read_fault_valid;
  end

  final begin
    if (enabled)
      $display("QBS_REPLAY_HOLD_SUMMARY holds=%0d overlaps=%0d held_at_end=%b",
          holds, overlaps, holding);
  end
endmodule

bind qbs_engine_tb qbs_replay_fault_probe i_replay_fault_probe ();
