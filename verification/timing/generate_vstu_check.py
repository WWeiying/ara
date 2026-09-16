#!/usr/bin/env python3
"""Extract the VSTU reference and check every assigned main-module register."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "hardware/src/vlsu/vstu.sv").read_text()
    states = sorted(set(re.findall(r"^\s*(\w+_q)\s*<=", source, re.M)))
    (args.output / "vstu_reference.sv").write_text(
        re.sub(r"\bvstu\b", "vstu_reference", args.before.read_text()))
    (args.output / "vstu_state_check.svh").write_text("\n".join(
        f'assert (dut.{name} === reference.{name}) else $fatal(1,"VSTU {name} check=%0d",checks);'
        for name in states if not name.startswith("debug_")) + "\n")
    print(f"generated VSTU checker for {len(states)} registers")


if __name__ == "__main__":
    main()
