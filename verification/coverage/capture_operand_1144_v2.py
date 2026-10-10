#!/usr/bin/env python3
"""Scope-corrected capture driver; original failed run and helpers stay sealed."""
import copy
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import capture_operand_1144 as original

HERE = Path(__file__).resolve().parent
ORIGINAL_OUTPUT = original.OUT / "operand-native-1144-capture-20261006-01"
ORIGINAL_SEAL = "82a7b92ccf8906db8326a3e25000dc5b5869311dc4bfbe3de8b4dcb563815e48"
ORIGINAL_TCL = original.TCL
ORIGINAL_TEST = original.TEST
original.TCL = HERE / "capture_operand_1144_v2.tcl"
original.TEST = HERE / "test_capture_operand_1144_v2.py"


def prepare(output):
    output = Path(output).absolute()
    original.require(output.parent.resolve() == original.OUT.resolve() and not output.exists(),
                     "Fresh direct out required")
    old = original.config_read(ORIGINAL_OUTPUT, ORIGINAL_SEAL)
    status_path = ORIGINAL_OUTPUT / "status.json"
    old_status = json.loads(status_path.read_text())
    original.require(old_status["status"] == "FAILED" and old_status["config_sha256"] == ORIGINAL_SEAL,
                     "Original FAIL must remain intact")
    manifest = original.proof.load_bound(original.PRECHECK / "manifest.sha256.json", {}, original.SEAL)
    original.require(set(manifest) == {"evidence.json", "capture-plan.json"}, "Wrong sealed members")
    for name, sha in manifest.items():
        original.proof.read_bound(original.PRECHECK / name, {}, sha)
    evidence = json.loads((original.PRECHECK / "evidence.json").read_text())
    plan = json.loads((original.PRECHECK / "capture-plan.json").read_text())
    original.require(old["plan"] == plan and all(old["pins"].get(p) == sha for p, sha in evidence["pins"].items())
                     and evidence["tests"] == 689 and evidence["selected_hits"] == 0,
                     "Prior config not bound to sealed689 evidence")
    config = copy.deepcopy(old)
    config["output"] = str(output)
    config["command"] = original.tool.launch_command(plan["tool_identity"], original.TCL)
    extra = [Path(__file__), original.TCL, original.TEST, ORIGINAL_TCL, ORIGINAL_TEST,
             ORIGINAL_OUTPUT / "config.json", status_path]
    for member in extra:
        original.proof.read_bound(member, config["pins"])
    config["prior_failure"] = dict(output=str(ORIGINAL_OUTPUT), config_sha256=ORIGINAL_SEAL,
                                  status_sha256=config["pins"][str(status_path)],
                                  correction="Declare global op1144_keys before sourcing selection inside session proc")
    output.mkdir()
    (output / "selection.tcl").write_text(original.selection(plan))
    original.proof.read_bound(output / "selection.tcl", config["pins"])
    original.check_inputs(old)
    original.check_inputs(config)
    path = output / "config.json"
    original.write(path, config)
    seal = original.hash_file(path)
    original.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal))
    print("PREPARED_NO_DVE config_sha256=" + seal, flush=True)
    return seal


original.prepare = prepare

if __name__ == "__main__":
    original.main()
