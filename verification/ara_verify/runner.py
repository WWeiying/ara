from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import tempfile
import threading
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
from .contract import check_contract_log, parse_contract_summary
from .artifacts import check_inputs, sha256 as _sha256, simulation_image
from .model import TestCase, TestResult
from .trace import TraceValidationError, validate_trace
from .probes import check_probe_capture


SUCCESS_RE = re.compile(r"Core Test \*\*\* SUCCESS \*\*\*")
FAIL_RE = re.compile(
    r"Core Test \*\*\* FAILED \*\*\*|\bUVM_FATAL\b(?![ \t]*:[ \t]*0\b)|Fatal:|"
    r"(?:Error|Fatal)[^\n]*(?:assertion|assert)[^\n]*fail|"
    r"^\s*(?:Index\s+\d+\s+)?FAILED(?:\.|\b)",
    re.IGNORECASE | re.MULTILINE,
)


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
    contract_monitor: bool = False
    probe_kinds: Tuple[str, ...] = ()
    code_coverage: bool = False


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def _command_text(command: Sequence[object]) -> str:
    return shlex.join(str(item) for item in command)


def _sim_l2_mb(simv: Path) -> int:
    config = simv.resolve().parent / "simulator.conf"
    if not config.is_file():
        raise RuntimeError(f"reused simv has no simulator.conf: {config}")
    settings = {}
    for line in config.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key in settings:
            raise RuntimeError(f"invalid simulator.conf entry: {line!r}")
        settings[key] = value
    try:
        mb = int(settings["sim_l2_mb"])
        size = int(settings["sim_l2_bytes"])
    except (KeyError, ValueError) as error:
        raise RuntimeError(f"simulator.conf lacks a valid L2 size: {config}") from error
    if mb not in (1, 2, 4, 8, 16, 32, 64) or size != mb * 1024 * 1024:
        raise RuntimeError(f"simulator.conf has inconsistent L2 size: {config}")
    return mb


def _contract_evidence(console: Path, run_log: Path) -> Dict[str, object]:
    # VCS mirrors its output to both files; validate each separately rather than
    # concatenating them and mistaking the duplicate copy for a second run.
    issues = []
    logs = {}
    summaries = []
    for path in (console, run_log):
        if path == run_log and not path.is_file():
            issues.append("VCS run log is missing")
            continue
        errors = check_contract_log(path)
        issues.extend(f"{path.name}: {error}" for error in errors)
        counts = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                summary = parse_contract_summary(line)
                if summary is not None:
                    counts.append(summary)
            logs[str(path)] = {"sha256": _sha256(path), "summaries": counts}
        summaries.append(counts)
    if len(summaries) == 2 and summaries[0] != summaries[1]:
        issues.append("console and VCS protocol summaries disagree")
    return {"status": "FAIL" if issues else "PASS", "issues": issues, "logs": logs,
            "scope": "Ara request/response protocol; not execution completion or ISA equivalence"}


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
def _apps_build_lock(repo_root: Path, cancel_event: Optional[threading.Event] = None):
    """Yield whether the lock was acquired; snapshot waits may be cancelled."""
    repo_key = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"ara-verify-apps-{os.getuid()}-{repo_key}.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        if cancel_event is None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        else:
            while not cancel_event.is_set():
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    cancel_event.wait(0.1)
            else:
                yield False
                return
        try:
            yield True
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    # Only signal the private session created by _run_monitored.  A terminated
    # parent may otherwise leave a compiler/simulator child consuming resources.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def _run_monitored(
    command: Sequence[object], cwd: Path, console_path: Path, timeout_s: int,
    cancel_event: Optional[threading.Event] = None,
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
            start_new_session=True,
        )

        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    break
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
                        break
                    scan_tail = scan_text[-256:]

                if returncode is not None:
                    break
                if time.monotonic() - start >= timeout_s:
                    timed_out = True
                    break
                time.sleep(0.1)
        finally:
            _stop_process(process)

    return process.returncode, time.monotonic() - start, timed_out, failure_seen


