from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .environment import resolve_bender
from .model import TestCase, TestResult
from .trace import TraceValidationError, validate_trace


SUCCESS_RE = re.compile(r"Core Test \*\*\* SUCCESS \*\*\*")
FAIL_RE = re.compile(
    r"Core Test \*\*\* FAILED \*\*\*|UVM_FATAL|Fatal:|"
    r"(?:Error|Fatal)[^\n]*(?:assertion|assert)[^\n]*fail|"
    r"^\s*(?:Index\s+\d+\s+)?FAILED(?:\.|\b)",
    re.IGNORECASE | re.MULTILINE,
)
REPORT_FILENAMES = ("summary.json", "summary.csv", "junit.xml")


@dataclass(frozen=True)
class RunOptions:
    repo_root: Path
    output_root: Path
    config: str
    jobs: int
    seed: int
    dry_run: bool
    build_only: bool
    skip_build: bool
    simv: Optional[Path]
    commit_trace: bool
    timeout_s: Optional[int]


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def _command_text(command: Sequence[object]) -> str:
    return shlex.join(str(item) for item in command)


def _invalidate_reports(output_root: Path) -> None:
    for filename in REPORT_FILENAMES:
        (output_root / filename).unlink(missing_ok=True)


def _run_logged(command: Sequence[object], cwd: Path, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {_command_text(command)}\n")
        log.flush()
        process = subprocess.run(
            [str(item) for item in command],
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if process.returncode != 0:
        raise RuntimeError(f"command failed ({process.returncode}); see {log_path}")


@contextmanager
def _apps_build_lock(repo_root: Path):
    repo_key = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"ara-verify-apps-{os.getuid()}-{repo_key}.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _run_apps_build(command: Sequence[object], repo_root: Path, log_path: Path) -> None:
    # The apps Makefile rewrites one shared linker script, so independent runners
    # must not execute app builds concurrently.
    with _apps_build_lock(repo_root):
        _run_logged(command, repo_root, log_path)


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_monitored(
    command: Sequence[object], cwd: Path, console_path: Path, timeout_s: int
) -> Tuple[int, float, bool, bool]:
    start = time.monotonic()
    observed_bytes = 0
    scan_tail = ""
    timed_out = False
    failure_seen = False

    with console_path.open("wb") as console:
        process = subprocess.Popen(
            [str(item) for item in command],
            cwd=cwd,
            stdout=console,
            stderr=subprocess.STDOUT,
        )

        while True:
            returncode = process.poll()
            with console_path.open("rb") as reader:
                reader.seek(observed_bytes)
                chunk = reader.read()
                observed_bytes = reader.tell()
            if chunk:
                decoded = chunk.decode("utf-8", errors="replace")
                scan_text = scan_tail + decoded
                if FAIL_RE.search(scan_text):
                    failure_seen = True
                    if returncode is None:
                        _stop_process(process)
                    break
                scan_tail = scan_text[-256:]

            if returncode is not None:
                break
            if time.monotonic() - start >= timeout_s:
                timed_out = True
                _stop_process(process)
                break
            time.sleep(0.1)

    return process.returncode, time.monotonic() - start, timed_out, failure_seen


def _git_metadata(repo_root: Path) -> Dict[str, object]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=repo_root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        )
        return result.stdout.strip()

    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "status": git("status", "--short").splitlines(),
    }


