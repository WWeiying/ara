#!/usr/bin/env python3
"""Locate inline FOR_VERIFY line blocks, without applying coverage waivers.

FOR_VERIFY membership alone does not prove a block is observational. This is
a source/bitmap-bound candidate inventory for manual fanout review, not a new
coverage denominator or permission to exclude an entire functional module.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guarded_lines(source):
    stack, result = [], set()
    for number, line in enumerate(source.splitlines(), 1):
        token = re.match(r"\s*`(ifdef|ifndef|elsif|else|endif)\b\s*(\w*)", line)
        if token:
            op, key = token.groups()
            if op in ('ifdef', 'ifndef'):
                if not key:
                    raise ValueError('Missing preprocessor condition')
                stack.append((key, op == 'ifdef'))
            elif not stack:
                raise ValueError('Unbalanced preprocessor guard')
            elif op == 'elsif':
                raise ValueError('elsif needs manual guard review')
            elif op == 'else':
                stack[-1] = (stack[-1][0], not stack[-1][1])
            else:
                stack.pop()
        elif ('FOR_VERIFY', True) in stack:
            result.add(number)
    if stack:
        raise ValueError('Unclosed preprocessor guard')
    return result


def classify(definition, cached, file_id, lines):
    bits = bin(int(cached['bits'], 16))[2:].zfill(cached['width'])
    if len(bits) != cached['width']:
        raise ValueError('Invalid bitmap width')
    seen, counts, candidates = set(), Counter(), []
    for block in definition.iter('linebb'):
        index = int(block.get('index'))
        if index in seen or not 0 <= index < len(bits):
            raise ValueError('Duplicate/out-of-range native line index')
        seen.add(index)
        statements = [block, *block.findall('linestmt')]
        observer = all(n.get('file_id') == file_id and
                       int(n.get('line_num', '-1')) in lines for n in statements)
        category = 'guarded_candidate' if observer else 'remaining_mapped'
        counts[category + '_points'] += 1
        counts[category + '_hit'] += bits[index] == '1'
        if observer:
            candidates.append({'native_index': index, 'hit': bits[index] == '1',
                'attributes': block.attrib,
                'statement_lines': sorted({int(n.get('line_num')) for n in statements})})
    unmapped = set(range(len(bits))) - seen
    counts['unmapped_points'] = len(unmapped)
    counts['unmapped_hit'] = sum(bits[i] == '1' for i in unmapped)
    return {'raw_line_bits': dict(counts), 'candidate_blocks': candidates,
            'unmapped_indices': sorted(unmapped)}


def inspect(plan_path, cache_path, source, instances):
    plan = json.loads(plan_path.read_text())
    cache = json.loads(cache_path.read_text())
    vdb = Path(plan['design_vdb'])
    db = vdb / 'snps/coverage/db'
    pins_path = vdb.parents[1] / 'build-source-pins.json'
    pins = json.loads(pins_path.read_text())
    source = source.resolve(strict=True)
    if pins.get(str(source)) != sha(source):
        raise ValueError('Source differs from compiled source manifest')
    for relative, expected in cache['design'].items():
        if sha(db / relative) != expected:
            raise ValueError('Cache design/shape differs from current VDB')
    info_path = db / 'auxiliary/verilog.sourceinfo.xml'
    info = ET.parse(info_path).getroot()
    matches = [n.get('id') for n in info.iter('fileinfo') if
               Path(n.get('name')).resolve() == source]
    if len(matches) != 1:
        raise ValueError('Ambiguous native source identity')
    shape_path = db / 'shape/line.verilog.shape.xml'
    with gzip.open(shape_path) as stream:
        shape = ET.parse(stream).getroot()
    lines = guarded_lines(source.read_text())
    result = {'status': 'CANDIDATES_ONLY', 'scope': 'raw line bits, not DVE scoring units',
              'waivers_applied': False, 'source': str(source), 'instances': {},
              'files': {str(p.resolve()): sha(p) for p in
                        (plan_path, cache_path, source, pins_path, shape_path, info_path)}}
    for name in instances:
        cached = cache['metrics']['line'][name]
        definitions = [d for d in shape.iter('linedef') if
                       d.get('chksum') == cached['checksum']]
        if cached['checksum'] is None or len(definitions) != 1:
            raise ValueError('Explicit unique instance checksum required')
        result['instances'][name] = classify(definitions[0], cached, matches[0], lines)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('plan', 'cache', 'source', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--instance', action='append', required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('A new output path is required')
    result = inspect(args.plan, args.cache, args.source, args.instance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    for name, value in result['instances'].items():
        print(name, value['raw_line_bits'])


if __name__ == '__main__':
    main()
