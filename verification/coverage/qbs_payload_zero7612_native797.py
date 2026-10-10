"""Local partial-bit binding preparation. No EDA entry point or global EL."""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import prepare_qbs_payload_zero796 as source
import dve_tool_identity as tools

need, digest = source.need, source.native.digest
ROOT, OUT, HERE = source.ROOT, source.OUT, source.HERE
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_qbs_payload_zero7612_native797.py')
PACKET = OUT / 'qbs-payload-controlzero796-prepared-agent-20261008-02.json'
PACKET_SHA = 'eaba18abb4b3cd12500b6a6ff49021e3ae2573fc93e26ba0694b1355f986fd84'
ADMISSION = OUT / 'vsmul-saturation-offline-admitted797-parent-20261008-01/admission-manifest.json'
ADMISSION_SHA = '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4'
REPORT = OUT / 'current-population797-inherited796-agent-20261008-01/config.json'
DVE = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve')
STAGES = ('before', 'applied', 'reset', 'reloaded', 'final')
SCHEMA = 'QBS7612_PARTIAL_NATIVE797_PREPARED_V1'
ANNOTATION = 'Frozen QBS exact controlzero bits only; startup X not waived; local binding not population application'
FILES = dict(before='initial-empty.el', applied='first.el', reset='reset-empty.el',
             reloaded='second.el', final='final-empty.el')


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def check_pins(pins):
    for path, sha in pins.items():
        need(digest(path) == sha, 'Frozen file drift: ' + path)


def read_bound(path, sha):
    need(type(sha) is str and len(sha) == 64 and digest(path) == sha, 'Exact input seal: ' + str(path))
    return json.loads(Path(path).read_bytes())


def atom(value):
    need(not any(c in str(value) for c in '{}\\\r\n\t'), 'Unsafe Tcl atom')
    return '{' + str(value) + '}'


def target_map(packet):
    need(packet['status'] == 'PREPARED_WITH_CONSTANT_BINDING_HOLD' and
         packet['candidate_positions'] == 7612 and packet['population'] == 796 and
         packet['approved_EL_sha256'] == source.EL_SHA, 'Exact received source packet')
    result, coords = {}, set()
    for group in packet['groups']:
        need(group['status'] == 'PREPARED_SOURCE_CANDIDATE_NOT_NATIVE_QUALIFIED', 'Source group HOLD')
        for target in group['targets']:
            for bit in target['unowned_bits']:
                key = target['scope'], target['signal']
                need(key[0] == source.SCOPES[1] and key[1].endswith('.hit'), 'Only bank1 hit bits')
                b = bit['bit']
                need(type(b) is int and 0 <= b < target['logical_width'], 'Exact selected bit')
                rec = result.setdefault(key, dict(width=target['logical_width'], bits=[],
                    attributes=target['compiled_attributes']))
                need(rec['width'] == target['logical_width'] and rec['attributes'] == target['compiled_attributes']
                     and b not in rec['bits'], 'No duplicate/overlapping source bits')
                rec['bits'].append(b)
                expected = [target['serialized_offset'] + 2*b + d for d in (0, 1)]
                need(bit['raw_zero_coordinates'] == expected, 'Exact source serialized bit pair')
                for c in expected:
                    need((key[0], c) not in coords, 'Duplicate raw coordinates')
                    coords.add((key[0], c))
    need(len(coords) == 7612 and sum(len(r['bits']) for r in result.values()) == 3806,
         'Exact7612 paired source positions')
    for rec in result.values():
        rec['bits'].sort()
    return result, coords


