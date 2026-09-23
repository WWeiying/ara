"""Optional dual-DDR patch, applied after export.patch_dram's reset fixes.

The exporter calls patch_ddr2(text) for dram_wrapper_xilinx.sv. Define
ARA_FPGA_DDR2 only in the dual-channel profile. Channel=0 uses ddr4 and
Channel=1 uses ddr4_c2; both vendor IPs retain their c0_* port names.
In that profile both fabric_reset_ni ports must receive the AND of the
independent fabric_ready_o signals, also used by the SoC reset synchronizer.
"""


def _replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("DDR2 integration source changed: " + old[:100])
    return text.replace(old, new)


def patch_ddr2(text):
    """Return patched source; fail closed on drift or a duplicate application."""
    text = _replace(text, "  parameter int unsigned Ddr4CsNWidth = 1,",
                    "  parameter int unsigned Channel = 0,\n"
                    "  parameter int unsigned Ddr4CsNWidth = 1,")
    text = _replace(text, "  output logic  fabric_ready_o,",
                    """  output logic  fabric_ready_o,
  // Mandatory in the dual profile; never default an omitted coupled reset high.
`ifdef ARA_FPGA_DDR2
  input  logic  fabric_reset_ni,
`endif""")
    text = _replace(text, "  rstgen i_ui_rstgen (\n"
                    "    .clk_i(dram_axi_clk), .rst_ni(fabric_ready_o), .test_mode_i(1'b0),",
                    """  rstgen i_ui_rstgen (
`ifdef ARA_FPGA_DDR2
    // The top drives both UI resets and the SoC rstgen from combined readiness.
    // Local ready and MIG sys_rst do not depend on this input or soc_resetn_i.
    .clk_i(dram_axi_clk), .rst_ni(fabric_ready_o & fabric_reset_ni), .test_mode_i(1'b0),
`else
    .clk_i(dram_axi_clk), .rst_ni(fabric_ready_o), .test_mode_i(1'b0),
`endif""")
    start = "`ifdef USE_DDR4\n  ddr4 i_dram ("
    end = "\n  );\n`endif"
    if text.count(start) != 1:
        raise RuntimeError("DDR2 integration requires one reviewed DDR4 instance")
    first = text.index(start)
    last = text.index(end, first) + len("\n  );")
    instance = text[first + len("`ifdef USE_DDR4\n"):last]
    if "    .*\n" not in instance or ".c0_ddr4_aresetn            ( ui_resetn    )" not in instance:
        raise RuntimeError("DDR2 integration requires patched MIG reset and PHY wiring")
    second = instance.replace("  ddr4 i_dram (", "  ddr4_c2 i_dram (")
    # With the define absent even the original i_dram hierarchy is unchanged.
    replacement = """`ifdef USE_DDR4
`ifdef ARA_FPGA_DDR2
  if (Channel == 0) begin : gen_channel_c1
""" + instance + """
  end else if (Channel == 1) begin : gen_channel_c2
""" + second + """
  end
`else
""" + instance + """
`endif"""
    text = text[:first] + replacement + text[last:]
    return _replace(text, "\nendmodule", """
  // pragma translate_off
  initial begin : check_channel
`ifdef ARA_FPGA_DDR2
    if (Channel > 1) $fatal(1, "DDR Channel must be 0 or 1");
`else
    if (Channel != 0) $fatal(1, "Channel 1 requires ARA_FPGA_DDR2");
`endif
  end
  // pragma translate_on
endmodule""")
