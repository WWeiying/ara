#!/usr/bin/env python3
"""Single historical test, exact448 and local-root refresh diagnostic only."""
import csv
from decimal import Decimal
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import apply_qbs_historical_v2 as corrected

base = corrected.base
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TCL = HERE / "probe_qbs_root_refresh.tcl"
TEST = HERE / "test_probe_qbs_root_refresh.py"
REFERENCE = base.OUT / "operand-root-update-single-20261006-02/root-update-result.json"
original_verify = base.verify_artifacts
original_prepare = base.prepare
HEADER = ["Stage", "RequestedScope", "Token", "Handle", "GUIPath", "Name", "Branch", "Score"]


def rooted_rows(path, scopes):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        base.require(reader.fieldnames == HEADER, "Root metrics schema differs")
        rows = list(reader)
    result = {}
    for row in rows:
        base.require(None not in row and all(row.values()), "Incomplete root metrics")
        key = row["Stage"], row["RequestedScope"]
        base.require(key not in result and key[0] in ("raw", "applied", "reset") and key[1] in scopes,
                     "Unexpected/duplicate root metrics")
        base.require(row["Token"] == key[1] and row["GUIPath"] == row["Name"] == key[1].split(".")[-1]
                     and row["Handle"] != "0", "Local root binding differs")
        for metric in ("Branch", "Score"):
            base.require(base.re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", row[metric]) is not None,
                         "Nonpercentage root metric")
            base.require(Decimal(row[metric][:-1]) <= 100, "Root percentage outside range")
        result[key] = row
    base.require(set(result) == {(stage, scope) for stage in ("raw", "applied", "reset") for scope in scopes},
                 "Missing root metrics")
    for scope in scopes:
        for metric in ("Branch", "Score"):
            base.require(result["raw", scope][metric] == result["reset", scope][metric], "Root reset differs")
        base.require(Decimal(result["applied", scope]["Branch"][:-1]) >
                     Decimal(result["raw", scope]["Branch"][:-1]), "No rooted branch increase")
    return rows


def verify_artifacts(output, config):
    result = original_verify(output, config)
    if "root_refresh_scopes" not in config:
        return result
    base.require(config["mode"] == "contract" and len(config["selected_tests"]) == 1, "Single test only")
    path = output / "rooted-metrics.csv"
    result["rooted_metrics"] = rooted_rows(path, config["root_refresh_scopes"])
    result["files"][str(path)] = base.sha(path)
    result["status"] = "QBS_SINGLE_TEST_ROOT_REFRESH_DIAGNOSTIC_VERIFIED_NOT_REPORT"
    result["limitation"] = "Single test only; no aggregate approval or official denominator validation"
    return result


def prepare(output, mode, qualification_result_seal, *args):
    base.require(mode == "contract", "No full population reload in this diagnostic")
    reference = json.loads(REFERENCE.read_bytes())
    base.require(reference["status"] == "SINGLE_TEST_ROOT_RECALCULATE_DIAGNOSTIC_VERIFIED_NOT_REPORT"
                 and reference["dependencies_unchanged"] is True and reference["tests"] == 1,
                 "Refresh reference not qualified")
    pins = {**reference["dependency_pins"], **reference["files"]}
    for path, expected in pins.items():
        base.require(base.sha(Path(path)) == expected, "Refresh reference pin changed: " + path)
    pins[str(REFERENCE)] = base.sha(REFERENCE)
    original_prepare(output, mode, qualification_result_seal, *args)
    config = json.loads((output / "config.json").read_bytes())
    scopes = ["ara_tb", "ara_tb.dut.i_ara_soc.i_system", "ara_tb.dut.i_ara_soc.i_system.i_ara"]
    scopes += sorted(config["plan"]["scopes"])
    base.require(len(scopes) == 5 and len(set(scopes)) == 5, "Wrong refresh scopes")
    config["root_refresh_scopes"] = scopes
    for path in (SCRIPT, TCL, TEST, corrected.SCRIPT, corrected.TEST, base.HERE / "apply_qbs_historical.tcl"):
        pins[str(path)] = base.sha(path)
    for path, expected in pins.items():
        base.require(path not in config["pins"] or config["pins"][path] == expected, "Conflicting diagnostic pin")
        config["pins"][path] = expected
    selection = output / "root-selection.tcl"
    # This generated selection is fixed by the config pin before the DVE launch.
    selection.write_text("set qbsrefresh_scopes {" + " ".join(base.capture.literal(s) for s in scopes) + "}\n")
    config["pins"][str(selection)] = base.sha(selection)
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, aggregate_admission=False))
    print("QBS_REFRESH_FINAL_SEAL " + seal, flush=True)


base.TCL, base.TEST = TCL, TEST
base.prepare, base.verify_artifacts = prepare, verify_artifacts
if __name__ == "__main__":
    base.main()
