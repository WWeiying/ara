#!/usr/bin/env python3
"""Absolute-helper capture retry; preserve both prior failed sessions."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import capture_operand_1144_v2 as v2

original = v2.original
HERE = Path(__file__).resolve().parent
original.TCL = HERE / "capture_operand_1144_v3.tcl"
original.TEST = HERE / "test_capture_operand_1144_v3.py"
FAILED02 = original.OUT / "operand-native-1144-capture-20261006-02"
SEAL02 = "2ae44e36f755ec09c9d264693955c0d86f24f92ea6c0e08ccc494efdf67172b0"
_environment = original.environment
_verify = original.verify_artifacts


def environment(record, output):
    env = _environment(record, output)
    env["OP1144_BASE_HOOK"] = str(v2.ORIGINAL_TCL.absolute())
    return env


def prepare(output):
    old02 = original.config_read(FAILED02, SEAL02)
    state = json.loads((FAILED02 / "status.json").read_text())
    original.require(state["status"] == "FAILED" and state["config_sha256"] == SEAL02,
                     "Keep terminal02 failure")
    v2.prepare(output)
    output = Path(output).absolute()
    config = json.loads((output / "config.json").read_text())
    for member in (Path(__file__), FAILED02 / "config.json", FAILED02 / "status.json",
                   FAILED02 / "DVEfiles/dve_gui.log", v2.HERE / "capture_operand_1144_v2.tcl"):
        original.proof.read_bound(member, config["pins"])
    config["absolute_helper"] = str(v2.ORIGINAL_TCL.absolute())
    config["prior_failure02"] = dict(output=str(FAILED02), config_sha256=SEAL02,
        correction="Absolute driver-supplied helper; mandatory complete-proc pre-session gate")
    original.check_inputs(old02)
    original.check_inputs(config)
    original.write(output / "config.json", config)
    seal = original.hash_file(output / "config.json")
    original.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal))
    print("V3_PREPARED_NO_DVE config_sha256=" + seal, flush=True)
    return seal


def verify_artifacts(output, config):
    original.require(config["absolute_helper"] == str(v2.ORIGINAL_TCL.absolute()) and
                     config["absolute_helper"] in config["pins"], "Unpinned helper path")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    original.require(log.splitlines().count("OP1144_HELPERS_READY") == 1 and
                     "OP1144_SOURCE_CONTEXT" in log and not any(s in log for s in
                     ("EK-CMD-015", "invalid command name", "helper-load-gate=")), "Helper load gate failed")
    return _verify(output, config)


original.environment = environment
original.prepare = prepare
original.verify_artifacts = verify_artifacts

if __name__ == "__main__":
    original.main()
