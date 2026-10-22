#!/usr/bin/env python3
"""Same-design raw VCS bitmap unions; official percentages remain DVE output.

Inputs must already be admitted by the PASS-only campaign. This tool checks
database shapes and metric encodings, but does not establish a test verdict.
Raw bit gains are diagnostic; they are not DVE scoring denominators.
"""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

METRICS = ('line', 'cond', 'branch', 'fsm')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_metric(path):
    with gzip.open(path, 'rb') as stream:
        root = ET.parse(stream).getroot()
    if root.tag != 'covdata':
        raise ValueError('Not a coverage data document')
    rows = {}
    for node in root.iter('instance_data'):
        name, bits = node.get('name'), node.get('value', '')
        if not name or name in rows or set(bits) - {'0', '1'}:
            raise ValueError('Duplicate instance or malformed bitmap')
        rows[name] = {'width': len(bits), 'checksum': node.get('chksum'),
                      'bits': hex(int(bits or '0', 2))}
    return rows


def combine(old, new):
    if old['design'] != new['design'] or set(old['metrics']) != set(new['metrics']):
        raise ValueError('Incompatible design or metrics')
    if set(old['tests']) & set(new['tests']):
        raise ValueError('Duplicate test databases')
    result = copy.deepcopy(old)
    result['tests'] += new['tests']
    result['input_hashes'].update(new['input_hashes'])
    for metric, rows in result['metrics'].items():
        other = new['metrics'][metric]
        if set(rows) != set(other):
            raise ValueError('Coverage instance universe changed')
        for name, row in rows.items():
            add = other[name]
            if (row['width'], row['checksum']) != (add['width'], add['checksum']):
                raise ValueError('Coverage point shape changed')
            row['bits'] = hex(int(row['bits'], 16) | int(add['bits'], 16))
    return result


def collect(inputs, metrics=METRICS):
    paths = [Path(p).resolve(strict=True) for p in inputs.read_text().splitlines() if p.strip()]
    if len(paths) < 2 or len(set(paths)) != len(paths):
        raise ValueError('A design and distinct test VDBs are required')
    db = paths[0] / 'snps/coverage/db'
    design = {str(p.relative_to(db)): digest(p) for p in
              [db / 'design/verilog.design.xml',
               *[db / f'shape/{m}.verilog.shape.xml' for m in metrics]]}
    result = None
    for index, path in enumerate(paths[1:], 1):
        sample = {'design': design, 'tests': [str(path)], 'input_hashes': {}, 'metrics': {}}
        for metric in metrics:
            files = list((path / 'snps/coverage/db/testdata').glob(f'*/{metric}.verilog.data.xml'))
            if len(files) != 1:
                raise ValueError('Ambiguous or missing test metric')
            source = files[0]
            before = digest(source)
            sample['metrics'][metric] = read_metric(source)
            if digest(source) != before:
                raise ValueError('Test database changed while reading')
            sample['input_hashes'][str(source)] = before
        if result is None:
            result = sample
        else:
            # Merge in place: the baseline can contain thousands of instances.
            if sample['design'] != result['design']:
                raise ValueError('Design drift')
            result['tests'].extend(sample['tests'])
            result['input_hashes'].update(sample['input_hashes'])
            for metric, rows in result['metrics'].items():
                new = sample['metrics'][metric]
                if rows.keys() != new.keys():
                    raise ValueError('Instance universe changed')
                for name, row in rows.items():
                    other = new[name]
                    if (row['width'], row['checksum']) != (other['width'], other['checksum']):
                        raise ValueError('Point width/checksum changed')
                    row['bits'] = hex(int(row['bits'], 16) | int(other['bits'], 16))
        if index % 100 == 0:
            print(f'Raw bitmap union: {index}/{len(paths)-1}', flush=True)
    result['scope'] = 'Raw diagnostic positions; not DVE percentages or a PASS verdict'
    return result


def delta(before, after, scope='ara_tb.dut.i_ara_soc.i_system'):
    if before['design'] != after['design'] or set(before['metrics']) != set(after['metrics']):
        raise ValueError('Incompatible design or metrics')
    result = {'scope': scope, 'raw_diagnostic_bits': True, 'metrics': {}, 'instances': []}
    for metric, old in before['metrics'].items():
        new = after['metrics'][metric]
        if old.keys() != new.keys():
            raise ValueError('Instance universe changed')
        total = 0
        for name, row in old.items():
            value = new[name]
            if (row['width'], row['checksum']) != (value['width'], value['checksum']):
                raise ValueError('Point shape changed')
            a, b = int(row['bits'], 16), int(value['bits'], 16)
            if a & ~b:
                raise ValueError('Previously covered points disappeared')
            gain = bin(b & ~a).count('1')
            if name == scope or name.startswith(scope + '.'):
                total += gain
                if gain:
                    result['instances'].append({'instance': name, 'metric': metric,
                        'new_bits': gain, 'before_hit': bin(a).count('1'), 'after_hit': bin(b).count('1'),
                        'raw_width': row['width']})
        result['metrics'][metric] = total
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('new output path required')
    result = collect(args.inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream)
        stream.write('\n')
    print(f'Collected {len(result["tests"])} same-design VDBs', flush=True)


if __name__ == '__main__':
    main()
