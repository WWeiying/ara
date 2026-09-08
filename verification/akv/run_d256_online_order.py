#!/usr/bin/env python3
"""Gate a serial D256 numerical regression on the real KV140 reproducer.

Run in a detached session. Each VCS point has a three-hour deadline, and no
simulation logs are polled. A failed point stops the remaining cohort.
"""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from run_portability_stage2 import ROOT, command, sha, write_json

ANCHORS = ROOT / "hardware/akv_d256_efficiency_runs"
CASES = (
    ("gemma_kv140", "akv_v2", "panel4_kv140"),
    ("online_pv_smoke", "smoke", "panel4_kv140"),
    ("gemma_kv17", "akv_v2", "panel4_kv17"),
    ("qwen_d128", "akv_v2", "qwen_d128_kv16"),
    ("smollm_d64", "akv_v2", "smollm_d64_kv5"),
    ("phi_d96", "akv_v2", "phi_d96_kv18"),
    ("rvv_gemma_kv140", "rvv", "panel4_kv140"),
)


def sources():
    names = subprocess.check_output([
        "git", "ls-files", "-z", "software/akv", "apps/llama_q4km_operator",
        "apps/akv_d256_reuse_smoke", "apps/common", "apps/Makefile",
        "verification/akv", "hardware/scripts/llama_q4km_extract"],
        cwd=ROOT).decode().split("\0")
    return {name: sha(ROOT / name) for name in sorted(names) if name and
            Path(name).name != "data.S" and
            (Path(name).suffix in (".c", ".h", ".S", ".py", ".sh", ".mk") or
             Path(name).name in ("Makefile", "CMakeLists.txt"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = {"status": "RUNNING", "pid": os.getpid(), "cases": {},
             "started_at": datetime.now(timezone.utc).isoformat(),
             "source_sha256": sources(),
             "revision": subprocess.check_output(
                 ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    plans = []
    for name, mode, anchor in CASES:
        metadata = json.loads((ANCHORS / anchor / "stage.json").read_text())
        plans.append({"name": name, "mode": mode, "capture": metadata["capture"],
                      "kv": metadata["kv"], "sim_dir": metadata["sim_dir"],
                      "simv_sha256": metadata["simv_sha256"]})
        state["cases"][name] = {"status": "PENDING"}
    write_json(out / "plan.json", plans)
    write_json(out / "status.json", state)
    rc = 1
    metrics = []
    try:
        for plan in plans:
            name, mode = plan["name"], plan["mode"]
            if sources() != state["source_sha256"]:
                raise RuntimeError("source changed; refusing a mixed-revision cohort")
            if sha(Path(plan["sim_dir"]) / "simv") != plan["simv_sha256"]:
                raise RuntimeError("simulator differs from the matched baseline")
            state["current"] = name
            state["cases"][name]["status"] = "RUNNING"
            write_json(out / "status.json", state)
            argv = [sys.executable, ROOT / "verification/akv/run_d256_efficiency.py",
                    "--mode", mode, "--sim-dir", plan["sim_dir"], "--output", out / name]
            if mode != "smoke":
                argv += ["--capture", plan["capture"], "--kv", str(plan["kv"])]
            rc = command(argv, out / f"{name}.log", timeout=11400)
            record = json.loads((out / name / "stage.json").read_text())
            state["cases"][name] = record
            if sources() != state["source_sha256"]:
                raise RuntimeError("source changed during the point; review its saved snapshot")
            if rc or record["status"] != "PASS":
                rc = rc or 1
                break
            if mode != "smoke":
                rows = json.loads((out / name / "metrics.json").read_text())
                total, = [row for row in rows if row["phase"] == "total"]
                metrics.append({"case": name, "status": "PASS", **{
                    key: total[key] for key in (
                        "kernel_cycles", "mismatches", "akv_v2_column_load",
                        "akv_v2_column_panel", "akv_v2_row_load", "akv_replay_bytes",
                        "retired_vector_inst_count", "retired_scalar_inst_count")}})
            write_json(out / "status.json", state)
        state["status"] = "PASS" if rc == 0 else "FAIL"
    except Exception as error:
        state.update(status="FAIL", error=str(error))
        rc = 1
    for record in state["cases"].values():
        if record["status"] == "PENDING":
            record["status"] = "SKIPPED_AFTER_FAILURE"
    state.update(finished_at=datetime.now(timezone.utc).isoformat(), return_code=rc)
    write_json(out / "status.json", state)
    write_json(out / "successful_metrics.json", metrics)
    if metrics:
        with (out / "successful_metrics.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(metrics[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(metrics)
    return rc


if __name__ == "__main__":
    sys.exit(main())
