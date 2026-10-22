#!/usr/bin/env python3
"""Display-depth hierarchy binding, preserving the frozen failed contract."""
import argparse
import csv
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import apply_qbs_historical as base

HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TEST = HERE / "test_apply_qbs_historical_v2.py"
FAILED = base.OUT / "qbs-application-contract-699-20261006-01"
FAILED_SEAL = "e90d73c2325947a75bc7d8981e23fa7bf6623e043e29fc028ffa72348fa48324"
previous_prepare = base.prepare


def summary(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        base.require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and
            {"Name", "Depth", "GUIPath", "Scope", "Score", "Line", "Toggle", "FSM", "Condition", "Branch"}
            <= set(reader.fieldnames), "Incomplete summary columns")
        rows = list(reader)
    stack, result = [], {}
    for row in rows:
        base.require(None not in row and all(v is not None and v != "" for v in row.values()), "Partial CSV row")
        base.require(re.fullmatch(r"0|[1-9][0-9]*", row["Depth"]), "Invalid display depth")
        depth = int(row["Depth"])
        base.require(depth <= 256 and depth <= len(stack), "Display depth jump")
        name = row["Name"]
        base.require(all(re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\[[0-9]+\])*", component)
                         for component in name.split(".")), "Noncanonical display name")
        # A displayed row can collapse several HDL generate-scope components.
        # Keep its exact name as ONE stack entry; Depth counts displayed rows.
        stack = stack[:depth] + [name]
        scope = ".".join(stack)
        base.require(stack[0] == "ara_tb" and row["GUIPath"] == row["Scope"] == scope,
                     "GUIPath differs from exact display hierarchy")
        base.require(scope not in result, "Duplicate/aliased summary scope")
        result[scope] = row
    base.require("ara_tb" in result and "ara_tb.dut.i_ara_soc.i_system" in result, "Missing root/system rows")
    return result


def offline_verify_failed():
    config = base.read_config(FAILED, FAILED_SEAL)
    status = json.loads((FAILED / "status.json").read_bytes())
    base.require(status["status"] == "FAILED" and status["reason"] ==
                 "ValueError: Relative or inconsistent GUI scope", "Original failure must remain intact")
    return base.verify_artifacts(FAILED, config)


def prepare(output, mode, qualification_result_seal, contract=None, contract_seal=None, contract_result_seal=None):
    offline_verify_failed()
    previous_prepare(output, mode, qualification_result_seal, contract, contract_seal, contract_result_seal)
    config = json.loads((output / "config.json").read_bytes())
    paths = [SCRIPT, TEST, base.HERE / "test_apply_qbs_historical.py", FAILED / "config.json", FAILED / "status.json"]
    result = offline_verify_failed()
    paths += [Path(p) for p in result["files"]]
    for path in paths:
        value = base.sha(path)
        base.require(str(path) not in config["pins"] or config["pins"][str(path)] == value, "Prior pin changed")
        config["pins"][str(path)] = value
    config["summary_binding"] = "Depth stack of exact displayed Names, including collapsed generate scopes; GUIPath and Scope must equal reconstructed canonical fullpath"
    config["prior_failure"] = dict(output=str(FAILED), config_sha256=FAILED_SEAL, original_status="FAILED",
                                  offline_artifacts_revalidated=True, old_status_not_promoted=True)
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, aggregate_admission=False))
    print("QBSAPP_V2_FINAL_SEAL " + seal, flush=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "recheck-failed":
        parser = argparse.ArgumentParser(description="Read-only full revalidation of preserved failed contract")
        parser.add_argument("command", choices=("recheck-failed",))
        parser.parse_args()
        print(json.dumps(offline_verify_failed(), indent=2))
    else:
        base.main()


base.summary = summary
base.prepare = prepare
base.TEST = TEST
if __name__ == "__main__":
    main()
