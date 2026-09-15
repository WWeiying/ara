#!/usr/bin/env python3
"""Bounded TAP/DMI comparison and actual board reset wiring test."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


RESET_TB = r"""
module reset_checker(output logic done = 0);
  timeunit 1ns; timeprecision 1ps;
  logic soc_clk = 0, dram_axi_clk = 0, ui_run = 1;
  always #10 soc_clk = ~soc_clk;
  always #3 if (ui_run) dram_axi_clk = ~dram_axi_clk;
  logic sys_reset = 1, clk_locked = 0, vio_reset = 0;
  @BOARD@
  wire sys_rst_i = sys_rst;
  logic dram_rst_o = 1, calib_complete = 0, fabric_ready_o;
  @DDR@
  wire fabric_ready = fabric_ready_o;
  wire rst_n;
  @SOC_RESET@
  int checks = 0;
  task automatic expect_run;
    #300;
    if (!rst_n || !ui_resetn || !fabric_ready) $fatal(1, "Reset did not release");
    checks++;
  endtask
  task automatic expect_reset;
    #1;
    if (rst_n || ui_resetn || fabric_ready) $fatal(1, "Reset did not assert on both AXI sides");
    checks++;
  endtask
  initial begin
    #101; sys_reset = 0; clk_locked = 1;
    #200;
    if (rst_n || ui_resetn) $fatal(1, "AXI released before calibration");
    @(negedge dram_axi_clk); calib_complete = 1; dram_rst_o = 0;
    expect_run();
    for (int phase = 0; phase < 20; phase++) begin
      #(phase + 1); sys_reset = 1; expect_reset();
      #31; sys_reset = 0;
      // Board POR + UI POR + registered ready + local reset pipelines.
      #19;
      if (rst_n || ui_resetn) $fatal(1, "Asynchronous reset release bypassed synchronizers");
      expect_run();
    end
    @(negedge soc_clk); vio_reset = 1;
    @(posedge soc_clk); #1; expect_reset();
    @(negedge soc_clk); vio_reset = 0; expect_run();
    @(negedge dram_axi_clk); dram_rst_o = 1;
    @(posedge dram_axi_clk); #1; expect_reset();
    @(negedge dram_axi_clk); dram_rst_o = 0; expect_run();
    @(negedge dram_axi_clk); calib_complete = 0;
    @(posedge dram_axi_clk); #1; expect_reset();
    @(negedge dram_axi_clk); calib_complete = 1; expect_run();
    // Clock loss/system reset must still assert with a stopped UI clock;
    // neither FIFO half may leave reset before that clock comes back.
    @(negedge dram_axi_clk); ui_run = 0;
    #5; clk_locked = 0; expect_reset();
    #31; clk_locked = 1; #300; expect_reset();
    ui_run = 1; expect_run();
    $display("PASS: board reset CDC, %0d checks, calibration/VIO/clock loss/stopped UI", checks);
    done = 1;
  end
endmodule
"""


def extract(text, start, end):
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError("Unexpected board/reset source shape")
    return text.split(start)[1].split(end)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    repo = here.parents[3]
    pkg = here.parents[1] / "ara_dsa_vcu118"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs = {}

    def copy(path, name=None):
        data = path.read_bytes()
        name = name or path.name
        (out / name).write_bytes(data)
        inputs[str(path.relative_to(repo))] = hashlib.sha256(data).hexdigest()
        return name

    files = [copy(pkg / "rtl/riscv-dbg/src/dm_pkg.sv")]
    for name in ("dmi_jtag.sv", "dmi_jtag_tap.sv"):
        files.append(copy(pkg / "rtl/riscv-dbg/src" / name))
        rel = "hardware/fpga/ara_dsa_vcu118/rtl/riscv-dbg/src/" + name
        ref = subprocess.check_output(["git", "show", "74042fbd:" + rel], cwd=repo, text=True)
        ref = re.sub(r"\bdmi_jtag_tap\b", "reference_dmi_jtag_tap", ref)
        ref = re.sub(r"\bdmi_jtag\b", "reference_dmi_jtag", ref)
        (out / ("reference_" + name)).write_text(ref)
        files.append("reference_" + name)
    files.append(copy(pkg / "rtl/riscv-dbg/src/dmi_cdc.sv"))
    for name in ("cdc_reset_ctrlr_pkg", "sync", "rstgen", "rstgen_bypass", "cdc_2phase_clearable",
                 "cdc_reset_ctrlr", "cdc_4phase", "spill_register", "spill_register_flushable"):
        files.append(copy(pkg / "rtl/common_cells/src" / (name + ".sv")))
    # Freeze includes; simulator output never goes in the package.
    (out / "common_cells").mkdir()
    for path in (pkg / "rtl/common_cells/include/common_cells").glob("*.svh"):
        copy(path, "common_cells/" + path.name)
    # Only the reference TAP/reset generators use technology clock cells.
    (out / "cells.sv").write_text("""
module tc_clk_inverter(input clk_i, output clk_o); assign clk_o = ~clk_i; endmodule
module tc_clk_mux2(input clk0_i, clk1_i, clk_sel_i, output clk_o);
  assign clk_o = clk_sel_i ? clk1_i : clk0_i;
endmodule
""")
    board = (pkg / "rtl/board/ara_dsa_vcu118.sv").read_text()
    ddr = (pkg / "rtl/board/dram_wrapper_xilinx.sv").read_text()
    inputs["board_sha256"] = hashlib.sha256(board.encode()).hexdigest()
    inputs["dram_sha256"] = hashlib.sha256(ddr.encode()).hexdigest()
    board_block = "  wire board_arst_n" + extract(board, "  wire board_arst_n", "  wire [3:0] status_async")
    ddr_block = "  logic ui_resetn;" + extract(ddr, "  logic ui_resetn;", "  // Signals before resizing")
    soc_reset = "  rstgen i_rstgen (" + extract(board, "  rstgen i_rstgen (", "  logic [4:0] rtc_count;")
    reset = RESET_TB.replace("@BOARD@", board_block).replace("@DDR@", ddr_block).replace("@SOC_RESET@", soc_reset)
    (out / "reset_tb.sv").write_text(reset)
    files += [copy(here / "jtag_sampled_tb.sv"), "reset_tb.sv", "cells.sv"]
    with (out / "compile.log").open("w") as log:
        subprocess.run([args.vcs, "-full64", "-sverilog", "+define+SYNTHESIS",
                        "-timescale=1ns/1ps", "+incdir+.", "-top", "tb", *files, "-o", "simv"],
                       cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "simv")], cwd=out, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=60)
    result = (out / "run.log").read_text()
    print(result)
    if "PASS: sampled JTAG" not in result or "PASS: board reset CDC" not in result:
        raise RuntimeError("Missing completion markers")
    (out / "result.json").write_text(json.dumps({"inputs": inputs, "reference": "74042fbd",
        "test": "digital TAP/DMI protocol and board-reset checks; no metastability/physical signoff",
        "run_sha256": hashlib.sha256(result.encode()).hexdigest()}, indent=2) + "\n")


if __name__ == "__main__":
    main()
