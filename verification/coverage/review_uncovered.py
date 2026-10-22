#!/usr/bin/env python3
"""Rank DUT coverage gaps from an integrity-checked Verilator merge."""

import argparse
import json
from collections import Counter
from pathlib import Path

from audit_merged import audit
from run_verilator_coverage import iter_raw_points, sha256


def source_line_diagnostic(raw_path: Path, hierarchy_prefix: str,
                           include_paths: list[str]) -> dict:
    lines = {}
    for properties, count in iter_raw_points(raw_path, hierarchy_prefix):
        source = properties.get("f", "")
        line = properties.get("l")
        if (properties.get("t") != "line" or line is None or
                not any(token in source for token in include_paths)):
            continue
        bucket = lines.setdefault((source, line), {"instances": 0, "hit": 0})
        bucket["instances"] += 1
        bucket["hit"] += count > 0

    by_source = {}
    for (source, _line), counts in lines.items():
        bucket = by_source.setdefault(source, {"lines_total": 0,
                                               "lines_any_hit": 0,
                                               "lines_all_instances_hit": 0})
        bucket["lines_total"] += 1
        bucket["lines_any_hit"] += counts["hit"] > 0
        bucket["lines_all_instances_hit"] += counts["hit"] == counts["instances"]
    return {
        "scope": "diagnostic unique source lines; not a replacement for instance-weighted coverage",
        "by_source": dict(sorted(by_source.items())),
    }


def review(audit_path: Path, minimum_cases: int = 1) -> dict:
    integrity = audit(audit_path, minimum_cases)
    if integrity["status"] != "PASS":
        raise ValueError("coverage merge integrity failed: " + "; ".join(integrity["issues"]))

    record = json.loads(audit_path.read_text())
    scoped = record["scoped_raw_coverage"]
    line_diagnostic = source_line_diagnostic(
        audit_path.parent / "merged.dat",
        record["hierarchy_coverage"]["hierarchy_prefix"],
        record["include_paths"],
    )
    by_source = {}
    missed = {}
    with Path(record["uncovered_points"]).open() as source:
        for line in source:
            point = json.loads(line)
            name = point["source"] or "<unknown>"
            bucket = missed.setdefault(name, {"types": Counter(), "lines": Counter()})
            bucket["types"][point["type"]] += 1
            if point["line"] is not None:
                bucket["lines"][str(point["line"])] += 1

    for name, counts in scoped["by_source"].items():
        gap = missed.get(name, {"types": Counter(), "lines": Counter()})
        total = counts["total"]
        hit = counts["hit"]
        by_source[name] = {
            "points_total": total,
            "points_hit": hit,
            "points_missed": total - hit,
            "hit_percent": round(100 * hit / total, 2) if total else None,
            "missed_by_type": dict(sorted(gap["types"].items())),
            "missed_lines": sorted(gap["lines"].items(),
                                   key=lambda item: (-item[1], int(item[0]))),
        }
    return {
        "status": "REVIEW_REQUIRED",
        "scope": "DUT hierarchy and source filters from merge; no exclusions applied",
        "merge_audit": str(audit_path.resolve()),
        "merge_audit_sha256": sha256(audit_path),
        "case_count": integrity["case_count"],
        "points_total": scoped["points_total"],
        "points_hit": scoped["points_hit"],
        "points_missed": scoped["points_total"] - scoped["points_hit"],
        "source_line_diagnostic": line_diagnostic,
        "by_source": dict(sorted(by_source.items(),
                                 key=lambda item: (-item[1]["points_missed"], item[0]))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--minimum-cases", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.minimum_cases < 1:
        parser.error("minimum-cases must be positive")
    try:
        result = review(args.audit, args.minimum_cases)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{result['points_missed']} missed of {result['points_total']} DUT points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
