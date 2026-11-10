`timescale 1ns/1ps
module commit_dirty_tb;
  import ariane_pkg::*;

  function automatic config_pkg::cva6_cfg_t configuration(input bit wb);
    config_pkg::cva6_cfg_t c;
    c = config_pkg::cva6_cfg_empty;
    c.XLEN = 64;
    c.VLEN = 64;
    c.GPLEN = 41;
    c.TRANS_ID_BITS = 3;
    c.NrCommitPorts = 2;
    c.FpPresent = 1;
    c.RVF = 1;
    c.RVA = 1;
    c.RVS = 1;
    c.DCacheType = wb ? config_pkg::WB : config_pkg::WT;
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t Cfg = configuration(0);
  localparam config_pkg::cva6_cfg_t CfgWb = configuration(1);

  typedef struct packed {
    logic [63:0] cause, tval;
    logic [40:0] tval2;
    logic [31:0] tinst;
    logic gva, valid;
  } exception_t;
  // commit_stage is type-parametric; these are all of its entry fields.
  typedef struct packed {
    logic [63:0] pc;
    logic [2:0] trans_id;
    fu_t fu;
    fu_op op;
    logic [4:0] rd;
    logic [63:0] result;
    logic valid;
    exception_t ex;
    logic is_macro_instr, is_last_macro_instr, vfp;
  } entry_t;
  typedef struct packed {
    exception_t exception;
    logic dirty;
    logic [1:0] ack, macro_ack;
    logic [1:0][4:0] waddr;
    logic [1:0][63:0] wdata;
    logic [1:0] we_gpr, we_fpr;
    logic [63:0] pc;
    fu_op csr_op;
    logic [63:0] csr_wdata;
    logic fflags, lsu;
    logic [2:0] trans_id;
    logic amo, csr, fence_i, fence, fence_t, flush, sfence, hfence_vv, hfence_g;
  } outputs_t;

  bit clk = 0;
  always #5 clk = ~clk;
  logic rst_n, halt, flush_dcache, single_step, lsu_ready, no_st_pending;
  logic [1:0] drop;
  logic [63:0] csr_rdata;
  amo_resp_t amo_resp;
  exception_t csr_exception;
  entry_t [1:0] entries;
  outputs_t before_o, after_o, before_wb, after_wb;
  int unsigned checks = 0, original_failures = 0, wb_original_failures = 0;

`define INSTANCE(MODULE, NAME, O, CONFIG) \
  MODULE #(.CVA6Cfg(CONFIG), .exception_t(exception_t), .scoreboard_entry_t(entry_t)) NAME ( \
    .clk_i(clk), .rst_ni(rst_n), .halt_i(halt), .flush_dcache_i(flush_dcache), \
    .single_step_i(single_step), .commit_instr_i(entries), .commit_drop_i(drop), \
    .amo_resp_i(amo_resp), .csr_rdata_i(csr_rdata), .csr_exception_i(csr_exception), \
    .commit_lsu_ready_i(lsu_ready), .no_st_pending_i(no_st_pending), \
    .exception_o(O.exception), .dirty_fp_state_o(O.dirty), .commit_ack_o(O.ack), \
    .commit_macro_ack_o(O.macro_ack), .waddr_o(O.waddr), .wdata_o(O.wdata), \
    .we_gpr_o(O.we_gpr), .we_fpr_o(O.we_fpr), .pc_o(O.pc), .csr_op_o(O.csr_op), \
    .csr_wdata_o(O.csr_wdata), .csr_write_fflags_o(O.fflags), .commit_lsu_o(O.lsu), \
    .commit_tran_id_o(O.trans_id), .amo_valid_commit_o(O.amo), .commit_csr_o(O.csr), \
    .fence_i_o(O.fence_i), .fence_o(O.fence), .fence_t_o(O.fence_t), \
    .flush_commit_o(O.flush), .sfence_vma_o(O.sfence), \
    .hfence_vvma_o(O.hfence_vv), .hfence_gvma_o(O.hfence_g));

  `INSTANCE(commit_stage_before, i_before, before_o, Cfg)
  `INSTANCE(commit_stage, i_after, after_o, Cfg)
  `INSTANCE(commit_stage_before, i_before_wb, before_wb, CfgWb)
  `INSTANCE(commit_stage, i_after_wb, after_wb, CfgWb)
