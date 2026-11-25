`timescale 1ns/1ps
`include "rvfi_types.svh"
`include "ara/intf_typedef.svh"

module akv_gate_tb;
  import ariane_pkg::*;
  import riscv::*;
  function automatic config_pkg::cva6_cfg_t configuration(input bit generic_cvxif);
    config_pkg::cva6_cfg_t c;
    c = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
    c.NrPMPEntries = 0;
    c.EnableAccelerator = !generic_cvxif;
    c.CvxifEn = generic_cvxif;
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg = configuration(0);
  localparam config_pkg::cva6_cfg_t CvxifCfg = configuration(1);
  `include "gate_types.svh"
  typedef `RVFI_PROBES_CSR_T(CVA6Cfg) rvfi_t;
  `CVA6_INTF_TYPEDEF_ACC_REQ(accelerator_req_t, CVA6Cfg, fpnew_pkg::roundmode_e)
  `CVA6_INTF_TYPEDEF_ACC_RESP(accelerator_resp_t, CVA6Cfg, exception_t)
  `CVA6_INTF_TYPEDEF_MMU_REQ(acc_mmu_req_t, CVA6Cfg)
  `CVA6_INTF_TYPEDEF_MMU_RESP(acc_mmu_resp_t, CVA6Cfg, exception_t)
  `CVA6_INTF_TYPEDEF_CVA6_TO_ACC(acc_req_t, accelerator_req_t, acc_mmu_resp_t)
  `CVA6_INTF_TYPEDEF_ACC_TO_CVA6(acc_resp_t, accelerator_resp_t, acc_mmu_req_t)

  bit clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, allowed, csr_flush, eret, flush_if, flush_id, flush_ex, flush_unissued;
  logic issue_hs = 0, request_ready = 1, fire_permitted = 0;
  fu_op csr_op = ADD;
  logic [11:0] csr_address = 0;
  logic [63:0] csr_wdata = 0, csr_rdata;
  logic [31:0] instruction = 32'h0005455b;
  exception_t csr_exception;
  priv_lvl_t privilege, memory_privilege;
  xs_t fs, vs;
  irq_ctrl_t irq_control;
  scoreboard_entry_t decoded, baseline, generic_decoded, generic_baseline, issue;
  scoreboard_entry_t [CVA6Cfg.NrCommitPorts-1:0] commits = '0;
  fu_data_t execute_data;
  acc_req_t req;
  acc_resp_t resp;
  int unsigned checks = 0, decode_cases = 0, blocked_cases = 0, request_count = 0;
  int unsigned noissue_cases = 0, csr_cases = 0, flush_cases = 0;
  int unsigned id_decode_cases = 0, id_register_cases = 0;
  fetch_entry_t [CVA6Cfg.NrIssuePorts-1:0] stage_fetch;
  scoreboard_entry_t [CVA6Cfg.NrIssuePorts-1:0] stage_issue;
  logic [CVA6Cfg.NrIssuePorts-1:0] stage_valid = '0, stage_ack = '0;
  logic [CVA6Cfg.NrIssuePorts-1:0] stage_ready, stage_issue_valid;

  always_comb begin
    stage_fetch = '0;
    stage_fetch[0].instruction = instruction;
    stage_fetch[0].address = 64'h80000200;
  end

  id_stage #(.CVA6Cfg(CVA6Cfg), .branchpredict_sbe_t(branchpredict_sbe_t),
      .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t),
      .exception_t(exception_t), .fetch_entry_t(fetch_entry_t), .jvt_t(jvt_t),
      .irq_ctrl_t(irq_ctrl_t), .scoreboard_entry_t(scoreboard_entry_t), .interrupts_t(interrupts_t)) id_path (
      .clk_i(clk), .rst_ni(rst_n), .flush_i(flush_if), .debug_req_i(1'b0),
      .fetch_entry_i(stage_fetch), .fetch_entry_valid_i(stage_valid), .fetch_entry_ready_o(stage_ready),
      .issue_entry_o(stage_issue), .issue_entry_valid_o(stage_issue_valid), .issue_instr_ack_i(stage_ack),
      .priv_lvl_i(privilege), .akv_access_allowed_i(allowed), .v_i(1'b0), .fs_i(fs), .vfs_i(Off),
      .frm_i('0), .vs_i(vs), .irq_i('0), .irq_ctrl_i(irq_control), .clic_mode_i(1'b0),
      .clic_irq_req_i(1'b0), .clic_irq_cause_i('0), .debug_mode_i(1'b0), .tvm_i(1'b0),
      .tw_i(1'b0), .vtw_i(1'b0), .tsr_i(1'b0), .hu_i(1'b0), .hart_id_i('0),
      .compressed_ready_i(1'b1), .jvt_i('0), .compressed_resp_i('0), .dcache_req_ports_i('0));

  task automatic check(input logic condition, input string message);
    checks++;
    if (condition !== 1'b1)
      $fatal(1, "GATE_FAIL check=%0d priv=%0d insn=%08h: %s", checks, privilege, instruction, message);
  endtask

  csr_regfile #(.CVA6Cfg(CVA6Cfg), .exception_t(exception_t), .jvt_t(jvt_t),
      .irq_ctrl_t(irq_ctrl_t), .scoreboard_entry_t(scoreboard_entry_t), .rvfi_probes_csr_t(rvfi_t)) csr (
      .clk_i(clk), .rst_ni(rst_n), .time_irq_i(1'b0), .commit_instr_i('0), .commit_ack_i('0),
      .boot_addr_i(64'h80000000), .hart_id_i('0), .ex_i('0), .csr_op_i(csr_op),
      .csr_addr_i(csr_address), .csr_wdata_i(csr_wdata), .csr_rdata_o(csr_rdata),
      .dirty_fp_state_i(1'b0), .csr_write_fflags_i(1'b0), .dirty_v_state_i(1'b0),
      .pc_i(64'h80000100), .csr_exception_o(csr_exception), .eret_o(eret), .flush_o(csr_flush),
      .priv_lvl_o(privilege), .ld_st_priv_lvl_o(memory_privilege), .akv_access_allowed_o(allowed),
      .fs_o(fs), .vs_o(vs), .irq_ctrl_o(irq_control), .acc_fflags_ex_i('0),
      .acc_fflags_ex_valid_i(1'b0), .csr_hs_ld_st_inst_i(1'b0), .irq_i('0),
      .clic_irq_req_i(1'b0), .clic_irq_shv_i(1'b0), .ipi_i(1'b0), .debug_req_i(1'b0),
      .fence_t_ceil_i('0), .perf_data_i('0));

`define DECODE(NAME, CONFIG, OUT, PERMISSION) \
  decoder #(.CVA6Cfg(CONFIG), .branchpredict_sbe_t(branchpredict_sbe_t), \
      .exception_t(exception_t), .irq_ctrl_t(irq_ctrl_t), .scoreboard_entry_t(scoreboard_entry_t), \
      .interrupts_t(interrupts_t)) NAME ( \
      .debug_req_i(1'b0), .pc_i(64'h80000200), .is_compressed_i(1'b0), .compressed_instr_i('0), \
      .is_illegal_i(1'b0), .instruction_i(instruction), .is_macro_instr_i(1'b0), \
      .is_last_macro_instr_i(1'b0), .is_double_rd_macro_instr_i(1'b0), .is_zcmt_i(1'b0), \
      .jump_address_i('0), .branch_predict_i('0), .ex_i('0), .irq_i('0), .irq_ctrl_i(irq_control), \
      .clic_mode_i(1'b0), .clic_irq_req_i(1'b0), .clic_irq_cause_i('0), .priv_lvl_i(privilege), \
      PERMISSION .v_i(1'b0), .debug_mode_i(1'b0), .fs_i(fs), .vfs_i(Off), .frm_i('0), .vs_i(vs), \
      .tvm_i(1'b0), .tw_i(1'b0), .vtw_i(1'b0), .tsr_i(1'b0), .hu_i(1'b0), .instruction_o(OUT));
