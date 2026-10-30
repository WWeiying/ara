#!/usr/bin/env python3
"""Gate native projection timing on the sealed pack candidate's functional tests."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_half_scale_soc import ROOT, atomic_json, digest, hashes


def functional_gate(directory, state):
    if state.get("state") != "PASS" or state.get("child_pid") is not None:
        raise ValueError("Packing functional suite is not complete")
    cases = state["cases"]
    if [(c["vlen"], c["avl_limit"], c["cases"]) for c in cases] != [
            (128, 0, 33264), (1024, 0, 33264), (1024, 7, 33264)]:
        raise ValueError("Missing required native packing cases")
    pins = json.loads((directory / "manifest.json").read_text())
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Packing functional input drift")
    for case in cases:
        vlen, avl = case["vlen"], case["avl_limit"]
        log = directory / f"vlen{vlen}-avl{avl}.log"
        if (digest(log) != case["log_sha256"] or
                digest(directory / f"init-avl{avl}") != case["elf_sha256"]):
            raise ValueError("Packing result identity differs")
        text = log.read_text()
        if (text.count(f"PACK_CANDIDATE_PASS cases=33264 rvv=1 avl_limit={avl} invalid=14") != 1
                or text.count("PACK_GUEST_EXIT=0") != 1 or "PACK_CANDIDATE_FAIL" in text):
            raise ValueError("Packing completion evidence differs")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--functional-run", type=Path, required=True)
    p.add_argument("--functional-service", required=True)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--simv", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source, build = args.functional_run.resolve(strict=True), args.build.resolve(strict=True)
    state = dict(state="waiting_functional_gate", pid=os.getpid())
    atomic_json(out / "status.json", state)
    try:
        deadline = time.monotonic() + 2100
        while True:
            progress = json.loads((source / "status.json").read_text())
            if progress["state"] == "PASS":
                break
            if progress["state"] == "FAIL":
                raise ValueError("Packing functional worker failed; no VCS dispatch")
            status = subprocess.run(["systemctl", "--user", "is-active", args.functional_service],
                                    capture_output=True, text=True, timeout=15)
            if status.stdout.strip() != "active":
                # Re-read final status in case completion raced the service query.
                progress = json.loads((source / "status.json").read_text())
                if progress["state"] == "PASS":
                    break
                raise ValueError("Functional owner is not active and has no PASS")
            if time.monotonic() >= deadline:
                raise TimeoutError("Functional gate exceeded bounded wait; no VCS dispatch")
            time.sleep(60)
        functional_gate(source, progress)
        pins = json.loads((build / "manifest.json").read_text())
        if hashes(map(Path, pins)) != pins:
            raise ValueError("Candidate build inputs changed")
        report = json.loads((build / "build.json").read_text())
        app = report["app"]
        if digest(build / app) != report["candidate_sha256"]:
            raise ValueError("Candidate ELF changed")
        state.update(state="running_vcs", functional_pass_sha256=digest(source / "status.json"),
                     candidate_sha256=report["candidate_sha256"])
        atomic_json(out / "status.json", state)
        command = [sys.executable, str(ROOT / "verification/qbs/run_half_scale_soc.py"),
                   "--output", str(out / "soc"), "--tools-root", "/home/wangwy/openproject/ara_dsa",
                   "--elf-dir", str(build), "--simv", str(args.simv.resolve(strict=True)),
                   "--cases", app, "--l2-mb", "16", "--timeout", "2700"]
        with (out / "worker.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        atomic_json(out / "status.json", state)


if __name__ == "__main__":
    main()
