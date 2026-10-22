#!/usr/bin/env python3
"""Review-gated supplemental old94+CSR107+operand1144 path. No automatic run."""
import argparse
import json
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "reviewed_operand_20261004"))
import operand_guard as guard
import operand_workflow as workflow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Read-only admission, no DVE")
    check.add_argument("--baseline", type=Path)
    prepare = commands.add_parser("prepare", help="Prepare immutable snapshot; never launches DVE")
    prepare.add_argument("output", type=Path)
    prepare.add_argument("--stage", choices=("capture", "report"), required=True)
    prepare.add_argument("--baseline", type=Path)
    prepare.add_argument("--capture", type=Path)
    prepare.add_argument("--capture-sha256")
    run = commands.add_parser("run", help="One session ONLY after independent receipt review")
    run.add_argument("output", type=Path)
    run.add_argument("--approval", type=Path, required=True)
    run.add_argument("--approval-sha256", required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        result = workflow.run(args.output, args.approval, args.approval_sha256)
    else:
        def expired(signum, frame):
            raise TimeoutError("Offline prepare/admission budget exhausted; no retry")
        old_handler = signal.signal(signal.SIGALRM, expired)
        signal.alarm(workflow.PREPARE_MAX_SECONDS)
        try:
            context = guard.build_context(args.baseline)
            result = dict(status="OFFLINE_ADMITTED_NOT_AUTHORIZED", tests=context["tests"], old_points=94, csr_points=107,
                          operand_points=1144, observers=10, retained_review_coordinates=1269,
                          retained_current_missing=context["retained_current_missing_count"], corpus=context["baseline"],
                          elapsed_seconds=context["admission_elapsed_seconds"], native_full1144_qualified=False, DVE_launches=0)
            if args.command == "prepare":
                bundle = workflow.snapshot(args.output, context, args.stage, args.capture, args.capture_sha256)
                result.update(snapshot=str(bundle), snapshot_sha256=guard.sha(bundle / "snapshot.json"))
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TimeoutError) as error:
        print("REJECTED: " + str(error), file=sys.stderr)
        raise SystemExit(1)
