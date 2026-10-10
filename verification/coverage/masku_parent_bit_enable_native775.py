"""Parent bit_enable_mask ONLY; static prepare, fresh five-stage native gates, no launcher."""
import argparse
import csv
import json
from pathlib import Path
import re
import sys

import review_masku_parent_bit_enable_static as source
import rvh0_exception60_native772_v3 as mature
import rank_ordinary_rvv_toggle766 as cache_source

life, need, typed = mature.life, mature.need, source.prior.typed
HERE = Path(__file__).resolve().parent
ENTRY = Path(__file__).with_suffix('.tcl')
REVIEW_SHA = '285717a381e0bd1a59d5f878a303180d991e68585353bae081209fff81a879f1'
BASE = source.OUT / 'vmacc-offline-admitted775-parent-20261007-01'
BASE_SHA = '59d67f7d5088baefaa498eda1d8e0f607e0eaf87945cc79a5f83607f8d679a13'
FULL = source.OUT / 'native-full775-cached-parent-20261007-01'
ANNOTATION = 'Frozen VlBitMaskEnable0 parent internal bit_enable_mask only; no startup X exclusion; ports and all complements protected'
STAGES, FILES = mature.STAGES, mature.FILES


def no_overlap(text):
    relevant = []
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        scopes = re.findall(r'^INSTANCE:\s*(\S+)\s*$', block, re.M)
        if not block.strip():
            continue
        need(len(scopes) == 1, 'EL block scope missing/ambiguous')
        scope = scopes[0]
        if scope != source.SCOPE and not source.SCOPE.startswith(scope + '.'):
            continue
        metrics = [line for line in block.splitlines() if line.strip() and not
                   line.startswith(('CHECKSUM:', 'INSTANCE:', 'ANNOTATION:', '//'))]
        need(metrics, 'Existing whole-scope/ancestor exclusion overlaps target')
        for line in metrics:
            need(not re.match(r'^Toggle(?:\s+(?:0to1|1to0))?\s+bit_enable_mask(?:\s|\[|$)', line),
                 'Existing Toggle exclusion overlaps exact target')
        relevant.append(block)
    return relevant


def compiled(review):
    db = source.OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    shape = typed.xml(db / 'shape/tgl.verilog.shape.xml')
    checks = {n.get('name'): n.get('chksum') for n in typed.xml(db / 'shape/tgl.verilog.info.xml').iter('instance_data')}
    owners = [dict(scope=source.SCOPE, module='masku', module_checksum=review['module_checksum'])] + review['protected_children']
    result = []
    for owner in owners:
        scope = owner['scope']
        matches = [d for d in shape.findall('tgldef') if d.get('chksum') == checks[scope]
                   and d.get('name').split(' (')[0] == owner['module']]
        need(len(matches) == 1, 'Unique actual scope/module/checksum definition')
        bindings = []
        for n in matches[0].find('tglshape'):
            obj = dict(kind=n.tag, **n.attrib)
            role = 'target' if scope == source.SCOPE and n.get('name') == source.NAME else 'protected'
            if role == 'target':
                source.validate_node(n)
            suffix = mature.labels.bounds(obj)
            allowed = sorted(mature.labels.aliases(obj))
            width = 1 if n.tag == 'node' else abs(int(n.get('left')) - int(n.get('right'))) + 1 if n.tag == 'vectornode' else None
            bindings.append(dict(name=n.get('name'), kind=n.tag, attributes=dict(n.attrib), role=role,
                                 width=width, label=n.get('name') + suffix, allowed_labels=allowed))
        instance = dict(scope=scope, design_checksum=owner['module_checksum'], toggle_checksum=checks[scope],
                        compiled_shape_name=matches[0].get('name'), bindings=bindings)
        result += mature.singleton_aliases([instance])
    need(len(result) == 26 and len(result[0]['bindings']) == 552 and
         sum(len(i['bindings']) for i in result) == 987 and
         sum(b['role'] == 'target' for i in result for b in i['bindings']) == 1 and
         sum(b['kind'] == 'arrays' for i in result for b in i['bindings']) == 37, 'Complete target/complement closure')
    return result


