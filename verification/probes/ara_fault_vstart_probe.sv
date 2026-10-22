// Simulation-only bind. Enable with +ARA_FAULT_VSTART_PROBE.
// RESP samples pre-NBA q/d. NEXT at the following posedge samples the q
// produced by that RESP edge, before the following edge's NBA updates.
// req_insn/current_insn are frontend signals, not an inferred faulting PC.
// Backend exception_vstart is meaningful only with its printed valid bits.
module ara_fault_vstart_probe #(
  parameter int unsigned CsrWidth = 1,
  parameter int unsigned BackendVstartWidth = 1,
  parameter int unsigned InsnWidth = 32,
  parameter int unsigned TransIdWidth = 1,
  parameter int unsigned CauseWidth = 1,
  parameter int unsigned TvalWidth = 1
) (
  input logic                          clk_i,
  input logic                          rst_ni,
  input logic                          req_valid_i,
  input logic                          req_ready_i,
  input logic [InsnWidth-1:0]          req_insn_i,
  input logic [InsnWidth-1:0]          current_insn_i,
  input logic [63:0]                   arch_seq_i,
  input logic [TransIdWidth-1:0]       req_trans_id_i,
  input logic                          resp_valid_i,
  input logic                          resp_ready_i,
  input logic [TransIdWidth-1:0]       resp_trans_id_i,
  input logic                          exception_valid_i,
  input logic [CauseWidth-1:0]         cause_i,
  input logic [TvalWidth-1:0]          tval_i,
  input logic                          backend_valid_i,
  input logic                          backend_exception_valid_i,
  input logic [BackendVstartWidth-1:0] exception_vstart_i,
  input logic [CsrWidth-1:0]           csr_vstart_q_i,
  input logic [CsrWidth-1:0]           csr_vstart_d_i
);
  bit enabled;
  bit pending;
  longint unsigned cycle;
  longint unsigned event_id;
  longint unsigned pending_cycle;
  longint unsigned pending_event_id;
  logic [TransIdWidth-1:0] pending_trans_id;
  logic [CsrWidth-1:0] pending_d;

  initial begin
    enabled = $test$plusargs("ARA_FAULT_VSTART_PROBE");
    pending = 1'b0;
    cycle = 0;
    event_id = 0;
    pending_cycle = 0;
    pending_event_id = 0;
    pending_trans_id = '0;
    pending_d = '0;
  end

  // Blocking assignments are local probe bookkeeping only. No DUT drives,
  // delays, assertions or simulation termination are introduced.
  always @(posedge clk_i) begin
    if (enabled) begin
      cycle = cycle + 1;
      if (pending) begin
        $display("[ARA_FAULT_VSTART] phase=NEXT inst=%m cycle=%0d time=%0t event=%0d resp_cycle=%0d trans_id=%0h rst_n=%b expected_d=%0h actual_q=%0h match=%b",
                 cycle, $time, pending_event_id, pending_cycle,
                 pending_trans_id, rst_ni, pending_d, csr_vstart_q_i,
                 csr_vstart_q_i == pending_d);
      end
      pending = 1'b0;
      if (rst_ni && resp_valid_i && exception_valid_i) begin
        event_id = event_id + 1;
        $display("[ARA_FAULT_VSTART] phase=RESP inst=%m cycle=%0d time=%0t event=%0d arch_seq=%0d req_valid=%b req_ready=%b req_insn=%h current_insn=%h req_trans_id=%0h trans_id=%0h resp_valid=%b resp_ready=%b fire=%b cause=%0h tval=%0h backend_valid=%b backend_exception=%b exception_vstart=%0h csr_vstart_q=%0h csr_vstart_d=%0h",
                 cycle, $time, event_id, arch_seq_i, req_valid_i, req_ready_i,
                 req_insn_i, current_insn_i, req_trans_id_i, resp_trans_id_i,
                 resp_valid_i, resp_ready_i, resp_valid_i && resp_ready_i,
                 cause_i, tval_i, backend_valid_i, backend_exception_valid_i,
                 exception_vstart_i, csr_vstart_q_i, csr_vstart_d_i);
        pending = 1'b1;
        pending_cycle = cycle;
        pending_event_id = event_id;
        pending_trans_id = resp_trans_id_i;
        pending_d = csr_vstart_d_i;
      end
    end
  end

  final begin
    if (enabled && pending)
      $display("[ARA_FAULT_VSTART] phase=END_PENDING inst=%m event=%0d resp_cycle=%0d trans_id=%0h next_q_observed=0",
               pending_event_id, pending_cycle, pending_trans_id);
  end
endmodule

bind ara_dispatcher ara_fault_vstart_probe #(
  .CsrWidth($bits(csr_vstart_q)),
  .BackendVstartWidth($bits(ara_resp.exception_vstart)),
  .InsnWidth($bits(acc_req_i.insn)),
  .TransIdWidth($bits(acc_resp_o.trans_id)),
  .CauseWidth($bits(acc_resp_o.exception.cause)),
  .TvalWidth($bits(acc_resp_o.exception.tval))
) i_ara_fault_vstart_probe (
  .clk_i(clk_i),
  .rst_ni(rst_ni),
  .req_valid_i(acc_req_i.req_valid),
  .req_ready_i(acc_resp_o.req_ready),
  .req_insn_i(acc_req_i.insn),
  .current_insn_i(verify_active_insn_q),
  .arch_seq_i(verify_active_arch_seq_q),
  .req_trans_id_i(acc_req_i.trans_id),
  .resp_valid_i(acc_resp_o.resp_valid),
  .resp_ready_i(acc_req_i.resp_ready),
  .resp_trans_id_i(acc_resp_o.trans_id),
  .exception_valid_i(acc_resp_o.exception.valid),
  .cause_i(acc_resp_o.exception.cause),
  .tval_i(acc_resp_o.exception.tval),
  .backend_valid_i(ara_resp_valid),
  .backend_exception_valid_i(ara_resp.exception.valid),
  .exception_vstart_i(ara_resp.exception_vstart),
  .csr_vstart_q_i(csr_vstart_q),
  .csr_vstart_d_i(csr_vstart_d)
);
