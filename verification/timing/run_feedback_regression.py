#!/usr/bin/env python3
"""Detach a focused current-RTL regression without sharing simulation outputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TESTS = ["rvv:" + name for name in (
    "vfredusum", "vfredosum", "vfredmin", "vfredmax", "vfwredusum", "vfwredosum",
    "vfrec7", "vfrsqrt7", "vfdiv", "vfsqrt", "vfmacc", "vfnmsac",
    "vwiden_overlap_edges")] + ["app:vsaxpy"]


def sources():
    paths = subprocess.check_output([
        "git", "ls-files", "-z", "hardware/src", "hardware/include", "hardware/tb",
        "hardware/Makefile", "config", "Bender.yml", "Bender.lock"], cwd=ROOT)
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in paths.decode().split("\0") if name and (ROOT / name).is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test", action="append", help="override the representative test list")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    tests = args.test or TESTS
    out = args.output.resolve()
    if not args.worker:
        out.mkdir(parents=True, exist_ok=False)
        with (out / "driver.log").open("w") as log:
            command = [sys.executable, str(Path(__file__).resolve()),
                       "--worker", "--output", str(out)]
            for test in tests:
                command += ["--test", test]
            proc = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(f"started pid={proc.pid} output={out}")
        return
    status = {"state": "RUNNING", "pid": os.getpid(),
              "started": datetime.now(timezone.utc).isoformat(), "tests": tests,
              "source_sha256": sources()}
    status_path = out / "status.json"
    status_path.write_text(json.dumps(status, indent=2) + "\n")
    command = [sys.executable, "verification/verify.py", "run", "--jobs", "2",
               "--timeout", "600", "--output", str(out / "results")]
    for test in tests:
        command += ["--test", test]
    env = dict(os.environ, MAKEFLAGS="qbs=1 akv=1 akv_v2=1 zcc=0", PYTHONUNBUFFERED="1")
    try:
        focus = [sys.executable, "verification/verify.py", "run", "--test", "app:vsaxpy",
                 "--timeout", "600", "--output", str(out / "focus")]
        if subprocess.run(focus, cwd=ROOT, env=env).returncode:
            raise RuntimeError("focused AXPY failed; broader regression was not started")
        command += ["--skip-build", "--simv", str(out / "focus/_build/vcs/simv")]
        result = subprocess.run(command, cwd=ROOT, env=env)
        summary = out / "results/summary.json"
        state = "PASS" if result.returncode == 0 and summary.is_file() else "FAIL"
        status.update(state=state, returncode=result.returncode)
        if sources() != status["source_sha256"]:
            status.update(state="INVALIDATED", error="RTL inputs changed during the regression")
    except Exception as exc:
        status.update(state="FAIL", error=str(exc))
    status["finished"] = datetime.now(timezone.utc).isoformat()
    status_path.write_text(json.dumps(status, indent=2) + "\n")


if __name__ == "__main__":
    main()