`undef INSTANCE

  task automatic defaults();
    @(negedge clk);
    rst_n = 1;
    halt = 0;
    flush_dcache = 0;
    single_step = 0;
    lsu_ready = 1;
    no_st_pending = 1;
    drop = 0;
    csr_rdata = 64'h12345678;
    amo_resp = '0;
    csr_exception = '0;
    entries = '0;
    for (int p = 0; p < 2; p++) begin
      entries[p].pc = 64'h80000268 + 4*p;
      entries[p].trans_id = 3'(p+1);
      entries[p].fu = ALU;
      entries[p].op = ADD;
      entries[p].rd = 5'(p+3);
      entries[p].result = 64'h0123456789abcdef + p;
    end
  endtask

  task automatic accel(input int p);
    entries[p].valid = 1;
    entries[p].fu = ACCEL;
    entries[p].op = ACCEL_OP_LOAD;  // Exact resident-PV first-pass classification.
    entries[p].vfp = 1;
  endtask

  task automatic fp(input int p, input fu_op op, input logic [4:0] flags);
    entries[p].valid = 1;
    entries[p].fu = FPU;
    entries[p].op = op;
    entries[p].ex.cause = {59'b0, flags};
  endtask

  task automatic check_case(input string name, input logic [1:0] ack,
                            input bit dirty, input bit fflags,
                            input logic [4:0] flags, input bit old_bug = 0);
    outputs_t a, b;
    logic [1:0] wb_ack;
    bit wb_dirty, wb_bug;
    #1;
    wb_ack = name == "flush_cache_contract" ? 2'b00 : ack;
    wb_dirty = name == "flush_cache_contract" ? 1'b0 : dirty;
    wb_bug = old_bug || name == "flush_cache_contract";
    if (after_o.ack !== ack || before_o.ack !== ack || after_o.dirty !== dirty ||
        after_o.fflags !== fflags || (fflags && after_o.csr_wdata !== {59'b0, flags}))
      $fatal(1, "contract name=%s ack=%b/%b dirty=%b/%b flags=%b:%h", name,
             after_o.ack, ack, after_o.dirty, dirty, after_o.fflags, after_o.csr_wdata);
    if (before_o.dirty !== (old_bug ? 1'b1 : dirty))
      $fatal(1, "original prediction name=%s old=%b expected=%b", name,
             before_o.dirty, (old_bug ? 1'b1 : dirty));
    a = before_o;
    b = after_o;
    a.dirty = 0;
    b.dirty = 0;
    if (a !== b) $fatal(1, "non-dirty output changed name=%s", name);
    if (after_wb.ack !== wb_ack || before_wb.ack !== wb_ack ||
        after_wb.dirty !== wb_dirty || before_wb.dirty !== (wb_bug ? 1'b1 : wb_dirty) ||
        after_wb.fflags !== fflags || (fflags && after_wb.csr_wdata !== {59'b0, flags}))
      $fatal(1, "WB contract name=%s ack=%b/%b dirty=%b/%b", name,
             after_wb.ack, wb_ack, after_wb.dirty, wb_dirty);
    a = before_wb;
    b = after_wb;
    a.dirty = 0;
    b.dirty = 0;
    if (a !== b) $fatal(1, "WB non-dirty output changed name=%s", name);
    checks++;
    if (old_bug) original_failures++;
    if (wb_bug) wb_original_failures++;
    $display("DIRTY_CASE cache=WT id=%0d name=%s ack=%b old=%b fixed=%b flags_write=%b flags=%02h reproduced=%b",
             checks, name, ack, before_o.dirty, after_o.dirty, fflags,
             fflags ? flags : 5'b0, old_bug);
    $display("DIRTY_CASE cache=WB id=%0d name=%s ack=%b old=%b fixed=%b flags_write=%b flags=%02h reproduced=%b",
             checks, name, wb_ack, before_wb.dirty, after_wb.dirty, fflags,
             fflags ? flags : 5'b0, wb_bug);
    @(posedge clk);
  endtask

  initial begin
    defaults(); rst_n = 0;
    check_case("reset_empty", 0, 0, 0, 0);
    defaults(); accel(0); entries[0].valid = 0;
    check_case("invalid_stale_accel", 0, 0, 0, 0, 1);
    defaults(); accel(0); halt = 1;
    check_case("halt_held_accel", 0, 0, 0, 0, 1);
    @(negedge clk);
    check_case("halt_still_held", 0, 0, 0, 0, 1);
    @(negedge clk); halt = 0;
    check_case("halt_release_retires", 1, 1, 0, 0);
    defaults(); accel(0); entries[0].ex.valid = 1; entries[0].ex.cause = 2;
    check_case("illegal_fs_off", 0, 0, 0, 0, 1);
    if (!after_o.exception.valid || after_o.exception.cause != 2)
      $fatal(1, "illegal exception missing");
    @(negedge clk); drop[0] = 1;
    check_case("exception_drop_ack_not_retire", 1, 0, 0, 0, 1);
    if (after_o.exception.valid) $fatal(1, "dropped exception escaped");
    defaults(); accel(0); drop[0] = 1;
    check_case("cancel_drop_ack_not_retire", 1, 0, 0, 0, 1);
    defaults(); accel(0); entries[0].valid = 0;
    check_case("scoreboard_flush_stale_class", 0, 0, 0, 0, 1);
    defaults(); accel(0);
    check_case("pv_retire", 1, 1, 0, 0);
    defaults(); accel(0); entries[0].vfp = 0;
    check_case("integer_accel", 1, 0, 0, 0);
    defaults(); entries[0].valid = 1; accel(1); entries[1].valid = 0;
    check_case("port1_invalid_stale_accel", 1, 0, 0, 0, 1);
    defaults(); entries[0].valid = 1; accel(1);
    check_case("port1_accel_cannot_retire", 1, 0, 0, 0, 1);
    defaults(); entries[0].valid = 1; entries[0].fu = STORE; entries[0].op = SD;
    lsu_ready = 0; accel(1);
    check_case("lsu_stall_blocks_port1", 0, 0, 0, 0, 1);
    defaults(); accel(0); flush_dcache = 1; no_st_pending = 0;
    // In WT flush_dcache does not hold ACK; in WB it waits for stores.
    check_case("flush_cache_contract", 1, 1, 0, 0);
    if (after_o.fence_i || after_wb.fence_i)
      $fatal(1, "cache-specific flush wait contract");
    @(negedge clk); no_st_pending = 1;
    check_case("flush_with_real_retire", 1, 1, 0, 0);
    if (after_o.fence_i || !after_wb.fence_i)
      $fatal(1, "cache-specific flush retire contract");
    defaults(); accel(0); entries[0].op = FENCE;
    no_st_pending = 0;
    check_case("fence_stall_not_retire", 0, 0, 0, 0, 1);
    defaults(); fp(0, FADD, 5'h11);
    check_case("native_fp_port0", 1, 1, 1, 5'h11);
    defaults(); entries[0].valid = 1; fp(1, FADD, 5'h02);
    check_case("native_fp_port1", 3, 1, 1, 5'h02);
    defaults(); fp(0, FADD, 5'h11); fp(1, FMUL, 5'h06);
    check_case("native_two_port_flags_union", 3, 1, 1, 5'h17);
    defaults(); fp(0, FCLASS, 0);
    check_case("native_fp_read_only_class", 1, 0, 1, 0);
    defaults(); fp(0, FCVT_F2I, 1);
    check_case("native_fp_to_int", 1, 0, 1, 1);
    defaults(); entries[0].valid = 1; entries[0].fu = LOAD; entries[0].op = FLD;
    check_case("native_fp_load", 1, 1, 0, 0);
    defaults(); entries[0].valid = 1; entries[0].fu = STORE; entries[0].op = FSD;
    check_case("native_fp_store_read_only", 1, 0, 0, 0);
    defaults(); fp(0, FADD, 5'h01); halt = 1;
    check_case("native_fp_halt", 0, 0, 0, 0);
    defaults(); fp(0, FADD, 5'h01); entries[0].valid = 0;
    check_case("native_fp_invalid", 0, 0, 0, 0);
    defaults(); fp(0, FADD, 5'h01); entries[0].ex.valid = 1;
    check_case("native_fp_exception", 0, 0, 0, 0);
    defaults(); fp(0, FADD, 5'h01); drop[0] = 1;
    // Preserve the existing native-FP drop behavior; this patch is ACCEL-only.
    check_case("native_fp_drop_unchanged", 1, 1, 0, 0);
    defaults(); fp(0, FADD, 5'h01); entries[0].ex.valid = 1; drop[0] = 1;
    check_case("native_fp_exception_drop_unchanged", 1, 1, 0, 0);
    defaults(); fp(0, FADD, 5'h01); fp(1, FMUL, 5'h06); single_step = 1;
    check_case("single_step_blocks_port1", 1, 1, 1, 1);
    defaults(); entries[0].valid = 1; fp(1, FMUL, 5'h06); entries[1].ex.valid = 1;
    check_case("port1_native_exception", 1, 0, 0, 0);
    defaults(); accel(0); fp(1, FMUL, 5'h06);
    check_case("accel_and_native_fp_retire", 3, 1, 1, 5'h06);
    defaults(); entries[0].valid = 1; entries[0].fu = CSR; entries[0].op = CSR_READ;
    csr_exception.valid = 1;
    check_case("csr_exception_ack_contract", 0, 0, 0, 0);
    defaults(); entries[0].valid = 1; entries[0].fu = ALU; entries[0].op = AMO_ADDD;
    check_case("amo_wait", 0, 0, 0, 0);
    @(negedge clk); amo_resp.ack = 1; amo_resp.result = 64'h10203040;
    check_case("amo_retire_flush", 1, 0, 0, 0);
    if (!after_o.flush) $fatal(1, "AMO flush not covered");
    defaults(); rst_n = 0;
    check_case("reset_after_activity", 0, 0, 0, 0);
    if (checks != 36 || original_failures != 11 || wb_original_failures != 12)
      $fatal(1, "coverage accounting checks=%0d WT=%0d WB=%0d", checks,
             original_failures, wb_original_failures);
    $display("COMMIT_DIRTY_PASS configurations=2 checks=72 original_failures=23 fixed_failures=0 non_dirty_equal=72");
    $finish;
  end
  initial begin
    #10000;
    $fatal(1, "bounded timeout");
  end
endmodule
