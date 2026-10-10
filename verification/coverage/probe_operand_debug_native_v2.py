#!/usr/bin/env python3
"""Find first unexpected native branch leaf and inspect observed Block detail."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import probe_operand_debug_native as base

HERE = Path(__file__).resolve().parent
base.TCL = HERE / "probe_operand_debug_native_v2.tcl"
base.TEST = HERE / "test_probe_operand_debug_native_v2.py"
original_prepare = base.prepare


def prepare(output):
    original_prepare(output)
    config = json.loads((output / "config.json").read_bytes())
    for path in (Path(__file__).resolve(), HERE / "probe_operand_debug_native.tcl"):
        config["pins"][str(path)] = base.sha(path)
    config["limits"] = dict(branch_parents=1000, branch_leaves=4000, unknown_stop=1,
                            recorded_unknown_nodes=2, line_parents=5, line_children=6, line_grandchildren=3)
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal,
                                           exclusions_generated=False, application_approval=False))
    print("PROBE_V2_FINAL_SEAL " + seal, flush=True)


base.prepare = prepare
if __name__ == "__main__":
    base.main()
