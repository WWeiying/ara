#!/usr/bin/env python3
"""Summarize observed batch outcomes without diagnosing or repairing RTL."""
import argparse
from collections import Counter
import json
import hashlib
from pathlib import Path


def read(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def fingerprint(outcome):
    artifact = Path(outcome["artifact_dir"])
    comparison = read(artifact / "commit_comparison.json")
    vector = read(artifact / "vector_commit_comparison.json")
    # A shared encoding is a triage hint, not proof of a shared root cause.
    next_op = comparison.get("next_spike") or {}
    mismatch = vector.get("first_mismatch") or comparison.get("mismatch") or {}
    if not isinstance(mismatch, dict):
        mismatch = {"detail": str(mismatch)}
    instruction = next_op.get("instruction") or mismatch.get("instruction")
    pc = next_op.get("pc") or mismatch.get("pc")
    key = f"{outcome['status']}:{instruction or 'unclassified'}"
    evidence = {}
    for name in ("inputs.json", "rtl.command.json", "spike.command.json", "command.json",
                 "commit_comparison.json", "vector_commit_comparison.json"):
        path = artifact / name
        if path.is_file():
            evidence[name] = {"path": str(path),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return key, {"instruction": instruction, "pc": pc, "first_mismatch": mismatch,
                 "last_matched": comparison.get("last_matched"),
                 "artifact_dir": str(artifact), "evidence_files": evidence,
                 "reproduction_note": "Recorded commands identify the exact stimulus and image; "
                                      "replay only into a fresh directory with redirected outputs. "
                                      "This is a representative case, not a minimized reproducer."}


def summarize(batch):
    checkpoint = read(batch / "checkpoint.json")
    plan = read(batch / "plan.json")["cases"]
    outcomes = checkpoint.get("cases", {})
    counts = Counter()
    by_kind = {}
    groups = {}
    cases = []
    for row in plan:
        outcome = outcomes.get(row["name"])
        status = outcome["status"] if outcome else "NOT_COMPLETED"
        counts[status] += 1
        kind_counts = by_kind.setdefault(row["kind"], Counter())
        kind_counts[status] += 1
        record = {"name": row["name"], "kind": row["kind"], "test": row.get("test"),
                  "seed": row.get("seed"), "status": status}
        if outcome:
            record.update(outcome)
        cases.append(record)
        if outcome and status != "PASS":
            key, evidence = fingerprint(outcome)
            group = groups.setdefault(key, {"count": 0, "representatives": [], "cases": []})
            group["count"] += 1
            group["cases"].append(row["name"])
            if len(group["representatives"]) < 3:
                group["representatives"].append({"name": row["name"], **evidence})
    return {"campaign_status": checkpoint.get("status"), "counts": dict(counts),
            "by_kind": {k: dict(v) for k, v in by_kind.items()}, "cases": cases,
            "failure_groups": groups,
            "grouping_note": "Provisional grouping by verdict/encoding, not confirmed RTL root causes. "
                             "All cases are retained; up to three examples per group are displayed.",
            "coverage_note": "Functional case counts are not code coverage percentages."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.batch.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("campaign_status", "counts", "by_kind")}, indent=2))


if __name__ == "__main__":
    main()
