#!/usr/bin/env python3
"""Wait once on a real owner, then exec an independent audit without rerunning VCS."""
import argparse
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from run_common_attention import checked_build, s, HERE, ROOT
sys.path.insert(0, str(ROOT / 'verification/akv'))
from run_after_verified_gate import wait_owner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'output', 'control'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--owner-pid', type=int, required=True)
    args = parser.parse_args()
    run = args.run.resolve(strict=True)
    out, control = args.output.resolve(), args.control.resolve()
    status = s.read_json(run / 'status.json')
    s.require(not out.exists() and not control.exists() and not out.is_relative_to(run) and
              not control.is_relative_to(run) and not out.is_relative_to(control) and
              not control.is_relative_to(out), 'Fresh independent outputs required')
    for path in (status['build'], status['prerequisite']):
        s.require(not out.is_relative_to(Path(path).resolve()) and not control.is_relative_to(Path(path).resolve()),
                  'Do not place audit outputs inside sealed inputs')
    control.mkdir(parents=True, exist_ok=False)
    try:
        s.require(status.get('pid') == args.owner_pid, 'Wrong VCS owner')
        _, pins = checked_build(Path(status['build']))
        s.merge_pins(pins, s.read_json(run / 'source-pins.json'))
        files = [Path(__file__), HERE / 'audit_common_attention.py', HERE / 'common_variant.py',
                 HERE / 'test_common_variant.py', HERE / 'test_audit_common_attention.py',
                 HERE / 'test_queue_common_audit.py', ROOT / 'verification/akv/run_after_verified_gate.py',
                 run / 'source-pins.json']
        s.merge_pins(pins, s.hashes(files))
        s.verify_pins(pins)
        s.atomic_json(control / 'source-pins.json', pins)
        receipt = s.digest(control / 'source-pins.json')
        s.atomic_json(control / 'status.json', dict(state='WAITING_OWNER', owner_pid=args.owner_pid,
                      run=str(run), audit=str(out), source_pins_sha256=receipt))
        wait_owner(run, args.owner_pid, HERE / 'run_common_attention.py', 14400)
        s.require(s.digest(control / 'source-pins.json') == receipt, 'Audit queue receipt drift')
        s.verify_pins(pins)
        s.atomic_json(control / 'status.json', dict(state='AUDIT_DISPATCHED', owner_pid=args.owner_pid,
                      run=str(run), audit=str(out), source_pins_sha256=receipt, current_inputs_match=True))
        os.execv(sys.executable, [sys.executable, '-B', str(HERE / 'audit_common_attention.py'),
                                 '--run', str(run), '--output', str(out)])
    except BaseException as exc:
        s.atomic_json(control / 'status.json', dict(state='PREREQUISITE_NOT_ACCEPTED', owner_pid=args.owner_pid,
                      run=str(run), error=repr(exc)))
        raise


if __name__ == '__main__': main()
