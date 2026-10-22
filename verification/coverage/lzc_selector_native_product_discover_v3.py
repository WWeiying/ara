#!/usr/bin/env python3
"""Bounded read-only successor with explicit product hierarchy expansion."""
import argparse
from pathlib import Path

import lzc_selector_native_product_discover as original
import lzc_selector_native_product_discover_v2 as timing
from lzc_selector_native_prepare import require, sha

HERE = Path(__file__).resolve().parent
LIBRARY = original.SCRIPT
SCRIPT = HERE / 'lzc_selector_native_product_discover_v3.tcl'
CHECK_ORIGINAL = original.safe_script


def safe_script(text):
    CHECK_ORIGINAL(LIBRARY.read_text())
    forbidden = ('gui_exclusion', 'gui_exclude', 'gui_cov_excl', 'apply_reviewed',
                 'exec ', 'eval ', 'gui_load_session', '.el')
    require(not any(word in text for word in forbidden), 'Successor is not read-only')
    require(text.count('source ') == 2 and
            'source {' + str(LIBRARY) + '}' in text and
            'source $env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION)' in text,
            'Successor may load only pinned read-only library and static selection')
    require(text.index('gui_open_cov ') < text.index('gui_list_expand -id CoverageTable.1') <
            text.index('foreach child $lpd_children'), 'Expand product hierarchy before selecting child')


def prepare(prepared, output):
    saved = original.write

    def successor_write(path, value):
        if path.name == 'discovery-plan.json':
            value['preparation_successor'] = 'v3 Tcl list continuation fix plus hierarchy expansion; same707 and300s'
            for pin in (LIBRARY, Path(__file__).resolve(), HERE / 'test_lzc_selector_native_product_discover_v3.py'):
                value['pins'][str(pin)] = sha(pin)
        saved(path, value)

    original.write = successor_write
    try:
        timing.prepare(prepared, output)
    finally:
        original.write = saved


def configure():
    original.SCRIPT = SCRIPT
    original.safe_script = safe_script


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--prepared', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    run = commands.add_parser('launch-readonly')
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    configure()
    if args.mode == 'prepare':
        prepare(args.prepared.resolve(), args.output.resolve())
    else:
        original.launch(args.output.resolve())


if __name__ == '__main__':
    main()
