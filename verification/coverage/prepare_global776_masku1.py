"""Prepare-only delta consumer of sealed775: exact776 population plus MASKU1.

No EDA entrypoint. The 188MB predecessor config is referenced, not copied.
All retained global parsers/observers execute unchanged in private views.
"""
import argparse
import csv
import inspect
import json
from pathlib import Path
import re
from types import FunctionType

import report_native_full775 as prior
import run_masku_parent_bit_enable_native775 as strict

life, need = prior.life, prior.need
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
SCHEMA = 'GLOBAL776_MASKU_PARENT1_BY_REFERENCE_PREPARE_V1'
BASE = life.OUT / 'vfirst-offline-admitted776-parent-20261007-01'
BASE_SHA = '85abeb09ddfc3c4ddbfc43eefa7c71d860932dd66af572edac0bd7030ce3c33c'
OLD = strict.qualification.FULL
OLD_SHA = strict.FULL_SHA
Q = strict.OUT
QUAL_SHA = '4b0066d021c80c7b08c3f1a2ecc3ed55a9dd44f926c1772847128ee88a7ee61a'
LAUNCH = life.OUT / 'masku-parent-only-launch-parent-20261007-01/launch-manifest.json'
LAUNCH_SHA = '4b159e76a882e31503c599ed72499242be1c16c0354da9c99acb4e3a114d1ea6'
RECEIPT = LAUNCH.parent / 'strict-inspection-receipt.json'
RECEIPT_SHA = 'f9fac6a46acd87c2d2e58adabb659bc90cc896a8581d8632353f0208e4c19035'
NATIVE_EL_SHA = 'dc989caebe5bd8a73b1e79f7290280f9b0267e9f4c90bdff93fdbd6bfa4ae65a'
PRIOR_PINS = {
    str(Path(prior.__file__).resolve()): 'fe3f313310e269097d6a996b7d2a216c8b6f7e8d8a55fddf2c8916b1083afbdf',
    str(prior.TCL): 'bc7746666b8b6a9964d78c0d4ac7894e12f6ef0946a70cb2924d538a47052e10',
}
STAGES = prior.STAGES
OTHER_SOURCE_FIRST = life.OUT / 'masku-vl-zero2-sourcefirst770-candidate-agent-20261007-01/config.json'
OTHER_SOURCE_FIRST_SHA = 'aaf018fa065416ac09b526b9e4762c4a59cef05901b82052316336d0c7223ff7'


def unexpanded_objects(native):
    pending = life.read_bound(OTHER_SOURCE_FIRST, OTHER_SOURCE_FIRST_SHA)
    need(pending['local_qualified'] is False and pending['ready_for_union'] is False and
         pending['qualification_seal'] is None and pending['native_reference'] is None,
         'Prior two internal source-first candidates are not native qualification')
    inst = next(i for i in native['instances'] if i['scope'] == strict.qualification.source.prior.SCOPE)
    result = []
    for name, line, port in [('deshuffled_vl_bit_mask', '71', '0'),
                             ('shuffled_vl_bit_mask', '72', '0'), ('bit_enable_mask_o', '60', '3')]:
        b = next(b for b in inst['bindings'] if b['name'] == name)
        a = b['attributes']
        need(b['role'] == 'protected' and b['width'] == 256 and b['kind'] == 'vectornode' and
             a['file'] == '558' and a['line_num'] == line and a['portnode'] == port and
             (a['left'], a['right'], a['type']) == ('255', '0', '1'), 'Exact unexpanded child identity')
        result.append(dict(scope=inst['scope'], name=name, bounds=[255, 0], bits=256,
            native_label=b['label'], toggle_checksum=inst['toggle_checksum'],
            design_checksum=inst['design_checksum'], source_file='hardware/src/masku/masku_operands.sv',
            source_declaration_line=int(line), portnode=int(port), settled_source_constant=0,
            constant_driver='Literal VlBitMaskEnable0 disables nonzero writes; whole-zero defaults/else; output &= cannot set zero.',
            in775_EL=False, qualified_by_parent1=False, selected_in776_successor=False,
            prior_source_first_native_qualified=False if port == '0' else None,
            disposition='SOURCE_PROVEN_ONLY_TURING_OWNERSHIP' if port == '0' else 'OUTPUT_PORT_PROTECTED_NOT_ADDED'))
    return result


