#!/usr/bin/env python3
"""Compile once and check the shared QBS/AKV reader with two MMU latencies."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "hardware/deps/axi/src/axi_pkg.sv",
    "hardware/include/qbs_pkg.sv",
    "hardware/src/vlsu/qbs/qbs_read_engine.sv",
    "verification/qbs/qbs_read_engine_tb.sv",
)
HEADERS = ("hardware/deps/axi/include/axi/typedef.svh",)
CASES = (
    "nonidentity_unaligned", "noncontiguous_pages",
    "second_page_fault", "post_fault_reuse",
)
ERROR = re.compile(r"(?:^|\n)\s*(?:Fatal(?:-|:)|Error(?:-|:)|UVM_FATAL|UVM_ERROR)|"
                   r"Assertion.*(?:fail|FAIL)")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_output(output):
    if output.is_symlink() or (output.exists() and
                               (not output.is_dir() or any(output.iterdir()))):
        raise ValueError(f"output must be a new or empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    try:
        with (output / ".run-owner").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "created_at": now()}) + "\n")
    except FileExistsError as error:
        raise ValueError(f"another run owns output: {output}") from error
    return output.resolve()


def snapshot_sources(root, output):
    records = {}
    for relative in SOURCES + HEADERS:
        source = root / relative
        target = output / "inputs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # Compile the exact bytes hashed here, not a changing worktree file.
        content = source.read_bytes()
        target.write_bytes(content)
        records[relative] = {"path": str(source.resolve()),
                             "sha256": hashlib.sha256(content).hexdigest()}
    return records


def changed_sources(records):
    return [name for name, entry in records.items()
            if not Path(entry["path"]).is_file() or sha256(entry["path"]) != entry["sha256"]]


def stop_process_group(process):
    # A parent exiting on SIGTERM does not imply its compiler/simulator
    # children exited. Always clean the entire session we created.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def command_run(command, directory, timeout_s):
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "console.log"
    record = {"command": [str(value) for value in command], "cwd": str(directory),
              "started_at": now(), "timeout_s": timeout_s, "log": str(log),
              "status": "RUNNING"}
    save_json(directory / "command.json", record)
    start = time.monotonic()
    errors = []
    returncode = None
    status = "FAIL"
    process = None
    interrupted = None
    with log.open("wb") as stream:
        try:
            process = subprocess.Popen(record["command"], cwd=directory, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                returncode = process.wait(timeout=timeout_s)
                status = "PASS" if returncode == 0 else "FAIL"
            except subprocess.TimeoutExpired:
                status = "TIMEOUT"
                errors.append(f"timeout after {timeout_s}s")
        except OSError as error:
            errors.append(str(error))
        except (KeyboardInterrupt, SystemExit) as error:
            status = "INTERRUPTED"
            errors.append(type(error).__name__)
            interrupted = error
        finally:
            if process is not None:
                stop_process_group(process)
                returncode = process.returncode
    record.update(status=status, returncode=returncode, errors=errors,
                  elapsed_s=time.monotonic() - start, completed_at=now(),
                  log_sha256=sha256(log))
    save_json(directory / "command_result.json", record)
    if interrupted is not None:
        raise interrupted
    return record


def check_log(text, mode):
    errors = []
    if ERROR.search(text):
        errors.append("simulator reported an error/fatal/assertion failure")
    lines = text.splitlines()
    if lines.count("QBS read engine PASS") != 1:
        errors.append("missing or duplicate suite completion")
    if len(re.findall(r"^QBS read legacy cases PASS t=\d+$", text, re.M)) != 1:
        errors.append("legacy checks did not finish exactly once")
    cases = Counter(re.findall(r"^\[QBS_READ_CASE\] (\w+) PASS$", text, re.M))
    if cases != Counter(CASES):
        errors.append(f"case completions differ: {dict(cases)}")
    faults = Counter(re.findall(r"^QBS stalled-AR fault PASS mode=(\d+) delay=(\d+)$",
                                text, re.M))
    if faults != Counter((str(m), str(d)) for m in range(3) for d in (0, 6)):
        errors.append("stalled-AR drain matrix incomplete or duplicated")
    expected = "1" if mode == "combinational" else "0"
    responses = re.findall(r"^QBS_MMU_RESPONSE .*combinational=([01]) req=([01])", text, re.M)
    if not responses or any(value != (expected, "1") for value in responses):
        errors.append("MMU response evidence missing or wrong mode/request level")
    return errors


def run(output, vcs, compile_timeout=300, run_timeout=60):
    output = prepare_output(output)
    report = {"schema_version": 1, "status": "RUNNING", "started_at": now(),
              "scope": "shared reader RTL with behavioral AXI/MMU; not Linux or CVA6 MMU signoff",
              "cases": list(CASES), "runs": [], "errors": []}
    save_json(output / "summary.json", report)
    interrupted = None
    try:
        runner_source = output / "runner.py"
        runner_source.write_bytes(Path(__file__).read_bytes())
        report["runner_sha256"] = sha256(runner_source)
        records = snapshot_sources(ROOT, output)
        report["sources"] = records
        report["vcs"] = str(Path(vcs).resolve())
        for name, args in (("commit", ["rev-parse", "HEAD"]),
                           ("worktree_status", ["status", "--porcelain"]),
                           ("branch", ["branch", "--show-current"])):
            result = subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                                    capture_output=True, text=True)
            report[name] = result.stdout.strip()
        build = output / "build"
        command = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "+lint=TFIPC-L",
                   f"+incdir+{output / 'inputs/hardware/deps/axi/include'}",
                   *[str(output / "inputs" / name) for name in SOURCES],
                   "-top", "qbs_read_engine_tb", "-o", str(build / "simv"), "-l", "compile.log"]
        report["compile"] = command_run(command, build, compile_timeout)
        compile_text = (build / "console.log").read_text(errors="replace")
        report["compile_warnings"] = re.findall(r"^Warning-\[([^]]+)\]", compile_text, re.M)
        if report["compile"]["status"] != "PASS" or ERROR.search(compile_text):
            report["errors"].append("compile failed; simulations not started")
        elif not (build / "simv").is_file():
            report["errors"].append("compile produced no executable")
        else:
            report["simv_sha256"] = sha256(build / "simv")
            for mode in ("delayed", "combinational"):
                directory = output / mode
                command = [str(build / "simv"), "-l", "run.log"]
                if mode == "combinational":
                    command.append("+COMBINATIONAL_MMU")
                result = command_run(command, directory, run_timeout)
                errors = check_log((directory / "console.log").read_text(errors="replace"), mode)
                if result["status"] != "PASS":
                    errors.insert(0, f"simulator status {result['status']}")
                report["runs"].append({**result, "mode": mode, "check_errors": errors,
                                       "check_status": "FAIL" if errors else "PASS"})
                report["errors"].extend(f"{mode}: {error}" for error in errors)
                # A first failure already has full probes. Analyze it before rerunning.
                if errors:
                    break
            drift = changed_sources(records)
            if drift:
                report["errors"].append(f"live source changed during run: {drift}")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["errors"].append(str(error))
    except (KeyboardInterrupt, SystemExit) as error:
        interrupted = error
        report["errors"].append(f"run interrupted: {type(error).__name__}")
    if len(report["runs"]) != 2:
        report["errors"].append("both MMU variants have not completed")
    report.update(status="FAIL" if report["errors"] else "PASS", completed_at=now())
    save_json(output / "summary.json", report)
    if interrupted is not None:
        raise interrupted
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    vcs = shutil.which(args.vcs)
    if not vcs:
        parser.error(f"VCS executable not found: {args.vcs}")
    def terminate(signum, _frame):
        raise SystemExit(128 + signum)

    old_term = signal.signal(signal.SIGTERM, terminate)
    try:
        try:
            report = run(args.output, vcs)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    finally:
        signal.signal(signal.SIGTERM, old_term)
    print(json.dumps({"status": report["status"], "output": str(args.output.resolve()),
                      "errors": report["errors"]}, indent=2))
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
