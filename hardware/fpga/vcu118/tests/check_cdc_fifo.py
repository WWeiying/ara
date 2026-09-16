#!/usr/bin/env python3
"""One bounded differential run against the routed FPGA FIFO baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


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
    hashes = {}

    def copy(path, name=None):
        data = path.read_bytes()
        name = name or path.name
        (out / name).write_bytes(data)
        hashes[str(path.relative_to(repo))] = hashlib.sha256(data).hexdigest()
        return name

    base = pkg / "rtl/common_cells/src"
    files = [copy(base / (name + ".sv")) for name in (
        "sync", "gray_to_binary", "binary_to_gray", "spill_register",
        "spill_register_flushable", "rstgen", "rstgen_bypass", "cdc_fifo_gray")]
    rel = "hardware/fpga/ara_dsa_vcu118/rtl/common_cells/src/cdc_fifo_gray.sv"
    reference = subprocess.check_output(["git", "show", "4d5a4b02:" + rel], cwd=repo, text=True)
    reference = re.sub(r"\bcdc_fifo_gray(_src|_dst)?\b", r"reference_cdc_fifo_gray\1", reference)
    (out / "reference.sv").write_text(reference)
    (out / "common_cells").mkdir()
    for path in (pkg / "rtl/common_cells/include/common_cells").glob("*.svh"):
        copy(path, "common_cells/" + path.name)
    files += ["reference.sv", copy(here / "cdc_fifo_equivalence_tb.sv")]
    with (out / "compile.log").open("w") as log:
        subprocess.run([args.vcs, "-full64", "-sverilog", "+define+SYNTHESIS",
                        "-timescale=1ns/1ps", "+incdir+.", "-top", "tb", *files, "-o", "simv"],
                       cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "simv")], cwd=out, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=120)
    result = (out / "run.log").read_text()
    print(result)
    if result.count("PASS FIFO ") != 7 or "PASS: all FIFO comparisons" not in result:
        raise RuntimeError("Missing FIFO completion/coverage markers")
    (out / "result.json").write_text(json.dumps({"reference": "4d5a4b02", "inputs": hashes,
        "test": "FIFO cycle equivalence, data order, reset, full/stall and selector invariants; not physical signoff",
        "run_sha256": hashlib.sha256(result.encode()).hexdigest()}, indent=2) + "\n")


if __name__ == "__main__":
    main()
