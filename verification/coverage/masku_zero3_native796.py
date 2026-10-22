"""Frozen MASKU zero3 local native qualification; prepare/check only, no launcher."""
import argparse
import csv
import json
from pathlib import Path
import re
import sys

import review_masku_zero3_static796_agent_20261008 as static

ROOT, OUT, need, digest, xml = static.ROOT, static.OUT, static.require, static.digest, static.xml
HERE = Path(__file__).resolve().parent
ENTRY = Path(__file__).with_suffix('.tcl')
REVIEW = static.OUTPUT
REVIEW_SHA = '5192f12f3860eae19512cb13dea747842a2228e15b32559979e30b81ba998a2e'
SCOPE = static.source_review.SCOPE
PARENT = SCOPE.rsplit('.', 1)[0]
NAMES = static.NAMES
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')
FILES = dict(before='initial-empty.el', selected='first.el', reset='reset-empty.el',
             reloaded='second.el', final='final-empty.el')
ANNOTATION = 'Frozen VlBitMaskEnable0 exact child zero3 including output; full complement retained; no initial X exclusion'
DVE_EXE = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/linux64/bin/dve.exe')
DVE_ENTRY = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve')


def read_bound(path, sha):
    need(digest(path) == sha, 'Pin drift: ' + str(path))
    return json.loads(Path(path).read_bytes())


def check_pins(pins):
    for path, sha in pins.items():
        need(digest(path) == sha, 'Frozen file drift: ' + path)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def atom(value):
    need(not any(c in str(value) for c in '{}\\\r\n'), 'Unsafe Tcl atom')
    return '{' + str(value) + '}'


def labels(kind, attrs):
    if kind == 'node':
        return attrs['name'], [attrs['name']]
    if kind == 'vectornode':
        full = attrs['name'] + '[%s:%s]' % (attrs['left'], attrs['right'])
        allowed = [full]
        if attrs['left'] == attrs['right']:
            allowed.append(attrs['name'])
        return full, sorted(set(allowed))
    need(kind == 'arrays' and not attrs.get('unpackedrange', '').strip(), 'Packed arrays only')
    dims = list(map(int, attrs['packedrange'].split()))
    need(dims and len(dims) % 2 == 0, 'Complete packed dimensions')
    full = attrs['name'] + ''.join('[%d:%d]' % pair for pair in zip(dims[::2], dims[1::2]))
    return full, sorted({full, full.replace('[0:0]', '[0]')})