def suffix_gate(packet, suffix, published):
    _, coords = target_map(packet)
    expected = source.native.union(packet['raw796_scopes'], suffix)
    need(expected == published, 'Raw797 must equal raw796 OR unique new suffix, both banks')
    for scope, row in suffix.items():
        need((row['width'], row['checksum']) == (66340, source.CHECKSUM), 'Suffix compiled identity')
    proof_coords = {(t['scope'], coordinate) for group in packet['groups'] for t in group['targets']
                    for bit in t['source_candidate_bits'] for coordinate in bit['raw_zero_coordinates']}
    need(coords <= proof_coords and len(proof_coords) == 16740, 'Complete source-zero projection including old EL')
    for scope, coordinate in proof_coords:
        row = suffix[scope]
        need(not (int(row['bits'], 16) >> (row['width'] - 1 - coordinate)) & 1,
             'Raw797 suffix counterexample; whole preparation HOLD')
    return dict(status='RAW797_SUFFIX_NO_CANDIDATE_COUNTEREXAMPLE', candidate_positions=7612,
                source_zero_positions_checked=16740, EL_owned_source_zeros_also_checked=True,
                both_banks_exact_OR=True, native_directions_inferred=False,
                startup_X_observation_proven=False, initial_X_counts_as_known_toggle=False)


def labels(kind, attrs):
    name = attrs['name']
    if kind == 'node':
        return name, [name]
    if kind == 'vectornode':
        label = name + '[%s:%s]' % (attrs['left'], attrs['right'])
        return label, [label]
    need(kind == 'arrays', 'Unknown compiled object')
    ranges = []
    for key in ('unpackedrange', 'packedrange'):
        dims = list(map(int, attrs.get(key, '').split()))
        need(len(dims) % 2 == 0, 'Complete MDA declaration')
        ranges += list(zip(dims[::2], dims[1::2]))
    need(ranges, 'MDA retained with explicit geometry')
    label = name + ''.join('[%d:%d]' % pair for pair in ranges)
    return label, [label]


