#!/usr/bin/env python3
"""Event-wait on a pinned live owner, then independently audit its clean PASS."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/akv'))
from run_after_verified_gate import wait_owner
from audit_live_regression import audit
import attention_run as s


def run(args):
    run, control = args.run.resolve(strict=True), args.control.resolve()
    out = args.output.resolve()
    s.require(1 <= args.wait_timeout <= 10800 and not out.exists() and
              not control.is_relative_to(run) and not out.is_relative_to(run) and
              not out.is_relative_to(control) and not control.is_relative_to(out), 'Independent fresh paths/bound required')
    control.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__), HERE/'test_audit_after_owner.py', HERE/'audit_live_regression.py',
        HERE/'test_audit_live_regression.py', HERE/'run_live_regression.py',
        HERE/'native_runtime_check.py', HERE/'f32_pv/prefill_slice_check.py',
        HERE/'attention_run.py', ROOT/'verification/akv/run_after_verified_gate.py', *s.script_files()]
    pins = s.hashes(files)
    s.atomic_json(control/'source-pins.json', pins)
    receipt = s.digest(control/'source-pins.json')
    s.atomic_json(control/'status.json', dict(state='WAITING_OWNER', owner_pid=args.owner_pid, run=str(run), output=str(out)))
    try:
        wait_owner(run, args.owner_pid, HERE/'run_live_regression.py', args.wait_timeout)
        s.require(s.digest(control/'source-pins.json') == receipt, 'Waiting audit receipt changed')
        s.verify_pins(pins)
        checked = audit(run, out)
        s.require(checked['state'] == 'CANONICAL_RTL_INDEPENDENTLY_ACCEPTED', 'Audit incomplete')
        s.verify_pins(pins)
        s.atomic_json(control/'status.json', dict(state='AUDIT_COMPLETE', owner_pid=args.owner_pid,
            run=str(run), output=str(out), audit_result_sha256=s.digest(out/'result.json'),
            source_pins_sha256=receipt, post_pins_match=True))
    except BaseException as exc:
        s.atomic_json(control/'status.json', dict(state='FAIL', error=repr(exc), run=str(run), output=str(out)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'output', 'control'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--owner-pid', type=int, required=True)
    parser.add_argument('--wait-timeout', type=int, default=10800)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
