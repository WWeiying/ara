#!/usr/bin/env python3
"""Read-only discovery successor: fix generated Tcl list line continuations only."""
import argparse
from pathlib import Path

import lzc_selector_native_product_discover as original
from lzc_selector_native_prepare import sha, require


def selection_successor(text):
    require(text.count('set lpd_children [list\n') == 1, 'Unexpected original selection shape')
    prefix, children = text.split('set lpd_children [list\n', 1)
    require(children.endswith(']\n'), 'Unexpected child list terminator')
    lines = children[:-2].splitlines()
    require(lines and all(line.startswith('  [list ') and line.endswith(']]') for line in lines),
            'Unexpected original child rows')
    return prefix + 'set lpd_children [list \\\n' + ''.join(line + ' \\\n' for line in lines) + ']\n'


def prepare(prepared, output):
    saved = original.write

    def successor_write(path, value):
        if path.name == 'selection.tcl':
            value = selection_successor(value)
        elif path.name == 'discovery-plan.json':
            value['preparation_successor'] = 'v2 generated Tcl list continuations only'
            for pin in (Path(__file__).resolve(), Path(__file__).with_name('test_lzc_selector_native_product_discover_v2.py')):
                value['pins'][str(pin)] = sha(pin)
        saved(path, value)

    original.write = successor_write
    try:
        original.prepare(prepared, output)
    finally:
        original.write = saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--prepared', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    run = commands.add_parser('launch-readonly')
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.prepared.resolve(), args.output.resolve())
    else:
        original.launch(args.output.resolve())


if __name__ == '__main__':
    main()
