#!/usr/bin/env python3
"""Resume exactly 540 pending cases after the consolidated 60-case gate.

Use the frozen full-recollection workers and PASS-only DVE exporter. The only
VDB relocation accepted is the explicitly audited VFDiv retry. Never rerun an
existing case, rebuild RTL, or mix simulator images.
"""
import argparse
import fcntl
import os
from pathlib import Path
import shlex
import sys

import run_full_recollection_20260928 as full
import consolidate_vfdiv_gate as consolidation

SCRIPT = Path(__file__).resolve()
SERVICE = "ara-full-recollection-resume-20260929-01.service"
original_frozen = full.frozen
original_vdb = full.batch.valid_vdb


def pending(plan, gate):
    full.require(gate["status"] == "PASS" and not gate.get("failed"), "gate not passed")
    names = [c["name"] for c in plan["cases"]]
    done = set(gate["cases"])
    full.require(len(names) == len(set(names)) == 600 and len(done) == 60 and done <= set(names),
                 "unexpected campaign membership")
    result = [name for name in names if name not in done]
    full.require(len(result) == 540, "expected 540 pending cases")
    return result


def frozen(output, case=None, all_cases=False):
    full.check(full.read(output / "resume.sha256.json"))
    return original_frozen(output, case, all_cases)


def relocation_validator(output):
    admission = full.read(output / "gate-consolidation.json")
    full.require(len(admission["wall_budget_override"]) == 1, "ambiguous retry")
    name = next(iter(admission["wall_budget_override"]))
    outcome = full.read(output / "outcomes" / (name + ".json"))
    approved = Path(outcome["vdb"])
    recorded = Path(outcome["relocation"]["recorded_result_path"]) / "code.vdb"

    def validate(vdb, test, image):
        if Path(vdb) != approved:
            return original_vdb(vdb, test, image)
        full.require(test == outcome["coverage_test"] and recorded.resolve(strict=True) == approved.resolve(strict=True),
                     "approved relocation changed")
        original_vdb(recorded, test, image)
        hashes = full.base.inventory(approved)
        full.require(hashes == outcome["vdb_files"], "relocated coverage changed")
        return hashes

    return validate


def prepare(output):
    full.require(not (output / "resume.json").exists(), "resume already prepared")
    plan, gate, _ = consolidation.verify_gate(output)
    full.check(gate["outcome_files"])
    state = full.read(output / "checkpoint.json")
    full.require(state["status"] == "READY" and state["completed"] == state["passed"] == 60,
                 "requires consolidated READY state")
    names = pending(plan, gate)
    full.require(not gate["full_dispatch_started"], "remaining queue already dispatched")
    full.require(all(not (output / "outcomes" / (n + ".json")).exists()
                     and not (output / "results" / n).exists() for n in names), "pending evidence already exists")
    full.save(output / "resume.json", {"service": SERVICE, "workers": 8, "cases": names,
        "gate_cases": gate["cases"], "original_plan_unchanged": True,
        "coverage": "all 600 outcomes; complete independently passed VDBs only"})
    hashes = full.pins([SCRIPT, Path(consolidation.__file__), output / "resume.json",
                        output / "gate-consolidation.json"])
    hashes.update(gate["outcome_files"])
    full.save(output / "resume.sha256.json", hashes)
    print("READY: 60 validated gate cases retained; 540 pending, 8 workers, automatic DVE")


def execute(output):
    full.base.check_service()
    try:
        with (full.ROOT / "verification/out/.batch-vcs.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            plan = frozen(output, all_cases=True)
            resume = full.read(output / "resume.json")
            state = full.read(output / "checkpoint.json")
            gate = full.read(output / "gate.json")
            full.require(state["status"] == "READY" and not gate["full_dispatch_started"], "already started")
            full.require(resume["cases"] == pending(plan, gate), "pending selection changed")
            full.require(not (output / "gate-scheduler").exists(), "scheduler already archived")
            (output / "scheduler").rename(output / "gate-scheduler")
            gate.update(full_dispatch_started=True, remaining=540, resume_service=SERVICE)
            full.save(output / "gate.json", gate)
            state.update(status="RUNNING", phase="remaining 540 coverage replay", workers=8,
                         simulations_started=True, reason=None)
            full.save(output / "checkpoint.json", state)
            full.original_schedule(output, resume["cases"], 8)
            frozen(output, all_cases=True)
            state = full.read(output / "checkpoint.json")
            full.require(state["completed"] == state["total"] == 600, "incomplete outcomes")
            state.update(phase="DVE: all independently passed cases", remaining=0)
            full.save(output / "checkpoint.json", state)
            outcomes = full.summarize(output, plan)
            frozen(output, all_cases=True)
            state.update(status="PASS" if all(x["status"] == "PASS" for x in outcomes) else "COMPLETE_WITH_FAILURES",
                         phase="complete", passed_only=sum(x["passed_only"] for x in outcomes))
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
                 "registered resume service required")
    frozen(output)
    full.batch.SCRIPT = SCRIPT
    full.frozen = full.batch.frozen = frozen
    full.batch.commands = full.commands
    full.batch.valid_vdb = relocation_validator(output)
    if args.worker:
        full.require(args.worker in full.read(output / "resume.json")["cases"], "cannot rerun a gate case")
        return full.worker(output, args.worker)
    if args.directed:
        full.require(args.directed in full.read(output / "resume.json")["cases"], "cannot rerun a gate case")
        return full.batch.directed(output, args.directed)
    return execute(output)


if __name__ == "__main__":
    raise SystemExit(main())
