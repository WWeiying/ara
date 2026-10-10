#!/usr/bin/env python3
"""Offline parameter-only branch reachability; never writes coverage exclusions."""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage/reviewed_20261004'))
import audit_readonly as audit

BASELINE = ROOT / 'verification/out/gap38-queue-current-20261004-02'
OUTPUT = ROOT / 'verification/out/gap53-operand-parameters-20261004-01'
POLICY = ROOT / 'verification/coverage/reviewed_20261004/policy.json'
QUEUE_SOURCE = ROOT / 'hardware/src/lane/operand_queue.sv'
STAGE_SOURCE = ROOT / 'hardware/src/lane/operand_queues_stage.sv'
PACKAGE = ROOT / 'hardware/include/ara_pkg.sv'
SUPPORT = ('SupportIntExt2', 'SupportIntExt4', 'SupportIntExt8',
           'SupportReduct', 'SupportNtrVal', 'FPUSupport')
PARAMETERS = (*SUPPORT, 'CmdBufDepth', 'DataBufDepth', 'NrSlaves',
              'NrLanes', 'VLEN', 'AccessCmdPop')
QUEUES = ('alu_a', 'alu_b', 'mfpu_a', 'mfpu_b', 'mfpu_c', 'st_mask_a',
          'slide_addrgen_a', 'mask_b', 'mask_m')
FUNCTIONS = dict(RVVD=5, RVVF=4, RVVH=3, RVVHA=2, RVVB=1, RVVBA=0)
require = audit.require


class Inputs:
    def __init__(self):
        self.files = {}

    def read(self, path, expected=None):
        path = Path(path).absolute()
        require(path.is_relative_to(ROOT) and path.resolve().is_relative_to(ROOT),
                'input outside integration workspace')
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        require(expected is None or digest == expected, 'input hash differs: ' + str(path))
        require(str(path) not in self.files or self.files[str(path)] == digest,
                'input changed during analysis: ' + str(path))
        self.files[str(path)] = digest
        return data

    def json(self, path, expected=None):
        return json.loads(self.read(path, expected))

    def bound(self, path, hashes):
        require(str(path) in hashes, 'missing original pin: ' + str(path))
        return self.read(path, hashes[str(path)])


def span(text, start, end):
    """One-based inclusive source positions, derived from bound source bytes."""
    def position(offset):
        return [text.count('\n', 0, offset) + 1, offset - text.rfind('\n', 0, offset)]
    require(0 <= start < end <= len(text), 'bad source span')
    return dict(start=position(start), end=position(end - 1), text=text[start:end])


def scrub_comments(text):
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def constant(expr, values):
    expr = re.sub(r"\b(\d+)'b([01]+)\b", lambda m: str(int(m[2], 2)), expr.strip())
    node = ast.parse(expr, mode='eval').body
    def visit(n):
        if isinstance(n, ast.Constant) and type(n.value) is int:
            return n.value
        if isinstance(n, ast.Name) and n.id in values:
            return values[n.id]
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            return visit(n.left) + visit(n.right)
        raise ValueError('unsupported constant: ' + expr)
    return visit(node)


def guard_tree(expr):
    """Allow only the parameter grammar actually used here; no dynamic shortcuts."""
    try:
        tree = ast.parse(expr.replace('ara_pkg::', '').replace('||', ' or ').strip(), mode='eval').body
        def visit(n):
            if isinstance(n, ast.Name) and n.id in (*SUPPORT, 'FPUSupportNone'):
                return ('name', n.id)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCTIONS:
                require(len(n.args) == 1 and not n.keywords, 'bad function arguments')
                return ('call', n.func.id, visit(n.args[0]))
            if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.NotEq):
                return ('ne', visit(n.left), visit(n.comparators[0]))
            if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or):
                children = [visit(c) for c in n.values]
                flat = [v for c in children for v in (c[1:] if c[0] == 'or' else [c])]
                return ('or', *flat)
            raise ValueError('not a wholly static parameter guard')
        return visit(tree)
    except (SyntaxError, ValueError):
        return None


