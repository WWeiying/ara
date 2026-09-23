#!/usr/bin/env python3
"""Bounded VCS routing and real-wrapper/reset tests; vendor PHY is not simulated."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from test_ddr2_patch import HERE, baseline_wrapper, patch_ddr2


def vendor_stub(name):
    widths = {
        "sys_rst": 1, "c0_sys_clk_i": 1, "c0_ddr4_aresetn": 1,
        "c0_ddr4_ui_clk": 1, "c0_ddr4_ui_clk_sync_rst": 1,
        "c0_init_calib_complete": 1, "addn_ui_clkout1": 1, "dbg_clk": 1, "dbg_bus": 512,
    }
    outputs = {"c0_ddr4_ui_clk", "c0_ddr4_ui_clk_sync_rst", "c0_init_calib_complete",
               "addn_ui_clkout1", "dbg_clk", "dbg_bus"}
    for channel in ("aw", "ar"):
        for field, width in (("id", 8), ("addr", 31), ("len", 8), ("size", 3),
                             ("burst", 2), ("lock", 1), ("cache", 4), ("prot", 3),
                             ("qos", 4), ("valid", 1), ("ready", 1)):
            port = "c0_ddr4_s_axi_" + channel + field
            widths[port] = width
            if field == "ready": outputs.add(port)
    for field, width in (("wdata", 512), ("wstrb", 64), ("wlast", 1), ("wvalid", 1),
                         ("wready", 1), ("bid", 8), ("bresp", 2), ("bvalid", 1), ("bready", 1),
                         ("rid", 8), ("rdata", 512), ("rresp", 2), ("rlast", 1),
                         ("rvalid", 1), ("rready", 1)):
        port = "c0_ddr4_s_axi_" + field
        widths[port] = width
        if field in {"wready", "bid", "bresp", "bvalid", "rid", "rdata", "rresp", "rlast", "rvalid"}:
            outputs.add(port)
    ports = [f"  {'output' if p in outputs else 'input'} wire [{w-1}:0] {p}" for p, w in widths.items()]
    values = {"c0_ddr4_ui_clk": "c0_sys_clk_i", "c0_ddr4_ui_clk_sync_rst": "sys_rst | ui_hold",
              "c0_init_calib_complete": "calibration & ~sys_rst"}
    assignments = [f"  assign {p} = {values.get(p, chr(39)+'0')};" for p in sorted(outputs)]
    return f"module {name}(\n" + ",\n".join(ports) + ");\n" + \
        "  logic calibration = 1, ui_hold = 0;\n" + "\n".join(assignments) + "\nendmodule\n"


WRAPPER_TB = r"""
`include "axi/typedef.svh"
module wrapper_tb;
  timeunit 1ns; timeprecision 1ps;
  `AXI_TYPEDEF_ALL(bus, logic [47:0], logic [4:0], logic [63:0], logic [7:0], logic [1:0])
  logic soc_clk = 0, ui0_clk = 0, ui1_clk = 0, stop_ui0 = 0, stop_ui1 = 0;
  always #10 soc_clk = ~soc_clk;
  always #3 if (!stop_ui0) ui0_clk = ~ui0_clk;
  always #4 if (!stop_ui1) ui1_clk = ~ui1_clk;
  logic sys_rst = 1;
  logic fabric_reset_allow = 1;
  wire ready0, ready1, soc_rst_n;
  wire all_ready = ready0 & ready1;
  wire fabric_reset_n = all_ready & fabric_reset_allow;
  rstgen i_soc_reset (.clk_i(soc_clk), .rst_ni(all_ready), .test_mode_i(1'b0),
                     .rst_no(soc_rst_n), .init_no());
  dram_wrapper_xilinx #(
    .axi_soc_aw_chan_t(bus_aw_chan_t), .axi_soc_w_chan_t(bus_w_chan_t), .axi_soc_b_chan_t(bus_b_chan_t),
    .axi_soc_ar_chan_t(bus_ar_chan_t), .axi_soc_r_chan_t(bus_r_chan_t),
    .axi_soc_req_t(bus_req_t), .axi_soc_resp_t(bus_resp_t), .Channel(0)
  ) c1 (
    .sys_rst_i(sys_rst), .dram_clk_i(ui0_clk), .soc_clk_i(soc_clk),
`ifdef ARA_FPGA_DDR2
    .fabric_reset_ni(fabric_reset_n),
`endif
    .soc_resetn_i(soc_rst_n), .fabric_ready_o(ready0), .soc_req_i('0), .soc_rsp_o()
  );
`ifdef ARA_FPGA_DDR2
  dram_wrapper_xilinx #(
    .axi_soc_aw_chan_t(bus_aw_chan_t), .axi_soc_w_chan_t(bus_w_chan_t), .axi_soc_b_chan_t(bus_b_chan_t),
    .axi_soc_ar_chan_t(bus_ar_chan_t), .axi_soc_r_chan_t(bus_r_chan_t),
    .axi_soc_req_t(bus_req_t), .axi_soc_resp_t(bus_resp_t), .Channel(1)
  ) c2 (
    .sys_rst_i(sys_rst), .dram_clk_i(ui1_clk), .soc_clk_i(soc_clk),
    .fabric_reset_ni(fabric_reset_n),
    .soc_resetn_i(soc_rst_n), .fabric_ready_o(ready1), .soc_req_i('0), .soc_rsp_o()
  );
`else
  assign ready1 = 1;
`endif
  task automatic settle;
    repeat (30) @(negedge soc_clk);
    if (!soc_rst_n || !c1.ui_resetn) $fatal(1, "Reset startup deadlock");
`ifdef ARA_FPGA_DDR2
    if (!c2.ui_resetn) $fatal(1, "C2 reset not released");
`endif
  endtask
  initial begin
    #1; sys_rst = 0;
    #1; sys_rst = 1;
    repeat (4) @(negedge soc_clk);
    sys_rst = 0; settle();
`ifdef ARA_FPGA_DDR2
    // Drive the coupled reset independently: local ready and SoC reset stay high.
    // Neither a local-only reset nor feedback from soc_resetn_i can pass this check.
    @(negedge ui0_clk); stop_ui0 = 1;
    @(negedge ui1_clk); stop_ui1 = 1;
    fabric_reset_allow = 0; #1;
    if (!all_ready || !soc_rst_n || c1.ui_resetn || c2.ui_resetn)
      $fatal(1, "Coupled reset did not assert asynchronously with both UIs stopped");
    fabric_reset_allow = 1; #1;
    if (c1.ui_resetn || c2.ui_resetn) $fatal(1, "UI reset release was asynchronous");
    stop_ui0 = 0;
    repeat (8) @(negedge soc_clk);
    if (!c1.ui_resetn || c2.ui_resetn) $fatal(1, "UI reset release needs its own clock");
    stop_ui1 = 0; settle();
    fabric_reset_allow = 0;
    repeat (8) @(negedge soc_clk);
    if (!all_ready || !soc_rst_n || c1.ui_resetn || c2.ui_resetn)
      $fatal(1, "Coupled reset fed back into local readiness");
    if (c1.gen_channel_c1.i_dram.sys_rst || c2.gen_channel_c2.i_dram.sys_rst)
      $fatal(1, "Coupled reset changed a MIG primary reset");
    fabric_reset_allow = 1; settle();
    // Cross-channel failure must assert BOTH destination resets, even with a stopped UI.
    @(negedge ui0_clk); stop_ui0 = 1;
    c2.gen_channel_c2.i_dram.calibration = 0;
    repeat (3) @(negedge ui1_clk);
    #1;
    if (soc_rst_n || c1.ui_resetn || c2.ui_resetn) $fatal(1, "C2 loss left a FIFO half alive");
    if (!ready0) $fatal(1, "Ready generation depends on combined reset");
    stop_ui0 = 0;
    c2.gen_channel_c2.i_dram.calibration = 1; settle();
    c1.gen_channel_c1.i_dram.calibration = 0;
    repeat (3) @(negedge ui0_clk);
    #1;
    if (soc_rst_n || c1.ui_resetn || c2.ui_resetn) $fatal(1, "C1 loss left a FIFO half alive");
    c1.gen_channel_c1.i_dram.calibration = 1; settle();
`else
    // The flag-off instance path is deliberately the original c1.i_dram.
    c1.i_dram.calibration = 0;
    repeat (3) @(negedge ui0_clk);
    #1;
    if (soc_rst_n || c1.ui_resetn) $fatal(1, "Baseline reset assertion changed");
    c1.i_dram.calibration = 1; settle();
`endif
    @(negedge ui0_clk); stop_ui0 = 1;
    sys_rst = 1; #1;
    if (ready0 || soc_rst_n || c1.ui_resetn) $fatal(1, "Stopped UI blocked system reset");
    stop_ui0 = 0; sys_rst = 0; settle();
    $display("PASS: DDR wrapper reset/channel selection (vendor PHY stub only)");
    $finish;
  end
  initial begin #20000; $fatal(1, "DDR wrapper watchdog"); end
endmodule
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New independent result directory")
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pkg = HERE.parent / "ara_dsa_vcu118"
    manifest = json.loads((pkg / "manifest.json").read_text())
    files = [str(pkg / p) for p in manifest["files"]
             if p.startswith(("rtl/common_cells/", "rtl/axi/"))]
    incs = ["+incdir+" + str(pkg / p) for p in manifest["include_dirs"]]
    incs += ["+incdir+" + str(pkg / "rtl/board")]
    original = baseline_wrapper()
    patched = patch_ddr2(original)
    (out / "dram_wrapper_xilinx.sv").write_text(patched)
    (out / "vendor_stubs.sv").write_text(vendor_stub("ddr4") + vendor_stub("ddr4_c2"))
    (out / "wrapper_tb.sv").write_text(WRAPPER_TB)
    tests = {
        "router": ("tb", [], [HERE / "rtl/ara_ddr_router.sv", HERE / "tests/ddr2_router_tb.sv"]),
        "baseline_wrapper": ("wrapper_tb", [], [out / "vendor_stubs.sv", out / "dram_wrapper_xilinx.sv", out / "wrapper_tb.sv"]),
        "dual_wrapper": ("wrapper_tb", ["+define+ARA_FPGA_DDR2"], [out / "vendor_stubs.sv", out / "dram_wrapper_xilinx.sv", out / "wrapper_tb.sv"]),
    }
    results = {}
    for name, (top, defines, extra) in tests.items():
        work = out / name
        work.mkdir()
        command = [args.vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                   "+define+SYNTHESIS+VCS+TARGET_VCU118", *defines, *incs, "-top", top,
                   *files, *map(str, extra), "-o", "simv"]
        with (work / "compile.log").open("w") as log:
            subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        with (work / "run.log").open("w") as log:
            subprocess.run([str(work / "simv")], cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
        result = (work / "run.log").read_text()
        print(result)
        if "PASS: DDR" not in result:
            raise RuntimeError("Missing test completion marker: " + name)
        results[name] = hashlib.sha256(result.encode()).hexdigest()
    sources = [Path(p) for p in files] + [HERE / "rtl/ara_ddr_router.sv", HERE / "ddr2_fpga.py",
               HERE / "tests/ddr2_router_tb.sv", Path(__file__).resolve(), out / "dram_wrapper_xilinx.sv"]
    (out / "result.json").write_text(json.dumps({"runs": results,
        "scope": "AXI routing and actual wrapper digital reset; no vendor PHY or physical signoff",
        "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}, indent=2) + "\n")


if __name__ == "__main__":
    main()
