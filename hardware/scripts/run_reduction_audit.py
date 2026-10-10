#!/usr/bin/env python3
"""Run already-built ELF tests with an explicitly selected Ara simulator.

VCS may exit zero after $fatal or a failed tohost test. A successful exit is
therefore necessary but insufficient: require the core PASS marker and reject
assertions, watchdogs, and failure markers. Keep each run in a separate folder.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(result, output):
    result["failures"] = re.findall(
        r"^.*(?:Fatal:|Error:|FAILED|\bFAIL\b|started at .*failed at|watchdog_timeout: 1).*$",
        output, re.MULTILINE)
    result["pass"] = (result["returncode"] == 0 and not result["failures"] and
                      "Core Test *** SUCCESS *** (tohost = 0)" in output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--sim-arg", action="append", default=[],
                        help="extra simulator argument (repeatable, e.g. +vcs+loopreport)")
    parser.add_argument("--recheck", action="store_true",
                        help="reclassify completed log files without rerunning simulation")
    parser.add_argument("apps", nargs="*")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    simulator = args.sim.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.recheck:
        manifest = json.loads((out / "manifest.json").read_text())
        for result in manifest["tests"]:
            classify(result, (out / result["app"] / "stdout.log").read_text(errors="replace"))
            print(f"{'PASS' if result['pass'] else 'FAIL'} {result['app']}")
        manifest["log_reclassified"] = True
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        sys.exit(0 if all(item["pass"] for item in manifest["tests"]) else 1)
    if not args.apps:
        parser.error("at least one application is required")
    if (out / "manifest.json").exists():
        parser.error("choose a new output directory to preserve earlier evidence")
    manifest = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "simulator": str(simulator), "simulator_sha256": sha256(simulator),
        "note": "Simulator build provenance must be checked against its compile log/filelist.",
        "tests": [],
    }
    # Freeze every input before launching any job: builds can otherwise replace
    # an ELF while it is queued, making a single suite span multiple versions.
    inputs = out / "inputs"
    inputs.mkdir()
    for app in args.apps:
        if Path(app).name != app:
            parser.error("application names must not contain directory components")
        shutil.copy2(root / "apps" / "bin" / app, inputs / app)

    def run(app):
        elf = inputs / app
        folder = out / app
        folder.mkdir()
        command = [str(simulator), "-no_save", f"+PRELOAD={elf}",
                   f"+TESTCASE={app}", "+NO_FSDB", "+PERF_WATCHDOG_CYCLES=200000",
                   "-l", "run.log"] + args.sim_arg
        result = {"app": app, "elf_sha256": sha256(elf), "command": command}
        started = time.monotonic()
        with (folder / "stdout.log").open("w") as log:
            try:
                process = subprocess.run(command, cwd=folder, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=args.timeout)
                result["returncode"] = process.returncode
            except subprocess.TimeoutExpired:
                result["returncode"] = "timeout"
        output = (folder / "stdout.log").read_text(errors="replace")
        result["seconds"] = round(time.monotonic() - started, 2)
        classify(result, output)
        print(f"{'PASS' if result['pass'] else 'FAIL'} {app} ({result['seconds']} s)",
              flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for result in pool.map(run, args.apps):
            manifest["tests"].append(result)
            (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    sys.exit(0 if all(item["pass"] for item in manifest["tests"]) else 1)


if __name__ == "__main__":
    main()
