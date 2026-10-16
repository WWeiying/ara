#!/usr/bin/env python3
"""Test the actual DDR/loader reset wiring with a real generated port signature."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from check_ddr2 import vendor_stub, WRAPPER_TB


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrapper", type=Path, help="Vivado-generated loader_bd_wrapper.v")
    parser.add_argument("output", type=Path)
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    here = Path(__file__).resolve().parents[1]
    package = here.parent / "ara_dsa_vcu118"
    manifest = json.loads((package / "manifest.json").read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    signature = args.wrapper.read_text().split("\n  wire ", 1)[0]
    outputs = re.findall(r"(?m)^  output (?:\[[0-9]+:[0-9]+\])?([A-Za-z0-9_]+);$", signature)
    if len(outputs) != 28 or "module loader_bd_wrapper" not in signature:
        raise RuntimeError("Unexpected generated wrapper signature")
    stub = signature + "\n" + "\n".join(f"assign {name} = '0;" for name in outputs) + "\nendmodule\n"
    stub += "module eth_control(input clk, input [255:0] probe_in0, output probe_out0); assign probe_out0=0; endmodule\n"
    stub += vendor_stub("ddr4")
    (output / "vendor_stubs.sv").write_text(stub)
    monitor = """
  always @(sys_rst or c1.ui_resetn) begin
    #1;
    if (c1.i_eth_loader.i_loader.sys_reset !== (sys_rst || !c1.ui_resetn) ||
        c1.i_eth_loader.i_loader.ui_reset !== !c1.ui_resetn)
      $fatal(1, "Loader reset did not follow the shared UI readiness loss");
  end
  initial begin #20000;
"""
    test = WRAPPER_TB.replace("initial begin #20000;", monitor)
    (output / "wrapper_tb.sv").write_text(test)
    files = [package / p for p in manifest["files"]
             if p.startswith(("rtl/common_cells/", "rtl/axi/"))]
    files += [output / "vendor_stubs.sv", package / "rtl/board/dram_wrapper_xilinx.sv",
              here / "rtl/ara_eth_loader.sv", here / "rtl/ara_eth_shared_ddr.sv", output / "wrapper_tb.sv"]
    command = [args.vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
               "+define+SYNTHESIS+VCS+TARGET_VCU118+ARA_FPGA_ETHERNET",
               *("+incdir+" + str(package / p) for p in manifest["include_dirs"]),
               "-top", "wrapper_tb", *map(str, files), "-o", "simv"]
    with (output / "compile.log").open("w") as log:
        subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    with (output / "run.log").open("w") as log:
        subprocess.run([str(output / "simv")], cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (output / "run.log").read_text()
    print(result)
    if "PASS: DDR wrapper" not in result:
        raise RuntimeError("Missing wrapper completion")
    (output / "result.json").write_text(json.dumps({
        "scope": "Actual wrapper/reset integration; vendor blocks stubbed, no PHY/physical signoff",
        "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files + [args.wrapper]},
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