def retained_equal(view, old):
    changed = {'schema', 'output', 'population', 'successor_entry', 'admission',
               'input_ledger', 'expected_selected', 'pins'}
    need(all(view.get(k) == v for k, v in old.items() if k not in changed),
         'Retained775 policies/bindings/parsers changed')


def hydrate(delta):
    need(delta['schema'] == SCHEMA and delta['reused775_config'] == str(OLD / 'config.json') and
         delta['reused775_config_sha256'] == OLD_SHA and delta['population'] == 776 and
         delta['successor_entry'] == str(Path(__file__).resolve()) and delta['EDA_launched'] is False,
         'Exact by-reference delta consumer')
    old = life.read_bound(OLD / 'config.json', OLD_SHA)
    c = dict(old, **delta)
    c['pins'] = prior.prior.merge(old['pins'], delta['pins'], {str(OLD / 'config.json'): OLD_SHA})
    retained_equal(c, old)
    return c


def masku(c):
    ref = c['masku776']
    need(ref == dict(config=str(Q / 'config.json'), config_seal=strict.NATIVE_SHA,
                    qualified=str(Q / 'capture-result.json'), qualified_seal=QUAL_SHA,
                    receipt=str(RECEIPT), receipt_seal=RECEIPT_SHA,
                    binding=str(Q / 'actual-binding.json'), first_EL=str(Q / 'first.el'),
                    first_EL_sha256=NATIVE_EL_SHA), 'Exact qualified family, no substituted config/EL')
    native = life.read_bound(Q / 'config.json', strict.NATIVE_SHA)
    qualified = life.read_bound(Q / 'capture-result.json', QUAL_SHA)
    receipt = life.read_bound(RECEIPT, RECEIPT_SHA)
    need(qualified['targets'] == 1 and qualified['protected'] == 986 and qualified['full_objects'] == 987
         and qualified['five_stages'] is True and qualified['initial_X_excluded'] is False and
         qualified['population_application'] is False and receipt['native_result_sha256'] == QUAL_SHA
         and receipt['launch_manifest_sha256'] == LAUNCH_SHA and receipt['exact_integer_terminal0'] is True,
         'Complete strict qualification closure')
    binding = json.loads((Q / 'actual-binding.json').read_bytes())
    need(binding['config_seal'] == strict.NATIVE_SHA and binding['targets'] == 1 and
         binding['protected'] == 986 and len(binding['scopes']) == 26, 'Actual987 scope binding')
    return native, binding


def split_masku(text):
    result = prior.partition(text, {'masku': {(strict.qualification.source.SCOPE, 'bit_enable_mask')}})
    return result['retained'], result['masku']


def records(text, c):
    retained, added = split_masku(text)
    native, _ = masku(c)
    expected = strict.qualification.records((Q / 'first.el').read_text(), native)
    need(strict.qualification.records(added, native) == expected, 'Exact MASKU1 member union')
    # The original full775 parser remains authoritative for every retained metric.
    return prior.records(retained, c)


def masku_rows(rows, native, reference, index, stage, before=None):
    need(index in range(26) and stage in STAGES, 'Exact five-stage scope')
    inst = native['instances'][index]
    refs = reference['scopes'][index]
    need(len(rows) == len(refs) == len(inst['bindings']), 'Complete987 full complement')
    need(len({r['handle'] for r in rows}) == len(rows), 'Unique actual native tokens')
    expected = {b['name']: b for b in inst['bindings']}
    by_label = {r[3]: r for r in refs}
    need(len(by_label) == len(refs), 'Unique sealed displayed identities')
    seen = set()
    for row in rows:
        need(row['handle'].isdigit() and row['name'] == row['path'] == row['meta']
             and row['name'] in by_label, 'Foreign/partial/flattened native object')
        ref = by_label[row['name']]
        need([row['path'], row['meta'], row['name']] == ref[1:] and ref[0] not in seen,
             'Exact source-bound native identity, no duplicate')
        seen.add(ref[0]); obj = expected[ref[0]]
        need(row['excluded'] == str(int(stage in ('selected', 'reloaded') and obj['role'] == 'target')),
             'MASKU target/protected/port flag changed')
        need(row['type'] and row['display'], 'Actual native type/display columns required')
    need(seen == set(expected), 'Missing typed protection')
    if before is not None:
        keys = ('path', 'meta', 'name', 'type', 'display')
        need(sorted(tuple(r[k] for k in keys) for r in rows) ==
             sorted(tuple(r[k] for k in keys) for r in before), 'Five-stage identity/type/display drift')