def compiled(review):
    check_pins(review['pins'])
    db = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    manifest_path = next(Path(p) for p in review['pins'] if p.endswith('/admission-manifest.json'))
    manifest = json.loads(manifest_path.read_bytes())
    info_path = db / 'shape/tgl.verilog.info.xml'
    need(digest(info_path) == manifest['input_pins'][str(info_path)], 'Compiled instance-info pin')
    design = xml(db / 'design/verilog.design.xml')
    shape = xml(db / 'shape/tgl.verilog.shape.xml')
    checks = {n.get('name'): n.get('chksum') for n in xml(info_path).iter('instance_data')}
    nodes = {n.get('id'): (n, m) for m in design.findall('srcdef') for n in m.findall('srcinst')}

    def full(key):
        n, _ = nodes[key]
        parent = n.get('pid')
        return (full(parent) + '.' if parent in nodes else '') + n.get('name')

    modules = {full(k): m for k, (_, m) in nodes.items()}
    scopes = [PARENT] + sorted(s for s in modules if s.startswith(PARENT + '.'))
    targets = {o['name']: o for o in review['objects']}
    result = []
    for scope in scopes:
        module = modules[scope]
        defs = [d for d in shape.findall('tgldef') if d.get('chksum') == checks[scope]
                and d.get('name').split(' (')[0] == module.get('name').split(' (')[0]]
        need(len(defs) == 1, 'Unique compiled scope/module/checksum')
        bindings = []
        for node in defs[0].find('tglshape'):
            a = dict(node.attrib)
            role = 'target' if scope == SCOPE and a['name'] in NAMES else 'protected'
            label, allowed = labels(node.tag, a)
            width = 1 if node.tag == 'node' else abs(int(a['left']) - int(a['right'])) + 1 if node.tag == 'vectornode' else None
            if role == 'target':
                need(node.tag == 'vectornode' and a == targets[a['name']]['compiled_attributes'] and
                     a['type'] == '1' and a['excluded'] == '0' and width == 256 and
                     a['left'] == '255' and a['right'] == '0' and a['file'] == '558', 'Exact source-bound target')
                need(a['portnode'] == ('3' if a['name'] == 'bit_enable_mask_o' else '0'), 'Exact port identity')
                need(module.get('chksum') == review['module_checksum'] and checks[scope] == review['toggle_checksum'],
                     'Exact child design/Toggle checksum')
            bindings.append(dict(name=a['name'], kind=node.tag, attributes=a, role=role,
                                 width=width, label=label, allowed_labels=allowed))
        aliases = [v for b in bindings for v in b['allowed_labels']]
        need(len(aliases) == len(set(aliases)), 'Native alias collision')
        result.append(dict(scope=scope, design_checksum=module.get('chksum'), toggle_checksum=checks[scope],
                           bindings=bindings))
    need(len(result) == 26 and sum(len(i['bindings']) for i in result) == 987 and
         sum(b['role'] == 'target' for i in result for b in i['bindings']) == 3 and
         sum(b['kind'] == 'arrays' for i in result for b in i['bindings']) == 37, 'Full987 partition')
    return result


def selection(c):
    text = ''.join('set ::re_' + k + ' ' + atom(c[k]) + '\n'
                   for k in ('design', 'sample', 'test', 'python', 'helper'))
    return text + 'set ::re_scopes [list ' + ' '.join(atom(i['scope']) for i in c['instances']) + ']\n'


def contract(c):
    review = read_bound(REVIEW, REVIEW_SHA)
    manifest_path = next(Path(p) for p in review['pins'] if p.endswith('/admission-manifest.json'))
    ledger = (manifest_path.parent / 'combined-inputs.txt').read_text().splitlines()
    need(c['instances'] == compiled(review) and c['source_review_sha256'] == REVIEW_SHA and
         c['population'] == 796 and c['targets'] == 3 and c['physical_bits'] == 768 and
         c['protected'] == 984 and c['timeout_seconds'] == 900 and
         c['launch_authorized'] is False and c['automatic_retry'] is False and
         c['population_application'] is False and c['initial_X_excluded'] is False and
         c['compiled_VlBitMaskEnable_direct_metadata_present'] is False and
         c['parent_alias_qualification_inherited'] is False and
         c['design'] == ledger[0] and c['sample'] == str(OUT / 'gap84-div32-old-image-20261006-01/code.vdb') and
         c['sample'] in ledger and c['helper'] == str(Path(__file__).resolve()) and
         c['python'] == sys.executable and c['expected_dve_exe'] == str(DVE_EXE) and
         c['effective_VlBitMaskEnable_basis'] == review['effective_value_basis'],
         'Exact child zero3 contract; no parent alias inheritance')
    need(all(c['pins'].get(p) == sha for p, sha in review['pins'].items()) and
         c['pins'].get(str(REVIEW)) == REVIEW_SHA, 'Full source review pins inherited')
    for path in (Path(__file__).resolve(), Path(static.__file__).resolve(), ENTRY,
                 HERE / 'test_masku_zero3_native796.py', DVE_EXE, DVE_ENTRY):
        need(c['pins'].get(str(path)) == digest(path), 'Required frozen tool pin')
    testdirs = list((Path(c['sample']) / 'snps/coverage/db/testdata').iterdir())
    need(len(testdirs) == 1 and c['test'] == str(Path(c['sample']).with_suffix('') / testdirs[0].name),
         'Exact native test identity')


