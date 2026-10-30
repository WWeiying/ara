#!/usr/bin/env python3
"""Successor scheduling adapter: explicit target builds and EINTR-safe pidfd wait."""
import argparse
from pathlib import Path
import selectors
import signal
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split import coordinate as original


class StopRequested(Exception):
    """Not InterruptedError: Python selectors deliberately swallow that class."""


def interrupted(sig, _frame):
    raise StopRequested(f'Signal {sig}')


def wait_all(handles, timeout, done):
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        for fd, row in handles:
            selector.register(fd, selectors.EVENT_READ, row)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Owner pidfd wait exceeded bound')
            events = selector.select(remaining)
            # An interrupted selector may return no events before the deadline.
            for key, _mask in events:
                original.terminal_pass(key.data)
                selector.unregister(key.fd)
                done(key.data)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--launch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unit-prefix', required=True)
    for kind in ('q4', 'q8'):
        parser.add_argument('--'+kind+'-build', type=Path, required=True)
        parser.add_argument('--'+kind+'-prerequisite', type=Path, default=original.ROOT /
                            f'verification/out/akv-quantkv-strided-attention-{kind}-20261024-01')
    parser.add_argument('--wait-timeout', type=int, default=10800)
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    # The immutable coordinator still owns every admission and launch gate.
    original.wait_all = wait_all
    original.run(args)


if __name__ == '__main__':
    main()
