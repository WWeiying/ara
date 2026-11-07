#!/usr/bin/env python3
"""Reuse the sealed owner, replacing only its private checker loader."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load_owner():
    spec = importlib.util.spec_from_file_location('auto_integration_runner_contract', HERE/'build.py')
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    contract.sealed_modules()
    owner = contract.load(HERE.parent/'run.py', 'auto_integration_sealed_owner_private')

    def load_checker(kind):
        contract.require(kind == 'qwen3_abba', 'This integration validates only primary plain Qwen3')
        path = HERE/'check.py'
        return path, contract.load(path, 'auto_integration_checker_private')

    owner.load_checker = load_checker
    return owner


def run(args):
    owner = load_owner()
    return owner.run(args)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, default=HERE.parents[3].parent/
        'ara_dsa_signoff_integration/verification/out/chain_soc_admitted_20261107_01')
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kind', choices=('qwen3_abba',), default='qwen3_abba')
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')

    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    run(parser.parse_args())
