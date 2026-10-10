#!/usr/bin/env python3
"""List uncovered VCS FSM states/transitions for one RTL instance."""

import argparse
import gzip
from pathlib import Path
import xml.etree.ElementTree as ET

from inspect_branch_gaps import instance_bits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--instance", required=True)
    args = parser.parse_args()
    paths = [Path(line) for line in args.inputs.read_text().splitlines() if line]
    design, tests = paths[0], paths[1:]
    checksum = None
    merged = None
    for test in tests:
        files = list((test / "snps/coverage/db/testdata").glob("*/fsm.verilog.data.xml"))
        if len(files) != 1:
            raise ValueError(f"expected one FSM data file in {test}")
        actual_checksum, value = instance_bits(files[0], args.instance)
        if checksum is None:
            checksum, merged = actual_checksum, bytearray(len(value))
        if actual_checksum != checksum or len(value) != len(merged):
            raise ValueError(f"incompatible FSM data in {test}")
        for index, char in enumerate(value):
            if char == "1":
                merged[index] = 1
            elif char != "0":
                raise ValueError(f"unexpected FSM bit {char!r}")
    shape = design / "snps/coverage/db/shape/fsm.verilog.shape.xml"
    with gzip.open(shape, "rb") as stream:
        root = ET.parse(stream).getroot()
    definition = next((node for node in root.iter("fsmdef")
                       if node.get("chksum") == checksum), None)
    if definition is None:
        raise ValueError(f"FSM definition not found: {checksum}")
    fsms = list(definition.iter("fsmfsm"))
    total = sum(len(fsm.findall("state")) + len(fsm.findall("transition"))
                for fsm in fsms)
    if total != len(merged):
        raise ValueError("FSM shape does not match data length")
    offset = 0
    for fsm in fsms:
        states = list(fsm.findall("state"))
        transitions = list(fsm.findall("transition"))
        width = len(states) + len(transitions)
        bits = merged[offset:offset + width]
        offset += width
        names = {node.get("id"): node.get("name") for node in states}
        print(f"instance={args.instance} fsm={fsm.get('name')} tests={len(tests)} "
              f"covered={sum(bits)}/{width}")
        for index, state in enumerate(states):
            if not bits[index]:
                print(f"state {state.get('name')} line={state.get('line')}")
        for index, edge in enumerate(transitions, len(states)):
            if not bits[index]:
                print(f"edge {names[edge.get('fromid')]} -> {names[edge.get('toid')]} "
                      f"line={edge.get('line')}")


if __name__ == "__main__":
    main()
