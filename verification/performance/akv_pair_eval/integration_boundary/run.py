#!/usr/bin/env python3
"""Sealed area-image runner with only the checker loader replaced; never builds an image."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('integration_boundary_run_check', HERE / 'check.py')
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)
b = checker.b


def load_checker(kind):
    b.require(kind == 'boundary', 'Only functional boundary kind is permitted')
    return HERE / 'check.py', checker


def private_owner():
    owner = b.load(b.PARENT / 'run.py', 'integration_boundary_private_owner', b.SEALED['run.py'])
    owner.load_checker = load_checker
    return owner


def run(args, *, seal_ready=False):
    b.require(seal_ready is True, 'Owner seal-ready is required before any VCS launch/preflight')
    b.require(args.kind == 'boundary', 'Functional boundary kind required')
    checker.verify_build(args.build)
    return private_owner().run(args)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, default=b.OUT / 'chain_soc_admitted_20261107_01')
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kind', choices=('boundary',), default='boundary')
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--seal-ready', action='store_true')
    def interrupted(sig, _frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    a = parser.parse_args()
    run(a, seal_ready=a.seal_ready)
