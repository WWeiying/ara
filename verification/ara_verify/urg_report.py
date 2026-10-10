"""Validate URG report integrity without treating coverage as signed off."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import xml.etree.ElementTree as ET
from pathlib import Path


METRIC_NAMES = {
    "line": "Line",
    "cond": "Cond",
    "fsm": "FSM",
    "tgl": "Toggle",
    "branch": "Branch",
}
FATAL_LOG = re.compile(
    r"Error-\[URG-|URG-LTFF|Segmentation fault|unexpected termination",
    re.IGNORECASE,
)
REPORT_FILES = ("session.xml", "dashboard.html", "hierarchy.html",
                "modlist.html")


def audit_report(report_dir: Path, log_path: Path,
                 requested_metrics: set[str],
                 compile_vdb: Path, test_vdb: Path) -> dict[str, object]:
    issues: list[str] = []
    for name in REPORT_FILES:
        path = report_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            issues.append(f"missing or empty URG report: {name}")
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        log_text = ""
        issues.append(f"cannot read URG log: {error}")
    if FATAL_LOG.search(log_text):
        issues.append("URG log contains a fatal diagnostic")

    top_instance: str | None = None
    metrics: dict[str, dict[str, int]] = {}
    try:
        session = ET.parse(report_dir / "session.xml").getroot()
        attrs = {node.get("name"): node.get("value")
                 for node in session.findall("./info/attr")}
        top_instance = attrs.get("top_instance")
        command = shlex.split(attrs.get("command") or "")
        for vdb in (compile_vdb.resolve(), test_vdb.resolve()):
            if str(vdb) not in command:
                issues.append(f"URG command does not name VDB: {vdb}")
        for node in session.findall("./old_coverage/scope[@type='top']/metric"):
            name = node.get("name")
            value = node.get("value") or ""
            if name is None or not re.fullmatch(r"[0-9]+/[0-9]+", value):
                issues.append(f"invalid URG metric: {name}={value}")
                continue
            covered, total = (int(part) for part in value.split("/"))
            if total == 0 or covered > total:
                issues.append(f"invalid URG metric denominator: {name}={value}")
            metrics[name] = {"covered": covered, "total": total}
    except (OSError, ET.ParseError, ValueError) as error:
        issues.append(f"cannot parse URG session: {error}")
    for requested in sorted(requested_metrics):
        name = METRIC_NAMES[requested]
        if name not in metrics:
            issues.append(f"requested URG metric is missing: {name}")

    return {
        "status": "REPORT_VALID" if not issues else "INVALID",
        "issues": issues,
        "top_instance": top_instance,
        "metrics": metrics,
        "compile_vdb": str(compile_vdb.resolve()),
        "test_vdb": str(test_vdb.resolve()),
        "scope_note": "report integrity only; DUT hierarchy and coverage thresholds are not signed off",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--compile-vdb", type=Path, required=True)
    parser.add_argument("--test-vdb", type=Path, required=True)
    parser.add_argument("--metrics", required=True,
                        help="comma-separated: line,cond,fsm,tgl,branch")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requested = set(args.metrics.split(","))
    invalid = requested - METRIC_NAMES.keys()
    if invalid or not requested:
        parser.error(f"invalid metrics: {sorted(invalid)}")
    result = audit_report(args.report, args.log, requested,
                          args.compile_vdb, args.test_vdb)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"URG report integrity: {result['status']}")
    return 0 if result["status"] == "REPORT_VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
