`timescale 1ns/1ps
`include "ara/intf_typedef.svh"

module acc_dispatcher_contract_tb;
  import ariane_pkg::*;
  import riscv::*;
  localparam config_pkg::cva6_cfg_t CVA6Cfg =
      build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  `include "contract_types.svh"
  `CVA6_INTF_TYPEDEF_ACC_REQ(accelerator_req_t, CVA6Cfg, fpnew_pkg::roundmode_e)
  `CVA6_INTF_TYPEDEF_ACC_RESP(accelerator_resp_t, CVA6Cfg, exception_t)
  `CVA6_INTF_TYPEDEF_MMU_REQ(acc_mmu_req_t, CVA6Cfg)
  `CVA6_INTF_TYPEDEF_MMU_RESP(acc_mmu_resp_t, CVA6Cfg, exception_t)
  `CVA6_INTF_TYPEDEF_CVA6_TO_ACC(acc_req_t, accelerator_req_t, acc_mmu_resp_t)
  `CVA6_INTF_TYPEDEF_ACC_TO_CVA6(acc_resp_t, accelerator_resp_t, acc_mmu_req_t)

  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  scoreboard_entry_t issue;
  scoreboard_entry_t [CVA6Cfg.NrCommitPorts-1:0] commits;
  fu_data_t execute_data, pipeline_data;
  acc_req_t req;
  acc_resp_t resp;
  exception_t exception_out;
  logic issue_hs, stall, cons, flush;
  logic [CVA6Cfg.NrCommitPorts-1:0] ack;
  logic [CVA6Cfg.TRANS_ID_BITS-1:0] result_id;
  logic [CVA6Cfg.XLEN-1:0] result_data;
  logic result_valid, fflags_valid;
  logic [4:0] fflags;
  int fd, trace_fd, config_fd, cycle = 0, scanned;
  int seq, ident, kind, view, consistency, c0_acc, c0_valid, c0_id;
  int c1_acc, c1_valid, c1_id, ack0, flush_value, ready_value;
  int resp_seq, resp_id, ld_done, st_done;
  string label, stimulus_path;

  acc_dispatcher #(
    .CVA6Cfg(CVA6Cfg), .dcache_req_i_t(dcache_req_i_t),
    .dcache_req_o_t(dcache_req_o_t), .exception_t(exception_t),
    .fu_data_t(fu_data_t), .scoreboard_entry_t(scoreboard_entry_t),
    .acc_req_t(acc_req_t), .acc_resp_t(acc_resp_t),
    .accelerator_req_t(accelerator_req_t), .accelerator_resp_t(accelerator_resp_t),
    .acc_mmu_req_t(acc_mmu_req_t), .acc_mmu_resp_t(acc_mmu_resp_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .acc_cons_en_i(cons),
    .acc_fflags_valid_o(fflags_valid), .acc_fflags_o(fflags),
    .ld_st_priv_lvl_i(PRIV_LVL_M), .sum_i(1'b0), .pmpcfg_i('0), .pmpaddr_i('0),
    .fcsr_frm_i(3'd2), .dirty_v_state_o(), .acc_mmu_en_i(1'b0),
    .issue_instr_i(issue), .issue_instr_hs_i(issue_hs), .issue_stall_o(stall),
    .fu_data_i(execute_data), .commit_instr_i(commits),
    .acc_trans_id_o(result_id), .acc_result_o(result_data), .acc_valid_o(result_valid),
    .acc_exception_o(exception_out), .acc_valid_ex_o(), .commit_ack_i(ack),
    .commit_st_barrier_i(1'b0), .acc_stall_st_pending_o(), .acc_no_st_pending_i(1'b1),
    .dcache_req_ports_i('0), .acc_mmu_req_o(), .acc_mmu_resp_i('0), .ctrl_halt_o(),
    .csr_addr_i('0), .flush_unissued_instr_i(flush), .flush_ex_i(flush),
    .flush_pipeline_o(), .single_step_o(), .acc_dcache_req_ports_o(),
    .acc_dcache_req_ports_i('0), .inval_ready_i(1'b1), .inval_valid_o(),
    .inval_addr_o(), .acc_req_o(req), .acc_resp_i(resp)
  );

  function automatic fu_op operation(int k);
    case (k)
      1: return ACCEL_OP_LOAD;
      2: return ACCEL_OP_STORE;
      default: return ACCEL_OP;
    endcase
  endfunction

  function automatic int memory_kind(fu_op op);
    if (op == ACCEL_OP_LOAD) return 1;
    if (op == ACCEL_OP_STORE) return 2;
    return 0;
  endfunction

  function automatic logic [31:0] instruction(int s, int k);
    case (k)
      1: return 32'h02006007 | (s << 7);
      2: return 32'h02006027 | (s << 7);
      default: return 32'h02000057 | (s << 7);
    endcase
  endfunction

  function automatic fu_data_t payload(int s, int id, int k);
    fu_data_t data;
    data = '0;
    data.fu = ACCEL;
    data.operation = operation(k);
    data.operand_a = s;
    data.operand_b = 64'hcafe0000 + s;
    data.imm = instruction(s, k);
    data.trans_id = CVA6Cfg.TRANS_ID_BITS'(id);
    return data;
  endfunction

  task automatic field(string name, logic [63:0] value);
    if ($isunknown(value)) $fatal(1, "CONTRACT_FAIL unknown probe %s cycle=%0d", name, cycle);
    $fwrite(trace_fd, ",\"%s\":%0d", name, value);
  endtask

  task automatic trace_edge;
    $fwrite(trace_fd, "{\"phase\":\"pre\",\"label\":\"%s\"", label);
    field("cycle", cycle); field("epoch", 1);
    field("hs", issue_hs); field("accept", dut.acc_valid_d);
    field("seq", seq); field("id", issue.trans_id); field("pc", issue.pc);
    field("kind", memory_kind(issue.op)); field("view", view);
    field("issue_fu", issue.fu); field("issue_op", issue.op);
    field("cons", cons); field("stall", stall);
    field("ex_valid", dut.acc_valid_q); field("ex_seq", execute_data.operand_a);
    field("ex_id", execute_data.trans_id); field("ex_kind", memory_kind(execute_data.operation));
    field("usage", dut.acc_insn_queue_usage); field("empty", dut.acc_insn_queue_empty);
    field("head_seq", dut.acc_insn_queue_o.operand_a);
    field("head_id", dut.acc_insn_queue_o.trans_id);
    field("head_kind", memory_kind(dut.acc_insn_queue_o.operation));
    field("head_insn", dut.acc_insn_queue_o.imm[31:0]);
    field("head_rs2", dut.acc_insn_queue_o.operand_b);
    field("c0_acc", commits[0].fu == ACCEL); field("c0_valid", commits[0].valid);
    field("c0_id", commits[0].trans_id); field("ack0", ack[0]);
    field("c1_acc", commits[1].fu == ACCEL); field("c1_valid", commits[1].valid);
    field("c1_id", commits[1].trans_id); field("commit", dut.acc_commit);
    field("commit_id", dut.acc_commit_trans_id);
    field("pending", dut.insn_pending_q); field("pending_next", dut.insn_pending_d);
    field("authorized", dut.insn_ready_q); field("authorized_next", dut.insn_ready_d);
    field("flush", flush); field("in_valid", dut.acc_req_valid);
    field("in_ready", dut.acc_req_ready); field("pop", dut.acc_insn_queue_pop);
    field("ld_pop", dut.acc_ld_disp); field("st_pop", dut.acc_st_disp);
    field("a_full", dut.i_accelerator_req_register.spill_register_flushable_i.gen_spill_reg.a_full_q);
    field("b_full", dut.i_accelerator_req_register.spill_register_flushable_i.gen_spill_reg.b_full_q);
    field("out_valid", req.acc_req.req_valid); field("out_ready", resp.acc_resp.req_ready);
    field("out_fire", req.acc_req.req_valid && resp.acc_resp.req_ready);
    field("out_seq", req.acc_req.rs1); field("out_id", req.acc_req.trans_id);
    field("out_insn", req.acc_req.insn); field("out_rs2", req.acc_req.rs2);
    field("out_frm", req.acc_req.frm);
    field("spec_ld", dut.acc_spec_loads_pending); field("disp_ld", dut.acc_disp_loads_pending);
    field("spec_st", dut.acc_spec_stores_pending); field("disp_st", dut.acc_disp_stores_pending);
    field("no_ld", dut.acc_no_ld_pending); field("no_st", dut.acc_no_st_pending);
    field("ld_done", resp.acc_resp.load_complete); field("st_done", resp.acc_resp.store_complete);
    field("resp_valid", resp.acc_resp.resp_valid); field("resp_seq", resp.acc_resp.result);
    field("resp_id", resp.acc_resp.trans_id); field("resp_flags", resp.acc_resp.fflags);
    field("resp_flags_valid", resp.acc_resp.fflags_valid);
    field("result_valid", result_valid); field("result_seq", result_data);
    field("result_id", result_id); field("result_flags", fflags);
    field("result_flags_valid", fflags_valid); field("exception", exception_out);
    field("resp_ready", req.acc_req.resp_ready);
    $fwrite(trace_fd, "}\n");
  endtask

  initial begin
    #3000;
    $fatal(1, "CONTRACT_FAIL watchdog");
  end

  initial begin
    issue = '0; commits = '0; execute_data = '0; pipeline_data = payload(99, 7, 2);
    resp = '0; issue_hs = 0; cons = 1; flush = 0; ack = '0;
    if (CVA6Cfg.XLEN != 64 || CVA6Cfg.NrCommitPorts != 2 ||
        CVA6Cfg.NR_SB_ENTRIES != 8 || CVA6Cfg.FpgaEn || !CVA6Cfg.EnableAccelerator)
      $fatal(1, "CONTRACT_FAIL unexpected real configuration");
    if (!$value$plusargs("STIMULUS=%s", stimulus_path))
      $fatal(1, "CONTRACT_FAIL missing stimulus");
    fd = $fopen(stimulus_path, "r");
    trace_fd = $fopen("trace.jsonl", "w");
    config_fd = $fopen("config.json", "w");
    if (!fd || !trace_fd || !config_fd) $fatal(1, "CONTRACT_FAIL file open");
    $fwrite(config_fd, "{\"xlen\":%0d,\"ids\":%0d,\"ports\":%0d,\"fpga\":%0d,\"accel\":%0d,\"load\":%0d,\"store\":%0d,\"ctrl\":%0d,\"fences\":[%0d,%0d,%0d,%0d,%0d]}\n",
        CVA6Cfg.XLEN, CVA6Cfg.NR_SB_ENTRIES, CVA6Cfg.NrCommitPorts, CVA6Cfg.FpgaEn,
        ACCEL, LOAD, STORE, CTRL_FLOW, FENCE, FENCE_I, SFENCE_VMA, HFENCE_VVMA, HFENCE_GVMA);
    $fclose(config_fd);
    repeat (2) @(posedge clk);
    @(negedge clk);
    rst_n = 1;
    forever begin
      scanned = $fscanf(fd, "%s %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
          label, seq, ident, kind, view, consistency, c0_acc, c0_valid, c0_id,
          c1_acc, c1_valid, c1_id, ack0, flush_value, ready_value,
          resp_seq, resp_id, ld_done, st_done);
      if (scanned == -1) break;
      if (scanned != 19 || cycle >= 256) $fatal(1, "CONTRACT_FAIL stimulus/bound");
      execute_data = pipeline_data;
      pipeline_data = seq ? payload(seq, ident, kind) : payload(99, 7, 2);
      issue = '0;
      issue.trans_id = CVA6Cfg.TRANS_ID_BITS'(ident);
      issue.pc = seq ? 64'h80000000 + 4 * seq : 0;
      issue.fu = ALU; issue.op = ADD;
      case (view)
        1: begin issue.fu = ACCEL; issue.op = operation(kind); end
        2: begin issue.fu = LOAD; issue.op = LD; end
        3: begin issue.fu = STORE; issue.op = SD; end
        4: begin issue.fu = CTRL_FLOW; issue.op = FENCE; end
        5: begin issue.fu = CTRL_FLOW; issue.op = FENCE_I; end
        6: begin issue.fu = CTRL_FLOW; issue.op = SFENCE_VMA; end
        7: begin issue.fu = CTRL_FLOW; issue.op = HFENCE_VVMA; end
        8: begin issue.fu = CTRL_FLOW; issue.op = HFENCE_GVMA; end
      endcase
      issue_hs = seq != 0;
      cons = 1'(consistency); flush = 1'(flush_value); ack = '0; ack[0] = 1'(ack0);
      commits = '0;
      commits[0].fu = c0_acc ? ACCEL : ALU;
      commits[0].valid = 1'(c0_valid); commits[0].trans_id = CVA6Cfg.TRANS_ID_BITS'(c0_id);
      commits[1].fu = c1_acc ? ACCEL : ALU;
      commits[1].valid = 1'(c1_valid); commits[1].trans_id = CVA6Cfg.TRANS_ID_BITS'(c1_id);
      resp = '0;
      resp.acc_resp.req_ready = 1'(ready_value);
      resp.acc_resp.resp_valid = resp_seq != 0;
      resp.acc_resp.trans_id = CVA6Cfg.TRANS_ID_BITS'(resp_id);
      resp.acc_resp.result = 64'(resp_seq);
      resp.acc_resp.fflags = resp_seq ? 5'h15 : 0;
      resp.acc_resp.fflags_valid = resp_seq != 0;
      resp.acc_resp.load_complete = 1'(ld_done); resp.acc_resp.store_complete = 1'(st_done);
      @(posedge clk);
      cycle++;
      if (issue_hs && stall) $fatal(1, "CONTRACT_FAIL upstream violated issue stall");
      trace_edge();
      #1;
      @(negedge clk);
    end
    if (cycle == 0) $fatal(1, "CONTRACT_FAIL empty stimulus");
    $fclose(fd); $fclose(trace_fd);
    $display("CVA6_CONTRACT_COMPLETE cycles=%0d", cycle);
    $finish;
  end
endmodule
