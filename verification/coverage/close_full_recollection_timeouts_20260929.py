#!/usr/bin/env python3
"""Close the 14 wall-timeouts in the frozen 600-case VCS collection."""
import argparse
import copy
import fcntl
import os
from pathlib import Path
import shutil
import sys

import run_full_recollection_20260928 as full
import resume_full_recollection_20260929 as resume


SCRIPT = Path(__file__).resolve()
SERVICE = "ara-full-recollection-timeout-closure-20260929-01.service"
OLD_BUDGET = 300
NEW_BUDGET = 1200


def selected(output):
    plan = resume.frozen(output, all_cases=True)
    state = full.read(output / "checkpoint.json")
    full.require(state["status"] == "COMPLETE_WITH_FAILURES" and
                 state["total"] == state["completed"] == 600 and state["passed"] == 586,
                 "requires completed 586/600 collection")
    names = [c["name"] for c in plan["cases"] if state["cases"][c["name"]]["status"] == "TIMEOUT"]
    full.require(len(names) == 14 and set(state["cases"]) == {c["name"] for c in plan["cases"]},
                 "expected exactly 14 timeouts, with no other missing or failed cases")
    for name in names:
        case = next(c for c in plan["cases"] if c["name"] == name)
        outcome = full.read(output / "outcomes" / (name + ".json"))
        rows = full.read(output / "results" / name / "summary.json")
        full.require(case["kind"] == "directed" and case["timeout_s"] == OLD_BUDGET and
                     outcome["status"] == rows[0]["status"] == "TIMEOUT" and
                     outcome["elf_sha256"] == case["elf_sha256"] and
                     "timeout after 300s" in rows[0]["reason"],
                     f"timeout evidence differs: {name}")
    return plan, names


def frozen(output, case=None, all_cases=False):
    plan = resume.frozen(output, case, all_cases)
    policy = full.read(output / "timeout-closure.json")
    effective = copy.deepcopy(plan)
    for row in effective["cases"]:
        if row["name"] in policy["cases"]:
            full.require(row["timeout_s"] == OLD_BUDGET, "original wall budget drift")
            row["timeout_s"] = NEW_BUDGET
    return effective


def prepare(output):
    full.require(not (output / "timeout-closure.json").exists(), "closure already prepared")
    plan, names = selected(output)
    full.require(not (output / "attempt-history/timeout300-20260929").exists(),
                 "attempt archive already exists")
    full.require(not (output / "retry-scheduler").exists(), "retry scheduler already exists")
    full.require(all((output / "results" / n).is_dir() for n in names), "missing old result")
    full.require((output / "dve/summary.csv").is_file(), "missing old DVE report")
    full.save(output / "timeout-closure.json", {
        "service": SERVICE, "cases": names, "workers": 8,
        "original_wall_s": OLD_BUDGET, "retry_wall_s": NEW_BUDGET,
        "plan_sha256": full.pins([output / "plan.json"]),
        "image": plan["image"], "policy": "same RTL/image/ELF/checkers; host wall budget only",
    })
    print(f"READY: {len(names)} directed wall-timeouts; 586 PASS results retained")


def archive(output, names):
    history = output / "attempt-history/timeout300-20260929"
    history.mkdir(parents=True, exist_ok=False)
    for dirname in ("results", "outcomes", "logs", "metadata"):
        (history / dirname).mkdir()
    for name in names:
        (output / "results" / name).rename(history / "results" / name)
        (output / "outcomes" / (name + ".json")).rename(history / "outcomes" / (name + ".json"))
        for path in (output / "logs").glob(name + "*"):
            path.rename(history / "logs" / path.name)
    for name in ("all-outcomes.json", "collection.json", "dve-inputs.before.json",
                 "dve-inputs.after.json", "dve-inputs.txt", "checkpoint.json"):
        shutil.copy2(output / name, history / "metadata" / name)
    (output / "dve").rename(history / "dve")
    (output / "scheduler").rename(history / "scheduler")


def execute(output):
    full.base.check_service()
    with (full.ROOT / "verification/out/.batch-vcs.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan, names = selected(output)
        policy = full.read(output / "timeout-closure.json")
        full.require(policy["service"] == SERVICE and policy["cases"] == names and
                     policy["plan_sha256"] == full.pins([output / "plan.json"]) and
                     policy["image"] == plan["image"], "closure policy drift")
        archive(output, names)
        state = full.read(output / "checkpoint.json")
        state.update(status="RUNNING", phase="14 directed wall-timeout retries", reason=None,
                     workers=8, timeout_closure=policy)
        full.save(output / "checkpoint.json", state)
        try:
            full.original_schedule(output, names, 8)
            state = full.read(output / "checkpoint.json")
            full.require(state["completed"] == 600, "incomplete closure")
            state.update(phase="DVE: all independently passed cases")
            full.save(output / "checkpoint.json", state)
            outcomes = full.summarize(output, plan)
            state = full.read(output / "checkpoint.json")
            state.update(status="PASS" if all(x["status"] == "PASS" for x in outcomes)
                         else "COMPLETE_WITH_FAILURES", phase="complete", reason=None)
            full.save(output / "checkpoint.json", state)
            return 0 if state["status"] == "PASS" else 1
        except Exception as error:
            state = full.read(output / "checkpoint.json")
            state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}")
            full.save(output / "checkpoint.json", state)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--worker")
    mode.add_argument("--directed")
    args = parser.parse_args()
    output = full.base.checked_output(args.output)
    os.environ["PYTHONPATH"] = str(full.ROOT / "verification")
    for key in list(os.environ):
        if key.startswith(("ARA_UVM_", "ARA_CONTRACT_", "ARA_VCS_")):
            del os.environ[key]
    if args.prepare:
        prepare(output)
        return 0
    full.require(os.environ.get("ARA_CHECKPOINT_UNIT") == SERVICE and os.environ.get("INVOCATION_ID"),
                 "registered closure service required")
    policy = full.read(output / "timeout-closure.json")
    full.batch.SCRIPT = SCRIPT
    full.frozen = full.batch.frozen = frozen
    full.batch.commands = full.commands
    full.batch.valid_vdb = resume.relocation_validator(output)
    if args.worker:
        full.require(args.worker in policy["cases"], "not a timeout closure case")
        return full.worker(output, args.worker)
    if args.directed:
        full.require(args.directed in policy["cases"], "not a timeout closure case")
        return full.batch.directed(output, args.directed)
    return execute(output)


if __name__ == "__main__":
    raise SystemExit(main())