def guard_value(tree, parameters):
    if tree[0] == 'name':
        return 0 if tree[1] == 'FPUSupportNone' else parameters[tree[1]]
    if tree[0] == 'call':
        return (guard_value(tree[2], parameters) >> FUNCTIONS[tree[1]]) & 1
    if tree[0] == 'ne':
        return int(guard_value(tree[1], parameters) != guard_value(tree[2], parameters))
    require(tree[0] == 'or', 'unsupported guard tree')
    return int(any(guard_value(c, parameters) for c in tree[1:]))


def if_guard(text, line):
    start = sum(len(s) for s in text.splitlines(keepends=True)[:line - 1])
    clean = scrub_comments(text)
    first_line = clean[start:].split('\n', 1)[0]
    matches = list(re.finditer(r'\bif\s*\(', first_line))
    require(len(matches) == 1, 'ambiguous source if at line ' + str(line))
    begin = start + matches[0].end()
    level = 1
    for end in range(begin, len(clean)):
        level += (clean[end] == '(') - (clean[end] == ')')
        if not level:
            return span(text, begin, end)
    raise ValueError('unclosed source guard')


def overrides(text, module):
    clean = scrub_comments(text)
    result = {}
    pattern = r'\b' + module + r'\s*#\s*\((.*?)\)\s*(\w+)\s*\('
    for match in re.finditer(pattern, clean, re.S):
        entries, offset = {}, 0
        body = match[1]
        while body[offset:].strip():
            p = re.match(r'\s*\.(\w+)\s*\(', body[offset:])
            require(p is not None, 'unsupported instance parameter syntax')
            begin, level = offset + p.end(), 1
            end = begin
            while end < len(body):
                level += (body[end] == '(') - (body[end] == ')')
                if not level:
                    break
                end += 1
            require(level == 0, 'unclosed parameter expression')
            require(p[1] not in entries, 'duplicate parameter override')
            entries[p[1]] = dict(expression=body[begin:end].strip(),
                                source=span(text, match.start(1) + begin, match.start(1) + end))
            offset = end + 1
            if body[offset:].strip():
                comma = re.match(r'\s*,', body[offset:])
                require(comma is not None, 'missing parameter separator')
                offset += comma.end()
        require(match[2] not in result, 'duplicate instance')
        result[match[2]] = entries
    return result


def defaults(text):
    found = {}
    for m in re.finditer(r'\bparameter\s+[^,\n=]*?\b(\w+)\s*=\s*([^,\n]+)', scrub_comments(text)):
        if m[1] in PARAMETERS:
            require(m[1] not in found, 'duplicate parameter default')
            found[m[1]] = dict(expression=m[2].strip(), source=span(text, m.start(2), m.end(2)))
    require(set(found) == set(PARAMETERS), 'missing parameter defaults')
    return found


def package_constants(text):
    clean = scrub_comments(text)
    values, records = {}, {}
    for m in re.finditer(r'\b(FPUSupport\w+)\s*=\s*(6\x27b[01]{6})', clean):
        values[m[1]] = constant(m[2], {})
        records[m[1]] = span(text, m.start(), m.end())
    require(values.get('FPUSupportNone') == 0 and values.get('FPUSupportHalfSingleDouble') == 56,
            'FP enum encoding differs')
    for name, bit in FUNCTIONS.items():
        matches = list(re.finditer(r'function automatic logic ' + name +
                                  r'\(fpu_support_e e\);\s*return e\[(\d+)\];\s*endfunction', clean))
        require(len(matches) == 1 and int(matches[0][1]) == bit, 'FP function differs: ' + name)
        records[name] = span(text, matches[0].start(), matches[0].end())
    for m in re.finditer(r'localparam\s+(?:int\s+unsigned\s+)?(\w+)\s*=\s*(\d+)\s*;', clean):
        values[m[1]] = int(m[2])
        records[m[1]] = span(text, m.start(), m.end())
    return values, records


def signature_variants(definition):
    text = definition.get('param')
    if text is None:
        match = re.fullmatch(r'operand_queue\s*\(\s*parameter\s+(.*?)\s*\)\s*', definition.get('name', ''))
        require(match is not None, 'missing compiled parameter signature')
        text = match[1]
    result = []
    for group in text.split(' + '):
        row = {}
        for field in group.split(','):
            name, sep, value = field.strip().partition('=')
            require(name not in row, 'duplicate compiled parameter')
            row[name] = int(value) if sep and re.fullmatch(r'-?\d+', value) else value if sep else None
        result.append(row)
    return result