def verify(out, seal):
    c = read_bound(out / 'config.json', seal)
    contract(c)
    check_pins(c['pins'])
    need(str(out) == c['output'], 'Output identity')
    for key, files in c['VDB_file_closures'].items():
        need(sorted(str(p) for p in Path(c[key]).rglob('*') if p.is_file()) == files, 'VDB closure file-set drift')
    need((out / 'selection.tcl').read_text() == selection(c), 'Selection drift')
    return c


def inventory(out, c, stage, index):
    need(stage in STAGES and index in range(len(c['instances'])), 'Exact stage/scope')
    inst = c['instances'][index]
    with (out / ('native_%s_%d.tsv' % (stage, index))).open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        need(reader.fieldnames == ['handle', 'path', 'meta', 'name', 'excluded'], 'Exact native schema')
        rows = list(reader)
    need(len(rows) == len(inst['bindings']), 'Complete complement inventory')
    for key in ('handle', 'path', 'name'):
        need(len({r[key] for r in rows}) == len(rows), 'Duplicate native identity')
    aliases = {v: b for b in inst['bindings'] for v in b['allowed_labels']}
    need(len(aliases) == sum(len(b['allowed_labels']) for b in inst['bindings']), 'Alias collision')
    seen, identities = set(), []
    for row in rows:
        need(set(row) == {'handle', 'path', 'meta', 'name', 'excluded'} and all(row.values()) and
             row['handle'].isdigit() and row['path'] == row['meta'] == row['name'], 'Actual path/meta/name identity')
        obj = aliases.get(row['name'])
        need(obj is not None and obj['name'] not in seen, 'Foreign/partial/duplicate typed object')
        seen.add(obj['name'])
        need(row['excluded'] == str(int(stage in ('selected', 'reloaded') and obj['role'] == 'target')),
             'Target or complement exclusion drift')
        identities.append([obj['name'], row['path'], row['meta'], row['name']])
    result = sorted(identities)
    need(seen == {b['name'] for b in inst['bindings']}, 'Missing complement object')
    if stage != 'before':
        binding = json.loads((out / 'actual-binding.json').read_bytes())
        before = out / ('native_before_%d.tsv' % index)
        need(binding['config_seal'] == digest(out / 'config.json') and
             binding['before_pins'][str(before)] == digest(before) and
             binding['scopes'][index] == result, 'Fresh-before identity drift')
    return result


def bind(out, c):
    scopes = [inventory(out, c, 'before', k) for k in range(len(c['instances']))]
    text, count = '', 0
    for index, inst in enumerate(c['instances']):
        labels2 = [r[3] for r in scopes[index] if r[0] in NAMES and inst['scope'] == SCOPE]
        expected = sorted(b['label'] for b in inst['bindings'] if b['role'] == 'target')
        need(sorted(labels2) == expected, 'Actual exact256 native target labels')
        count += len(labels2)
        text += 'set ::re_targets(%d) [list %s]\n' % (index, ' '.join(atom(v) for v in labels2))
    need(count == 3, 'Three child targets only')
    target_path = out / 'actual-selection.tcl'
    need(not target_path.exists() and not (out / 'actual-binding.json').exists(), 'Fresh binding only')
    with target_path.open('x') as stream:
        stream.write(text)
    save(out / 'actual-binding.json', dict(config_seal=digest(out / 'config.json'), scopes=scopes,
         before_pins={str(out / ('native_before_%d.tsv' % k)): digest(out / ('native_before_%d.tsv' % k))
                      for k in range(len(c['instances']))}, actual_selection_sha256=digest(target_path),
         targets=3, protected=984))


def bound_selection(out):
    binding = json.loads((out / 'actual-binding.json').read_bytes())
    need(binding['config_seal'] == digest(out / 'config.json') and binding['actual_selection_sha256'] ==
         digest(out / 'actual-selection.tcl'), 'Actual selection pin')
    check_pins(binding['before_pins'])


