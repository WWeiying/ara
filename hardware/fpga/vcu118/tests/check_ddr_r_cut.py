#!/usr/bin/env python3
"""Bounded AXI R-channel cut test; does not verify routed timing or MIG internals."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    tests = Path(__file__).resolve().parent
    pkg = tests.parents[1] / "ara_dsa_vcu118"
    rtl = pkg / "rtl"
    files = [
        rtl / "axi/src/axi_pkg.sv",
        rtl / "axi/src/axi_intf.sv",
        rtl / "common_cells/src/spill_register_flushable.sv",
        rtl / "common_cells/src/spill_register.sv",
        rtl / "axi/src/axi_cut.sv",
        tests / "ddr_r_cut_tb.sv",
    ]
    wrapper = rtl / "board/dram_wrapper_xilinx.sv"
    includes = [rtl / "common_cells/include", rtl / "axi/include"]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    command = [args.vcs, "-full64", "-sverilog", "+define+SYNTHESIS",
               "-timescale=1ns/1ps", "-top", "ddr_r_cut_tb",
               *["+incdir+" + str(path) for path in includes],
               *map(str, files), "-o", str(out / "simv")]
    with (out / "compile.log").open("w") as log:
        subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "simv"), "-no_save"], cwd=out,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    marker = "PASS DDR R cut: 128 ordered 512-bit beats with stalls and independent RREADY"
    if marker not in (out / "run.log").read_text():
        raise RuntimeError("Missing R-cut completion marker")
    (out / "result.json").write_text(json.dumps({
        "passed": True,
        "scope": "R-channel AXI cut data/handshake and bypassed channels; not physical signoff",
        "inputs": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in [*files, wrapper]},
    }, indent=2) + "\n")
    print(marker)
    print(f"Evidence: {out}")


if __name__ == "__main__":
    main()
