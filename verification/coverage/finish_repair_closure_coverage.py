#!/usr/bin/env python3
"""Audit an externally launched vlsseg retry, then merge 20 PASS VDBs plus retry.

Never compiles or launches simulations. Prepare may run while replay is active;
execute waits at most --wait-s (default 2400), audits, then exports full DVE
hierarchy. Run execute as systemd main process with ARA_CHECKPOINT_UNIT and
KillMode=control-group. Original timeout and all original records stay untouched.
"""
import argparse
import csv
import fcntl
from pathlib import Path
import sys
import time

import run_repair_closure_coverage as campaign
from ara_verify.artifacts import check_inputs, simulation_image, sha256

ROOT, HERE = campaign.ROOT, campaign.HERE
SCRIPT = Path(__file__).resolve()
SOURCE = ROOT / "verification/out/repair-closure-coverage-20260927-01"
RETRY = SOURCE / "results/vlsseg_retry1800"
read, save, check, pins = campaign.read, campaign.save, campaign.check, campaign.pins
require, base, coverage = campaign.require, campaign.base, campaign.coverage


def replay_inputs(output, source_plan, runtime):
    data = read(output / "replay-inputs.json")
    spec = source_plan["jobs"]["vlsseg"]
    require(data["source"] == str(SOURCE) and data["result"] == str(RETRY), "unexpected replay directories")
    require(data["timeout_s"] == 1800 and data["original_timeout_s"] == 900,
            "only the authorized 900-to-1800 wall timeout change is allowed")
    require(data["elf"] == spec["elf"] and data["elf_sha256"] == spec["elf_sha256"] and
            data["test"] == spec["test"] == "rvv:vlsseg" and data["coverage_test"] == "vlsseg",
            "retry ELF/test identity differs")
    require(data["wrapper"] == str(SOURCE / "inputs/coverage_simv") and
            data["wrapper_image"] == runtime["wrapper_image"], "retry wrapper image differs")
    check(data["pins"])
    check({data["elf"]: data["elf_sha256"]})
    return data


def previous_passes(source_plan, runtime):
    require(set(source_plan["jobs"]) == campaign.FIRST | campaign.SECOND, "not the exact 21-case repair set")
    require(read(SOURCE / "status.json")["status"] == "FAIL", "expected preserved original failed collection")
    failed = read(SOURCE / "outcomes/vlsseg.json")
    old_rows = read(SOURCE / "results/vlsseg/summary.json")
    require(failed["status"] == "FAIL" and failed["admitted"] is False and len(old_rows) == 1 and
            old_rows[0]["status"] == "TIMEOUT", "original vlsseg timeout provenance missing")
    items, files = [], {}
    for name, spec in source_plan["jobs"].items():
        if name == "vlsseg":
            continue
        path = SOURCE / "outcomes" / (name + ".json")
        item = read(path)
        require(item["name"] == name and item["status"] == "PASS" and item["admitted"] is True and
                item["elf_sha256"] == spec["elf_sha256"] and item["coverage_test"] == spec["coverage_test"],
                "original outcome is not matching PASS")
        check(item["files"])
        result = SOURCE / "results" / name
        if spec["kind"] == "axpy":
            report = read(result / "uvm_result.json")
            require(report == read(result / "independent_uvm_audit.json") and report["status"] == "PASS" and
                    not report["issues"] and report["sim_image_sha256"] == runtime["wrapper_image"] and
                    report["elf_sha256"] == spec["elf_sha256"] and
                    campaign.prior.cycles(result / "work/run.vcs.log") <= 2810, "AXPY audit/gate differs")
            work = result / "work"
        else:
            # This validator is read-only for non-AXPY; never rewrite old cycle_comparison.json.
            campaign.prior.validate_result(SOURCE, name, source_plan)
            row = read(result / "summary.json")[0]
            artifact = Path(row["artifact_dir"])
            coverage.audit_ok(read(result / "independent_audit.json"), dict(spec, source_name=row["name"]), artifact)
            work = artifact / "work" if spec["kind"] == "directed" else artifact
        vdb = Path(item["vdb"]).resolve()
        require(vdb == (work / "code.vdb").resolve() and vdb.is_relative_to(result), "original VDB path differs")
        require(coverage.valid_vdb(vdb, spec["coverage_test"], str(SOURCE / "sim/simv")) == item["vdb_files"],
                "original PASS VDB changed")
        files.update(item["files"])
        files.update(item["vdb_files"])
        files.update(pins([path]))
        items.append(dict(item, reused=True, source_outcome=str(path)))
    require(len(items) == 20, "exactly 20 old PASS cases required")
    return items, files


