#!/usr/bin/env python3
"""Minimal queryability gate before a single exact690 hierarchy UI comparison."""
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import diagnose_operand_hierarchy as previous

app = previous.app
HERE = previous.HERE
HOOK = HERE / "diagnose_operand_hierarchy_v2.tcl"
FAILED = app.OUT / "operand-hierarchy-probe-690-20261006-01"
FAILED_SEAL = "dc18a1467dd0219c4d535ccd2bfd9c656ecdccf525ad7ccddc719c70c4ebfedb"


def query_rows(path, config):
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    expected = set(config["plan"]["scopes"])
    app.require(len(rows) == len(expected) == 36 and {r["scope"] for r in rows} == expected,
                "Query scope set differs")
    app.require(all(r["token"] == r["scope"] and r["handle"] and r["branch_coordinates"] == "101" for r in rows),
                "Actual query token/inventory differs")


def run(mode, output, pilot=None):
    app.require(mode in ("pilot", "full") and output.parent == app.OUT and not output.exists(), "Fresh direct output required")
    config = app.read_config(previous.SOURCE, previous.SEAL)
    app.require(app.native.hash_file(previous.SOURCE / "application-result.json") == previous.RESULT_SEAL,
                "Original application seal differs")
    result = json.loads((previous.SOURCE / "application-result.json").read_text())
    for path, sha in result["files"].items():
        app.require(app.native.hash_file(path) == sha, "Original application artifact differs")
    app.require(app.native.hash_file(FAILED / "config.json") == FAILED_SEAL and
                json.loads((FAILED / "status.json").read_text())["status"] == "FAILED", "Original failure differs")
    paths = [Path(__file__), HOOK, HERE / "test_diagnose_operand_hierarchy_v2.py", previous.HOOK,
             HERE / "diagnose_operand_hierarchy.py", FAILED / "config.json", FAILED / "status.json", FAILED / "DVEfiles/dve_gui.log"]
    if mode == "full":
        app.require(pilot is not None and pilot.parent == app.OUT, "Minimal real pilot required")
        passed = json.loads((pilot / "status.json").read_text())
        app.require(passed["status"] == "MINIMAL_36_SCOPE_QUERY_VERIFIED_NO_EXCLUSIONS", "Pilot not passed")
        saved = json.loads((pilot / "config.json").read_text())
        app.require(saved["source_config_sha256"] == previous.SEAL and saved["mode"] == "pilot", "Wrong pilot binding")
        for path, sha in saved["pins"].items():
            app.require(app.native.hash_file(path) == sha, "Pilot pin differs")
        for path, sha in passed["files"].items():
            app.require(app.native.hash_file(path) == sha, "Pilot artifact differs")
        query_rows(pilot / "queryable_before.tsv", config)
        paths += [pilot / name for name in ("config.json", "status.json", "DVEfiles/dve_gui.log", "queryable_before.tsv", "queryable_final.tsv")]
    pins = {str(p): app.native.hash_file(p) for p in paths}
    command = app.tool.launch_command(config["tool_identity"], HOOK)
    output.mkdir()
    (output / "selection.tcl").write_bytes((previous.SOURCE / "selection.tcl").read_bytes())
    pins[str(output / "selection.tcl")] = app.native.hash_file(output / "selection.tcl")
    record = dict(mode=mode, source=str(previous.SOURCE), source_config_sha256=previous.SEAL,
                  source_result_sha256=previous.RESULT_SEAL, pins=pins, command=command, diagnostic_only=True)
    app.native.write(output / "config.json", record)
    print("PREPARED config_sha256=" + app.native.hash_file(output / "config.json"), flush=True)
    env = app.tool.controlled_environment(config["tool_identity"], os.environ)
    env.pop("DVE", None)
    env.update(DVE_COVERAGE_OUTPUT=str(output), OPH_MODE=mode, OPH_V1_HOOK=str(previous.HOOK),
               OPH_APP_HOOK=str(HERE / "apply_operand_1144_690_v2.tcl"),
               OP1144_BASE_HOOK=str(HERE / "capture_operand_1144.tcl"))
    status = dict(status="RUNNING_DIAGNOSTIC_ONLY", mode=mode)
    app.native.write(output / "status.json", status)
    process = None
    try:
        with (output / "launcher.log").open("w") as log:
            process = subprocess.Popen(command, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            start = app.tool.process_info(process.pid)["starttime"]
            deadline = time.monotonic() + 60
            live = None
            while process.poll() is None and time.monotonic() < deadline:
                live = app.native.find_live(process, config["tool_identity"], start)
                if live:
                    break
                time.sleep(0.2)
            app.require(live is not None, "No verified live DVE")
            app.native.write(output / "live-identity.json", live)
            app.check(config)
            (output / "live-ready").write_text("LIVE_ELF_VERIFIED\n")
            print("LIVE_DVE pid=" + str(live["pid"]), flush=True)
            rc = process.wait(timeout=1800)
        app.require(rc == 0, "DVE process failed")
        app.check(config)
        for path, sha in pins.items():
            app.require(app.native.hash_file(path) == sha, "Probe pin differs")
        log = (output / "DVEfiles/dve_gui.log").read_text()
        app.require(log.splitlines().count("OPH2_DONE_RESET") == 1 and "OPH2_FAILED" not in log and
                    "OPH2_CLEANUP_ERROR" not in log and "EK-CMD-" not in log, "GUI probe failed; retain raw error")
        expected_tests = config["selected_tests"][:1] if mode == "pilot" else config["selected_tests"]
        app.require((output / "selected_tests.txt").read_text().splitlines() == expected_tests, "Membership differs")
        for stage in ("before", "final"):
            query_rows(output / ("queryable_" + stage + ".tsv"), config)
        for name in ("initial-empty.el", "final-empty.el"):
            app.require((output / name).read_bytes() == b"", "Not empty")
        if mode == "full":
            query_rows(output / "queryable_after.tsv", config)
            identities = None
            for stage, expected in (("raw", "before"), ("applied", "selected"), ("after", "selected"), ("final", "final")):
                identities = app.native.states(output / ("states_" + stage + ".tsv"), config["plan"], expected, identities)
            native = app.native.parse_native((previous.SOURCE / "applied.el").read_bytes())
            for name in ("applied-before.el", "applied-after.el"):
                app.require(app.native.parse_native((output / name).read_bytes()) == native, "Native set differs")
        status.update(status="MINIMAL_36_SCOPE_QUERY_VERIFIED_NO_EXCLUSIONS" if mode == "pilot" else
                      "HIERARCHY_UI_COMPARISON_VERIFIED_NOT_NEW_APPLICATION_REPORT", tests=len(expected_tests), scopes=36)
        status["files"] = {str(p): app.native.hash_file(p) for p in output.iterdir() if p.is_file() and p.name != "status.json"}
        status["files"][str(output / "DVEfiles/dve_gui.log")] = app.native.hash_file(output / "DVEfiles/dve_gui.log")
    except Exception as error:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        status.update(status="FAILED", reason=str(error))
        raise
    finally:
        app.native.write(output / "status.json", status)


if __name__ == "__main__":
    run(sys.argv[1], Path(sys.argv[2]).absolute(), Path(sys.argv[3]).absolute() if len(sys.argv) > 3 else None)
