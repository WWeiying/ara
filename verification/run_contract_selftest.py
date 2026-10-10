#!/usr/bin/env python3
"""Run the monitor's positive and negative controls, not DUT verification."""

import argparse
from pathlib import Path
import subprocess

from ara_verify.contract import check_contract_log, parse_contract_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("simv", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = {
        "legal": True,
        "reset": True,
        "duplicate": False,
        "orphan": False,
        "request_drop": False,
        "response_drop": False,
        "request_payload": False,
        "request_frm": False,
        "response_payload": False,
        "exception_payload": False,
        "unknown": False,
        "error_then_reset": False,
        "incomplete": False,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    failed = []
    for case, should_accept in cases.items():
        log = (args.output / f"{case}.log").resolve()
        # A failed launch must not reuse a previous run's successful selftest.
        log.unlink(missing_ok=True)
        result = subprocess.run(
            [str(args.simv.resolve()), f"+CASE={case}",
             "+ARA_CONTRACT_TRACE_LIMIT=64", "-l", str(log)],
            cwd=args.output, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=30, check=False,
        )
        text = log.read_text() if log.is_file() else result.stdout
        issues = check_contract_log(log, require_core_success=False) if log.is_file() else ["no log"]
        summaries = [line for line in text.splitlines() if "[ARA_CONTRACT]" in line]
        counts = parse_contract_summary(summaries[0]) if len(summaries) == 1 else None
        expected_errors = 0 if case in ("legal", "reset", "incomplete") else 1
        valid = (f"[SELFTEST_PASS] case={case} " in text
                 and log.is_file() and counts is not None
                 and counts["protocol_errors"] == expected_errors
                 and "Fatal:" not in text and "Fatal-[" not in text
                 and (not issues) == should_accept
                 and result.returncode in (0, 1)
                 and (not should_accept or result.returncode == 0))
        print(f"{'PASS' if valid else 'FAIL'} {case}: "
              f"{'accepted' if not issues else 'rejected'} by log gate")
        if not valid:
            print(text[-6000:])
            failed.append(case)
    print(f"contract selftest: {len(cases) - len(failed)}/{len(cases)} passed")
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
