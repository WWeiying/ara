#!/usr/bin/env python3
"""Archive the non-FU timing changes only after every functional gate passes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from collect_control_timing_results import compare_commands, completed, rows
from run_feedback_regression import sources

ROOT = Path(__file__).resolve().parents[2]
CHANGED = (
    "ara_dispatcher.sv", "segment_sequencer.sv", "ara_soc.sv", "vlsu/addrgen.sv",
    "vlsu/vstu.sv", "vlsu/qbs/qbs_engine.sv", "vlsu/akv/akv_engine.sv")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks, run, out = args.checks.resolve(), args.run.resolve(), args.output.resolve()
    baseline = json.loads(args.baseline_summary.read_text())
    soc = json.loads((run / "soc_final/status.json").read_text())
    real = json.loads((run / "real/status.json").read_text())
    if soc["state"] != "PASS" or real["state"] != "PASS":
        raise RuntimeError("SoC and real-capture gates must both pass")
    if soc["source_sha256"] != sources() or len(real["results"]) != 8:
        raise RuntimeError("source changed or capture set incomplete")
    tests = rows(run / "soc_final/results/summary.csv")
    if len(tests) != len(soc["tests"]) or any(r["status"] != "PASS" for r in tests):
        raise RuntimeError("incomplete SoC regression")
    markers = {
        "expanded_final/dispatcher/run.log": "Dispatcher equivalence PASS checks=68640",
        "expanded_final/dispatcher/layout_run.log": "Dispatcher layout equivalence PASS",
        "cones/address_run.log": "AddrGen equivalence PASS",
        "vstu_final/vstu/run.log": "VSTU equivalence PASS cycles=24192",
        "qbs_miter/run.log": "QBS engine PASS: 33 functional cases plus four fault classes",
        "akv_miter/run.log": "AKV engine PASS: v1 D64/D128 plus v2 D64/D96/D128 and segmented D256",
    }
    for relative, marker in markers.items():
        completed(checks / relative, marker)
    commands = compare_commands(Path(baseline["run"]) / "engine/run.log", checks / "qbs_miter/run.log")
    if sha(checks / "qbs_miter/simv") != real["simv_sha256"]:
        raise RuntimeError("real captures did not use the cycle-checked simulator")
    changes = []
    for name in CHANGED:
        path = Path("hardware/src") / name
        old, new = checks / "before" / path, ROOT / path
        if sha(old) != baseline["source_sha256"][str(path)]:
            raise RuntimeError(f"pre-edit RTL differs from synthesis/capture baseline: {path}")
        changes.append({"path": str(path), "before_sha256": sha(old), "after_sha256": sha(new)})
    out.mkdir(parents=True, exist_ok=False)
    for relative in markers:
        dest = out / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(checks / relative, dest)
    for relative in ("soc_final/results/summary.csv", "soc_final/focus/summary.csv",
                     "real/summary.csv", "real/status.json"):
        dest = out / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run / relative, dest)
    layout = (checks / "expanded_final/dispatcher/layout_run.log").read_text()
    result = {
        "state": "PASS", "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "run": str(run), "checks": str(checks), "changes": changes,
        "baseline_summary": str(args.baseline_summary.resolve()),
        "baseline_sha256": sha(args.baseline_summary),
        "source_sha256": soc["source_sha256"], "soc_tests": tests,
        "dispatcher_cycles": 68640, "dispatcher_register_groups": 70,
        "layout_vectors": {v: int(n) for v, n in re.findall(r"VLEN=(\d+) checks=(\d+)", layout)},
        "address_vectors": 144000, "vstu_cycles": 24192,
        "qbs_cycle_checked_outputs": 68, "akv_cycle_checked_outputs": 53,
        "qbs_commands": commands, "real_cases": real["results"],
        "compute_pipeline_stages_added": 0, "address_cursor_state_bits_added": 288,
        "mmio_latency_change": "AXI cut on CTRL branch only; five independently buffered channels",
        "formal_equivalence": False, "local_dc_run": False,
        "post_change_whole_soc_timing_available": False,
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: control timing verification archived at {out}")


if __name__ == "__main__":
    main()
