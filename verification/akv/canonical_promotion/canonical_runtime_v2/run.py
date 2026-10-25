#!/usr/bin/env python3
"""Frozen ordinary runtime with mandatory exact-graph successor admission."""
import argparse
from pathlib import Path
import signal
import sys
from types import SimpleNamespace
import importlib.util

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('canonical_runtime_v2_build', HERE.parent / 'canonical_build_v2/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
FROZEN_SHA = '85065e8784520c5e49db1b7ed26f97930a4ac48cd110ed0c0484390deddd2f8c'
original = build.load('canonical_runtime_v2_frozen', HERE.parent / 'ordinary_runtime/run.py', FROZEN_SHA)
FILES = tuple(HERE / n for n in ('run.py', 'test_run.py', 'README.md'))
builder = SimpleNamespace(**vars(original.builder))
builder.expected_graph = build.graph.expected_graph


def build_dependencies(common):
    return list(dict.fromkeys([*original.build_dependencies(common),
                              *map(Path, build.source_inputs())]))


checked_soc = build.clone(original.checked_soc, dict(builder=builder, build_dependencies=build_dependencies))


def own_pins():
    pins = original.own_pins()
    original.s.merge_pins(pins, build.source_inputs())
    original.s.merge_pins(pins, original.s.hashes(FILES))
    return pins


run = build.clone(original.run, dict(checked_soc=checked_soc, own_pins=own_pins))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, required=True)
    parser.add_argument('--expected-soc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=9000)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    sys.exit(0 if run(args)['state'] in ('PASS', 'CANONICAL_ORDINARY_PREFLIGHT_NOT_RUN') else 1)
