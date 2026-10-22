#!/usr/bin/env python3
"""Decode exact branch/FSM points for selected same-image VCS instances."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def points(shape, metric, checksum):
    tag = 'branch_def' if metric == 'branch' else 'fsmdef'
    definition = next((n for n in shape.iter(tag) if n.get('chksum') == checksum), None)
    if definition is None or checksum is None:
        raise ValueError(f'Missing {metric} definition for checksum {checksum}')
    result = []
    if metric == 'branch':
        for spec in definition.iter('branch_spec'):
            exprs = [dict(n.attrib) for n in spec if n.tag in ('branch_expr', 'branch_cexpr')]
            vectors = list(spec.findall('branch_vector'))
            if len(vectors) != int(spec.get('totalbranches')):
                raise ValueError('Branch vector/width mismatch')
            for vector in vectors:
                result.append({'spec': spec.get('id'), 'vector_id': vector.get('id'),
                               'vector': vector.get('vector'), 'expressions': exprs})
    else:
        for fsm in definition.iter('fsmfsm'):
            states = fsm.findall('state')
            names = {n.get('id'): n.get('name') for n in states}
            for state in states:
                result.append({'fsm': fsm.get('name'), 'kind': 'state', 'name': state.get('name'),
                               'line': state.get('line')})
            for edge in fsm.findall('transition'):
                result.append({'fsm': fsm.get('name'), 'kind': 'transition',
                               'from': names[edge.get('fromid')], 'to': names[edge.get('toid')],
                               'line': edge.get('line')})
    return result


def audit(inputs, instances):
    paths = [Path(p) for p in inputs.read_text().splitlines() if p.strip()]
    if len(paths) < 2 or len(set(paths)) != len(paths):
        raise ValueError('Design and distinct test VDBs required')
    result = {'inputs': str(inputs.resolve()), 'tests': len(paths) - 1, 'instances': {}}
    for metric in ('branch', 'fsm'):
        with gzip.open(paths[0] / f'snps/coverage/db/shape/{metric}.verilog.shape.xml', 'rb') as stream:
            shape = ET.parse(stream).getroot()
        selected = set(instances)
        if metric == 'fsm':
            selected &= {n.get('name') for n in shape.iter('fsminst')}
        merged, checksums = {}, {}
        for test in paths[1:]:
            files = list((test / 'snps/coverage/db/testdata').glob(f'*/{metric}.verilog.data.xml'))
            if len(files) != 1:
                raise ValueError('Ambiguous test metric file')
            found = set()
            with gzip.open(files[0], 'rb') as stream:
                for _, node in ET.iterparse(stream, events=('end',)):
                    name = node.get('name')
                    if node.tag == 'instance_data' and name in selected:
                        found.add(name)
                        value, checksum = node.get('value'), node.get('chksum')
                        if not value:
                            node.clear()
                            continue
                        if checksum is None:
                            raise ValueError(f'Inherited checksum requires explicit elaboration mapping: {name}')
                        if name not in merged:
                            merged[name] = bytearray(len(value)); checksums[name] = checksum
                        if checksums[name] != checksum or len(merged[name]) != len(value):
                            raise ValueError('Incompatible test points')
                        for i, bit in enumerate(value):
                            if bit not in '01':
                                raise ValueError('Non-binary coverage value')
                            merged[name][i] |= bit == '1'
                    node.clear()
            if found != selected:
                raise ValueError(f'Missing {metric} instances: {selected - found}')
        for name, bits in merged.items():
            decoded = points(shape, metric, checksums[name])
            if len(decoded) != len(bits):
                raise ValueError('Shape/data length mismatch')
            result['instances'].setdefault(name, {})[metric] = {
                'checksum': checksums[name], 'covered': sum(bits), 'total': len(bits),
                'bits': ''.join(map(str, bits)),
                'missing': [dict(point, bit_index=i) for i, point in enumerate(decoded) if not bits[i]]}
    return result


def union(before, addition):
    """Merge compatible point evidence without losing historical covered bits."""
    result = copy.deepcopy(before)
    for instance, metrics in before['instances'].items():
        for metric, old in metrics.items():
            new = addition['instances'][instance][metric]
            if old['checksum'] != new['checksum'] or old['total'] != new['total']:
                raise ValueError('Incompatible comparison shapes')
            if len(old['bits']) != old['total'] or len(new['bits']) != new['total']:
                raise ValueError('Malformed point width')
            if set(old['bits'] + new['bits']) - {'0', '1'}:
                raise ValueError('Non-binary coverage value')
            bits = ''.join('1' if a == '1' or b == '1' else '0'
                           for a, b in zip(old['bits'], new['bits']))
            target = result['instances'][instance][metric]
            target.update(bits=bits, covered=bits.count('1'),
                          missing=[p for p in old['missing'] if bits[p['bit_index']] == '0'])
    result['tests'] = before['tests'] + addition['tests']
    result['inputs'] = [before['inputs'], addition['inputs']]
    return result


def gains(before, after):
    result = {}
    for instance, metrics in before['instances'].items():
        for metric, old in metrics.items():
            new = after['instances'][instance][metric]
            if old['checksum'] != new['checksum'] or old['total'] != new['total']:
                raise ValueError('Incompatible comparison shapes')
            if len(old['bits']) != old['total'] or len(new['bits']) != new['total']:
                raise ValueError('Malformed point width')
            if any(a == '1' and b != '1' for a, b in zip(old['bits'], new['bits'])):
                raise ValueError('Cumulative coverage lost historical points')
            by_index = {point['bit_index']: point for point in old['missing']}
            hit = [by_index[i] for i, (a, b) in enumerate(zip(old['bits'], new['bits'])) if a == '0' and b == '1']
            result.setdefault(instance, {})[metric] = {'new_points': len(hit), 'points': hit}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--instance', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = audit(args.inputs, args.instance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(record, stream, indent=2); stream.write('\n')
    for name, metrics in record['instances'].items():
        print(name, {k: f"{v['covered']}/{v['total']}" for k, v in metrics.items()}, flush=True)


if __name__ == '__main__':
    main()
