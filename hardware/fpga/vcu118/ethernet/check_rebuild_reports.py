#!/usr/bin/env python3
"""Fail-closed gates for a new experimental build, not functional/CDC signoff."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import re


def number(value):
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', value):
        raise ValueError(f'Invalid numeric field: {value}')
    return Decimal(value)


def summary(text):
    match = re.search(r'^\s*WNS\(ns\)[^\n]*\n[^\n]*\n([^\n]+)', text, re.M)
    if not match:
        raise ValueError('Missing timing summary')
    fields = match[1].split()
    if len(fields) != 12:
        raise ValueError('Unexpected timing summary layout')
    values = [number(x) for x in fields]
    for offset in (0, 4, 8):
        if values[offset+3] <= 0 or values[offset+2] < 0:
            raise ValueError('Missing timing endpoints')
    return values


def clock_violations(text):
    result = {}
    # Vivado uses fixed columns, including blank clock and timing fields.
    for title, prefix in (('Intra Clock Table', 'Clock'),
                          ('Inter Clock Table', 'From Clock')):
        section = text.split('| ' + title + '\n')
        if len(section) != 2:
            raise ValueError('Missing/duplicate ' + title)
        lines = section[1].splitlines()
        header_index = next((i for i, s in enumerate(lines)
                             if s.startswith(prefix) and 'WHS(ns)' in s), None)
        if header_index is None:
            raise ValueError('Missing clock header')
        header = lines[header_index]
        columns = list(re.finditer(r'\S(?:.*?\S)?(?=  |$)', header))
        starts = [m.start() - (2 if i >= (2 if prefix == 'From Clock' else 1) else 0)
                  for i, m in enumerate(columns)]
        names = [m.group() for m in columns]
        rows = 0
        for line in lines[header_index+2:]:
            if not line.strip():
                break
            values = [line[start:(starts[i+1] if i+1 < len(starts) else len(line))].strip()
                      for i, start in enumerate(starts)]
            record = dict(zip(names, values))
            rows += 1
            clock_count = 2 if prefix == 'From Clock' else 1
            clocks = tuple(line[:starts[clock_count]].split())
            if len(clocks) != clock_count:
                clocks = ('', *clocks) if clock_count == 2 and len(clocks) == 1 else clocks
            for label, count in (('WHS(ns)', 'THS Failing Endpoints'),
                                 ('WPWS(ns)', 'TPWS Failing Endpoints')):
                if label not in record or not record[label]:
                    continue
                slack, failing = number(record[label]), number(record[count])
                if slack < 0 or failing > 0:
                    key = (title, clocks, label)
                    if key in result:
                        raise ValueError('Duplicate failing clock group')
                    result[key] = (slack, failing)
        if not rows:
            raise ValueError('Empty clock table')
    return result


def synthesis(current, baseline):
    values = summary(current)
    if values[0] < 0 or values[1] != 0 or values[2] != 0:
        raise ValueError('Synthesis setup failed; no implementation allowed')
    old = clock_violations(baseline)
    new = clock_violations(current)
    for key, (slack, count) in new.items():
        if key not in old or slack < old[key][0]:
            raise ValueError(f'New/worse physical synthesis violation: {key}: {slack}')
        # Intra-clock hold endpoint counts can grow with the new RTL. Cross-clock
        # and MIG pulse/skew counts may not expand without a new review.
        if (key[0] == 'Inter Clock Table' or key[2] == 'WPWS(ns)') and count > old[key][1]:
            raise ValueError(f'Expanded cross-clock/pulse violation: {key}')
    for offset, label in ((4, 'WHS(ns)'), (8, 'WPWS(ns)')):
        counts = sum(count for key, (_, count) in new.items() if key[2] == label)
        if counts != values[offset+2]:
            raise ValueError(f'Incomplete physical violation inventory: {label}')
    return {'setup_passed': True, 'physical_groups_deferred': len(new),
            'policy': 'Reviewed synthesis hold/skew only; routed checks remain strict'}


def cdc_rows(text):
    if not re.search(r'ID\s+Severity\s+Count\s+Description', text):
        raise ValueError('Missing CDC summary')
    rows = Counter()
    clocks = ['', '', '']
    counts = Counter()
    for line in text.splitlines():
        for i, label in enumerate(('Source Clock:', 'Destination Clock:', 'CDC Type:')):
            if line.startswith(label):
                clocks[i] = line[len(label):].strip()
        match = re.match(r'\s*(CDC-\d+)\s+(Critical|Warning)\s+(\d+)\s+', line)
        if match:
            counts[(match[1], match[2])] += int(match[3])
        match = re.match(r'\s*\d+\s+(CDC-\d+)\s+(Critical|Warning)\s+(.*)', line)
        if match:
            # Keep both full pin paths, exception, depth and clock context.
            if not all(clocks) or '/' not in match[3]:
                raise ValueError('Incomplete CDC detail row')
            rows[(*clocks, match[1], match[2], ' '.join(match[3].split()))] += 1
    observed = Counter()
    for row, count in rows.items():
        observed[(row[3], row[4])] += count
    if observed != counts or not rows:
        raise ValueError('CDC detail/summary coverage mismatch')
    return rows


def release(reports, baseline):
    values = summary((reports / 'timing_summary.rpt').read_text())
    for offset in (0, 4, 8):
        if values[offset] < 0 or values[offset+1] != 0 or values[offset+2] != 0:
            raise ValueError('Routed setup/hold/pulse failed')
    timing = (reports / 'check_timing.rpt').read_text()
    for check in ('no_clock', 'unconstrained_internal_endpoints', 'multiple_clock',
                  'generated_clocks', 'loops', 'latch_loops'):
        match = re.search(r'checking ' + check + r' \((\d+)\)', timing)
        if not match or int(match[1]):
            raise ValueError('Timing coverage failed: ' + check)
    for name in ('drc', 'methodology'):
        report = (reports / (name + '.rpt')).read_text()
        if not re.search(r'Violations found:\s*\d+', report):
            raise ValueError('Missing ' + name + ' inventory')
        if re.search(r'^\s*\|\s*[^|]+\|\s*(Error|Critical Warning)\s*\|', report, re.M):
            raise ValueError('Blocking ' + name + ' finding')
    new = cdc_rows((reports / 'cdc.rpt').read_text())
    old = cdc_rows(baseline)
    if new - old:
        raise ValueError(f'New/changed CDC detail rows: {sum((new-old).values())}; manual review required')
    return {'experimental_bitstream_eligible': True, 'cdc_signoff': False,
            'remaining_known_cdc_findings': sum(new.values()), 'hardware_validated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('synthesis', 'release'))
    parser.add_argument('current', type=Path)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        old = args.baseline.read_text()
        result = (synthesis(args.current.read_text(), old) if args.mode == 'synthesis'
                  else release(args.current, old))
    except (ValueError, OSError) as exc:
        args.out.write_text(json.dumps({'passed': False, 'error': str(exc)}, indent=2))
        raise SystemExit(str(exc))
    args.out.write_text(json.dumps({'passed': True, **result}, indent=2))
    print(json.dumps(result))
