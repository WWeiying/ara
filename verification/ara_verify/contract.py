"""Check a real-DUT Ara accelerator contract monitor log."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_SUMMARY_MARKER = "[ARA_CONTRACT]"
_SUMMARY_RE = re.compile(
    r"\[ARA_CONTRACT\] requests=(?P<requests>[0-9]+) "
    r"responses=(?P<responses>[0-9]+) "
    r"exceptions=(?P<exceptions>[0-9]+) "
    r"mmu_request_cycles=(?P<mmu_request_cycles>[0-9]+) "
    r"protocol_errors=(?P<protocol_errors>[0-9]+) "
    r"outstanding=(?P<outstanding>[0-9]+) "
    r"req_stalled=(?P<req_stalled>[0-9]+) "
    r"resp_stalled=(?P<resp_stalled>[0-9]+)"
)
_VCS_ERROR_RE = re.compile(r"\b(?:Error:|Fatal:|Error-\[|Fatal-\[)")
_UVM_ERROR_RE = re.compile(r"\b(?:UVM_ERROR|UVM_FATAL)\b")
_UVM_ZERO_RE = re.compile(r"(?:UVM_ERROR|UVM_FATAL)[ \t]*:[ \t]*0+")
_CORE_SUCCESS_RE = re.compile(r"\bCore Test \*\*\* SUCCESS\b")
_CORE_FAILURE_RE = re.compile(r"\bCore Test \*\*\* FAILED\b")


def parse_contract_summary(line: str) -> dict[str, int] | None:
    """Parse one complete record, without accepting malformed/unknown values."""
    match = _SUMMARY_RE.fullmatch(line.strip())
    if match is None:
        return None
    try:
        return {name: int(value) for name, value in match.groupdict().items()}
    except ValueError:
        return None


def check_contract_log(
    path: str | Path, require_core_success: bool = True
) -> list[str]:
    """Return gate failures; exception/MMU counts are informational, not errors."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"cannot read contract log {path}: {error}"]

    issues: list[str] = []
    summary_count = 0
    core_success = False
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        location = f"line {line_number}"
        if _SUMMARY_MARKER in line:
            # Count malformed records too, so a later valid one cannot mask them.
            summary_count += line.count(_SUMMARY_MARKER)
            counts = parse_contract_summary(line)
            if counts is None:
                issues.append(f"{location}: malformed {_SUMMARY_MARKER} summary")
            else:
                for name in ("requests", "responses"):
                    if counts[name] == 0:
                        issues.append(f"{location}: {name} must be nonzero")
                if counts["requests"] != counts["responses"]:
                    issues.append(
                        f"{location}: requests={counts['requests']} and "
                        f"responses={counts['responses']} must be equal"
                    )
                for name in ("protocol_errors", "outstanding", "req_stalled", "resp_stalled"):
                    if counts[name] != 0:
                        issues.append(f"{location}: {name}={counts[name]} must be zero")

        # Diagnostics are independent evidence, even if final counters are zero.
        if "[ARA_CONTRACT_ERROR]" in line:
            issues.append(f"{location}: contract diagnostic: {line}")
        if _VCS_ERROR_RE.search(line):
            issues.append(f"{location}: simulator diagnostic: {line}")
        if _UVM_ERROR_RE.search(line) and not _UVM_ZERO_RE.fullmatch(line):
            issues.append(f"{location}: UVM diagnostic: {line}")
        if _CORE_FAILURE_RE.search(line):
            issues.append(f"{location}: Core Test failure: {line}")
        if _CORE_SUCCESS_RE.search(line):
            core_success = True

    if summary_count != 1:
        issues.append(f"expected exactly one {_SUMMARY_MARKER} summary, found {summary_count}")
    if require_core_success and not core_success:
        issues.append("missing Core Test *** SUCCESS marker")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="simulator console log")
    parser.add_argument(
        "--no-core-success",
        action="store_false",
        dest="require_core_success",
        help="skip the Core Test success requirement for monitor-only tests",
    )
    args = parser.parse_args(argv)
    issues = check_contract_log(args.log, require_core_success=args.require_core_success)
    if issues:
        for issue in issues:
            print(f"FAIL: {issue}", file=sys.stderr)
        return 1
    print(f"PASS: Ara contract log: {args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
