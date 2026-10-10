#!/usr/bin/env python3
"""Run both original AKV programs with budgets derived from passing shards."""
import argparse
import copy
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import run_full_recollection_20260928 as full
import resume_full_recollection_20260929 as resume


SCRIPT = Path(__file__).resolve()
SERVICE = "ara-full-recollection-akv-closure-20260929-01.service"
CONFIG = {
    "app:akv_portability_smoke": ("app:coverage_akv_portability_", 8, 2400),
    "app:akv_d256_reuse_smoke": ("app:coverage_akv_d256_", 14, 7200),
}
HISTORY = "attempt-history/akv-wall1200-20260929"
POLICY = "akv-combined-closure.json"
GUARD = "akv-combined-closure.sha256.json"


def final_cycle(trace):
    line = subprocess.check_output(["tail", "-n", "1", str(trace)], text=True)
    match = re.match(r"\s*\d+ns\s+(\d+)\s", line)
    full.require(match is not None, f"missing final cycle: {trace}")
    return int(match.group(1))


def trace_path(output, name):
    paths = list((output / "results" / name).glob("tests/*/work/trace_hart_0.log"))
    full.require(len(paths) == 1, f"ambiguous scalar trace: {name}")
    return paths[0]


def prepare(output):
    full.require(not (output / POLICY).exists(), "AKV closure already prepared")
    full.require(not (output / HISTORY).exists(), "AKV archive already exists")
    plan = resume.frozen(output, all_cases=True)
    state = full.read(output / "checkpoint.json")
    collection = full.read(output / "collection.json")
    full.require(state["status"] == collection["status"] == "COMPLETE_WITH_FAILURES"
                 and state["completed"] == 600 and state["passed"] == collection["passed"] == 598
                 and state["counts"] == {"PASS": 598, "TIMEOUT": 2},
                 "requires independently collected 598 PASS / 2 TIMEOUT")
    full.check(collection["reports"])
    names, reviews, evidence = [], {}, [SCRIPT]
    for source, (prefix, count, budget) in CONFIG.items():
        matches = [c for c in plan["cases"] if c.get("source_name") == source]
        full.require(len(matches) == 1, f"missing combined case: {source}")
        case = matches[0]
        name = case["name"]
        outcome = output / "outcomes" / (name + ".json")
        rows = full.read(output / "results" / name / "summary.json")
        full.require(full.read(outcome)["status"] == rows[0]["status"] == "TIMEOUT"
                     and rows[0]["reason"] == "timeout after 1200s"
                     and case["kind"] == "directed", "unexpected combined failure")
        evidence.extend((outcome, output / "results" / name / "summary.json",
                         trace_path(output, name)))
        shards = [c for c in plan["cases"] if c.get("source_name", "").startswith(prefix)]
        full.require(len(shards) == count, f"incomplete shard set: {source}")
        shard_review = []
        for shard in shards:
            path = output / "outcomes" / (shard["name"] + ".json")
            item = full.read(path)
            full.require(item["status"] == "PASS" and item["passed_only"] and item["vdb_valid"]
                         and item["elf_sha256"] == shard["elf_sha256"], "unverified shard")
            summary = output / "results" / shard["name"] / "summary.json"
            trace = trace_path(output, shard["name"])
            shard_review.append({"name": shard["name"], "source_name": shard["source_name"],
                                "cycles": final_cycle(trace),
                                "elapsed_s": full.read(summary)[0]["elapsed_s"]})
            evidence.extend((path, summary, trace))
        observed = final_cycle(trace_path(output, name))
        summed = sum(s["cycles"] for s in shard_review)
        projected = 1200 * summed / observed
        full.require(budget >= projected * 1.25, "budget lacks measured workload margin")
        reviews[name] = {"source_name": source, "original_plan_wall_s": case["timeout_s"],
                         "previous_wall_s": 1200, "retry_wall_s": budget,
                         "cycles_at_timeout": observed, "sum_shard_cycles": summed,
                         "estimated_full_wall_s": projected, "shards": shard_review}
        names.append(name)
    full.require(set(names) == {n for n, v in state["cases"].items() if v["status"] != "PASS"},
                 "unexpected unclosed cases")
    full.save(output / POLICY, {"service": SERVICE, "workers": 2, "cases": names,
              "review": reviews, "image": plan["image"],
              "policy": "original full ELF; same frozen image/oracles; host wall budgets only",
              "estimate_note": "sum of independently passed shard cycles includes repeated setup",
              "plan_files": full.pins([output / "plan.json"])})
    evidence.append(output / POLICY)
    full.save(output / GUARD, full.pins(evidence))
    print("READY: both full AKV ELFs; 2 workers; wall budgets 2400s and 7200s")


