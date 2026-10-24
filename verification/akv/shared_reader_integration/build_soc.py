#!/usr/bin/env python3
"""Directly owned, bounded full-SoC overlay compile; no simulator execution."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "verification"))
from ara_verify.vcs_source_manifest import collect
from prepare import digest
from compile import verify


def accepted_command(text):
    lines = text.splitlines()
    if not lines or not lines[0].startswith("Command: "):
        raise ValueError("Missing accepted VCS command")
    parts = []
    for index, line in enumerate(lines):
        part = line[len("Command: "):] if index == 0 else line
        parts.append(part.removesuffix("\\"))
        if not part.endswith("\\"):
            break
    command = shlex.split(" ".join(parts))
    required = {"-full64", "-sverilog", "-timescale=1ns/100fs", "-ntb_opts",
                "uvm-1.2", "+define+ARA_VERIFY_UVM_CVXIF", "+define+ARA_FAIL_FAST_ASSERTS",
                "+define+ARA_NO_FSDB", "-debug_access+all", "+lint=PCWM"}
    if not required <= set(command) or command[command.index("-top")+1] != "ara_tb":
        raise ValueError("Accepted SoC flags/top mismatch")
    return command


def mapped_command(command, report):
    result = list(command)
    old_filelist = json.loads(Path(report["baseline_manifest"]).read_text())["filelist"]
    if result.count(old_filelist) != 1:
        raise ValueError("Ambiguous original filelist")
    result[result.index(old_filelist)] = report["filelist"]
    mapping = report["source_mapping"]
    extras = json.loads(Path(report["baseline_manifest"]).read_text())["extra_sources"]
    if len(extras) != 5 or sum(Path(p).suffix == ".o" for p in extras) != 1:
        raise ValueError("Expected unchanged elfloader plus four UVM sources")
    for source in extras:
        if result.count(source) != 1 or source not in mapping:
            raise ValueError("Missing mapped extra source: " + source)
        result[result.index(source)] = mapping[source]
    return result, [mapping[source] for source in extras]


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--compile-receipt", type=Path, required=True)
    parser.add_argument("--accepted-sim", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snap = args.snapshot.resolve(strict=True)
    manifest = snap / "manifest.json"
    report = json.loads(manifest.read_text())
    receipt_path = args.compile_receipt.resolve(strict=True)
    receipt = json.loads(receipt_path.read_text())
    if (receipt["state"] != "COMPILE_PASS_NOT_EXECUTED" or
            receipt["snapshot_manifest"] != str(manifest) or receipt["snapshot_sha256"] != digest(manifest)):
        raise ValueError("Need passing VLSU compile of this exact snapshot")
    verify(receipt["artifact_pins"])
    verify(report["input_pins"])
    verify(report["artifact_pins"])
    baseline = args.accepted_sim.resolve(strict=True)
    if str(baseline / "vcs_source_manifest.json") != report["baseline_manifest"]:
        raise ValueError("Wrong accepted image")
    config = (baseline / "simulator.conf").read_text()
    for line in ("sim_l2_bytes=16777216", "nr_lanes=4", "vlen=1024", "qbs_enabled=1",
                 "qbs_vrf_continuation=1", "akv_v2_enabled=1", "verify_axi_delay=0"):
        if config.splitlines().count(line) != 1:
            raise ValueError("Wrong accepted image configuration: " + line)
    command, extras = mapped_command(accepted_command((baseline / "comp.vcs.log").read_text()), report)
    vcs = shutil.which(command[0])
    if not vcs or digest(vcs) != receipt["tool_sha256"]:
        raise ValueError("VCS changed since successful VLSU compile")
    command[0] = vcs
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sim = out / "sim"
    sim.mkdir()
    (sim / "incremental_db").mkdir()
    own = [Path(__file__), HERE / "test_build_soc.py", HERE / "prepare.py", HERE / "compile.py",
           ROOT / "verification/ara_verify/vcs_source_manifest.py", Path(sys.executable).resolve(),
           Path(vcs), Path(vcs).resolve(), receipt_path, manifest,
           baseline / "comp.vcs.log", baseline / "simulator.conf"]
    pins = {**report["input_pins"], **report["artifact_pins"], **receipt["artifact_pins"],
            **{str(p): digest(p) for p in own}}
    write_json(out / "source-pins.json", pins)
    write_json(out / "command.json", command)
    closure_root = snap / "source"
    vcs_manifest = {"schema_version": 1, "repo_root": str(closure_root),
                    "filelist": report["filelist"], "extra_sources": extras,
                    "files": collect(Path(report["filelist"]), closure_root, list(map(Path, extras)))}
    write_json(sim / "vcs_source_manifest.json", vcs_manifest)
    state = {"state": "BUILDING", "pid": os.getpid(), "child_pid": None,
             "started": datetime.now(timezone.utc).isoformat(),
             "scope": "Full production SoC overlay build only; no simulation launched",
             "snapshot_manifest": str(manifest), "snapshot_sha256": digest(manifest),
             "source_pins_sha256": digest(out / "source-pins.json"), "timeout_seconds": 7200}

    def save():
        write_json(out / "status.json", state)

    def interrupted(sig, _frame):
        raise InterruptedError(f"Signal {sig}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    save()
    try:
        with (out / "build.log").open("w") as log:
            child = subprocess.Popen(command, cwd=sim, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            state["child_pid"] = child.pid
            save()
            try:
                code = child.wait(timeout=7200)
            finally:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
                state["child_pid"] = None
        verify(pins)
        current = collect(Path(report["filelist"]), closure_root, list(map(Path, extras)))
        if current != vcs_manifest["files"]:
            raise ValueError("Private closure inventory drift")
        text = (sim / "comp.vcs.log").read_text()
        if code or re.search(r"Error-\[|Error:|Fatal:", text) or not (sim / "simv").is_file():
            raise RuntimeError(f"Full SoC compile failed: {code}")
        (sim / "simulator.conf").write_text(config)
        state["state"] = "SOC_BUILT_NOT_EXECUTED"
        write_json(out / "result.json", {**state, "post_pins_match": True,
            "compile_receipt": str(receipt_path), "simv": str(sim / "simv"),
            "artifact_pins": {str(p): digest(p) for p in
                [out / "command.json", out / "build.log", out / "source-pins.json",
                 sim / "comp.vcs.log", sim / "simv", sim / "vcs_source_manifest.json",
                 sim / "simulator.conf", *sorted((sim / "simv.daidir").glob("*.so"))]}})
    except BaseException as exc:
        state.update(state="TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "FAIL", error=repr(exc))
        raise
    finally:
        state["finished"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    main()
