#!/usr/bin/env python3
"""Snapshot a stopped coverage queue, then explicitly execute only missing outcomes.

Preparation never simulates. Execute as the MAIN process of a dedicated systemd
user service, KillMode=control-group, Restart=no, RemainAfterExit=no, with
ARA_CHECKPOINT_UNIT set. Nested runner sessions require cgroup cleanup on errors.
Completed prior failures remain failures; interrupted jobs without outcomes retry
in this NEW output. No old output, checker, image, or RTL is modified.
"""

import argparse
from collections import Counter
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import run_batch_coverage as old
import run_graceful_coverage as graceful

ROOT, COVERAGE = old.ROOT, old.COVERAGE
SCRIPT = Path(__file__).resolve()
read, save, sha256 = old.read, old.save, old.sha256


def stopped(unit):
    if not unit or not re.fullmatch(r"[A-Za-z0-9_.@-]+\.service", unit):
        raise ValueError("explicit previous service name required")
    keys = ("LoadState", "ActiveState", "MainPID", "ControlPID", "ControlGroup", "TasksCurrent")
    result = subprocess.run(["systemctl", "--user", "show", unit,
                             *[f"--property={key}" for key in keys]],
                            capture_output=True, text=True, check=True, timeout=10)
    state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if (state.get("LoadState") not in ("loaded", "not-found") or
            state.get("ActiveState") not in ("inactive", "failed") or
            state.get("MainPID") != "0" or state.get("ControlPID") != "0" or
            state.get("TasksCurrent") not in ("0", "[not set]")):
        raise RuntimeError("previous service is live or its quiescence is unknown")
    group = state.get("ControlGroup", "")
    if group:
        root = Path("/sys/fs/cgroup")
        directory = (root / group.lstrip("/")).resolve()
        if directory == root or not directory.is_relative_to(root):
            raise RuntimeError("unsafe cgroup path")
        if directory.exists() and any(p.read_text().strip() for p in directory.rglob("cgroup.procs")):
            raise RuntimeError("previous cgroup still populated")
    # Transient units may be unloaded after stop. Check the exact unit component,
    # not command substrings or signal-zero probes (which can be unreliable).
    for path in Path("/proc").glob("[0-9]*/cgroup"):
        try:
            groups = path.read_text().splitlines()
        except FileNotFoundError:
            continue
        if any(unit in line.split(":", 2)[-1].split("/") for line in groups):
            raise RuntimeError(f"previous service has a remaining task: {path}")
    return state