def match_signature(parameters, definition):
    variants = signature_variants(definition)
    matches = [v for v in variants if all(k in v and (v[k] == value or
               (k == 'SupportNtrVal' and v[k] is None)) for k, value in parameters.items())]
    require(len(matches) == 1, 'source parameters disagree with compiled signature')
    return dict(attributes=dict(definition.attrib), variants=variants, matched=matches[0],
                omitted_values_resolved_from_bound_source=[k for k in parameters if matches[0][k] is None],
                definition_sha256=audit.tree_digest(definition))


def branch_points(definition, raw):
    specs = list(definition.iter('branch_spec'))
    require(len({s.get('id') for s in specs}) == len(specs), 'duplicate branch spec')
    width = sum(len(s.findall('branch_vector')) for s in specs)
    require(raw['width'] == width, 'raw branch width differs')
    require(raw.get('checksum') in (None, definition.get('chksum')), 'raw branch checksum differs')
    number = int(raw['bits'], 16)
    require(0 <= number < 1 << width, 'raw branch bits exceed width')
    bits = format(number, f'0{width}b')
    base = 0
    for spec in specs:
        vectors = spec.findall('branch_vector')
        require(int(spec.get('totalbranches')) == len(vectors), 'spec vector count differs')
        require(len({v.get('id') for v in vectors}) == len(vectors), 'duplicate branch vector')
        lengths = {len(v.get('vector', '')) for v in vectors}
        require(len(lengths) == 1 and min(lengths) > 0, 'inconsistent branch vector width')
        for position, vector in enumerate(vectors):
            require(set(vector.get('vector')) <= set('01-'), 'invalid branch vector encoding')
            index = base + len(vectors) - 1 - position
            mapped, _, _, _ = audit.branch_index(definition, spec.get('id'), vector.get('id'))
            require(index == mapped, 'reverse-within-spec mapping differs')
            yield spec, vector, index, bits[index], base, len(vectors)
        base += len(vectors)


def impossible_true(vector, expressions, parameters):
    reasons = []
    for expr in expressions:
        index = int(expr['index'])
        require(0 < index <= len(vector), 'expression index exceeds vector')
        tree = guard_tree(expr['exprstr'])
        if tree is not None and guard_value(tree, parameters) == 0 and vector[-index] == '1':
            reasons.append(expr)
    return reasons


def decide(vector, expressions, parameters, hit, reviewed=False):
    reasons = impossible_true(vector, expressions, parameters)
    require(not (reasons and hit), 'observed hit contradicts static-false TRUE model')
    if hit:
        require(not reviewed, 'already reviewed exclusion has a raw hit')
        return 'HIT', reasons
    if reviewed:
        return 'ALREADY_REVIEWED', reasons
    return ('PARAMETER_FALSE_TRUE_CANDIDATE' if reasons else 'RETAINED_STIMULUS_REVIEW'), reasons