def population(pins):
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    pins[str(BASE / 'admission-manifest.json')] = BASE_SHA
    ledger_path = BASE / 'combined-inputs.txt'
    pins[str(ledger_path)] = manifest['output_pins'][str(ledger_path)]
    life.check({str(ledger_path): pins[str(ledger_path)]})
    ledger = ledger_path.read_text().splitlines()
    need(manifest['coverage_admitted'] and len(ledger) == len(set(ledger)) == 776, 'Exact formal775 ledger')
    cache = life.read_bound(cache_source.CACHE, cache_source.CACHE_SHA)
    pins[str(cache_source.CACHE)] = cache_source.CACHE_SHA
    old = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    pins[str(old)] = cache['input_pins'][str(old)]
    life.check({str(old): pins[str(old)]})
    need(ledger[:742] == old.read_text().splitlines(), 'Exact validated cached741 prefix')
    merged = {source.SCOPE: {k: cache['instances'][source.SCOPE][k] for k in ('width', 'checksum', 'bits')}}
    samples = []
    for vdb in ledger[742:]:
        files = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(files) == 1 and str(files[0]) in manifest['input_pins'], 'One manifest-pinned actual Toggle sample')
        path = files[0]
        pins[str(path)] = manifest['input_pins'][str(path)]
        rows, sha = typed.rows(path, [source.SCOPE])
        need(sha == pins[str(path)], 'Actual sample pin drift')
        merged = typed.union(merged, rows)
        samples.append(str(path))
    need(len(samples) == 34 and len(set(samples)) == 34, 'Exact775 suffix34')
    row = merged[source.SCOPE]
    need(row['checksum'] == '2088425441', 'Parent compiled Toggle checksum')
    binary = format(int(row['bits'], 16), '0%db' % row['width'])
    need(binary[3422:3934] == '0' * 512, 'Target has observed hit; HOLD rather than exclude startup activity')
    full_config = FULL / 'config.json'
    pins[str(full_config)] = life.digest(full_config)
    config = json.loads(full_config.read_bytes())
    need(config['population'] == 775 and config['input_ledger'] == ledger and
         config['admission']['seal'] == BASE_SHA, 'Running full775 exact ledger authority')
    el = FULL / 'combined.el'
    pins[str(el)] = config['pins'][str(el)]
    life.check({str(el): pins[str(el)]})
    blocks = no_overlap(el.read_text())
    return dict(population=775, manifest_sha256=BASE_SHA, cached_prefix=741, actual_suffix=34,
                actual_suffix_files=samples, target_missing_positions=list(range(3422, 3934)),
                target_missing_slots=512, target_observed_hit_slots=0, scoped_actual_union=row,
                current_EL=str(el), current_EL_sha256=pins[str(el)], relevant_nonoverlap_blocks=blocks), ledger


def contract(c):
    review = life.read_bound(source.REPORT, REVIEW_SHA)
    need(c['instances'] == compiled(review) and c['source_review_sha256'] == REVIEW_SHA and
         c['population_evidence']['target_observed_hit_slots'] == 0 and
         c['timeout_seconds'] == 900 and not c['launch_authorized'] and not c['automatic_retry'] and
         not c['population_application'] and not c['initial_X_excluded'], 'Exact parent-only contract')


def inventory(out, c, stage, index):
    need(stage in STAGES and index in range(26), 'Exact scope/stage')
    inst = c['instances'][index]
    path = out / ('native_%s_%d.tsv' % (stage, index))
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        need(reader.fieldnames == ['handle', 'path', 'meta', 'name', 'excluded'], 'Exact full native schema')
        rows = list(reader)
    need(len(rows) == len(inst['bindings']), 'Complete native inventory including arrays')
    for key in ('handle', 'path', 'name'):
        need(len({r[key] for r in rows}) == len(rows), 'Duplicate native identity')
    aliases = {label: b for b in inst['bindings'] for label in b['allowed_labels']}
    need(len(aliases) == sum(len(b['allowed_labels']) for b in inst['bindings']), 'Alias collision')
    seen = set(); identities = []
    for row in rows:
        need(set(row) == set(reader.fieldnames) and all(row.values()) and row['handle'].isdigit()
             and row['path'] == row['meta'] == row['name'], 'Exact displayed path/meta identity')
        obj = aliases.get(row['name'])
        need(obj is not None and obj['name'] not in seen, 'Foreign, partial array, duplicate typed object')
        seen.add(obj['name'])
        need(row['excluded'] == str(int(stage in ('selected', 'reloaded') and obj['role'] == 'target')),
             'Target/protected object flag changed')
        identities.append([obj['name'], row['path'], row['meta'], row['name']])
    need(seen == {b['name'] for b in inst['bindings']}, 'Missing complete complement')
    result = sorted(identities)
    if stage != 'before':
        binding = json.loads((out / 'actual-binding.json').read_bytes())
        before = out / ('native_before_%d.tsv' % index)
        need(binding['config_seal'] == life.digest(out / 'config.json') and
             binding['before_pins'][str(before)] == life.digest(before) and
             result == binding['scopes'][index], 'Fresh-before identity drift')
    return result