def inventories(out, c):
    native, reference = masku(c)
    for index in range(26):
        before = None
        for stage in STAGES:
            path = out / ('masku776_%s_%d.tsv' % (stage, index))
            with path.open(newline='') as stream:
                reader = csv.DictReader(stream, delimiter='\t')
                need(reader.fieldnames == ['handle', 'path', 'meta', 'name', 'type', 'coverage', 'display', 'excluded'],
                     'Complete mature native column schema')
                rows = list(reader)
            need(all(set(r) == set(reader.fieldnames) and all(r.values()) for r in rows), 'Missing native cells')
            masku_rows(rows, native, reference, index, stage, before)
            if before is None: before = rows


def observers(out, c):
    namespace = dict(prior.observers.__globals__, records=records)
    retained = FunctionType(prior.observers.__code__, namespace)
    proof = retained(out, c)
    inventories(out, c)
    return dict(retained775=proof, masku_target=1, full_objects=987, protected=986,
                all_five_stages=True, no_Xstartup_exclusion=True)


class ViewLife:
    """Only the new delta-config read is hydrated; no sealed module is mutated."""
    def __getattr__(self, name): return getattr(life, name)

    def read_bound(self, path, sha):
        data = life.read_bound(path, sha)
        return hydrate(data) if Path(path).name == 'config.json' and isinstance(data, dict) and data.get('schema') == SCHEMA else data


def inherited_check(out, seal):
    text = inspect.getsource(prior.check)
    changes = {"c['population']==775": "c['population']==776",
               "==775,'Actual775 full population'": "==776,'Actual776 full population'"}
    for old, new in changes.items():
        need(text.count(old) == 1, 'Exact population adapter anchor')
        text = text.replace(old, new)
    namespace = dict(vars(prior), life=ViewLife(), records=records, __file__=__file__, SCHEMA=SCHEMA,
                     BASE=BASE, BASE_SHA=BASE_SHA)
    exec(compile(text, __file__ + ':private775-check', 'exec'), namespace)
    return namespace['check'](out, seal)


def check(out, seal):
    delta = life.read_bound(out / 'config.json', seal)
    c = hydrate(delta)
    need(c['output'] == str(out) and c['admission'] == dict(manifest=str(BASE / 'admission-manifest.json'),
         seal=BASE_SHA, population=776, exact775prefix=True, full6162_OR=True), 'Exact776 admission contract')
    need(c['host_prepare_is_not_native_qualification'] is True and c['parent_launch_approval_required'] is True,
         'No preparation masquerading as native qualification')
    life.check(c['pins'])
    old = life.read_bound(OLD / 'config.json', OLD_SHA)
    m = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    need(m['coverage_admitted'] is True and m['baseline'] == str(prior.BASE) and
         m['baseline_seal'] == prior.BASE_SHA, 'Exact775 predecessor')
    a = life.read_bound(prior.BASE / 'combined-bits.json', c['pins'][str(prior.BASE / 'combined-bits.json')])
    b = life.read_bound(BASE / 'combined-bits.json', c['pins'][str(BASE / 'combined-bits.json')])
    single = life.read_bound(BASE / 'single-bits.json', c['pins'][str(BASE / 'single-bits.json')])
    prior.population(a, b, single, 776)
    need(c['input_ledger'] == [old['input_ledger'][0], *b['tests']] and
         c['input_ledger'][:-1] == old['input_ledger'], 'Unchanged exact775 ledger prefix')
    native, _ = masku(c)
    need(c['unexpanded_MASKU_child_objects'] == unexpanded_objects(native), 'Unexpanded child audit changed')
    added = (Q / 'first.el').read_text()
    retained, extracted = split_masku((out / 'combined.el').read_text())
    need(strict.qualification.records(extracted, native) == strict.qualification.records(added, native), 'Exact added EL')
    need(prior.records(retained, c) == prior.records((OLD / 'combined.el').read_text(), old),
         'Retained EL metrics changed/lost')
    strict.qualification.no_overlap(retained)
    need((out / 'selection.tcl').read_text() == (OLD / 'selection.tcl').read_text() +
         '\nset ::full776_masku_scopes [list %s]\n' % ' '.join(prior.prior.tcl_atom(i['scope']) for i in native['instances']),
         'Reuse original selection, add exact26 scopes only')
    inherited_check(out, seal)
    return c