def prepare(output):
    require(output != SOURCE and not any((output / p).exists() for p in
            ("finish-plan.json", "finish-status.json", "dve", "independent_audit.json")), "finisher output already used")
    source_plan = campaign.frozen(SOURCE, True)
    runtime = read(SOURCE / "runtime.json")
    info = replay_inputs(output, source_plan, runtime)
    items, files = previous_passes(source_plan, runtime)
    base.pure_design(SOURCE / "sim/simv.vdb")
    require(base.inventory(SOURCE / "sim/simv.vdb") == runtime["design_files"], "design VDB drift")
    files.update(runtime["design_files"])
    files.update(pins(campaign.tool_paths() + [SCRIPT, output / "replay-inputs.json", SOURCE / "status.json",
              SOURCE / "outcomes/vlsseg.json", SOURCE / "results/vlsseg/summary.json",
              SOURCE / "plan.json", SOURCE / "plan.sha256.json", SOURCE / "runtime.json", SOURCE / "runtime.sha256.json"]))
    files.update(info["pins"])
    plan = {"schema_version": 1, "source": str(SOURCE), "replay": info, "reused": items, "files": files,
            "image": runtime["image"], "design_files": runtime["design_files"],
            "excluded_timeout_vdb": str(SOURCE / "results/vlsseg/tests/rvv_vlsseg/work/code.vdb"),
            "policy": "AUDIT_THEN_PASS_ONLY_MERGE; NO_SIMULATION_OR_COMPILATION"}
    save(output / "finish-plan.json", plan)
    save(output / "finish-plan.sha256.json", pins([output / "finish-plan.json"]))
    frozen(output)
    save(output / "finish-status.json", {"status": "PREPARED", "reused_pass": 20, "awaiting": "vlsseg",
                                        "coverage_verified": False})


def frozen(output):
    check(read(output / "finish-plan.sha256.json"))
    plan = read(output / "finish-plan.json")
    check(plan["files"])
    source_plan = campaign.frozen(SOURCE, True)
    replay_inputs(output, source_plan, read(SOURCE / "runtime.json"))
    require(simulation_image(SOURCE / "sim/simv") == plan["image"], "real simulator inventory drift")
    return plan


def wait_replay(output, timeout_s):
    require(0 < timeout_s <= 7200, "wait bound must be 1..7200 seconds")
    deadline = time.monotonic() + timeout_s
    while True:
        path = output / "replay-status.json"
        state = read(path) if path.exists() else {"status": "MISSING"}
        if state["status"] == "PASS":
            require(state["result"] == str(RETRY) and state["timeout_s"] == 1800 and
                    state["coverage_verified"] is False and
                    state["summary_sha256"] == sha256(RETRY / "summary.json"), "replay completion identity differs")
            return state
        require(state["status"] in ("MISSING", "RUNNING"), "replay failed; coverage is NOT_PROVEN")
        require(time.monotonic() < deadline, "replay wait exhausted; coverage is NOT_PROVEN")
        time.sleep(min(10, max(0, deadline - time.monotonic())))


def audit_retry(output, plan):
    info = plan["replay"]
    rows = read(RETRY / "summary.json")
    require(len(rows) == 1 and rows[0]["status"] == "PASS" and rows[0]["returncode"] == 0 and
            rows[0]["name"] == info["test"], "retry selfcheck did not complete PASS")
    artifact = Path(rows[0]["artifact_dir"]).resolve()
    require(artifact == (RETRY / "tests/rvv_vlsseg").resolve(), "retry artifact escaped expected directory")
    metadata = read(artifact / "inputs.json")
    require(not check_inputs(metadata, artifact / "input.elf") and
            metadata["binary"]["sha256"] == info["elf_sha256"] and
            metadata["simv"]["path"] == info["wrapper"] and
            metadata["simv"]["image_sha256"] == info["wrapper_image"], "retry executed ELF/wrapper differs")
    work, audit_path = artifact / "work", output / "independent_audit.json"
    vdb = work / "code.vdb"
    evidence = [p for p in RETRY.rglob("*") if p.is_file() and not p.is_relative_to(vdb)]
    before = pins(evidence + [output / "replay-status.json"])
    require(not audit_path.exists(), "audit output exists; no overwrite")
    command = [sys.executable, str(ROOT / "verification/verify.py"), "audit", "--run", str(RETRY),
               "--require-trace", "--output", str(audit_path)]
    require(coverage.invoke(command, output / "finish-logs/audit.log", 300) == 0, "independent trace audit failed")
    coverage.audit_ok(read(audit_path), {"kind": "directed", "source_name": info["test"]}, artifact)
    check(before)
    launch = read(work / "coverage.command.json")
    require(launch["command"][0] == str(SOURCE / "sim/simv") and
            "+ARA_FAULT_VSTART_PROBE" not in launch["command"], "retry real image/probe policy differs")
    hashes = coverage.valid_vdb(vdb, info["coverage_test"], str(SOURCE / "sim/simv"))
    frozen(output)
    item = {"name": "vlsseg", "status": "PASS", "admitted": True, "reused": False,
            "elf_sha256": info["elf_sha256"], "coverage_test": info["coverage_test"],
            "vdb": str(vdb), "vdb_files": hashes, "files": dict(before, **pins([audit_path])),
            "source_timeout_preserved": True, "wall_timeout_s": 1800}
    save(output / "vlsseg-audited.json", item)
    return item


