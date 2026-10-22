#!/usr/bin/env python3
"""Native quoted-expression adapter, preserving frozen source and native files."""
import copy
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import capture_operand_debug_branch_v2 as previous

base = previous.base
HERE = Path(__file__).resolve().parent
base.TEST = HERE / "test_capture_operand_debug_branch_v3.py"
frozen_bind = base.debug.bind_native
previous_prepare = base.prepare


def quoted_field(text):
    base.require(all(32 <= ord(c) < 127 for c in text), "Unsupported native expression character")
    # Actual pilot04 export escaped source string quotes. This derives expected
    # field bytes only; it never manufactures an exclusion directive/file.
    return text.replace("\\", "\\\\").replace('"', '\\"')


def bind_native(raw, config):
    expected = copy.deepcopy(config)
    for metrics in expected["plan"]["scopes"].values():
        base.require(set(metrics) == {"branch"}, "No Line/Condition native binding allowed")
        for row in metrics["branch"]:
            for expression in row["point"]["expressions"]:
                expression["exprstr"] = quoted_field(expression["exprstr"])
    return frozen_bind(raw, expected)


def prepare(output, mode, pilot=None, pilot_seal=None, pilot_result_seal=None):
    failed = base.debug.OUT / "operand-debug-branch-pilot2-20261006-04"
    state = json.loads((failed / "status.json").read_bytes())
    base.require(state["status"] == "FAILED", "Prior quote mismatch must remain terminal")
    parent_config = json.loads((failed / "config.json").read_bytes())
    base.require(len(bind_native((failed / "first.el").read_bytes(), parent_config)) == 2,
                 "Actual quoted expression pilot evidence no longer binds")
    previous_prepare(output, mode, pilot, pilot_seal, pilot_result_seal)
    config = json.loads((output / "config.json").read_bytes())
    for path in (Path(__file__).resolve(), failed / "config.json", failed / "status.json", failed / "first.el",
                 failed / "DVEfiles/dve_gui.log", HERE / "test_capture_operand_debug_branch_v2.py"):
        config["pins"][str(path)] = base.sha(path)
    selection = output / "selection.tcl"
    with selection.open("a") as stream:
        stream.write("set dbg_driver " + base.capture.literal(str(Path(__file__).resolve())) + "\n")
    config["pins"][str(selection)] = base.sha(selection)
    config["native_expression_encoding"] = "ASCII quoted field; backslash and double quote escaped; exact source-derived comparison"
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, mode=mode,
        targets=config["targets"], protected=config["protected"], application_approval=False))
    print("BRANCH_V3_FINAL_SEAL " + seal, flush=True)


base.debug.bind_native = bind_native
base.prepare = prepare
if __name__ == "__main__":
    base.main()
