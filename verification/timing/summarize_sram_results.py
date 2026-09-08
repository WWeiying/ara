#!/usr/bin/env python3
"""Archive completed SRAM verification evidence, never infer missing results."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CASE = re.compile(r"QBS end-to-end case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) "
                  r"Kb=(\d+) layouts=(\d+)/(\d+) cycles=(\d+)")
TRAFFIC = re.compile(r"QBS traffic case=0 weight=(\d+) activation=(\d+) payload=(\d+) "
                     r"ranges=(\d+) dot=(\d+) prefetch_wait=(\d+)")
NAMES = ["q4_decode_m1n32", "q4_m4n32", "q4_m8n16", "q4_m7n16",
         "q6_m4n32", "q6_m8n16", "q6_m7n16"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed(path, marker):
    text = path.read_text()
    if marker not in text or re.search(r"Fatal:|Error:|Timing violation", text):
        raise ValueError(f"not a passing completed result: {path}")
    return text


def compare_cases(baseline, candidate):
    old = {tuple(map(int, row[:-1])): int(row[-1]) for row in CASE.findall(baseline)}
    new = {tuple(map(int, row[:-1])): int(row[-1]) for row in CASE.findall(candidate)}
    if not old or old.keys() != new.keys():
        raise ValueError("baseline/candidate case identities differ")
    return [list(key) + [old[key], new[key], new[key] - old[key],
                        100 * (new[key] - old[key]) / old[key]] for key in sorted(old)]


def write_csv(path, header, rows):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = args.run_root.resolve()
    out = args.output.resolve()
    logs = {
        "adapter": runs / "adapter/sram/run.log",
        "macro_functional": runs / "macro_functional/sram/run.log",
        "engine": runs / "check/engine/run.log",
        "baseline_engine": runs / "baseline/baseline_engine/run.log",
        "profile": runs / "profile_wired/run.log",
        "synthesis_define_vcs": runs / "synthesis_define/run.log",
    }
    markers = {"adapter": "QBS SRAM adapter PASS cases=81 strobe_masks=65536",
               "macro_functional": "QBS SRAM adapter PASS cases=81 strobe_masks=65536",
               "profile": "QBS profile engine PASS: 448 cases"}
    texts = {key: completed(path, markers.get(key, "QBS engine PASS: 33 functional cases plus four fault classes"))
             for key, path in logs.items()}
    engine_rows = compare_cases(texts["baseline_engine"], texts["engine"])
    assert len(engine_rows) == 33
    real_rows = []
    input_hashes = {}
    for name in NAMES:
        base = runs / "baseline_real" / f"{name}.log"
        candidate = runs / "real" / f"{name}.log"
        bt = completed(base, "QBS engine PASS: 1 functional cases")
        ct = completed(candidate, "QBS engine PASS: 1 functional cases")
        comparison, = compare_cases(bt, ct)
        traffic_old = TRAFFIC.search(bt)
        traffic_new = TRAFFIC.search(ct)
        if not traffic_old or not traffic_new or traffic_old.groups() != traffic_new.groups():
            raise ValueError(f"traffic differs: {name}")
        real_rows.append([name] + comparison[1:] + list(traffic_new.groups()))
        vector = runs / "real" / f"{name}.vectors"
        baseline_vector = runs / "baseline_real" / f"{name}.vectors"
        if baseline_vector.exists() and sha(vector) != sha(baseline_vector):
            raise ValueError(f"input vector differs: {name}")
        input_hashes[name] = sha(vector)
        logs[f"baseline_{name}"] = base
        logs[name] = candidate
    handoff = json.loads((args.handoff / "status.json").read_text())
    assert handoff["status"] == "PASS"
    for name, expected in handoff["source_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"RTL/source changed after top-level handoff: {name}")
    handoff_log = args.handoff / "handoff/latest/console.log"
    completed(handoff_log, "QBS/AKV handoff smoke: PASS traps=0")
    logs["handoff"] = handoff_log
    out.mkdir(parents=True, exist_ok=True)
    common = ["profile", "m", "n", "k_blocks", "weight_layout", "activation_layout",
              "baseline_cycles", "sram_cycles", "delta_cycles", "delta_percent"]
    write_csv(out / "engine_cycles.csv", ["case"] + common, engine_rows)
    write_csv(out / "real_cycles.csv", ["case"] + common +
              ["weight_bytes", "activation_bytes", "payload_bytes", "ranges", "dot_cycles", "prefetch_wait_cycles"], real_rows)
    evidence = {}
    for name, path in logs.items():
        target = out / f"{name}.log"
        shutil.copyfile(path, target)
        evidence[name] = {"path": str(path), "sha256": sha(path)}
    for bank in (0, 4):
        path = runs / "real" / f"sram_adapter_{bank}.csv"
        shutil.copyfile(path, out / path.name)
    summary = {
        "baseline_commit": subprocess.check_output(["git", "rev-parse", "be1487b5"], cwd=ROOT, text=True).strip(),
        "status": "PASS", "scope": "functional storage candidate, not a PPA result",
        "sram_logical_bytes": 3584, "tsmc_macro_count": 24, "tsmc_macro_capacity_bytes": 6144,
        "pending_register_bits": 634, "new_dot_pipeline_stages": 0,
        "dc_run": False, "physical_timing_validated": False,
        "macro_functional_timing_checks": "disabled: +notimingcheck (zero-delay RTL)",
        "engine_cases": len(engine_rows), "engine_unchanged_cases": sum(row[-2] == 0 for row in engine_rows),
        "engine_max_cycle_increase_percent": max(row[-1] for row in engine_rows),
        "real_cases": len(real_rows), "real_traffic_and_dot_unchanged": True,
        "real_max_cycle_increase_percent": max(row[10] for row in real_rows),
        "input_vector_sha256": input_hashes,
        "top_level": {key: handoff[key] for key in ("status", "scope", "started_at", "finished_at", "simv_sha256", "source_sha256")},
        "evidence": evidence,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS: {len(engine_rows)} engine cases, {len(real_rows)} real slices; wrote {out}")


if __name__ == "__main__":
    main()