def frozen(output, case=None, all_cases=False):
    full.check(full.read(output / GUARD))
    plan = copy.deepcopy(resume.frozen(output, case, all_cases))
    review = full.read(output / POLICY)["review"]
    for row in plan["cases"]:
        if row["name"] in review:
            full.require(row["timeout_s"] == review[row["name"]]["original_plan_wall_s"],
                         "original plan budget drift")
            row["timeout_s"] = review[row["name"]]["retry_wall_s"]
    return plan


def execute(output):
    full.base.check_service()
    with (full.ROOT / "verification/out/.batch-vcs.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = frozen(output, all_cases=True)
        policy = full.read(output / POLICY)
        state = full.read(output / "checkpoint.json")
        full.require(state["status"] == "COMPLETE_WITH_FAILURES" and state["passed"] == 598,
                     "collection state drift")
        history = output / HISTORY
        history.mkdir(parents=True, exist_ok=False)
        for folder in ("results", "outcomes", "logs", "metadata"):
            (history / folder).mkdir()
        guard = full.read(output / GUARD)
        for name in policy["cases"]:
            (output / "results" / name).rename(history / "results" / name)
            (output / "outcomes" / (name + ".json")).rename(history / "outcomes" / (name + ".json"))
            for path in (output / "logs").glob(name + "*"):
                path.rename(history / "logs" / path.name)
        for name in ("checkpoint.json", "collection.json", "all-outcomes.json",
                     "dve-inputs.txt", "dve-inputs.before.json", "dve-inputs.after.json"):
            shutil.copy2(output / name, history / "metadata" / name)
        (output / "dve").rename(history / "dve")
        (output / "scheduler").rename(history / "scheduler")
        # Old timeout files move into the archive; guard their archived paths.
        moved_guard = {}
        for path, digest in guard.items():
            old = Path(path)
            replacement = old
            for folder in ("results", "outcomes"):
                base = output / folder
                if old.is_relative_to(base) and old.relative_to(base).parts[0].split(".json")[0] in policy["cases"]:
                    replacement = history / folder / old.relative_to(base)
            moved_guard[str(replacement)] = digest
        full.check(moved_guard)
        full.save(output / GUARD, moved_guard)
        state.update(status="RUNNING", phase="two complete AKV programs", workers=2,
                     akv_closure=policy, reason=None)
        full.save(output / "checkpoint.json", state)
        try:
            full.original_schedule(output, policy["cases"], 2)
            frozen(output, all_cases=True)
            state = full.read(output / "checkpoint.json")
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
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--worker")
    modes.add_argument("--directed")
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
                 "registered AKV closure service required")
    full.batch.SCRIPT = SCRIPT
    full.frozen = full.batch.frozen = frozen
    full.batch.commands = full.commands
    full.batch.valid_vdb = resume.relocation_validator(output)
    name = args.worker or args.directed
    if name:
        full.require(name in full.read(output / POLICY)["cases"], "not an AKV closure case")
        return full.worker(output, name) if args.worker else full.batch.directed(output, name)
    return execute(output)


if __name__ == "__main__":
    raise SystemExit(main())
