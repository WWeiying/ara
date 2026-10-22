#!/usr/bin/env python3
"""Source-indexed diagnostic zeros from a completed PASS-only aggregate.

This is not an admission checker or a native exclusion generator. Raw point
ordering is diagnostic, including reversed rows within branch/condition groups.
"""
import argparse
from collections import Counter
import csv
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import closure_scorecard as score

TAGS = {'line': 'linedef', 'branch': 'branch_def', 'cond': 'conddef'}


def read_xml(path):
    data = path.read_bytes()
    return ET.fromstring(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)


def definition(root, module, checksum):
    candidates = [n for n in root if n.get('chksum') == str(checksum)
                  and n.get('id') == module.get('id')]
    score.require(len(candidates) == 1, 'ambiguous/missing native definition: id=%s checksum=%s shape=%s' %
                  (module.get('id'), checksum, root.tag))
    return candidates[0]


def points(metric, node, width):
    result = []
    if metric == 'line':
        for bb in node.iter('linebb'):
            result.append(dict(raw_index=int(bb.get('index')), native_id=bb.get('id'),
                file_id=bb.get('file_id'), line=bb.get('line_num'),
                expression=bb.get('bbsig', ''), vector='',
                attributes=dict(bb.attrib), statements=[dict(s.attrib) for s in bb]))
    elif metric == 'branch':
        offset = 0
        for group in node.iter('branch_spec'):
            vectors = group.findall('branch_vector')
            score.require(len(vectors) == int(group.get('totalbranches')), 'branch width drift')
            expressions = [dict(n.attrib) for n in group
                           if n.tag in ('branch_expr', 'branch_cexpr')]
            for index, vector in enumerate(vectors):
                result.append(dict(raw_index=offset + len(vectors) - 1 - index,
                    native_id=group.get('id'), file_id=group.get('file_id'),
                    line=expressions[0].get('id') if expressions else None,
                    expression=' ; '.join(e.get('exprstr', '') for e in expressions),
                    vector=vector.get('id'), attributes=dict(group.attrib),
                    native_vector=dict(vector.attrib), expressions=expressions))
            offset += len(vectors)
        score.require(offset == width, 'branch shape/data width differs')
    else:
        score.require(metric == 'cond', 'unsupported metric')
        parents = {id(n): s for s in node.iter('condspec') for n in s.iter('expr_monitored')}
        expressions = sorted(node.iter('expr_monitored'), key=lambda e: int(e.get('condregid')))
        ids = [int(e.get('condregid')) for e in expressions]
        score.require(ids == list(range(1, len(ids) + 1)), 'noncontiguous condition register IDs')
        offset = 0
        for expression in expressions:
            table = expression.find('truth_table')
            score.require(table is not None, 'missing condition truth table')
            rows, columns = int(table.get('nrows')), int(table.get('ncols'))
            vectors = table.get('vecs', '')
            score.require(rows > 0 and columns > 0 and len(vectors) == rows * columns,
                          'malformed condition truth table')
            parent = parents[id(expression)]
            for index in range(rows):
                result.append(dict(raw_index=offset + rows - 1 - index,
                    native_id=expression.get('condregid'), file_id=parent.get('file'),
                    line=parent.get('lines'), expression=expression.get('exprstr', ''),
                    vector=vectors[index * columns:(index + 1) * columns],
                    attributes=dict(expression.attrib), spec=dict(parent.attrib),
                    truth_table=dict(table.attrib), row=index))
            offset += rows
        score.require(offset == width, 'condition shape/data width differs')
    positions = [p['raw_index'] for p in result]
    score.require(len(set(positions)) == len(positions) and
                  all(0 <= p < width for p in positions), 'duplicate/out-of-range position')
    return sorted(result, key=lambda p: p['raw_index'])


def selected(scope, critical):
    return any(scope == prefix or scope.startswith(prefix + '.') for prefix in critical)


def metric_checksum(data_checksum, info_checksum):
    if data_checksum is None and info_checksum is None:
        return None
    value = info_checksum if info_checksum is not None else data_checksum
    score.require(data_checksum in (None, value), 'metric info/data checksum mismatch')
    return value


