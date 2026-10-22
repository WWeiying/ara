#!/usr/bin/env python3
"""Merge frozen coverage samples for exploration, never as correctness signoff."""
import argparse
import json
from pathlib import Path
import subprocess

from run_verilator_coverage import sha256, summarize_raw, write_uncovered_raw


def validate_sample(path):
    result = json.loads(path.read_text())
    for key, digest in (("simv", "simv_sha256"), ("elf", "elf_sha256")):
        file = Path(result[key])
        if not file.is_file() or sha256(file) != result.get(digest):
            raise ValueError(f"changed/missing {key}: {path}")
    for name, digest in (("coverage.dat", "coverage_sha256"), ("sim.log", "sim_log_sha256")):
        file = path.parent / name
        if not file.is_file() or sha256(file) != result.get(digest):
            raise ValueError(f"changed/missing {name}: {path}")
    data = path.parent / "coverage.dat"
    if summarize_raw(data)["points_total"] == 0:
        raise ValueError(f"no parseable coverage points: {path}")
    return {"result": str(path), "result_sha256": sha256(path),
            "coverage": str(data), "coverage_sha256": sha256(data),
            "image_sha256": result["simv_sha256"],
            "simulation_status": result.get("status", "UNKNOWN"),
            "self_check_pass": result.get("self_check_pass", False)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verilator-coverage", type=Path, required=True)
    parser.add_argument("--hierarchy-prefix", default="")
    parser.add_argument("--include-path", action="append", default=[])
    args = parser.parse_args()
    paths = [p.resolve(strict=True) for p in args.case]
    if len(set(paths)) != len(paths):
        parser.error("duplicate sample")
    samples = [validate_sample(p) for p in paths]
    hashes = {s["image_sha256"] for s in samples}
    if len(hashes) != 1:
        parser.error("cannot merge different instrumented images")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reporter = args.verilator_coverage.resolve(strict=True)
    merged = out / "exploration.dat"
    command = [str(reporter), "--write", str(merged), *(s["coverage"] for s in samples)]
    with (out / "merge.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    scoped = write_uncovered_raw(merged, out / "uncovered.jsonl",
                                 args.hierarchy_prefix, args.include_path)
    if not scoped["points_total"]:
        raise ValueError("empty requested scope")
    report = {"status": "COLLECTED", "purpose": "EXPLORATION_ONLY_NOT_CORRECTNESS_SIGNOFF",
              "includes_failed_samples": any(s["simulation_status"] != "PASS" for s in samples),
              "image_sha256": next(iter(hashes)), "samples": samples,
              "hierarchy_prefix": args.hierarchy_prefix, "include_paths": args.include_path,
              "scoped_raw_coverage": scoped, "merged_sha256": sha256(merged),
              "note": "Failed-prefix activity is coverage evidence, not verified functionality. "
                      "Use the independent PASS-only collection for correctness-backed coverage."}
    (out / "exploration.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"COLLECTED (exploration only): {out}")


if __name__ == "__main__":
    main()
