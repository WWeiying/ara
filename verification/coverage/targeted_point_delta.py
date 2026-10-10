#!/usr/bin/env python3
"""Measure source-indexed target hits between compatible PASS-only bitmaps."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def inspect(before, after, inventory, scope, expression, metric_filter='cond'):
    if before['design'] != after['design']:
        raise ValueError('different coverage designs')
    if not set(before['tests']).issubset(after['tests']):
        raise ValueError('after snapshot does not include baseline tests')
    counts = Counter()
    recovered = []
    remaining = []
    seen = set()
    for point in inventory:
        if point['metric'] != metric_filter:
            continue
        if scope not in point['scope'] or expression not in point['expression']:
            continue
        metric = point['metric']
        name = point['scope']
        index = int(point['raw_index'])
        key = (metric, name, index)
        if key in seen:
            raise ValueError('duplicate inventory point')
        seen.add(key)
        old = before['metrics'][metric][name]
        new = after['metrics'][metric][name]
        if (old['width'], old['checksum']) != (new['width'], new['checksum']):
            raise ValueError('coverage point shape changed: ' + name)
        if not 0 <= index < old['width']:
            raise ValueError('out-of-range source index')
        old_bits = format(int(old['bits'], 16), '0%db' % old['width'])
        new_bits = format(int(new['bits'], 16), '0%db' % new['width'])
        if len(old_bits) != old['width'] or len(new_bits) != new['width']:
            raise ValueError('coverage bit width overflow')
        if old_bits[index] == '1' and new_bits[index] != '1':
            raise ValueError('baseline point lost')
        if old_bits[index] == '0':
            counts['baseline_unhit'] += 1
            if new_bits[index] == '1':
                recovered.append(point)
                counts['newly_hit'] += 1
            else:
                remaining.append(point)
                counts['remaining_unhit'] += 1
    return dict(counts=dict(counts), newly_hit=recovered, remaining_unhit=remaining,
                scope_filter=scope, expression_filter=expression, metric_filter=metric_filter,
                interpretation='raw source-indexed diagnostic points, not DVE percentages')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--expression', default='')
    parser.add_argument('--metric', choices=['line', 'cond', 'branch'], default='cond')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.before.read_text())
    after = json.loads(args.after.read_text())
    with args.inventory.open(newline='') as source:
        result = inspect(before, after, csv.DictReader(source), args.scope, args.expression, args.metric)
    with args.output.open('x') as target:
        json.dump(result, target, indent=2)
        target.write('\n')
    print(json.dumps(result['counts']))


if __name__ == '__main__':
    main()