def inventory(baseline, completion, source_manifest):
    baseline = baseline.resolve(strict=True)
    verified = score.scorecard(baseline, completion)
    pins = dict(verified['report_pins'])

    def pin(path, expected=None):
        path = path.absolute()
        actual = score.digest(path)
        score.require(expected is None or actual == expected, 'input drift: ' + str(path))
        score.require(str(path) not in pins or pins[str(path)] == actual,
                      'input changed during inventory')
        pins[str(path)] = actual
        return path

    plan_path = baseline / 'plan.json'
    seal_path = pin(baseline / 'plan.sha256.json')
    seal = score.read(seal_path)
    score.require(set(seal) == {str(plan_path)}, 'foreign plan seal')
    plan = score.read(pin(plan_path, seal[str(plan_path)]))
    source_manifest = source_manifest.absolute()
    score.require(str(source_manifest) in plan['files'], 'unbound source manifest')
    source_hashes = score.read(pin(source_manifest, plan['files'][str(source_manifest)]))
    bits = score.read(baseline / 'combined-bits.json')
    design_vdb = Path(plan['design_vdb'])
    db = design_vdb / 'snps/coverage/db'
    score.require((baseline / 'combined-dve/inputs.txt').read_text().splitlines()[0] ==
                  str(design_vdb), 'report/design VDB mismatch')
    for relative, expected in bits['design'].items():
        pin(db / relative, expected)
    source_info = db / 'auxiliary/verilog.sourceinfo.xml'
    score.require(str(source_info) in plan['files'], 'unbound source coordinates')
    files = {n.get('id'): n.get('name') for n in
             read_xml(pin(source_info, plan['files'][str(source_info)])).iter('fileinfo')}
    design = read_xml(db / 'design/verilog.design.xml')
    nodes = {n.get('id'): (n, d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    hierarchy = {}

    def path(key, visiting=()):
        score.require(key not in visiting, 'cyclic hierarchy')
        n, _ = nodes[key]
        parent = n.get('pid')
        return (path(parent, visiting + (key,)) + '.' if parent in nodes else '') + n.get('name')

    for key, (_, module) in nodes.items():
        name = path(key)
        score.require(name not in hierarchy, 'duplicate hierarchy path')
        hierarchy[name] = module
    critical = {r['scope'] for r in verified['modules']}
    zero_points, missing, counts = [], [], Counter()
    cache, sources = {}, {}
    for metric in TAGS:
        root = read_xml(db / ('shape/%s.verilog.shape.xml' % metric))
        info_path = db / ('shape/%s.verilog.info.xml' % metric)
        score.require(str(info_path) in plan['files'], 'unbound metric instance definitions')
        info = {n.get('name'): n.get('chksum') for n in
                read_xml(pin(info_path, plan['files'][str(info_path)])).iter('instance_data')}
        for scope, row in sorted(bits['metrics'][metric].items()):
            if not selected(scope, critical) or not row['width']:
                continue
            score.require(scope in hierarchy, 'unknown bitmap instance')
            module = hierarchy[scope]
            checksum = metric_checksum(row['checksum'], info.get(scope))
            raw = format(int(row['bits'], 16), '0%db' % row['width'])
            score.require(len(raw) == row['width'], 'bitmap width overflow')
            if checksum is None:
                missing.append(dict(scope=scope, metric=metric,
                    offsets=[i for i, hit in enumerate(raw) if hit == '0'],
                    reason='No per-instance native checksum; inherited layout not inferred'))
                continue
            cache_key = (module.get('id'), checksum, row['width'])
            if cache_key not in cache:
                node = definition(root, module, checksum)
                cache[cache_key] = points(metric, node, row['width'])
            mapped = cache[cache_key]
            offsets = {p['raw_index'] for p in mapped}
            unmapped = [i for i, hit in enumerate(raw) if hit == '0' and i not in offsets]
            if unmapped:
                missing.append(dict(scope=scope, metric=metric, offsets=unmapped,
                                    reason='No source-bearing point; not automatically waived'))
            for point in mapped:
                if raw[point['raw_index']] != '0':
                    continue
                source = files.get(point['file_id'])
                score.require(source in source_hashes, 'unbound point source')
                if source not in sources:
                    pin(Path(source), source_hashes[source])
                    sources[source] = Path(source).read_text().splitlines()
                number = str(point['line'] or '')
                excerpt = ''
                if number.isdigit():
                    start = max(0, int(number) - 2)
                    excerpt = '\n'.join('%d: %s' % (i + 1, sources[source][i])
                                        for i in range(start, min(len(sources[source]), start + 4)))
                zero_points.append(dict(point, scope=scope, module=module.get('name'),
                    metric=metric, metric_checksum=checksum, source=source,
                    source_sha256=source_hashes[source], excerpt=excerpt,
                    classification='UNREVIEWED', native_dve_qualified=False))
                counts[metric] += 1
        cache.clear()
    for name, expected in pins.items():
        score.require(score.digest(Path(name)) == expected, 'final input drift: ' + name)
    return dict(schema='closure-point-inventory-v1', status='DIAGNOSTIC_NOT_SIGNOFF',
        baseline=str(baseline), passed=verified['passed'], official_raw=verified['global_raw'],
        report_pins=pins, source_points=zero_points, unmapped_zeros=missing,
        zero_point_counts=dict(counts), waivers_applied=False,
        interpretation='No tools/tests run and no exclusions generated. Reads completed aggregate '
            'evidence without re-admitting tests or rehashing historical test VDBs. Point positions '
            'are diagnostic: explicit line index, reversed within each branch/condition group. '
            'Native DVE qualification and reachability review remain separate requirements.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--completion', type=Path)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    score.require(not args.output.exists(), 'fresh output directory required')
    report = inventory(args.baseline, args.completion, args.source_manifest)
    args.output.mkdir(parents=True)
    with (args.output / 'inventory.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    fields = ('scope', 'module', 'metric', 'metric_checksum', 'raw_index', 'native_id',
              'vector', 'source', 'line', 'expression', 'classification', 'native_dve_qualified')
    with (args.output / 'zeros.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(report['source_points'])
    print('DIAGNOSTIC_NOT_SIGNOFF: PASS=%d; zeros=%s; unmapped groups=%d' %
          (report['passed'], report['zero_point_counts'], len(report['unmapped_zeros'])))


if __name__ == '__main__':
    main()