def compiled(packet):
    paths = [next(Path(p) for p in packet['input_pins'] if p.endswith(s)) for s in
             ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml', 'shape/tgl.verilog.shape.xml')]
    design, info, shape = [source.native.xml(p) for p in paths]
    nodes = {n.get('id'): n for m in design.findall('srcdef') for n in m.findall('srcinst')}
    owners = {n.get('id'): m for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def full(key, seen=()):
        need(key not in seen, 'Hierarchy cycle')
        n = nodes[key]
        parent = n.get('pid')
        return (full(parent, seen + (key,)) + '.' if parent in nodes else '') + n.get('name')
    all_scopes = [full(k) for k in nodes]
    scopes = sorted(s for s in all_scopes if any(s == root or s.startswith(root + '.') for root in source.SCOPES))
    modules = {full(k): owners[k] for k in nodes}
    checks = {}
    for node in info.iter('instance_data'):
        scope = node.get('name')
        if scope in scopes:
            need(scope not in checks and node.get('chksum'), 'Unique protected compiled scope checksum')
            checks[scope] = node.get('chksum')
    need(set(checks) == set(scopes), 'Complete protected hierarchy checksums')
    targets, _ = target_map(packet)
    found, instances = set(), []
    for scope in scopes:
        module = modules[scope]
        definitions = [d for d in shape.findall('tgldef') if d.get('chksum') == checks[scope] and
                       d.get('name').split(' (')[0] == module.get('name').split(' (')[0]]
        need(len(definitions) == 1, 'Unique module-base/checksum protected definition')
        definition = definitions[0]
        objects = []
        for n in definition.find('tglshape'):
            attrs = dict(n.attrib)
            label, allowed = labels(n.tag, attrs)
            key = scope, attrs['name']
            selected = targets.get(key)
            if selected:
                need(n.tag == 'vectornode' and attrs == selected['attributes'] and
                     int(attrs['left']) + 1 == selected['width'] and attrs['right'] == '0',
                     'Exact selected hit compiled geometry')
                found.add(key)
            objects.append(dict(name=attrs['name'], kind=n.tag, attributes=attrs,
                label=label, allowed_labels=allowed, selected_bits=selected['bits'] if selected else [],
                width=selected['width'] if selected else None))
        aliases = [a for o in objects for a in o['allowed_labels']]
        need(len(aliases) == len(set(aliases)), 'Native label alias collision')
        instances.append(dict(scope=scope, design_checksum=module.get('chksum'),
                              toggle_checksum=checks[scope], objects=objects,
                              compiled_module_name=module.get('name'), toggle_definition_name=definition.get('name'),
                              protected_parameter_merge_not_qualified=True))
    need(found == set(targets) and all(s in scopes for s in source.SCOPES), 'Complete target/complement hierarchy')
    return instances


def evidence(replay=False):
    packet = read_bound(PACKET, PACKET_SHA)
    check_pins(packet['input_pins'])
    if replay:
        source.verify_packet(packet, source.collect())
    pins = dict(packet['input_pins'], **{str(PACKET): PACKET_SHA, str(ADMISSION): ADMISSION_SHA})
    admission = read_bound(ADMISSION, ADMISSION_SHA)
    need(admission['coverage_admitted'] is True and admission['baseline'] == str(source.BASE) and
         admission['baseline_seal'] == source.BASE_SHA, 'Exact admitted797 genealogy')
    def bound(path, expected):
        need(digest(path) == expected, 'Bound797 input drift: ' + str(path))
        pins[str(path)] = expected
        return Path(path).read_bytes()
    ledger_path = ADMISSION.parent / 'combined-inputs.txt'
    ledger = bound(ledger_path, admission['output_pins'][str(ledger_path)]).decode().splitlines()
    old_ledger = (source.BASE / 'combined-inputs.txt').read_text().splitlines()
    need(len(ledger) == len(set(ledger)) == 798 and ledger[:-1] == old_ledger, 'Exact796 prefix plus one797 sample')
    raw_path = ADMISSION.parent / 'combined-toggle-bits.json'
    raw = json.loads(bound(raw_path, admission['output_pins'][str(raw_path)]))
    suffix_files = list((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(suffix_files) == 1, 'One raw797 suffix file mandatory')
    suffix_path = suffix_files[0]
    bound(suffix_path, admission['input_pins'][str(suffix_path)])
    suffix, sha = source.native.rows(suffix_path, source.SCOPES)
    need(sha == pins[str(suffix_path)], 'Raw suffix immutable parse')
    receipt = suffix_gate(packet, suffix, {s: raw[s] for s in source.SCOPES})
    report_sha = digest(REPORT)
    report = read_bound(REPORT, report_sha)
    need(report['population'] == 797 and report['admission'] == dict(path=str(ADMISSION), sha256=ADMISSION_SHA)
         and report['input_ledger'] == ledger and report['new_exclusions_added'] is False,
         'Prepared797 same-policy authority, not native report qualification')
    pins[str(REPORT)] = report_sha
    el = Path(report['output']) / 'combined.el'
    bound(el, report['pins'][str(el)])
    need(digest(el) == source.EL_SHA, 'Same exact796 approved EL required')
    sample = OUT / 'qbs-payload-residual4-old-image766-agent-20261007-01/code.vdb'
    need(str(sample) in ledger, 'Actual QBS native sample admitted')
    testdirs = list((sample / 'snps/coverage/db/testdata').iterdir())
    need(len(testdirs) == 1 and testdirs[0].is_dir(), 'One actual QBS native test')
    closures = {}
    for role, vdb in (('design', Path(ledger[0])), ('sample', sample)):
        files = sorted(str(p) for p in vdb.rglob('*') if p.is_file())
        need(files, 'Nonempty frozen VDB file closure')
        for f in files:
            bound(Path(f), admission['input_pins'][f])
        closures[role] = files
    receipt.update(path=str(suffix_path), sha256=sha, vdb=ledger[-1], population=797)
    return dict(instances=compiled(packet), pins=pins, suffix_receipt=receipt,
                design=ledger[0], sample=str(sample), test=str(sample.with_suffix('') / testdirs[0].name),
                VDB_file_closures=closures)


def objects_gate(text, inst, stage, previous=None):
    need(stage in STAGES, 'Exact native phase')
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    need(reader.fieldnames == ['path', 'meta', 'name', 'type', 'coverage', 'excluded'], 'Full native object schema')
    aliases = {a: o for o in inst['objects'] for a in o['allowed_labels']}
    found, paths, metas = {}, set(), set()
    for row in reader:
        need(set(row) == set(reader.fieldnames) and all(row.values()), 'Complete object attributes')
        obj = aliases.get(row['name'])
        need(obj is not None and obj['name'] not in found and row['path'] not in paths and row['meta'] not in metas,
             'Foreign/duplicate/ambiguous object identity')
        need(row['path'] == row['meta'] == row['name'], 'Exact native compiled label identity')
        need(row['excluded'] in ('0', '1'), 'Native Boolean exclusion')
        selected = bool(obj['selected_bits'])
        if not selected or stage in ('before', 'reset', 'final'):
            need(row['excluded'] == '0', 'Protected or reset object excluded')
        if previous is not None:
            old = previous[obj['name']]
            need(all(row[k] == old[k] for k in ('path', 'meta', 'name', 'type')), 'Object native identity drift')
            if not selected or stage in ('reset', 'final'):
                need(row['coverage'] == old['coverage'] and row['excluded'] == old['excluded'],
                     'Full protected complement or reset coverage drift')
        found[obj['name']] = row
        paths.add(row['path']); metas.add(row['meta'])
    need(set(found) == {o['name'] for o in inst['objects']}, 'Full compiled complement missing')
    return found


def bits_gate(text, inst, stage, previous=None):
    need(stage in STAGES, 'Exact native phase')
    selected = {o['name']: o for o in inst['objects'] if o['selected_bits']}
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    need(reader.fieldnames == ['signal', 'bit', 'path', 'meta', 'name', 'coverage', '0to1', '1to0'],
         'Native full-vector physical bit schema')
    found, paths, metas = {}, set(), set()
    for row in reader:
        need(set(row) == set(reader.fieldnames) and all(row.values()), 'Complete bit attributes')
        name = row['signal']; obj = selected.get(name)
        need(obj is not None and row['bit'].isdecimal(), 'Foreign native bit')
        b = int(row['bit']); key = name, b
        need(0 <= b < obj['width'] and row['name'] == '%s[%d]' % key and
             row['path'] == row['meta'] == row['name'], 'Actual exact physical bit label')
        need(key not in found and row['path'] not in paths and row['meta'] not in metas, 'Native bit bijection')
        target = b in obj['selected_bits']
        expected = str(int(target and stage in ('applied', 'reloaded')))
        need(row['0to1'] == row['1to0'] == expected, 'Target/adjacent protected direction exclusion drift')
        if stage == 'before' and target:
            need(row['coverage'] == '0.00%', 'Native candidate has coverage; HOLD, never infer raw direction names')
        if previous is not None:
            old = previous[key]
            need(all(row[k] == old[k] for k in ('path', 'meta', 'name')), 'Native bit identity drift')
            if not target or stage in ('reset', 'final'):
                need(row['coverage'] == old['coverage'], 'Adjacent bit or reset coverage drift')
        found[key] = row; paths.add(row['path']); metas.add(row['meta'])
    need(set(found) == {(n, b) for n, o in selected.items() for b in range(o['width'])},
         'Complete selected-vector bit complement mandatory')
    return found


def inventory(out, c, stage):
    result = []
    for index, inst in enumerate(c['instances']):
        before_obj = before_bits = None
        if stage != 'before':
            before_obj = objects_gate((out / ('native_before_%d.tsv' % index)).read_text(), inst, 'before')
            before_bits = bits_gate((out / ('bits_before_%d.tsv' % index)).read_text(), inst, 'before')
        objects = objects_gate((out / ('native_%s_%d.tsv' % (stage, index))).read_text(), inst, stage, before_obj)
        bits = bits_gate((out / ('bits_%s_%d.tsv' % (stage, index))).read_text(), inst, stage, before_bits)
        result.append((objects, bits))
    return result


def el_gate(text, c):
    expected = {(i['scope'], o['name'], b, d) for i in c['instances'] for o in i['objects']
                for b in o['selected_bits'] for d in ('0to1', '1to0')}
    found = set(); scope = checksum = None; records = []; annotations = []
    instances = {i['scope']: i for i in c['instances']}
    def finish():
        need(scope in instances and records and annotations and all(a == ANNOTATION for a in annotations),
             'Complete exact annotated partial native EL block')
        inst = instances[scope]
        need(checksum == inst['design_checksum'] + ' ' + inst['toggle_checksum'], 'Native checksum pair')
        objects = {o['name']: o for o in inst['objects'] if o['selected_bits']}
        for direction, name, left, right, declaration in records:
            obj = objects.get(name)
            need(obj is not None and declaration == 'logic ' + obj['label'], 'No parent/foreign/full-object EL')
            lo, hi = int(right or left), int(left)
            need(lo <= hi and set(range(lo, hi + 1)) <= set(obj['selected_bits']), 'No adjacent protected EL bit')
            for b in range(lo, hi + 1):
                for d in ((direction,) if direction else ('0to1', '1to0')):
                    key = scope, name, b, d
                    need(key not in found, 'Duplicate native EL physical direction')
                    found.add(key)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        m = re.fullmatch(r'CHECKSUM:\s*"([^"\r\n]+)"', line)
        if m:
            if checksum is not None:
                finish()
            checksum, scope, records, annotations = m[1], None, [], []
            continue
        m = re.fullmatch(r'INSTANCE:\s*(\S+)', line)
        if m:
            need(checksum is not None and scope is None and m[1] in instances, 'Exact unique instance in block')
            scope = m[1]; continue
        m = re.fullmatch(r'ANNOTATION:\s*"([^"\r\n]*)"', line)
        if m:
            need(scope is not None, 'Scoped annotation')
            annotations.append(m[1]); continue
        m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) \[(\d+)(?::(\d+))?\] "([^"\r\n]+)"', line)
        need(scope is not None and m is not None, 'Only explicit partial native Toggle directives')
        records.append(m.groups())
    need(checksum is not None, 'Missing native EL')
    finish()
    need(found == expected and len(found) == 7612, 'Exact7612 native directions, no missing/protected bits')
    return sorted(found)


