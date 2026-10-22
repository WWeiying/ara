#!/usr/bin/env python3
"""Independent sealed M9 control evidence audit; never reruns the DUT."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    root = HERE / "prepared01"
    plan_path = root / "plan.json"
    complete_path = root / "complete.json"
    plan = json.loads(plan_path.read_text())
    complete = json.loads(complete_path.read_text())
    need(complete["status"] == "PASS_M9_CONTROLS16_ARCHITECTURAL", "Terminal status")
    need(complete["aborted"] is False and complete["retries"] == 0, "Abort/retry")
    need(digest(plan_path) == complete["plan_sha256"], "Plan identity")
    pins = dict(plan["pins"])
    for path, expected in complete["evidence_pins"].items():
        need(path not in pins or pins[path] == expected, "Conflicting pin: " + path)
        pins[path] = expected
    for path, expected in pins.items():
        need(digest(path) == expected, "Evidence drift: " + path)
    cases = {case["id"]: case for case in plan["cases"]}
    results = {result["name"]: result for result in complete["results"]}
    need(len(cases) == len(results) == len(complete["results"]) == 16, "Membership")
    need(cases.keys() == results.keys(), "Missing/extra member")
    rows = 0
    for name, case in cases.items():
        result = results[name]
        need(result["status"] == "PASS" and type(result["returncode"]) is int
             and result["returncode"] == 0, "Case outcome: " + name)
        artifacts = Path(result["artifact_dir"])
        child = json.loads((artifacts / "child_exit.json").read_text())
        need(type(child["returncode"]) is int and child["returncode"] == 0
             and child["timed_out"] is False and child["failure_seen"] is False,
             "Child outcome: " + name)
        need(child["elapsed_s"] <= case["timeout_s"], "Child budget: " + name)
        need(digest(artifacts / "input.elf") == case["sha256"], "ELF: " + name)
        console = (artifacts / "console.log").read_text()
        for marker in case["pass_markers"]:
            need(marker in console, "Missing marker: " + name)
        actual = artifacts / "commit_trace.csv"
        baseline = Path(case["baseline_csv"])
        need(digest(actual) == digest(baseline), "Complete CSV differs: " + name)
        with actual.open(newline="") as stream:
            reader = csv.reader(stream)
            next(reader)
            count = sum(1 for _ in reader)
        need(count == complete["performance"][name]["rows"], "Row count: " + name)
        rows += count
    need(rows == complete["compared_rows"] == 310350, "Aggregate rows")
    report = dict(status="PASS_INDEPENDENT_M9_CONTROLS16_AUDIT", cases=16,
                  compared_rows=rows, checked_pins=len(pins),
                  complete_sha256=digest(complete_path), plan_sha256=digest(plan_path),
                  scope="Exact M9 controls16 versus sealed M8 complete CSVs; no alignment4 acceptance")
    destination = HERE / "audit_resume01.json"
    with destination.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
