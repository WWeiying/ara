`timescale 1ns/1ps
module stage2_matrix_queue_probe #(
  parameter int unsigned QueueDepth = 0
) (
  input logic clk_i, rst_ni, command_fire_i, success_i, fault_i,
  input logic [3:0] m_i, profile_i,
  input logic [5:0] n_i,
  input logic [8:0] k_blocks_i,
  input logic seeded_i, enabled_i, push_i, pop_i,
  input logic [31:0] occupancy_i,
  input logic [139:0] data_i, data_o,
  input logic fp_valid_i, fp_ready_i, final_drain_i, fault_drain_i,
  input logic start_valid_i, start_ready_i,
  input logic [1:0] contexts_i,
  input logic result_pending_i,
  input logic [4:0] fp_occupancy_i
);
  logic [139:0] shadow [$];
  logic [139:0] expected;
  bit active = 0, terminal_seen = 0;
  longint unsigned seq = 0, commands = 0, resets = 0, reset_flushed = 0;
  longint unsigned total_push = 0, total_pop = 0;
  longint unsigned pushes, pops, fp_accept, max_occ, full_cycles;
  longint unsigned decoupled, start_overlap, final_drain, fault_drain;
  longint unsigned start_blocked, blocked_context [4];
  longint unsigned blocked_pending, blocked_fp_full, blocked_queue_full;
  int unsigned accepted_k [128];
  int unsigned index, stride;

  always @(posedge clk_i) begin
    if (!rst_ni) begin
      if (active) begin
        $display("STAGE2_QUEUE_RESET seq=%0d enq=%0d deq=%0d flushed=%0d", seq, pushes, pops, shadow.size());
        resets++;
        reset_flushed += shadow.size();
      end
      active = 0;
      terminal_seen = 0;
      shadow.delete();
    end else begin
      assert (occupancy_i == shadow.size() && occupancy_i <= QueueDepth)
        else $fatal(1, "STAGE2_QUEUE occupancy/real-handshake mismatch");
      if (command_fire_i) begin
        assert (shadow.size() == 0) else $fatal(1, "STAGE2_QUEUE cross-command residue");
        seq++;
        active = 1;
        terminal_seen = 0;
        pushes = 0; pops = 0; fp_accept = 0; max_occ = 0; full_cycles = 0;
        decoupled = 0; start_overlap = 0; final_drain = 0; fault_drain = 0;
        start_blocked = 0; blocked_pending = 0; blocked_fp_full = 0; blocked_queue_full = 0;
        foreach (accepted_k[i]) accepted_k[i] = 0;
        foreach (blocked_context[i]) blocked_context[i] = 0;
      end
      if (occupancy_i > max_occ) max_occ = occupancy_i;
      if (enabled_i && occupancy_i == QueueDepth) full_cycles++;
      if (enabled_i && fp_valid_i && fp_ready_i)
        assert (pop_i) else $fatal(1, "STAGE2_QUEUE FP accepted without FIFO pop");
      if (pop_i) begin
        assert (shadow.size() != 0 && fp_valid_i && fp_ready_i)
          else $fatal(1, "STAGE2_QUEUE phantom pop");
        expected = shadow.pop_front();
        assert (data_o === expected) else $fatal(1, "STAGE2_QUEUE reordered/changed FP request");
        pops++;
        total_pop++;
      end
      if (push_i) begin
        assert (enabled_i && QueueDepth != 0) else $fatal(1, "STAGE2_QUEUE fallback used queue");
        shadow.push_back(data_i);
        pushes++;
        total_push++;
        if (fp_valid_i && !fp_ready_i) decoupled++;
      end
      if (fp_valid_i && fp_ready_i) begin
        index = int'(data_o[135:129]);
        stride = m_i > 4 ? 16 : 32;
        assert (index / stride < m_i && index % stride < n_i &&
                data_o[139:136] == 4'((index % stride % 4)*4 + index / stride % 4) &&
                data_o[128] == (!seeded_i && accepted_k[index] == 0) &&
                accepted_k[index] < k_blocks_i)
          else $fatal(1, "STAGE2_QUEUE slot/index/first/K order mismatch");
        accepted_k[index]++;
        fp_accept++;
      end
      if (start_valid_i && start_ready_i && occupancy_i != 0) start_overlap++;
      if (final_drain_i && occupancy_i != 0) final_drain++;
      if (fault_drain_i && occupancy_i != 0) fault_drain++;
      if (start_valid_i && !start_ready_i) begin
        start_blocked++;
        blocked_context[contexts_i]++;
        if (result_pending_i) blocked_pending++;
        if (fp_occupancy_i == 16) blocked_fp_full++;
        if (QueueDepth != 0 && occupancy_i == QueueDepth) blocked_queue_full++;
      end
      if ((success_i || fault_i) && !terminal_seen) begin
        assert (shadow.size() == 0 && pushes == pops)
          else $fatal(1, "STAGE2_QUEUE terminal before exact payload drain");
        if (success_i) begin
          assert (fp_accept == longint'(m_i)*n_i*k_blocks_i &&
                  pushes == (enabled_i ? fp_accept : 0))
            else $fatal(1, "STAGE2_QUEUE missing/duplicated successful FP work");
        end
        commands++;
        active = 0;
        terminal_seen = 1;
        $display("STAGE2_QUEUE_COMMAND seq=%0d depth=%0d enabled=%0d m=%0d n=%0d profile=%0d kb=%0d success=%0d fault=%0d enq=%0d deq=%0d fp_accept=%0d max_occ=%0d full=%0d decoupled=%0d start_overlap=%0d final_drain=%0d fault_drain=%0d start_blocked=%0d ctx0=%0d ctx1=%0d ctx2=%0d ctx3=%0d pending=%0d fp_full=%0d queue_full=%0d",
          seq, QueueDepth, enabled_i, m_i, n_i, profile_i, k_blocks_i, success_i, fault_i,
          pushes, pops, fp_accept, max_occ, full_cycles, decoupled, start_overlap,
          final_drain, fault_drain, start_blocked, blocked_context[0], blocked_context[1],
          blocked_context[2], blocked_context[3], blocked_pending, blocked_fp_full, blocked_queue_full);
      end
    end
  end
  final $display("STAGE2_QUEUE_DONE commands=%0d enq=%0d deq=%0d resets=%0d reset_flushed=%0d depth=%0d",
    commands, total_push, total_pop, resets, reset_flushed, QueueDepth);
endmodule
