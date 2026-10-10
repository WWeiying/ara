#!/usr/bin/env python3
"""Map merged VCS branch bits back to source expressions for one RTL instance."""

import argparse
import gzip
from pathlib import Path
import xml.etree.ElementTree as ET


def elements(path, tag):
    with gzip.open(path, "rb") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == tag:
                yield element
            element.clear()


def instance_bits(path, instance):
    for element in elements(path, "instance_data"):
        if element.get("name") == instance:
            return element.get("chksum"), element.get("value")
    raise ValueError(f"instance not found in {path}: {instance}")


def branch_specs(path, checksum):
    with gzip.open(path, "rb") as stream:
        root = ET.parse(stream).getroot()
    definition = next((item for item in root.iter("branch_def")
                       if item.get("chksum") == checksum), None)
    if definition is None:
        raise ValueError(f"branch definition not found: {checksum}")
    specs = []
    for spec in definition.iter("branch_spec"):
        expr = spec.find("branch_expr")
        specs.append((int(spec.get("totalbranches")),
                      expr.get("id") if expr is not None else "?",
                      expr.get("exprstr") if expr is not None else "?"))
    return specs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True, help="DVE inputs.txt")
    parser.add_argument("--instance", required=True, help="full RTL instance path")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    paths = [Path(line) for line in args.inputs.read_text().splitlines() if line]
    design, tests = paths[0], paths[1:]
    merged = None
    checksum = None
    for index, test in enumerate(tests, 1):
        files = list((test / "snps/coverage/db/testdata").glob("*/branch.verilog.data.xml"))
        if len(files) != 1:
            raise ValueError(f"expected one branch data file in {test}, got {len(files)}")
        actual_checksum, value = instance_bits(files[0], args.instance)
        if checksum is None:
            checksum, merged = actual_checksum, bytearray(len(value))
        if actual_checksum != checksum or len(value) != len(merged):
            raise ValueError(f"incompatible branch data in {test}")
        for bit, char in enumerate(value):
            if char == "1":
                merged[bit] = 1
            elif char != "0":
                raise ValueError(f"unexpected branch bit {char!r} in {test}")
    specs = branch_specs(design / "snps/coverage/db/shape/branch.verilog.shape.xml", checksum)
    if sum(width for width, _, _ in specs) != len(merged):
        raise ValueError("branch definition width does not match test data")
    print(f"instance={args.instance} tests={len(tests)} covered={sum(merged)}/{len(merged)}")
    offset = 0
    shown = 0
    for width, line, expr in specs:
        bits = merged[offset:offset + width]
        if 0 in bits and shown < args.limit:
            print(f"line={line} covered={sum(bits)}/{width} expr={expr}")
            shown += 1
        offset += width
    uncovered = 0
    offset = 0
    for width, _, _ in specs:
        uncovered += 0 in merged[offset:offset + width]
        offset += width
    print(f"uncovered_expressions={uncovered}")


if __name__ == "__main__":
    main()
