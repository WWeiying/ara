#!/usr/bin/env python3
"""Collect focused timing evidence without treating unfinished runs as passes."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return path.read_text(errors="replace") if path.is_file() else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    result = {"recorded_utc": datetime.now(timezone.utc).isoformat(),
              "run_directory": str(run.relative_to(ROOT)), "added_pipeline_stages": 0,
              "added_rtl_state_bits": 50, "post_fix_integrated_timing_measured": False,
              "formal_equivalence": False, "source_sha256": {}, "checks": {}, "dc": {}}
    for name in ("hardware/src/lane/vmfpu.sv", "hardware/src/vlsu/qbs/qbs_engine.sv",
                 "hardware/src/vlsu/qbs/qbs_profile_engine_int.sv"):
        result["source_sha256"][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    for name, relative, pattern in (
        ("cones", "check/feedback/run.log", r"Feedback cones PASS arb=(\d+) address_cycles=(\d+)"),
        ("profile", "qbs_profile_r2/run.log", r"QBS profile engine PASS:.*"),
        ("engine", "qbs_engine/run.log", r"QBS engine PASS:.*")):
        text = read(run / relative)
        match = re.search(pattern, text)
        failed = re.search(r"Fatal:|Error:", text)
        result["checks"][name] = {"state": "FAIL" if failed else "PASS" if match else "PENDING",
                                   "evidence": match.group(0) if match else None, "log": relative}
    real = run / "real/summary.csv"
    if real.is_file():
        with real.open() as stream:
            result["real_model_slices"] = list(csv.DictReader(stream))
    rvv_dir = run / ("rvv_r2" if (run / "rvv_r2/status.json").is_file() else "rvv")
    rvv_status = rvv_dir / "status.json"
    if rvv_status.is_file():
        status = json.loads(rvv_status.read_text())
        result["rvv"] = {key: value for key, value in status.items() if key != "source_sha256"}
        result["rvv"]["directory"] = str(rvv_dir.relative_to(run))
        summary = rvv_dir / "results/summary.csv"
        if summary.is_file():
            with summary.open() as stream:
                result["rvv"]["results"] = list(csv.DictReader(stream))
    integrated = run / "soc_dc/status.json"
    if integrated.is_file():
        result["integrated_dc"] = json.loads(integrated.read_text())
    for name in ("dc_arb_before", "dc_arb_after", "dc_addr_before", "dc_addr_after"):
        path = run / name
        status = json.loads((path / "status.json").read_text())
        report = read(path / "reg_to_reg.rpt")
        arrival = re.search(r"data arrival time\s+([\d.]+)", report)
        slack = re.search(r"slack \((?:MET|VIOLATED)\)\s+(-?[\d.]+)", report)
        area = re.search(r"Total cell area:\s+([\d.]+)", read(path / "area.rpt"))
        status["first_ff_path_arrival_ns"] = float(arrival[1]) if arrival else None
        status["first_ff_path_slack_ns"] = float(slack[1]) if slack else None
        status["total_cell_area"] = float(area[1]) if area else None
        status["scope"] = "extracted cone, not complete module or integrated SoC"
        result["dc"][name] = status
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
