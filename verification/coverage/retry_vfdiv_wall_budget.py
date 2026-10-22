#!/usr/bin/env python3
"""Explicit same-image retry of the incomplete 600-second VFDiv gate.

Preserve the original campaign, timeout evidence, RTL, ELF and checkers.
Only this case's host wall budget changes; no simulated watchdog is changed.
"""
import argparse
import copy
from pathlib import Path

import run_full_recollection_20260928 as full


def select(plan):
    matches = [c for c in plan["cases"] if c.get("coverage_test") == "vfdiv_mask_flags"]
    full.require(len(matches) == 1, "expected exactly one VFDiv case")
    case = copy.deepcopy(matches[0])
    full.require(case["kind"] == "uvm" and not case.get("require_axi", True),
                 "unexpected checker contract")
    full.require(case["timeout_s"] == 600, "unexpected original wall budget")
    case["timeout_s"] = 1200
    return case


def run(source, output):
    source, output = source.resolve(), output.resolve()
    full.require(output.is_relative_to(full.ROOT / "verification/out"), "output outside evidence tree")
    full.require(not output.exists(), "output exists; never overwrite evidence")
    original_frozen = full.frozen
    plan = original_frozen(source, all_cases=True)
    case = select(plan)
    old = source / "outcomes" / (case["name"] + ".json")
    full.require(full.read(old)["status"] == "RTL_TIMEOUT", "original case was not a timeout")
    for name in ("logs", "outcomes", "results"):
        (output / name).mkdir(parents=True, exist_ok=True)
    effective = copy.deepcopy(plan)
    effective["cases"] = [case]
    full.save(output / "effective-plan.json", effective)
    full.save(output / "retry-policy.json", {
        "source_campaign": str(source), "original_outcome": str(old),
        "change": "host wall timeout 600 -> 1200 seconds for vfdiv_mask_flags only",
        "rtl_changed": False, "elf_changed": False, "checker_changed": False,
        "remaining_campaign_auto_started": False,
    })
    guard = full.pins([Path(__file__).resolve(), old, source / "gate.json",
                      output / "effective-plan.json", output / "retry-policy.json"])
    full.save(output / "retry.sha256.json", guard)

    def verify(_output, selected=None, all_cases=False):
        full.check(guard)
        original_frozen(source, selected, all_cases)
        return copy.deepcopy(effective)

    full.frozen = verify
    full.save(output / "checkpoint.json", {"status": "RUNNING", "total": 1,
              "workers": 1, "completed": 0, "cases": {}, "source_campaign": str(source)})
    try:
        rc = full.worker(output, case["name"])
        verify(output, all_cases=True)
        outcome = full.read(output / "outcomes" / (case["name"] + ".json"))
        state = full.read(output / "checkpoint.json")
        state["status"] = outcome["status"]
        full.save(output / "checkpoint.json", state)
        return 0 if rc == 0 and outcome["status"] == "PASS" and outcome["passed_only"] else 1
    except Exception as error:
        state = full.read(output / "checkpoint.json")
        state.update(status="INFRASTRUCTURE_ERROR", reason=str(error))
        full.save(output / "checkpoint.json", state)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.source, args.output))
