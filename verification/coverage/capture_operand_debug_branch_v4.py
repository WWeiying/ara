#!/usr/bin/env python3
"""Exact native record comparison independent of DVE serialization order."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import capture_operand_debug_branch_v3 as previous

base = previous.base
HERE = Path(__file__).resolve().parent
base.TEST = HERE / "test_capture_operand_debug_branch_v4.py"
quoted_bind = previous.bind_native
previous_prepare = base.prepare


def bind_native(raw, config):
    # Population/duplicate/source binding is checked before ordering. Every
    # native field is retained; only the sequence of complete records changes.
    return sorted(quoted_bind(raw, config), key=lambda row: (row["scope"], row["point"]))


def prepare(output, mode, pilot=None, pilot_seal=None, pilot_result_seal=None):
    failed = base.debug.OUT / "operand-debug-branch-pilot2-20261006-05"
    state = json.loads((failed / "status.json").read_bytes())
    base.require(state["status"] == "FAILED" and state["reason"] == "ValueError: Native roundtrip changed",
                 "Preserve exact prior order-only rejection")
    old_config = json.loads((failed / "config.json").read_bytes())
    first = bind_native((failed / "first.el").read_bytes(), old_config)
    second = bind_native((failed / "second.el").read_bytes(), old_config)
    base.require(len(first) == len(second) == 2 and first == second, "Prior actual native fields differ")
    previous_prepare(output, mode, pilot, pilot_seal, pilot_result_seal)
    config = json.loads((output / "config.json").read_bytes())
    for path in (Path(__file__).resolve(), failed / "config.json", failed / "status.json", failed / "first.el",
                 failed / "second.el", failed / "DVEfiles/dve_gui.log", HERE / "test_capture_operand_debug_branch_v3.py"):
        config["pins"][str(path)] = base.sha(path)
    selection = output / "selection.tcl"
    with selection.open("a") as stream:
        stream.write("set dbg_driver " + base.capture.literal(str(Path(__file__).resolve())) + "\n")
    config["pins"][str(selection)] = base.sha(selection)
    config["roundtrip_comparison"] = "exact complete native records sorted by scope/point; raw ELs preserved with separate SHA256"
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, mode=mode,
        targets=config["targets"], protected=config["protected"], application_approval=False))
    print("BRANCH_V4_FINAL_SEAL " + seal, flush=True)


base.debug.bind_native = bind_native
base.prepare = prepare
if __name__ == "__main__":
    base.main()