def bind(out, c):
    actual = inventory(out, c, 'before')
    lines, target_rows = [], []
    for index, inst in enumerate(c['instances']):
        chosen = [o for o in inst['objects'] if o['selected_bits']]
        if not chosen:
            continue
        lines += ['CHECKSUM: "%s %s"' % (inst['design_checksum'], inst['toggle_checksum']),
                  'INSTANCE: ' + inst['scope'], 'ANNOTATION: "' + ANNOTATION + '"']
        for o in chosen:
            for b in o['selected_bits']:
                row = actual[index][1][o['name'], b]
                need(row['name'] == '%s[%d]' % (o['name'], b), 'Native before bit binding')
                lines.append('Toggle %s [%d] "logic %s"' % (o['name'], b, o['label']))
                target_rows.append(dict(scope=inst['scope'], signal=o['name'], bit=b,
                                        path=row['path'], meta=row['meta'], label=row['name']))
    text = '\n'.join(lines) + '\n'
    el_gate(text, c)
    need(not (out / 'actual-binding.json').exists() and not (out / 'candidate.el').exists(), 'Fresh native binding only')
    with (out / 'candidate.el').open('x') as stream:
        stream.write(text)
    pins = {str(out / ('%s_before_%d.tsv' % (prefix, k))): digest(out / ('%s_before_%d.tsv' % (prefix, k)))
            for prefix in ('native', 'bits') for k in range(len(c['instances']))}
    save(out / 'actual-binding.json', dict(config_seal=digest(out / 'config.json'), before_pins=pins,
         candidate_EL_sha256=digest(out / 'candidate.el'), targets=target_rows,
         actual_native_directions=7612, initial_X_excluded=False, known_toggle_qualification=False))


