#!/usr/bin/env python3
"""Compile complete VLSU overlay only, never execute the generated simulator."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
from prepare import digest


def verify(pins):
    for path, sha in pins.items():
        if digest(path) != sha:
            raise ValueError(f"Pin drift: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.snapshot.resolve() / "manifest.json"
    report = json.loads(manifest.read_text())
    if report["state"] != "PREPARED_NOT_COMPILED":
        raise ValueError("Wrong snapshot type")
    verify(report["input_pins"])
    verify(report["artifact_pins"])
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS missing from PATH")
    command = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-debug_access+all",
               "+lint=TFIPC-L", "-f", report["compile_filelist"], report["top"],
               "-top", "shared_reader_integration_compile_top", "-o", str(out / "simv")]
    (out / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    state = {"state": "COMPILING", "pid": os.getpid(), "child_pid": None,
             "snapshot_manifest": str(manifest), "snapshot_sha256": digest(manifest),
             "tool": vcs, "tool_sha256": digest(vcs), "timeout_seconds": 600,
             "scope": "VLSU-only elaboration; no simulation or SoC acceptance"}

    def save():
        tmp = out / "status.tmp"
        tmp.write_text(json.dumps(state, indent=2) + "\n")
        tmp.replace(out / "status.json")

    def interrupted(signum, _frame):
        raise RuntimeError(f"Interrupted {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    save()
    try:
        with (out / "compile.log").open("w") as log:
            child = subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            state["child_pid"] = child.pid
            save()
            try:
                code = child.wait(timeout=600)
            finally:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
                state["child_pid"] = None
        verify(report["input_pins"])
        verify(report["artifact_pins"])
        text = (out / "compile.log").read_text()
        if code or re.search(r"Error-\[|Error:|Fatal:", text) or not (out / "simv").is_file():
            raise RuntimeError(f"VCS compilation failed: exit={code}")
        state["state"] = "COMPILE_PASS_NOT_EXECUTED"
        (out / "result.json").write_text(json.dumps({**state,
            "artifact_pins": {str(out / name): digest(out / name)
                              for name in ("command.json", "compile.log", "simv")}}, indent=2) + "\n")
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
