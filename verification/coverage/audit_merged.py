#!/usr/bin/env python3
"""Re-audit frozen Verilator coverage artifacts without rerunning simulation."""

import argparse
import json
import tempfile
from pathlib import Path

from run_verilator_coverage import (SUCCESS, sha256, summarize_lcov,
                                    summarize_raw, write_uncovered_raw)


def audit(audit_path: Path, minimum_cases: int = 1) -> dict:
    audit_path = audit_path.resolve()
    root = audit_path.parent
    issues = []
    try:
        record = json.loads(audit_path.read_text())
        if record.get("status") != "PASS":
            issues.append("merge report is not PASS")
        merged = root / "merged.dat"
        info = root / "merged.info"
        uncovered = root / "uncovered.jsonl"
        for path, key in ((merged, "merged_sha256"),
                          (info, "merged_info_sha256"),
                          (uncovered, "uncovered_sha256")):
            if not path.is_file() or sha256(path) != record.get(key):
                issues.append(f"missing or changed merge artifact: {path.name}")
        if record.get("uncovered_points") != str(uncovered):
            issues.append("uncovered-point path differs from frozen merge output")

        cases = record.get("cases", [])
        if not isinstance(cases, list) or len(cases) < minimum_cases:
            issues.append("too few passing cases in merged report")
            cases = []
        images = set()
        for item in cases:
            result_path = Path(item["result"])
            data = Path(item["coverage"])
            if (not result_path.is_file() or
                    sha256(result_path) != item.get("result_sha256")):
                issues.append(f"missing or changed case result: {result_path}")
                continue
            result = json.loads(result_path.read_text())
            if (result.get("status") != "PASS" or
                    result.get("sim_returncode") != 0 or
                    result.get("report_returncode") != 0 or
                    result.get("self_check_pass") is not True):
                issues.append(f"case is not a passing instrumented run: {result_path}")
            if (not data.is_file() or
                    sha256(data) != item.get("coverage_sha256") or
                    result.get("coverage_sha256") != item.get("coverage_sha256")):
                issues.append(f"missing or changed case coverage: {data}")
            for key, hash_key in (("simv", "simv_sha256"), ("elf", "elf_sha256")):
                path = Path(result.get(key, ""))
                if not path.is_file() or sha256(path) != result.get(hash_key):
                    issues.append(f"missing or changed {key}: {result_path}")
            for name, hash_key in (("sim.log", "sim_log_sha256"),
                                   ("coverage.info", "coverage_info_sha256")):
                path = result_path.parent / name
                if not path.is_file() or sha256(path) != result.get(hash_key):
                    issues.append(f"missing or changed {name}: {result_path}")
            log = result_path.parent / "sim.log"
            if log.is_file():
                with log.open(errors="replace") as stream:
                    if not any(SUCCESS.search(line) for line in stream):
                        issues.append(f"Ara success marker missing: {log}")
            images.add(result.get("simv_sha256"))
        if images != {record.get("simv_sha256")}:
            issues.append("case simulator images differ from merge identity")

        hierarchy = record.get("hierarchy_coverage", {}).get("hierarchy_prefix")
        includes = record.get("include_paths", [])
        if not hierarchy or not isinstance(includes, list) or not includes:
            issues.append("DUT hierarchy/source scope is missing")
        if merged.is_file() and info.is_file():
            raw = summarize_raw(merged, hierarchy or "")
            if raw != record.get("hierarchy_coverage") or raw["points_total"] == 0:
                issues.append("DUT hierarchy counts differ from merged data")
            if summarize_lcov(info) != record.get("raw_coverage"):
                issues.append("raw LCOV counts differ from merged report")
            if (includes and summarize_lcov(info, includes) !=
                    record.get("scoped_coverage")):
                issues.append("source-scoped LCOV counts differ from merged report")
            with tempfile.TemporaryDirectory() as directory:
                rechecked = Path(directory) / "uncovered.jsonl"
                scoped = write_uncovered_raw(merged, rechecked, hierarchy or "",
                                             includes)
                if (scoped != record.get("scoped_raw_coverage") or
                        scoped["points_total"] == 0 or
                        sha256(rechecked) != record.get("uncovered_sha256")):
                    issues.append("DUT/source counts or missed-point list differ")
    except (OSError, ValueError, KeyError, TypeError) as error:
        issues.append(str(error))
        record = {}
        cases = []
    return {"status": "PASS" if not issues else "FAIL", "issues": issues,
            "scope": "collection integrity only; uncovered points still require review",
            "merge_audit": str(audit_path),
            "merge_audit_sha256": sha256(audit_path) if audit_path.is_file() else None,
            "case_count": len(cases),
            "simv_sha256": record.get("simv_sha256")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--minimum-cases", type=int, default=1)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.minimum_cases < 1:
        parser.error("minimum-cases must be positive")
    result = audit(args.audit, args.minimum_cases)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