def records(text, c):
    inst = next(i for i in c['instances'] if i['scope'] == SCOPE)
    lines = [s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith('//')]
    header = ['CHECKSUM: "%s %s"' % (inst['design_checksum'], inst['toggle_checksum']),
              'INSTANCE: ' + SCOPE, 'ANNOTATION: "' + ANNOTATION + '"']
    expected = sorted(tuple(header + ['Toggle %s "logic %s[255:0]"' % (n, n)]) for n in NAMES)
    need(len(lines) == 12 and sorted(tuple(lines[k:k+4]) for k in range(0, len(lines), 4)) == expected,
         'Only exact three annotated full vectors; no partial/direction/parent/metric/foreign')
    return expected


def check_el(out, c, stage):
    need(stage in STAGES, 'Exact EL phase')
    text = (out / FILES[stage]).read_text()
    if stage in ('before', 'reset', 'final'):
        need(text == '', 'All-scope empty EL required')
        return []
    return records(text, c)


def inspect(out, seal):
    c = verify(out, seal)
    terminal = json.loads((out / 'terminal.json').read_bytes())
    execution = json.loads((out / 'execution.json').read_bytes())
    live = json.loads((out / 'live-identity.json').read_bytes())
    need(terminal['returncode'] == 0 and terminal['timeout'] is False and
         len(terminal['actual_dve']) == 1 and live == terminal['actual_dve'], 'Fresh native terminal/live identity')
    process = live[0]
    need(isinstance(process['pid'], int) and process['pid'] > 0 and process['cwd'] == str(out) and
         process['exe'] == c['expected_dve_exe'] and process['cgroup'].strip(), 'Actual native process identity')
    need(execution['automatic_retry'] is False and execution['timeout_seconds'] == 900 and
         execution['systemd_invocation'] and str(DVE_ENTRY) in execution['command'] and
         '-full64' in execution['command'] and '-cov' in execution['command'] and
         '-script' in execution['command'] and
         execution['command'][execution['command'].index('-script') + 1] == str(ENTRY), 'Exact native execution entry')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('MASKU_ZERO3_NATIVE_DONE') == 1 and 'MASKU_ZERO3_FAILED' not in log and
         "The design '%s' was loaded successfully." % c['design'] in log and
         not re.search(r'UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:', log) and
         not (out / 'error.txt').exists(), 'Complete native log; no rejection')
    bound_selection(out)
    for stage in STAGES:
        check_el(out, c, stage)
        for index in range(len(c['instances'])):
            inventory(out, c, stage, index)
    need((out / 'cleanup-empty.el').read_bytes() == b'', 'Empty cleanup')
    need(records((out / 'first.el').read_text(), c) == records((out / 'second.el').read_text(), c), 'Semantic reload')
    result = dict(status='MASKU_ZERO3_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED', config_seal=seal,
                  targets=3, physical_bits=768, protected=984, full_objects=987, five_stages=True,
                  population_application=False, initial_X_excluded=False, official_percentage=None,
                  parent_alias_qualification_inherited=False,
                  compiled_VlBitMaskEnable_direct_metadata_present=False,
                  pins={str(p): digest(p) for p in out.rglob('*') if p.is_file() and
                        p.name not in ('capture-result.json', 'service.log', 'worker.log')})
    path = out / 'capture-result.json'
    if path.exists():
        need(json.loads(path.read_bytes()) == result, 'Frozen result drift')
    else:
        save(path, result)
    return result


