#!/usr/bin/env python3
"""Extract the small alignment cones verbatim for exhaustive offset/strobe tests."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    modules = []
    for engine in ("qbs", "akv"):
        path = ROOT / f"hardware/src/vlsu/{engine}/{engine}_engine.sv"
        source = path.read_text()
        declarations = []
        assignments = []
        for signal in ("descriptor_write_data", "descriptor_write_mask"):
            declaration = re.findall(rf"^  logic (\[\d+:0\]) {signal};$", source, re.M)
            assignment = re.findall(rf"^  assign {signal} = [^;\n]+;$", source, re.M)
            if len(declaration) != 1 or len(assignment) != 1:
                raise ValueError(f"{path}: expected one simple declaration/assignment for {signal}")
            declarations.append(f"  output logic {declaration[0]} {signal}")
            assignments.append(assignment[0])
        modules.append(
            f"module {engine}_descriptor_alignment_dut (\n"
            "  input logic [127:0] read_data,\n"
            "  input logic [15:0] read_data_strb, read_data_offset,\n"
            + ",\n".join(declarations) + "\n);\n"
            + "\n".join(assignments) + "\nendmodule\n")
    args.output.write_text("\n".join(modules))


if __name__ == "__main__":
    main()
