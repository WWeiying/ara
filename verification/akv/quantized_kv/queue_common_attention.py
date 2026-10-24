#!/usr/bin/env python3
"""Pin a successor, wait on its real predecessor owner, then exec it directly."""
import argparse
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv'))
from run_after_verified_gate import wait_owner
from run_common_attention import checked_build,s


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('build','prerequisite','output','control'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--owner-pid',type=int,required=True)
    parser.add_argument('--wait-timeout',type=int,default=10800)
    args=parser.parse_args()
    build,prior=args.build.resolve(strict=True),args.prerequisite.resolve(strict=True)
    out,control=args.output.resolve(),args.control.resolve()
    s.require(1<=args.wait_timeout<=10800 and not out.exists() and
        not control.is_relative_to(prior) and not control.is_relative_to(build) and
        not out.is_relative_to(control) and not control.is_relative_to(out) and
        not out.is_relative_to(prior) and not out.is_relative_to(build),'Independent fresh paths/bound required')
    control.mkdir(parents=True,exist_ok=False)
    try:
        _,pins=checked_build(build)
        s.merge_pins(pins,s.read_json(prior/'source-pins.json'))
        files=[Path(__file__),HERE/'run_common_attention.py',HERE/'test_common_attention_run.py',
            HERE/'audit_attention.py',HERE/'check_common_attention.py',HERE/'test_common_attention.py',
            HERE/'test_queue_common_attention.py',prior/'source-pins.json',
            ROOT/'verification/akv/run_after_verified_gate.py']
        s.merge_pins(pins,s.hashes(files)); s.verify_pins(pins)
        s.atomic_json(control/'source-pins.json',pins); receipt=s.digest(control/'source-pins.json')
        s.atomic_json(control/'status.json',dict(state='WAITING_OWNER',owner_pid=args.owner_pid,
            prerequisite=str(prior),output=str(out),source_pins_sha256=receipt))
        wait_owner(prior,args.owner_pid,HERE/'run_attention.py',args.wait_timeout)
        s.require(s.digest(control/'source-pins.json')==receipt,'Queue receipt drift'); s.verify_pins(pins)
        s.atomic_json(control/'status.json',dict(state='DISPATCHED',owner_pid=args.owner_pid,
            prerequisite=str(prior),output=str(out),source_pins_sha256=receipt,post_pins_match=True))
        # exec preserves the transient service as the direct worker owner.
        os.execv(sys.executable,[sys.executable,'-B',str(HERE/'run_common_attention.py'),
            '--build',str(build),'--prerequisite',str(prior),'--output',str(out),'--timeout','10800'])
    except BaseException as exc:
        s.atomic_json(control/'status.json',dict(state='FAIL',error=repr(exc),prerequisite=str(prior),output=str(out)))
        raise


if __name__=='__main__': main()