def bind(out, c):
    all_scopes = [inventory(out, c, 'before', index) for index in range(26)]
    targets = [r[3] for r in all_scopes[0] if r[0] == source.NAME]
    need(targets == ['bit_enable_mask[255:0]'], 'Actual exact full vector only')
    text = ''.join('set ::re_targets(%d) [list %s]\n' % (k, ' '.join(mature.atom(t) for t in targets) if k == 0 else '')
                   for k in range(26))
    path = out / 'actual-selection.tcl'
    need(not path.exists() and not (out / 'actual-binding.json').exists(), 'Fresh actual binding only')
    path.write_text(text)
    life.save(out / 'actual-binding.json', dict(config_seal=life.digest(out / 'config.json'), scopes=all_scopes,
        before_pins={str(out / ('native_before_%d.tsv' % k)): life.digest(out / ('native_before_%d.tsv' % k)) for k in range(26)},
        actual_selection_sha256=life.digest(path), targets=1, protected=986))


def records(text, c):
    lines = [s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith('//')]
    inst = c['instances'][0]
    expected = ['CHECKSUM: "%s %s"' % (inst['design_checksum'], inst['toggle_checksum']),
                'INSTANCE: ' + source.SCOPE, 'ANNOTATION: "' + ANNOTATION + '"',
                'Toggle bit_enable_mask "logic bit_enable_mask[255:0]"']
    need(lines == expected, 'Only exact annotated whole internal vector; no other metric/partial/split/foreign/orphan')
    return [(source.SCOPE, source.NAME, 'logic bit_enable_mask[255:0]', ANNOTATION)]


def check_el(out, c, stage):
    need(stage in STAGES, 'Exact EL stage')
    text = (out / FILES[stage]).read_text()
    if stage in ('before', 'reset', 'final'):
        need(text == '', 'All-scope empty EL required')
        return []
    return records(text, c)


def inspect(out, seal):
    c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins'])
    terminal = json.loads((out / 'terminal.json').read_bytes())
    need(terminal['returncode'] == 0 and terminal['timeout'] is False and len(terminal['actual_dve']) == 1,
         'Actual native terminal0 without timeout, not DONE alone')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('MASKU_PARENT_ONLY_NATIVE_DONE') == 1 and 'MASKU_PARENT_ONLY_FAILED' not in log
         and not (out / 'error.txt').exists(), 'Incomplete/rejected native stages')
    for stage in STAGES:
        check_el(out, c, stage)
        for index in range(26):
            inventory(out, c, stage, index)
    need((out / 'cleanup-empty.el').read_bytes() == b'', 'Cleanup must remain empty')
    need(records((out / 'first.el').read_text(), c) == records((out / 'second.el').read_text(), c), 'Semantic reload')
    result = dict(status='MASKU_PARENT_BIT_ENABLE_ONLY_NATIVE_QUALIFIED_NOT_APPLIED', config_seal=seal,
        source_review_sha256=REVIEW_SHA, targets=1, bits=256, full_objects=987, protected=986,
        five_stages=True, initial_X_excluded=False, population_application=False, official_percentage=None,
        pins={str(p): life.digest(p) for p in out.rglob('*') if p.is_file() and
              p.name not in ('capture-result.json', 'service.log', 'worker.log')})
    path = out / 'capture-result.json'
    if path.exists():
        need(json.loads(path.read_bytes()) == result, 'Frozen result differs')
    else:
        life.save(path, result)
    print('MASKU_PARENT_ONLY_FIVE_STAGE_QUALIFIED_NOT_APPLIED')


