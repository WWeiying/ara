#!/usr/bin/env python3
"""Extend the original-image PASS-only campaign with the checked Gap29 tests."""

import argparse
import json
import os
from pathlib import Path
import sys

import queue_other_gap_exploration as previous
from ara_verify.model import TestCase


batch, gap, memory = previous.batch, previous.gap, previous.memory
ROOT = previous.ROOT
SCRIPT = Path(__file__).resolve()
BASELINE = ROOT / "verification/out/vcs-original473-gap28-20260928-01"
SELECTION = ROOT / "verification/tests/next_gap29_selection.json"
READY = ROOT / "verification/tests/next_gap29_ready.json"
read, save, check, pins = batch.read, batch.save, batch.check, batch.pins
require = previous.require


def select_tests(catalog, old, names):
    expected = read(SELECTION)["tests"]
    require(names == expected and len(names) == 7, "Gap29 selection changed")
    rvv = gap.select_tests(catalog, old, names[:6])
    name = names[6]
    require(name == "app:akv_d96_gap29", "unexpected application test")
    binary = ROOT / "apps/bin/akv_d96_gap29"
    digest = batch.sha256(binary)
    require(digest not in {case["elf_sha256"] for case in old["cases"]} and
            digest not in {item[2] for item in rvv}, "duplicate application ELF")
    test = TestCase(name=name, kind="app", build_target="bin/akv_d96_gap29",
                    binary=binary, testcase="akv_d96_gap29", timeout_s=300)
    return rvv + [(name, test, digest)]


def prepare(output, selection, ready):
    state = read(BASELINE / "checkpoint.json")
    require(state["status"] == "COMPLETE_WITH_FAILURES" and state["total"] == 521 and
            state["completed"] == 521 and state["passed"] == 503,
            "expected completed 503-PASS predecessor")
    proof = read(ready)
    require(proof["status"] == "READY" and proof["tests"] == read(selection)["tests"] and
            Path(proof["previous"]) == BASELINE, "Gap29 readiness mismatch")
    check(proof["files"])
    require(str(selection) in proof["files"], "selection is not pinned")
    gap.extension.select_tests = select_tests
    gap.prepare(output, BASELINE, selection)
    plan = read(output / "plan.json")
    plan["files"].update(proof["files"])
    plan["files"].update(pins([SCRIPT, ready, Path(previous.__file__)]))
    plan["files"].update(pins(output / "outcomes" / (name + ".json")
                              for name in plan["reused"]))
    plan.update(evidence_version="ORIGINAL_PRE_SEGMENT_VL0_REPAIR_IMAGE",
                current_rtl_claim=False, repaired_vdb_reuse=False,
                baseline_passed=503, archived_sources=str(previous.QUEUE / "original-sources/archive.json"))
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pins([output / "plan.json"]))
    previous.frozen(output, all_cases=True)


def summarize(output, plan):
    outcomes = memory.summarize(output, plan)
    path = output / "collection.json"
    result = read(path)
    result.update(evidence_version="ORIGINAL_PRE_SEGMENT_VL0_REPAIR_IMAGE",
                  current_rtl_claim=False, repaired_vdb_reuse=False,
                  baseline_passed=503, added_passed=result["passed"] - 503)
    save(path, result)
    return outcomes


def main():
    batch.SCRIPT = gap.extension.SCRIPT = SCRIPT
    batch.frozen = previous.frozen
    batch.summarize = summarize
    batch.schedule = memory.original_schedule
    batch.base.sources = previous.original_sources
    previous.BASELINE = BASELINE
    previous.prepare = prepare
    if len(sys.argv) > 2 and sys.argv[1] == "--coverage-exec":
        argv = batch.adapter_command(read(sys.argv[2]), sys.argv[3:], Path.cwd().resolve())
        with Path("coverage.command.json").open("x") as stream:
            json.dump({"command": argv, "cwd": str(Path.cwd())}, stream)
        os.execv(argv[0], argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=7)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--worker")
    modes.add_argument("--directed")
    args = parser.parse_args()
    output = batch.base.checked_output(args.output)
    previous.QUEUE = output.with_name(output.name + "-queue")
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.worker:
        return batch.worker(output, args.worker)
    if args.directed:
        return batch.directed(output, args.directed)
    return previous.queue(output, SELECTION, READY, previous.PREDECESSOR_UNIT)


if __name__ == "__main__":
    sys.exit(main())
