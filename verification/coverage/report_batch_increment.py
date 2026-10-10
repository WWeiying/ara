#!/usr/bin/env python3
"""Report same-image raw-point increments, independently of the frozen driver.

Each collection's first N samples in frozen plan order form its own baseline.
Invalid evidence is fatal, never skipped to select a more favorable baseline.
No simulator, coverage merger, or external command is executed. Raw branch
points are reported separately; line/expr are not unique-source-line metrics.
"""

import argparse
import hashlib
import json
from pathlib import Path

from merge_exploration import validate_sample
from run_verilator_coverage import iter_raw_points, sha256

SCOPES = {"line": True, "expression": True, "toggle": False,
          "fsm": False, "assertion": False}
PURPOSES = {"exploration": "EXPLORATION_ONLY_NOT_CORRECTNESS_SIGNOFF",
            "passed-only": "INDEPENDENT_VCS_PASS_AND_COVERAGE_PASS"}
TYPES = ("line", "expr", "branch")


def read(path):
    return json.loads(Path(path).read_text())


def checked(path, expected):
    path = Path(path).resolve(strict=True)
    if sha256(path) != expected:
        raise ValueError(f"changed input: {path}")
    return path


def set_digest(points):
    value = hashlib.sha256()
    for point in sorted(points):
        value.update(json.dumps(point, separators=(",", ":"), ensure_ascii=True).encode() + b"\n")
    return value.hexdigest()


def point_sets(path, hierarchy, includes):
    universe, hits = set(), set()
    for props, count in iter_raw_points(path, hierarchy):
        if includes and not any(token in props.get("f", "") for token in includes):
            continue
        if count < 0 or props.get("t") not in TYPES:
            raise ValueError(f"negative count or unsupported raw point type: {path}: {props}")
        # Keep every property, including hierarchy, expression term and branch arm.
        point = tuple(sorted(props.items()))
        universe.add(point)
        if count:
            hits.add(point)
    if not universe:
        raise ValueError(f"no points in requested scope: {path}")
    return universe, hits


def load_collection(path, kind, baseline):
    document = read(path)
    if (document.get("status") != "COLLECTED" or document.get("purpose") != PURPOSES[kind] or
            document.get("coverage") != SCOPES):
        raise ValueError(f"not a collected line/expression {kind} collection: {path}")
    plan_path = checked(document["source_plan"], document["source_plan_sha256"])
    plan = read(plan_path)
    if plan.get("coverage") != SCOPES:
        raise ValueError("source plan coverage scope differs")
    checked(plan["image"], plan["image_sha256"])
    samples = document["samples"]
    if len(samples) < baseline:
        raise ValueError(f"{kind}: needs {baseline} valid samples, has {len(samples)}; baseline not shortened")
    names = [row["name"] for row in plan["cases"]]
    selected = [row["name"] for row in samples]
    if (len(set(names)) != len(names) or len(set(selected)) != len(selected) or
            selected != [name for name in names if name in set(selected)]):
        raise ValueError("collection is duplicated, reordered, or not a subset of its frozen plan")
    cases = {row["name"]: row for row in plan["cases"]}
    seen_results = set()
    for sample in samples:
        case = cases[sample["name"]]
        if sample.get("raw_valid") is not True or sample.get("status") not in ("PASS", "FAIL"):
            raise ValueError("collection contains a non-valid replay sample")
        if (sample.get("source_status") != case["source_status"] or
                sample.get("source_status") == "REJECTED_STIMULUS" or
                sample.get("elf_sha256") != case["elf_sha256"] or
                sample.get("source_elf") != case["source_elf"] or
                sample.get("source_audit") != case.get("source_audit") or
                sample.get("source_files") != case["source_files"]):
            raise ValueError("source association differs from frozen plan")
        passed = sample["source_status"] == sample["status"] == "PASS"
        if sample.get("passed_only") is not passed or (kind == "passed-only" and not passed):
            raise ValueError("failed sample cannot be treated as independently passed")
        result = checked(sample["result"], sample["result_sha256"])
        if result in seen_results:
            raise ValueError("duplicate replay result")
        seen_results.add(result)
    return document, plan


def check_pass_audit(sample, case):
    audit = checked(sample["source_reaudit"], sample["source_reaudit_sha256"])
    report = read(audit)
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
        raise ValueError("source re-audit is not a matching complete PASS")