def inventory(previous, cases):
    names = [case["name"] for case in cases]
    if (len(set(names)) != len(names) or
            any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", n) for n in names)):
        raise ValueError("invalid or duplicate plan names")
    found = {}
    for path in sorted((previous / "outcomes").glob("*.json")):
        record = read(path)
        name = record.get("name")
        if name not in names or path.stem != name or name in found:
            raise ValueError(f"unknown/duplicate outcome: {path}")
        if record.get("status") not in ("PASS", "FAIL", "INFRASTRUCTURE_ERROR"):
            raise ValueError(f"incomplete previous outcome: {path}")
        found[name] = path
    # replays/result.json and scheduler state are NOT completion authorities.
    return found, [name for name in names if name not in found]


def inherited_evidence(path, case, plan):
    item = read(path)
    files = old.pin([path])
    if item["status"] == "INFRASTRUCTURE_ERROR":
        if item.get("raw_valid") or item.get("passed_only"):
            raise ValueError("infrastructure outcome cannot contribute coverage")
        return files
    result_path = Path(item["result"])
    old.check_files({str(result_path): item["result_sha256"]})
    validated = old.check_result(result_path, case, plan, 0 if item["status"] == "PASS" else 1)
    for key, value in validated.items():
        if item.get(key) != value:
            raise ValueError(f"old outcome/result disagreement: {key}: {path}")
    for key in ("source_status", "source_elf", "elf_sha256", "source_audit", "source_files"):
        if item.get(key) != case[key]:
            raise ValueError(f"old outcome/source disagreement: {key}")
    fresh = Path(item["source_reaudit"])
    old.check_files({str(fresh): item["source_reaudit_sha256"]})
    old.validate_audit(read(fresh), case)
    result = read(result_path)
    files.update(old.pin([result_path, fresh, Path(result["simv"]), Path(result["elf"]),
                          result_path.parent / "sim.log"]))
    for name in ("coverage.dat", "coverage.info"):
        artifact = result_path.parent / name
        if artifact.is_file():
            files.update(old.pin([artifact]))
    return files


def check_inputs(output, case=None, all_cases=False):
    plan = old.check_inputs(output, case, all_cases)
    found, pending = inventory(Path(plan["previous"]), plan["cases"])
    if list(found) != plan["inherited_names"] or pending != plan["pending_names"]:
        raise RuntimeError("previous outcomes inventory changed after snapshot")
    return plan


def prepare(previous, unit, reference, output):
    service = stopped(unit)
    original = old.check_inputs(previous, all_cases=True)
    old.check_batch(Path(original["batch"]))
    if original["coverage"] != old.SCOPES or any(c["source_status"] != "PASS" for c in original["cases"]):
        raise ValueError("requires the same frozen image and source PASS selection")
    found, pending = inventory(previous, original["cases"])
    cases = {case["name"]: case for case in original["cases"]}
    files = dict(original["files"])
    files.update(old.pin([previous / "plan.json", previous / "plan.sha256.json",
                          previous / "status.json", SCRIPT, COVERAGE / "run_graceful_coverage.py"]))
    for name, path in found.items():
        files.update(inherited_evidence(path, cases[name], original))
        target = output / "outcomes" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if sha256(target) != files[str(path)]:
            raise RuntimeError("outcome changed while snapshotting")
        files.update(old.pin([target]))
    matches = [read(path) for path in found.values() if read(path).get("result") == str(reference)]
    if len(matches) != 1 or not matches[0].get("passed_only"):
        raise ValueError("reference must be an inherited independently audited PASS")
    _, reference_pins = graceful.reference_points(reference, original["image_sha256"])
    files.update(reference_pins)
    plan = dict(original, schema_version=2, previous=str(previous), previous_unit=unit,
                previous_service_at_snapshot=service, inherited_names=list(found), pending_names=pending,
                reference_result=str(reference), grace_s=120, timeout_s=900, term_cycles=100000,
                jobs_max=3, files=files)
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", old.pin([output / "plan.json"]))
    check_inputs(output, all_cases=True)
    stopped(unit)
    save(output / "status.json", {"status": "PREPARED", "phase": "coverage",
         "total": len(plan["cases"]), "inherited": len(found), "pending": len(pending),
         "inherited_counts": dict(Counter(read(path)["status"] for path in found.values())),
         "source_selection": plan.get("source_selection"), "coverage": old.SCOPES,
         "simulations_started": False})


def replay_command(plan, case, target):
    command = [sys.executable, str(COVERAGE / "run_graceful_coverage.py"),
               "--simv", plan["image"], "--elf", case["frozen_elf"], "--output", str(target),
               "--verilator-coverage", plan["reporter"], "--reference-result", plan["reference_result"],
               "--term-cycles", "100000", "--timeout", "900", "--grace", "120"]
    if case["tohost_addr"] is not None:
        command += ["--tohost-addr", hex(case["tohost_addr"])]
    return command


def check_result(path, case, plan, rc):
    result = read(path)
    if (result.get("infrastructure_errors") or rc not in (0, 1) or
            result.get("status") not in ("PASS", "FAIL", "TIMEOUT") or
            (rc == 0) != (result["status"] == "PASS")):
        raise RuntimeError("graceful runner infrastructure failure or exit/result disagreement")
    for key, expected in (("simv_sha256", plan["image_sha256"]), ("elf_sha256", case["elf_sha256"]),
                          ("term_cycles", 100000), ("timeout_s", 900), ("grace_s", 120),
                          ("tohost_addr", case["tohost_addr"]), ("reference_result", plan["reference_result"]),
                          ("reporter_sha256", plan["files"][plan["reporter"]])):
        if result.get(key) != expected:
            raise RuntimeError(f"graceful result identity differs: {key}")
    old.check_files({result["simv"]: result["simv_sha256"], result["elf"]: result["elf_sha256"],
                     str(path.parent / "sim.log"): result["sim_log_sha256"]})
    if any(Path(result[key]).parent != path.parent for key in ("simv", "elf")):
        raise RuntimeError("result does not reference its frozen replay inputs")
    if (result.get("timed_out") != (result["status"] == "TIMEOUT") or
            (result["status"] == "PASS" and (not result.get("replay_pass_eligible") or
             not result.get("self_check_pass") or result.get("sim_returncode") != 0))):
        raise RuntimeError("timeout/PASS classification disagreement")
    valid = result.get("exploration_eligible") is True
    if valid and (result.get("raw_valid") is not True or result.get("denominator_check") != "PASS" or
                  result.get("report_returncode") != 0):
        raise RuntimeError("partial raw lacks complete denominator/report validation")
    sample = old.validate_sample(path) if valid else None
    if result["status"] == "PASS" and not valid:
        raise RuntimeError("PASS missing valid coverage")
    return {"status": result["status"], "raw_valid": valid, "sample": sample,
            "partial": result["status"] != "PASS", "passed_only": result["status"] == "PASS",
            "result": str(path), "result_sha256": sha256(path)}


def worker(output, name):
    outcome_path = output / "outcomes" / f"{name}.json"
    if outcome_path.exists():
        return 1  # Never overwrite a completed inherited or new outcome.
    try:
        plan = check_inputs(output)
        if name not in plan["pending_names"]:
            raise ValueError("worker not in frozen pending set")
        case = next(c for c in plan["cases"] if c["name"] == name)
        old.check_files(case["source_files"])
        fresh = output / "audits" / f"{name}.json"
        fresh.parent.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, str(ROOT / "verification/verify.py"), "audit",
                   "--run", str(Path(case["summary"]).parent), "--require-trace", "--output", str(fresh)]
        if case["kind"] != "directed":
            command += ["--require-vector", "--require-full-match"]
        if old.invoke(command, output / "logs" / f"{name}-audit.log", 300) != 0:
            raise RuntimeError("fresh independent VCS source audit failed")
        old.validate_audit(read(fresh), case)
        target = output / "replays" / name
        rc = old.invoke(replay_command(plan, case, target), output / "logs" / f"{name}.log", 1200)
        item = check_result(target / "result.json", case, plan, rc)
        check_inputs(output, case)
        item.update({key: case[key] for key in ("name", "source_status", "source_elf", "elf_sha256",
                                                "source_audit", "source_files")})
        item.update(source_reaudit=str(fresh), source_reaudit_sha256=sha256(fresh))
        save(outcome_path, item)
        return 0  # TIMEOUT/FAIL are ordinary replay outcomes, not queue infrastructure errors.
    except Exception as error:
        save(outcome_path, {"name": name, "status": "INFRASTRUCTURE_ERROR", "reason": str(error)})
        return 1