def snapshot(data, out):
    c = ViewLife().read_bound(out / 'config.json', data['config_seal'])
    inherited = prior.namespace()['snapshot_stdout']
    private = dict(inherited.__globals__, life=ViewLife())
    FunctionType(inherited.__code__, private, inherited.__name__, inherited.__defaults__, inherited.__closure__)(data, out)
    data['formal775_predecessor_manifest_seal'] = data.pop('formal775_manifest_seal')
    data.update(population=776, admission=c['admission'], formal776_manifest_seal=BASE_SHA,
        additional_qualified_families=data['additional_qualified_families'] + ['masku_parent1'],
        MASKU_targets=1, MASKU_full_objects=987, MASKU_protected=986,
        MASKU_local_qualification_sha256=QUAL_SHA, MASKU_strict_receipt_sha256=RECEIPT_SHA,
        MASKU_initial_X_excluded=False, raw_slots_not_used_as_denominator=True)
    extra = {str(p): life.digest(p) for p in out.glob('masku776_*.tsv')}
    need(len(extra) == 26 * 5, 'All130 fresh MASKU inventories must be sealed')
    data['output_pins'] = prior.prior.merge(data['output_pins'], extra)


def namespace():
    # Deliberately expose no run method in this prepare-only successor.
    ns = prior.namespace()
    ns.update(life=ViewLife(), check=check, records=records, audit_observers=observers,
              snapshot_stdout=snapshot, TCL=TCL, __file__=__file__)
    ns['verify'] = FunctionType(ns['verify'].__code__, ns)
    ns.pop('run', None)
    return ns


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh776 independent preparation only')
    life.check(PRIOR_PINS)
    old = prior.check(OLD, OLD_SHA)
    need((Q / 'capture-result.json').exists() and RECEIPT.exists(), 'Existing qualification required, no recreation')
    strict.strict_inspect(Q, strict.NATIVE_SHA, LAUNCH, LAUNCH_SHA)
    q = life.read_bound(Q / 'capture-result.json', QUAL_SHA)
    launch = life.read_bound(LAUNCH, LAUNCH_SHA)
    native = life.read_bound(Q / 'config.json', strict.NATIVE_SHA)
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    need(manifest['coverage_admitted'] is True and manifest['baseline'] == str(prior.BASE) and
         manifest['baseline_seal'] == prior.BASE_SHA, 'Exact776 actual admission')
    pins = prior.prior.merge(manifest['input_pins'], manifest['output_pins'], q['pins'], launch['pins'], PRIOR_PINS,
        {str(BASE / 'admission-manifest.json'): BASE_SHA, str(OLD / 'config.json'): OLD_SHA,
         str(Q / 'capture-result.json'): QUAL_SHA, str(RECEIPT): RECEIPT_SHA, str(LAUNCH): LAUNCH_SHA,
         str(OTHER_SOURCE_FIRST): OTHER_SOURCE_FIRST_SHA})
    bits = life.read_bound(BASE / 'combined-bits.json', pins[str(BASE / 'combined-bits.json')])
    previous = life.read_bound(prior.BASE / 'combined-bits.json', old['pins'][str(prior.BASE / 'combined-bits.json')])
    prior.population(previous, bits, life.read_bound(BASE / 'single-bits.json', pins[str(BASE / 'single-bits.json')]), 776)
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    need(ledger == [old['input_ledger'][0], *bits['tests']] and ledger[:-1] == old['input_ledger'], 'Exact775 prefix')
    status = life.read_bound(BASE / 'status.json', pins[str(BASE / 'status.json')])
    need(status['aggregate_passed'] == 776 and status['coverage_admitted'] is True and
         status['full_OR_metric_instances'] == 6162, 'Formal776 terminal PASS')
    added = (Q / 'first.el').read_text()
    need(life.digest(Q / 'first.el') == life.digest(Q / 'second.el') == NATIVE_EL_SHA, 'Authoritative local EL')
    strict.qualification.no_overlap((OLD / 'combined.el').read_text())
    # Reuse qualified exact775 scoped union, add only the actual776 sample.
    vdb = Path(ledger[-1]); files = list((vdb / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(files) == 1 and str(files[0]) in pins, 'One bound actual776 Toggle sample')
    rows, sha = strict.qualification.typed.rows(files[0], [strict.qualification.source.SCOPE])
    need(sha == pins[str(files[0])], 'Actual776 Toggle pin')
    union = strict.qualification.typed.union(
        {strict.qualification.source.SCOPE: native['population_evidence']['scoped_actual_union']}, rows)
    row = union[strict.qualification.source.SCOPE]
    need(format(int(row['bits'], 16), '0%db' % row['width'])[3422:3934] == '0' * 512,
         'Actual776 target hit/startup activity: HOLD')
    config = dict(schema=SCHEMA, output=str(out), population=776, successor_entry=str(Path(__file__).resolve()),
        reused775_config=str(OLD / 'config.json'), reused775_config_sha256=OLD_SHA,
        admission=dict(manifest=str(BASE / 'admission-manifest.json'), seal=BASE_SHA, population=776,
                       exact775prefix=True, full6162_OR=True),
        input_ledger=ledger, expected_selected=[str(Path(db).with_suffix('') / p.name) for db in ledger
            for p in sorted((Path(db) / 'snps/coverage/db/testdata').glob('*')) if p.is_dir()],
        masku776=dict(config=str(Q / 'config.json'), config_seal=strict.NATIVE_SHA,
                      qualified=str(Q / 'capture-result.json'), qualified_seal=QUAL_SHA,
                      receipt=str(RECEIPT), receipt_seal=RECEIPT_SHA, binding=str(Q / 'actual-binding.json'),
                      first_EL=str(Q / 'first.el'), first_EL_sha256=NATIVE_EL_SHA),
        masku_raw776=dict(sample=str(files[0]), union=row, missing_slots=512,
                         positions=list(range(3422, 3934)), denominator_claim=False),
        unexpanded_MASKU_child_objects=unexpanded_objects(native),
        EDA_launched=False, pins=pins)
    files = [Path(__file__).resolve(), TCL, HERE / 'test_prepare_global776_masku1.py', Path(strict.__file__).resolve(),
             Path(strict.qualification.__file__).resolve()]
    pins.update({str(p): life.digest(p) for p in files})
    selection = (OLD / 'selection.tcl').read_text() + '\nset ::full776_masku_scopes [list %s]\n' % ' '.join(
        prior.prior.tcl_atom(i['scope']) for i in native['instances'])
    view = hydrate(config)
    need(records((OLD / 'combined.el').read_text() + added, view) == old['expected_union'], 'Exact retained+MASKU union')
    life.check(view['pins']); out.mkdir()
    for name, value in [('combined.el', (OLD / 'combined.el').read_text() + added),
                        ('selection.tcl', selection), ('inputs.txt', '\n'.join(ledger) + '\n')]:
        (out / name).write_text(value); pins[str(out / name)] = life.digest(out / name)
    life.save(out / 'config.json', config)
    seal = life.digest(out / 'config.json'); check(out, seal)
    receipt = dict(status='GLOBAL776_MASKU1_PREPARED_CHECK_PASS_NO_EDA', config_seal=seal,
        predecessor_config_sha256=OLD_SHA, masku_qualified_sha256=QUAL_SHA,
        targets=1, protected=986, scopes=26, fresh_inventory_files_required=130,
        predecessor_bindings_copied=False, EDA_launched=False, native_qualification_of_global=False,
        official_percentage=None)
    life.save(out / 'prepare-receipt.json', receipt)
    print(json.dumps(dict(output=str(out), config_seal=seal, prepare_receipt_seal=life.digest(out / 'prepare-receipt.json'),
                         status=receipt['status'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    args = parser.parse_args(); out = args.output.resolve()
    if args.mode == 'prepare': prepare(out)
    else:
        need(args.seal, 'Exact prepared delta config seal')
        if args.mode == 'check': check(out, args.seal); print('GLOBAL776_MASKU1_CHECK_PASS_NO_EDA')
        else: namespace()['verify'](out, args.seal)