@contextmanager
def _cancel_signals(event: threading.Event):
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {}
    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, lambda signum, frame: event.set())
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


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
        self.cancel_event = threading.Event()
        self._frozen_binaries: Dict[str, str] = {}
        self._suite_frozen = False

    def _freeze_programs_locked(self) -> None:
        # Called while holding the apps build lock: every case in this run
        # must observe the same completed application build.
        for test in self.tests:
            if not test.binary.is_file():
                continue
            snapshot = self.output_root / "tests" / _safe_name(test.name) / "input.elf"
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(test.binary.read_bytes())
            self._frozen_binaries[test.name] = _sha256(snapshot)
        self._suite_frozen = True

    def prepare(self) -> None:
        if self.options.code_coverage and (self.options.simv or self.options.skip_build):
            raise ValueError("--code-coverage requires a fresh instrumented VCS build")
        kinds = self.options.probe_kinds
        if len(set(kinds)) != len(kinds) or any(
            re.fullmatch(r"[a-z][a-z0-9_]*", kind) is None for kind in kinds
        ):
            raise ValueError("probe kinds must be distinct lowercase identifiers")
        names = [_safe_name(test.name) for test in self.tests]
        if len(set(names)) != len(names) or any(not name for name in names):
            raise ValueError("test names must map to distinct nonempty artifact directories")
        if self.options.output_root.is_symlink():
            raise ValueError("output directory must not be a symlink")
        if self.output_root.exists() and (
            not self.output_root.is_dir() or any(self.output_root.iterdir())
        ):
            raise ValueError(f"output must be new or empty; existing results preserved: {self.output_root}")
        self.output_root.mkdir(parents=True, exist_ok=True)
        try:
            with (self.output_root / ".run-owner").open("x", encoding="utf-8") as owner:
                json.dump({"pid": os.getpid(), "invocation": self.invocation}, owner)
        except FileExistsError as error:
            raise ValueError(f"another run owns output: {self.output_root}") from error
        metadata = {
            "status": "DRY_RUN" if self.options.dry_run else "RUNNING",
            "created_at": datetime.now().astimezone().isoformat(),
            "invocation": self.invocation,
            "config": self.options.config,
            "jobs": self.options.jobs,
            "seed": self.options.seed,
            "simv": str(self.options.simv.resolve()) if self.options.simv else None,
            "commit_trace": self.options.commit_trace,
            "contract_monitor": self.options.contract_monitor,
            "code_coverage": self.options.code_coverage,
            "probe_kinds": list(self.options.probe_kinds),
            "input_snapshots": True,
            "timeout_s": self.options.timeout_s,
            "tests": [test.name for test in self.tests],
            "git": _git_metadata(self.options.repo_root),
        }
        (self.output_root / "run.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _build_commands(self) -> List[List[object]]:
        targets = list(dict.fromkeys(test.build_target for test in self.tests))
        simv = self.options.simv
        if simv is None and self.options.skip_build:
            simv = self.options.repo_root / "hardware/sim/simv"
        app_command: List[object] = [
            "make", "-C", "apps", f"-j{self.options.jobs}",
            f"config={self.options.config}", *targets,
        ]
        if simv is not None:
            app_command.insert(5, f"sim_l2_mb={_sim_l2_mb(simv)}")

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
            "verify_source_manifest=1",
        ]
        if self.options.code_coverage:
            hw_command.append("code_coverage=1")
        if bender:
            hw_command.append(f"BENDER={bender}")
        if self.options.contract_monitor:
            monitor = self.output_root / "inputs/ara_acc_contract_monitor.sv"
            if self.options.dry_run:
                monitor = self.options.repo_root / "verification/uvm/ara_acc_contract_monitor.sv"
            extras = shlex.split(os.environ.get("verify_extra_sources", ""))
            extras = [path for path in extras if Path(path).name != monitor.name]
            hw_command.append(f"verify_extra_sources={' '.join([*extras, str(monitor)])}")
        return [app_command, hw_command]

    def build(self) -> Path:
        if self.options.contract_monitor and not self.options.dry_run:
            source = self.options.repo_root / "verification/uvm/ara_acc_contract_monitor.sv"
            monitor = self.output_root / "inputs" / source.name
            monitor.parent.mkdir(parents=True, exist_ok=True)
            monitor.write_bytes(source.read_bytes())
            metadata_path = self.output_root / "run.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["contract_monitor_source"] = {
                "path": str(monitor), "sha256": _sha256(monitor),
                "compiled_by_this_run": not (self.options.simv or self.options.skip_build),
            }
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if self.options.simv:
            simv = self.options.simv.resolve()
            if not simv.is_file():
                raise RuntimeError(f"simv does not exist: {simv}")
            if not self.options.skip_build:
                command = self._build_commands()[0]
                if self.options.dry_run:
                    print(_command_text(command))
                else:
                    with _apps_build_lock(self.options.repo_root):
                        _run_logged(command, self.options.repo_root,
                                    self.build_root / "apps-build.log")
                        if not self.options.build_only:
                            self._freeze_programs_locked()
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

        with _apps_build_lock(self.options.repo_root):
            _run_logged(commands[0], self.options.repo_root, self.build_root / "apps-build.log")
            if not self.options.build_only:
                self._freeze_programs_locked()
        _run_logged(commands[1], self.options.repo_root, self.build_root / "vcs-build.log")
        simv = self.build_root / "vcs/simv"
        if not simv.is_file():
            raise RuntimeError(f"VCS completed without producing {simv}")
        if self.options.code_coverage and not (
            self.build_root / "vcs/simv.vdb/snps/coverage/db/design/verilog.design.xml"
        ).is_file():
            raise RuntimeError("VCS completed without a coverage design database")
        source_manifest = self.build_root / "vcs/vcs_source_manifest.json"
        if not source_manifest.is_file():
            raise RuntimeError("VCS completed without a source manifest")
        metadata_path = self.output_root / "run.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["vcs_source_manifest"] = {
            "path": str(source_manifest), "sha256": _sha256(source_manifest)
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return simv.resolve()

    def _run_test(self, test: TestCase, simv: Path) -> TestResult:
        artifact_dir = self.output_root / "tests" / _safe_name(test.name)
        if self.cancel_event.is_set():
            return TestResult(test.name, test.kind, "CANCELLED", None, 0.0,
                              "cancelled before simulation started", artifact_dir)
        work_dir = artifact_dir / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        binary_snapshot = artifact_dir / "input.elf"
        preload = test.binary if self.options.dry_run else binary_snapshot
        command = [
            str(simv), "-l", "run.vcs.log",
            f"+ntb_random_seed={self.options.seed}",
            f"+PRELOAD={preload}",
            f"+TESTCASE={test.testcase}",
            "+NO_FSDB",
        ]
        if self.options.code_coverage:
            command.extend((
                "-cm", "line+cond+fsm+tgl+branch",
                "-cm_dir", str(work_dir / "code.vdb"),
                "-cm_name", _safe_name(test.name),
            ))
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

        if test.name not in self._frozen_binaries and (
            self._suite_frozen or not test.binary.is_file()
        ):
            return TestResult(test.name, test.kind, "ERROR", None, 0.0, "binary is missing", artifact_dir)

        if test.name not in self._frozen_binaries:
            # Direct single-case use still takes the build lock; normal suites
            # freeze all inputs together before starting worker threads.
            with _apps_build_lock(self.options.repo_root, self.cancel_event) as acquired:
                if not acquired or self.cancel_event.is_set():
                    return TestResult(test.name, test.kind, "CANCELLED", None, 0.0,
                                      "cancelled before program snapshot", artifact_dir)
                binary_snapshot.write_bytes(test.binary.read_bytes())
                self._frozen_binaries[test.name] = _sha256(binary_snapshot)
        provenance = {
            "binary": {"source": str(test.binary), "path": str(binary_snapshot),
                       "sha256": self._frozen_binaries[test.name]},
            "simv": {"path": str(simv), "image_sha256": simulation_image(simv)},
        }
        (artifact_dir / "inputs.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        (artifact_dir / "command.json").write_text(
            json.dumps({"command": command, "cwd": str(work_dir)}, indent=2) + "\n", encoding="utf-8"
        )

        console_path = artifact_dir / "console.log"
        timeout_s = self.options.timeout_s or test.timeout_s
        returncode, elapsed, timed_out, failure_seen = _run_monitored(
            command, work_dir, console_path, timeout_s, self.cancel_event
        )
        contract_error = ""
        probe_error = ""
        if self.options.probe_kinds:
            capture = check_probe_capture(work_dir, self.options.probe_kinds)
            (artifact_dir / "probe_capture.json").write_text(
                json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            if capture["status"] != "PASS":
                probe_error = "; ".join(capture["issues"])
        if self.options.contract_monitor:
            evidence = _contract_evidence(console_path, work_dir / "run.vcs.log")
            (artifact_dir / "contract_summary.json").write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            if evidence["status"] != "PASS":
                contract_error = "; ".join(evidence["issues"])
        if self.cancel_event.is_set():
            return TestResult(test.name, test.kind, "CANCELLED", returncode, elapsed,
                              "run cancelled; private process group stopped", artifact_dir)
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
                trace_summary = {"status": "VALID", **validate_trace(commit_trace_path)}
                (artifact_dir / "trace_summary.json").write_text(
                    json.dumps(trace_summary, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except TraceValidationError as error:
                trace_error = str(error)
        input_errors = check_inputs(provenance, binary_snapshot)
        if failure_seen:
            status, reason = "FAIL", "failure marker found in simulation log"
        elif contract_error:
            status, reason = "FAIL", f"contract monitor: {contract_error}"
        elif probe_error:
            status, reason = "FAIL", f"probe capture: {probe_error}"
        elif input_errors:
            status, reason = "FAIL", "; ".join(input_errors)
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
        elif self.options.code_coverage and not (
            work_dir / "code.vdb/snps/coverage/db/testdata" /
            _safe_name(test.name) / "siminfo.xml"
        ).is_file():
            status, reason = "FAIL", "VCS code coverage database was not produced"
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
            "status": ("DRY_RUN" if self.options.dry_run else
                       "INTERRUPTED" if self.cancel_event.is_set() else "COMPLETE"),
            "completed_at": datetime.now().astimezone().isoformat(),
            "status_counts": dict(Counter(result.status for result in results)),
        })
        run_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def run(self) -> List[TestResult]:
        self.prepare()
        try:
            simv = self.build()
        except Exception as error:
            path = self.output_root / "run.json"
            metadata = json.loads(path.read_text(encoding="utf-8"))
            metadata.update(status="BUILD_ERROR", error=str(error),
                            completed_at=datetime.now().astimezone().isoformat())
            path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            raise
        if self.options.build_only:
            path = self.output_root / "run.json"
            metadata = json.loads(path.read_text(encoding="utf-8"))
            metadata.update(status="DRY_RUN" if self.options.dry_run else "BUILT",
                            simv=str(simv), completed_at=datetime.now().astimezone().isoformat())
            path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return []

        results: List[TestResult] = []
        with _cancel_signals(self.cancel_event):
            if self.options.skip_build and not self.options.dry_run:
                with _apps_build_lock(self.options.repo_root, self.cancel_event) as acquired:
                    if acquired and not self.cancel_event.is_set():
                        self._freeze_programs_locked()
            with ThreadPoolExecutor(max_workers=self.options.jobs) as executor:
                futures = {executor.submit(self._run_test, test, simv): test for test in self.tests}
                try:
                    for future in as_completed(futures):
                        test = futures[future]
                        try:
                            result = future.result()
                        except Exception as error:
                            result = TestResult(test.name, test.kind, "ERROR", None, 0.0,
                                                f"{type(error).__name__}: {error}",
                                                self.output_root / "tests" / _safe_name(test.name))
                        results.append(result)
                        print(
                            f"[{result.status:7}] {result.name:32} "
                            f"{result.elapsed_s:8.2f}s {result.reason}",
                            flush=True,
                        )
                except BaseException:
                    self.cancel_event.set()
                    raise
        order = {test.name: index for index, test in enumerate(self.tests)}
        results.sort(key=lambda result: order[result.name])
        self._write_reports(results)
        return results


def default_output(repo_root: Path, label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / "verification" / "out" / f"{timestamp}_{_safe_name(label)}"
