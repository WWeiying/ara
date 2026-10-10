// 仅验证：通过 extra_sources 加入新 SoC 镜像，不进入正常 RTL 文件表。
// 已核对 deps/cva6/core/{csr_regfile,fpu_wrap}.sv 和 deps/fpnew/src/fpnew_top.sv。
// 不改 stimulus、不 force；当前 bind 要求 CVA6Cfg.FpPresent=1。
// +CVA6_STATE_PREREQ_ROWS=<1..8192>：每路上限，单 hart 两路合计最多 16K 行。
// +CVA6_STATE_PREREQ_FILE=<basename>：默认 state_prereq，生成 .csr.log/.fpu.log。
// 同名旧日志保留，自动加数字后缀。没有 END 不能视为完整采集，更不是 DUT PASS。
// 所有数据用 posedge 前 #1step 同相位采样；仅记录活动、活动后一拍和 reset 变化。
// cycle 不随 reset 重置，epoch 计异步 reset 断言；与边界/生命周期日志按时间关联。
// FPU 没有 PC：用 epoch/cycle/tag/输入序号和 CSR commit0 PC 关联，禁止只按 tag。
// 此文件不判断 NaN 数值；raw、译码 d、保持 q、选中 sel、规范化 boxed 分开记录。
// main 将本文件追加到 verify_extra_sources，保留已有 boundary/acc lifecycle 探针。
// 必须使用包含三类探针的新镜像；旧镜像缺少标量 FPU 内部证据，不用于本次诊断。
// 静态语法检查：verible-verilog-syntax --verifytree <本文件>；尚未做 VCS elaboration。
`ifndef SYNTHESIS

// 两路共用日志管理，record 只由各自 clocking block 的采样事件调用。
module cva6_state_prereq_sink #(
  parameter string Kind = "csr"
);
  timeunit 1ns;
  timeprecision 1ps;

  localparam int MaxRows = 8192;
  int row_limit = MaxRows;
  int unsigned rows = 0;
  longint unsigned cycle_count = 0;
  longint unsigned activity_edges = 0;
  longint unsigned dropped = 0;
  longint unsigned last_epoch = 0;
  longint unsigned last_row_cycle = 0;
  logic last_reset = 1'bx;
  bit tail = 0;
  bit truncated = 0;
  int fd = 0;
  string base = "state_prereq";
  string path;

  initial begin : open_log
    int existing;
    int suffix;
    void'($value$plusargs("CVA6_STATE_PREREQ_ROWS=%d", row_limit));
    void'($value$plusargs("CVA6_STATE_PREREQ_FILE=%s", base));
    if (row_limit < 1 || row_limit > MaxRows)
      $fatal(1, "[CVA6_STATE_PREREQ] ROWS must be 1..%0d", MaxRows);
    if (base.len() == 0 || base == "." || base == "..")
      $fatal(1, "[CVA6_STATE_PREREQ] FILE must be a cwd-local basename");
    for (int i = 0; i < base.len(); i++)
      if (base.getc(i) == 8'h2f || base.getc(i) == 8'h5c)
        $fatal(1, "[CVA6_STATE_PREREQ] FILE must not contain path separators");
    path = {base, ".", Kind, ".log"};
    suffix = 0;
    existing = $fopen(path, "r");
    while (existing != 0) begin
      $fclose(existing);
      suffix++;
      path = $sformatf("%s.%s.log.%0d", base, Kind, suffix);
      existing = $fopen(path, "r");
    end
    fd = $fopen(path, "a");
    if (fd == 0) $fatal(1, "[CVA6_STATE_PREREQ] cannot open %s", path);
    $display("[CVA6_STATE_PREREQ] instance=%m file=%s max_rows=%0d", path, row_limit);
    $fwrite(fd, "# CVA6_STATE_PREREQ version=1 kind=%s instance=%m max_rows=%0d\n",
            Kind, row_limit);
    $fwrite(fd, "# sample=pre_edge input_skew=1step edge_time_unit=ns cycle_origin=first_posedge\n");
    $fwrite(fd, "# Activity plus one following edge and reset changes; gap counts omitted idle edges.\n");
    $fwrite(fd, "# q/d and every payload are from one snapshot; d is next-state intent, not post-NBA q.\n");
    $fwrite(fd, "# Fires are sampled valid&&ready, NOT reset/flush qualified; unknown bits are retained.\n");
    $fwrite(fd, "# IDs are reused; input/output/retirement are distinct events. END is not DUT PASS.\n");
    if (Kind == "csr") begin
      $fwrite(fd, "# commit0_sbe_valid means result-valid; only ack[0] qualifies commit0 retirement.\n");
      $fwrite(fd, "# ack contains all ports, but this CSR interface exposes only commit0 payload.\n");
      $fwrite(fd, "# csr_wdata_in is unmodified source; csr_wdata is SET/CLEAR merged write data.\n");
    end else if (Kind == "fpu") begin
      $fwrite(fd, "# Operand packed order: c:b:a, each FLEN bits; raw_i/d/q/sel/boxed are distinct.\n");
      $fwrite(fd, "# meta0=d, meta1=q, meta2=sel; raw opcode is CVA6, meta op is FPnew.\n");
      $fwrite(fd, "# up_seq/in_seq/out_seq are lifetime fire ordinals (current fire uses prior value).\n");
      $fwrite(fd, "# Ordinals count only rst_n==1 fires; flush does not suppress raw fire counting.\n");
      $fwrite(fd, "# Ordinals are not input/output pairing; flush/reset may cancel, and IDs can repeat.\n");
      $fwrite(fd, "# Raw issue payload needs up_valid; selected/boxed payload needs in_valid.\n");
      $fwrite(fd, "# out_status[4:0]=NV,DZ,OF,UF,NX; fpu_exception.cause carries flags, not a trap.\n");
    end
    $fflush(fd);
  end

  // 先用采样后的控制量决定是否格式化，长 idle 或截断后不再构造大字符串。
  function automatic bit wants_row(input bit active, input logic rst_n,
                                    input longint unsigned epoch);
    return active || tail || (rst_n !== last_reset) || (epoch != last_epoch);
  endfunction

  task automatic record(input bit active, input logic rst_n,
                        input longint unsigned epoch, input realtime edge_time,
                        input string payload);
    if (active) activity_edges++;
    if (wants_row(active, rst_n, epoch)) begin
      if (rows < row_limit) begin
        $fwrite(fd, "cycle=%0d epoch=%0d edge_time_ns=%0.3f row=%0d rst_n=%b activity=%b gap=%0d %s\n",
                cycle_count, epoch, edge_time, rows, rst_n, active,
                rows == 0 ? cycle_count : cycle_count - last_row_cycle - 1, payload);
        last_row_cycle = cycle_count;
        rows++;
        if (rows == row_limit) $fwrite(fd, "# LIMIT_REACHED cycle=%0d rows=%0d\n", cycle_count, rows);
        if (rows == 1 || rows == row_limit || (rows % 128) == 0) $fflush(fd);
      end else begin
        dropped++;
        if (!truncated) begin
          truncated = 1;
          $fwrite(fd, "# TRUNCATED first_dropped_cycle=%0d epoch=%0d limit=%0d\n",
                  cycle_count, epoch, row_limit);
          $fflush(fd);
        end
      end
    end
    tail = active;
    last_reset = rst_n;
    last_epoch = epoch;
    cycle_count++;
  endtask

  final begin
    if (fd != 0) begin
      $fwrite(fd, "# END sim_final=1 rows=%0d limit=%0d truncated=%b dropped=%0d sampled_edges=%0d activity_edges=%0d epoch=%0d\n",
              rows, row_limit, truncated, dropped, cycle_count, activity_edges, last_epoch);
      $fflush(fd);
      $fclose(fd);
      $display("[CVA6_STATE_PREREQ] END file=%s rows=%0d truncated=%b dropped=%0d activity_edges=%0d",
               path, rows, truncated, dropped, activity_edges);
    end
  end
endmodule

module cva6_state_prereq_csr_probe #(
  parameter config_pkg::cva6_cfg_t CVA6Cfg = config_pkg::cva6_cfg_empty,
  parameter type exception_t = logic,
  parameter type scoreboard_entry_t = logic
) (
  input logic clk_i, rst_ni,
  input riscv::mstatus_rv_t mstatus_q, mstatus_d,
  input riscv::fcsr_t fcsr_q, fcsr_d,
  input ariane_pkg::fu_op csr_op_i,
  input logic [11:0] csr_addr_i, conv_addr,
  input logic csr_we, csr_read,
  input logic [CVA6Cfg.XLEN-1:0] csr_wdata_i, csr_wdata, csr_rdata, csr_rdata_o,
  input logic dirty_v_state_i, dirty_fp_state_i, dirty_fp_state_csr,
  input logic csr_write_fflags_i, acc_fflags_ex_valid_i,
  input logic [4:0] acc_fflags_ex_i,
  input logic [CVA6Cfg.VLEN-1:0] pc_i, epc_o,
  input scoreboard_entry_t commit_instr_i,
  input logic [CVA6Cfg.NrCommitPorts-1:0] commit_ack_i,
  input exception_t ex_i, csr_exception_o,
  input logic read_access_exception, update_access_exception, privilege_violation,
  input logic flush_o, eret_o, mret, sret, dret,
  input riscv::priv_lvl_t priv_lvl_o,
  input logic v_o
);
  timeunit 1ns;
  timeprecision 1ps;

  longint unsigned reset_epoch = 0;
  cva6_state_prereq_sink #(.Kind("csr")) log_sink();
  always @(negedge rst_ni)
    if (rst_ni === 1'b0) reset_epoch++;

  clocking sample_cb @(posedge clk_i);
    default input #1step;
    input rst_ni;
    input epoch = reset_epoch;
    input mstatus_q, mstatus_d, fcsr_q, fcsr_d;
    input csr_op_i, csr_addr_i, conv_addr, csr_we, csr_read;
    input csr_wdata_i, csr_wdata, csr_rdata, csr_rdata_o;
    input dirty_v_state_i, dirty_fp_state_i, dirty_fp_state_csr;
    input csr_write_fflags_i, acc_fflags_ex_valid_i, acc_fflags_ex_i;
    input pc_i, epc_o, commit_instr_i, commit_ack_i, ex_i, csr_exception_o;
    input read_access_exception, update_access_exception, privilege_violation;
    input flush_o, eret_o, mret, sret, dret, priv_lvl_o, v_o;
  endclocking

  always @(sample_cb) begin : sample_csr
    bit active;
    string row;
    active = (sample_cb.rst_ni === 1'b1) &&
      (({sample_cb.csr_we, sample_cb.csr_read, sample_cb.dirty_v_state_i,
         sample_cb.dirty_fp_state_i, sample_cb.dirty_fp_state_csr,
         sample_cb.csr_write_fflags_i, sample_cb.acc_fflags_ex_valid_i,
         sample_cb.ex_i.valid, sample_cb.csr_exception_o.valid,
         sample_cb.flush_o, sample_cb.eret_o} !== '0) ||
       (sample_cb.mstatus_q !== sample_cb.mstatus_d) ||
       (sample_cb.fcsr_q !== sample_cb.fcsr_d) ||
       ((sample_cb.commit_ack_i[0] !== 1'b0) &&
        (sample_cb.commit_instr_i.fu inside {ariane_pkg::FPU, ariane_pkg::FPU_VEC,
                                             ariane_pkg::ACCEL})));
    row = "";
    if (log_sink.rows < log_sink.row_limit &&
        log_sink.wants_row(active, sample_cb.rst_ni, sample_cb.epoch)) begin
      row = $sformatf({"mstatus_q=%h mstatus_d=%h vs_q=%b vs_d=%b fs_q=%b fs_d=%b",
                       " xs_q=%b xs_d=%b sd_q=%b sd_d=%b fcsr_q=%h fcsr_d=%h"},
                      sample_cb.mstatus_q, sample_cb.mstatus_d,
                      sample_cb.mstatus_q.vs, sample_cb.mstatus_d.vs,
                      sample_cb.mstatus_q.fs, sample_cb.mstatus_d.fs,
                      sample_cb.mstatus_q.xs, sample_cb.mstatus_d.xs,
                      sample_cb.mstatus_q.sd, sample_cb.mstatus_d.sd,
                      sample_cb.fcsr_q, sample_cb.fcsr_d);
      row = {row, $sformatf({" csr_op=%0d csr_addr=%h conv_addr=%h csr_we=%b csr_read=%b",
                             " csr_wdata_in=%h csr_wdata=%h csr_rdata=%h csr_rdata_out=%h",
                             " dirty_v=%b dirty_fp=%b dirty_fp_csr=%b write_fflags=%b",
                             " acc_fflags_valid=%b acc_fflags=%h"},
                            sample_cb.csr_op_i, sample_cb.csr_addr_i, sample_cb.conv_addr,
                            sample_cb.csr_we, sample_cb.csr_read, sample_cb.csr_wdata_i,
                            sample_cb.csr_wdata, sample_cb.csr_rdata, sample_cb.csr_rdata_o,
                            sample_cb.dirty_v_state_i, sample_cb.dirty_fp_state_i,
                            sample_cb.dirty_fp_state_csr, sample_cb.csr_write_fflags_i,
                            sample_cb.acc_fflags_ex_valid_i, sample_cb.acc_fflags_ex_i)};
      row = {row, $sformatf({" pc=%h ack=%b commit0_pc=%h commit0_id=%h commit0_fu=%0d",
                             " commit0_op=%0d commit0_sbe_valid=%b commit0_ex=%h",
                             " ex_valid=%b ex_cause=%h ex_tval=%h csr_ex=%h epc=%h",
                             " read_fault=%b write_fault=%b priv_fault=%b flush=%b eret=%b",
                             " mret=%b sret=%b dret=%b priv=%b virt=%b"},
                            sample_cb.pc_i, sample_cb.commit_ack_i,
                            sample_cb.commit_instr_i.pc, sample_cb.commit_instr_i.trans_id,
                            sample_cb.commit_instr_i.fu, sample_cb.commit_instr_i.op,
                            sample_cb.commit_instr_i.valid, sample_cb.commit_instr_i.ex,
                            sample_cb.ex_i.valid, sample_cb.ex_i.cause, sample_cb.ex_i.tval,
                            sample_cb.csr_exception_o, sample_cb.epc_o,
                            sample_cb.read_access_exception, sample_cb.update_access_exception,
                            sample_cb.privilege_violation, sample_cb.flush_o, sample_cb.eret_o,
                            sample_cb.mret, sample_cb.sret, sample_cb.dret,
                            sample_cb.priv_lvl_o, sample_cb.v_o)};
    end
    log_sink.record(active, sample_cb.rst_ni, sample_cb.epoch, $realtime, row);
  end
endmodule

module cva6_state_prereq_fpu_probe #(
  parameter config_pkg::cva6_cfg_t CVA6Cfg = config_pkg::cva6_cfg_empty,
  parameter type fu_data_t = logic,
  parameter type exception_t = logic
) (
  input logic clk_i, rst_ni, flush_i, fpu_valid_i, fpu_ready_o, fpu_valid_o,
  input fu_data_t fu_data_i,
  input logic [1:0] fpu_fmt_i,
  input logic [2:0] fpu_rm_i, fpu_frm_i,
  input logic [6:0] fpu_prec_i,
  input logic state_q, state_d, hold_inputs, use_hold,
  input logic [2:0][CVA6Cfg.FLen-1:0] raw_i, operands_d, operands_q, operands_sel, boxed,
  // 各元数据数组 [0]=d, [1]=q, [2]=sel；操作数数组 [0]=a,[1]=b,[2]=c。
  input logic [2:0][fpnew_pkg::OP_BITS-1:0] op,
  input logic [2:0][$clog2(fpnew_pkg::NUM_FP_FORMATS)-1:0] srcfmt, dstfmt,
  input logic [2:0][$clog2(fpnew_pkg::NUM_INT_FORMATS)-1:0] ifmt,
  input logic [2:0][2:0] rm,
  input logic [2:0] op_mod, vec_op,
  input logic [2:0][CVA6Cfg.TRANS_ID_BITS-1:0] tag,
  input logic in_valid, in_ready, out_valid, out_ready, busy,
  input logic [CVA6Cfg.FLen-1:0] result_o,
  input logic [4:0] status,
  input logic [CVA6Cfg.TRANS_ID_BITS-1:0] fpu_trans_id_o,
  input exception_t fpu_exception_o
);
  timeunit 1ns;
  timeprecision 1ps;

  longint unsigned reset_epoch = 0;
  longint unsigned up_seq = 0, in_seq = 0, out_seq = 0;
  cva6_state_prereq_sink #(.Kind("fpu")) log_sink();
  always @(negedge rst_ni)
    if (rst_ni === 1'b0) reset_epoch++;

  clocking sample_cb @(posedge clk_i);
    default input #1step;
    input rst_ni;
    input epoch = reset_epoch;
    input flush_i, fpu_valid_i, fpu_ready_o, fpu_valid_o, fu_data_i;
    input fpu_fmt_i, fpu_rm_i, fpu_frm_i, fpu_prec_i;
    input state_q, state_d, hold_inputs, use_hold;
    input raw_i, operands_d, operands_q, operands_sel, boxed;
    input op, srcfmt, dstfmt, ifmt, rm, op_mod, vec_op, tag;
    input in_valid, in_ready, out_valid, out_ready, busy;
    input result_o, status, fpu_trans_id_o, fpu_exception_o;
  endclocking

  always @(sample_cb) begin : sample_fpu
    bit active;
    string row;
    active = (sample_cb.rst_ni === 1'b1) &&
      (({sample_cb.fpu_valid_i, sample_cb.in_valid, sample_cb.out_valid,
         sample_cb.fpu_valid_o, sample_cb.hold_inputs, sample_cb.use_hold,
         sample_cb.flush_i, sample_cb.busy} !== '0) ||
       (sample_cb.state_q !== sample_cb.state_d));
    row = "";
    if (log_sink.rows < log_sink.row_limit &&
        log_sink.wants_row(active, sample_cb.rst_ni, sample_cb.epoch)) begin
      row = $sformatf({"flen=%0d up_seq=%0d in_seq=%0d out_seq=%0d up_valid=%b up_ready=%b up_fire=%b",
                       " raw_id=%h raw_fu=%0d raw_op=%0d fmt_i=%h rm_i=%h frm_i=%h prec_i=%h",
                       " raw_i=%h operands_d=%h operands_q=%h operands_sel=%h boxed=%h",
                       " state_q=%b state_d=%b hold_inputs=%b use_hold=%b flush=%b busy=%b"},
                      CVA6Cfg.FLen, up_seq, in_seq, out_seq,
                      sample_cb.fpu_valid_i, sample_cb.fpu_ready_o,
                      sample_cb.fpu_valid_i && sample_cb.fpu_ready_o,
                      sample_cb.fu_data_i.trans_id, sample_cb.fu_data_i.fu,
                      sample_cb.fu_data_i.operation, sample_cb.fpu_fmt_i,
                      sample_cb.fpu_rm_i, sample_cb.fpu_frm_i, sample_cb.fpu_prec_i,
                      sample_cb.raw_i, sample_cb.operands_d, sample_cb.operands_q,
                      sample_cb.operands_sel, sample_cb.boxed, sample_cb.state_q,
                      sample_cb.state_d, sample_cb.hold_inputs, sample_cb.use_hold,
                      sample_cb.flush_i, sample_cb.busy);
      for (int stage = 0; stage < 3; stage++) begin
        row = {row, $sformatf({" meta%0d_op=%h meta%0d_mod=%b meta%0d_srcfmt=%h",
                               " meta%0d_dstfmt=%h meta%0d_ifmt=%h meta%0d_rm=%h",
                               " meta%0d_vec=%b meta%0d_tag=%h"},
                              stage, sample_cb.op[stage], stage, sample_cb.op_mod[stage],
                              stage, sample_cb.srcfmt[stage], stage, sample_cb.dstfmt[stage],
                              stage, sample_cb.ifmt[stage], stage, sample_cb.rm[stage],
                              stage, sample_cb.vec_op[stage], stage, sample_cb.tag[stage])};
      end
      row = {row, $sformatf({" in_valid=%b in_ready=%b in_fire=%b out_valid=%b out_ready=%b out_fire=%b",
                             " wrapper_out_valid=%b result=%h out_status=%h out_tag=%h out_exception=%h"},
                            sample_cb.in_valid, sample_cb.in_ready,
                            sample_cb.in_valid && sample_cb.in_ready,
                            sample_cb.out_valid, sample_cb.out_ready,
                            sample_cb.out_valid && sample_cb.out_ready,
                            sample_cb.fpu_valid_o, sample_cb.result_o, sample_cb.status,
                            sample_cb.fpu_trans_id_o, sample_cb.fpu_exception_o)};
    end
    log_sink.record(active, sample_cb.rst_ni, sample_cb.epoch, $realtime, row);
    // 计数只用于输入次序关联；不在 flush 上清零，也不推断跨 flush 的成功完成。
    if (sample_cb.rst_ni === 1'b1) begin
      if ((sample_cb.fpu_valid_i && sample_cb.fpu_ready_o) === 1'b1) up_seq++;
      if ((sample_cb.in_valid && sample_cb.in_ready) === 1'b1) in_seq++;
      if ((sample_cb.out_valid && sample_cb.out_ready) === 1'b1) out_seq++;
    end
  end
endmodule

bind csr_regfile cva6_state_prereq_csr_probe #(
  .CVA6Cfg(CVA6Cfg), .exception_t(exception_t), .scoreboard_entry_t(scoreboard_entry_t)
) i_cva6_state_prereq_csr_probe (
  .clk_i(clk_i), .rst_ni(rst_ni),
  .mstatus_q(mstatus_q), .mstatus_d(mstatus_d), .fcsr_q(fcsr_q), .fcsr_d(fcsr_d),
  .csr_op_i(csr_op_i), .csr_addr_i(csr_addr_i), .conv_addr(conv_csr_addr.address),
  .csr_we(csr_we), .csr_read(csr_read), .csr_wdata_i(csr_wdata_i),
  .csr_wdata(csr_wdata), .csr_rdata(csr_rdata), .csr_rdata_o(csr_rdata_o),
  .dirty_v_state_i(dirty_v_state_i), .dirty_fp_state_i(dirty_fp_state_i),
  .dirty_fp_state_csr(dirty_fp_state_csr), .csr_write_fflags_i(csr_write_fflags_i),
  .acc_fflags_ex_valid_i(acc_fflags_ex_valid_i), .acc_fflags_ex_i(acc_fflags_ex_i),
  .pc_i(pc_i), .epc_o(epc_o), .commit_instr_i(commit_instr_i), .commit_ack_i(commit_ack_i),
  .ex_i(ex_i), .csr_exception_o(csr_exception_o),
  .read_access_exception(read_access_exception), .update_access_exception(update_access_exception),
  .privilege_violation(privilege_violation), .flush_o(flush_o), .eret_o(eret_o),
  .mret(mret), .sret(sret), .dret(dret), .priv_lvl_o(priv_lvl_o), .v_o(v_o)
);

bind fpu_wrap cva6_state_prereq_fpu_probe #(
  .CVA6Cfg(CVA6Cfg), .fu_data_t(fu_data_t), .exception_t(exception_t)
) i_cva6_state_prereq_fpu_probe (
  .clk_i(clk_i), .rst_ni(rst_ni), .flush_i(flush_i),
  .fpu_valid_i(fpu_valid_i), .fpu_ready_o(fpu_ready_o), .fpu_valid_o(fpu_valid_o),
  .fu_data_i(fu_data_i), .fpu_fmt_i(fpu_fmt_i), .fpu_rm_i(fpu_rm_i),
  .fpu_frm_i(fpu_frm_i), .fpu_prec_i(fpu_prec_i),
  .state_q(state_q), .state_d(state_d),
  .hold_inputs(fpu_gen.hold_inputs), .use_hold(fpu_gen.use_hold),
  .raw_i({fpu_gen.operand_c_i, fpu_gen.operand_b_i, fpu_gen.operand_a_i}),
  .operands_d({fpu_gen.operand_c_d, fpu_gen.operand_b_d, fpu_gen.operand_a_d}),
  .operands_q({fpu_gen.operand_c_q, fpu_gen.operand_b_q, fpu_gen.operand_a_q}),
  .operands_sel({fpu_gen.operand_c, fpu_gen.operand_b, fpu_gen.operand_a}),
  .boxed(fpu_gen.fpu_operands),
  .op({fpu_gen.fpu_op, fpu_gen.fpu_op_q, fpu_gen.fpu_op_d}),
  .srcfmt({fpu_gen.fpu_srcfmt, fpu_gen.fpu_srcfmt_q, fpu_gen.fpu_srcfmt_d}),
  .dstfmt({fpu_gen.fpu_dstfmt, fpu_gen.fpu_dstfmt_q, fpu_gen.fpu_dstfmt_d}),
  .ifmt({fpu_gen.fpu_ifmt, fpu_gen.fpu_ifmt_q, fpu_gen.fpu_ifmt_d}),
  .rm({fpu_gen.fpu_rm, fpu_gen.fpu_rm_q, fpu_gen.fpu_rm_d}),
  .op_mod({fpu_gen.fpu_op_mod, fpu_gen.fpu_op_mod_q, fpu_gen.fpu_op_mod_d}),
  .vec_op({fpu_gen.fpu_vec_op, fpu_gen.fpu_vec_op_q, fpu_gen.fpu_vec_op_d}),
  .tag({fpu_gen.fpu_tag, fpu_gen.fpu_tag_q, fpu_gen.fpu_tag_d}),
  .in_valid(fpu_gen.fpu_in_valid), .in_ready(fpu_gen.fpu_in_ready),
  .out_valid(fpu_gen.fpu_out_valid), .out_ready(fpu_gen.fpu_out_ready),
  .busy(fpu_gen.i_fpnew_bulk.busy_o), .result_o(result_o), .status(fpu_gen.fpu_status),
  .fpu_trans_id_o(fpu_trans_id_o), .fpu_exception_o(fpu_exception_o)
);
`endif