def merge(output, plan):
    outcomes = [read(output / "outcomes" / f"{c['name']}.json") for c in plan["cases"]]
    for item in outcomes:
        if item["status"] == "INFRASTRUCTURE_ERROR":
            if item["name"] not in plan["inherited_names"]:
                raise RuntimeError("new infrastructure failure")
            continue
        old.check_files({item["result"]: item["result_sha256"],
                         item["source_reaudit"]: item["source_reaudit_sha256"]})
    for name, script, selected in (
            ("exploration", "merge_exploration.py", [x for x in outcomes if x.get("raw_valid")]),
            ("passed-only", "merge_verilator_coverage.py", [x for x in outcomes if x.get("passed_only")])):
        target = output / name
        if selected:
            command = [sys.executable, str(COVERAGE / script)]
            for item in selected:
                command += ["--case", item["result"]]
            command += ["--output", str(target), "--verilator-coverage", plan["reporter"], *old.SCOPE_ARGS]
            if old.invoke(command, output / "logs" / f"merge-{name}.log", 660) != 0:
                raise RuntimeError(f"{name} merge failed")
            if name == "passed-only":
                command = [sys.executable, str(COVERAGE / "audit_merged.py"), "--audit",
                           str(target / "audit.json"), "--minimum-cases", str(len(selected)),
                           "--report", str(target / "independent_audit.json")]
                if old.invoke(command, output / "logs/merge-audit.log", 300) != 0:
                    raise RuntimeError("strict merged coverage audit failed")
        save(target / "collection.json", {"status": "COLLECTED" if selected else "EMPTY",
             "coverage": old.SCOPES, "source_selection": plan.get("source_selection"),
             "source_plan": str(output / "plan.json"), "source_plan_sha256": sha256(output / "plan.json"),
             "inherited_names": plan["inherited_names"], "includes_source_failures": False,
             "includes_replay_failures": any(x["status"] != "PASS" for x in selected),
             "purpose": "EXPLORATION_ONLY_NOT_CORRECTNESS_SIGNOFF" if name == "exploration"
                        else "INDEPENDENT_VCS_PASS_AND_COVERAGE_PASS", "samples": selected})
    return outcomes