def analyze():
    inputs = Inputs()
    plan_path = BASELINE / 'plan.json'
    plan_pins = inputs.json(BASELINE / 'plan.sha256.json')
    require(str(plan_path) in plan_pins, 'unbound baseline plan')
    plan = inputs.json(plan_path, plan_pins[str(plan_path)])
    collection = inputs.json(BASELINE / 'collection.json')
    checkpoint = inputs.json(BASELINE / 'checkpoint.json')
    require(collection['status'] == 'PASS' and collection['passed'] == 641 and
            checkpoint['coverage_status'] == 'COMPLETE' and checkpoint['aggregate_passed'] == 641,
            'expected completed raw641 corpus')
    require(collection['image'] == plan['image'], 'collection image differs')
    def report(name):
        path = BASELINE / name
        return json.loads(inputs.bound(path, collection['reports']))
    raw = report('combined-bits.json')
    ledger = report('all-passed-outcomes.json')
    waiver_status = report('combined-dve/waiver_status.json')
    require(len(ledger) == 641 and len({r['name'] for r in ledger}) == 641 and
            all(r['status'] == 'PASS' and r['passed_only'] is True and r['vdb_valid'] is True for r in ledger),
            'baseline membership differs')
    require(raw['tests'] == [r['vdb'] for r in ledger], 'bitmap membership differs')
    listing = inputs.bound(BASELINE / 'combined-dve/inputs.txt', collection['reports']).decode().splitlines()
    require(listing == [plan['design_vdb'], *raw['tests']], 'DVE membership differs')
    db = Path(plan['design_vdb']) / 'snps/coverage/db'
    for relative, digest in raw['design'].items():
        require(plan['design_files'].get(str(db / relative)) == digest, 'raw/plan shape binding differs')
    design_paths = [db / 'design/verilog.design.xml', db / 'auxiliary/verilog.sourceinfo.xml',
                    *[db / f'shape/{m}.verilog.{kind}.xml'
                      for m in ('line', 'branch', 'tgl') for kind in ('shape', 'info')]]
    for path in design_paths:
        inputs.bound(path, plan['design_files'])
    design = audit.Design(plan['design_vdb'])
    manifest_path = Path(plan['simv']).parent / 'vcs_source_manifest.json'
    manifest = json.loads(inputs.bound(manifest_path, plan['files']))
    compiled = {p['path']: p['sha256'] for p in manifest['files']}
    require(len(compiled) == len(manifest['files']), 'duplicate compiled source pins')
    sources = [QUEUE_SOURCE, STAGE_SOURCE, PACKAGE, ROOT / 'hardware/src/ara.sv',
               ROOT / 'hardware/src/lane/lane.sv', ROOT / 'config/default.mk']
    texts = {}
    for path in sources:
        require(compiled.get(str(path)) == plan['files'].get(str(path)) and str(path) in compiled,
                'source not bound by compiled manifest and frozen plan')
        texts[path] = inputs.bound(path, compiled).decode()
    filelist = inputs.bound(Path(manifest['filelist']), plan['files']).decode()
    defines = sorted(line.strip() for line in filelist.splitlines() if line.startswith('+define+'))
    require('+define+NR_LANES=4' in defines and '+define+VLEN=1024' in defines, 'compiled defines differ')
    ara = design.definition(audit.SYSTEM + '.i_ara', 'tgl')
    inherited = signature_variants(ara)[0]
    parent = {k: inherited[k] for k in ('NrLanes', 'VLEN', 'FPUSupport')}
    require(parent == dict(NrLanes=4, VLEN=1024, FPUSupport=56), 'compiled parent parameters differ')
    chain = []
    for path, module, instance in ((ROOT / 'hardware/src/ara.sv', 'lane', 'i_lane'),
                                   (ROOT / 'hardware/src/lane/lane.sv', 'operand_queues_stage', 'i_operand_queues')):
        entries = overrides(texts[path], module)[instance]
        for name in parent:
            require(entries[name]['expression'] == name, 'parent parameter is not forwarded')
        chain.append(dict(path=str(path), instance=instance, parameters={k: entries[k] for k in parent}))
    values, package_proofs = package_constants(texts[PACKAGE])
    values.update(parent)
    default = defaults(texts[QUEUE_SOURCE])
    stage = overrides(texts[STAGE_SOURCE], 'operand_queue')
    require(set(stage) == {'i_operand_queue_' + q for q in QUEUES}, 'queue instance set differs')
    policy = inputs.json(POLICY)
    inputs.read(POLICY.with_name('audit.json'), policy['audit_sha256'])
    require(policy['design_sha256'] == inputs.files[str(db / 'design/verilog.design.xml')], 'policy design differs')
    require({(p['scope'], p['point']) for p in policy['allowed_points']} == audit.expected_points(),
            'reviewed policy point set differs')
    old = [p for p in policy['allowed_points'] if '.i_operand_queue_' in p['scope']]
    require(len(old) == 88, 'expected 88 reviewed queue objects')
    reviewed, reviewed_records = set(), []
    for p in old:
        resolved = design.point(p)
        reviewed_records.append(dict(p, resolved=resolved))
        if resolved['metric'] == 'branch':
            reviewed.add((p['scope'], resolved['raw_indices'][0]))
    require(len(reviewed) == 16, 'expected 16 previously reviewed queue branch points')
    instances, specs, points = [], {}, []
    actual_scopes = {s for s, d in design.hierarchy.items() if d.get('name') == 'operand_queue'}
    expected_scopes = {f'{audit.SYSTEM}.i_ara.gen_lanes[{lane}].i_lane.i_operand_queues.i_operand_queue_{q}'
                       for lane in range(parent['NrLanes']) for q in QUEUES}
    require(actual_scopes == expected_scopes, 'compiled operand queue universe differs')
    for scope in sorted(expected_scopes):
        queue = scope.rsplit('i_operand_queue_', 1)[1]
        lane = int(re.search(r'gen_lanes\[(\d+)\]', scope)[1])
        entries = stage['i_operand_queue_' + queue]
        parameters, provenance = {}, {}
        for name in PARAMETERS:
            entry = entries.get(name, default[name])
            parameters[name] = constant(entry['expression'], values)
            provenance[name] = dict(entry, path=str(STAGE_SOURCE if name in entries else QUEUE_SOURCE),
                                    kind='instance_override' if name in entries else 'module_default')
        compiled_proof = match_signature(parameters, design.definition(scope, 'tgl'))
        definition = design.definition(scope, 'branch')
        source = design.source(scope)
        require(source['source_path'] == str(QUEUE_SOURCE), 'unexpected branch source')
        source.update(sha256=inputs.files[str(QUEUE_SOURCE)])
        counts = Counter()
        for spec, vector, index, bit, base, width in branch_points(definition, raw['metrics']['branch'][scope]):
            key = definition.get('chksum') + ':' + spec.get('id')
            if key not in specs:
                expressions = []
                for node in spec:
                    if node.tag not in ('branch_expr', 'branch_cexpr'):
                        continue
                    expr = dict(node.attrib, tag=node.tag)
                    require(expr['file_id'] == source['file_id'], 'expression file differs')
                    line = int(expr['id'])
                    lines = texts[QUEUE_SOURCE].splitlines(keepends=True)
                    start = sum(map(len, lines[:line - 1]))
                    expr['source_line'] = span(texts[QUEUE_SOURCE], start, start + len(lines[line - 1].rstrip('\n')))
                    tree = guard_tree(expr['exprstr']) if node.tag == 'branch_expr' else None
                    if tree is not None:
                        expr['source_guard'] = if_guard(texts[QUEUE_SOURCE], line)
                        require(guard_tree(expr['source_guard']['text']) == tree, 'XML/source guard differs')
                    expressions.append(expr)
                specs[key] = dict(attributes=dict(spec.attrib), expressions=expressions,
                                  source=source, raw_base=base, vector_count=width,
                                  spec_sha256=audit.tree_digest(spec),
                                  branch_definition_sha256=audit.tree_digest(definition))
            expressions = [e for e in specs[key]['expressions'] if e['tag'] == 'branch_expr']
            classification, reasons = decide(vector.get('vector'), expressions, parameters,
                                             bit == '1', (scope, index) in reviewed)
            counts[classification] += 1
            if classification != 'HIT':
                points.append(dict(scope=scope, lane=lane, queue=queue, metric='branch',
                    point=f"Branch {spec.get('id')} ({vector.get('id')})", spec_key=key,
                    definition_checksum=source['definition_checksum'], metric_checksum=definition.get('chksum'),
                    spec_checksum=spec.get('chksum'), vector=dict(vector.attrib), raw_index=index,
                    spec_base=base, spec_vector_count=width, raw641='0', classification=classification,
                    impossible_true_guards=[dict(expression_index=int(e['index']), expression=e['exprstr'],
                        constant_value=0, demanded_value=vector.get('vector')[-int(e['index'])],
                        source_guard=e['source_guard']) for e in reasons]))
        instances.append(dict(scope=scope, queue=queue, lane=lane, parameters=parameters,
                              fpu_bits=format(parameters['FPUSupport'], '06b'), parameter_sources=provenance,
                              compiled_signature=compiled_proof, source=source, raw_width=raw['metrics']['branch'][scope]['width'],
                              raw_bits=raw['metrics']['branch'][scope]['bits'], counts=dict(counts)))
    require({(p['scope'], p['raw_index']) for p in points if p['classification'] == 'ALREADY_REVIEWED'} == reviewed,
            'reviewed point subtraction differs')
    counts = Counter(p['classification'] for p in points)
    retained = [p for p in points if p['classification'] == 'RETAINED_STIMULUS_REVIEW']
    by_scope = {i['scope']: i for i in instances}
    for p in retained:
        this = by_scope[p['scope']]
        peers = [i for i in instances if all(i['parameters'][k] == this['parameters'][k] for k in SUPPORT)
                 and (i['lane'] == 0) == (p['lane'] == 0)]
        p['same_support_same_lane_zero_class_hit_witnesses'] = [i['scope'] for i in peers if
            format(int(i['raw_bits'], 16), f"0{i['raw_width']}b")[p['raw_index']] == '1']
        p['reachability'] = 'NOT_PROVEN_FOR_THIS_PRODUCER; investigate stimulus, do not waive'
    inputs.read(Path(audit.__file__))
    inputs.read(Path(__file__))
    inputs.read(Path(__file__).with_name('test_gap53_operand_parameters.py'))
    # Recheck only this bounded input set, never the 641 historical VDB corpus.
    for path, digest in list(inputs.files.items()):
        inputs.read(path, digest)
    return dict(schema='gap53-operand-parameters-v1', status='ANALYSIS_ONLY_NOT_APPLIED',
        baseline=str(BASELINE), baseline_passed=641, native_exclusions_changed=False, simulations_started=False,
        bitmap_provenance='Existing admitted raw641 union, bound to original collection; historical tests not replayed or rehashed',
        mapping='raw_index = prior spec vector counts + current vector count - 1 - XML vector position; guard TRUE iff vector[-expression.index] == 1',
        rule='Only wholly static FALSE parameter guards with an explicit TRUE vector demand. No false/inactive-parent or producer/cmd.conv exclusions.',
        summary=dict(instances=len(instances), raw_branch_points=sum(i['raw_width'] for i in instances),
                     raw_missing=len(points), already_reviewed_queue_objects=88, already_reviewed_branch_points=16,
                     new_candidates=counts['PARAMETER_FALSE_TRUE_CANDIDATE'], retained_missing=len(retained),
                     retained_with_peer_hit=sum(bool(p['same_support_same_lane_zero_class_hit_witnesses']) for p in retained)),
        compiled_parent=dict(scope=audit.SYSTEM + '.i_ara', attributes=dict(ara.attrib),
                             definition_sha256=audit.tree_digest(ara), parameters=parent, forwarding=chain),
        compiled_manifest=str(manifest_path), defines=defines, package_proofs=package_proofs,
        existing_policy=dict(path=str(POLICY), status=policy['status'], raw641_waiver_status=waiver_status,
                             queue_objects=reviewed_records),
        instances=instances, branch_specs=specs, points=points, checked_hashes=inputs.files,
        limitations=['No new native exclusions, adjusted coverage percentages, or measured stimulus gains.',
                     'Retained does not prove legal producer reachability; constant-true false arms and inactive paths stay retained.',
                     'Merged toggle signatures omit SupportNtrVal for some variants; exact values come from hash-bound instance overrides/defaults.'])