`define GATE_PERMISSION .akv_access_allowed_i(allowed),
  `DECODE(gated_decoder, CVA6Cfg, decoded, `GATE_PERMISSION)
  `DECODE(legacy_default_decoder, CVA6Cfg, baseline, )
  `DECODE(generic_decoder, CvxifCfg, generic_decoded, `GATE_PERMISSION)
  `DECODE(generic_default_decoder, CvxifCfg, generic_baseline, )
`undef DECODE
`undef GATE_PERMISSION

  controller #(.CVA6Cfg(CVA6Cfg), .bp_resolve_t(bp_resolve_t)) control (
      .clk_i(clk), .rst_ni(rst_n), .v_i(1'b0), .flush_if_o(flush_if), .flush_id_o(flush_id),
      .flush_unissued_instr_o(flush_unissued), .flush_ex_o(flush_ex), .flush_dcache_ack_i(1'b0),
      .boot_addr_i(64'h80000000), .pc_commit_i(64'h80000100), .halt_csr_i(1'b0), .halt_acc_i(1'b0),
      .cache_busy_i(1'b0), .fence_t_pad_i('0), .fence_t_src_sel_i(1'b0), .time_irq_i(1'b0),
      .priv_lvl_i(privilege), .eret_i(eret), .ex_valid_i(1'b0), .set_debug_pc_i(1'b0),
      .resolved_branch_i('0), .flush_csr_i(csr_flush), .fence_i_i(1'b0), .fence_i(1'b0),
      .fence_t_i(1'b0), .sfence_vma_i(1'b0), .hfence_vvma_i(1'b0), .hfence_gvma_i(1'b0),
      .flush_commit_i(1'b0), .flush_acc_i(1'b0));

  always_comb begin
    issue = decoded;
    issue.trans_id = CVA6Cfg.TRANS_ID_BITS'(1);
    resp = '0;
    resp.acc_resp.req_ready = request_ready;
  end
  always @(posedge clk) begin
    execute_data <= '{fu: issue.fu, operation: issue.op, operand_a: 64'h12345678,
                      operand_b: 64'habcdef00, imm: issue.result, trans_id: issue.trans_id};
    if (rst_n && req.acc_req.req_valid && request_ready) begin
      if (!fire_permitted) $fatal(1, "GATE_FAIL unauthorized accelerator request");
      request_count <= request_count + 1;
    end
  end
  acc_dispatcher #(.CVA6Cfg(CVA6Cfg), .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t),
      .exception_t(exception_t), .fu_data_t(fu_data_t), .scoreboard_entry_t(scoreboard_entry_t),
      .acc_req_t(acc_req_t), .acc_resp_t(acc_resp_t), .accelerator_req_t(accelerator_req_t),
      .accelerator_resp_t(accelerator_resp_t), .acc_mmu_req_t(acc_mmu_req_t),
      .acc_mmu_resp_t(acc_mmu_resp_t)) dispatch (
      .clk_i(clk), .rst_ni(rst_n), .acc_cons_en_i(1'b1), .ld_st_priv_lvl_i(memory_privilege),
      .sum_i(1'b0), .pmpcfg_i('0), .pmpaddr_i('0), .fcsr_frm_i('0), .acc_mmu_en_i(1'b0),
      .issue_instr_i(issue), .issue_instr_hs_i(issue_hs), .fu_data_i(execute_data),
      .commit_instr_i(commits), .commit_ack_i('0), .commit_st_barrier_i(1'b0),
      .acc_no_st_pending_i(1'b1), .dcache_req_ports_i('0), .acc_mmu_resp_i('0), .csr_addr_i('0),
      .flush_unissued_instr_i(flush_unissued), .flush_ex_i(flush_ex), .acc_dcache_req_ports_i('0),
      .inval_ready_i(1'b1), .acc_req_o(req), .acc_resp_i(resp));

  task automatic tick;
    @(posedge clk); #1; @(negedge clk); #1;
  endtask
  task automatic idle;
    csr_op = ADD; issue_hs = 0; commits = '0;
    stage_valid = '0; stage_ack = '0;
  endtask
  task automatic reset;
    @(negedge clk); idle(); rst_n = 0; request_ready = 1; fire_permitted = 0;
    repeat (3) tick();
    rst_n = 1; tick();
    check(privilege == PRIV_LVL_M && allowed, "reset must retain legacy access");
  endtask
  task automatic csr_access(input fu_op op, input logic [11:0] address,
                            input logic [63:0] data, input bit legal, input bit flush_expected);
    csr_op = op; csr_address = address; csr_wdata = data; #1;
    check(csr_exception.valid == !legal, "CSR privilege/availability exception");
    if (!legal) check(csr_exception.cause == ILLEGAL_INSTR, "CSR illegal cause");
    check(csr_flush == flush_expected, "CSR serialization flush");
    if (flush_expected)
      check(flush_if && flush_id && flush_ex && flush_unissued, "all younger pipeline stages must flush");
    tick(); csr_op = ADD; #1; csr_cases++;
  endtask
  task automatic read_control(input logic [2:0] control);
    csr_op = CSR_READ; csr_address = 12'h5c0; #1;
    check(!csr_exception.valid && !csr_flush && csr_rdata == (64'h414b560100000000 | 64'(control)),
          "signature/reserved bits/control readback");
    csr_op = ADD;
  endtask
  task automatic setup(input logic [2:0] control, input priv_lvl_t target, input bit mprv = 0);
    logic [63:0] status;
    reset(); read_control(0);
    csr_access(CSR_WRITE, 12'h5c0, 64'hfedcba98fffffff8 | 64'(control), 1, 1);
    read_control(control);
    status = (64'd3 << 13) | (64'd3 << 9) | (64'(target == PRIV_LVL_M ? 0 : target) << 11) |
             (64'(mprv) << 17);
    csr_access(CSR_WRITE, riscv::CSR_MSTATUS, status, 1, 1);
    if (target != PRIV_LVL_M) begin
      csr_op = MRET; tick(); csr_op = ADD; tick();
    end
    check(privilege == target, "actual execution privilege setup");
    if (target == PRIV_LVL_M && mprv)
      check(memory_privilege == PRIV_LVL_U && allowed, "MPRV memory privilege must not revoke trusted M execution");
    check(allowed == (!control[0] || target == PRIV_LVL_M ||
          (target == PRIV_LVL_S && control[2]) || (target == PRIV_LVL_U && control[1])), "permission truth table");
  endtask
  task automatic check_decode;
    bit denied;
    #1;
    check(id_path.decoded_instruction[0] === decoded, "real ID-stage permission/first-pass path differs from direct decoder");
    id_decode_cases++;
    denied = !allowed && instruction[6:0] == 7'h5b && instruction[14:12] >= 2;
    if (denied) begin
      check(decoded.ex.valid && decoded.ex.cause == ILLEGAL_INSTR && decoded.fu == NONE,
            "blocked AKV must be illegal before accelerator classification escapes");
      check(decoded.ex.tval == 64'(instruction) && decoded.rs1 == 0 && decoded.rs2 == 0 && decoded.rd == 0,
            "blocked AKV tval/dependencies");
      check(generic_decoded.ex.valid && generic_decoded.ex.cause == ILLEGAL_INSTR && generic_decoded.fu == NONE,
            "generic CVXIF must not recapture blocked AKV");
      blocked_cases++;
    end else begin
      check(decoded === baseline, "allowed/default or RVV/QBS decode changed");
      check(generic_decoded === generic_baseline, "generic CVXIF/default compatibility changed");
    end
    decode_cases++;
  endtask
  task automatic noissue;
    int unsigned before_count;
    before_count = request_count;
    check(decoded.ex.valid, "noissue stimulus must really be rejected");
    issue_hs = 1; #1;
    check(!dispatch.acc_valid_d, "real dispatcher must reject even a forced exception handshake");
    tick(); issue_hs = 0;
    repeat (4) tick();
    check(!req.acc_req.req_valid && request_count == before_count && dispatch.acc_insn_queue_empty,
          "rejected instruction reached queue/output");
    noissue_cases++;
  endtask
  task automatic inject_info(input bit authorize, input bit stall_output = 0);
    instruction = 32'h0005455b; #1;
    check(!decoded.ex.valid && decoded.fu == ACCEL, "allowed INFO must decode through the real first-pass module");
    request_ready = !stall_output;
    issue_hs = 1; tick(); issue_hs = 0; tick();
    if (authorize) begin
      commits[0] = issue; commits[0].valid = 0;
      fire_permitted = 1;
    end
  endtask

  task automatic stage_capture(input bit denied);
    instruction = 32'h0005455b;
    stage_ack = '0; stage_valid[0] = 1;
    #1; check(stage_ready[0] && !flush_if, "ID-stage fetch handshake unavailable");
    tick(); stage_valid = '0;
    check(stage_issue_valid[0], "real ID-stage register did not capture instruction");
    if (denied)
      check(stage_issue[0].ex.valid && stage_issue[0].ex.cause == ILLEGAL_INSTR &&
            stage_issue[0].fu == NONE && stage_issue[0].ex.tval == 64'h0005455b,
            "ID-stage register lost permission-denial exception");
    else
      check(!stage_issue[0].ex.valid && stage_issue[0].fu == ACCEL, "ID-stage register lost allowed INFO");
    stage_ack[0] = 1; tick(); stage_ack = '0;
    check(!stage_issue_valid[0], "ID-stage issue acknowledgment failed");
    id_register_cases++;
  endtask

  initial begin : test
    priv_lvl_t target;
    int unsigned before_count;
    if (CVA6Cfg.XLEN != 64 || CVA6Cfg.RVH || !CVA6Cfg.EnableAccelerator)
      $fatal(1, "Only actual RV64 no-H accelerator configuration is claimed");
    for (int control_bits = 0; control_bits < 8; control_bits++) begin
      for (int p = 0; p < 3; p++) begin
        target = p == 0 ? PRIV_LVL_U : p == 1 ? PRIV_LVL_S : PRIV_LVL_M;
        setup(3'(control_bits), target, p == 2);
        for (int f3 = 0; f3 < 8; f3++)
          for (int f7 = 0; f7 < 128; f7++) begin
            instruction = (32'(f7) << 25) | (32'd11 << 20) | (32'd10 << 15) |
                          (32'(f3) << 12) | (32'd10 << 7) | 32'h5b;
            check_decode();
          end
        instruction = 32'h02000057; check_decode();
        instruction = 32'h0c007557; check_decode();
        instruction = 32'h02055087; check_decode();
        instruction = 32'h020550a7; check_decode();
        if (!allowed) begin
          for (int f3 = 2; f3 < 8; f3++) begin
            instruction = (32'(f3) << 12) | 32'h5b; #1; noissue();
          end
        end
        if (target == PRIV_LVL_U) begin
          for (int operation = 0; operation < 4; operation++)
            case (operation)
              0: csr_access(CSR_READ, 12'h5c0, 0, 0, 0);
              1: csr_access(CSR_WRITE, 12'h5c0, 7, 0, 0);
              2: csr_access(CSR_SET, 12'h5c0, 7, 0, 0);
              3: csr_access(CSR_CLEAR, 12'h5c0, 7, 0, 0);
            endcase
          check(allowed == (!control_bits[0] || control_bits[1]), "U CSR access changed permission");
        end else begin
          csr_access(CSR_SET, 12'h5c0, 7, 1, 1); read_control(7);
          csr_access(CSR_CLEAR, 12'h5c0, 6, 1, 1); read_control(1);
          csr_access(CSR_WRITE, 12'h5c0, 0, 1, 1); read_control(0);
        end
      end
    end

    // A decoded younger instruction waits behind the older CSR and is flushed.
    setup(7, PRIV_LVL_S);
    before_count = request_count;
    commits[0].fu = CSR; commits[0].valid = 1;
    inject_info(0);
    repeat (3) tick();
    check(!dispatch.acc_insn_queue_empty && !req.acc_req.req_valid, "younger request escaped before CSR commit");
    csr_access(CSR_WRITE, 12'h5c0, 1, 1, 1);
    check(!allowed && decoded.ex.valid, "revocation must apply after the CSR edge");
    commits[0] = issue; commits[0].fu = ACCEL; commits[0].valid = 0;
    repeat (5) tick();
    check(dispatch.acc_insn_queue_empty && !req.acc_req.req_valid && request_count == before_count,
          "stale decoded/queued permission survived CSR flush");
    noissue(); flush_cases++;

    // Committed older work keeps its authorization across a later revocation.
    setup(7, PRIV_LVL_S);
    before_count = request_count;
    inject_info(1, 1);
    repeat (6) tick();
    check(req.acc_req.req_valid && req.acc_req.insn == 32'h0005455b, "older authorized request not retained");
    csr_access(CSR_WRITE, 12'h5c0, 1, 1, 1);
    check(!allowed && req.acc_req.req_valid && req.acc_req.insn == 32'h0005455b,
          "permission was incorrectly gated asynchronously after authorization");
    request_ready = 1; repeat (4) tick();
    check(request_count == before_count + 1 && !req.acc_req.req_valid, "older authorized request lost or duplicated");
    flush_cases++;

    // Exercise the real ID/issue register in all three execution privileges.
    setup(1, PRIV_LVL_M); stage_capture(0);
    setup(1, PRIV_LVL_S); stage_capture(1);
    setup(1, PRIV_LVL_U); stage_capture(1);
    setup(5, PRIV_LVL_S); stage_capture(0);
    setup(3, PRIV_LVL_U); stage_capture(0);

    // An allowed instruction already held in ID must not survive revocation.
    setup(7, PRIV_LVL_S);
    instruction = 32'h0005455b; stage_valid[0] = 1; tick(); stage_valid = '0;
    check(stage_issue_valid[0] && stage_issue[0].fu == ACCEL, "stale-ID stimulus did not capture allowed INFO");
    csr_access(CSR_WRITE, 12'h5c0, 1, 1, 1);
    check(!allowed && !stage_issue_valid[0], "CSR flush retained stale permission in ID register");
    id_register_cases++;
    stage_capture(1);

    // Fetch on the same edge as the CSR update must also be discarded.
    csr_access(CSR_WRITE, 12'h5c0, 7, 1, 1);
    stage_valid[0] = 1;
    csr_access(CSR_WRITE, 12'h5c0, 1, 1, 1); stage_valid = '0;
    check(!stage_issue_valid[0], "same-edge fetch survived permission-update flush");
    id_register_cases++;
    csr_access(CSR_WRITE, 12'h5c0, 5, 1, 1); stage_capture(0);

    check(id_decode_cases == 24672 && id_register_cases == 9, "ID-stage coverage cardinality");
    $display("ID_GATE_PASS decode=%0d registered=%0d", id_decode_cases, id_register_cases);
    check(decode_cases == 24672 && blocked_cases == 3072 && noissue_cases == 25 && flush_cases == 2,
          "coverage cardinality");
    $display("GATE_PASS decode=%0d blocked=%0d noissue=%0d csr=%0d flush=%0d requests=%0d checks=%0d",
             decode_cases, blocked_cases, noissue_cases, csr_cases, flush_cases, request_count, checks);
    $finish;
  end
  initial begin #1000000; $fatal(1, "GATE_FAIL bounded watchdog"); end
endmodule
