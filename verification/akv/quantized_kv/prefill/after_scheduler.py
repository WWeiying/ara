#!/usr/bin/env python3
"""Wait on the exact scheduler worker, then conditionally exec a full-call run."""
import argparse
import json
import math
import os
from pathlib import Path
import select
import sys


def accepted_parent(result, expected_elf):
    for key in ('performance_measured', 'independent_protocol_checked', 'post_pins_match'):
        if result.get(key) is not True:
            raise ValueError('Unaccepted predecessor: ' + key)
    if result.get('state') != 'PASS' or result.get('elf_sha256') != expected_elf:
        raise ValueError('Predecessor state or ELF mismatch')
    measured = result.get('measured', {})
    if measured.get('paired_bitexact') is not True or len(measured.get('trials', [])) != 4:
        raise ValueError('Missing complete paired measurement')
    cycles = [trial.get('cycles') for trial in measured['trials']]
    if any(type(c) is not int or c <= 0 for c in cycles):
        raise ValueError('Invalid cycle measurements')
    if [t.get('shared') for t in measured['trials']] != [0, 1, 1, 0]:
        raise ValueError('Invalid ABBA order')
    ratio = (cycles[0]+cycles[3])/(cycles[1]+cycles[2])
    if not math.isclose(measured.get('speedup', 0), ratio, rel_tol=1e-12):
        raise ValueError('Inconsistent speedup')
    return ratio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-pid', type=int, required=True)
    parser.add_argument('--parent-output', type=Path, required=True)
    parser.add_argument('--parent-elf-sha256', required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    parent = args.parent_output.resolve(strict=True)
    if args.output.exists():
        raise ValueError('Output already exists')
    # pidfd pins process identity and blocks in the kernel: no repeated log or
    # result polling, and no possibility of waiting on a later reused PID.
    try:
        fd = os.pidfd_open(args.parent_pid)
    except ProcessLookupError:
        fd = None
    if fd is not None:
        try:
            try:
                argv = Path(f'/proc/{args.parent_pid}/cmdline').read_bytes().split(b'\0')
            except FileNotFoundError:
                argv = []
            if argv and (str(parent).encode() not in argv or
                         not any(x.endswith(b'/prefill/run_native.py') for x in argv)):
                raise ValueError('Unexpected predecessor process identity')
            print('WAITING_FOR_ACCEPTED_SCHEDULER pid='+str(args.parent_pid), flush=True)
            poll = select.poll()
            poll.register(fd, select.POLLIN)
            if not poll.poll(4*60*60*1000):
                raise TimeoutError('Predecessor did not exit within four hours')
        finally:
            os.close(fd)
    result = json.loads((parent/'result.json').read_text())
    ratio = accepted_parent(result, args.parent_elf_sha256)
    if ratio <= 1.05:
        print(f'NOT_PROMOTED scheduler_speedup={ratio:.9f}', flush=True)
        return
    print(f'ACCEPTED_SCHEDULER speedup={ratio:.9f}; starting whole-call measurement', flush=True)
    runner = Path(__file__).resolve().with_name('run_full_native.py')
    os.execv(sys.executable, [sys.executable, '-B', str(runner), '--build',
                            str(args.build.resolve(strict=True)), '--output',
                            str(args.output.resolve()), '--execute-reviewed'])


if __name__ == '__main__':
    main()
