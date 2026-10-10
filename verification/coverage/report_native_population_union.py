"""Sealed population successor; host prepare never starts DVE."""
import argparse
import copy
import csv
import importlib.util
import inspect
import json
from pathlib import Path
import re
import subprocess
from types import FunctionType, SimpleNamespace

import report_diagnostic_combo745 as frozen
import check_generated_report_tcl as generated

life, require = frozen.life, frozen.require
merge = frozen.prior.old.chain.merge_inventories
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
SCHEMA = 'SEALED_POPULATION_NATIVE_UNION_V1'
BASE = life.OUT / 'qualified-native-combo-diagnostic-full745-agent-20261007-01'
BASE_SHA = '69cdeba221f23874be91c266b5236b5b48c49c4836e8064fc29b4298e5b6231f'
CHILD = life.OUT / 'qbs-child-statistics-native-agent-20261007-01'
CHILD_SHA = '3fa51ba861639a7fb18f0d8a742257200b08d2e1897969a2a4f4186c7697cde4'
CAST = life.OUT / 'fpnew-cast-fp-shared168-native745-agent-20261007-04'
CAST_SHA = 'acf46cc867704929ba718e0cf7efd9ffe936de463081f84667f0b4cfa87fe41a'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')


def normalized(value):
    return json.loads(json.dumps(value))


