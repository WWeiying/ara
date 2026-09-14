#!/usr/bin/env python3
"""Check the board's actual VIO status wiring with the exported sync module."""
import argparse
from pathlib import Path
import re
import subprocess


TESTBENCH = r"""
module tb;
  timeunit 1ns;
  timeprecision 1ps;
  logic soc_clk = 0;
  always #10 soc_clk = ~soc_clk;
  logic rst_n = 0, fabric_ready = 0, clk_locked = 0, sys_rst = 0;
  @BOARD_STATUS@
  logic [3:0] previous = 0;
  int checks = 0;

  task automatic drive_and_check(input logic [3:0] value);
    @(negedge soc_clk);
    #3;
    {rst_n, fabric_ready, clk_locked, sys_rst} = value;
    #1;
    if (status !== previous) $fatal(1, "Asynchronous status change reached VIO");
    @(posedge soc_clk);
    #1;
    if (status !== previous) $fatal(1, "Status bypassed the second stage");
    @(posedge soc_clk);
    #1;
    if (status !== value) $fatal(1, "Status did not arrive after two samples");
    previous = value;
    checks++;
  endtask

  initial begin
    // The monitor is deliberately not reset by the signals it observes.
    repeat (2) @(posedge soc_clk);
    #1;
    if (status !== 0) $fatal(1, "Status did not settle after initial samples");
    for (int value = 0; value < 16; value++) drive_and_check(4'(value));
    for (int bitno = 0; bitno < 4; bitno++) begin
      drive_and_check(4'b0001 | (4'b0001 << bitno));
      drive_and_check(4'b0001);
    end
    // Back-to-back source samples verify that stages are not collapsed.
    for (int value = 0; value < 16; value++) begin
      @(negedge soc_clk);
      #3;
      {rst_n, fabric_ready, clk_locked, sys_rst} = 4'(value);
      @(posedge soc_clk);
      #1;
      if (status !== previous) $fatal(1, "Status pipeline sample mismatch");
      previous = 4'(value);
      checks++;
    end
    @(posedge soc_clk);
    #1;
    if (status !== previous) $fatal(1, "Last pipeline sample missing");
    $display("PASS: VIO status synchronization, %0d transitions", checks);
    $finish;
  end
  initial begin
    #10000;
    $fatal(1, "Status test watchdog");
  end
endmodule
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New independent test directory")
    parser.add_argument("--package", type=Path,
                        default=Path(__file__).resolve().parents[2] / "ara_dsa_vcu118")
    parser.add_argument("--board", type=Path,
                        default=Path(__file__).resolve().parents[1] / "rtl/ara_dsa_vcu118.sv")
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    source = args.board.read_text()
    blocks = re.findall(r"  wire \[3:0\] status_async = .*?end : gen_status_sync", source, re.S)
    if len(blocks) != 1 or ".probe_in0(status)" not in source:
        raise RuntimeError("Unexpected board status wiring")
    sync = (args.package / "rtl/common_cells/src/sync.sv").resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "tb.sv").write_text(TESTBENCH.replace("@BOARD_STATUS@", blocks[0]))
    with (output / "compile.log").open("w") as log:
        subprocess.run([args.vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-top", "tb",
                        str(sync), "tb.sv", "-o", "simv"], cwd=output,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    with (output / "run.log").open("w") as log:
        subprocess.run([str(output / "simv")], cwd=output,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    result = (output / "run.log").read_text()
    print(result)
    if "PASS: VIO status synchronization, 40 transitions" not in result:
        raise RuntimeError("Missing status-test completion marker")


if __name__ == "__main__":
    main()
