// Verification-only; requires cva6_state_prereq_sink from cva6_state_prereq_probe.sv.
// Uses its CVA6_STATE_PREREQ_FILE/ROWS options and independent 8192-row limits.
// Outputs <base>.trap_decode.log and <base>.trap_ctrl.log. No stimulus or force.
// Every payload is sampled pre-edge (#1step); sink adds one tail edge and reset rows.
// Ordinary fetch traffic and branch flushes alone do not activate these probes.
`ifndef SYNTHESIS

module trap_prereq_decode_probe #(
  parameter config_pkg::cva6_cfg_t CVA6Cfg = config_pkg::cva6_cfg_empty,
  parameter type fetch_entry_t = logic,
  parameter type scoreboard_entry_t = logic,
  parameter type issue_struct_t = logic,
  parameter type irq_ctrl_t = logic
) (
  input logic clk_i, rst_ni, flush_i,
  input fetch_entry_t [CVA6Cfg.NrIssuePorts-1:0] fetch_entry_i,
  input logic [CVA6Cfg.NrIssuePorts-1:0] fetch_entry_valid_i, fetch_entry_ready_o,
  input logic [CVA6Cfg.NrIssuePorts-1:0][31:0] instruction_rvc, instruction_deco,
  input logic [CVA6Cfg.NrIssuePorts-1:0] is_compressed_deco, is_illegal_deco,
  input logic [CVA6Cfg.NrIssuePorts-1:0] decoded_instruction_valid, stall_instr_fetch,
  input scoreboard_entry_t [CVA6Cfg.NrIssuePorts-1:0] decoded_instruction,
  input issue_struct_t [CVA6Cfg.NrIssuePorts-1:0] issue_q, issue_n,
  input scoreboard_entry_t [CVA6Cfg.NrIssuePorts-1:0] issue_entry_o,
  input logic [CVA6Cfg.NrIssuePorts-1:0] issue_entry_valid_o, issue_instr_ack_i,
  input logic [CVA6Cfg.NrIssuePorts-1:0][31:0] orig_instr_o,
  input riscv::priv_lvl_t priv_lvl_i,
  input logic v_i, debug_mode_i, debug_req_i, clic_mode_i, tvm_i, tw_i, tsr_i,
  input logic [1:0] irq_i,
  input irq_ctrl_t irq_ctrl_i
);
  timeunit 1ns;
  timeprecision 1ps;

  longint unsigned reset_epoch = 0;
  bit previous_valid = 0;
  irq_ctrl_t previous_irq_ctrl;
  riscv::priv_lvl_t previous_priv;
  logic [8:0] previous_controls;
  cva6_state_prereq_sink #(.Kind("trap_decode")) log_sink();

  always @(negedge rst_ni)
    if (rst_ni === 1'b0) reset_epoch++;

  clocking sample_cb @(posedge clk_i);
    default input #1step;
    input rst_ni;
    input epoch = reset_epoch;
    input flush_i, fetch_entry_i, fetch_entry_valid_i, fetch_entry_ready_o;
    input instruction_rvc, instruction_deco, is_compressed_deco, is_illegal_deco;
    input decoded_instruction_valid, stall_instr_fetch, decoded_instruction;
    input issue_q, issue_n, issue_entry_o, issue_entry_valid_o, issue_instr_ack_i;
    input orig_instr_o, priv_lvl_i, v_i, debug_mode_i, debug_req_i, clic_mode_i;
    input tvm_i, tw_i, tsr_i, irq_i, irq_ctrl_i;
  endclocking

  function automatic bit trap_related(input scoreboard_entry_t entry,
                                      input logic [31:0] original);
    return (entry.ex.valid !== 1'b0) ||
           (entry.op inside {ariane_pkg::CSR_WRITE, ariane_pkg::CSR_SET,
                             ariane_pkg::CSR_CLEAR, ariane_pkg::MRET,
                             ariane_pkg::SRET, ariane_pkg::DRET,
                             ariane_pkg::WFI, ariane_pkg::SFENCE_VMA}) ||
           ((original[6:0] == 7'h73) && (original[31:20] == 12'hfff));
  endfunction

  // SBE valid is result-ready, not a transport valid or a retirement event.
  function automatic string sbe_fields(input string prefix,
                                       input scoreboard_entry_t entry);
    return $sformatf({" %s_pc=%h %s_sbe_valid=%b %s_fu=%0d %s_op=%0d",
                      " %s_ex_valid=%b %s_ex_cause=%h %s_ex_tval=%h %s_ex=%h"},
                     prefix, entry.pc, prefix, entry.valid,
                     prefix, entry.fu, prefix, entry.op,
                     prefix, entry.ex.valid, prefix, entry.ex.cause,
                     prefix, entry.ex.tval, prefix, entry.ex);
  endfunction

  always @(sample_cb) begin : sample_decode
    bit active, control_changed, instruction_activity;
    logic [8:0] controls;
    scoreboard_entry_t q_sbe, n_sbe;
    string row, prefix;

    controls = {sample_cb.v_i, sample_cb.debug_mode_i, sample_cb.debug_req_i,
                sample_cb.clic_mode_i, sample_cb.tvm_i, sample_cb.tw_i,
                sample_cb.tsr_i, sample_cb.irq_i};
    control_changed = !previous_valid ||
                      (sample_cb.irq_ctrl_i !== previous_irq_ctrl) ||
                      (sample_cb.priv_lvl_i !== previous_priv) ||
                      (controls !== previous_controls);
    instruction_activity = 0;
    for (int i = 0; i < CVA6Cfg.NrIssuePorts; i++) begin
      // id_stage stores sbe as bits rather than a scoreboard_entry_t member.
      q_sbe = scoreboard_entry_t'(sample_cb.issue_q[i].sbe);
      n_sbe = scoreboard_entry_t'(sample_cb.issue_n[i].sbe);
      instruction_activity |=
        ((sample_cb.fetch_entry_valid_i[i] !== 1'b0) &&
         trap_related(sample_cb.decoded_instruction[i], sample_cb.fetch_entry_i[i].instruction)) ||
        ((sample_cb.issue_q[i].valid !== 1'b0) &&
         trap_related(q_sbe, sample_cb.issue_q[i].orig_instr)) ||
        ((sample_cb.issue_n[i].valid !== 1'b0) &&
         trap_related(n_sbe, sample_cb.issue_n[i].orig_instr));
    end
    active = (sample_cb.rst_ni === 1'b1) && (control_changed || instruction_activity);
    row = "";
    if (log_sink.rows < log_sink.row_limit &&
        log_sink.wants_row(active, sample_cb.rst_ni, sample_cb.epoch)) begin
      row = $sformatf({"schema=1 issue_ports=%0d ctrl_changed=%b instr_activity=%b",
                       " flush=%b priv=%b virt=%b debug_mode=%b debug_req=%b",
                       " clic_mode=%b tvm=%b tw=%b tsr=%b irq_pins=%b irq_ctrl=%h",
                       " irq_mie=%h irq_mip=%h irq_mideleg=%h irq_sie=%b irq_global=%b"},
                      CVA6Cfg.NrIssuePorts, control_changed, instruction_activity,
                      sample_cb.flush_i, sample_cb.priv_lvl_i, sample_cb.v_i,
                      sample_cb.debug_mode_i, sample_cb.debug_req_i, sample_cb.clic_mode_i,
                      sample_cb.tvm_i, sample_cb.tw_i, sample_cb.tsr_i, sample_cb.irq_i,
                      sample_cb.irq_ctrl_i, sample_cb.irq_ctrl_i.mie,
                      sample_cb.irq_ctrl_i.mip, sample_cb.irq_ctrl_i.mideleg,
                      sample_cb.irq_ctrl_i.sie, sample_cb.irq_ctrl_i.global_enable);
      for (int i = 0; i < CVA6Cfg.NrIssuePorts; i++) begin
        prefix = $sformatf("p%0d", i);
        q_sbe = scoreboard_entry_t'(sample_cb.issue_q[i].sbe);
        n_sbe = scoreboard_entry_t'(sample_cb.issue_n[i].sbe);
        row = {row, $sformatf({" %s_fetch_valid=%b %s_fetch_ready=%b %s_fetch_fire=%b",
                               " %s_fetch_pc=%h %s_fetch_instr=%h %s_fetch_ex_valid=%b",
                               " %s_fetch_ex_cause=%h %s_fetch_ex_tval=%h %s_fetch_ex=%h",
                               " %s_rvc_instr=%h %s_decode_instr=%h %s_compressed=%b",
                               " %s_illegal=%b %s_decoded_valid=%b %s_fetch_stall=%b"},
                              prefix, sample_cb.fetch_entry_valid_i[i],
                              prefix, sample_cb.fetch_entry_ready_o[i],
                              prefix, sample_cb.fetch_entry_valid_i[i] && sample_cb.fetch_entry_ready_o[i],
                              prefix, sample_cb.fetch_entry_i[i].address,
                              prefix, sample_cb.fetch_entry_i[i].instruction,
                              prefix, sample_cb.fetch_entry_i[i].ex.valid,
                              prefix, sample_cb.fetch_entry_i[i].ex.cause,
                              prefix, sample_cb.fetch_entry_i[i].ex.tval,
                              prefix, sample_cb.fetch_entry_i[i].ex,
                              prefix, sample_cb.instruction_rvc[i],
                              prefix, sample_cb.instruction_deco[i],
                              prefix, sample_cb.is_compressed_deco[i],
                              prefix, sample_cb.is_illegal_deco[i],
                              prefix, sample_cb.decoded_instruction_valid[i],
                              prefix, sample_cb.stall_instr_fetch[i]),
                    sbe_fields({prefix, "_dec"}, sample_cb.decoded_instruction[i]),
                    $sformatf({" %s_q_valid=%b %s_n_valid=%b %s_q_orig=%h %s_n_orig=%h",
                               " %s_out_valid=%b %s_out_ack=%b %s_out_fire=%b %s_out_orig=%h"},
                              prefix, sample_cb.issue_q[i].valid,
                              prefix, sample_cb.issue_n[i].valid,
                              prefix, sample_cb.issue_q[i].orig_instr,
                              prefix, sample_cb.issue_n[i].orig_instr,
                              prefix, sample_cb.issue_entry_valid_o[i],
                              prefix, sample_cb.issue_instr_ack_i[i],
                              prefix, sample_cb.issue_entry_valid_o[i] && sample_cb.issue_instr_ack_i[i],
                              prefix, sample_cb.orig_instr_o[i]),
                    sbe_fields({prefix, "_q"}, q_sbe),
                    sbe_fields({prefix, "_n"}, n_sbe),
                    sbe_fields({prefix, "_out"}, sample_cb.issue_entry_o[i])};
      end
    end
    log_sink.record(active, sample_cb.rst_ni, sample_cb.epoch, $realtime, row);
    previous_valid = sample_cb.rst_ni === 1'b1;
    previous_irq_ctrl = sample_cb.irq_ctrl_i;
    previous_priv = sample_cb.priv_lvl_i;
    previous_controls = controls;
  end
endmodule

module trap_prereq_ctrl_probe #(
  parameter config_pkg::cva6_cfg_t CVA6Cfg = config_pkg::cva6_cfg_empty,
  parameter type exception_t = logic,
  parameter type scoreboard_entry_t = logic,
  parameter type irq_ctrl_t = logic,
  parameter type satp_t = logic
) (
  input logic clk_i, rst_ni,
  input exception_t ex_i, csr_exception_o,
  input logic [CVA6Cfg.VLEN-1:0] pc_i, epc_o, trap_vector_base_o,
  input scoreboard_entry_t commit_instr_i,
  input logic [CVA6Cfg.NrCommitPorts-1:0] commit_ack_i,
  input riscv::priv_lvl_t priv_lvl_q, priv_lvl_d, priv_lvl_o, trap_to_priv_lvl,
  input riscv::mstatus_rv_t mstatus_q, mstatus_d,
  input logic [CVA6Cfg.XLEN-1:0] mie_q, mie_d, mip_q, mip_d,
  input logic [CVA6Cfg.XLEN-1:0] medeleg_q, medeleg_d, mideleg_q, mideleg_d,
  input logic [CVA6Cfg.XLEN-1:0] mtvec_q, mtvec_d, stvec_q, stvec_d,
  input logic [CVA6Cfg.XLEN-1:0] mepc_q, mepc_d, sepc_q, sepc_d,
  input logic [CVA6Cfg.XLEN-1:0] mcause_q, mcause_d, scause_q, scause_d,
  input logic [CVA6Cfg.XLEN-1:0] mtval_q, mtval_d, stval_q, stval_d,
  input logic [CVA6Cfg.XLEN-1:0] mscratch_q, mscratch_d, sscratch_q, sscratch_d,
  input satp_t satp_q, satp_d,
  input ariane_pkg::fu_op csr_op_i,
  input logic [11:0] csr_addr_i, conv_addr,
  input logic csr_we, csr_read,
  input logic [CVA6Cfg.XLEN-1:0] csr_wdata_i, csr_wdata, csr_rdata, csr_rdata_o,
  input logic read_access_exception, update_access_exception, privilege_violation,
  input logic eret_o, flush_o, mret, sret, dret, v_o,
  input logic debug_mode_q, debug_mode_d, debug_req_i, set_debug_pc_o, clic_mode_o,
  input riscv::dcsr_t dcsr_q, dcsr_d,
  input logic [1:0] irq_i,
  input logic ipi_i, time_irq_i,
  input irq_ctrl_t irq_ctrl_o
);
  timeunit 1ns;
  timeprecision 1ps;

  longint unsigned reset_epoch = 0;
  cva6_state_prereq_sink #(.Kind("trap_ctrl")) log_sink();
  always @(negedge rst_ni)
    if (rst_ni === 1'b0) reset_epoch++;

  clocking sample_cb @(posedge clk_i);
    default input #1step;
    input rst_ni;
    input epoch = reset_epoch;
    input ex_i, csr_exception_o, pc_i, epc_o, trap_vector_base_o;
    input commit_instr_i, commit_ack_i, priv_lvl_q, priv_lvl_d, priv_lvl_o, trap_to_priv_lvl;
    input mstatus_q, mstatus_d, mie_q, mie_d, mip_q, mip_d;
    input medeleg_q, medeleg_d, mideleg_q, mideleg_d;
    input mtvec_q, mtvec_d, stvec_q, stvec_d, mepc_q, mepc_d, sepc_q, sepc_d;
    input mcause_q, mcause_d, scause_q, scause_d, mtval_q, mtval_d, stval_q, stval_d;
    input mscratch_q, mscratch_d, sscratch_q, sscratch_d, satp_q, satp_d;
    input csr_op_i, csr_addr_i, conv_addr, csr_we, csr_read;
    input csr_wdata_i, csr_wdata, csr_rdata, csr_rdata_o;
    input read_access_exception, update_access_exception, privilege_violation;
    input eret_o, flush_o, mret, sret, dret, v_o;
    input debug_mode_q, debug_mode_d, debug_req_i, set_debug_pc_o, clic_mode_o;
    input dcsr_q, dcsr_d, irq_i, ipi_i, time_irq_i, irq_ctrl_o;
  endclocking

  always @(sample_cb) begin : sample_ctrl
    bit active, state_changed;
    string row;
    state_changed =
      ({sample_cb.priv_lvl_q, sample_cb.mstatus_q, sample_cb.mie_q, sample_cb.mip_q,
        sample_cb.medeleg_q, sample_cb.mideleg_q, sample_cb.mtvec_q, sample_cb.stvec_q,
        sample_cb.mepc_q, sample_cb.sepc_q, sample_cb.mcause_q, sample_cb.scause_q,
        sample_cb.mtval_q, sample_cb.stval_q, sample_cb.mscratch_q, sample_cb.sscratch_q,
        sample_cb.satp_q, sample_cb.debug_mode_q, sample_cb.dcsr_q} !==
       {sample_cb.priv_lvl_d, sample_cb.mstatus_d, sample_cb.mie_d, sample_cb.mip_d,
        sample_cb.medeleg_d, sample_cb.mideleg_d, sample_cb.mtvec_d, sample_cb.stvec_d,
        sample_cb.mepc_d, sample_cb.sepc_d, sample_cb.mcause_d, sample_cb.scause_d,
        sample_cb.mtval_d, sample_cb.stval_d, sample_cb.mscratch_d, sample_cb.sscratch_d,
        sample_cb.satp_d, sample_cb.debug_mode_d, sample_cb.dcsr_d});
    active = (sample_cb.rst_ni === 1'b1) &&
      (state_changed ||
       ({sample_cb.ex_i.valid, sample_cb.csr_exception_o.valid, sample_cb.csr_we,
         sample_cb.read_access_exception, sample_cb.update_access_exception,
         sample_cb.privilege_violation, sample_cb.eret_o, sample_cb.flush_o,
         sample_cb.set_debug_pc_o} !== '0));
    row = "";
    if (log_sink.rows < log_sink.row_limit &&
        log_sink.wants_row(active, sample_cb.rst_ni, sample_cb.epoch)) begin
      row = $sformatf({"schema=1 xlen=%0d gplen=%0d tval_en=%b zero_tval=%b",
                       " rvs=%b rvu=%b rvh=%b rvc=%b debug_en=%b state_changed=%b",
                       " pc=%h ex_valid=%b ex_cause=%h ex_tval=%h ex=%h",
                       " cause_xlen_msb=%b cause_gplen_msb=%b",
                       " priv_q=%b priv_d=%b priv_out=%b trap_to_priv=%b virt=%b",
                       " epc=%h trap_vector=%h eret=%b flush=%b mret=%b sret=%b dret=%b"},
                      CVA6Cfg.XLEN, CVA6Cfg.GPLEN, CVA6Cfg.TvalEn, ariane_pkg::ZERO_TVAL,
                      CVA6Cfg.RVS, CVA6Cfg.RVU, CVA6Cfg.RVH, CVA6Cfg.RVC, CVA6Cfg.DebugEn,
                      state_changed, sample_cb.pc_i, sample_cb.ex_i.valid,
                      sample_cb.ex_i.cause, sample_cb.ex_i.tval, sample_cb.ex_i,
                      sample_cb.ex_i.cause[CVA6Cfg.XLEN-1],
                      sample_cb.ex_i.cause[CVA6Cfg.GPLEN-1],
                      sample_cb.priv_lvl_q, sample_cb.priv_lvl_d, sample_cb.priv_lvl_o,
                      sample_cb.trap_to_priv_lvl, sample_cb.v_o, sample_cb.epc_o,
                      sample_cb.trap_vector_base_o, sample_cb.eret_o, sample_cb.flush_o,
                      sample_cb.mret, sample_cb.sret, sample_cb.dret);
      row = {row, $sformatf({" mstatus_q=%h mstatus_d=%h mie_q=%h mie_d=%h mip_q=%h mip_d=%h",
                             " medeleg_q=%h medeleg_d=%h mideleg_q=%h mideleg_d=%h",
                             " mtvec_q=%h mtvec_d=%h stvec_q=%h stvec_d=%h",
                             " mepc_q=%h mepc_d=%h sepc_q=%h sepc_d=%h",
                             " mcause_q=%h mcause_d=%h scause_q=%h scause_d=%h",
                             " mtval_q=%h mtval_d=%h stval_q=%h stval_d=%h",
                             " mscratch_q=%h mscratch_d=%h sscratch_q=%h sscratch_d=%h",
                             " satp_q=%h satp_d=%h"},
                            sample_cb.mstatus_q, sample_cb.mstatus_d,
                            sample_cb.mie_q, sample_cb.mie_d, sample_cb.mip_q, sample_cb.mip_d,
                            sample_cb.medeleg_q, sample_cb.medeleg_d,
                            sample_cb.mideleg_q, sample_cb.mideleg_d,
                            sample_cb.mtvec_q, sample_cb.mtvec_d, sample_cb.stvec_q, sample_cb.stvec_d,
                            sample_cb.mepc_q, sample_cb.mepc_d, sample_cb.sepc_q, sample_cb.sepc_d,
                            sample_cb.mcause_q, sample_cb.mcause_d, sample_cb.scause_q, sample_cb.scause_d,
                            sample_cb.mtval_q, sample_cb.mtval_d, sample_cb.stval_q, sample_cb.stval_d,
                            sample_cb.mscratch_q, sample_cb.mscratch_d,
                            sample_cb.sscratch_q, sample_cb.sscratch_d, sample_cb.satp_q, sample_cb.satp_d)};
      row = {row, $sformatf({" csr_op=%0d csr_addr=%h conv_addr=%h csr_we=%b csr_read=%b",
                             " csr_wdata_in=%h csr_wdata=%h csr_rdata=%h csr_rdata_out=%h",
                             " read_fault=%b write_fault=%b priv_fault=%b",
                             " csr_ex_valid=%b csr_ex_cause=%h csr_ex_tval=%h csr_ex=%h",
                             " commit0_pc=%h commit0_id=%h commit0_fu=%0d commit0_op=%0d",
                             " commit0_sbe_valid=%b commit0_ex_valid=%b commit0_ex_cause=%h",
                             " commit0_ex_tval=%h commit0_ex=%h ack=%b"},
                            sample_cb.csr_op_i, sample_cb.csr_addr_i, sample_cb.conv_addr,
                            sample_cb.csr_we, sample_cb.csr_read,
                            sample_cb.csr_wdata_i, sample_cb.csr_wdata,
                            sample_cb.csr_rdata, sample_cb.csr_rdata_o,
                            sample_cb.read_access_exception, sample_cb.update_access_exception,
                            sample_cb.privilege_violation, sample_cb.csr_exception_o.valid,
                            sample_cb.csr_exception_o.cause, sample_cb.csr_exception_o.tval,
                            sample_cb.csr_exception_o, sample_cb.commit_instr_i.pc,
                            sample_cb.commit_instr_i.trans_id, sample_cb.commit_instr_i.fu,
                            sample_cb.commit_instr_i.op, sample_cb.commit_instr_i.valid,
                            sample_cb.commit_instr_i.ex.valid, sample_cb.commit_instr_i.ex.cause,
                            sample_cb.commit_instr_i.ex.tval, sample_cb.commit_instr_i.ex,
                            sample_cb.commit_ack_i)};
      row = {row, $sformatf({" irq_ctrl=%h irq_sie=%b irq_global=%b irq_pins=%b ipi=%b time_irq=%b",
                             " debug_q=%b debug_d=%b debug_req=%b set_debug_pc=%b",
                             " dcsr_q=%h dcsr_d=%h clic_mode=%b"},
                            sample_cb.irq_ctrl_o, sample_cb.irq_ctrl_o.sie,
                            sample_cb.irq_ctrl_o.global_enable, sample_cb.irq_i,
                            sample_cb.ipi_i, sample_cb.time_irq_i,
                            sample_cb.debug_mode_q, sample_cb.debug_mode_d, sample_cb.debug_req_i,
                            sample_cb.set_debug_pc_o, sample_cb.dcsr_q, sample_cb.dcsr_d,
                            sample_cb.clic_mode_o)};
    end
    log_sink.record(active, sample_cb.rst_ni, sample_cb.epoch, $realtime, row);
  end
endmodule

bind id_stage trap_prereq_decode_probe #(
  .CVA6Cfg(CVA6Cfg), .fetch_entry_t(fetch_entry_t),
  .scoreboard_entry_t(scoreboard_entry_t), .issue_struct_t(issue_struct_t), .irq_ctrl_t(irq_ctrl_t)
) i_trap_prereq_decode_probe (
  .clk_i(clk_i), .rst_ni(rst_ni), .flush_i(flush_i),
  .fetch_entry_i(fetch_entry_i), .fetch_entry_valid_i(fetch_entry_valid_i),
  .fetch_entry_ready_o(fetch_entry_ready_o), .instruction_rvc(instruction_rvc),
  .instruction_deco(instruction_deco), .is_compressed_deco(is_compressed_deco),
  .is_illegal_deco(is_illegal_deco), .decoded_instruction_valid(decoded_instruction_valid),
  .stall_instr_fetch(stall_instr_fetch), .decoded_instruction(decoded_instruction),
  .issue_q(issue_q), .issue_n(issue_n), .issue_entry_o(issue_entry_o),
  .issue_entry_valid_o(issue_entry_valid_o), .issue_instr_ack_i(issue_instr_ack_i),
  .orig_instr_o(orig_instr_o), .priv_lvl_i(priv_lvl_i), .v_i(v_i),
  .debug_mode_i(debug_mode_i), .debug_req_i(debug_req_i), .clic_mode_i(clic_mode_i),
  .tvm_i(tvm_i), .tw_i(tw_i), .tsr_i(tsr_i), .irq_i(irq_i), .irq_ctrl_i(irq_ctrl_i)
);

bind csr_regfile trap_prereq_ctrl_probe #(
  .CVA6Cfg(CVA6Cfg), .exception_t(exception_t), .scoreboard_entry_t(scoreboard_entry_t),
  .irq_ctrl_t(irq_ctrl_t), .satp_t(satp_t)
) i_trap_prereq_ctrl_probe (
  .clk_i(clk_i), .rst_ni(rst_ni), .ex_i(ex_i), .csr_exception_o(csr_exception_o),
  .pc_i(pc_i), .epc_o(epc_o), .trap_vector_base_o(trap_vector_base_o),
  .commit_instr_i(commit_instr_i), .commit_ack_i(commit_ack_i),
  .priv_lvl_q(priv_lvl_q), .priv_lvl_d(priv_lvl_d), .priv_lvl_o(priv_lvl_o),
  .trap_to_priv_lvl(trap_to_priv_lvl), .mstatus_q(mstatus_q), .mstatus_d(mstatus_d),
  .mie_q(mie_q), .mie_d(mie_d), .mip_q(mip_q), .mip_d(mip_d),
  .medeleg_q(medeleg_q), .medeleg_d(medeleg_d), .mideleg_q(mideleg_q), .mideleg_d(mideleg_d),
  .mtvec_q(mtvec_q), .mtvec_d(mtvec_d), .stvec_q(stvec_q), .stvec_d(stvec_d),
  .mepc_q(mepc_q), .mepc_d(mepc_d), .sepc_q(sepc_q), .sepc_d(sepc_d),
  .mcause_q(mcause_q), .mcause_d(mcause_d), .scause_q(scause_q), .scause_d(scause_d),
  .mtval_q(mtval_q), .mtval_d(mtval_d), .stval_q(stval_q), .stval_d(stval_d),
  .mscratch_q(mscratch_q), .mscratch_d(mscratch_d), .sscratch_q(sscratch_q), .sscratch_d(sscratch_d),
  .satp_q(satp_q), .satp_d(satp_d), .csr_op_i(csr_op_i), .csr_addr_i(csr_addr_i),
  .conv_addr(conv_csr_addr.address), .csr_we(csr_we), .csr_read(csr_read),
  .csr_wdata_i(csr_wdata_i), .csr_wdata(csr_wdata), .csr_rdata(csr_rdata), .csr_rdata_o(csr_rdata_o),
  .read_access_exception(read_access_exception), .update_access_exception(update_access_exception),
  .privilege_violation(privilege_violation), .eret_o(eret_o), .flush_o(flush_o),
  .mret(mret), .sret(sret), .dret(dret), .v_o(v_o),
  .debug_mode_q(debug_mode_q), .debug_mode_d(debug_mode_d), .debug_req_i(debug_req_i),
  .set_debug_pc_o(set_debug_pc_o), .clic_mode_o(clic_mode_o), .dcsr_q(dcsr_q), .dcsr_d(dcsr_d),
  .irq_i(irq_i), .ipi_i(ipi_i), .time_irq_i(time_irq_i), .irq_ctrl_o(irq_ctrl_o)
);

`endif
