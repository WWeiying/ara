#!/usr/bin/env python3
"""Snapshot-only adapter: exact reviewed objects, identities and source guards."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure(context, base, audit):
    policy = context['policy']
    expected_points = policy['allowed_points']
    observers = context['observers']
    base.HERE = HERE
    base.APPROVED = {policy['design_sha256']: 'reviewed-current-20261004'}
    base.SHAPES = {'reviewed-current-20261004': hashlib.sha256(
        json.dumps(context['shape_files'], sort_keys=True).encode()).hexdigest()}
    base.approved_points = lambda: {(p['scope'], p['point']) for p in expected_points}

    def exclusions(text):
        parsed = audit.native_entries(text)
        points = [p for p in parsed if p['point'] != 'INSTANCE']
        key = lambda p: (p['scope'], p['point'])
        audit.require(sorted(points, key=key) == sorted(expected_points, key=key),
                      'Native point identity/signature changed')
        actual_observers = [p for p in parsed if p['point'] == 'INSTANCE']
        expected_observers = [{k: p[k] for k in ('scope', 'point', 'checksum',
                              'native_directive', 'nativepointchecksum', 'native_signature')}
                             for p in observers]
        audit.require(not actual_observers or sorted(actual_observers, key=key) ==
                      sorted(expected_observers, key=key), 'Native observer set changed')
        return {(p['scope'], p['point']) for p in parsed}

    def scopes(data):
        audit.require(hashlib.sha256(data).hexdigest() == policy['design_sha256'],
                      'Wrong observer design')
        return [(p['scope'], 1, 'Verification observer; checker remains active') for p in observers]

    base.exclusion_items, base.scopes = exclusions, scopes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('auto', 'off'), default='auto')
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    audit, base = load('audit_readonly'), load('waiver_base')
    context = audit.jread(HERE / 'context.json')
    audit.verify_hashes({str(HERE / p): h for p, h in audit.jread(HERE / 'snapshot.json').items()})
    audit.verify_hashes(context['pins'])
    audit.require(args.design.resolve() == Path(context['design']).resolve(), 'Foreign VDB')
    configure(context, base, audit)
    if args.finalize:
        # Do not publish APPLIED if native recalculation changed the raw data.
        with (args.output / 'summary.csv').open() as stream:
            raw = list(csv.DictReader(stream))
        with Path(context['raw_reference']).open() as stream:
            audit.require(raw == list(csv.DictReader(stream)), 'Raw report changed')
        base.finalize(args.design, args.output)
    else:
        print(base.prepare(args.design, args.output, args.mode)['status'])


if __name__ == '__main__':
    main()