def selection(c):
    text = ''.join('set ::qb_%s %s\n' % (k, atom(c[k])) for k in ('design', 'sample', 'test', 'python', 'helper'))
    text += 'set ::qb_instances [list ' + ' '.join('[list %s [list %s]]' %
        (atom(i['scope']), ' '.join('[list %s %s %d]' % (atom(o['name']), atom(o['label']), o['width'])
         for o in i['objects'] if o['selected_bits'])) for i in c['instances']) + ']\n'
    return text


def tcl_pins():
    pins, pending = {}, [TCL]
    while pending:
        path = pending.pop()
        if str(path) in pins:
            continue
        pins[str(path)] = digest(path)
        pending += [Path(p) for p in re.findall(r'source\s+\{(/[^{}\n]+\.tcl)\}', path.read_text())]
    return pins


def prepare(out):
    need(out.parent == OUT and not out.exists(), 'Fresh independent native directory')
    proof = evidence(replay=True)
    pins = dict(proof['pins'], **tcl_pins())
    for path in (SCRIPT, TEST, Path(tools.__file__).resolve()):
        pins[str(path)] = digest(path)
    identity = tools.prepare(str(DVE), '/usr/bin/xvfb-run')
    pins.update({r['path']: r['sha256'] for r in identity['files']})
    c = dict(schema=SCHEMA, status='PREPARED_RAW797_PASS_NOT_LAUNCHED_NOT_NATIVE_QUALIFIED',
        output=str(out), python=sys.executable, helper=str(SCRIPT), pins=pins, identity=identity,
        **{k: proof[k] for k in ('instances', 'design', 'sample', 'test', 'VDB_file_closures', 'suffix_receipt')},
        source_packet_sha256=PACKET_SHA, candidate_positions=7612, physical_bits=3806,
        timeout_seconds=900, automatic_retry=False, population_application=False,
        initial_X_excluded=False, initial_X_counts_as_known_toggle=False, known_toggle_qualification=False,
        native_qualified=False, launch_authorized=False, EDA_started=False, global_EL_created=False)
    check_pins(pins)
    out.mkdir()
    save(out / 'source-and-suffix-proof.json', proof)
    for name, text in (('selection.tcl', selection(c)), ('native-bind.tcl', TCL.read_text())):
        with (out / name).open('x') as stream:
            stream.write(text)
        pins[str(out / name)] = digest(out / name)
    pins[str(out / 'source-and-suffix-proof.json')] = digest(out / 'source-and-suffix-proof.json')
    save(out / 'config.json', c)
    return dict(status=c['status'], output=str(out), seal=digest(out / 'config.json'),
                candidate_positions=7612, EDA_started=False)