def selected_databases(plan, retry):
    items = [*plan["reused"], retry]
    require(len(items) == 21 and {i["name"] for i in items} == campaign.FIRST | campaign.SECOND,
            "expected exactly 20 original PASS cases plus new vlsseg")
    databases = {str(SOURCE / "sim/simv.vdb"): plan["design_files"]}
    for item in items:
        require(item["status"] == "PASS" and item["admitted"] is True, "non-PASS cannot enter coverage")
        vdb = Path(item["vdb"]).resolve()
        if item["name"] == "vlsseg":
            require(vdb == (RETRY / "tests/rvv_vlsseg/work/code.vdb").resolve(), "old timeout VDB forbidden")
        else:
            require(vdb.is_relative_to(SOURCE / "results" / item["name"]), "unrelated VDB forbidden")
        require(str(vdb) != plan["excluded_timeout_vdb"] and str(vdb) not in databases, "timeout/duplicate VDB forbidden")
        check(item["files"])
        require(coverage.valid_vdb(vdb, item["coverage_test"], str(SOURCE / "sim/simv")) == item["vdb_files"],
                "accepted coverage VDB drift")
        databases[str(vdb)] = item["vdb_files"]
    base.pure_design(SOURCE / "sim/simv.vdb")
    require(all(base.inventory(Path(p)) == digest for p, digest in databases.items()), "coverage database drift")
    return items, databases


def merge(output, plan, retry):
    items, databases = selected_databases(plan, retry)
    save(output / "dve-inputs.before.json", databases)
    target = output / "dve"
    require(coverage.invoke(["bash", str(campaign.DVE / "run_dve_coverage.sh"), str(target), *databases],
                output / "finish-logs/dve.log", 720, {"DVE_COVERAGE_TIMEOUT": "600"}) == 0, "DVE export failed")
    expected = [str(Path(i["vdb"]).with_suffix("") / i["coverage_test"]) for i in items]
    require((target / "selected_tests.txt").read_text().splitlines() == expected, "DVE selection differs")
    with (target / "summary.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(rows and {"Line", "Condition", "FSM", "Toggle", "Branch"} <= rows[0].keys(), "five coverage columns required")
    after = {p: base.inventory(Path(p)) for p in databases}
    save(output / "dve-inputs.after.json", after)
    require(after == databases, "DVE changed input VDBs")
    frozen(output)
    check(retry["files"])
    stack, probes = [], []
    for row in rows:
        stack[int(row["Depth"]):] = [row]
        if "ara_fault_vstart_probe" in row["Name"]:
            probes.append({"path": ".".join(r["Name"].strip() for r in stack), "row": row, "ancestors": stack[:-1]})
    summary = {"status": "PASS", "coverage_verified": True, "passed": 21, "reused_pass": 20,
               "newly_audited": 1, "image": plan["image"], "metrics_requested": base.METRICS,
               "coverage_top": rows[0], "cases": items, "excluded_timeout_vdb": plan["excluded_timeout_vdb"],
               "original_failure_preserved": True, "replacement_cases": 3,
               "scope": "Same frozen coverage image only. Original replacement failures remain unchanged. "
                  "Raw full hierarchy includes TB/UVM/probe; ancestor scores include probe. NA stays unavailable. "
                  "No pure-DUT score or direct comparison/cumulation with old 427 cases.",
               "probe_enabled_cases": sorted(campaign.PROBES), "probe_hierarchy_rows": probes,
               "reports": pins([p for p in target.rglob("*") if p.is_file() and p.suffix in (".csv", ".txt", ".log")])}
    save(output / "collection.json", summary)
    save(output / "summary.json", summary)


def execute(output, wait_s):
    base.check_service()
    state = read(output / "finish-status.json")
    require(state["status"] == "PREPARED", "finisher must be fresh PREPARED; no automatic retries")
    with (ROOT / "verification/out/.batch-vcs.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            plan = frozen(output)
            state.update(status="RUNNING", phase="wait-external-replay")
            save(output / "finish-status.json", state)
            wait_replay(output, wait_s)
            plan = frozen(output)
            (output / "finish-logs").mkdir(exist_ok=True)
            state["phase"] = "independent-audit"
            save(output / "finish-status.json", state)
            retry = audit_retry(output, plan)
            state["phase"] = "DVE"
            save(output / "finish-status.json", state)
            merge(output, plan, retry)
            state.update(status="PASS", phase="complete", coverage_verified=True, passed=21)
            save(output / "finish-status.json", state)
        except Exception as error:
            state.update(status="FAIL", coverage_verified=False, reason=f"{type(error).__name__}: {error}")
            save(output / "finish-status.json", state)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--wait-s", type=int, default=2400)
    args = parser.parse_args()
    output = base.checked_output(args.output)
    if args.prepare_only:
        prepare(output)
    else:
        execute(output, args.wait_s)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"STOP: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