def parser(path):
    spec = importlib.util.spec_from_file_location('union_private_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def blocks(text):
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        if not block.strip():
            continue
        scopes = re.findall(r'(?m)^INSTANCE: *(\S+)$', block)
        require(len(scopes) == 1, 'Unbound native block')
        yield scopes[0], block


def route(text, c):
    child = {i['scope']: {s['name'] for s in i['signals']} for i in c['child_config']['instances']}
    fma = {i['scope'] for i in c['active_fma_config']['instances']}
    cast = {i['scope'] for i in c['cast_config']['instances']}
    parts = {k: [] for k in ('prior', 'child', 'cast', 'fma')}
    for scope, block in blocks(text):
        header, body, pending, last = [], {k: [] for k in parts}, [], None
        for line in block.splitlines():
            if not line or line.startswith('//'):
                continue
            if line.startswith(('CHECKSUM:', 'INSTANCE:')):
                header.append(line)
            elif line.startswith('ANNOTATION:'):
                (body[last] if last else pending).append(line)
            else:
                m = re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?([\w.]+)(?:\s|\[|$)', line)
                family = ('fma' if m and scope in fma else 'cast' if m and scope in cast else
                          'child' if m and m[1] in child.get(scope, set()) else 'prior')
                body[family].extend(pending)
                pending = []
                body[family].append(line)
                last = family
        if not any(body.values()):
            parts['prior'].append(block)
        else:
            require(not pending, 'Orphan annotation')
            for family, lines in body.items():
                if lines:
                    parts[family].append('\n'.join(header + lines) + '\n')
    return {k: ''.join(v) for k, v in parts.items()}


def records(text, c):
    parts = route(text, c)
    # Frozen legacy parser validates all other policies. Its FMA108 placeholder is
    # separately pinned, removed from the returned tree, and never written to EL.
    legacy = frozen.records(parts['prior'] + c['legacy_fma_el'], c)
    require(len(legacy['prior']['original']['prior'][2]) == 108, 'Wrong legacy FMA reference')
    legacy['prior']['original']['prior'][2] = []
    if c['fma_mode'] == 'expanded612':
        fma = parser(HERE / 'fma_expanded_native_04.py').parse_el(parts['fma'], c['active_fma_config'])
    else:
        fma = frozen.prior.old.chain.fma.parse_el(parts['fma'], c['active_fma_config'])
    cast = parser(HERE / 'capture_cast168_native_typed.py').parse_el(parts['cast'], c['cast_config'])
    child = frozen.diagnostic.predecessor.namespace()['parse_el'](parts['child'], c['child_config'])
    return normalized(dict(retained=legacy, fma=fma, cast168=cast, child15=child))


def ownership(c):
    owners = {}
    families = [('child15', c['child_config'], 'signals'), ('cast168', c['cast_config'], 'targets'),
                ('fma', c['active_fma_config'], 'targets' if c['fma_mode'] == 'expanded612' else 'signals'),
                ('diagnostic224', c['diagnostic_config'], 'signals'),
                ('queue', c['queue_config'], 'signals'), ('c910', c['c910_config'], 'signals'),
                ('fp16', c['fp16_config'], 'signals')]
    for family, config, key in families:
        for i in config['instances']:
            for item in i[key]:
                identity = i['scope'], item['name']
                require(identity not in owners, 'Duplicate whole field/cross-policy overlap: ' + str(identity))
                require(not any(identity[0] == o or identity[0].startswith(o + '.') for o in c['observers']),
                        'Observer recursively overlaps datapath')
                owners[identity] = family
    return owners


def population(manifest, seal, reference):
    book = life.read_bound(manifest, seal)
    require(book['explicit_parent_authorized'] is True and book['output'] == str(manifest.parent),
            'Formal admission authority/output differs')
    pins = merge(book['input_pins'], book['output_pins'], {str(manifest): seal})
    life.check(pins)
    def output(name):
        p = manifest.parent / name
        require(str(p) in book['output_pins'], 'Unsealed formal output: ' + name)
        return life.read_bound(p, book['output_pins'][str(p)])
    bits, status = output('combined-bits.json'), output('status.json')
    n = status['aggregate_passed']
    require(type(n) is int and n in (760, 761, 762) and status['coverage_admitted'] is True and
            (status.get('exact_prefix') is True or status.get('exact%d_prefix' % (n - 1)) is True) and
            status['full_OR_instances'] == 6162,
            'Not admitted full6162 population760/761/762')
    ledger_path = manifest.parent / 'combined-inputs.txt'
    require(str(ledger_path) in book['output_pins'], 'Ledger not sealed')
    ledger = ledger_path.read_text().splitlines()
    require(len(bits['tests']) == len(set(bits['tests'])) == n and
            ledger == [reference['input_ledger'][0], *bits['tests']] and
            bits['tests'][:745] == reference['input_ledger'][1:], 'Exact745 prefix/unique ledger differs')
    previous_dir = Path(book['baseline'])
    previous_book = life.read_bound(previous_dir / 'admission-manifest.json', book['baseline_seal'])
    previous_path = previous_dir / 'combined-bits.json'
    previous_bits = life.read_bound(previous_path, previous_book['output_pins'][str(previous_path)])
    require(len(previous_bits['tests']) == n - 1 and bits['tests'][:-1] == previous_bits['tests'] and
            bits['design'] == previous_bits['design'], 'Immediate formal prefix differs')
    pins = merge(pins, {str(previous_dir / 'admission-manifest.json'): book['baseline_seal'],
                       str(previous_path): previous_book['output_pins'][str(previous_path)]})
    oldpath = frozen.prior.BASE / 'combined-bits.json'
    require(str(oldpath) in reference['pins'], 'Unsealed745 raw reference')
    oldbits = life.read_bound(oldpath, reference['pins'][str(oldpath)])
    require(bits['design'] == oldbits['design'], 'Compiled design differs')
    total = 0
    for metric, previous in oldbits['metrics'].items():
        actual = bits['metrics'][metric]
        require(set(actual) == set(previous), 'Metric hierarchy differs: ' + metric)
        total += len(actual)
        for scope, p in previous.items():
            r = actual[scope]
            require((r['width'], r['checksum']) == (p['width'], p['checksum']), 'Shape identity differs')
            value, before = int(r['bits'], 16), int(p['bits'], 16)
            require(value.bit_length() <= r['width'] and value >= 0 and not before & ~value,
                    'Lost prefix hit/bitmap overflow')
    require(total == 6162 and set(bits['metrics']) == set(oldbits['metrics']), 'Not complete6162 shapes')
    selected = []
    for vdb in ledger:
        for test in sorted((Path(vdb) / 'snps/coverage/db/testdata').glob('*')):
            if test.is_dir():
                selected.append(str(Path(vdb).with_suffix('') / test.name))
    require(len(selected) == len(set(selected)) == n, 'Ambiguous actual test selection')
    return n, ledger, selected, pins, dict(schema=book['schema'], seal=seal, manifest=str(manifest),
        combined_bits_sha=book['output_pins'][str(manifest.parent / 'combined-bits.json')],
        exact745prefix=True, full_shape_instances=total, admitted_OR_proof='SEALED_FORMAL_ADMISSION_NOT_RECOMPUTED')


def qualified_capture(out, sha, status):
    q = life.read_bound(out / 'capture-result.json', sha)
    require(q['status'] == status and q['semantic_reload'] is True and q['population_application'] is False,
            'Native qualification missing/failed/foreign')
    life.check(q['pins'])
    csha = q.get('config_seal', q['pins'].get(str(out / 'config.json')))
    c = life.read_bound(out / 'config.json', csha)
    return c, q, merge(q['pins'], {str(out / 'capture-result.json'): sha,
                                 str(out / 'config.json'): csha})


def table(path, columns):
    rows = frozen.prior.csv_rows(path, '\t')
    require(rows and rows[0] == columns and all(len(r) == len(columns) for r in rows[1:]),
            'Native table schema differs: ' + str(path))
    reference = [r[1:4] for r in rows[1:]]
    require(reference and len(reference) == len({tuple(r) for r in reference}), 'Ambiguous native complement')
    return reference


def prepare(out, manifest, seal, fma_out=None, fma_seal=None, runtime_ready=False):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent output only')
    q = life.read_bound(BASE / 'qualification.json', BASE_SHA)
    require(q['status'] == 'FULL745_WITH_DIAGNOSTIC_NATIVE_UNION_REPORT_VERIFIED' and q['population'] == 745,
            'Base report not qualified')
    c = life.read_bound(BASE / 'config.json', q['config_seal'])
    life.check(c['pins']); life.check(q['output_pins'])
    n, ledger, selected, pins, admission = population(manifest, seal, c)
    cc, cq, cpins = qualified_capture(CHILD, CHILD_SHA, 'QBS_CHILD_COMPLETE15_EXACT_NATIVE_ROUNDTRIP_PASS')
    require(cq['objects'] == 15 and cq['bit_directions'] == 798 and cq['all_non_targets_protected'] and
            cq['global_final_empty'] and cq['actual_occupancy_control_retained'] and
            not cq['runtime_checks_disabled'], 'Child15 gates differ')
    cast, castq, castpins = qualified_capture(CAST, CAST_SHA, 'EXACT_CAST168_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED')
    require(castq['objects'] == 168 and castq['logical_bits'] == 9576 and castq['protected_local_objects'] == 2064 and
            castq['global_final_reset_empty'] and castq['all_children_retained'] and
            castq['both_directions_whole_objects'] and not castq['exhaustive_IEEE'], 'Cast scope gates differ')
    cp = parser(HERE / 'capture_cast168_native_typed.py')
    require(cp.parse_el((CAST / 'first.el').read_text(), cast) == cp.parse_el((CAST / 'second.el').read_text(), cast),
            'Cast semantic reload differs')
    require(frozen.diagnostic.predecessor.namespace()['parse_el']((CHILD / 'first.el').read_text(), cc) ==
            frozen.diagnostic.predecessor.namespace()['parse_el']((CHILD / 'second.el').read_text(), cc),
            'Child semantic reload differs')
    config = copy.deepcopy(c)
    config.update(schema=SCHEMA, population=n, output=str(out), successor_entry=str(Path(__file__).resolve()),
        input_ledger=ledger, expected_selected=selected, admission=admission, child_config=cc, cast_config=cast,
        fma_mode='retained108', active_fma_config=c['fma_config'], child_references=[],
        runtime_apply_authorized=runtime_ready, runtime_timeout_seconds=3600,
        official_denominator_verified=False, exhaustive_IEEE=False, runtime_checks_disabled=False,
        host_prepare_is_not_native_qualification=True)
    parts = list(blocks((BASE / 'applied.el').read_text()))
    fma_scopes = {i['scope'] for i in c['fma_config']['instances']}
    config['legacy_fma_el'] = ''.join(b for s, b in parts if s in fma_scopes)
    combined = ''.join(b for s, b in parts if s not in fma_scopes)
    fma_text = config['legacy_fma_el']
    native_pins = merge(cpins, castpins)
    if fma_out is not None:
        require(fma_seal, 'Explicit FMA qualification seal required')
        fc, fq, fpins = qualified_capture(fma_out, fma_seal, 'EXACT_612_FMA_EXPANDED_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS')
        require(fq['objects'] == 612 and fq['logical_bits'] == 26064 and fq['both_directions'] and
                fq['reset_global_empty'] and fq['non_target_exclusions'] == 0 and
                fq['all_nontarget_complement_retained'] and fq['all_descendants_retained'] and
                fq['complete_source_type_identity_retained'], 'Expanded FMA full native gates differ')
        fp = parser(HERE / 'fma_expanded_native_04.py')
        require(fp.parse_el((fma_out / 'first.el').read_text(), fc) ==
                fp.parse_el((fma_out / 'second.el').read_text(), fc), 'Expanded semantic reload differs')
        previous = {(i['scope'], s['name'], s['left'], s['right']) for i in c['fma_config']['instances'] for s in i['signals']}
        new = {(i['scope'], t['name'], *t['dimensions'][0]) for i in fc['instances'] for t in i['targets']
               if len(t['dimensions']) == 1}
        require(len(previous) == 108 and previous <= new, 'Expanded does not contain exact original108 bounds')
        config.update(fma_mode='expanded612', active_fma_config=fc, fma_capture_seal=fma_seal)
        fma_text = (fma_out / 'first.el').read_text()
        native_pins = merge(native_pins, fpins)
        for group in config['toggle_groups']:
            if group['policy'] == 'fma':
                instance = next(i for i in fc['instances'] if i['scope'] == group['scope'])
                reference = table(fma_out / ('native_initial_%d.tsv' % group['index']), ['handle', 'path', 'meta', 'name'])
                targets = [t['native_name'] for t in instance['targets']]
                group.update(reference=sorted(reference), targets=targets,
                             protected=[r[2] for r in reference if r[2] not in targets])
    combined += fma_text + (CHILD / 'first.el').read_text() + (CAST / 'first.el').read_text()
    ownership(config)
    config['expected_union'] = records(combined, config)
    require(len(config['expected_union']['child15']) == 798 and len(config['expected_union']['cast168']) == 168 and
            len(config['expected_union']['fma']) == (612 if fma_out else 108), 'Canonical union size differs')
    original = copy.deepcopy(c['expected_union'])
    original['prior']['original']['prior'][2] = []
    require(config['expected_union']['retained'] == original, 'Other qualified policies changed')
    atom = frozen.prior.old.base.capture.tcl_atom
    selection = (BASE / 'selection.tcl').read_text() + '\nset child_instances {}\n'
    for index, i in enumerate(cc['instances']):
        reference = table(CHILD / ('native_before_%d.tsv' % index), ['handle', 'path', 'meta', 'name', 'column1', 'column2'])
        config['child_references'].append(reference)
        labels = [s['native_label'] for s in i['signals']]
        require(all([r[2] for r in reference].count(n) == 1 for n in labels), 'Child native target missing')
        selection += 'lappend child_instances [list %s [list %s]]\n' % (atom(i['scope']), ' '.join(map(atom, labels)))
    for index, i in enumerate(cast['instances']):
        reference = cp.v2.inventory(CAST, cast, 'before', index)
        require(all(cp.v2.inventory(CAST, cast, s, index) == reference for s in STAGES), 'Cast native five-stage drift')
        targets = [t['native_name'] for t in i['targets']]
        config['toggle_groups'].append(dict(policy='cast168', index=index, scope=i['scope'], targets=targets,
            protected=i['protected'], reference=normalized(reference)))
    selection += 'set combo_groups {}\n'
    for index, group in enumerate(config['toggle_groups']):
        labels = [r[2] for r in group['reference']]
        require(len(labels) == len(set(labels)) and set(labels) == set(group['targets']) | set(group['protected']) and
                not set(group['targets']) & set(group['protected']), 'Not exact target/protected partition')
        selection += 'lappend combo_groups [list %s %d [list %s]]\n' % (atom(group['scope']), index, ' '.join(map(atom, labels)))
    for i in cc['instances'] + cast['instances']:
        if i['scope'] not in {r['scope'] for r in config['hierarchy_roots']}:
            root = dict(scope=i['scope'], name=i['scope'].split('.')[-1])
            config['hierarchy_roots'].append(root)
            selection += 'lappend report745_roots [list %s %s]\n' % (atom(root['scope']), atom(root['name']))
    dependencies = [Path(__file__).resolve(), TCL, HERE / 'test_report_native_population_union.py',
                    Path(generated.__file__), HERE / 'check_generated_tcl.py',
                    HERE / 'verify_cast168_native_offline.py', HERE / 'capture_cast168_native_typed.py',
                    HERE / 'capture_cast168_native_v2.py', HERE / 'capture_cast168_native_entry.py']
    if fma_out:
        dependencies.extend([HERE / 'fma_expanded_native_04.py', HERE / 'verify_fma612_native_offline.py'])
    pins = merge(pins, c['pins'], q['output_pins'], native_pins,
        {str(BASE / 'qualification.json'): BASE_SHA, str(BASE / 'config.json'): q['config_seal']},
        {str(p): life.digest(p) for p in dependencies})
    life.check(pins)
    out.mkdir()
    # Text files deliberately bypass the JSON writer. Check actual bytes after write.
    for name, text in [('selection.tcl', selection), ('combined.el', combined), ('inputs.txt', '\n'.join(ledger) + '\n')]:
        with (out / name).open('x') as stream:
            stream.write(text)
        require((out / name).read_bytes() == text.encode('ascii'), 'Generated text serialization differs')
        pins[str(out / name)] = life.digest(out / name)
    evaluation = generated.evaluate(out / 'selection.tcl', {str(out / 'selection.tcl'): pins[str(out / 'selection.tcl')]},
        ('combo_groups', 'diagnostic_instances', 'child_instances', 'report745_roots', 'fx_groups'))
    syntax = parser(HERE / 'check_generated_tcl.py')
    syntax_checks = [syntax.check(out / 'selection.tcl'), syntax.check(TCL)]
    # Source the actual entry and actual generated selection through the full GUI
    # stub regression; no native or product coverage claim is made by this test.
    from test_report_native_population_union import actual_hook_regression
    hook = actual_hook_regression(out / 'selection.tcl', config)
    life.save(out / 'host-generated-tcl-evidence.json', dict(selection=evaluation, hook=hook, syntax_checks=syntax_checks,
        no_EDA=True, native_qualification=False, report_percentages=None))
    pins[str(out / 'host-generated-tcl-evidence.json')] = life.digest(out / 'host-generated-tcl-evidence.json')
    config['pins'] = pins
    life.check(pins)
    life.save(out / 'config.json', config)
    print(json.dumps(dict(status='PREPARED_HOST_ONLY_NO_DVE' if not runtime_ready else 'PREPARED_NO_DVE',
        output=str(out), seal=life.digest(out / 'config.json'), population=n, fma_mode=config['fma_mode'],
        child_fields=15, cast_fields=168, pins=len(pins))), flush=True)


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(c['schema'] == SCHEMA and c['output'] == str(out) and c['population'] in (760, 761, 762) and
            c['successor_entry'] == str(Path(__file__).resolve()) and c['runtime_timeout_seconds'] == 3600,
            'Wrong successor schema/output/entry/population')
    life.check(c['pins'])
    require((out / 'inputs.txt').read_text().splitlines() == c['input_ledger'] and
            len(c['expected_selected']) == len(set(c['expected_selected'])) == c['population'], 'Population identity differs')
    ownership(c)
    require(records((out / 'combined.el').read_text(), c) == c['expected_union'], 'Canonical union drift')
    return c


def audit_six(out, prefix, references):
    for index, reference in enumerate(references):
        for stage in STAGES:
            require(table(out / ('%s_%s_%d.tsv' % (prefix, stage, index)),
                ['handle', 'path', 'meta', 'name', 'column1', 'column2']) == reference,
                'Five-stage full target/protected identity differs')


def verify(out, seal):
    c = check(out, seal)
    audit_six(out, 'native', c['queue_references'])
    audit_six(out, 'diagnostic', c['diagnostic_references'])
    audit_six(out, 'child', c['child_references'])
    reports = {}
    for stage in frozen.prior.STAGES:
        rows = frozen.prior.dict_rows(out / ('modules_' + stage + '.csv'))
        require(rows and list(rows[0]) == ['Stage', 'Scope', 'Token', 'Handle', 'GUIPath', 'Name',
            'Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch'], 'Module report schema differs')
        require([(r['Scope'], r['Name']) for r in rows] == [(r['scope'], r['name']) for r in c['hierarchy_roots']] and
                all(r['Token'] == r['Scope'] and r['GUIPath'] == r['Name'] and r['Stage'] == stage for r in rows),
                'Module hierarchy identity differs')
        reports[stage] = {r['Scope']: {m: r[m] for m in frozen.prior.old.base.native.METRICS} for r in rows}
    require(reports['raw'] == reports['reset'] == reports['final'] and
            reports['applied'] == reports['reloaded'], 'Same-session reports differ')
    def save(path, data):
        require(path == out / 'qualification.json', 'Unexpected verifier output')
        data.update(status='SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED', population=c['population'],
            admission=c['admission'], fma_objects=len(c['expected_union']['fma']), child_fields=15, cast_fields=168,
            module_reports=reports, actual_population_i_system=data['system'], exhaustive_IEEE=False,
            integration_scope_not_new_RTL_signoff=True, runtime_checks_disabled=False)
        if path.exists():
            require(json.loads(path.read_bytes()) == data, 'Sealed result differs')
        else:
            life.save(path, data)
    core = frozen.prior.inherited.original_verify
    require(Path(core.__code__.co_filename).name == 'report_c910_combo742.py', 'Not substantive native verifier')
    ns = dict(core.__globals__, records=records, life=SimpleNamespace(**{**vars(life), 'save': save}))
    FunctionType(core.__code__, ns)(out, seal)


def run(out, seal):
    c = check(out, seal)
    require(c['runtime_apply_authorized'] is True, 'Host rehearsal cannot launch DVE')
    def popen(*args, **kwargs):
        return subprocess.Popen(*args, **dict(kwargs, env=dict(kwargs['env'], DVE_REVIEWED_WAIVERS=str(TCL))))
    base = frozen.prior.old.base
    body = inspect.getsource(base.run)
    require(body.count('process.wait(timeout=900)') == 1, 'Lifecycle budget anchor differs')
    body = body.replace('process.wait(timeout=900)', 'process.wait(timeout=c[\'runtime_timeout_seconds\'])')
    ns = dict(base.run.__globals__, verify=verify, subprocess=SimpleNamespace(**{**vars(subprocess), 'Popen': popen}))
    exec(compile(body, str(Path(base.__file__).resolve()), 'exec'), ns)
    ns['run'](out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'verify', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--manifest', type=Path)
    p.add_argument('--manifest-seal')
    p.add_argument('--fma-output', type=Path)
    p.add_argument('--fma-seal')
    p.add_argument('--runtime-ready', action='store_true')
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare':
        require(a.manifest and a.manifest_seal, 'Formal manifest and seal required')
        prepare(out, a.manifest.resolve(), a.manifest_seal,
                a.fma_output.resolve() if a.fma_output else None, a.fma_seal, a.runtime_ready)
    else:
        require(a.seal, 'Exact config seal required')
        if a.mode == 'check':
            check(out, a.seal); print('SEALED_POPULATION_UNION_CHECK_PASS_NO_DVE')
        else:
            (verify if a.mode == 'verify' else run)(out, a.seal)
