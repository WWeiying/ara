// Verification-only: include through CLI extra_sources, not normal RTL targets.
// +CVA6_ACC_LIFECYCLE_CYCLES=<1..65536> lowers the default capture length.
// +CVA6_ACC_LIFECYCLE_FILE=<basename> changes the cwd-local output basename.
// Existing files are preserved by selecting basename.1, basename.2, etc.
`ifndef SYNTHESIS
module cva6_acc_lifecycle_probe #(
  parameter config_pkg::cva6_cfg_t CVA6Cfg = config_pkg::cva6_cfg_empty,
  parameter type fu_data_t = logic,
  parameter type scoreboard_entry_t = logic,
  parameter type accelerator_req_t = logic,
  parameter type acc_req_t = logic,
  parameter type acc_resp_t = logic,
  parameter int unsigned QueueUsageWidth = 2
) (
  input logic clk_i,
  input logic rst_ni,
  input scoreboard_entry_t issue_instr_i,
  input logic issue_instr_hs_i,
  input logic issue_stall_o,
  input fu_data_t fu_data_i,
  input logic acc_valid_d,
  input logic acc_valid_q,
  input logic acc_ready,
  input logic acc_insn_queue_pop,
  input logic acc_insn_queue_empty,
  input logic [QueueUsageWidth-1:0] acc_insn_queue_usage,
  input fu_data_t acc_insn_queue_o,
  input scoreboard_entry_t [CVA6Cfg.NrCommitPorts-1:0] commit_instr_i,
  input logic [CVA6Cfg.NrCommitPorts-1:0] commit_ack_i,
  input logic acc_commit,
  input logic [CVA6Cfg.TRANS_ID_BITS-1:0] acc_commit_trans_id,
  input logic [CVA6Cfg.NR_SB_ENTRIES-1:0] insn_pending_q,
  input logic [CVA6Cfg.NR_SB_ENTRIES-1:0] insn_pending_d,
  input logic [CVA6Cfg.NR_SB_ENTRIES-1:0] insn_ready_q,
  input logic [CVA6Cfg.NR_SB_ENTRIES-1:0] insn_ready_d,
  input logic flush_unissued_instr_i,
  input logic flush_ex_i,
  input logic flush_pipeline_o,
  input accelerator_req_t acc_req,
  input logic acc_req_valid,
  input logic acc_req_ready,
  input accelerator_req_t acc_req_int,
  input acc_req_t acc_req_o,
  input acc_resp_t acc_resp_i,
  input logic [2:0] acc_spec_loads_pending,
  input logic [2:0] acc_disp_loads_pending,
  input logic [2:0] acc_spec_stores_pending,
  input logic [2:0] acc_disp_stores_pending,
  input logic acc_spec_loads_overflow,
  input logic acc_disp_loads_overflow,
  input logic acc_spec_stores_overflow,
  input logic acc_disp_stores_overflow,
  input logic acc_ld_disp,
  input logic acc_st_disp,
  input logic acc_no_ld_pending,
  input logic acc_no_st_pending,
  input logic acc_no_st_pending_i,
  input logic acc_cons_en_i,
  input logic commit_st_barrier_i,
  input logic wait_acc_store_q,
  input logic wait_acc_store_d,
  input logic ctrl_halt_o
);
  timeunit 1ns;
  timeprecision 1ps;

  localparam int MaxRows = 65536;
  int row_limit = MaxRows;
  int unsigned row_count = 0;
  longint unsigned cycle_count = 0;
  longint unsigned reset_epoch = 0;
  bit triggered = 0;
  bit truncated = 0;
  int log_fd = 0;
  string log_base = "acc_lifecycle.log";
  string log_path;

  // Count observed asynchronous assertions, including pulses between clocks.
  // Epoch zero is the initial interval; cycle numbering never restarts.
  always @(negedge rst_ni) begin
    if (rst_ni === 1'b0) reset_epoch = reset_epoch + 1;
  end

  // All row data, including derived fires, comes from this single snapshot.
  // No post-NBA state or live combinational signal is mixed into a row.
  clocking sample_cb @(posedge clk_i);
    default input #1step;
    input rst_ni;
    input epoch = reset_epoch;
    input issue_instr_i, issue_instr_hs_i, issue_stall_o, fu_data_i;
    input acc_valid_d, acc_valid_q, acc_ready;
    input acc_insn_queue_pop, acc_insn_queue_empty, acc_insn_queue_usage;
    input acc_insn_queue_o;
    input commit_instr_i, commit_ack_i, acc_commit, acc_commit_trans_id;
    input insn_pending_q, insn_pending_d, insn_ready_q, insn_ready_d;
    input flush_unissued_instr_i, flush_ex_i, flush_pipeline_o;
    input acc_req, acc_req_valid, acc_req_ready, acc_req_int;
    input acc_req_o, acc_resp_i;
    input acc_spec_loads_pending, acc_disp_loads_pending;
    input acc_spec_stores_pending, acc_disp_stores_pending;
    input acc_spec_loads_overflow, acc_disp_loads_overflow;
    input acc_spec_stores_overflow, acc_disp_stores_overflow;
    input acc_ld_disp, acc_st_disp, acc_no_ld_pending, acc_no_st_pending;
    input acc_no_st_pending_i, acc_cons_en_i, commit_st_barrier_i;
    input wait_acc_store_q, wait_acc_store_d, ctrl_halt_o;
  endclocking

  initial begin : open_log
    int existing_fd;
    int unsigned suffix;
    void'($value$plusargs("CVA6_ACC_LIFECYCLE_CYCLES=%d", row_limit));
    void'($value$plusargs("CVA6_ACC_LIFECYCLE_FILE=%s", log_base));
    if (row_limit < 1 || row_limit > MaxRows)
      $fatal(1, "[CVA6_ACC_LIFECYCLE] CYCLES must be in 1..%0d", MaxRows);
    if (log_base.len() == 0 || log_base == "." || log_base == "..")
      $fatal(1, "[CVA6_ACC_LIFECYCLE] FILE must be a cwd-local basename");
    for (int i = 0; i < log_base.len(); i++) begin
      if (log_base.getc(i) == 8'h2f || log_base.getc(i) == 8'h5c)
        $fatal(1, "[CVA6_ACC_LIFECYCLE] FILE must not contain a path separator");
    end
    suffix = 0;
    log_path = log_base;
    existing_fd = $fopen(log_path, "r");
    while (existing_fd != 0) begin
      $fclose(existing_fd);
      suffix = suffix + 1;
      log_path = $sformatf("%s.%0d", log_base, suffix);
      existing_fd = $fopen(log_path, "r");
    end
    log_fd = $fopen(log_path, "a");
    if (log_fd == 0)
      $fatal(1, "[CVA6_ACC_LIFECYCLE] cannot open %s", log_path);
    $display("[CVA6_ACC_LIFECYCLE] instance=%m file=%s max_rows=%0d",
             log_path, row_limit);
    $fwrite(log_fd, "# CVA6_ACC_LIFECYCLE version=1 instance=%m\n");
    $fwrite(log_fd, {"# sample=pre_edge input_skew=1step edge_time_unit=ns",
                    " trigger=first_rst_ni_and_acc_valid_d max_rows=%0d\n"}, row_limit);
    $fwrite(log_fd, {"# xlen=%0d pc_bits=%0d id_bits=%0d sb_entries=%0d",
                    " commit_ports=%0d queue_usage_bits=%0d\n"},
            CVA6Cfg.XLEN, CVA6Cfg.VLEN, CVA6Cfg.TRANS_ID_BITS,
            CVA6Cfg.NR_SB_ENTRIES, CVA6Cfg.NrCommitPorts, QueueUsageWidth);
    $fwrite(log_fd, "# cycle is zero-based and never resets; epoch counts observed async reset assertions.\n");
    $fwrite(log_fd, "# One lifetime window includes the trigger row and reset cycles; no rearming after reset.\n");
    $fwrite(log_fd, "# IDs are reused: correlate epoch/cycle/PC/payload and handshakes, never ID alone.\n");
    $fwrite(log_fd, "# issue_sbe_valid and commitN_valid mean result-valid, not instruction-present.\n");
    $fwrite(log_fd, "# fu_* is registered issue data qualified by acc_valid_q, NOT the current issue_pc.\n");
    $fwrite(log_fd, "# queue_push/pop are raw controls; reset/flush can override them. Usage excludes fall-through.\n");
    $fwrite(log_fd, "# Queue head is qualified by !queue_empty; other payloads by their respective valid.\n");
    $fwrite(log_fd, "# acc_commit is non-speculative authorization, not retirement; commitN_ack is retirement.\n");
    $fwrite(log_fd, "# spill_in_fire/queue_pop, spill_out_fire, resp_fire and memory_complete are distinct events.\n");
    $fwrite(log_fd, "# Fires are raw sampled valid&&ready, not reset-qualified; inspect rst_n and flush flags.\n");
    $fwrite(log_fd, "# Spill payload is insn/rs1/rs2/frm/id; live sidebands are logged separately.\n");
    $fwrite(log_fd, "# FU/op are numeric enums; ex fields are packed hex structs; unknown bits are retained.\n");
    $fwrite(log_fd, "# Pending counts are raw 3-bit values; overflow bits are separate, not sticky errors.\n");
    $fflush(log_fd);
  end

  always @(sample_cb) begin : log_cycle
    if (!triggered && sample_cb.rst_ni === 1'b1 && sample_cb.acc_valid_d === 1'b1) begin
      triggered = 1;
      $fwrite(log_fd, "# TRIGGER cycle=%0d epoch=%0d edge_time_ns=%0.3f\n",
              cycle_count, sample_cb.epoch, $realtime);
    end
    if (triggered && !truncated) begin
      $fwrite(log_fd, "cycle=%0d epoch=%0d edge_time_ns=%0.3f row=%0d rst_n=%b",
              cycle_count, sample_cb.epoch, $realtime, row_count, sample_cb.rst_ni);
      $fwrite(log_fd, {" issue_pc=%h issue_id=%h issue_fu=%0d issue_op=%0d",
                      " issue_hs=%b issue_ex_valid=%b issue_ex=%h issue_sbe_valid=%b",
                      " issue_stall=%b acc_valid_d=%b acc_valid_q=%b acc_ready=%b"},
              sample_cb.issue_instr_i.pc, sample_cb.issue_instr_i.trans_id,
              sample_cb.issue_instr_i.fu, sample_cb.issue_instr_i.op,
              sample_cb.issue_instr_hs_i, sample_cb.issue_instr_i.ex.valid,
              sample_cb.issue_instr_i.ex, sample_cb.issue_instr_i.valid,
              sample_cb.issue_stall_o, sample_cb.acc_valid_d,
              sample_cb.acc_valid_q, sample_cb.acc_ready);
      $fwrite(log_fd, " fu_id=%h fu_fu=%0d fu_op=%0d fu_imm=%h fu_a=%h fu_b=%h",
              sample_cb.fu_data_i.trans_id, sample_cb.fu_data_i.fu,
              sample_cb.fu_data_i.operation, sample_cb.fu_data_i.imm,
              sample_cb.fu_data_i.operand_a, sample_cb.fu_data_i.operand_b);
      $fwrite(log_fd, {" queue_push=%b queue_pop=%b queue_usage=%0d queue_empty=%b",
                      " queue_head_id=%h queue_head_fu=%0d queue_head_op=%0d",
                      " queue_head_insn=%h queue_head_imm=%h queue_head_a=%h queue_head_b=%h"},
              sample_cb.acc_valid_q, sample_cb.acc_insn_queue_pop,
              sample_cb.acc_insn_queue_usage, sample_cb.acc_insn_queue_empty,
              sample_cb.acc_insn_queue_o.trans_id, sample_cb.acc_insn_queue_o.fu,
              sample_cb.acc_insn_queue_o.operation, sample_cb.acc_insn_queue_o.imm[31:0],
              sample_cb.acc_insn_queue_o.imm, sample_cb.acc_insn_queue_o.operand_a,
              sample_cb.acc_insn_queue_o.operand_b);
      for (int port = 0; port < CVA6Cfg.NrCommitPorts; port++) begin
        $fwrite(log_fd, {" commit%0d_valid=%b commit%0d_ack=%b commit%0d_id=%h",
                        " commit%0d_pc=%h commit%0d_fu=%0d commit%0d_op=%0d",
                        " commit%0d_ex_valid=%b commit%0d_ex=%h"},
                port, sample_cb.commit_instr_i[port].valid,
                port, sample_cb.commit_ack_i[port],
                port, sample_cb.commit_instr_i[port].trans_id,
                port, sample_cb.commit_instr_i[port].pc,
                port, sample_cb.commit_instr_i[port].fu,
                port, sample_cb.commit_instr_i[port].op,
                port, sample_cb.commit_instr_i[port].ex.valid,
                port, sample_cb.commit_instr_i[port].ex);
      end
      $fwrite(log_fd, {" acc_commit=%b acc_commit_id=%h pending_q=%h pending_d=%h",
                      " ready_q=%h ready_d=%h flush_unissued=%b flush_ex=%b flush_pipeline=%b"},
              sample_cb.acc_commit, sample_cb.acc_commit_trans_id,
              sample_cb.insn_pending_q, sample_cb.insn_pending_d,
              sample_cb.insn_ready_q, sample_cb.insn_ready_d,
              sample_cb.flush_unissued_instr_i, sample_cb.flush_ex_i,
              sample_cb.flush_pipeline_o);
      $fwrite(log_fd, {" spill_in_valid=%b spill_in_ready=%b spill_in_fire=%b",
                      " spill_in_id=%h spill_in_insn=%h spill_in_rs1=%h spill_in_rs2=%h spill_in_frm=%h"},
              sample_cb.acc_req_valid, sample_cb.acc_req_ready,
              sample_cb.acc_req_valid && sample_cb.acc_req_ready,
              sample_cb.acc_req.trans_id, sample_cb.acc_req.insn,
              sample_cb.acc_req.rs1, sample_cb.acc_req.rs2, sample_cb.acc_req.frm);
      $fwrite(log_fd, {" spill_out_valid=%b spill_out_ready=%b spill_out_fire=%b",
                      " spill_out_id=%h spill_out_insn=%h spill_out_rs1=%h spill_out_rs2=%h spill_out_frm=%h"},
              sample_cb.acc_req_o.acc_req.req_valid, sample_cb.acc_resp_i.acc_resp.req_ready,
              sample_cb.acc_req_o.acc_req.req_valid && sample_cb.acc_resp_i.acc_resp.req_ready,
              sample_cb.acc_req_int.trans_id, sample_cb.acc_req_int.insn,
              sample_cb.acc_req_int.rs1, sample_cb.acc_req_int.rs2, sample_cb.acc_req_int.frm);
      $fwrite(log_fd, {" spec_loads=%0d disp_loads=%0d spec_stores=%0d disp_stores=%0d",
                      " spec_loads_overflow=%b disp_loads_overflow=%b",
                      " spec_stores_overflow=%b disp_stores_overflow=%b",
                      " ld_disp=%b st_disp=%b no_ld_pending=%b no_st_pending=%b"},
              sample_cb.acc_spec_loads_pending, sample_cb.acc_disp_loads_pending,
              sample_cb.acc_spec_stores_pending, sample_cb.acc_disp_stores_pending,
              sample_cb.acc_spec_loads_overflow, sample_cb.acc_disp_loads_overflow,
              sample_cb.acc_spec_stores_overflow, sample_cb.acc_disp_stores_overflow,
              sample_cb.acc_ld_disp, sample_cb.acc_st_disp,
              sample_cb.acc_no_ld_pending, sample_cb.acc_no_st_pending);
      $fwrite(log_fd, {" load_complete=%b store_complete=%b resp_valid=%b resp_ready=%b",
                      " resp_fire=%b resp_id=%h resp_result=%h resp_ex_valid=%b resp_ex=%h",
                      " resp_ex_cause=%h resp_ex_tval=%h resp_ex_tval2=%h",
                      " resp_ex_tinst=%h resp_ex_gva=%b resp_fflags_valid=%b resp_fflags=%h"},
              sample_cb.acc_resp_i.acc_resp.load_complete,
              sample_cb.acc_resp_i.acc_resp.store_complete,
              sample_cb.acc_resp_i.acc_resp.resp_valid, sample_cb.acc_req_o.acc_req.resp_ready,
              sample_cb.acc_resp_i.acc_resp.resp_valid && sample_cb.acc_req_o.acc_req.resp_ready,
              sample_cb.acc_resp_i.acc_resp.trans_id, sample_cb.acc_resp_i.acc_resp.result,
              sample_cb.acc_resp_i.acc_resp.exception.valid, sample_cb.acc_resp_i.acc_resp.exception,
              sample_cb.acc_resp_i.acc_resp.exception.cause, sample_cb.acc_resp_i.acc_resp.exception.tval,
              sample_cb.acc_resp_i.acc_resp.exception.tval2, sample_cb.acc_resp_i.acc_resp.exception.tinst,
              sample_cb.acc_resp_i.acc_resp.exception.gva, sample_cb.acc_resp_i.acc_resp.fflags_valid,
              sample_cb.acc_resp_i.acc_resp.fflags);
      $fwrite(log_fd, {" scalar_no_st_pending=%b acc_cons_en=%b req_store_pending=%b",
                      " resp_store_pending=%b commit_st_barrier=%b wait_store_q=%b wait_store_d=%b",
                      " ctrl_halt=%b req_inval_ready=%b resp_inval_valid=%b\n"},
              sample_cb.acc_no_st_pending_i, sample_cb.acc_cons_en_i,
              sample_cb.acc_req_o.acc_req.store_pending, sample_cb.acc_resp_i.acc_resp.store_pending,
              sample_cb.commit_st_barrier_i, sample_cb.wait_acc_store_q, sample_cb.wait_acc_store_d,
              sample_cb.ctrl_halt_o, sample_cb.acc_req_o.acc_req.inval_ready,
              sample_cb.acc_resp_i.acc_resp.inval_valid);
      row_count = row_count + 1;
      if (row_count == row_limit) begin
        truncated = 1;
        $fwrite(log_fd, "# TRUNCATED reason=row_limit rows=%0d last_cycle=%0d epoch=%0d\n",
                row_count, cycle_count, sample_cb.epoch);
        $fflush(log_fd);
      end else if (row_count == 1 || (row_count % 256) == 0) begin
        $fflush(log_fd);
      end
    end
    cycle_count = cycle_count + 1;
  end

  final begin
    if (log_fd != 0) begin
      $fwrite(log_fd, "# END triggered=%0d rows=%0d limit=%0d truncated=%0d sampled_edges=%0d\n",
              triggered, row_count, row_limit, truncated, cycle_count);
      $fflush(log_fd);
      $fclose(log_fd);
    end
  end
endmodule

bind acc_dispatcher cva6_acc_lifecycle_probe #(
  .CVA6Cfg(CVA6Cfg),
  .fu_data_t(fu_data_t),
  .scoreboard_entry_t(scoreboard_entry_t),
  .accelerator_req_t(accelerator_req_t),
  .acc_req_t(acc_req_t),
  .acc_resp_t(acc_resp_t),
  .QueueUsageWidth($bits(acc_insn_queue_usage))
) i_cva6_acc_lifecycle_probe (
  .clk_i(clk_i),
  .rst_ni(rst_ni),
  .issue_instr_i(issue_instr_i),
  .issue_instr_hs_i(issue_instr_hs_i),
  .issue_stall_o(issue_stall_o),
  .fu_data_i(fu_data_i),
  .acc_valid_d(acc_valid_d),
  .acc_valid_q(acc_valid_q),
  .acc_ready(acc_ready),
  .acc_insn_queue_pop(acc_insn_queue_pop),
  .acc_insn_queue_empty(acc_insn_queue_empty),
  .acc_insn_queue_usage(acc_insn_queue_usage),
  .acc_insn_queue_o(acc_insn_queue_o),
  .commit_instr_i(commit_instr_i),
  .commit_ack_i(commit_ack_i),
  .acc_commit(acc_commit),
  .acc_commit_trans_id(acc_commit_trans_id),
  .insn_pending_q(insn_pending_q),
  .insn_pending_d(insn_pending_d),
  .insn_ready_q(insn_ready_q),
  .insn_ready_d(insn_ready_d),
  .flush_unissued_instr_i(flush_unissued_instr_i),
  .flush_ex_i(flush_ex_i),
  .flush_pipeline_o(flush_pipeline_o),
  .acc_req(acc_req),
  .acc_req_valid(acc_req_valid),
  .acc_req_ready(acc_req_ready),
  .acc_req_int(acc_req_int),
  .acc_req_o(acc_req_o),
  .acc_resp_i(acc_resp_i),
  .acc_spec_loads_pending(acc_spec_loads_pending),
  .acc_disp_loads_pending(acc_disp_loads_pending),
  .acc_spec_stores_pending(acc_spec_stores_pending),
  .acc_disp_stores_pending(acc_disp_stores_pending),
  .acc_spec_loads_overflow(acc_spec_loads_overflow),
  .acc_disp_loads_overflow(acc_disp_loads_overflow),
  .acc_spec_stores_overflow(acc_spec_stores_overflow),
  .acc_disp_stores_overflow(acc_disp_stores_overflow),
  .acc_ld_disp(acc_ld_disp),
  .acc_st_disp(acc_st_disp),
  .acc_no_ld_pending(acc_no_ld_pending),
  .acc_no_st_pending(acc_no_st_pending),
  .acc_no_st_pending_i(acc_no_st_pending_i),
  .acc_cons_en_i(acc_cons_en_i),
  .commit_st_barrier_i(commit_st_barrier_i),
  .wait_acc_store_q(wait_acc_store_q),
  .wait_acc_store_d(wait_acc_store_d),
  .ctrl_halt_o(ctrl_halt_o)
);
`endif
