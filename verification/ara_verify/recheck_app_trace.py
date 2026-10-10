"""Recheck completed application traces after a trace-checker correction."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .artifacts import sha256, simulation_image
from .runner import FAIL_RE, SUCCESS_RE
from .trace import validate_trace


def recheck(summary: Path) -> dict:
    original = json.loads(summary.read_text(encoding="utf-8"))
    image_cache: dict[Path, dict[str, str]] = {}
    cases = []
    for row in original:
        case = {"name": row["name"], "original_status": row["status"]}
        trace_failure = row["status"] == "FAIL" and row.get("reason", "").startswith(
            "invalid commit trace:"
        )
        if row["status"] != "PASS" and not trace_failure:
            case["recheck_status"] = "UNCHANGED"
            cases.append(case)
            continue

        artifact = Path(row["artifact_dir"])
        issues = []
        try:
            inputs = json.loads((artifact / "inputs.json").read_text(encoding="utf-8"))
            elf = artifact / "input.elf"
            if inputs["binary"]["path"] != str(elf) or sha256(elf) != inputs["binary"]["sha256"]:
                issues.append("frozen ELF identity mismatch")
            simv = Path(inputs["simv"]["path"])
            if simv not in image_cache:
                image_cache[simv] = simulation_image(simv)
            if image_cache[simv] != inputs["simv"]["image_sha256"]:
                issues.append("VCS image identity mismatch")
            text = (artifact / "console.log").read_text(encoding="utf-8", errors="replace")
            run_log = artifact / "work" / "run.vcs.log"
            if run_log.is_file():
                text += "\n" + run_log.read_text(encoding="utf-8", errors="replace")
            if FAIL_RE.search(text) or not SUCCESS_RE.search(text):
                issues.append("program self-check did not pass cleanly")
            if row["returncode"] != 0:
                issues.append("simulator exit code is not zero")
            trace = validate_trace(artifact / "commit_trace.csv")
            case["trace"] = trace
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append(f"recheck could not validate evidence: {error}")
        if issues:
            case["recheck_status"] = "FAIL"
        elif trace_failure:
            case["recheck_status"] = "PASS_AFTER_CHECKER_FIX"
        else:
            case["recheck_status"] = "RECONFIRMED_PASS"
        case["issues"] = issues
        cases.append(case)

    counts = Counter(case["recheck_status"] for case in cases)
    return {
        "source_summary": str(summary.resolve()),
        "source_summary_sha256": sha256(summary),
        "original_counts": dict(Counter(row["status"] for row in original)),
        "recheck_counts": dict(counts),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = recheck(args.summary)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"original": report["original_counts"], "recheck": report["recheck_counts"]}))
    return 1 if report["recheck_counts"].get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
