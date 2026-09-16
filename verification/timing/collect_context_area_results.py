#!/usr/bin/env python3
"""Gate full-SoC synthesis on context-SRAM and QBS area-reduction regressions."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from collect_control_timing_results import compare_commands, compare_real, completed, rows
from collect_qbs_pipeline_results import command_cases

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_slice(before, after):
    old = completed(before, "QBS engine PASS: 1 functional cases")
    new = completed(after, "QBS engine PASS: 1 functional cases")
    for prefix in ("QBS end-to-end ", "QBS phase ", "QBS traffic "):
        previous = [line for line in old.splitlines() if line.startswith(prefix)]
        current = [line for line in new.splitlines() if line.startswith(prefix)]
        if len(previous) != 1 or previous != current:
            raise RuntimeError(f"real input result/cycle/counter mismatch: {after}")
    return command_cases(after)[0]


def macro_areas(library):
    records = {}
    for depth in (64, 76, 96, 128):
        name = f"ts1n28hpcpuhdsvtb{depth}x256m1swbso_170a"
        base = library / name
        lib = base / "NLDM" / f"{name}_tt0p9v25c.lib"
        matches = re.findall(r"^\s*area\s*:\s*([\d.]+)\s*;", lib.read_text(), re.M)
        if len(matches) != 1:
            raise RuntimeError(f"expected one SRAM cell area: {lib}")
        db = base / "DB" / f"{name}_tt0p9v25c.db"
        records[str(depth)] = {"area_um2": float(matches[0]),
                               "lib": str(lib), "lib_sha256": sha(lib),
                               "db": str(db), "db_sha256": sha(db)}
    old = records["64"]["area_um2"]
    savings = {name: round(count * old - new_count * records[str(depth)]["area_um2"], 6)
               for name, count, new_count, depth in (
                   ("qbs_activation_context", 4, 2, 76),
                   ("akv_context", 4, 2, 96), ("akv_v2_context", 16, 8, 128))}
    return {"corner": "TT 0.9V 25C", "macros": records,
            "macro_area_savings_um2": savings,
            "total_macro_area_savings_um2": round(sum(savings.values()), 6),
            "basis": "Liberty cell areas; not mapped whole-SoC net area"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--library", type=Path,
                        default=Path("/home/wangwy/ara/backend/library/mem"))
    args = parser.parse_args()
    run, baseline, out = args.run.resolve(), args.baseline.resolve(), args.output.resolve()
    soc = json.loads((run / "soc/status.json").read_text())
    previous = json.loads(args.baseline_summary.read_text())
    if soc["state"] != "PASS" or previous["state"] != "PASS":
        raise RuntimeError("current SoC and prior baseline must be PASS")
    tests = rows(run / "soc/results/summary.csv")
    if (len(tests) != len(soc["tests"]) or
            {r["name"] for r in tests} != set(soc["tests"]) or
            any(r["status"] != "PASS" for r in tests)):
        raise RuntimeError("incomplete SoC tests")
    for path, expected in soc["source_sha256"].items():
        if sha(ROOT / path) != expected:
            raise RuntimeError(f"source changed after SoC regression: {path}")
    changes = json.loads((run / "checks/manifest.json").read_text())
    if len(changes) != 5 or len({r["path"] for r in changes}) != 5:
        raise RuntimeError("expected five independently compared modules")
    for record in changes:
        name = record["path"]
        if (sha(run / "before" / name) != record["before_sha256"] or
                previous["source_sha256"][name] != record["before_sha256"] or
                sha(ROOT / name) != record["after_sha256"]):
            raise RuntimeError(f"old/new miter source provenance mismatch: {name}")
    markers = {
        "profile/run.log": "QBS profile engine PASS: 448 cases",
        "profile_stall/run.log": "QBS profile engine PASS: 448 cases",
        "engine/run.log": "QBS engine PASS: 33 functional cases plus four fault classes",
        "qbs_context_functional/run.log": "QBS activation context PASS: full depth, refill, alignment, backpressure",
        "akv_functional/run.log": "AKV engine PASS: v1 D64/D128 plus v2 D64/D96/D128 and segmented D256",
    }
    for path, marker in markers.items():
        completed(run / path, marker)
    for path in ("profile/run.log", "profile_stall/run.log"):
        ids = re.findall(r"^QBS RTL case (\d+) PASS", (run / path).read_text(), re.M)
        if list(map(int, ids)) != list(range(448)):
            raise RuntimeError(f"incomplete profile sweep: {path}")
    commands = compare_commands(baseline / "after/engine/run.log", run / "engine/run.log")
    slices = compare_real(baseline / "real_after/real/summary.csv", run / "real_after/summary.csv")
    inputs, logs, real = {}, {}, []
    for row in slices:
        old = baseline / "real_after/real" / row["case"]
        new = run / "real_after" / row["case"]
        result = compare_slice(old.with_suffix(".log"), new.with_suffix(".log"))
        if sha(old.with_suffix(".vectors")) != sha(new.with_suffix(".vectors")):
            raise RuntimeError(f"real capture input changed: {new}")
        inputs[str(new.with_suffix(".vectors"))] = sha(new.with_suffix(".vectors"))
        logs[str(new.with_suffix(".log"))] = sha(new.with_suffix(".log"))
        real.append({**row, "before_cycles": result["cycles"], "delta_cycles": 0})
    for profile, k in (("q4_K", 1536), ("q6_K", 8960)):
        old = baseline / "decode" / f"{profile}_after/run.log"
        new = run / "decode" / profile / "run.log"
        result = compare_slice(old, new)
        old_input, new_input = [p / "decode" / f"{profile}.vectors" for p in (baseline, run)]
        if sha(old_input) != sha(new_input):
            raise RuntimeError(f"decode capture changed: {profile}")
        inputs[str(new_input)], logs[str(new)] = sha(new_input), sha(new)
        traffic = re.search(
            r"QBS traffic case=0 weight=(\d+) activation=(\d+) payload=(\d+) "
            r"ranges=(\d+) dot=(\d+) prefetch_wait=(\d+)", new.read_text())
        if traffic is None:
            raise RuntimeError(f"decode traffic is missing: {new}")
        counters = dict(zip(("weight_bytes", "activation_bytes", "payload_bytes",
                             "ranges", "dot_cycles", "prefetch_wait_cycles"),
                            map(int, traffic.groups())))
        real.append({"case": f"{profile}_decode_m1n32", "profile": profile,
                     "m": 1, "n": 32, "k": k, "cycles": result["cycles"],
                     "before_cycles": result["cycles"], "delta_cycles": 0, **counters})
    area = macro_areas(args.library)
    if out.exists():
        archived = json.loads((out / "summary.json").read_text())
        if (archived["run"] != str(run) or archived["baseline"] != str(baseline) or
                archived["source_sha256"] != soc["source_sha256"]):
            raise RuntimeError("refusing to overwrite a different regression archive")
    out.mkdir(parents=True, exist_ok=True)
    artifacts = (*markers, "soc/results/summary.csv", "soc/focus/summary.csv",
                 "checks/manifest.json", "engine/compile.log", "profile/compile.log",
                 "qbs_context_functional/compile.log", "akv_functional/compile.log",
                 "run_decode.sh")
    for relative in artifacts:
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run / relative, target)
    for name, data in (("real.csv", real), ("commands.csv", commands)):
        fields = list(dict.fromkeys(key for row in data for key in row))
        with (out / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
    result = {"state": "PASS", "recorded_utc": datetime.now(timezone.utc).isoformat(),
              "run": str(run), "baseline": str(baseline),
              "source_sha256": soc["source_sha256"], "changes": changes,
              "input_sha256": inputs, "real_log_sha256": logs,
              "artifact_sha256": {name: sha(out / name) for name in artifacts},
              "simv_sha256": sha(run / "engine/simv"),
              "soc_tests": tests, "command_count": len(commands),
              "native_profile_cases": 448, "stalled_profile_cases": 448,
              "real_cases": real, "area": area,
              "declared_state_bits_saved": {"integer_metadata": 750,
                                             "aux_subtotals": 192, "fp_entries": 496},
              "added_architectural_latency_cycles": 0, "formal_equivalence": False,
              "macro_simulation": "vendor Verilog, +notimingcheck, cycle miters",
              "local_dc_run": False, "new_whole_soc_ppa_available": False}
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: 448+448 profiles, 33 commands, 4 SoC tests, 8 real slices; {out}")


if __name__ == "__main__":
    main()
