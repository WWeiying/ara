#!/usr/bin/env python3
"""Archive the explicit D256 cohort, including failures and pending tests."""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import select
import time

from run_d256_efficiency import collect
from run_portability_stage2 import ROOT, sha, write_json

COHORT = (
    "baseline_kv17", "rvv_kv17", "reuse4_kv17", "panel4_kv17",
    "reuse4_kv140", "rvv_kv140", "panel4_kv140",
    "qwen_d128_kv16", "smollm_d64_kv5", "phi_d96_kv18",
    "bit_exact_panel4",
)
FIELDS = (
    "case", "status", "kernel_cycles", "mismatches",
    "akv_v2_full", "akv_v2_column_load", "akv_v2_column_panel",
    "akv_v2_logical_column", "akv_v2_row_load", "akv_replay_bytes",
    "akv_kv_external_bytes", "axi_ar_bytes", "retired_vector_inst_count",
    "retired_scalar_inst_count", "fp_exec_lane_fires", "akv_busy_cycles",
)
RESULT = re.compile(r"^LLAMA_OPERATOR \S+ (PASS|FAIL) cycles=(\d+) mismatches=(\d+)$", re.M)
EVIDENCE = re.compile(r"^(?:ATTENTION_DISPATCH|ATTENTION_MISMATCH|LLAMA_OPERATOR|"
                      r"Core Test|AKV_D256_REUSE|AKV D256 reuse smoke|"
                      r"AKV native portability smoke|QBS/AKV handoff smoke)")


def read_state(directory):
    path = directory / "stage.json"
    return json.loads(path.read_text()) if path.exists() else {"status": "MISSING"}


def wait_workers(root, handoff):
    """One blocking pidfd wait; never periodically poll VCS logs."""
    workers = [(read_state(root / name).get("pid"), str(root / name)) for name in COHORT]
    if handoff is not None and (handoff / "pid").exists():
        workers.append((int((handoff / "pid").read_text()), str(handoff.name)))
    descriptors = []
    try:
        for pid, identity in workers:
            if not pid:
                continue
            try:
                fd = os.pidfd_open(pid)
            except ProcessLookupError:
                continue
            try:
                cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
                # The shell launcher may not put its environment tag in argv.
                if identity not in cmdline and "run_portability_rtl.sh" not in cmdline:
                    os.close(fd)
                    continue
            except (FileNotFoundError, ProcessLookupError):
                os.close(fd)
                continue
            descriptors.append(fd)
        remaining = list(descriptors)
        deadline = time.monotonic() + 11500
        while remaining:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                break
            ready, _, _ = select.select(remaining, [], [], timeout)
            if not ready:
                break
            remaining = [fd for fd in remaining if fd not in ready]
    finally:
        for fd in descriptors:
            os.close(fd)


def archive(root, destination, handoff=None):
    destination.mkdir(parents=True, exist_ok=True)
    result = {"recorded_at": datetime.now(timezone.utc).isoformat(),
              "run_root": str(root), "cases": {}, "complete": True,
              "d256_default_ggml_selector": "fallback; performance and numerics gates unchanged"}
    table = []
    for name in COHORT:
        directory = root / name
        state = read_state(directory)
        record = {"state": state, "evidence": []}
        paths = [p / "ara.log" for p in directory.glob("decode_attention_core_*")
                 if p.is_dir() and not p.is_symlink()]
        if state.get("mode") == "smoke":
            paths = [directory / "ara.log"]
        if len(paths) > 1:
            raise RuntimeError(f"ambiguous cohort directory: {name}")
        row = {"case": name, "status": state["status"]}
        if paths and paths[0].exists():
            log = paths[0]
            text = log.read_text()
            record["evidence"] = [line for line in text.splitlines() if EVIDENCE.match(line)]
            record["log_sha256"] = sha(log)
            if match := RESULT.search(text):
                row.update(kernel_cycles=int(match[2]), mismatches=int(match[3]))
            if state["status"] == "PASS" and state.get("mode") != "smoke":
                records = collect(directory, state["mode"], state["kv"])
                totals = [r for r in records if r["phase"] == "total"]
                if len(totals) != 1 or totals[0]["simv_sha256"] != state["simv_sha256"]:
                    raise RuntimeError(f"inconsistent simulator/total evidence: {name}")
                row.update({key: totals[0][key] for key in FIELDS if key in totals[0]})
                record["metrics"] = records
            elif state["status"] == "PASS" and (
                    "AKV D256 reuse smoke: PASS cases=8 bit_exact=1" not in text or
                    "Core Test *** SUCCESS" not in text):
                raise RuntimeError("incomplete bit-exact evidence")
        elif state["status"] == "PASS":
            raise RuntimeError(f"PASS without evidence: {name}")
        if state["status"] not in ("PASS", "FAIL"):
            result["complete"] = False
        table.append(row)
        result["cases"][name] = record

    if handoff is not None:
        handoff_state = ((handoff / "status").read_text().strip()
                         if (handoff / "status").exists() else "MISSING")
        result["handoff"] = {"path": str(handoff), "status": handoff_state, "tests": {}}
        for name in ("portable", "handoff"):
            log = handoff / name / "run.vcs.log"
            if log.exists():
                result["handoff"]["tests"][name] = {
                    "log_sha256": sha(log),
                    "evidence": [line for line in log.read_text().splitlines() if EVIDENCE.match(line)],
                }
        if handoff_state not in ("PASS", "FAIL") and not handoff_state.startswith("FAIL_"):
            result["complete"] = False
    for name in ("numerics_kv140.json",):
        path = root / name
        if path.exists():
            result[name.removesuffix(".json")] = json.loads(path.read_text())
    superseded = root / "bit_exact/superseded.json"
    if superseded.exists():
        result["superseded_fixture"] = json.loads(superseded.read_text())
    result["all_pass"] = (all(row["status"] == "PASS" for row in table) and
                          (handoff is None or result["handoff"]["status"] == "PASS"))
    with (destination / "performance.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(table)
    write_json(destination / "summary.json", result)
    print(json.dumps({"complete": result["complete"],
                      "statuses": {r["case"]: r["status"] for r in table},
                      "output": str(destination)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "hardware/akv_d256_efficiency_runs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--handoff", type=Path)
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    handoff = args.handoff.resolve() if args.handoff else None
    if args.wait:
        wait_workers(root, handoff)
    archive(root, args.output.resolve(), handoff)


if __name__ == "__main__":
    main()
