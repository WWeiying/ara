`timescale 1ns/1ps
`include "rvfi_types.svh"
`include "ara/intf_typedef.svh"

// Module integration, not a core: operand supply, scalar WB and accelerator
// response are BFMs. Decode, ID, scoreboard, CSR buffer and commit are real RTL.
module commit_boundary_tb;
  import ariane_pkg::*;
  import riscv::*;
  function automatic config_pkg::cva6_cfg_t configuration();
    config_pkg::cva6_cfg_t c;
    c = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
    c.NrPMPEntries = 0;
    c.EnableAccelerator = 1;
    c.CvxifEn = 0;
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg = configuration();
  `include "gate_types.svh"
  typedef `RVFI_PROBES_CSR_T(CVA6Cfg) rvfi_t;
  typedef logic [CVA6Cfg.TRANS_ID_BITS-1:0] tid_t;
  typedef struct packed {
    logic [CVA6Cfg.NR_SB_ENTRIES-1:0] still_issued;
    tid_t issue_pointer;
    writeback_t [CVA6Cfg.NrWbPorts-1:0] wb;
    scoreboard_entry_t [CVA6Cfg.NR_SB_ENTRIES-1:0] sbe;
  } forwarding_t;
  `CVA6_INTF_TYPEDEF_ACC_REQ(accelerator_req_t, CVA6Cfg, fpnew_pkg::roundmode_e)
  `CVA6_INTF_TYPEDEF_ACC_RESP(accelerator_resp_t, CVA6Cfg, exception_t)
  `CVA6_INTF_TYPEDEF_MMU_REQ(acc_mmu_req_t, CVA6Cfg)
  `CVA6_INTF_TYPEDEF_MMU_RESP(acc_mmu_resp_t, CVA6Cfg, exception_t)
  `CVA6_INTF_TYPEDEF_CVA6_TO_ACC(acc_req_t, accelerator_req_t, acc_mmu_resp_t)
  `CVA6_INTF_TYPEDEF_ACC_TO_CVA6(acc_resp_t, accelerator_resp_t, acc_mmu_req_t)
  localparam logic [31:0] INFO = 32'h0005455b;
  localparam logic [31:0] NOP = 32'h00000013;
  localparam logic [31:0] LOAD = 32'h00053583;
  localparam logic [31:0] RET_M = 32'h30200073;
  localparam logic [31:0] RET_S = 32'h10200073;

  bit clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic allowed, csr_flush, eret, flush_if, flush_id, flush_ex, flush_unissued;
  logic halt, dirty_fp, dirty_v, fflags, csr_commit;
  logic fence_i, fence, fence_t, sfence, hfence_vv, hfence_gv, flush_commit;
  logic [63:0] pc_commit, csr_wdata, csr_rdata;
  logic [11:0] csr_address;
  fu_op csr_op;
  exception_t csr_exception, commit_exception;
  priv_lvl_t privilege, memory_privilege;
  xs_t fs, vs;
  irq_ctrl_t irq_control;
  fetch_entry_t [0:0] fetch;
  scoreboard_entry_t [0:0] id_entry, issue_entry;
  scoreboard_entry_t [1:0] commits;
  logic [0:0] fetch_valid = 0, fetch_ready, id_valid, id_ack, issue_valid, issue_ack;
  logic [0:0][31:0] orig_instr;
  logic [1:0] ack, macro_ack, retire_ack, drop;
  forwarding_t forwarding;
  logic issue_enable = 0, issue_stall, csr_ready;
  logic [63:0] operand = 0;
  fu_data_t ex_data;
  logic ex_csr_valid;
  logic [63:0] csr_result;
  tid_t [CVA6Cfg.NrWbPorts-1:0] wb_id;
  logic [CVA6Cfg.NrWbPorts-1:0][63:0] wb_data;
  logic [CVA6Cfg.NrWbPorts-1:0] wb_valid;
  exception_t [CVA6Cfg.NrWbPorts-1:0] wb_ex;
  logic scalar_wb = 0;
  tid_t scalar_id = 0;
  logic [63:0] scalar_data = 0;
  exception_t scalar_ex;
  acc_req_t req;
  acc_resp_t resp;
  logic response_valid;
  tid_t response_id, acc_wb_id;
  logic [63:0] response_data, acc_wb_data;
  logic acc_wb_valid;
  exception_t acc_wb_ex;
  logic request_ready = 1, expect_request = 0;
  logic [63:0] expected_token = 0, token = 100;
  tid_t expected_id;
  int checks = 0, requests = 0, pops = 0, retires = 0, rejects = 0;
  int flushes = 0, replays = 0, races = 0, waits = 0, cycle = 0;
  int c_checks, c_requests, c_pops, c_retires, c_rejects, c_flushes, c_replays, c_races, c_waits;
  int events;
  string case_name = "boot", phase = "reset";

  id_stage #(.CVA6Cfg(CVA6Cfg), .branchpredict_sbe_t(branchpredict_sbe_t),
      .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t),
      .exception_t(exception_t), .fetch_entry_t(fetch_entry_t), .jvt_t(jvt_t),
      .irq_ctrl_t(irq_ctrl_t), .scoreboard_entry_t(scoreboard_entry_t), .interrupts_t(interrupts_t)) id_path (
      .clk_i(clk), .rst_ni(rst_n), .flush_i(flush_if), .debug_req_i(1'b0),
      .fetch_entry_i(fetch), .fetch_entry_valid_i(fetch_valid), .fetch_entry_ready_o(fetch_ready),
      .issue_entry_o(id_entry), .issue_entry_valid_o(id_valid), .issue_instr_ack_i(id_ack),
      .orig_instr_o(orig_instr), .priv_lvl_i(privilege), .akv_access_allowed_i(allowed),
      .v_i(1'b0), .fs_i(fs), .vfs_i(Off), .frm_i('0), .vs_i(vs), .irq_i('0),
      .irq_ctrl_i(irq_control), .clic_mode_i(1'b0), .clic_irq_req_i(1'b0), .clic_irq_cause_i('0),
      .debug_mode_i(1'b0), .tvm_i(1'b0), .tw_i(1'b0), .vtw_i(1'b0), .tsr_i(1'b0),
      .hu_i(1'b0), .hart_id_i('0), .compressed_ready_i(1'b1), .jvt_i('0),
      .compressed_resp_i('0), .dcache_req_ports_i('0));

  scoreboard #(.CVA6Cfg(CVA6Cfg), .bp_resolve_t(bp_resolve_t), .exception_t(exception_t),
      .scoreboard_entry_t(scoreboard_entry_t), .forwarding_t(forwarding_t),
      .writeback_t(writeback_t)) sb (
      .clk_i(clk), .rst_ni(rst_n), .flush_unissued_instr_i(flush_unissued), .flush_i(flush_id),
      .x_transaction_accepted_i(1'b0), .x_issue_writeback_i(1'b0), .x_id_i('0),
      .commit_instr_o(commits), .commit_drop_o(drop), .commit_ack_i(ack),
      .decoded_instr_i(id_entry), .orig_instr_i(orig_instr), .decoded_instr_valid_i(id_valid),
      .decoded_instr_ack_o(id_ack), .issue_instr_o(issue_entry), .issue_instr_valid_o(issue_valid),
      .issue_ack_i(issue_ack), .fwd_o(forwarding), .resolved_branch_i('0),
      .trans_id_i(wb_id), .wbdata_i(wb_data), .ex_i(wb_ex), .wt_valid_i(wb_valid),
      .acc_preview_valid_i(1'b0), .acc_preview_id_i('0), .acc_preview_data_i('0),
      .x_we_i(1'b0), .x_rd_i('0));
  assign issue_ack[0] = issue_enable && issue_valid[0] && !issue_stall && !flush_unissued;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin ex_data <= '0; ex_csr_valid <= 0; end
    else begin
      ex_csr_valid <= issue_ack[0] && issue_entry[0].fu == CSR && !issue_entry[0].ex.valid;
      if (issue_ack[0])
        ex_data <= '{fu: issue_entry[0].fu, operation: issue_entry[0].op,
                     operand_a: operand, operand_b: issue_entry[0].result,
                     imm: issue_entry[0].result, trans_id: issue_entry[0].trans_id};
    end
  end
  csr_buffer #(.CVA6Cfg(CVA6Cfg), .fu_data_t(fu_data_t)) csr_buf (
      .clk_i(clk), .rst_ni(rst_n), .flush_i(flush_ex), .fu_data_i(ex_data),
      .csr_ready_o(csr_ready), .csr_valid_i(ex_csr_valid), .csr_result_o(csr_result),
      .csr_commit_i(csr_commit), .csr_addr_o(csr_address));

  commit_stage #(.CVA6Cfg(CVA6Cfg), .exception_t(exception_t),
      .scoreboard_entry_t(scoreboard_entry_t)) commit_path (
      .clk_i(clk), .rst_ni(rst_n), .halt_i(halt), .flush_dcache_i(1'b0), .single_step_i(1'b0),
      .commit_instr_i(commits), .commit_drop_i(drop), .commit_ack_o(ack), .commit_macro_ack_o(macro_ack),
      .amo_resp_i('0), .pc_o(pc_commit), .csr_op_o(csr_op), .csr_wdata_o(csr_wdata),
      .csr_rdata_i(csr_rdata), .csr_write_fflags_o(fflags), .csr_exception_i(csr_exception),
      .exception_o(commit_exception), .dirty_fp_state_o(dirty_fp), .commit_lsu_ready_i(1'b1),
      .no_st_pending_i(1'b1), .commit_csr_o(csr_commit), .fence_i_o(fence_i), .fence_o(fence),
      .fence_t_o(fence_t), .flush_commit_o(flush_commit), .sfence_vma_o(sfence),
      .hfence_vvma_o(hfence_vv), .hfence_gvma_o(hfence_gv));
  assign retire_ack = macro_ack & ~drop;
  csr_regfile #(.CVA6Cfg(CVA6Cfg), .exception_t(exception_t), .jvt_t(jvt_t),
      .irq_ctrl_t(irq_ctrl_t), .scoreboard_entry_t(scoreboard_entry_t), .rvfi_probes_csr_t(rvfi_t)) csr (
      .clk_i(clk), .rst_ni(rst_n), .time_irq_i(1'b0), .commit_instr_i(commits[0]),
      .commit_ack_i(retire_ack), .boot_addr_i(64'h80000000), .hart_id_i('0),
      .ex_i(commit_exception), .csr_op_i(csr_op), .csr_addr_i(csr_address), .csr_wdata_i(csr_wdata),
      .csr_rdata_o(csr_rdata), .dirty_fp_state_i(dirty_fp), .csr_write_fflags_i(fflags),
      .dirty_v_state_i(dirty_v), .pc_i(pc_commit), .csr_exception_o(csr_exception),
      .eret_o(eret), .flush_o(csr_flush), .priv_lvl_o(privilege), .ld_st_priv_lvl_o(memory_privilege),
      .akv_access_allowed_o(allowed), .fs_o(fs), .vs_o(vs), .irq_ctrl_o(irq_control),
      .acc_fflags_ex_i('0), .acc_fflags_ex_valid_i(1'b0), .csr_hs_ld_st_inst_i(1'b0), .irq_i('0),
      .clic_irq_req_i(1'b0), .clic_irq_shv_i(1'b0), .ipi_i(1'b0), .debug_req_i(1'b0),
      .fence_t_ceil_i('0), .perf_data_i('0));
  controller #(.CVA6Cfg(CVA6Cfg), .bp_resolve_t(bp_resolve_t)) control (
      .clk_i(clk), .rst_ni(rst_n), .v_i(1'b0), .flush_if_o(flush_if), .flush_id_o(flush_id),
      .flush_unissued_instr_o(flush_unissued), .flush_ex_o(flush_ex), .flush_dcache_ack_i(1'b0),
      .boot_addr_i(64'h80000000), .pc_commit_i(pc_commit), .halt_csr_i(1'b0), .halt_acc_i(1'b0),
      .halt_o(halt), .cache_busy_i(1'b0), .fence_t_pad_i('0), .fence_t_src_sel_i(1'b0),
      .time_irq_i(1'b0), .priv_lvl_i(privilege), .eret_i(eret), .ex_valid_i(commit_exception.valid),
      .set_debug_pc_i(1'b0), .resolved_branch_i('0), .flush_csr_i(csr_flush),
      .fence_i_i(fence_i), .fence_i(fence), .fence_t_i(fence_t), .sfence_vma_i(sfence),
      .hfence_vvma_i(hfence_vv), .hfence_gvma_i(hfence_gv), .flush_commit_i(flush_commit), .flush_acc_i(1'b0));
  acc_dispatcher #(.CVA6Cfg(CVA6Cfg), .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t),
      .exception_t(exception_t), .fu_data_t(fu_data_t), .scoreboard_entry_t(scoreboard_entry_t),
      .acc_req_t(acc_req_t), .acc_resp_t(acc_resp_t), .accelerator_req_t(accelerator_req_t),
      .accelerator_resp_t(accelerator_resp_t), .acc_mmu_req_t(acc_mmu_req_t),
      .acc_mmu_resp_t(acc_mmu_resp_t)) dispatch (
      .clk_i(clk), .rst_ni(rst_n), .acc_cons_en_i(1'b1), .ld_st_priv_lvl_i(memory_privilege),
      .sum_i(1'b0), .pmpcfg_i('0), .pmpaddr_i('0), .fcsr_frm_i('0), .acc_mmu_en_i(1'b0),
      .issue_instr_i(issue_entry[0]), .issue_instr_hs_i(issue_ack[0]), .issue_stall_o(issue_stall),
      .fu_data_i(ex_data), .commit_instr_i(commits), .commit_ack_i(retire_ack),
      .dirty_v_state_o(dirty_v), .commit_st_barrier_i(1'b0), .acc_no_st_pending_i(1'b1),
      .dcache_req_ports_i('0), .acc_mmu_resp_i('0), .csr_addr_i(csr_address),
      .flush_unissued_instr_i(flush_unissued), .flush_ex_i(flush_ex), .acc_dcache_req_ports_i('0),
      .inval_ready_i(1'b1), .acc_req_o(req), .acc_resp_i(resp), .acc_trans_id_o(acc_wb_id),
      .acc_result_o(acc_wb_data), .acc_valid_o(acc_wb_valid), .acc_exception_o(acc_wb_ex));
  always_comb begin
    resp = '0;
    resp.acc_resp.req_ready = request_ready;
    resp.acc_resp.resp_valid = response_valid;
    resp.acc_resp.trans_id = response_id;
    resp.acc_resp.result = response_data;
    wb_valid = '0; wb_id = '0; wb_data = '0; wb_ex = '0;
    wb_valid[0] = scalar_wb; wb_id[0] = scalar_id; wb_data[0] = scalar_data; wb_ex[0] = scalar_ex;
    wb_valid[ACC_WB] = acc_wb_valid; wb_id[ACC_WB] = acc_wb_id;
    wb_data[ACC_WB] = acc_wb_data; wb_ex[ACC_WB] = acc_wb_ex;
  end
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin response_valid <= 0; response_id <= 0; response_data <= 0; end
    else begin
      response_valid <= req.acc_req.req_valid && request_ready;
      if (req.acc_req.req_valid && request_ready) begin
        response_id <= req.acc_req.trans_id;
        response_data <= req.acc_req.rs1 + 1;
      end
    end
  end

  task automatic check(input logic ok, input string message);
    checks++;
    if (ok !== 1'b1)
      $fatal(1, "COMMIT_BOUNDARY_FAIL name=%s phase=%s cycle=%0d check=%0d %s",
             case_name, phase, cycle, checks, message);
  endtask
  always @(posedge clk) begin
    cycle++;
    $fwrite(events, "%0d,%s,%s,%0d,%0d,%0d,%0d,%03h,%016h,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0h,%0h,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%08h,%016h,%0d\n",
      cycle, case_name, phase, rst_n, privilege, allowed, csr_op, csr_address, csr_wdata,
      commits[0].fu, commits[0].valid, commits[0].trans_id, commits[1].fu, commits[1].valid,
      commits[1].trans_id, ack[0], ack[1], csr_commit, commit_exception.valid, commit_exception.cause,
      csr_flush, eret, flush_if, flush_id, flush_ex, flush_unissued, id_valid[0], id_entry[0].ex.valid,
      issue_ack[0], issue_entry[0].trans_id, dispatch.insn_pending_q, dispatch.insn_ready_q,
      dispatch.acc_commit, dispatch.acc_commit_trans_id, dispatch.acc_insn_queue_empty,
      dispatch.acc_insn_queue_usage, dispatch.acc_insn_queue_pop, dispatch.acc_req_valid,
      req.acc_req.req_valid, request_ready, req.acc_req.trans_id, response_valid,
      req.acc_req.insn, req.acc_req.rs1, retire_ack[0] && commits[0].fu == ACCEL);
    $fflush(events);
    if (rst_n) begin
      check(!$isunknown({ack, allowed, flush_unissued, flush_ex, req.acc_req.req_valid}), "unknown control");
      if (flush_ex) begin
        check(!dispatch.acc_insn_queue_pop && !dispatch.acc_req_valid, "flush crossed speculative boundary");
        check(dispatch.insn_ready_d == '0 && dispatch.insn_pending_d == '0, "flush next-state retains ID bits");
      end
      if (dispatch.acc_insn_queue_pop) begin
        check(expect_request && allowed && !flush_unissued, "unexpected queue-to-output transfer");
        pops++;
      end
      if (req.acc_req.req_valid && request_ready) begin
        check(expect_request && req.acc_req.trans_id == expected_id && req.acc_req.insn == INFO &&
              req.acc_req.rs1 == expected_token, "unexpected or stale actual request");
        requests++;
      end
      if (retire_ack[0] && commits[0].fu == ACCEL) begin
        check(commits[0].valid && !commits[0].ex.valid && commits[0].result == expected_token + 1,
              "accelerator retirement must follow response WB");
        retires++;
      end
    end
  end
  task automatic tick;
    @(posedge clk); #1; @(negedge clk); #1;
  endtask
  function automatic logic [31:0] write_csr(input logic [11:0] address);
    return {address, 5'd10, 3'b001, 5'd0, 7'h73};
  endfunction
  task automatic capture(input logic [31:0] insn);
    check(!id_valid[0], "ID must be empty before fetch");
    fetch = '0; fetch[0].instruction = insn; fetch[0].address = 64'h80000200;
    fetch_valid = 1; #1;
    check(fetch_ready[0] && !flush_if, "fetch handshake unavailable");
    tick(); fetch_valid = 0;
    check(id_valid[0], "real ID register did not capture");
  endtask
  task automatic send(input logic [31:0] insn, input logic [63:0] value, output tid_t id);
    capture(insn);
    if (id_entry[0].fu == CSR) check(csr_ready, "CSR address buffer not available");
    id = issue_entry[0].trans_id; operand = value; issue_enable = 1; #1;
    check(issue_ack[0], "legal single-issue handshake unavailable");
    if (insn == INFO && !allowed) begin
      check(id_entry[0].ex.valid && id_entry[0].ex.cause == ILLEGAL_INSTR &&
            id_entry[0].ex.tval == 64'(INFO) && id_entry[0].fu == NONE && !dispatch.acc_valid_d,
            "denied AKV entered accelerator classification");
      rejects++;
    end else check(!id_entry[0].ex.valid, "unexpected decode exception");
    tick(); issue_enable = 0; tick();
  endtask
  task automatic writeback(input tid_t id, input logic [63:0] data, input bit fault = 0);
    check(sb.mem_q[id].issued && !sb.mem_q[id].sbe.valid, "WB must target a live incomplete entry");
    scalar_wb = 1; scalar_id = id; scalar_data = data; scalar_ex = '0;
    if (fault) begin scalar_ex.valid = 1; scalar_ex.cause = LOAD_PAGE_FAULT; scalar_ex.tval = 64'h90000000; end
    tick(); scalar_wb = 0; scalar_ex = '0; #1;
  endtask
  task automatic csr_write(input logic [11:0] address, input logic [63:0] data);
    tid_t id;
    send(write_csr(address), data, id);
    check(csr_address == address && csr_buf.csr_reg_q.valid && csr_result == data, "real CSR buffer address/result");
    writeback(id, data);
    check(ack[0] && csr_commit && csr_op == CSR_WRITE && csr_wdata == data && !commit_exception.valid,
          "commit_stage did not produce CSR write");
    tick(); tick();
  endtask
  task automatic return_plain(input logic [31:0] insn, input priv_lvl_t target);
    tid_t id;
    send(insn, 0, id); writeback(id, 0);
    check(ack[0] && eret && !commit_exception.valid && flush_ex, "real xRET boundary");
    tick(); tick(); check(privilege == target, "xRET target privilege");
  endtask
  task automatic setup(input logic [2:0] bits, input priv_lvl_t target, input bit delegate_fault);
    phase = "setup";
    @(negedge clk); rst_n = 0; fetch_valid = 0; issue_enable = 0;
    scalar_wb = 0; scalar_ex = '0; fetch = '0; expect_request = 0; request_ready = 1;
    repeat (3) tick(); rst_n = 1; tick();
    check(privilege == PRIV_LVL_M && allowed, "reset access");
    csr_write(12'h5c0, 64'(bits));
    csr_write(CSR_MEDELEG, delegate_fault ? (64'd1 << LOAD_PAGE_FAULT) : 0);
    csr_write(CSR_MSTATUS, (64'd3 << 13) | (64'd3 << 9) | (64'(target) << 11));
    if (target != PRIV_LVL_M) return_plain(RET_M, target);
    check(privilege == target && vs != Off, "setup privilege/vector state");
  endtask
  task automatic empty_state;
    check(!id_valid[0] && dispatch.acc_insn_queue_empty && !dispatch.acc_valid_q &&
          dispatch.insn_pending_q == '0 && dispatch.insn_ready_q == '0 &&
          !req.acc_req.req_valid && forwarding.still_issued == '0, "flush retained old ID/queue/scoreboard state");
  endtask
  task automatic align_ids;
    tid_t id;
    check(forwarding.still_issued == '0 && !id_valid[0], "alignment requires empty pipeline");
    for (int n = 0; n < CVA6Cfg.NR_SB_ENTRIES; n++) begin
      if (forwarding.issue_pointer != 0) begin
        send(NOP, 0, id); writeback(id, 0); tick();
      end
    end
    check(forwarding.issue_pointer == 0, "real scoreboard ID wrap failed");
  endtask

  // Older scalar completion is deliberately delayed, not its commit ack.
  // kind: 0=SAKVCTL write, 1=MRET, 2=SRET, 3=load fault.
  task automatic boundary(input int kind, input logic [63:0] data,
                           input priv_lvl_t target, input bit target_allowed);
    tid_t older, younger;
    bit old_allowed;
    int before_requests;
    align_ids(); old_allowed = allowed; before_requests = requests;
    phase = kind == 0 ? "csr_boundary" : kind == 1 ? "mret_boundary" :
            kind == 2 ? "sret_boundary" : "trap_boundary";
    send(kind == 0 ? write_csr(12'h5c0) : kind == 1 ? RET_M : kind == 2 ? RET_S : LOAD, data, older);
    token++; send(INFO, token, younger);
    check(older == 0 && younger == 1 && commits[0].trans_id == older && commits[1].trans_id == younger,
          "real adjacent commit slots/ID allocation");
    check(!ack[0] && !dispatch.acc_commit && requests == before_requests, "younger escaped incomplete older");
    if (old_allowed)
      check(!commits[1].valid && commits[1].fu == ACCEL && !dispatch.acc_insn_queue_empty &&
            dispatch.insn_pending_q[younger], "nonempty speculative queue precondition");
    else check(commits[1].valid && commits[1].ex.valid && dispatch.acc_insn_queue_empty,
               "denied younger must be exception, never fabricated ACCEL");
    capture(INFO);
    check(id_entry[0].ex.valid == !old_allowed, "held ID permission precondition");
    writeback(older, data, kind == 3);
    check(flush_if && flush_id && flush_ex && flush_unissued && !ack[1], "all younger paths must flush");
    if (kind == 3) begin
      check(!ack[0] && commit_exception.valid && commit_exception.cause == LOAD_PAGE_FAULT &&
            !eret && !csr_flush && !dispatch.acc_commit, "trap must originate from real commit exception");
    end else begin
      check(ack[0] && csr_commit && !commit_exception.valid && !csr_exception.valid,
            "real CSR/xRET retirement ack");
      check(kind == 0 ? (csr_op == CSR_WRITE && csr_flush && !eret && csr_wdata == data) :
            (eret && csr_op == (kind == 1 ? MRET : SRET)), "real commit CSR operation/return");
      if (old_allowed) begin
        check(dispatch.acc_commit && dispatch.insn_pending_q[younger] &&
              dispatch.acc_commit_trans_id == younger && !dispatch.acc_insn_queue_pop &&
              dispatch.insn_ready_d == '0, "release candidate must lose to flush before ready can persist");
        races++;
      end
    end
    check(!dispatch.acc_req_valid && !req.acc_req.req_valid, "boundary leaked actual request");
    tick(); tick(); empty_state();
    check(privilege == target && allowed == target_allowed && requests == before_requests,
          "post-boundary permission/count");
    flushes++;
  endtask
  task automatic replay;
    tid_t older, younger;
    int r, p, t;
    phase = "reuse_wait"; align_ids();
    check(allowed, "positive replay requires current permission");
    r = requests; p = pops; t = retires;
    send(NOP, 0, older); token++; send(INFO, token, younger);
    check(older == 0 && younger == 1 && dispatch.insn_pending_q[younger], "reuse exact flushed transaction ID");
    repeat (3) begin
      check(!ack[0] && !dispatch.acc_commit && !req.acc_req.req_valid &&
            dispatch.insn_ready_q == '0 && !dispatch.acc_insn_queue_pop, "reused ID inherited old ready");
      tick(); waits++;
    end
    phase = "positive_release";
    expect_request = 1; expected_id = younger; expected_token = token;
    writeback(older, 0);
    check(ack[0] && !flush_unissued && dispatch.acc_commit && dispatch.acc_insn_queue_pop &&
          req.acc_req.req_valid && !commits[1].valid && !ack[1], "non-vacuous port1 release, not retirement");
    repeat (5) tick();
    check(requests == r+1 && pops == p+1 && retires == t+1 && dispatch.insn_ready_q == '0 &&
          forwarding.still_issued == '0 && !req.acc_req.req_valid, "exactly one replay request/response/retirement");
    expect_request = 0; replays++;
  endtask
  task automatic denied_hold;
    int r;
    r = requests; phase = "denied_refetch";
    capture(INFO);
    check(!allowed && id_entry[0].ex.valid && id_entry[0].ex.cause == ILLEGAL_INSTR &&
          id_entry[0].ex.tval == 64'(INFO) && id_entry[0].fu == NONE, "new privilege must reject fresh decode");
    repeat (2) tick();
    check(requests == r && dispatch.acc_insn_queue_empty && !req.acc_req.req_valid, "denied held ID leaked");
    rejects++;
    // Consumed only by the next reset; no fake issue acknowledgement is used.
  endtask
  task automatic begin_case(input string name);
    case_name = name;
    c_checks = checks; c_requests = requests; c_pops = pops; c_retires = retires;
    c_rejects = rejects; c_flushes = flushes; c_replays = replays; c_races = races; c_waits = waits;
  endtask
  task automatic end_case(input int nr, input int nj, input int nf, input int np, input int nc);
    check(requests-c_requests == nr && pops-c_pops == nr && retires-c_retires == nr &&
          rejects-c_rejects == nj && flushes-c_flushes == nf && replays-c_replays == np &&
          races-c_races == nc && waits-c_waits == 3*np, "case event cardinality");
    $display("COMMIT_BOUNDARY_CASE_PASS name=%s checks=%0d requests=%0d rejects=%0d flushes=%0d replays=%0d pops=%0d retires=%0d races=%0d waits=%0d",
      case_name, checks-c_checks, requests-c_requests, rejects-c_rejects, flushes-c_flushes,
      replays-c_replays, pops-c_pops, retires-c_retires, races-c_races, waits-c_waits);
  endtask
  initial begin
    events = $fopen("events.csv", "w");
    if (!events) $fatal(1, "COMMIT_BOUNDARY_FAIL cannot open CSV");
    $fwrite(events, "cycle,case,phase,rst_n,priv,allowed,csr_op,csr_addr,csr_wdata,p0_fu,p0_valid,p0_id,p1_fu,p1_valid,p1_id,ack0,ack1,csr_commit,exception,cause,csr_flush,eret,flush_if,flush_id,flush_ex,flush_unissued,id_valid,id_exception,issue_hs,issue_id,pending,ready,acc_commit,acc_commit_id,queue_empty,queue_usage,queue_pop,acc_req_valid,req_valid,req_ready,req_id,resp_valid,req_insn,req_rs1,acc_retire\n");
    begin_case("csr_close_open_s");
    check(CVA6Cfg.XLEN == 64 && !CVA6Cfg.RVH && !CVA6Cfg.SuperscalarEn && CVA6Cfg.NrIssuePorts == 1 &&
          CVA6Cfg.NrCommitPorts == 2 && CVA6Cfg.EnableAccelerator && !CVA6Cfg.RVZCMP && ACC_WB != 0,
          "only RV64 noH single issue two commit ports supported");
    setup(5, PRIV_LVL_S, 0);
    boundary(0, 1, PRIV_LVL_S, 0);
    boundary(0, 5, PRIV_LVL_S, 1);
    replay(); end_case(1, 1, 2, 1, 1);

    begin_case("csr_open_m_mret_u");
    setup(1, PRIV_LVL_M, 0);
    boundary(0, 3, PRIV_LVL_M, 1); replay();
    csr_write(CSR_MSTATUS, (64'd3 << 13) | (64'd3 << 9));
    boundary(1, 0, PRIV_LVL_U, 1); replay(); end_case(2, 0, 2, 2, 2);

    begin_case("u_only_trap_sret");
    setup(3, PRIV_LVL_U, 1);
    boundary(3, 0, PRIV_LVL_S, 0);
    boundary(2, 0, PRIV_LVL_U, 1); replay(); end_case(1, 1, 2, 1, 0);

    begin_case("s_only_trap_sret_mret");
    setup(5, PRIV_LVL_U, 1);
    boundary(3, 0, PRIV_LVL_S, 1); replay();
    boundary(2, 0, PRIV_LVL_U, 0);
    // Load faults are delegated; an illegal AKV instead traps to M (not delegated).
    phase = "illegal_trap_m";
    begin
      tid_t id;
      send(INFO, 0, id); tick();
      check(privilege == PRIV_LVL_M, "denied AKV must trap through commit to M");
      empty_state();
    end
    boundary(1, 0, PRIV_LVL_U, 0); denied_hold(); end_case(1, 3, 3, 1, 2);
    $display("COMMIT_BOUNDARY_PASS cases=4 checks=%0d requests=%0d rejects=%0d flushes=%0d replays=%0d pops=%0d retires=%0d races=%0d waits=%0d",
             checks, requests, rejects, flushes, replays, pops, retires, races, waits);
    $fclose(events); $finish;
  end
  initial begin #50000; $fatal(1, "COMMIT_BOUNDARY_FAIL bounded watchdog"); end
endmodule
