#!/usr/bin/env python3
"""Absolute-helper retry for the bounded read-only native API probe."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import probe_operand_debug_native_v2 as previous

base = previous.base
HERE = Path(__file__).resolve().parent
base.TCL = HERE / "probe_operand_debug_native_v3.tcl"
base.TEST = HERE / "test_probe_operand_debug_native_v3.py"
prior_prepare = base.prepare


def prepare(output):
    failed = base.debug.OUT / "operand-debug-native-api-probe-20261006-02"
    state = json.loads((failed / "status.json").read_bytes())
    base.require(state["status"] == "FAILED", "Prior loader failure must be terminal")
    prior_prepare(output)
    config = json.loads((output / "config.json").read_bytes())
    for path in (Path(__file__).resolve(), failed / "status.json", failed / "config.json",
                 failed / "DVEfiles/dve_gui.log"):
        config["pins"][str(path)] = base.sha(path)
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal,
                                           exclusions_generated=False, application_approval=False))
    print("PROBE_V3_FINAL_SEAL " + seal, flush=True)


base.prepare = prepare
if __name__ == "__main__":
    base.main()
