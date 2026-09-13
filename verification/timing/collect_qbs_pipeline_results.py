#!/usr/bin/env python3
"""Collect retimed-QBS functional results, cycle deltas and independent DC status."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return path.read_text(errors="replace") if path.is_file() else ""


def check(path, marker):
    log = read(path)
    errors = re.findall(r"^(?:Error|Fatal):.*", log, re.M)
    return {"state": "FAIL" if errors else "PASS" if marker in log and
            "$finish" in log else "PENDING", "log": str(path), "errors": errors}


def command_cases(path):
    pattern = (r"QBS end-to-end case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) "
               r"Kb=(\d+) layouts=(\d+)/(\d+) cycles=(\d+)")
    return {int(values[0]): dict(zip(
        ("case", "profile", "m", "n", "k_blocks", "weight_layout", "activation_layout", "cycles"),
        map(int, values))) for values in re.findall(pattern, read(path))}


def csv_rows(path):
    if not path.is_file():
        return {}
    with path.open(newline="") as source:
        return {row["case"]: row for row in csv.DictReader(source)}


def dc_result(path):
    status = json.loads(read(path / "status.json") or '{"state":"PENDING"}')
    if status["state"] == "PASS":
        timing = read(path / "reg_to_reg.rpt")
        for key, pattern in (
                ("worst_ff_arrival_ns", r"data arrival time\s+([\d.]+)"),
                ("worst_ff_slack_ns", r"slack \([^)]*\)\s+(-?[\d.]+)")):
            match = re.search(pattern, timing)
            status[key] = float(match[1]) if match else None
        match = re.search(r"Total cell area:\s+([\d.]+)", read(path / "area.rpt"))
        status["cell_area"] = float(match[1]) if match else None
    status["scope"] = "integer profile pipeline with input FFs; not integrated SRAM/SoC timing"
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, baseline, out = args.run.resolve(), args.baseline.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"recorded_utc": datetime.now(timezone.utc).isoformat(),
              "run": str(run), "baseline": str(baseline),
              "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                 text=True).strip(),
              "dot_latency_before": 1, "dot_latency_after": 3,
              "correction_latency_before": 1, "correction_latency_after": 3,
              "added_declared_state_bits": 1561, "integrated_new_timing_measured": False,
              "formal_equivalence": False, "sources": {}}
    for name in ("qbs_dot_array.sv", "qbs_profile_engine_int.sv"):
        before = run / "before" / name
        after = ROOT / "hardware/src/vlsu/qbs" / name
        result["sources"][name] = {
            "before_sha256": hashlib.sha256(before.read_bytes()).hexdigest(),
            "after_sha256": hashlib.sha256(after.read_bytes()).hexdigest()}
    result["checks"] = {
        "dot": check(run / "check/dot_pipeline/run.log", "QBS dot pipeline PASS"),
        "datapath": check(run / "check/datapath/run.log", "Timing datapath equivalence PASS"),
        "profiles": check(run / "profile/run.log", "QBS profile engine PASS: 448 cases"),
        "profiles_stalled": check(run / "profile_stall/run.log", "QBS profile engine PASS: 448 cases"),
        "engine": check(run / "engine/run.log", "QBS engine PASS: 33 functional cases plus four fault classes"),
        "compute": check(run / "compute/run.log", "QBS command engine PASS: 33 functional cases")}
    result["pipeline_fault_stages"] = re.findall(
        r"QBS pipeline fault stage (\d) PASS drain_cycles=(\d+)", read(run / "compute/run.log"))
    before, after = command_cases(baseline / "qbs_engine/run.log"), command_cases(run / "engine/run.log")
    comparisons = []
    for key in sorted(before.keys() & after.keys()):
        old, new = before[key], after[key]
        if any(old[field] != new[field] for field in old if field != "cycles"):
            raise SystemExit(f"command identity mismatch: case {key}")
        comparisons.append({**new, "before_cycles": old["cycles"],
                            "delta_cycles": new["cycles"] - old["cycles"],
                            "delta_percent": 100 * (new["cycles"] / old["cycles"] - 1)})
    result["command_comparisons"] = comparisons
    if comparisons:
        with (out / "commands.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(comparisons[0]))
            writer.writeheader()
            writer.writerows(comparisons)
    before, after = csv_rows(baseline / "real/summary.csv"), csv_rows(run / "real/summary.csv")
    real = []
    for key in before.keys() & after.keys():
        old, new = before[key], after[key]
        if any(old[field] != new[field] for field in ("profile", "m", "n", "k")):
            raise SystemExit(f"real slice identity mismatch: {key}")
        real.append({**new, "before_cycles": int(old["cycles"]),
                     "delta_cycles": int(new["cycles"]) - int(old["cycles"]),
                     "delta_percent": 100 * (int(new["cycles"]) / int(old["cycles"]) - 1),
                     "traffic_and_work_equal": all(old[field] == new[field] for field in (
                         "weight_bytes", "activation_bytes", "payload_bytes", "ranges", "dot_cycles"))})
    result["real_comparisons"] = sorted(real, key=lambda row: row["case"])
    result["dc"] = {name: dc_result(run / name) for name in ("dc_before", "dc_after")}
    result["soc_regression"] = json.loads(read(run / "soc/status.json") or '{"state":"PENDING"}')
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    if real:
        with (out / "real.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(result["real_comparisons"][0]))
            writer.writeheader()
            writer.writerows(result["real_comparisons"])
    print(json.dumps({"checks": {k: v["state"] for k, v in result["checks"].items()},
                      "commands": len(comparisons), "real_slices": len(real),
                      "dc": {k: v["state"] for k, v in result["dc"].items()},
                      "soc": result["soc_regression"]["state"]}, indent=2))


if __name__ == "__main__":
    main()
