#!/usr/bin/env python3
"""Prepare a same-image VCS batch; explicit execute uses at most eight workers.

No build or checker changes. Random ELFs use existing Spike/scalar/vector replay;
directed ELFs use the existing RegressionRunner selfcheck plus independent trace
audit. Ordinary test failures continue; infrastructure failure exits the main
systemd service, whose KillMode=control-group cleans up nested runner sessions.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import fcntl
import gzip
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import run_vcs_dve_checkpoint as base

ROOT, HERE = base.ROOT, base.HERE
SCRIPT = Path(__file__).resolve()
read, save, pins, check = base.read, base.save, base.pins, base.check
from ara_verify.artifacts import sha256, simulation_image
from ara_verify.catalog import load_catalog
from ara_verify.model import TestCase
from ara_verify.runner import RegressionRunner, RunOptions, _safe_name
from run_batch_exploration import classify, check_environment_logs
from run_failfast_checkpoint import stop_groups

CHECKPOINT = ROOT / "verification/out/vcs-dve-coverage-20260927-01"
METRIC_FILES = {f"{name}.verilog.data.xml" for name in ("line", "cond", "fsm", "tgl", "branch")}


def audit_ok(report, case, artifact):
    required = ["require_complete", "require_trace"]
    if case["kind"] != "directed":
        required += ["require_vector", "require_full_match"]
    rows = report.get("cases", [])
    if (report.get("status") != "PASS" or report.get("errors") or report.get("case_count") != 1 or
            report.get("passed_cases") != 1 or report.get("failed_cases") != 0 or len(rows) != 1 or
            rows[0].get("status") != "PASS" or rows[0].get("name") != case["source_name"] or
            rows[0].get("errors") or Path(rows[0]["artifact_dir"]).resolve() != artifact.resolve() or
            any(report.get("policy", {}).get(k) is not True for k in required)):
        raise RuntimeError("independent audit does not prove this case PASS")


def xml_root(path):
    with path.open("rb") as stream:
        compressed = stream.read(2) == b"\x1f\x8b"
    with (gzip.open(path, "rb") if compressed else path.open("rb")) as stream:
        return ET.parse(stream).getroot()


def valid_vdb(vdb, test, image):
    """Reject truncated/incomplete databases, even when a prefix is parseable."""
    root = vdb / "snps/coverage/db/testdata"
    if not root.is_dir() or sorted(p.name for p in root.iterdir() if p.is_dir()) != [test]:
        raise ValueError("missing or unexpected testdata directories")
    directory = root / test
    if {p.name for p in directory.glob("*.data.xml")} != METRIC_FILES:
        raise ValueError("incomplete or unexpected metric files")
    info = xml_root(directory / "siminfo.xml").find("srctest")
    if info is None or int(info.get("finishtime", "0")) <= int(info.get("starttime", "0")):
        raise ValueError("coverage test has no completed write timestamp")
    command = shlex.split(info.get("cmdline", ""))
    if not command or command[0] != image:
        raise ValueError("coverage test used a different simulator")
    for option, expected in (("-cm", base.METRICS), ("-cm_dir", str(vdb)), ("-cm_name", test)):
        if command.count(option) != 1 or command[command.index(option) + 1] != expected:
            raise ValueError(f"coverage siminfo differs: {option}")
    for name in METRIC_FILES:
        if xml_root(directory / name).tag != "covdata":
            raise ValueError(f"invalid coverage XML root: {name}")
    return base.inventory(vdb)


def adapter_command(config, args, cwd):
    if not cwd.is_relative_to(Path(config["results"])) or any(
            a == "-cm" or a.startswith("-cm_") for a in args):
        raise ValueError("invalid replay cwd or coverage override")
    names = [a.split("=", 1)[1] for a in args if a.startswith("+TESTCASE=")]
    if len(names) != 1 or not re.fullmatch(r"[A-Za-z0-9_.-]+", names[0]):
        raise ValueError("one safe TESTCASE required")
    check(config["image"])
    database = cwd / "code.vdb"
    if database.exists():
        raise ValueError("refuse to overwrite existing coverage")
    # Keep directed TESTCASE exactly unchanged; only the coverage label is normalized.
    test = re.sub(r"[^A-Za-z0-9_]", "_", names[0])
    return [config["simv"], *args, "-cm", base.METRICS, "-cm_dir", str(database), "-cm_name", test]


def selection(batch):
    state, source = read(batch / "checkpoint.json"), read(batch / "plan.json")["cases"]
    names = [row["name"] for row in source]
    if len(names) != len(set(names)) or state["total"] != len(source):
        raise ValueError("inconsistent source batch")
    rows = [(row, state["cases"][row["name"]]) for row in source
            if state["cases"].get(row["name"], {}).get("status") == "PASS"]
    if Counter(row["kind"] for row, _ in rows) != {"random": 186, "directed": 47}:
        raise ValueError("expected batch04's exact 186 random + 47 directed PASS selection")
    excluded = [{"name": row["name"], "original": state["cases"].get(row["name"])}
                for row in source if state["cases"].get(row["name"], {}).get("status") != "PASS"]
    return rows, {"batch": str(batch), "original_status": state["status"], "original_total": len(source),
                  "selected": len(rows), "excluded": excluded, "complete_original_batch": False}


def source_case(row, actual, output, catalog, reference_image, oracles):
    name = row["name"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("unsafe case name")
    summary, artifact, audit = Path(actual["summary"]), Path(actual["artifact_dir"]), Path(actual["audit"])
    records = read(summary)
    if len(records) != 1 or records[0]["status"] != "PASS" or Path(records[0]["artifact_dir"]) != artifact:
        raise ValueError("source summary and checkpoint disagree")
    record = records[0]
    case = dict(row, source_name=record["name"], source_summary=str(summary), source_audit=str(audit),
                source_artifact=str(artifact), oracle="selfcheck+trace-audit" if row["kind"] == "directed"
                else "Spike+scalar+vector+independent-audit")
    audit_ok(read(audit), case, artifact)
    metadata = read(artifact / "inputs.json")
    if metadata["simv"]["image_sha256"] != reference_image:
        raise RuntimeError("source PASS used a different frozen configuration")
    elf = artifact / "input.elf"
    check({str(elf): metadata["binary"]["sha256"]})
    frozen = output / "inputs" / (name + ".elf")
    frozen.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(elf, frozen)
    check({str(frozen): metadata["binary"]["sha256"]})
    case.update(frozen_elf=str(frozen), elf_sha256=sha256(frozen))
    evidence = [summary, audit, frozen, artifact / "inputs.json", elf]
    if row["kind"] == "directed":
        test = catalog.tests[row["test"]]
        if test.name != record["name"]:
            raise ValueError("directed catalog/source identity differs")
        case["directed_test"] = dict(asdict(test), binary=str(frozen))
        case["coverage_test"] = re.sub(r"[^A-Za-z0-9_]", "_", test.testcase)
    else:
        spike = Path(metadata["spike"]["path"])
        expected_spike = metadata["spike"]["sha256"]
        if str(spike) not in oracles:
            check({str(spike): expected_spike})
            oracles[str(spike)] = expected_spike
        elif oracles[str(spike)] != expected_spike:
            raise RuntimeError("source cases disagree on the shared Spike oracle")
        replay = output / "inputs" / (name + ".json")
        save(replay, [{"name": record["name"], "profile": record.get("profile", ""),
                       "seed": record["seed"], "status": "PASS", "elf": str(frozen)}])
        case.update(replay_summary=str(replay), spike=str(spike), spike_sha256=expected_spike,
                    coverage_test=record["name"])
        evidence.append(replay)
    # Prior PASS selects the stimulus; it is not reused as the new replay verdict.
    # Fresh oracle/audit evidence is hashed by worker(), so do not repeatedly
    # scan historical multi-gigabyte trace logs during input preparation.
    evidence.extend([artifact / "command.json"] if row["kind"] == "directed" else
                    [artifact / "rtl.command.json", artifact / "spike.command.json"])
    case["source_files"] = pins(evidence)
    return case


def inherited(case, original, checkpoint, image):
    record = read(checkpoint / "outcomes" / (original["name"] + ".json"))
    check(record["files"])
    if record["status"] != "PASS" or case["elf_sha256"] != original["elf_sha256"]:
        raise ValueError("overlap is not an identical PASS ELF")
    target = checkpoint / "results" / original["name"]
    artifact = target / "tests" / original["testcase"]
    audit_ok(read(target / "independent_audit.json"), case, artifact)
    files = valid_vdb(Path(record["vdb"]), original["testcase"], image)
    if files != record["vdb_files"]:
        raise RuntimeError("inherited coverage changed")
    evidence = dict(record["files"], **pins([checkpoint / "outcomes" / (original["name"] + ".json")]))
    return {"name": case["name"], "kind": case["kind"], "status": "PASS", "reused": True,
            "elf_sha256": case["elf_sha256"], "vdb": record["vdb"], "coverage_test": original["testcase"],
            "vdb_valid": True, "passed_only": True, "vdb_files": files, "files": evidence,
            "source_audit": case["source_audit"], "oracle": case["oracle"]}


def prepare(output, batch, checkpoint):
    output.mkdir(parents=True, exist_ok=False)
    if read(checkpoint / "status.json")["status"] != "PASS":
        raise RuntimeError("coverage checkpoint is not PASS")
    previous = base.frozen(checkpoint)
    base.sources(checkpoint / "sim/vcs_source_manifest.json")
    image = simulation_image(checkpoint / "sim/simv")
    check(read(checkpoint / "image.json"))
    catalog = load_catalog(ROOT, ROOT / "verification/suites.json")
    rows, selected = selection(batch)
    reference_image = simulation_image(base.REFERENCE / "sim/simv")
    oracles = {}
    cases = [source_case(row, actual, output, catalog, reference_image, oracles) for row, actual in rows]
    seed = next(c for c in previous["cases"] if c["name"] == "seed509")
    seed_source = read(seed["source_summary"])[0]
    cases.append(source_case({"name": "seed509", "kind": "replay", "timeout_s": 300,
                               "spike_timeout_s": 120, "watchdog_cycles": 250000},
                              {"summary": seed["source_summary"], "audit": seed["source_audit"],
                               "artifact_dir": seed_source["artifact_dir"]}, output, catalog, reference_image, oracles))
    files = pins([SCRIPT, Path(base.__file__), ROOT / "verification/run_batch_exploration.py",
                  ROOT / "verification/run_failfast_checkpoint.py", ROOT / "verification/suites.json",
                  batch / "plan.json", batch / "checkpoint.json", checkpoint / "status.json",
                  checkpoint / "plan.json", checkpoint / "plan.sha256.json", checkpoint / "image.json",
                  checkpoint / "sim/vcs_source_manifest.json", checkpoint / "sim/simulator.conf",
                  HERE / "run_dve_coverage.sh", HERE / "export_dve_coverage.tcl"])
    files.update(previous["files"])
    files.update(image)
    files.update(oracles)
    originals = {row["name"]: row for row in previous["cases"]}
    reused = []
    for case in cases:
        if case["name"] in originals:
            item = inherited(case, originals[case["name"]], checkpoint, str(checkpoint / "sim/simv"))
            save(output / "outcomes" / (case["name"] + ".json"), item)
            reused.append(case["name"])
            files.update(item["files"])
            files.update(item["vdb_files"])
            files.update(pins([output / "outcomes" / (case["name"] + ".json")]))
    if len(cases) != 234 or len(reused) != 5:
        raise ValueError("expected 234 total and 5 reused (four overlaps plus seed509)")
    config = output / "inputs/coverage-wrapper.json"
    save(config, {"simv": str(checkpoint / "sim/simv"), "image": image, "results": str(output / "results")})
    wrapper = output / "inputs/coverage_simv"
    wrapper.write_text("#!/bin/sh\nexec " + shlex.join([sys.executable, str(SCRIPT), "--coverage-exec", str(config)]) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + ".daidir").symlink_to(checkpoint / "sim/simv.daidir", target_is_directory=True)
    shutil.copyfile(checkpoint / "sim/simulator.conf", output / "inputs/simulator.conf")
    files.update(pins([config, wrapper, output / "inputs/simulator.conf"]))
    plan = {"cases": cases, "files": files, "reused": reused, "checkpoint": str(checkpoint),
            "source_selection": selected, "simv": str(checkpoint / "sim/simv"), "image": image, "oracles": oracles,
            "wrapper": str(wrapper), "wrapper_image": simulation_image(wrapper), "workers_max": 8,
            "dve_timeout_s": 600, "dve_outer_timeout_s": 720,
            "design_vdb": str(checkpoint / "sim/simv.vdb"),
            "design_files": base.inventory(checkpoint / "sim/simv.vdb")}
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pins([output / "plan.json"]))
    frozen(output, all_cases=True)
    state = {"status": "PREPARED", "phase": "VCS coverage batch", "total": 234, "workers": 8,
             "source_selection": selected, "cases": {}, "simulations_started": False}
    save(output / "checkpoint.json", state)
    for name in reused:
        publish(output, read(output / "outcomes" / (name + ".json")))


def frozen(output, case=None, all_cases=False):
    check(read(output / "plan.sha256.json"))
    plan = read(output / "plan.json")
    if all_cases:
        check(plan["files"])
    else:
        # The immutable image is the executed design. Recheck all source/build
        # provenance at the batch boundaries, not once per parallel case.
        critical = {path: digest for path, digest in plan["files"].items()
                    if Path(path).suffix in (".py", ".sh", ".tcl")}
        critical.update(plan["image"])
        critical.update(plan["wrapper_image"])
        critical.update(plan["oracles"])
        for path in (output / "inputs/coverage-wrapper.json", output / "inputs/simulator.conf"):
            critical[str(path)] = plan["files"][str(path)]
        check(critical)
    for row in plan["cases"] if all_cases else [case] if case else []:
        check(row["source_files"])
    return plan


def publish(output, outcome):
    with (output / "checkpoint.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(output / "checkpoint.json")
        state["cases"][outcome["name"]] = {k: outcome.get(k) for k in
              ("status", "reused", "vdb_valid", "passed_only", "reason")}
        counts = Counter(row["status"] for row in state["cases"].values())
        state.update(completed=len(state["cases"]), passed=counts["PASS"], counts=dict(counts),
                     valid_vdb=sum(bool(c["vdb_valid"]) for c in state["cases"].values()),
                     reused=sum(bool(c["reused"]) for c in state["cases"].values()))
        save(output / "checkpoint.json", state)


def commands(output, case, plan):
    target = output / "results" / case["name"]
    if case["kind"] == "directed":
        command = [sys.executable, str(SCRIPT), "--output", str(output), "--directed", case["name"]]
    else:
        command = [sys.executable, str(ROOT / "verification/verify.py"), "replay-failed-rvv",
                   "--summary", case["replay_summary"], "--include-passed", "--case", case["source_name"],
                   "--simv", plan["wrapper"], "--spike", case["spike"], "--spike-isa", base.ISA,
                   "--jobs", "1", "--timeout", str(case["timeout_s"]), "--spike-timeout",
                   str(case["spike_timeout_s"]), "--watchdog-cycles", str(case["watchdog_cycles"]),
                   "--output", str(target)]
    audit = [sys.executable, str(ROOT / "verification/verify.py"), "audit", "--run", str(target),
             "--require-trace", "--output", str(target / "independent_audit.json")]
    if case["kind"] != "directed":
        audit += ["--require-vector", "--require-full-match"]
    return command, audit


def directed(output, name):
    plan = frozen(output)
    case = next(c for c in plan["cases"] if c["name"] == name and c["kind"] == "directed")
    check(case["source_files"])
    test = TestCase(**dict(case["directed_test"], binary=Path(case["frozen_elf"])))
    options = RunOptions(repo_root=ROOT, output_root=output / "results" / name, config="default",
                         jobs=1, seed=1, dry_run=False, build_only=False, skip_build=True,
                         simv=Path(plan["wrapper"]), commit_trace=True, timeout_s=case["timeout_s"])
    results = RegressionRunner(options, [test], sys.argv).run()
    return 0 if len(results) == 1 and results[0].status == "PASS" else 1


def invoke(command, log, timeout, env=None):
    save(log.with_suffix(".command.json"), {"command": command, "timeout_s": timeout,
                                           "env_overrides": env or {}})
    with log.open("w") as stream:
        return subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                              timeout=timeout, check=False, env=dict(os.environ, **(env or {}))).returncode


def worker(output, name):
    outcome_path = output / "outcomes" / (name + ".json")
    if outcome_path.exists():
        return 1
    try:
        plan = frozen(output)
        case = next(c for c in plan["cases"] if c["name"] == name)
        check(case["source_files"])
        command, audit = commands(output, case, plan)
        target = output / "results" / name
        rc = invoke(command, output / "logs" / (name + ".log"), case["timeout_s"] + 600)
        check_environment_logs(target)
        rows = read(target / "summary.json")
        if len(rows) != 1:
            raise RuntimeError("expected one replay result")
        row = rows[0]
        verdict = classify(row, rc)
        artifact = Path(row["artifact_dir"]).resolve()
        if not artifact.is_relative_to(target):
            raise RuntimeError("replay artifact outside its assigned directory")
        metadata = read(artifact / "inputs.json")
        if metadata["simv"]["image_sha256"] != plan["wrapper_image"]:
            raise RuntimeError("wrong replay image")
        check({str(artifact / "input.elf"): case["elf_sha256"]})
        if metadata["binary"]["sha256"] != case["elf_sha256"]:
            raise RuntimeError("wrong replay ELF metadata")
        if case["kind"] != "directed" and metadata["spike"]["sha256"] != case["spike_sha256"]:
            raise RuntimeError("wrong Spike oracle")
        evidence = [target / "summary.json", artifact / "inputs.json", artifact / "input.elf"]
        if verdict == "PASS":
            if invoke(audit, output / "logs" / (name + "-audit.log"), 300) != 0:
                raise RuntimeError("independent audit failed after claimed PASS")
            audit_path = target / "independent_audit.json"
            audit_ok(read(audit_path), case, artifact)
            evidence.append(audit_path)
        work = artifact / "work" if case["kind"] == "directed" else artifact
        vdb = work / "code.vdb"
        rejection, vdb_files = None, {}
        try:
            vdb_files = valid_vdb(vdb, case["coverage_test"], plan["simv"])
        except (OSError, ValueError, ET.ParseError, EOFError, IndexError) as error:
            rejection = f"{type(error).__name__}: {error}"
            if verdict == "PASS":
                raise RuntimeError(f"passing replay lacks complete VDB: {rejection}") from error
        evidence.extend(p for p in artifact.rglob("*") if p.is_file() and
                        p.suffix in (".json", ".csv", ".log"))
        frozen(output, case)
        outcome = {"name": name, "kind": case["kind"], "status": verdict, "reused": False,
                   "elf_sha256": case["elf_sha256"], "source_audit": case["source_audit"],
                   "oracle": case["oracle"], "returncode": rc, "files": pins(evidence),
                   "vdb": str(vdb), "vdb_valid": bool(vdb_files), "vdb_files": vdb_files,
                   "coverage_test": case["coverage_test"], "vdb_rejection": rejection,
                   "passed_only": verdict == "PASS" and bool(vdb_files)}
        save(outcome_path, outcome)
        publish(output, outcome)
        return 0
    except Exception as error:
        outcome = {"name": name, "status": "INFRASTRUCTURE_ERROR", "reason": str(error)}
        save(outcome_path, outcome)
        publish(output, outcome)
        return 1


def schedule(output, names, jobs):
    """Observe ALL completions before every dispatch; no hidden pending futures."""
    records = [{"name": n, "status": "PENDING"} for n in names]
    active, index, cancelled = {}, 0, []
    previous = {sig: signal.signal(sig, lambda signum, frame: cancelled.append(signum))
                for sig in (signal.SIGTERM, signal.SIGINT)}
    def publish_scheduler():
        save(output / "scheduler/status.json", {"jobs": jobs, "results": records})
    try:
        while active or index < len(records):
            done = [(i, child.poll()) for i, child in active.items()]
            failure = None
            changed = False
            for i, rc in done:
                if rc is not None:
                    changed = True
                    records[i].update(status="PASS" if rc == 0 else "FAIL", returncode=rc)
                    if rc and failure is None:
                        failure = i
            if failure is not None or cancelled:
                save(output / "scheduler/STOP.json", {"failure": records[failure] if failure is not None else None,
                                                       "signals": cancelled})
                raise RuntimeError("infrastructure failure or service cancellation; queue stopped")
            for i, rc in done:
                if rc is not None:
                    del active[i]
            if index < len(records) and len(active) < jobs:
                record = records[index]
                log = output / "scheduler/logs" / f"{index:04d}.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("w") as stream:
                    active[index] = subprocess.Popen([sys.executable, str(SCRIPT), "--output", str(output),
                         "--worker", record["name"]], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)
                record.update(status="RUNNING", pid=active[index].pid, stdout=str(log))
                index += 1
                publish_scheduler()
                continue
            if changed:
                publish_scheduler()
            if active:
                time.sleep(0.1)
    finally:
        if active:
            cleanup = stop_groups(active)
            for i in active:
                if records[i]["status"] == "RUNNING":
                    records[i]["status"] = "CANCELLED"
            for row in records[index:]:
                row["status"] = "CANCELLED"
            save(output / "scheduler/cleanup.json", cleanup)
            publish_scheduler()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def summarize(output, plan):
    outcomes = [read(output / "outcomes" / (c["name"] + ".json")) for c in plan["cases"]]
    for item in outcomes:
        check(item["files"])
        if item["vdb_valid"] and base.inventory(Path(item["vdb"])) != item["vdb_files"]:
            raise RuntimeError("coverage changed after worker completion")
    design = Path(plan["design_vdb"])
    base.pure_design(design)
    for label, selected in (("passed-only", [x for x in outcomes if x["passed_only"]]),
                             ("exploration", [x for x in outcomes if x["vdb_valid"]])):
        target = output / label
        database_pins = {str(design): plan["design_files"], **{x["vdb"]: x["vdb_files"] for x in selected}}
        if any(base.inventory(Path(path)) != digest for path, digest in database_pins.items()):
            raise RuntimeError("VDB drift before DVE")
        save(output / f"{label}.inputs.before.json", database_pins)
        if selected:
            command = ["bash", str(HERE / "run_dve_coverage.sh"), str(target), str(design),
                       *[x["vdb"] for x in selected]]
            if invoke(command, output / "logs" / f"{label}-dve.log", 720,
                      {"DVE_COVERAGE_TIMEOUT": "600"}) != 0:
                raise RuntimeError(f"DVE {label} export failed")
            actual = (target / "selected_tests.txt").read_text().splitlines()
            expected = [str(Path(x["vdb"]).with_suffix("") / x["coverage_test"]) for x in selected]
            if actual != expected:
                raise RuntimeError("DVE selected unexpected tests")
        after = {path: base.inventory(Path(path)) for path in database_pins}
        save(output / f"{label}.inputs.after.json", after)
        if after != database_pins:
            raise RuntimeError("DVE modified input VDBs")
        save(target / "collection.json", {"status": "COLLECTED" if selected else "EMPTY", "samples": selected,
             "purpose": "INDEPENDENT_PASS_ONLY" if label == "passed-only" else "EXPLORATION_NOT_CORRECTNESS_SIGNOFF",
             "source_selection": plan["source_selection"], "image": plan["image"], "metrics_requested": base.METRICS,
             "unavailable_metrics": "DVE NA remains unavailable; no assertion coverage claim",
             "excluded_incomplete_vdb": [x["name"] for x in outcomes if not x["vdb_valid"]],
             "exporter": pins([HERE / "run_dve_coverage.sh", HERE / "export_dve_coverage.tcl"]),
             "reports": pins([target / "summary.csv", target / "selected_tests.txt"]) if selected else {}})
    return outcomes


def execute(output, jobs):
    try:
        base.check_service()
        state = read(output / "checkpoint.json")
        if state["status"] != "PREPARED" or not 1 <= jobs <= 8:
            raise RuntimeError("requires fresh PREPARED batch and 1..8 workers")
        with (ROOT / "verification/out/.batch-vcs.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            plan = frozen(output, all_cases=True)
            base.sources(Path(plan["checkpoint"]) / "sim/vcs_source_manifest.json")
            state.update(status="RUNNING", phase="coverage replay", simulations_started=True, workers=jobs)
            save(output / "checkpoint.json", state)
            names = [c["name"] for c in plan["cases"] if c["name"] not in plan["reused"]]
            schedule(output, names, jobs)
            frozen(output, all_cases=True)
            state = read(output / "checkpoint.json")
            if state["completed"] != state["total"]:
                raise RuntimeError("incomplete batch outcomes")
            state.update(phase="DVE")
            save(output / "checkpoint.json", state)
            outcomes = summarize(output, plan)
            frozen(output, all_cases=True)
            base.sources(Path(plan["checkpoint"]) / "sim/vcs_source_manifest.json")
            state.update(status="PASS" if all(x["status"] == "PASS" for x in outcomes) else "COMPLETE_WITH_FAILURES",
                         phase="complete", passed_only=sum(x["passed_only"] for x in outcomes))
            save(output / "checkpoint.json", state)
        return 0
    except Exception as error:
        state = read(output / "checkpoint.json")
        state.update(status="STOPPED", reason=str(error))
        save(output / "checkpoint.json", state)
        return 1


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--coverage-exec":
        argv = adapter_command(read(sys.argv[2]), sys.argv[3:], Path.cwd().resolve())
        with Path("coverage.command.json").open("x") as stream:
            json.dump({"command": argv, "cwd": str(Path.cwd())}, stream, indent=2)
        os.execv(argv[0], argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch", type=Path, default=base.BATCH)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=8)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--worker", help=argparse.SUPPRESS)
    modes.add_argument("--directed", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = base.checked_output(args.output)
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.worker:
        return worker(output, args.worker)
    if args.directed:
        return directed(output, args.directed)
    if args.execute:
        return execute(output, args.jobs)
    prepare(output, args.batch.resolve(strict=True), args.checkpoint.resolve(strict=True))
    print(f"PREPARED, NOT LAUNCHED: {output}; 234 total, 5 inherited, 229 new, max 8 workers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
