#!/usr/bin/env python3
"""One independent exact690 UI probe; preserve all earlier application artifacts."""
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import apply_operand_1144_690 as app

HERE = Path(__file__).resolve().parent
SOURCE = app.OUT / "operand-exact1144-application-690-20261006-02"
SEAL = "0e6823417d483e68abd19ac31aef915c8d9ceb18315efa6860600034bf7231c3"
RESULT_SEAL = "d27c0aeaa7fd8bda6dc530ba648251ca41e786ada2ce3cce5a675327ce511ae8"
HOOK = HERE / "diagnose_operand_hierarchy.tcl"


def run(output):
    app.require(output.parent == app.OUT and not output.exists(), "Fresh direct output required")
    config = app.read_config(SOURCE, SEAL)
    app.require(app.native.hash_file(SOURCE / "application-result.json") == RESULT_SEAL, "Application seal differs")
    result = json.loads((SOURCE / "application-result.json").read_text())
    for path, sha in result["files"].items():
        app.require(app.native.hash_file(path) == sha, "Original artifact differs: " + path)
    pins = {str(p): app.native.hash_file(p) for p in
            (Path(__file__), HOOK, HERE / "test_diagnose_operand_hierarchy.py")}
    command = app.tool.launch_command(config["tool_identity"], HOOK)
    output.mkdir()
    (output / "selection.tcl").write_bytes((SOURCE / "selection.tcl").read_bytes())
    pins[str(output / "selection.tcl")] = app.native.hash_file(output / "selection.tcl")
    record = dict(source=str(SOURCE), source_config_sha256=SEAL, source_result_sha256=RESULT_SEAL,
                  pins=pins, command=command, diagnostic_only=True)
    app.native.write(output / "config.json", record)
    print("PREPARED config_sha256=" + app.native.hash_file(output / "config.json"), flush=True)
    env = app.tool.controlled_environment(config["tool_identity"], os.environ)
    env.pop("DVE", None)
    env.update(DVE_COVERAGE_OUTPUT=str(output), OPH_APP_HOOK=str(HERE / "apply_operand_1144_690_v2.tcl"),
               OP1144_BASE_HOOK=str(HERE / "capture_operand_1144.tcl"))
    status = dict(status="RUNNING_DIAGNOSTIC_ONLY")
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
            app.require(live is not None, "No verified live DVE child")
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
        app.require("OPH_DONE_RESET" in log and "OPH_FAILED" not in log and "OPH_CLEANUP_FAILED" not in log,
                    "Probe failed; see original GUI error")
        identities = None
        for stage, mode in (("raw", "before"), ("applied", "selected"), ("after", "selected"), ("final", "final")):
            identities = app.native.states(output / ("states_" + stage + ".tsv"), config["plan"], mode, identities)
        app.require((output / "selected_tests.txt").read_text().splitlines() == config["selected_tests"], "Membership differs")
        expected = app.native.parse_native((SOURCE / "applied.el").read_bytes())
        for name in ("applied-before.el", "applied-after.el"):
            app.require(app.native.parse_native((output / name).read_bytes()) == expected, "Native set differs")
        for name in ("initial-empty.el", "final-empty.el"):
            app.require((output / name).read_bytes() == b"", "Not empty")
        status.update(status="UI_PROBE_VERIFIED_NOT_NEW_APPLICATION_REPORT", targets=1144, protected=2492, tests=690)
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
    run(Path(sys.argv[1]).absolute())
