#!/usr/bin/env python3
"""Supplemental 94+107 points / 10 observers report; explicit review before run."""
import argparse
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "reviewed_csr_20261004"))
import workflow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Read-only latest-corpus and raw-bit admission; no DVE")
    check.add_argument("--baseline", type=Path)
    prepare = commands.add_parser("prepare", help="Create an independent snapshot for review; no DVE")
    prepare.add_argument("output", type=Path)
    prepare.add_argument("--baseline", type=Path)
    run = commands.add_parser("run", help="One bounded supplemental report AFTER independent approval")
    run.add_argument("output", type=Path)
    run.add_argument("--approval", type=Path, required=True)
    run.add_argument("--approval-sha256", required=True)
    args = parser.parse_args(argv)

    def expired(signum, frame):
        raise TimeoutError("Supplemental wrapper exceeded its 170-second work budget (cleanup reserved)")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(170)
    try:
        return workflow.dispatch(args)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TimeoutError) as error:
        print("REJECTED: " + str(error), file=sys.stderr)
        raise SystemExit(1)
