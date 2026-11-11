#!/usr/bin/env python3
"""Same numerical checks and exact QBS trap contract, bound to the V10 copy."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
QBS_CHECK_SHA = '93b1d5b1ef5116390d7f384ecb05e1f2ce94adefa01ad9c140a58d19309e536a'
if hashlib.sha256((HERE / 'check_v2.py').read_bytes()).hexdigest() != QBS_CHECK_SHA:
    raise ValueError('Sealed exact QBS checker drift')
spec = importlib.util.spec_from_file_location('execution_v3_exact_qbs', HERE / 'check_v2.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
c = q.c
SOURCE = c.OUT / 'stage5_qemu_prepare_variant_20261110_04/qemu-10.2.0'
q.SOURCE = SOURCE


def check(kind, log, trace):
    if kind != 'qbs':
        return c.check(kind, log, trace)
    proof = q.check(log, trace)
    proof.update(qemu_source=str(SOURCE), trap_sources_sha256=q.SOURCES,
                 checker_rebind='v10-same-image-qbs')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--kind', choices=('qbs', 'perf', 'functional'), required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.kind, args.log, args.trace), indent=2, sort_keys=True))
