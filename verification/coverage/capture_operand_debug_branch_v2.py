#!/usr/bin/env python3
"""Frozen branch-only successor with session-global selection initialization."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import capture_operand_debug_branch as base

HERE = Path(__file__).resolve().parent
base.TCL = HERE / "capture_operand_debug_branch_v2.tcl"
base.TEST = HERE / "test_capture_operand_debug_branch_v2.py"
original_prepare = base.prepare


def prepare(output, mode, pilot=None, pilot_seal=None, pilot_result_seal=None):
    failed = base.debug.OUT / "operand-debug-branch-pilot2-20261006-02"
    state = json.loads((failed / "status.json").read_bytes())
    base.require(state["status"] == "FAILED", "Prior pilot must be terminal")
    original_prepare(output, mode, pilot, pilot_seal, pilot_result_seal)
    config = json.loads((output / "config.json").read_bytes())
    for path in (Path(__file__).resolve(), failed / "config.json", failed / "status.json",
                 failed / "DVEfiles/dve_gui.log"):
        config["pins"][str(path)] = base.sha(path)
    selection = output / "selection.tcl"
    with selection.open("a") as stream:
        stream.write("set dbg_driver " + base.capture.literal(str(Path(__file__).resolve())) + "\n")
    config["pins"][str(selection)] = base.sha(selection)
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, mode=mode,
        targets=config["targets"], protected=config["protected"], application_approval=False))
    print("BRANCH_V2_FINAL_SEAL " + seal, flush=True)


base.prepare = prepare
if __name__ == "__main__":
    base.main()