def check(out, seal):
    c = read_bound(out / 'config.json', seal)
    need(c['schema'] == SCHEMA and c['output'] == str(out) and c['source_packet_sha256'] == PACKET_SHA and
         c['candidate_positions'] == 7612 and c['physical_bits'] == 3806 and
         type(c['timeout_seconds']) is int and c['timeout_seconds'] == 900 and
         all(c[k] is False for k in ('automatic_retry', 'population_application', 'initial_X_excluded',
             'initial_X_counts_as_known_toggle', 'known_toggle_qualification', 'native_qualified',
             'launch_authorized', 'EDA_started', 'global_EL_created')), 'Closed preparation contract')
    check_pins(c['pins'])
    proof = read_bound(out / 'source-and-suffix-proof.json', c['pins'][str(out / 'source-and-suffix-proof.json')])
    need(all(c[k] == proof[k] for k in ('instances', 'design', 'sample', 'test', 'VDB_file_closures', 'suffix_receipt')),
         'Frozen source/native selection equality')
    current = evidence()
    need(all(current[k] == proof[k] for k in ('instances', 'design', 'sample', 'test', 'VDB_file_closures', 'suffix_receipt'))
         and all(c['pins'].get(p) == sha for p, sha in current['pins'].items()), 'Fresh raw797 required at every check')
    for p, sha in tcl_pins().items():
        need(c['pins'].get(p) == sha, 'Complete sourced Tcl pin')
    for p in (SCRIPT, TEST, Path(tools.__file__).resolve()):
        need(c['pins'].get(str(p)) == digest(p), 'Required helper/test pin')
    need((out / 'selection.tcl').read_text() == selection(c) and
         (out / 'native-bind.tcl').read_text() == TCL.read_text(), 'Exact native driver')
    tools.revalidate(c['identity'])
    return c


