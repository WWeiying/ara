#!/usr/bin/env python3
"""Canonical DVE list-string application loader; keep original failed attempt."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import apply_operand_1144_690 as original

HERE = Path(__file__).resolve().parent
FAILED = original.OUT / "operand-exact1144-application-690-20261006-01"
FAILED_SEAL = "c0ab95495ad12f0b983457bf192a2928cb09df80fcc48e7725dc014f9fc3354c"
original.TCL = HERE / "apply_operand_1144_690_v2.tcl"
_prepare = original.prepare
_verify = original.verify_artifacts


def prepare(output, seal):
    old = original.read_config(FAILED, FAILED_SEAL)
    state = json.loads((FAILED / "status.json").read_text())
    original.require(state["status"] == "FAILED" and state["config_sha256"] == FAILED_SEAL,
                     "Original failure must remain unchanged")
    _prepare(output, seal)
    config = json.loads((output / "config.json").read_text())
    for path in (Path(__file__), HERE / "test_apply_operand_1144_690_v2.py", FAILED / "config.json",
                 FAILED / "status.json", FAILED / "DVEfiles/dve_gui.log"):
        original.proof.read_bound(path, config["pins"])
    reference = original.OUT / "raw690-dve-20261006-01"
    for name in ("summary.csv", "selected_tests.txt", "DVEfiles/dve_gui.log"):
        original.proof.read_bound(reference / name, config["pins"])
    original.require((reference / "selected_tests.txt").read_text().splitlines() == config["selected_tests"],
                     "Reference raw690 membership differs")
    reference_log = (reference / "DVEfiles/dve_gui.log").read_text()
    original.require(reference_log.splitlines().count("DVE_COVERAGE_EXPORT_DONE") == 1 and
                     not any(s in reference_log for s in ("UCAPI-DLMA", "DVCDT136", "EXPORT_FAILED", "Load Failed")),
                     "Raw690 reference incomplete")
    config["raw_reference"] = str(reference / "summary.csv")
    config["prior_failure"] = dict(output=str(FAILED), config_sha256=FAILED_SEAL,
        correction="Canonical lappend list strings immediately before gui_open_cov; no literal element braces")
    original.check(old)
    original.check(config)
    original.native.write(output / "config.json", config)
    value = original.native.hash_file(output / "config.json")
    original.native.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=value))
    print("V2_PREPARED_NO_DVE config_sha256=" + value, flush=True)


def verify_artifacts(output, config):
    log = (output / "DVEfiles/dve_gui.log").read_text()
    original.require(log.splitlines().count("OPAPP_CANONICAL_INPUTS_690") == 1,
                     "Missing canonical GUI input gate")
    original.require(log.splitlines().count("OPAPP_LOAD_GATE_PASSED") == 1,
                     "Missing successful coverage load gate")
    original.require(original.summaries(output / "summary_raw.csv") == original.summaries(Path(config["raw_reference"])),
                     "Independent full690 raw reference differs")
    return _verify(output, config)


original.prepare = prepare
original.verify_artifacts = verify_artifacts

if __name__ == "__main__":
    original.main()
