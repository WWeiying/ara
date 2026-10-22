#!/usr/bin/env python3
"""Merge only passing Verilator runs from the same instrumented image."""

import argparse
import json
import subprocess
from pathlib import Path

from audit_merged import audit as audit_previous
from run_verilator_coverage import (SUCCESS, sha256, summarize_lcov, summarize_raw,
                                    write_uncovered_raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, action="append", required=True,
                        help="result.json from a new passing coverage case")
    parser.add_argument("--extend-audit", type=Path,
                        help="audited prior merge; reuse its cases on the same image")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verilator-coverage", type=Path, required=True)
    parser.add_argument("--report-timeout", type=int, default=120,
                        help="timeout in seconds for each coverage report command")
    parser.add_argument("--include-path", action="append", default=[],
                        help="source-path substring for a scoped count")
    parser.add_argument("--hierarchy-prefix", default="",
                        help="DUT instance prefix in Verilator raw coverage")
    args = parser.parse_args()
    if args.report_timeout < 1:
        parser.error("report timeout must be positive")
    case_paths = []
    if args.extend_audit:
        previous_path = args.extend_audit.resolve()
        previous_check = audit_previous(previous_path)
        if previous_check["status"] != "PASS":
            parser.error(f"prior merge audit failed: {previous_check['issues']}")
        previous = json.loads(previous_path.read_text())
        previous_prefix = previous["hierarchy_coverage"]["hierarchy_prefix"]
        previous_includes = previous["include_paths"]
        if args.hierarchy_prefix and args.hierarchy_prefix != previous_prefix:
            parser.error("hierarchy scope differs from prior merge")
        if args.include_path and args.include_path != previous_includes:
            parser.error("source scope differs from prior merge")
        args.hierarchy_prefix = previous_prefix
        args.include_path = previous_includes
        case_paths.extend(Path(case["result"]) for case in previous["cases"])
    case_paths.extend(args.case)
    resolved = [path.resolve() for path in case_paths]
    if len(set(resolved)) != len(resolved):
        parser.error("duplicate coverage case in merge")
    cases = []
    image_hashes = set()
    for path in resolved:
        result = json.loads(path.read_text())
        if result.get("status") != "PASS":
            parser.error(f"case did not pass: {path}")
        if (result.get("sim_returncode") != 0 or
                result.get("report_returncode") != 0 or
                result.get("self_check_pass") is not True):
            parser.error(f"case lacks successful simulation/report evidence: {path}")
        for key, hash_key in (("simv", "simv_sha256"),
                              ("elf", "elf_sha256")):
            source = Path(result.get(key, ""))
            if not source.is_file() or sha256(source) != result.get(hash_key):
                parser.error(f"{key} is missing or changed: {path}")
        for name, hash_key in (("sim.log", "sim_log_sha256"),
                               ("coverage.dat", "coverage_sha256"),
                               ("coverage.info", "coverage_info_sha256")):
            source = path.parent / name
            if not source.is_file() or sha256(source) != result.get(hash_key):
                parser.error(f"{name} is missing or changed: {path}")
        with (path.parent / "sim.log").open(errors="replace") as log:
            success_marker = any(SUCCESS.search(line) for line in log)
        if not success_marker:
            parser.error(f"sim.log lacks Ara success marker: {path}")
        data = path.parent / "coverage.dat"
        if data.stat().st_size == 0:
            parser.error(f"missing coverage.dat: {path}")
        image_hashes.add(result["simv_sha256"])
        cases.append({"result": str(path.resolve()), "result_sha256": sha256(path),
                      "coverage": str(data.resolve()), "coverage_sha256": sha256(data)})
    if len(image_hashes) != 1:
        parser.error("coverage cases use different Verilator images")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    reporter = args.verilator_coverage.resolve(strict=True)
    merged = output / "merged.dat"
    info = output / "merged.info"
    commands = [[str(reporter), "--write", str(merged),
                 *(case["coverage"] for case in cases)],
                [str(reporter), "--write-info", str(info), str(merged)]]
    for command in commands:
        report = subprocess.run(command, cwd=output, capture_output=True,
                                text=True, timeout=args.report_timeout, check=False)
        if report.returncode != 0:
            raise RuntimeError(f"report failed: {command}: {report.stdout}{report.stderr}")
    if not merged.is_file() or not info.is_file() or info.stat().st_size == 0:
        raise RuntimeError("Verilator did not produce a nonempty merged report")
    hierarchy_coverage = summarize_raw(merged, args.hierarchy_prefix)
    if args.hierarchy_prefix and hierarchy_coverage["points_total"] == 0:
        raise RuntimeError(f"no coverage points matched {args.hierarchy_prefix}")
    uncovered = output / "uncovered.jsonl"
    scoped_raw = write_uncovered_raw(merged, uncovered, args.hierarchy_prefix,
                                    args.include_path)
    if scoped_raw["points_total"] == 0:
        raise RuntimeError("no raw coverage points matched the requested DUT/source scope")
    audit = {
        "status": "PASS",
        "simv_sha256": next(iter(image_hashes)),
        "cases": cases,
        "merged_sha256": sha256(merged),
        "merged_info_sha256": sha256(info),
        "hierarchy_coverage": hierarchy_coverage,
        "scoped_raw_coverage": scoped_raw,
        "uncovered_points": str(uncovered),
        "uncovered_sha256": sha256(uncovered),
        "raw_coverage": summarize_lcov(info),
        "include_paths": args.include_path,
        "scoped_coverage": summarize_lcov(info, args.include_path)
        if args.include_path else None,
        "scope_note": "Hierarchy points exclude other instances; uncovered points still need review",
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"PASS: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
