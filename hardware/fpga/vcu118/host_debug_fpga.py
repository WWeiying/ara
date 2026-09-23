"""Read-only CVA6 retirement/trap probes for the optional FPGA host profile."""


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected exactly one FPGA probe insertion point: {old}")
    return text.replace(old, new, 1)


def patch_soc_debug(text):
    if "fpga_retire_count_o" in text:
        return text
    text = once(text, "module cheshire_soc", '`include "rvfi_types.svh"\n\nmodule cheshire_soc')
    text = once(text, "  // External AXI LLC (DRAM) port", """`ifdef ARA_FPGA_HOST
  output logic [7:0] fpga_retire_count_o,
  output logic [63:0] fpga_retire_pc_o, fpga_head_pc_o,
  output logic fpga_trap_o,
  output logic [63:0] fpga_trap_pc_o, fpga_trap_cause_o, fpga_trap_tval_o,
`endif
  // External AXI LLC (DRAM) port""")
    text = once(text, "    // CLIC interface", """`ifdef ARA_FPGA_HOST
    typedef `RVFI_PROBES_INSTR_T(Cva6Cfg) fpga_instr_t;
    typedef `RVFI_PROBES_CSR_T(Cva6Cfg) fpga_csr_t;
    typedef struct packed {
      fpga_csr_t csr;
      fpga_instr_t instr;
    } fpga_probes_t;
    fpga_probes_t fpga_probes;
    if (i == 0) begin : gen_fpga_probe
      always_comb begin
        fpga_retire_count_o = 0;
        fpga_retire_pc_o = 0;
        for (int p = 0; p < Cva6Cfg.NrCommitPorts; p++) begin
          if (fpga_probes.instr.commit_ack[p] && !fpga_probes.instr.commit_drop[p]) begin
            fpga_retire_count_o = fpga_retire_count_o + 1;
            fpga_retire_pc_o = 64'($signed(fpga_probes.instr.commit_instr_pc[p]));
          end
        end
        fpga_head_pc_o = 64'($signed(fpga_probes.instr.commit_instr_pc[0]));
        fpga_trap_o = fpga_probes.instr.ex_commit_valid;
        fpga_trap_pc_o = fpga_head_pc_o;
        fpga_trap_cause_o = fpga_probes.instr.ex_commit_cause;
        fpga_trap_tval_o = fpga_probes.instr.tval;
      end
    end
`endif
    // CLIC interface""")
    return once(text, "      .rvfi_probes_o    ( ),", """`ifdef ARA_FPGA_HOST
      .rvfi_probes_o    ( fpga_probes ),
`else
      .rvfi_probes_o    ( ),
`endif""")
