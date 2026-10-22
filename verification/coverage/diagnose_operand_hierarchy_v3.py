#!/usr/bin/env python3
"""Frozen-v2 delegation with separately sealed empty-selection correction."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import diagnose_operand_hierarchy_v2 as runner

HERE = Path(__file__).resolve().parent
runner.HOOK = HERE / "diagnose_operand_hierarchy_v3.tcl"


def main():
    output = Path(sys.argv[2]).absolute()
    pins = {str(path): runner.app.native.hash_file(path) for path in
            (Path(__file__), runner.HOOK, HERE / "test_diagnose_operand_hierarchy_v3.py",
             HERE / "diagnose_operand_hierarchy_v2.tcl", HERE / "diagnose_operand_hierarchy_v2.py")}
    runner.app.require(pins[str(HERE / "diagnose_operand_hierarchy_v2.tcl")] ==
                       "f18ace10167a58a55556a743257f9c1c0f9b541fe76d90443eeb42fbbcbd1b9e" and
                       pins[str(HERE / "diagnose_operand_hierarchy_v2.py")] ==
                       "c8c5733daab5086f77dcd04de140cc39b1698aad5135c86e41eb50450326501a", "Frozen v2 differs")
    if sys.argv[1] == "full":
        pilot = Path(sys.argv[3]).absolute()
        dependency = json.loads((pilot / "dependency-verification.json").read_text())
        runner.app.require(dependency == dict(unchanged=True, pins=pins), "Pilot correction seal differs")
    try:
        runner.run(sys.argv[1], output, Path(sys.argv[3]).absolute() if len(sys.argv) > 3 else None)
    finally:
        unchanged = all(runner.app.native.hash_file(path) == sha for path, sha in pins.items())
        if output.exists():
            runner.app.native.write(output / "dependency-verification.json", dict(unchanged=unchanged, pins=pins))
        runner.app.require(unchanged, "Probe dependency changed")


if __name__ == "__main__":
    main()
