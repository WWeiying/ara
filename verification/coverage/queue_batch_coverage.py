#!/usr/bin/env python3
"""Wait in a background service for a frozen batch/build, then run coverage."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_coverage_checkpoint import check_service, save
from run_batch_coverage import check_files, check_source_stopped, pass_source_snapshot, selection_summary


def ready(path, unit, allowed):
    result = subprocess.run(["systemctl", "--user", "show", unit,
                             "-p", "ActiveState", "-p", "Result"],
                            capture_output=True, text=True, timeout=5, check=True)
    state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    report = json.loads(path.read_text()) if path.is_file() else {}
    status = report.get("status", "MISSING")
    if status in ("STOPPED", "FAIL") or state.get("ActiveState") == "failed":
        raise RuntimeError(f"dependency failed: {unit}: {status}")
    if status not in allowed and state.get("ActiveState") not in ("active", "activating"):
        raise RuntimeError(f"dependency is not live and lacks completion: {unit}: {status}")
    return status in allowed and state.get("ActiveState") == "inactive"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--batch-unit", required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--build-unit", required=True)
    parser.add_argument("--queue-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-pass-only", action="store_true")
    args = parser.parse_args()
    check_service()
    queue = args.queue_output.resolve()
    queue.mkdir(parents=True, exist_ok=False)
    state = {"status": "WAITING", "phase": "dependencies", "batch": str(args.batch),
             "image_dir": str(args.image_dir), "coverage_output": str(args.output)}
    save(queue / "checkpoint.json", state)
    try:
        snapshot = None
        if args.source_pass_only:
            snapshot = pass_source_snapshot(args.batch.resolve(strict=True), args.batch_unit)
            save(queue / "source_selection.json", snapshot)
            state.update(phase="build", source_selection=selection_summary(snapshot))
            save(queue / "checkpoint.json", state)
        deadline = time.monotonic() + 24 * 3600
        while True:
            if snapshot:
                check_files(snapshot["files"])
                check_source_stopped(args.batch.resolve(), args.batch_unit)
                batch_ready = True
            else:
                batch_ready = ready(args.batch / "checkpoint.json", args.batch_unit,
                                    {"PASS", "COMPLETE_WITH_FAILURES"})
            build_ready = ready(args.image_dir / "status.json", args.build_unit, {"PASS"})
            if batch_ready and build_ready:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("dependency wait exceeded 24 hours")
            time.sleep(30)
        script = ROOT / "verification/coverage/run_batch_coverage.py"
        command = [sys.executable, str(script), "--batch", str(args.batch),
                   "--image-dir", str(args.image_dir), "--output", str(args.output)]
        if snapshot:
            command += ["--source-pass-only", "--batch-unit", args.batch_unit,
                        "--source-snapshot", str(queue / "source_selection.json")]
        state.update(status="RUNNING", phase="prepare")
        save(queue / "checkpoint.json", state)
        with (queue / "prepare.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
        state.update(status="HANDED_OFF", phase="coverage",
                     note="Read the coverage output status.json for the final result.")
        save(queue / "checkpoint.json", state)
        # Keep the same service MainPID for the coverage driver's safety check.
        os.execv(sys.executable, [sys.executable, str(script), "--output", str(args.output),
                                 "--execute-prepared", "--jobs", "3"])
    except Exception as error:
        state.update(status="STOPPED", reason=str(error))
        save(queue / "checkpoint.json", state)
        raise


if __name__ == "__main__":
    main()
