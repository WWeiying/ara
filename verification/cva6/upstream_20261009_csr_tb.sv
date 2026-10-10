`timescale 1ns/1ps
`include "rvfi_types.svh"
module upstream_20261009_csr_tb;
  `include "upstream_20261009_common.svh"
  typedef `RVFI_PROBES_CSR_T(CVA6Cfg) rvfi_t;
  rvfi_t probes;
  ariane_pkg::fu_op op = CSR_READ;
  logic [11:0] address = riscv::CSR_MSTATUS;
  logic [63:0] wdata = 0, rdata;
  exception_t ex;
  riscv::priv_lvl_t priv, ld_priv;
  logic eret;
  csr_regfile #(.CVA6Cfg(CVA6Cfg), .exception_t(exception_t), .jvt_t(jvt_t),
    .irq_ctrl_t(irq_ctrl_t), .scoreboard_entry_t(scoreboard_entry_t),
    .rvfi_probes_csr_t(rvfi_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .time_irq_i(1'b0), .commit_instr_i('0),
    .commit_ack_i('0), .boot_addr_i(64'h80000000), .hart_id_i('0), .ex_i('0),
    .csr_op_i(op), .csr_addr_i(address), .csr_wdata_i(wdata), .csr_rdata_o(rdata),
    .dirty_fp_state_i(1'b0), .csr_write_fflags_i(1'b0), .dirty_v_state_i(1'b0),
    .pc_i(64'h80000080), .csr_exception_o(ex), .eret_o(eret), .priv_lvl_o(priv),
    .ld_st_priv_lvl_o(ld_priv), .rvfi_csr_o(probes), .acc_fflags_ex_i('0),
    .acc_fflags_ex_valid_i(1'b0), .csr_hs_ld_st_inst_i(1'b0), .irq_i('0),
    .clic_irq_req_i(1'b0), .clic_irq_shv_i(1'b0), .ipi_i(1'b0),
    .debug_req_i(1'b0), .fence_t_ceil_i('0), .perf_data_i('0));

  task automatic write_csr(logic [11:0] addr, logic [63:0] data);
    @(negedge clk); address = addr; wdata = data; op = CSR_WRITE;
    #1; if (ex.valid !== 1'b0) $fatal(1, "CSR setup rejected addr=%h", addr);
    @(posedge clk); #1;
    @(negedge clk); op = CSR_READ;
  endtask
  initial begin
    int rc, sret, dest, mprv, pie, start_s;
    logic [63:0] status;
    open_files();
    while (!$feof(input_file)) begin
      rc = $fscanf(input_file, "%d %d %d %d %d %d\n", id, sret, dest, mprv, pie, start_s);
      if (rc != 6 || id != completed) $fatal(1, "Bad CSR case");
      op = CSR_READ; address = riscv::CSR_MSTATUS; reset_dut();
      // Include vector/FP dirty bits as adjacent preservation checks.
      status = (64'(mprv) << 17) | (64'(pie) << 7) | (64'(pie) << 5) |
               (64'd3 << 13) | (64'd3 << 9);
      if (sret) status |= (64'(start_s ? 1 : 3) << 11) | (64'(dest) << 8);
      else status |= 64'(dest) << 11;
      write_csr(riscv::CSR_MEPC, 64'h80002000);
      write_csr(riscv::CSR_SEPC, 64'h80003000);
      write_csr(riscv::CSR_MSTATUS, status);
      if (start_s) begin
        // MPRV=0 here: enter S normally without contaminating the SRET test.
        op = MRET; @(posedge clk); #1;
        @(negedge clk); op = CSR_READ;
      end
      #1;
      observe("before_priv", priv);
      observe("before_mprv", probes.mstatus_extended[17]);
      op = sret ? SRET : MRET;
      #1; observe("eret", eret);
      observe("target_epc", dut.epc_o);
      @(posedge clk); #1;
      // Keep xRET asserted only through this edge; reads in the new mode
      // are not allowed to feed another state-changing operation.
      @(negedge clk); op = CSR_READ; address = sret ? riscv::CSR_SSTATUS : riscv::CSR_MSTATUS;
      #1;
      observe("after_priv", priv);
      observe("after_mprv", probes.mstatus_extended[17]);
      observe("effective_ld_priv", ld_priv);
      observe("previous_priv", sret ? 64'(probes.mstatus_extended[8]) : 64'(probes.mstatus_extended[12:11]));
      observe("ie", sret ? 64'(probes.mstatus_extended[1]) : 64'(probes.mstatus_extended[3]));
      observe("pie", sret ? 64'(probes.mstatus_extended[5]) : 64'(probes.mstatus_extended[7]));
      observe("fs", probes.mstatus_extended[14:13]);
      observe("vs", probes.mstatus_extended[10:9]);
      observe("sd", probes.mstatus_extended[63]);
      completed++;
    end
    finish_test();
  end
endmodule
