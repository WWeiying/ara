#!/usr/bin/env python3
"""Exact source-derived older signature, observed in the sealed two-bank pilot."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import capture_qbs_pending_metadata as base

HERE = Path(__file__).resolve().parent
base.TEST = HERE / "test_capture_qbs_pending_metadata_v2.py"
previous_bind = base.bind_native
previous_prepare = base.prepare


def bind_native(raw, config):
    rows = previous_bind(raw, config)
    expected = {}
    for scope, metrics in config["plan"]["scopes"].items():
        for r in metrics["branch"]:
            if r["target"]:
                p = r["point"]
                expected[scope, "Branch %s (%s)" % (p["native_id"], p["vector"])] = (
                    p["expressions"][0]["exprstr"] + " 1,0")
    for r in rows:
        base.require(r["native_signature"] == expected[r["scope"], r["point"]],
                     "Native older signature differs from compiled enable TRUE/use_newer FALSE")
    return rows


def prepare(output, mode, pilot=None, pilot_seal=None, pilot_result_seal=None):
    previous_prepare(output, mode, pilot, pilot_seal, pilot_result_seal)
    config = json.loads((output / "config.json").read_bytes())
    for path in (Path(__file__).resolve(), HERE / "test_capture_qbs_pending_metadata.py"):
        config["pins"][str(path)] = base.sha(path)
    selection = output / "selection.tcl"
    with selection.open("a") as stream:
        stream.write("set dbg_driver " + base.capture.literal(str(Path(__file__).resolve())) + "\n")
    config["pins"][str(selection)] = base.sha(selection)
    config["native_signature_binding"] = "exact source-derived enable expression plus 1,0; observed in actual sealed two-bank pilot"
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, application_approval=False))
    print("QBS_V2_FINAL_SEAL " + seal, flush=True)


base.bind_native = bind_native
base.native.bind_native = bind_native
base.prepare = prepare
if __name__ == "__main__":
    base.main()