class RegressionRunner:
    def __init__(self, options: RunOptions, tests: Sequence[TestCase], invocation: Sequence[str]):
        self.options = options
        self.tests = list(tests)
        self.invocation = list(invocation)
        self.output_root = options.output_root.resolve()
        self.build_root = self.output_root / "_build"

    def prepare(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        _invalidate_reports(self.output_root)
        metadata = {
            "status": "DRY_RUN" if self.options.dry_run else "RUNNING",
            "created_at": datetime.now().astimezone().isoformat(),
            "invocation": self.invocation,
            "config": self.options.config,
            "jobs": self.options.jobs,
            "seed": self.options.seed,
            "simv": str(self.options.simv.resolve()) if self.options.simv else None,
            "commit_trace": self.options.commit_trace,
            "timeout_s": self.options.timeout_s,
            "tests": [test.name for test in self.tests],
            "git": _git_metadata(self.options.repo_root),
        }
        (self.output_root / "run.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _build_commands(self) -> List[List[object]]:
        targets = list(dict.fromkeys(test.build_target for test in self.tests))
        app_command: List[object] = [
            "make", "-C", "apps", f"-j{self.options.jobs}",
            f"config={self.options.config}", *targets,
        ]

        sim_dir = self.build_root / "vcs"
        hw_build = self.build_root / "hardware"
        relative_sim_dir = os.path.relpath(sim_dir, self.options.repo_root / "hardware")
        bender = resolve_bender(self.options.repo_root)
        hw_command: List[object] = [
            "make", "-C", "hardware", "compile",
            f"config={self.options.config}",
            f"buildpath={hw_build}",
            f"sim_dir={relative_sim_dir}",
            "fail_on_assert=1",
            "no_fsdb=1",
        ]
        if bender:
            hw_command.append(f"BENDER={bender}")
        return [app_command, hw_command]

    def build(self) -> Path:
        if self.options.simv:
            simv = self.options.simv.resolve()
            if not simv.is_file():
                raise RuntimeError(f"simv does not exist: {simv}")
            if not self.options.skip_build:
                command = self._build_commands()[0]
                if self.options.dry_run:
                    print(_command_text(command))
                else:
                    _run_apps_build(
                        command, self.options.repo_root, self.build_root / "apps-build.log"
                    )
            return simv

        commands = self._build_commands()
        if self.options.skip_build:
            simv = self.options.repo_root / "hardware/sim/simv"
            if not simv.is_file():
                raise RuntimeError("--skip-build requires --simv or hardware/sim/simv")
            return simv.resolve()

        if self.options.dry_run:
            for command in commands:
                print(_command_text(command))
            return (self.build_root / "vcs/simv").resolve()

        _run_apps_build(commands[0], self.options.repo_root, self.build_root / "apps-build.log")
        _run_logged(commands[1], self.options.repo_root, self.build_root / "vcs-build.log")
        simv = self.build_root / "vcs/simv"
        if not simv.is_file():
            raise RuntimeError(f"VCS completed without producing {simv}")
        return simv.resolve()

    def _run_test(self, test: TestCase, simv: Path) -> TestResult:
        artifact_dir = self.output_root / "tests" / _safe_name(test.name)
        work_dir = artifact_dir / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        command = [
            str(simv), "-l", "run.vcs.log",
            f"+ntb_random_seed={self.options.seed}",
            f"+PRELOAD={test.binary}",
            f"+TESTCASE={test.testcase}",
            "+NO_FSDB",
        ]
        commit_trace_path = artifact_dir / "commit_trace.csv"
        if self.options.commit_trace:
            command.append(f"+COMMIT_TRACE={commit_trace_path}")
        (artifact_dir / "command.json").write_text(
            json.dumps({"command": command, "cwd": str(work_dir)}, indent=2) + "\n",
            encoding="utf-8",
        )
        if self.options.dry_run:
            print(f"(cd {shlex.quote(str(work_dir))} && {_command_text(command)})")
            return TestResult(test.name, test.kind, "DRY_RUN", None, 0.0, "", artifact_dir)

        if not test.binary.is_file():
            return TestResult(test.name, test.kind, "ERROR", None, 0.0, "binary is missing", artifact_dir)

        console_path = artifact_dir / "console.log"
        timeout_s = self.options.timeout_s or test.timeout_s
        returncode, elapsed, timed_out, failure_seen = _run_monitored(
            command, work_dir, console_path, timeout_s
        )
        if timed_out:
            return TestResult(
                test.name, test.kind, "TIMEOUT", None, elapsed,
                f"timeout after {timeout_s}s", artifact_dir,
            )

        run_log = work_dir / "run.vcs.log"
        text = console_path.read_text(encoding="utf-8", errors="replace")
        if run_log.is_file():
            text += "\n" + run_log.read_text(encoding="utf-8", errors="replace")
        trace_error = ""
        if self.options.commit_trace and commit_trace_path.is_file() and not failure_seen and returncode == 0:
            try:
                trace_summary = validate_trace(commit_trace_path)
                (artifact_dir / "trace_summary.json").write_text(
                    json.dumps(trace_summary, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except TraceValidationError as error:
                trace_error = str(error)
        if failure_seen:
            status, reason = "FAIL", "failure marker found in simulation log"
        elif self.options.commit_trace and not commit_trace_path.is_file():
            status, reason = "FAIL", "commit trace was requested but not produced"
        elif trace_error:
            status, reason = "FAIL", f"invalid commit trace: {trace_error}"
        elif returncode != 0:
            status, reason = "FAIL", f"simulator exited with {returncode}"
        elif FAIL_RE.search(text):
            status, reason = "FAIL", "failure marker found in simulation log"
        elif not SUCCESS_RE.search(text):
            status, reason = "FAIL", "success marker was not found"
        else:
            status, reason = "PASS", ""
        return TestResult(test.name, test.kind, status, returncode, elapsed, reason, artifact_dir)

    def _write_reports(self, results: Sequence[TestResult]) -> None:
        serializable = []
        for result in results:
            item = asdict(result)
            item["artifact_dir"] = str(result.artifact_dir)
            serializable.append(item)
        (self.output_root / "summary.json").write_text(
            json.dumps(serializable, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        with (self.output_root / "summary.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=[
                "name", "kind", "status", "returncode", "elapsed_s", "reason", "artifact_dir"
            ])
            writer.writeheader()
            for item in serializable:
                writer.writerow(item)

        suite = ET.Element("testsuite", {
            "name": "ara-verification",
            "tests": str(len(results)),
            "failures": str(sum(result.status not in {"PASS", "DRY_RUN"} for result in results)),
            "time": f"{sum(result.elapsed_s for result in results):.3f}",
        })
        for result in results:
            case = ET.SubElement(suite, "testcase", {
                "name": result.name,
                "classname": result.kind,
                "time": f"{result.elapsed_s:.3f}",
            })
            if result.status not in {"PASS", "DRY_RUN"}:
                failure = ET.SubElement(case, "failure", {"message": result.reason})
                failure.text = str(result.artifact_dir)
        ET.ElementTree(suite).write(self.output_root / "junit.xml", encoding="utf-8", xml_declaration=True)

        run_path = self.output_root / "run.json"
        metadata = json.loads(run_path.read_text(encoding="utf-8"))
        metadata.update({
            "status": "DRY_RUN" if self.options.dry_run else "COMPLETE",
            "completed_at": datetime.now().astimezone().isoformat(),
            "status_counts": dict(Counter(result.status for result in results)),
        })
        run_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def run(self) -> List[TestResult]:
        self.prepare()
        simv = self.build()
        if self.options.build_only:
            return []

        results: List[TestResult] = []
        with ThreadPoolExecutor(max_workers=self.options.jobs) as executor:
            futures = {executor.submit(self._run_test, test, simv): test for test in self.tests}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print(
                    f"[{result.status:7}] {result.name:32} "
                    f"{result.elapsed_s:8.2f}s {result.reason}",
                    flush=True,
                )
        order = {test.name: index for index, test in enumerate(self.tests)}
        results.sort(key=lambda result: order[result.name])
        self._write_reports(results)
        return results


def default_output(repo_root: Path, label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / "verification" / "out" / f"{timestamp}_{_safe_name(label)}"