def prepare(out):
    need(out.parent == OUT and not out.exists(), 'Fresh isolated directory')
    review = read_bound(REVIEW, REVIEW_SHA)
    need(static.collect() == review, 'Replay frozen source/796 target review')
    instances = compiled(review)
    pins = dict(review['pins'], **{str(REVIEW): REVIEW_SHA})
    manifest_path = next(Path(p) for p in pins if p.endswith('/admission-manifest.json'))
    manifest = json.loads(manifest_path.read_bytes())
    ledger = (manifest_path.parent / 'combined-inputs.txt').read_text().splitlines()
    sample = OUT / 'gap84-div32-old-image-20261006-01/code.vdb'
    need(str(sample) in ledger, 'Sample admitted in exact796')
    testdirs = list((sample / 'snps/coverage/db/testdata').iterdir())
    need(len(testdirs) == 1 and testdirs[0].is_dir(), 'One actual sample')
    for metric in ('line', 'cond', 'branch', 'fsm', 'tgl'):
        path = testdirs[0] / (metric + '.verilog.data.xml')
        need(digest(path) == manifest['input_pins'][str(path)], 'Admitted sample metric pin')
    design = Path(ledger[0])
    closures = {}
    for key, vdb in (('design', design), ('sample', sample)):
        closures[key] = sorted(str(p) for p in vdb.rglob('*') if p.is_file())
        need(closures[key], 'Complete nonempty VDB closure')
        pins.update({p: digest(p) for p in closures[key]})
    pending = [ENTRY]
    while pending:
        path = pending.pop()
        if str(path) in pins:
            continue
        pins[str(path)] = digest(path)
        pending += [Path(p) for p in re.findall(r'source\s+\{(/[^{}\n]+\.tcl)\}', path.read_text())]
    for path in (Path(__file__).resolve(), Path(static.__file__).resolve(),
                 HERE / 'test_masku_zero3_native796.py', DVE_EXE, DVE_ENTRY):
        pins[str(path)] = digest(path)
    c = dict(status='FROZEN796_ZERO3_PREPARED_NOT_LAUNCHED_NOT_NATIVE_QUALIFIED',
             instances=instances, source_review_sha256=REVIEW_SHA, population=796,
             targets=3, physical_bits=768, protected=984, timeout_seconds=900,
             launch_authorized=False, automatic_retry=False, population_application=False,
             initial_X_excluded=False, parent_alias_qualification_inherited=False,
             compiled_VlBitMaskEnable_direct_metadata_present=False,
             effective_VlBitMaskEnable_basis=review['effective_value_basis'],
             expected_dve_exe=str(DVE_EXE),
             supersedes_static_candidate_policy='Output is eligible by complete zero proof; no interface-based ban. All three require fresh local native qualification.',
             design=str(design), sample=str(sample), test=str(sample.with_suffix('') / testdirs[0].name),
             python=sys.executable, helper=str(Path(__file__).resolve()), output=str(out),
             VDB_file_closures=closures, pins=pins)
    contract(c)
    check_pins(pins)
    out.mkdir()
    with (out / 'selection.tcl').open('x') as stream:
        stream.write(selection(c))
    pins[str(out / 'selection.tcl')] = digest(out / 'selection.tcl')
    save(out / 'config.json', c)
    save(out / 'freeze-receipt.json', dict(status=c['status'], config_sha256=digest(out / 'config.json'),
         candidate_objects=list(NAMES), targets=3, physical_bits=768, protected=984,
         EDA_started=False, native_qualified=False, RTL_changed=False, frozen_tools_changed=False,
         parent_alias_qualification_inherited=False, frozen_tool_pins={p: sha for p, sha in pins.items()
             if Path(p).parent == HERE}, command='python3 -B %s verify-config --output %s --seal %s' %
             (Path(__file__).resolve(), out, digest(out / 'config.json'))))
    return c


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify-config', 'bind', 'inventory', 'el', 'selection', 'inspect'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--stage', choices=STAGES)
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    out = args.output.absolute()
    if args.mode == 'prepare':
        prepare(out)
    else:
        need(args.seal, 'Exact configuration seal required')
        c = verify(out, args.seal)
        if args.mode == 'bind': bind(out, c)
        elif args.mode == 'inventory': inventory(out, c, args.stage, args.index)
        elif args.mode == 'el': check_el(out, c, args.stage)
        elif args.mode == 'selection': bound_selection(out)
        elif args.mode == 'inspect': inspect(out, args.seal)
    print(json.dumps(dict(mode=args.mode, output=str(out), config_sha256=digest(out / 'config.json'))))
