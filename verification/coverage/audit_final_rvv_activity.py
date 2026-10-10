#!/usr/bin/env python3
"""Audit the final-image RVV retired-activity union without replaying RTL."""

import argparse
import json
from pathlib import Path

from run_verilator_coverage import sha256


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"
RANDOM = OUT / "integrated-random-retired-70case-20260925-01.json"
POLICY = OUT / "integrated-policy-matrix-retired-20260925-01.json"
AXES = ("sew", "lmul", "memory_mode", "policy_pair")


def union_axis(first: dict, second: dict) -> dict:
    if set(first["bins"]) != set(second["bins"]):
        raise ValueError("activity axis targets differ")
    missing = sorted(name for name in first["bins"] if
                     first["bins"][name]["retired_instructions"] +
                     second["bins"][name]["retired_instructions"] == 0)
    return {"target_bins": len(first["bins"]), "observed_bins": len(first["bins"]) - len(missing),
            "unobserved_bins": missing}


def verify_case_hashes(record: dict, objdump: Path) -> None:
    case = Path(record["case"])
    expected = record["sha256"]
    paths = {"elf": case / "input.elf", "objdump": objdump}
    if record["evidence_kind"] == "directed_program_selfcheck":
        paths.update({"commit_trace": case / "commit_trace.csv",
                      "summary": case.parents[1] / "summary.json",
                      "inputs": case / "inputs.json",
                      "trace_summary": case / "trace_summary.json"})
    elif record["evidence_kind"] == "random_spike_complete_result":
        paths.update({"commit_trace": case / "ara_commit_trace.csv",
                      "result": case / "result.json"})
    else:
        raise ValueError(f"unsupported evidence kind: {record['evidence_kind']}")
    if set(expected) != set(paths):
        raise ValueError(f"case evidence inventory differs: {case}")
    for label, path in paths.items():
        if sha256(path) != expected[label]:
            raise ValueError(f"case evidence changed: {case}: {label}")


def audit(random_path: Path = RANDOM, policy_path: Path = POLICY) -> dict:
    random = json.loads(random_path.read_text())
    policy = json.loads(policy_path.read_text())
    if (len(random["accepted_cases"]) != 70 or len(policy["accepted_cases"]) != 1 or
            random["excluded_cases"] or policy["excluded_cases"]):
        raise ValueError("final activity case inventory differs")
    images = (random["image_groups"], policy["image_groups"])
    if (any(image["status"] != "SINGLE_IMAGE" or image["group_count"] != 1
            for image in images) or
            set(images[0]["groups"]) != set(images[1]["groups"])):
        raise ValueError("activity reports do not share one final simulator image")
    if random["plan"] != policy["plan"]:
        raise ValueError("activity reports use different coverage plans")
    plan = Path(random["plan"]["path"])
    if sha256(plan) != random["plan"]["sha256"]:
        raise ValueError("coverage plan changed")
    objdump = Path(random["inputs"]["objdump"])
    if objdump != Path(policy["inputs"]["objdump"]):
        raise ValueError("activity reports use different disassemblers")
    cases = random["accepted_cases"] + policy["accepted_cases"]
    if len({entry["case"] for entry in cases}) != 71:
        raise ValueError("duplicate case in activity union")
    for entry in cases:
        verify_case_hashes(entry, objdump)
    axes = {name: union_axis(random["axes"][name], policy["axes"][name])
            for name in AXES}
    cross = union_axis(random["crosses"]["sew_lmul_policy"],
                       policy["crosses"]["sew_lmul_policy"])
    complete = all(not axis["unobserved_bins"] for axis in axes.values()) and not cross["unobserved_bins"]
    return {"status": "ACTIVITY_OBSERVED" if complete else "INCOMPLETE",
            "scope": "DUT-retired activity from strict random comparisons and one directed selfcheck; "
                     "not RTL code or full functional coverage",
            "case_count": 71, "random_case_count": 70, "directed_case_count": 1,
            "image_fingerprint": next(iter(images[0]["groups"])),
            "random_report": str(random_path), "random_report_sha256": sha256(random_path),
            "policy_report": str(policy_path), "policy_report_sha256": sha256(policy_path),
            "plan_sha256": random["plan"]["sha256"], "objdump_sha256": sha256(objdump),
            "axes": axes, "sew_lmul_policy": cross}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output exists: {args.output}")
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{result['status']}: {result['case_count']} cases; "
          f"{result['sew_lmul_policy']['observed_bins']}/"
          f"{result['sew_lmul_policy']['target_bins']} type/policy bins")
    return 0 if result["status"] == "ACTIVITY_OBSERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
