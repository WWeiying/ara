#!/usr/bin/env python3
"""Archive the zero-cycle-change dispatcher, estimate and QBS range checks."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

try:
    from .collect_qbs_pipeline_results import command_cases
except ImportError:
    from collect_qbs_pipeline_results import command_cases

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed(path, marker):
    text = path.read_text()
    if marker not in text or "$finish" not in text or re.search(r"^(?:Fatal|Error):", text, re.M):
        raise RuntimeError(f"incomplete or failed check: {path}")
    return text


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def compare_commands(before, after):
    old, new = command_cases(before), command_cases(after)
    if (len(old) != 33 or old != new or
            any(p.read_text().count("QBS end-to-end case ") != 33 for p in (before, after))):
        raise RuntimeError("QBS command identity or cycle count changed")
    return list(new.values())


def compare_real(before, after):
    old, new = rows(before), rows(after)
    if len(old) != 6 or len(new) != 6:
        raise RuntimeError("expected six distinct real QBS cases")
    old = {r["case"]: r for r in old}
    new = {r["case"]: r for r in new}
    if len(old) != 6 or old != new:
        raise RuntimeError("real QBS identity, traffic, work or cycles changed")
    return list(new.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, baseline, out = args.run.resolve(), args.baseline.resolve(), args.output.resolve()
    soc = json.loads((run / "soc/status.json").read_text())
    real = json.loads((run / "real/status.json").read_text())
    if soc["state"] != "PASS" or real["state"] != "PASS":
        raise RuntimeError("SoC and real-capture regression must both pass")
    if sha(Path(real["simv"])) != real["simv_sha256"]:
        raise RuntimeError("QBS simulator changed after the real-capture regression")
    for name, expected in soc["source_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"source changed after verification: {name}")
    tests = rows(run / "soc/results/summary.csv")
    if ({r["name"] for r in tests} != set(soc["tests"]) or
            len(tests) != len(soc["tests"]) or any(r["status"] != "PASS" for r in tests)):
        raise RuntimeError("incomplete SoC test results")
    markers = {
        "checks/dispatcher/run.log": "Dispatcher equivalence PASS checks=67040",
        "exact_address_checks/feedback/run.log": "Feedback cones PASS arb=225680 address_cycles=67571",
        "engine/run.log": "QBS engine PASS: 33 functional cases plus four fault classes",
    }
    for path, marker in markers.items():
        completed(run / path, marker)
    commands = compare_commands(baseline / "final/engine/run.log", run / "engine/run.log")
    slices = compare_real(baseline / "real_after/real/summary.csv", run / "real/real/summary.csv")
    inputs = {}
    for relative in ("commands.vectors", *(f"real/{r['case']}.vectors" for r in slices)):
        old, new = baseline / "real_after" / relative, run / "real" / relative
        if sha(old) != sha(new):
            raise RuntimeError(f"real or command input changed: {relative}")
        inputs[relative] = sha(new)
    for r in slices:
        relative = f"real/{r['case']}.log"
        old = completed(baseline / "real_after" / relative, "QBS engine PASS: 1 functional cases")
        new = completed(run / "real" / relative, "QBS engine PASS: 1 functional cases")
        for prefix in ("QBS traffic ", "QBS phase "):
            previous = [line for line in old.splitlines() if line.startswith(prefix)]
            current = [line for line in new.splitlines() if line.startswith(prefix)]
            if not previous or previous != current:
                raise RuntimeError(f"phase or traffic changed: {relative}")
    out.mkdir(parents=True, exist_ok=False)
    for relative in (*markers, "soc/results/summary.csv", "real/real/summary.csv"):
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run / relative, target)
    result = {
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "run": str(run), "baseline": str(baseline), "state": "PASS",
        "added_pipeline_stages": 0, "added_architectural_latency_cycles": 0,
        "added_declared_rtl_state_bits": 48, "formal_equivalence": False,
        "source_sha256": soc["source_sha256"],
        "input_sha256": inputs,
        "soc_tests": tests, "command_cases": commands, "real_cases": slices,
        "whole_soc_timing_after_changes_available": False,
        "local_dc": {},
    }
    for name in ("dc_address_before", "dc_address", "dc_dispatcher_before", "dc_dispatcher"):
        path = run / name / "status.json"
        result["local_dc"][name] = json.loads(path.read_text()) if path.exists() else {"state": "PENDING"}
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: {len(tests)} SoC tests, 33 QBS commands, six real slices; {out}")


if __name__ == "__main__":
    main()