def prepare(out):
    need(out.parent == source.OUT and not out.exists(), 'Fresh isolated preparation')
    review = life.read_bound(source.REPORT, REVIEW_SHA)
    need(source.collect() == review, 'Replay full frozen-source review')
    pins = dict(review['pins']); pins[str(source.REPORT)] = REVIEW_SHA
    evidence, ledger = population(pins)
    instances = compiled(review)
    sample = source.OUT / 'gap84-div32-old-image-20261006-01/code.vdb'
    need(str(sample) in ledger, 'Representative actual sample is admitted775')
    tests = list((sample / 'snps/coverage/db/testdata').iterdir())
    need(len(tests) == 1 and tests[0].is_dir(), 'One complete representative sample')
    for metric in ('line', 'cond', 'branch', 'fsm', 'tgl'):
        need((tests[0] / (metric + '.verilog.data.xml')).is_file(), 'Complete sample testdata')
    design = Path(ledger[0])
    closures = {}
    for role, vdb in (('design', design), ('sample', sample)):
        files = sorted(str(p) for p in vdb.rglob('*') if p.is_file())
        need(files, 'Nonempty actual VDB closure')
        closures[role] = files
        pins.update({p: life.digest(p) for p in files})
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).suffix == '.py' and Path(path).resolve().parent == HERE:
            pins[str(Path(path).resolve())] = life.digest(path)
    pending = [ENTRY]; visited = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path); pins[str(path)] = life.digest(path)
        pending += [Path(p) for p in re.findall(r'source\s+\{(/[^{}\n]+\.tcl)\}', path.read_text())]
    test = HERE / 'test_masku_parent_bit_enable_native775.py'
    pins[str(test)] = life.digest(test)
    c = dict(status='SOURCE_BOUND_FORMAL775_PARENT_ONLY_PREPARED_NOT_LAUNCHED_NOT_QUALIFIED',
        instances=instances, source_review_sha256=REVIEW_SHA, population_evidence=evidence,
        design=str(design), sample=str(sample), test=str(sample.with_suffix('') / tests[0].name),
        python=sys.executable, helper=str(Path(__file__).resolve()), output=str(out),
        timeout_seconds=900, launch_authorized=False, automatic_retry=False, population_application=False,
        initial_X_excluded=False, VDB_file_closures=closures, pins=pins)
    contract(c); life.check(pins); out.mkdir()
    (out / 'selection.tcl').write_text(mature.selection(c))
    pins[str(out / 'selection.tcl')] = life.digest(out / 'selection.tcl')
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'),
                         status=c['status'], missing_slots=512, protected=986)))


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins'])
    for role, files in c['VDB_file_closures'].items():
        need(sorted(str(p) for p in Path(c[role]).rglob('*') if p.is_file()) == files, 'VDB closure file-set drift')
    need((out / 'selection.tcl').read_text() == mature.selection(c), 'Plain absolute global selection')
    no_overlap(Path(c['population_evidence']['current_EL']).read_text())
    print('MASKU_PARENT_ONLY_STATIC_VERIFY_PASS_NOT_LAUNCHED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'verify-config', 'bind', 'inventory', 'el', 'selection', 'inspect'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal'); parser.add_argument('--stage', choices=STAGES); parser.add_argument('--index', type=int)
    args = parser.parse_args(); out = args.output.absolute()
    if args.mode == 'prepare':
        prepare(out)
    else:
        need(args.seal, 'Exact config seal')
        config = life.read_bound(out / 'config.json', args.seal)
        if args.mode == 'verify-config': verify(out, args.seal)
        elif args.mode == 'inspect': inspect(out, args.seal)
        elif args.mode == 'bind': bind(out, config)
        elif args.mode == 'inventory': inventory(out, config, args.stage, args.index)
        elif args.mode == 'el': check_el(out, config, args.stage)
        else:
            binding = json.loads((out / 'actual-binding.json').read_bytes())
            need(binding['config_seal'] == args.seal and binding['actual_selection_sha256'] ==
                 life.digest(out / 'actual-selection.tcl'), 'Actual-selection pin')
