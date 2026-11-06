  longint unsigned replay_probe_cycle = 0;
  logic replay_probe_busy_q = 0, replay_probe_fault_q = 0;
  initial $display("MATRIX_FAULT_SCHEDULE fast=%0d", $test$plusargs("MATRIX_FAST_FAULT_DRAIN"));
  always @(posedge clk) begin
    replay_probe_cycle++;
    if (rst_n && inject_axi_fault && activation_access inside {
        QBS_ACTIVATION_ACCESS_REUSE, QBS_ACTIVATION_ACCESS_RELEASE}) begin
      if (dut.i_engine.context_replay_start_valid && dut.i_engine.context_replay_start_ready)
        $display("MATRIX_REPLAY_EVENT cycle=%0d event=START m=%0d access=%0d busy=%0b offset=%0d",
          replay_probe_cycle, command_m, activation_access,
          dut.i_engine.context_replay_busy, dut.i_engine.context_replay_offset);
      if (dut.i_engine.context_replay_data_valid && dut.i_engine.context_replay_data_ready &&
          dut.i_engine.context_replay_last)
        $display("MATRIX_REPLAY_EVENT cycle=%0d event=REPLAY_LAST m=%0d access=%0d busy=%0b offset=%0d",
          replay_probe_cycle, command_m, activation_access,
          dut.i_engine.context_replay_busy, dut.i_engine.context_replay_offset);
      if (replay_probe_busy_q && !dut.i_engine.context_replay_busy)
        $display("MATRIX_REPLAY_EVENT cycle=%0d event=REPLAY_IDLE m=%0d access=%0d busy=%0b offset=%0d",
          replay_probe_cycle, command_m, activation_access,
          dut.i_engine.context_replay_busy, dut.i_engine.context_replay_offset);
      if (axi_r_valid && axi_r_ready && axi_r.resp == RESP_SLVERR)
        $display("MATRIX_REPLAY_EVENT cycle=%0d event=AXI_ERROR m=%0d access=%0d busy=%0b offset=%0d",
          replay_probe_cycle, command_m, activation_access,
          dut.i_engine.context_replay_busy, dut.i_engine.context_replay_offset);
      if (axi_r_valid && axi_r_ready && axi_r.last)
        $display("MATRIX_REPLAY_EVENT cycle=%0d event=AXI_LAST m=%0d access=%0d busy=%0b offset=%0d",
          replay_probe_cycle, command_m, activation_access,
          dut.i_engine.context_replay_busy, dut.i_engine.context_replay_offset);
      if (dut.i_engine.read_fault_valid && !replay_probe_fault_q)
        $display("MATRIX_REPLAY_EVENT cycle=%0d event=READ_FAULT m=%0d access=%0d busy=%0b offset=%0d",
          replay_probe_cycle, command_m, activation_access,
          dut.i_engine.context_replay_busy, dut.i_engine.context_replay_offset);
    end
    replay_probe_busy_q <= dut.i_engine.context_replay_busy;
    replay_probe_fault_q <= dut.i_engine.read_fault_valid;
  end