def markdown(result):
    s = result['summary']
    lines = ['# Gap53 Operand Queue Parameter Reachability', '',
             'Analysis only. No exclusion policy or native DVE changes. No simulations.', '',
             f"Raw641: {s['instances']} instances, {s['raw_branch_points']} branch points, {s['raw_missing']} missing.",
             f"Subtract {s['already_reviewed_branch_points']} branch points from the 88 already-reviewed queue objects.",
             f"New static-FALSE/TRUE-demand candidates: **{s['new_candidates']}**. Retained missing: **{s['retained_missing']}**.",
             f"Retained points with same-support, same lane-zero-class peer hits: {s['retained_with_peer_hit']} (not proofs for this producer).", '',
             '## Parameters and Counts', '',
             '| Queue | Ext2/4/8 | Reduct/NtrVal | FPU bits | Missing (4 lanes) | Reviewed | Candidates | Retained |',
             '|---|---|---|---|---:|---:|---:|---:|']
    for q in QUEUES:
        items = [i for i in result['instances'] if i['queue'] == q]
        p = items[0]['parameters']
        require(all(i['parameters'] == p for i in items), 'lane parameter variation')
        c = Counter()
        for i in items:
            c.update(i['counts'])
        lines.append(f"| {q} | {p['SupportIntExt2']}/{p['SupportIntExt4']}/{p['SupportIntExt8']} | "
                     f"{p['SupportReduct']}/{p['SupportNtrVal']} | {p['FPUSupport']:06b} | "
                     f"{404-c['HIT']} | {c['ALREADY_REVIEWED']} | {c['PARAMETER_FALSE_TRUE_CANDIDATE']} | {c['RETAINED_STIMULUS_REVIEW']} |")
    lines += ['', '## Evidence and Conservative Boundary', '',
              'reachability.json contains every missing coordinate, native checksums, reverse-mapped raw index, vector, source guard line/column range, parameter origin, and compiled-signature cross-check.',
              'The frozen i_ara toggle definition explicitly records NrLanes=4, VLEN=1024, FPUSupport=56. Hash-bound ara/lane forwarding and stage overrides/defaults determine each queue. Merged queue toggle signatures are checked, never treated as unique parameter tables.',
              'FPUSupportNone=000000; HalfSingleDouble=111000. ara_pkg functions are checked against their explicit bit selection: RVVB=e[1], RVVBA=e[0], both zero here.',
              'Candidates require an explicit TRUE demand on a wholly static FALSE guard. FALSE/inactive parent paths, constant-TRUE false arms, dynamic cmd.conv choices, and producer routing assumptions are not waived.',
              'The policy has 88 reviewed queue objects: 48 line, 24 toggle, 16 branch. Only the 16 branch coordinates are subtracted from this branch inventory. The raw641 waiver_status reports NOT_APPLICABLE_UNREVIEWED_DESIGN; reviewed is not claimed to mean natively applied.',
              'Historical VDB/tool binaries were not rehashed. The admitted raw641 union, ledger/listing, frozen plan, required design/shape files and relevant compiled source/config pins were checked.', '',
              '## Remaining Stimulus Investigation', '',
              'stimulus-opportunities.json lists ALL remaining missing points, including source expressions and optional peer-hit references. These are retained investigation targets, not a claim that every producer can legally drive them.',
              'Branch 4: neutral/reduction paths and final-packet element counts. Branch 5: conversion selection, width, seed extraction and neutral fill. Branch 6: accepted operand, conversion-dependent counters and queue pop. Other specs retain their exact source expressions.',
              'Peer hits are prioritization evidence only. Lane role, producer routing, and legal opcode/SEW/LMUL combinations still need independent stimulus review. No candidate count is a measured coverage gain.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == ROOT / 'verification/out' and output.name.startswith('gap53-') and not output.exists(),
            'a NEW local gap53 output directory is required')
    result = analyze()
    output.mkdir()
    documents = {'reachability.json': result,
                 'candidates.json': dict(status=result['status'], points=[p for p in result['points'] if p['classification'] == 'PARAMETER_FALSE_TRUE_CANDIDATE'], branch_specs=result['branch_specs']),
                 'stimulus-opportunities.json': dict(status='RETAINED_NOT_PROVEN_REACHABLE', points=[p for p in result['points'] if p['classification'] == 'RETAINED_STIMULUS_REVIEW'], branch_specs=result['branch_specs']),
                 'checked-hashes.json': result['checked_hashes']}
    for name, value in documents.items():
        with (output / name).open('x') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
    with (output / 'review.md').open('x') as stream:
        stream.write(markdown(result))
    hashes = {str(p): audit.sha(p) for p in sorted(output.iterdir())}
    with (output / 'manifest.sha256.json').open('x') as stream:
        json.dump(hashes, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(result['summary'], sort_keys=True))
    print(output)


if __name__ == '__main__':
    main()
