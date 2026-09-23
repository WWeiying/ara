#!/usr/bin/env python3
"""Bounded simulation of debug registers/counters, not vendor JTAG or MIG IP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vcs", default=str(Path(os.environ.get("VCS_HOME", "")) / "bin/vcs"))
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tests = Path(__file__).resolve().parent
    files = [tests.parent / "rtl" / n for n in ("ara_axi_observer.sv", "ara_fpga_debug.sv")]
    files.append(tests / "host_debug_tb.sv")
    with (out / "compile.log").open("w") as log:
        subprocess.run([args.vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                        "-top", "host_debug_tb", *map(str, files), "-o", "simv"],
                       cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "simv")], cwd=out, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=30)
    text = (out / "run.log").read_text()
    if "PASS: host debug 36 checks" not in text:
        raise RuntimeError("Missing completion marker")
    record = {"scope": "register ABI, arbitration, passive AXI counters, atomic snapshot, watchdog",
              "not_tested": ["vendor JTAG IP", "MIG", "physical FPGA", "full CPU execution"],
              "inputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              "run_sha256": hashlib.sha256((out / "run.log").read_bytes()).hexdigest()}
    (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(text)


if __name__ == "__main__":
    main()