def scheduler_rows(plan, output):
    return [{"name": name, "cwd": str(ROOT), "command": [sys.executable, str(SCRIPT),
             "--output", str(output), "--worker", name]} for name in plan["pending_names"]]


def execute(output, jobs):
    state = read(output / "status.json")
    try:
        old.check_service()
        if state["status"] != "PREPARED" or not 1 <= jobs <= 3:
            raise RuntimeError("requires PREPARED output and 1..3 workers")
        with (ROOT / "verification/out/.batch-coverage-replay.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            plan = check_inputs(output, all_cases=True)
            stopped(plan["previous_unit"])
            old.check_batch(Path(plan["batch"]))
            rows = scheduler_rows(plan, output)
            save(output / "scheduler-plan.json", rows)
            state.update(status="RUNNING", jobs=jobs, simulations_started=bool(rows))
            save(output / "status.json", state)
            if rows:
                command = [sys.executable, str(ROOT / "verification/run_failfast_checkpoint.py"),
                           "--plan", str(output / "scheduler-plan.json"), "--jobs", str(jobs),
                           "--output", str(output / "scheduler")]
                if old.invoke(command, output / "scheduler.log", len(rows) * 1560 + 120) != 0:
                    raise RuntimeError("queue stopped; inspect scheduler/STOP.json")
            check_inputs(output, all_cases=True)
            outcomes = merge(output, plan)
            check_inputs(output, all_cases=True)
            old.check_batch(Path(plan["batch"]))
            state.update(status="COMPLETE", completed=len(outcomes),
                         counts=dict(Counter(x["status"] for x in outcomes)),
                         valid_raw=sum(bool(x.get("raw_valid")) for x in outcomes),
                         passed_only=sum(bool(x.get("passed_only")) for x in outcomes),
                         status_scope="collection complete, not correctness signoff")
            save(output / "status.json", state)
            return 0
    except Exception as error:
        state.update(status="STOPPED", reason=str(error))
        save(output / "status.json", state)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--previous-unit")
    parser.add_argument("--reference-result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 4), default=3)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute-prepared", action="store_true")
    modes.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = old.checked_output(args.output)
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.worker:
        return worker(output, args.worker)
    if args.execute_prepared:
        return execute(output, args.jobs)
    if not all((args.previous, args.previous_unit, args.reference_result)):
        parser.error("prepare requires --previous, --previous-unit and --reference-result")
    output.mkdir(parents=True, exist_ok=False)
    try:
        with (ROOT / "verification/out/.batch-coverage-replay.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            prepare(args.previous.resolve(strict=True), args.previous_unit,
                    args.reference_result.resolve(strict=True), output)
    except Exception as error:
        save(output / "status.json", {"status": "STOPPED", "phase": "prepare", "reason": str(error)})
        return 1
    print(f"PREPARED, NOT LAUNCHED: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
