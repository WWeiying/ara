#!/usr/bin/env python3
"""Prepare, then explicitly replay a completed exploration batch (no RTL builds).

Preparation is the default and never simulates. Execute with --execute-prepared
as the main process of a dedicated systemd user service: KillMode=control-group,
Restart=no, RemainAfterExit=no, ARA_CHECKPOINT_UNIT=<unit>. The existing supervisor
stops on infrastructure errors; normal case failures return zero from workers.
The service is required to clean up runners' descendants, including new sessions.
An interrupted/stopped output cannot be resumed or silently overwritten.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
COVERAGE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(ROOT / "verification"))

from build_provenance import collect
from merge_exploration import validate_sample
from run_batch_exploration import NORMAL_FAILURES, check_identity as check_batch
from run_coverage_checkpoint import check_service, checked_output, save
from run_verilator_coverage import sha256

SCOPES = {"line": True, "expression": True, "toggle": False,
          "fsm": False, "assertion": False}
SCOPE_ARGS = ["--hierarchy-prefix", "ara_tb_verilator.dut.i_ara_soc",
              "--include-path", "/hardware/src/", "--include-path", "/hardware/deps/cva6/"]
ENV_ERROR = re.compile(r"error while loading shared libraries|No space left on device|"
                       r"Cannot allocate memory|std::bad_alloc|Permission denied|"
                       r"Traceback \(most recent call last\)", re.I)


def read(path):
    return json.loads(Path(path).read_text())


def pin(paths):
    return {str(Path(p).resolve(strict=True)): sha256(Path(p)) for p in paths}


def check_files(files):
    for path, expected in files.items():
        if sha256(Path(path)) != expected:
            raise RuntimeError(f"input drift: {path}")


def check_sources(path):
    saved = read(path)
    current = collect(Path(saved["filelist"]), Path(saved["repo_root"]), Path(saved["build_dir"]))
    if current != saved["files"]:
        raise RuntimeError("coverage source provenance drift")
    return saved


def check_source_stopped(batch, unit):
    """Require an identified, quiescent systemd cgroup, not just a dead MainPID."""
    if not unit or not re.fullmatch(r"[A-Za-z0-9_.@-]+\.service", unit):
        raise ValueError("source-pass-only requires an explicit --batch-unit")
    keys = ("LoadState", "ActiveState", "MainPID", "ControlPID", "ControlGroup", "TasksCurrent", "ExecStart")
    result = subprocess.run(["systemctl", "--user", "show", unit,
                             *[f"--property={key}" for key in keys]],
                            capture_output=True, text=True, check=True, timeout=10)
    state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if (state.get("LoadState") != "loaded" or state.get("ActiveState") not in ("inactive", "failed") or
            state.get("MainPID") != "0" or state.get("ControlPID") != "0" or
            str(batch) not in state.get("ExecStart", "")):
        raise RuntimeError("source batch service is unidentified or still live")
    group = state.get("ControlGroup", "")
    if group:
        root = Path("/sys/fs/cgroup")
        directory = (root / group.lstrip("/")).resolve()
        if directory == root or not directory.is_relative_to(root):
            raise RuntimeError("unsafe source cgroup path")
        if directory.exists() and any(path.read_text().strip()
                                      for path in directory.rglob("cgroup.procs")):
            raise RuntimeError("source batch cgroup still has processes")
    elif state.get("TasksCurrent") not in ("0", "[not set]"):
        raise RuntimeError("cannot prove source service has no remaining tasks")
    return state


def pass_source_snapshot(batch, unit):
    service = check_source_stopped(batch, unit)
    files = pin([batch / name for name in ("checkpoint.json", "plan.json", "identity.json")])
    state = read(batch / "checkpoint.json")
    rows = read(batch / "plan.json")["cases"]
    names = [row["name"] for row in rows]
    outcomes = state["cases"]
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", row["name"]) or
           row["kind"] not in ("random", "replay", "directed") for row in rows):
        raise RuntimeError("unsafe source plan case")
    if (state.get("status") not in ("STOPPED", "PASS", "COMPLETE_WITH_FAILURES", "INCOMPLETE_STIMULUS") or
            len(set(names)) != len(names) or state.get("total") != len(names) or
            not set(outcomes) <= set(names) or state.get("completed") != len(outcomes)):
        raise RuntimeError("source checkpoint is not a consistent terminal batch")
    selected = [row for row in rows if outcomes.get(row["name"], {}).get("status") == "PASS"]
    if not selected or state.get("passed") != len(selected):
        raise RuntimeError("source checkpoint PASS count disagrees or is empty")
    # No wrapper/checker waiver: historical identity and evidence must still verify.
    check_batch(batch)
    check_files(files)
    return {"mode": "SOURCE_PASS_ONLY", "batch": str(batch), "batch_unit": unit,
            "original_status": state["status"], "original_total": len(rows),
            "original_checkpoint": state, "selected_count": len(selected),
            "selected_names": [row["name"] for row in selected],
            "selected_random": sum(row["kind"] == "random" for row in selected),
            "selected_directed": sum(row["kind"] == "directed" for row in selected),
            "excluded": [{"name": row["name"], "kind": row["kind"],
                          "original": outcomes.get(row["name"], {"status": "NOT_COMPLETED"})}
                         for row in rows if row not in selected],
            "complete_original_batch": False, "service_at_snapshot": service, "files": files}


def selection_summary(selection):
    return {key: value for key, value in selection.items()
            if key not in ("original_checkpoint", "service_at_snapshot", "files")}


def ready_cases(batch):
    state = read(batch / "checkpoint.json")
    rows = read(batch / "plan.json")["cases"]
    names = [row["name"] for row in rows]
    if (state.get("status") not in ("PASS", "COMPLETE_WITH_FAILURES") or
            state.get("infrastructure_errors") != 0 or not names or
            len(set(names)) != len(names) or set(state["cases"]) != set(names) or
            state.get("completed") != len(names) or state.get("total") != len(names)):
        raise RuntimeError("functional batch is not complete and ready")
    for row in rows:
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", row["name"]) or
                row["kind"] not in ("random", "replay", "directed")):
            raise ValueError("unsafe case name or unknown source kind")
        actual = state["cases"][row["name"]]
        if actual["status"] not in NORMAL_FAILURES | {"PASS"}:
            raise RuntimeError(f"non-case failure in batch: {actual}")
    return [(row, state["cases"][row["name"]]) for row in rows]


def validate_audit(report, case):
    required = ["require_complete", "require_trace"]
    if case["kind"] != "directed":
        required += ["require_vector", "require_full_match"]
    rows = report.get("cases", [])
    if (report.get("status") != "PASS" or report.get("errors") or
            report.get("case_count") != 1 or report.get("passed_cases") != 1 or
            report.get("failed_cases") != 0 or len(rows) != 1 or
            any(report.get("policy", {}).get(key) is not True for key in required) or
            rows[0].get("status") != "PASS" or rows[0].get("errors") or
            rows[0].get("name") != case["source_name"] or
            Path(rows[0]["artifact_dir"]).resolve() != Path(case["artifact_dir"])):
        raise RuntimeError("source lacks a matching independent VCS PASS audit")


def source_case(row, actual, output, identity):
    source = Path(actual["artifact_dir"]).resolve(strict=True)
    summary = Path(actual["summary"]).resolve(strict=True)
    records = read(summary)
    if (len(records) != 1 or records[0]["status"] != actual["status"] or
            Path(records[0]["artifact_dir"]).resolve() != source or
            not source.is_relative_to(summary.parent)):
        raise RuntimeError("checkpoint, summary and source result disagree")
    # Directed Runner stores TestResult only in summary.json, unlike random/replay.
    if row["kind"] != "directed" and read(source / "result.json")["status"] != actual["status"]:
        raise RuntimeError("checkpoint, summary and source result disagree")
    metadata = read(source / "inputs.json")
    elf = source / "input.elf"
    expected = metadata["binary"]["sha256"]
    if (Path(metadata["binary"]["path"]).resolve() != elf or sha256(elf) != expected or
            expected != row.get("elf_sha256", expected)):
        raise RuntimeError("source ELF hash mismatch")
    if metadata["simv"]["image_sha256"] != identity["images"][identity["image"]]:
        raise RuntimeError("source case used a different VCS image")
    files = [summary, source / "inputs.json", elf]
    if row["kind"] == "directed":
        files.extend((source / "command.json", source / "console.log"))
    else:
        files.append(source / "result.json")
    address = None
    if row["kind"] != "directed":
        command = source / "rtl.command.json"
        args = [arg for arg in read(command)["command"] if arg.startswith("+COMMIT_TOHOST=")]
        if len(args) != 1:
            raise RuntimeError("random source requires exactly one COMMIT_TOHOST")
        address = int(args[0].split("=", 1)[1], 16)
        if not 0x80000000 <= address <= 0x801ffff8 or address % 8:
            raise RuntimeError("random tohost must be aligned and inside the 2 MiB model")
        if metadata["spike"]["sha256"] != identity["files"][identity["spike"]]:
            raise RuntimeError("source case used a different Spike")
        files.append(command)
    case = {"name": row["name"], "kind": row["kind"], "source_status": actual["status"],
            "source_name": records[0]["name"], "artifact_dir": str(source),
            "summary": str(summary), "source_elf": str(elf), "elf_sha256": expected,
            "source_audit": actual.get("audit"), "tohost_addr": address}
    if actual["status"] == "PASS":
        if not case["source_audit"]:
            raise RuntimeError("source PASS is missing its independent audit")
        validate_audit(read(case["source_audit"]), case)
        files.append(Path(case["source_audit"]))
    case["source_files"] = pin(files)
    frozen = output / "inputs" / (row["name"] + ".elf")
    frozen.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(elf, frozen)
    check_files(case["source_files"])
    if sha256(frozen) != expected:
        raise RuntimeError("ELF changed while freezing")
    case["frozen_elf"] = str(frozen)
    case["source_files"].update(pin([frozen]))
    return case


def invoke(command, log, timeout):
    log.parent.mkdir(parents=True, exist_ok=True)
    save(log.with_suffix(".command.json"), {"command": command, "timeout_s": timeout})
    with log.open("w") as stream:
        return subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                              timeout=timeout, check=False).returncode


def prepare(batch, image_dir, reporter, output, source_pass_only=False, batch_unit=None,
            source_snapshot=None):
    selection = None
    if source_pass_only:
        if source_snapshot:
            saved = read(source_snapshot)
            if saved.get("batch") != str(batch) or saved.get("batch_unit") != batch_unit:
                raise RuntimeError("source snapshot refers to a different batch/service")
            check_files(saved["files"])
        selection = pass_source_snapshot(batch, batch_unit)
        if source_snapshot and selection_summary(selection) != selection_summary(saved):
            raise RuntimeError("source PASS selection changed after queuing")
        save(output / "source_selection.json", selection)
        state = selection["original_checkpoint"]
        rows = [(row, state["cases"][row["name"]]) for row in read(batch / "plan.json")["cases"]
                if row["name"] in selection["selected_names"]]
    else:
        rows = ready_cases(batch)
    status_path = image_dir / "status.json"
    status = read(status_path)
    image = image_dir / "Vara_tb_verilator"
    if (status.get("status") != "PASS" or status.get("source_check") != "PASS" or
            status.get("coverage") != SCOPES or Path(status["image"]).resolve() != image or
            not os.access(image, os.X_OK) or sha256(image) != status["image_sha256"]):
        raise RuntimeError("coverage image is not a frozen line/expression PASS build")
    manifest = image_dir / "source_manifest.json"
    sources = check_sources(manifest)
    for suffix in ("before", "after"):
        if read(image_dir / f"source_manifest.{suffix}.json") != sources:
            raise RuntimeError("coverage before/after provenance disagrees")
    identity = check_batch(batch)
    vcs = {row["path"]: row["sha256"] for row in identity["sources"]}
    verilator = {row["path"]: row["sha256"] for row in sources["files"]}
    shared = vcs.keys() & verilator.keys()
    if str(ROOT / "hardware/src/ara_dispatcher.sv") not in shared or any(
            vcs[path] != verilator[path] for path in shared):
        raise RuntimeError("VCS and coverage images do not share the same RTL checkpoint")
    if not os.access(reporter, os.X_OK):
        raise RuntimeError("missing coverage reporter")
    cases = [source_case(row, actual, output, identity) for row, actual in rows]
    fit = [str(ROOT / "verification/tools/soc-venv/bin/python"),
           str(COVERAGE / "check_elf_fit.py")]
    for case in cases:
        fit += ["--elf", case["frozen_elf"]]
    fit += ["--ram-bytes", "2097152", "--ram-word-bytes", "16",
            "--output", str(output / "elf_fit.json")]
    # A RAM/model incompatibility must not silently reduce requested coverage.
    if invoke(fit, output / "elf_fit.log", 120) != 0 or read(output / "elf_fit.json")["status"] != "PASS":
        raise RuntimeError("ELF/model preflight failed; inspect elf_fit.log/json")
    files = [status_path, manifest, image, reporter, SCRIPT,
             batch / "checkpoint.json", batch / "plan.json", batch / "identity.json",
             image_dir / "source_manifest.before.json", image_dir / "source_manifest.after.json",
             ROOT / "verification/verify.py", ROOT / "verification/run_batch_exploration.py",
             ROOT / "verification/run_coverage_checkpoint.py",
             ROOT / "verification/run_failfast_checkpoint.py"]
    files.extend(COVERAGE.glob("*.py"))
    files.extend((ROOT / "verification/ara_verify").glob("*.py"))
    if selection:
        files.append(output / "source_selection.json")
        if source_snapshot:
            files.append(source_snapshot)
    plan = {"schema_version": 1, "batch": str(batch), "image": str(image),
            "image_sha256": status["image_sha256"], "source_manifest": str(manifest),
            "reporter": str(reporter), "coverage": SCOPES, "jobs_max": 3,
            "term_cycles": 100000, "timeout_s": 900, "cases": cases,
            "shared_source_count": len(shared), "files": pin(files)}
    if selection:
        plan["source_selection"] = selection_summary(selection)
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pin([output / "plan.json"]))
    check_inputs(output, all_cases=True)
    save(output / "status.json", {"status": "PREPARED", "total": len(cases),
                                  "coverage": SCOPES, "simulations_started": False,
                                  "source_selection": plan.get("source_selection")})


def check_inputs(output, case=None, all_cases=False):
    check_files(read(output / "plan.sha256.json"))
    plan = read(output / "plan.json")
    check_files(plan["files"])
    check_sources(Path(plan["source_manifest"]))
    for item in plan["cases"] if all_cases else ([case] if case else []):
        check_files(item["source_files"])
    return plan


def replay_command(plan, case, target):
    command = [sys.executable, str(COVERAGE / "run_verilator_coverage.py"),
               "--simv", plan["image"], "--elf", case["frozen_elf"], "--output", str(target),
               "--verilator-coverage", plan["reporter"], "--term-cycles", "100000",
               "--timeout", "900"]
    if case["tohost_addr"] is not None:
        command += ["--tohost-addr", hex(case["tohost_addr"])]
    return command


def check_result(path, case, plan, rc):
    result = read(path)
    if rc not in (0, 1) or (rc == 0) != (result.get("status") == "PASS"):
        raise RuntimeError("coverage runner exit/result disagreement")
    for key, expected in (("simv_sha256", plan["image_sha256"]),
                          ("elf_sha256", case["elf_sha256"]),
                          ("term_cycles", 100000), ("timeout_s", 900),
                          ("tohost_addr", case["tohost_addr"])):
        if result.get(key) != expected:
            raise RuntimeError(f"coverage result identity differs: {key}")
    for key, digest in (("simv", "simv_sha256"), ("elf", "elf_sha256")):
        if Path(result[key]).parent != path.parent or sha256(Path(result[key])) != result[digest]:
            raise RuntimeError(f"frozen replay {key} changed")
    log = path.parent / "sim.log"
    if sha256(log) != result.get("sim_log_sha256"):
        raise RuntimeError("coverage log changed")
    with log.open(errors="replace") as stream:
        if any(ENV_ERROR.search(line) for line in stream):
            raise RuntimeError("coverage environment failure")
    if result.get("status") == "PASS":
        if (result.get("sim_returncode") != 0 or result.get("report_returncode") != 0 or
                result.get("self_check_pass") is not True):
            raise RuntimeError("malformed coverage PASS")
    elif (result.get("status") != "FAIL" or result.get("self_check_pass") is True or
          result.get("report_returncode") is not None or
          result.get("sim_returncode") not in (None, 0, 1, -6) or
          not (result.get("reason", "").startswith("timeout:") or
               result.get("reason") == "simulation or in-program self-check failed")):
        raise RuntimeError("unclassified coverage runner/report failure")
    raw = path.parent / "coverage.dat"
    sample = validate_sample(path) if raw.is_file() and raw.stat().st_size else None
    if result["status"] == "PASS" and sample is None:
        raise RuntimeError("passing replay has no valid raw coverage")
    return {"status": result["status"], "raw_valid": sample is not None,
            "partial": result["status"] != "PASS" or case["source_status"] != "PASS",
            "passed_only": result["status"] == case["source_status"] == "PASS",
            "result": str(path), "result_sha256": sha256(path), "sample": sample}


def worker(output, name):
    outcome_path = output / "outcomes" / f"{name}.json"
    try:
        plan = check_inputs(output)
        case = next(case for case in plan["cases"] if case["name"] == name)
        check_files(case["source_files"])
        fresh = None
        if case["source_status"] == "PASS":
            fresh = output / "audits" / f"{name}.json"
            fresh.parent.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, str(ROOT / "verification/verify.py"), "audit",
                       "--run", str(Path(case["summary"]).parent), "--require-trace",
                       "--output", str(fresh)]
            if case["kind"] != "directed":
                command += ["--require-vector", "--require-full-match"]
            if invoke(command, output / "logs" / f"{name}-audit.log", 300) != 0:
                raise RuntimeError("fresh independent VCS audit failed")
            validate_audit(read(fresh), case)
        target = output / "replays" / name
        rc = invoke(replay_command(plan, case, target), output / "logs" / f"{name}.log", 1020)
        outcome = check_result(target / "result.json", case, plan, rc)
        check_inputs(output, case)
        outcome.update(name=name, source_status=case["source_status"],
                       source_elf=case["source_elf"], elf_sha256=case["elf_sha256"],
                       source_audit=case["source_audit"], source_files=case["source_files"],
                       source_reaudit=str(fresh) if fresh else None,
                       source_reaudit_sha256=sha256(fresh) if fresh else None)
        save(outcome_path, outcome)
        return 0
    except Exception as error:
        save(outcome_path, {"name": name, "status": "INFRASTRUCTURE_ERROR", "reason": str(error)})
        return 1


def merge(output, plan):
    outcomes = [read(output / "outcomes" / f"{case['name']}.json") for case in plan["cases"]]
    if any(item["status"] not in ("PASS", "FAIL") for item in outcomes):
        raise RuntimeError("cannot merge incomplete or infrastructure-failed replay")
    for item in outcomes:
        check_files({item["result"]: item["result_sha256"]})
        if item["passed_only"]:
            check_files({item["source_reaudit"]: item["source_reaudit_sha256"]})
    for name, script, selected in (
            ("exploration", "merge_exploration.py", [x for x in outcomes if x["raw_valid"]]),
            ("passed-only", "merge_verilator_coverage.py", [x for x in outcomes if x["passed_only"]])):
        target = output / name
        if selected:
            command = [sys.executable, str(COVERAGE / script)]
            for item in selected:
                command += ["--case", item["result"]]
            command += ["--output", str(target), "--verilator-coverage", plan["reporter"], *SCOPE_ARGS]
            if invoke(command, output / "logs" / f"merge-{name}.log", 660) != 0:
                raise RuntimeError(f"{name} merge failed")
            if name == "passed-only":
                command = [sys.executable, str(COVERAGE / "audit_merged.py"),
                           "--audit", str(target / "audit.json"), "--minimum-cases", str(len(selected)),
                           "--report", str(target / "independent_audit.json")]
                if invoke(command, output / "logs" / "merge-audit.log", 300) != 0:
                    raise RuntimeError("strict merged coverage audit failed")
        save(target / "collection.json", {
            "status": "COLLECTED" if selected else "EMPTY", "coverage": SCOPES,
            "source_selection": plan.get("source_selection"),
            "purpose": "EXPLORATION_ONLY_NOT_CORRECTNESS_SIGNOFF" if name == "exploration"
                       else "INDEPENDENT_VCS_PASS_AND_COVERAGE_PASS",
            "source_plan": str(output / "plan.json"), "source_plan_sha256": sha256(output / "plan.json"),
            "includes_source_failures": any(x["source_status"] != "PASS" for x in selected),
            "includes_replay_failures": any(x["status"] != "PASS" for x in selected),
            "samples": selected})
    return outcomes


def execute(output, jobs):
    state = read(output / "status.json")
    try:
        check_service()
        if state["status"] != "PREPARED" or not 1 <= jobs <= 3:
            raise RuntimeError("requires PREPARED output and 1..3 workers")
        with (ROOT / "verification/out/.batch-coverage-replay.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            plan = check_inputs(output, all_cases=True)
            if plan.get("source_selection"):
                check_source_stopped(Path(plan["batch"]), plan["source_selection"]["batch_unit"])
            check_batch(Path(plan["batch"]))
            scheduler_plan = [{"name": row["name"], "cwd": str(ROOT), "command": [sys.executable,
                               str(SCRIPT), "--output", str(output), "--worker", row["name"]]}
                              for row in plan["cases"]]
            save(output / "scheduler-plan.json", scheduler_plan)
            state.update(status="RUNNING", jobs=jobs, simulations_started=True)
            save(output / "status.json", state)
            command = [sys.executable, str(ROOT / "verification/run_failfast_checkpoint.py"),
                       "--plan", str(output / "scheduler-plan.json"), "--jobs", str(jobs),
                       "--output", str(output / "scheduler")]
            if invoke(command, output / "scheduler.log", len(scheduler_plan) * 1320 + 120) != 0:
                raise RuntimeError("coverage queue stopped; inspect scheduler/STOP.json")
            check_inputs(output, all_cases=True)
            outcomes = merge(output, plan)
            check_inputs(output, all_cases=True)
            check_batch(Path(plan["batch"]))
            state.update(status="COMPLETE", replay_pass=sum(x["status"] == "PASS" for x in outcomes),
                         replay_fail=sum(x["status"] == "FAIL" for x in outcomes),
                         valid_raw=sum(x["raw_valid"] for x in outcomes),
                         passed_only=sum(x["passed_only"] for x in outcomes),
                         status_scope="collection complete, not functional correctness signoff")
            save(output / "status.json", state)
            return 0
    except Exception as error:
        state.update(status="STOPPED", reason=str(error))
        save(output / "status.json", state)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, help="completed functional batch (required for prepare)")
    parser.add_argument("--image-dir", type=Path)
    parser.add_argument("--source-pass-only", action="store_true",
                        help="explicit partial snapshot: only source PASS, preserve excluded cases")
    parser.add_argument("--batch-unit", help="quiescent source service required for source-pass-only")
    parser.add_argument("--source-snapshot", type=Path, help="optional pinned queue selection")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verilator-coverage", type=Path,
                        default=ROOT / "install/verilator/bin/verilator_coverage")
    parser.add_argument("--jobs", type=int, choices=range(1, 4), default=3)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--execute-prepared", action="store_true")
    modes.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = checked_output(args.output)
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.worker:
        return worker(output, args.worker)
    if args.execute_prepared:
        return execute(output, args.jobs)
    if not args.batch or not args.image_dir:
        parser.error("preparation requires --batch and --image-dir")
    if args.source_pass_only and not args.batch_unit:
        parser.error("--source-pass-only requires --batch-unit")
    if args.source_snapshot and not args.source_pass_only:
        parser.error("--source-snapshot requires --source-pass-only")
    output.mkdir(parents=True, exist_ok=False)
    try:
        options = {"source_pass_only": True, "batch_unit": args.batch_unit,
                   "source_snapshot": args.source_snapshot.resolve(strict=True) if args.source_snapshot else None}
        prepare(args.batch.resolve(strict=True), args.image_dir.resolve(strict=True),
                args.verilator_coverage.resolve(strict=True), output,
                **(options if args.source_pass_only else {}))
    except Exception as error:
        save(output / "status.json", {"status": "STOPPED", "phase": "prepare", "reason": str(error)})
        return 1
    print(f"PREPARED (not launched): {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