def check_binding(out, seal):
    b = json.loads((out / 'actual-binding.json').read_bytes())
    c = read_bound(out / 'config.json', seal)
    need(b['config_seal'] == seal and b['candidate_EL_sha256'] == digest(out / 'candidate.el') and
         b['actual_native_directions'] == 7612 and b['initial_X_excluded'] is False and
         b['known_toggle_qualification'] is False, 'Fresh actual native before binding')
    check_pins(b['before_pins'])
    required = {str(out / ('%s_before_%d.tsv' % (prefix, k))) for prefix in ('native', 'bits')
                for k in range(len(c['instances']))}
    need(set(b['before_pins']) == required, 'All native-before complement pins required')
    actual = inventory(out, c, 'before')
    expected = [dict(scope=inst['scope'], signal=o['name'], bit=bit,
                     path=actual[k][1][o['name'], bit]['path'], meta=actual[k][1][o['name'], bit]['meta'],
                     label=actual[k][1][o['name'], bit]['name'])
                for k, inst in enumerate(c['instances']) for o in inst['objects'] for bit in o['selected_bits']]
    need(b['targets'] == expected, 'Complete fresh native partial-bit selection binding')
    el_gate((out / 'candidate.el').read_text(), c)


def inspect_local(out, seal):
    c = check(out, seal)
    need(not (out / 'error.txt').exists(), 'Native failure HOLD')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('QBS7612_FIVE_PHASE_DONE') == 1 and
         "The design '%s' was loaded successfully." % c['design'] in log and
         not re.search(r'QBS7612_FAILED|EK-CMD-|UCAPI-DLMA|DVCDT136|Load Failed|Error:|Fatal:', log),
         'Complete real native five phases')
    need((out / 'selected_tests.txt').read_text().splitlines() == [c['test']], 'Actual admitted sample identity')
    check_binding(out, seal)
    for stage in STAGES:
        inventory(out, c, stage)
        text = (out / FILES[stage]).read_text()
        if stage in ('before', 'reset', 'final'):
            need(text == '', 'Global empty local reset EL')
        else:
            el_gate(text, c)
    need((out / 'cleanup-empty.el').read_bytes() == b'', 'Independent cleanup empty')
    need(el_gate((out / 'first.el').read_text(), c) == el_gate((out / 'second.el').read_text(), c), 'Exact reload')
    return dict(status='LOCAL_NATIVE_BINDING_ROUNDTRIP_PASS_NOT_KNOWN_TOGGLE_QUALIFICATION',
                directions=7612, initial_X_excluded=False, initial_X_counts_as_known_toggle=False,
                known_toggle_qualification=False, population_application=False, official_percentage=None)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'inventory', 'bind', 'el', 'binding', 'inspect-local'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--stage', choices=STAGES)
    p.add_argument('--file', choices=('first.el', 'second.el'))
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.seal is None, 'Prepare does not authorize EDA')
        result = prepare(out)
    else:
        c = check(out, a.seal)
        if a.mode == 'inventory': inventory(out, c, a.stage)
        elif a.mode == 'bind': bind(out, c)
        elif a.mode == 'binding': check_binding(out, a.seal)
        elif a.mode == 'el': el_gate((out / a.file).read_text(), c)
        result = inspect_local(out, a.seal) if a.mode == 'inspect-local' else dict(status=a.mode + '_PASS_NOT_LAUNCHED')
    print(json.dumps(result, indent=2), flush=True)
