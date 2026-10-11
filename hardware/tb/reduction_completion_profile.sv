// SPDX-License-Identifier: SHL-0.51
// Simulation-only observer, added explicitly to a profiling filelist. It has
// no drivers into the DUT and does not belong to the synthesis source list.
module reduction_completion_profile import ara_rce_pkg::*; #(
  parameter int ContextDepth = 2,
  parameter int NrLanes = 4
) (
  input logic clk_i, rst_ni,
  input logic [ContextDepth-1:0] valid_i,
  input rce_command_t [ContextDepth-1:0] context_i,
  input rce_command_t command_i,
  input logic command_valid_i, command_ready_i,
  input logic [NrLanes-1:0] partial_valid_i, partial_ready_i,
  input rce_result_t result_i,
  input logic result_valid_i, result_ready_i
);
  timeunit 1ns;
  timeprecision 1ps;
  bit enabled;
  longint unsigned occupied_cycles, two_context_cycles, heterogeneous_sew_cycles;
  longint unsigned command_stalls, partial_stall_cycles, result_stalls;
  longint unsigned commands, results;
  initial enabled = $test$plusargs("RCE_PROFILE");

  always @(posedge clk_i) begin
    if (!rst_ni) begin
      occupied_cycles = 0;
      two_context_cycles = 0;
      heterogeneous_sew_cycles = 0;
      command_stalls = 0;
      partial_stall_cycles = 0;
      result_stalls = 0;
      commands = 0;
      results = 0;
    end else if (enabled) begin
      automatic bit different_sew = 0;
      occupied_cycles += |valid_i;
      two_context_cycles += $countones(valid_i) >= 2;
      for (int a = 0; a < ContextDepth; a++)
        for (int b = a+1; b < ContextDepth; b++)
          different_sew |= valid_i[a] && valid_i[b] && context_i[a].eew != context_i[b].eew;
      heterogeneous_sew_cycles += different_sew;
      command_stalls += command_valid_i && !command_ready_i;
      partial_stall_cycles += |(partial_valid_i & ~partial_ready_i);
      result_stalls += result_valid_i && !result_ready_i;
      if (command_valid_i && command_ready_i) begin
        commands++;
        $display("[RCE_PROFILE] command t=%0t id=%0d op=%s eew=%0d seed_mode=%0d",
                 $time, command_i.id, command_i.op.name(), command_i.eew, command_i.seed_mode);
      end
      if (result_valid_i && result_ready_i) begin
        results++;
        $display("[RCE_PROFILE] retire t=%0t id=%0d data=%h flags=%h",
                 $time, result_i.id, result_i.data, result_i.fflags);
      end
      if (different_sew)
        for (int slot = 0; slot < ContextDepth; slot++)
          if (valid_i[slot])
            $display("[RCE_PROFILE] mixed_sew t=%0t slot=%0d id=%0d op=%s eew=%0d",
                     $time, slot, context_i[slot].id, context_i[slot].op.name(), context_i[slot].eew);
    end
  end

  final begin
    if (enabled)
      $display("[RCE_PROFILE] summary commands=%0d results=%0d occupied=%0d two_context=%0d mixed_sew=%0d cmd_stall=%0d partial_stall=%0d result_stall=%0d",
               commands, results, occupied_cycles, two_context_cycles, heterogeneous_sew_cycles,
               command_stalls, partial_stall_cycles, result_stalls);
  end
endmodule

bind reduction_completion_engine reduction_completion_profile #(
  .ContextDepth(ContextDepth), .NrLanes(NrLanes)
) i_completion_profile (
  .clk_i, .rst_ni, .valid_i(valid_q), .context_i(command_q), .command_i(cmd_i),
  .command_valid_i(cmd_valid_i), .command_ready_i(cmd_ready_o),
  .partial_valid_i, .partial_ready_i(partial_ready_o),
  .result_i(result_o), .result_valid_i(result_valid_o), .result_ready_i
);