def report(exploration, passed_only, baseline, hierarchy, includes):
    if baseline < 1:
        raise ValueError("baseline sample count must be positive")
    paths = {"exploration": Path(exploration).resolve(strict=True),
             "passed-only": Path(passed_only).resolve(strict=True)}
    before = {kind: sha256(path) for kind, path in paths.items()}
    collections, plans = {}, {}
    for kind, path in paths.items():
        collections[kind], plans[kind] = load_collection(path, kind, baseline)
    if (collections["exploration"]["source_plan_sha256"] !=
            collections["passed-only"]["source_plan_sha256"] or
            plans["exploration"] != plans["passed-only"]):
        raise ValueError("collections must refer to the same frozen batch plan and image")
    plan = plans["exploration"]
    expected_passed = [s for s in collections["exploration"]["samples"] if s["passed_only"]]
    if expected_passed != collections["passed-only"]["samples"]:
        raise ValueError("passed-only collection is not the exact independently passing subset")
    cases = {row["name"]: row for row in plan["cases"]}
    accumulated = {kind: {"baseline": set(), "full": set()} for kind in paths}
    positions = {kind: {s["name"]: i for i, s in enumerate(collections[kind]["samples"])}
                 for kind in paths}
    universe = None
    evidence = []
    for sample in collections["exploration"]["samples"]:
        result_path = Path(sample["result"])
        checked(result_path, sample["result_sha256"])
        validated = validate_sample(result_path)
        result = read(result_path)
        if (validated != sample["sample"] or validated["image_sha256"] != plan["image_sha256"] or
                result["status"] != sample["status"] or result["elf_sha256"] != sample["elf_sha256"]):
            raise ValueError("raw sample/image/ELF identity differs from collection")
        case = cases[sample["name"]]
        for source, digest in case["source_files"].items():
            checked(source, digest)
        checked(case["source_elf"], case["elf_sha256"])
        if sample["passed_only"]:
            if (result.get("sim_returncode") != 0 or result.get("report_returncode") != 0 or
                    result.get("self_check_pass") is not True):
                raise ValueError("passed sample lacks successful replay evidence")
            check_pass_audit(sample, case)
        raw = Path(validated["coverage"])
        current, hits = point_sets(raw, hierarchy, includes)
        if universe is None:
            universe = current
        elif current != universe:
            raise ValueError(f"point denominator mismatch: {sample['name']}: "
                             f"missing={len(universe-current)}, extra={len(current-universe)}")
        checked(raw, validated["coverage_sha256"])
        checked(result_path, sample["result_sha256"])
        for kind in paths:
            position = positions[kind].get(sample["name"])
            if position is not None:
                accumulated[kind]["full"].update(hits)
                if position < baseline:
                    accumulated[kind]["baseline"].update(hits)
        evidence.append({"name": sample["name"], "source_status": sample["source_status"],
                         "replay_status": sample["status"], "elf_sha256": sample["elf_sha256"],
                         **validated})
    result = {"status": "PASS", "status_scope": "increment evidence integrity only, not RTL signoff",
              "image_sha256": plan["image_sha256"], "coverage": SCOPES,
              "hierarchy_prefix": hierarchy, "include_paths": includes,
              "baseline_samples": baseline,
              "baseline_rule": "first N valid samples per collection in frozen plan order; not completion order",
              "point_identity": "all raw properties, instance-sensitive; duplicate keys unioned",
              "denominator_check": {"status": "PASS", "samples_checked": len(evidence),
                                    "points": len(universe), "point_set_sha256": set_digest(universe)},
              "collections": {}, "samples": evidence}
    for kind, sets in accumulated.items():
        by_type = {}
        for point_type in TYPES:
            domain = {key for key in universe if dict(key)["t"] == point_type}
            initial = sets["baseline"] & domain
            final = sets["full"] & domain
            gained = final - initial
            by_type[point_type] = {
                "baseline_denominator": len(domain), "full_denominator": len(domain),
                "denominator_equal": True, "denominator_sha256": set_digest(domain),
                "baseline_hit": len(initial), "full_hit": len(final), "new_hit": len(gained),
                "baseline_hit_sha256": set_digest(initial), "full_hit_sha256": set_digest(final),
                "new_hit_sha256": set_digest(gained),
                "baseline_percent": 100 * len(initial) / len(domain) if domain else None,
                "full_percent": 100 * len(final) / len(domain) if domain else None,
                "increment_percentage_points": 100 * len(gained) / len(domain) if domain else None}
        samples = collections[kind]["samples"]
        result["collections"][kind] = {
            "manifest": str(paths[kind]), "manifest_sha256": before[kind],
            "purpose": PURPOSES[kind], "baseline_names": [s["name"] for s in samples[:baseline]],
            "full_names": [s["name"] for s in samples], "by_type": by_type}
        checked(paths[kind], before[kind])
        checked(collections[kind]["source_plan"], collections[kind]["source_plan_sha256"])
    checked(plan["image"], plan["image_sha256"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exploration", type=Path, required=True, help="exploration/collection.json")
    parser.add_argument("--passed-only", type=Path, required=True, help="passed-only/collection.json")
    parser.add_argument("--baseline-samples", type=int, required=True)
    parser.add_argument("--hierarchy-prefix", default="ara_tb_verilator.dut.i_ara_soc")
    parser.add_argument("--include-path", action="append",
                        help="repeatable; defaults to hardware/src and hardware/deps/cva6")
    parser.add_argument("--output", type=Path, required=True, help="new JSON report; never overwrite")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    try:
        result = report(args.exploration, args.passed_only, args.baseline_samples,
                        args.hierarchy_prefix, args.include_path or ["/hardware/src/", "/hardware/deps/cva6/"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"INCREMENT_REJECTED: {error}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for kind, collection in result["collections"].items():
        for point_type in ("line", "expr"):
            counts = collection["by_type"][point_type]
            print(f"{kind} {point_type}: {counts['baseline_hit']} -> {counts['full_hit']} "
                  f"/ {counts['full_denominator']}, new_hit={counts['new_hit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
