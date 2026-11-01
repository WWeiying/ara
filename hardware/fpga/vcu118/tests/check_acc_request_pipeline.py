#!/usr/bin/env python3
"""Bounded XSim check of the FPGA-only accelerator request timing boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vivado-bin", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    fpga = here.parents[1] / "ara_dsa_vcu118"
    dispatcher = fpga / "rtl/cva6/core/acc_dispatcher.sv"
    text = dispatcher.read_text()
    instance = re.search(
        r"\bspill_register\s*#\((.*?)\)\s*i_accelerator_req_register\s*\((.*?)\);",
        text, re.S)
    if instance is None:
        raise RuntimeError("FPGA request instance is not a spill register")
    compact = re.sub(r"\s+", "", instance.group(0))
    for connection in (
        ".T(accelerator_req_t)", ".Bypass(1'b0)", ".clk_i(clk_i)",
        ".rst_ni(rst_ni)", ".data_i(acc_req)", ".valid_i(acc_req_valid)",
        ".ready_o(acc_req_ready)", ".data_o(acc_req_int)",
        ".valid_o(acc_req_o.acc_req.req_valid)",
        ".ready_i(acc_resp_i.acc_resp.req_ready)",
    ):
        if connection not in compact:
            raise RuntimeError("Unexpected request boundary connection: " + connection)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cells = fpga / "rtl/common_cells"
    sources = [cells / "src/spill_register_flushable.sv",
               cells / "src/spill_register.sv", here / "acc_request_pipeline_tb.sv"]
    inputs = sources + [dispatcher] + sorted((cells / "include/common_cells").glob("*.svh"))
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    commands = [
        ["xvlog", "-sv", "-d", "SYNTHESIS", "-i", str(cells / "include"),
         *map(str, sources)],
        ["xelab", "-mt", "2", "-timescale", "1ns/1ps", "acc_request_pipeline_tb",
         "-s", "acc_request_pipeline_tb_sim"],
        ["xsim", "acc_request_pipeline_tb_sim", "-runall"],
    ]
    result = {"passed": False, "inputs": hashes, "commands": commands,
              "scope": "component handshake/order/throughput and static instance wiring; "
                       "not full CPU/Ara regression, routed timing or board performance"}
    try:
        for command in commands:
            with (out / (command[0] + ".console.log")).open("w") as log:
                subprocess.run([str(args.vivado_bin.resolve() / command[0]), *command[1:]],
                               cwd=out, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=180)
        output = (out / "xsim.console.log").read_text()
        if "PASS: order, capacity, stall, cancellation, reset, no bypass;" not in output:
            raise RuntimeError("Missing simulation PASS marker")
        if any(hashlib.sha256(p.read_bytes()).hexdigest() != hashes[str(p)] for p in inputs):
            raise RuntimeError("Inputs changed during test")
        result["passed"] = True
        print(output)
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
